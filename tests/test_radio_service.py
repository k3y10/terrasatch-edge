from __future__ import annotations

import threading
import time
import wave
from datetime import UTC, datetime, timedelta
from pathlib import Path

from terrasatch_edge.config import EdgeConfig
from terrasatch_edge.radio_receiver import RadioAudioCapture, RadioCandidateRejection
from terrasatch_edge.radio_service import RadioMonitorService, resolve_radio_config
from terrasatch_edge.speech import SpeechProcessingError, SpeechTranscript


def _write_wav(path: Path, amplitude: int = 1200) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16_000)
        wav.writeframes(amplitude.to_bytes(2, "little", signed=True) * 16_000)


def _capture(path: Path, source_id: str, *, amplitude: int = 1200) -> RadioAudioCapture:
    _write_wav(path, amplitude)
    started = datetime.now(UTC)
    return RadioAudioCapture(
        path=path,
        channel=5,
        duration_seconds=1.0,
        peak_rms=amplitude,
        source_message_id=source_id,
        started_at=started,
        ended_at=started + timedelta(seconds=1),
    )


class FakeProvider:
    def __init__(self, gate: threading.Event | None = None) -> None:
        self.gate = gate
        self.entered = threading.Event()

    def transcribe(self, _path, *, language=None, hotwords=None, initial_prompt=None):
        self.entered.set()
        if self.gate is not None:
            self.gate.wait(5)
        return SpeechTranscript(
            raw_text="Division Alpha reports a wind shift.",
            normalized_text="Division Alpha reports a wind shift.",
            language="en",
            provider="faster_whisper",
            model="base.en",
        )


class FakeClient:
    def __init__(self, failures: int = 0) -> None:
        self.failures = failures
        self.payloads = []

    def ingest_text(self, **payload):
        self.payloads.append(payload)
        if self.failures:
            self.failures -= 1
            from terrasatch_edge.api import TerraSatchApiError

            raise TerraSatchApiError("offline")
        return {"duplicate": False}


def _wait_for(predicate, timeout: float = 5) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition was not reached")


def test_remote_radio_config_overrides_defaults_and_preserves_groups() -> None:
    edge = EdgeConfig(radio_channel=2)
    resolved = resolve_radio_config(
        edge,
        {
            "radio": {
                "profile": "bca-frs-na",
                "receivers": [{"name": "wasatch-rx-01", "device_index": 1, "channels": [5]}],
                "processing": {"min_transmission_seconds": 0.75, "keep_audio": False},
                "qa": {"enabled": True, "max_files": 10},
                "groups": {"rescue": {"channel": 9, "privacy_code": 11, "priority": "emergency"}},
            }
        },
    )
    assert resolved.config.receivers[0].channels == [5]
    assert resolved.config.processing.min_transmission_seconds == 0.75
    assert resolved.config.qa.max_files == 10
    assert resolved.config.groups["rescue"].priority == "emergency"


def test_malformed_remote_radio_config_falls_back_safely() -> None:
    resolved = resolve_radio_config(EdgeConfig(radio_channel=7), {"radio": "bad"})
    assert resolved.config.receivers[0].channels == [7]
    assert resolved.warnings

    invalid_nested = resolve_radio_config(
        EdgeConfig(radio_channel=7),
        {"radio": {"processing": {"min_transmission_seconds": -1}}},
    )
    assert invalid_nested.config.processing.min_transmission_seconds == 0.4
    assert invalid_nested.warnings


def test_receiver_keeps_accepting_candidates_while_transcription_is_busy(tmp_path: Path) -> None:
    captures = [
        _capture(tmp_path / "one.wav", "source-1"),
        _capture(tmp_path / "two.wav", "source-2"),
    ]
    yielded = []

    class Receiver:
        def captures(self, stop_event):
            for item in captures:
                yielded.append(item.source_message_id)
                yield item

    def factory(_settings, _path_factory, _minimum, _on_rejection):
        return Receiver()

    gate = threading.Event()
    provider = FakeProvider(gate)
    client = FakeClient()
    config = resolve_radio_config(
        EdgeConfig(site_id="site-1", device_id="device-1", radio_channel=5),
        {"radio": {"processing": {"vad_enabled": False}}},
    ).config
    service = RadioMonitorService(
        edge_config=EdgeConfig(site_id="site-1", device_id="device-1", radio_channel=5),
        monitor_config=config,
        provider=provider,
        client=client,
        receiver_factory=factory,
        state_dir=tmp_path / "state",
    )
    service.start()
    assert provider.entered.wait(2)
    _wait_for(lambda: len(yielded) == 2)
    gate.set()
    _wait_for(lambda: service.status()["accepted"] == 2)
    _wait_for(lambda: service.status()["api_delivered"] == 2)
    service.stop()
    service.wait()
    assert service.status()["receiver_state"] == "STOPPED"
    assert not captures[0].path.exists()
    assert client.payloads[0]["source_message_id"] == "source-1"
    assert client.payloads[0]["started_at"].endswith("+00:00")
    assert client.payloads[0]["rf_metadata"]["duration_ms"] == 1000
    assert client.payloads[0]["rf_metadata"]["snr_db"] is None


