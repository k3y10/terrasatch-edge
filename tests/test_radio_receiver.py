from __future__ import annotations

import wave
from datetime import UTC, datetime
from pathlib import Path

import pytest

from terrasatch_edge.radio_receiver import (
    PcmActivityGate,
    RadioReceiveSettings,
    _finalize_capture,
    build_rtl_fm_command,
    pcm_rms,
)


def _pcm(amplitude: int, *, samples: int = 200) -> bytes:
    return amplitude.to_bytes(2, "little", signed=True) * samples


def test_rtl_fm_command_tunes_exact_bca_channel_and_is_receive_only() -> None:
    settings = RadioReceiveSettings(channel=5, rtl_squelch=22, rtl_squelch_delay=10, gain_db=28.0)
    command = build_rtl_fm_command(settings, executable="/usr/bin/rtl_fm")
    assert command[:3] == ["/usr/bin/rtl_fm", "-d", "0"]
    assert command[command.index("-M") + 1] == "fm"
    assert command[command.index("-f") + 1] == "462662500"
    assert command[command.index("-r") + 1] == "16000"
    assert command[command.index("-l") + 1] == "22"
    assert command[command.index("-t") + 1] == "10"
    assert command[command.index("-g") + 1] == "28"
    assert command[-1] == "-"
    assert "tx" not in " ".join(command).lower()


def test_zero_squelch_is_rejected_for_bounded_capture() -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        build_rtl_fm_command(RadioReceiveSettings(channel=1, rtl_squelch=0))


def test_pcm_rms_detects_signal() -> None:
    silence = b"\x00\x00" * 100
    toneish = (1000).to_bytes(2, "little", signed=True) * 100
    assert pcm_rms(silence) == 0
    assert pcm_rms(toneish) == 1000


def test_pcm_gate_ignores_continuous_quiet_output() -> None:
    settings = RadioReceiveSettings(
        channel=5,
        output_sample_rate=1_000,
        end_gap_seconds=0.4,
        activity_rms_threshold=500,
        release_rms_threshold=200,
    )
    gate = PcmActivityGate(settings)
    for _ in range(10):
        assert gate.feed(_pcm(100)) is None
    assert not gate.active


def test_pcm_gate_closes_on_quiet_gap_and_trims_it() -> None:
    settings = RadioReceiveSettings(
        channel=5,
        output_sample_rate=1_000,
        end_gap_seconds=0.4,
        activity_rms_threshold=500,
        release_rms_threshold=200,
    )
    gate = PcmActivityGate(settings)
    started = datetime(2026, 8, 28, tzinfo=UTC)
    assert gate.feed(_pcm(1_000), observed_at=started) is None
    assert gate.feed(_pcm(900)) is None
    assert gate.feed(_pcm(100)) is None
    segment = gate.feed(_pcm(100))
    assert segment is not None
    assert segment.started_at == started
    assert segment.peak_rms == 1_000
    assert len(segment.pcm) == 800
    assert not gate.active


def test_pcm_gate_bounds_an_open_transmission() -> None:
    settings = RadioReceiveSettings(
        channel=5,
        output_sample_rate=1_000,
        max_transmission_seconds=0.6,
        activity_rms_threshold=500,
        release_rms_threshold=200,
    )
    gate = PcmActivityGate(settings)
    assert gate.feed(_pcm(1_000)) is None
    assert gate.feed(_pcm(1_000)) is None
    segment = gate.feed(_pcm(1_000))
    assert segment is not None
    assert len(segment.pcm) == 1_200


def test_pcm_gate_can_finish_when_squelch_pauses_stdout() -> None:
    settings = RadioReceiveSettings(
        channel=5,
        output_sample_rate=1_000,
        activity_rms_threshold=500,
        release_rms_threshold=200,
    )
    gate = PcmActivityGate(settings)
    assert gate.feed(_pcm(1_000)) is None
    assert gate.feed(_pcm(900)) is None
    segment = gate.flush()
    assert segment is not None
    assert len(segment.pcm) == 800
    assert segment.peak_rms == 1_000


def test_finalize_capture_writes_mono_16bit_wav(tmp_path: Path) -> None:
    settings = RadioReceiveSettings(channel=5, output_sample_rate=16_000)
    pcm = (500).to_bytes(2, "little", signed=True) * 16_000
    path = tmp_path / "capture.wav"
    result = _finalize_capture(
        [pcm],
        output_path=path,
        settings=settings,
        peak_rms=500,
        source_message_id="radio-1",
        started_at=datetime(2026, 8, 28, tzinfo=UTC),
    )
    assert result.duration_seconds == pytest.approx(1.0)
    assert result.channel == 5
    assert result.duration_ms == 1000
    assert result.ended_at > result.started_at
    with wave.open(str(path), "rb") as wav:
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        assert wav.getframerate() == 16_000
        assert wav.getnframes() == 16_000