def test_no_speech_is_nonfatal_and_audio_is_cleaned_up(tmp_path: Path) -> None:
    capture = _capture(tmp_path / "silent.wav", "source-silent", amplitude=0)

    class Receiver:
        def captures(self, _stop_event):
            yield capture

    class NoSpeechProvider:
        def transcribe(self, *_args, **_kwargs):
            raise SpeechProcessingError("No speech was detected in the audio segment")

    config = resolve_radio_config(
        EdgeConfig(site_id="site-1", radio_channel=5),
        {"radio": {"processing": {"vad_enabled": False}}},
    ).config
    service = RadioMonitorService(
        edge_config=EdgeConfig(site_id="site-1", radio_channel=5),
        monitor_config=config,
        provider=NoSpeechProvider(),
        client=FakeClient(),
        receiver_factory=lambda *_args: Receiver(),
        state_dir=tmp_path / "state",
    )
    service.start()
    _wait_for(lambda: service.status()["no_speech_rejected"] == 1)
    assert service.status()["receiver_state"] == "RUNNING"
    service.stop()
    service.wait()
    assert not capture.path.exists()
    assert service.outbox.depth() == 0


def test_api_failure_leaves_stable_item_in_durable_outbox(tmp_path: Path) -> None:
    capture = _capture(tmp_path / "offline.wav", "stable-source-id")

    class Receiver:
        def captures(self, _stop_event):
            yield capture

    config = resolve_radio_config(
        EdgeConfig(site_id="site-1", radio_channel=5),
        {"radio": {"processing": {"vad_enabled": False}}},
    ).config
    service = RadioMonitorService(
        edge_config=EdgeConfig(site_id="site-1", radio_channel=5),
        monitor_config=config,
        provider=FakeProvider(),
        client=FakeClient(failures=1),
        receiver_factory=lambda *_args: Receiver(),
        state_dir=tmp_path / "state",
    )
    service.start()
    _wait_for(lambda: service.status()["api_failed"] == 1)
    service.stop()
    service.wait()
    assert service.outbox.depth() == 1
    assert service.outbox.due(now=10**12).source_message_id == "stable-source-id"


def test_rf_gate_rejection_counters_distinguish_short_and_weak_candidates(tmp_path: Path) -> None:
    config = resolve_radio_config(EdgeConfig(site_id="site-1", radio_channel=5)).config
    service = RadioMonitorService(
        edge_config=EdgeConfig(site_id="site-1", radio_channel=5),
        monitor_config=config,
        provider=FakeProvider(),
        client=FakeClient(),
        state_dir=tmp_path / "state",
    )
    service._on_rejection(RadioCandidateRejection("short", 0.1, 800))
    service._on_rejection(RadioCandidateRejection("signal", 1.0, 20))
    status = service.status()
    assert status["short_rejected"] == 1
    assert status["signal_rejected"] == 1
    assert status["rf_candidates"] == 0


def test_restart_delivers_existing_outbox_item_with_same_source_id(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    edge = EdgeConfig(site_id="site-1", radio_channel=5)
    config = resolve_radio_config(edge).config
    first = RadioMonitorService(
        edge_config=edge,
        monitor_config=config,
        provider=FakeProvider(),
        client=FakeClient(),
        state_dir=state_dir,
    )
    first.outbox.enqueue(
        "restart-source-id",
        {
            "site_id": "site-1",
            "text": "Persisted valid transcript",
            "source": "terrasatch-edge-radio-bca-ch05",
            "source_message_id": "restart-source-id",
        },
    )

    class QuietReceiver:
        def captures(self, _stop_event):
            return iter(())

    client = FakeClient()
    restarted = RadioMonitorService(
        edge_config=edge,
        monitor_config=config,
        provider=FakeProvider(),
        client=client,
        receiver_factory=lambda *_args: QuietReceiver(),
        state_dir=state_dir,
    )
    restarted.start()
    _wait_for(lambda: restarted.status()["api_delivered"] == 1)
    restarted.stop()
    restarted.wait()
    assert restarted.outbox.depth() == 0
    assert client.payloads[0]["source_message_id"] == "restart-source-id"
