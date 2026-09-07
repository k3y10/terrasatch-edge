"""Persistent continuous radio monitor with decoupled local workers."""

from __future__ import annotations

import json
import logging
import queue
import signal
import threading
import time
import uuid
from copy import deepcopy
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field, ValidationError, model_validator

from .api import TerraSatchApiClient, TerraSatchApiError
from .config import EdgeConfig, get_paths, load_remote_config
from .radio_audio import QaAudioRetention, QaRetentionSettings, has_voice_activity
from .radio_calibration import RadioCalibrationResult
from .radio_outbox import RadioOutbox, RadioOutboxFull
from .radio_profiles import BCA_FRS_NA_PROFILE, bca_frs_channel
from .radio_receiver import (
    ContinuousRtlReceiver,
    RadioAudioCapture,
    RadioCandidateRejection,
    RadioReceiveSettings,
)
from .speech import SpeechProcessingError, SpeechToTextProvider
from .radio_context import radio_source

logger = logging.getLogger(__name__)


class RadioReceiverConfig(BaseModel):
    name: str = Field(default="primary", min_length=1, max_length=100)
    device_index: int = Field(default=0, ge=0, le=32)
    sdr_serial: str | None = Field(default=None, max_length=255)
    channels: list[int] = Field(default_factory=list, min_length=1, max_length=22)
    privacy_code: int | None = Field(default=None, ge=0, le=121)


class RadioProcessingConfig(BaseModel):
    min_transmission_seconds: float = Field(default=0.5, gt=0, le=10)
    max_transmission_seconds: float = Field(default=30, ge=1, le=300)
    end_gap_seconds: float = Field(default=0.9, gt=0, le=10)
    auto_calibrate: bool = True
    calibration_seconds: float = Field(default=0.4, gt=0, le=10)
    min_peak_rms: int = Field(default=180, ge=0, le=32_767)
    release_rms_threshold: int = Field(default=120, ge=0, le=32_767)
    vad_enabled: bool = True
    vad_rms_threshold: int = Field(default=180, ge=0, le=32_767)
    discard_no_speech: bool = True
    keep_audio: bool = False
    candidate_queue_max: int = Field(default=32, ge=1, le=1000)
    outbox_max_items: int = Field(default=1000, ge=1, le=100_000)

    @model_validator(mode="after")
    def validate_window(self) -> RadioProcessingConfig:
        if self.max_transmission_seconds < self.min_transmission_seconds:
            raise ValueError("maximum radio duration must not be shorter than minimum duration")
        if self.release_rms_threshold >= self.min_peak_rms and self.min_peak_rms > 0:
            self.release_rms_threshold = self.min_peak_rms - 1
        return self


class RadioQaConfig(BaseModel):
    enabled: bool = False
    max_storage_mb: int = Field(default=500, ge=0, le=100_000)
    max_age_hours: float = Field(default=24, ge=0, le=8760)
    max_files: int = Field(default=100, ge=0, le=100_000)


class RadioGroupConfig(BaseModel):
    channel: int = Field(ge=1, le=22)
    privacy_code: int | None = Field(default=None, ge=0, le=121)
    priority: str | None = Field(default=None, max_length=64)


class RadioMonitorConfig(BaseModel):
    enabled: bool = True
    mode: str = Field(default="continuous", pattern="^(continuous|foreground)$")
    profile: str = BCA_FRS_NA_PROFILE
    receivers: list[RadioReceiverConfig] = Field(min_length=1)
    processing: RadioProcessingConfig = Field(default_factory=RadioProcessingConfig)
    qa: RadioQaConfig = Field(default_factory=RadioQaConfig)
    groups: dict[str, RadioGroupConfig] = Field(default_factory=dict)
    logical_channel_id: str | None = None
    channel_bindings: dict[int, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_bindings(self) -> RadioMonitorConfig:
        if any(channel not in range(1, 23) or not value.strip()
               for channel, value in self.channel_bindings.items()):
            raise ValueError("Channel bindings require BCA channels 1-22 and nonempty logical IDs")
        if self.profile != BCA_FRS_NA_PROFILE:
            raise ValueError("No implemented receiver provider for this radio profile")
        return self

    def channel_id_for(self, channel: int) -> str | None:
        if self.channel_bindings:
            return self.channel_bindings.get(channel)
        # Legacy binding applies only to the configured carrier, never arbitrary captures.
        if channel == self.receivers[0].channels[0]:
            return self.logical_channel_id
        return None


@dataclass(frozen=True)
class ResolvedRadioConfig:
    config: RadioMonitorConfig
    warnings: tuple[str, ...] = ()


def resolve_radio_config(
    edge_config: EdgeConfig,
    remote_config: dict[str, Any] | None = None,
) -> ResolvedRadioConfig:
    """Safely overlay the existing remote control-plane radio section on defaults."""

    channel = edge_config.radio_channel or 5
    base: dict[str, Any] = {
        "enabled": True,
        "mode": "continuous",
        "profile": edge_config.radio_profile,
        "receivers": [{"name": "primary", "device_index": 0, "channels": [channel]}],
        "processing": {
            "min_transmission_seconds": edge_config.radio_min_transmission_seconds,
            "max_transmission_seconds": edge_config.radio_max_transmission_seconds,
            "end_gap_seconds": edge_config.radio_silence_seconds,
            "auto_calibrate": edge_config.radio_auto_calibrate,
            "calibration_seconds": edge_config.radio_calibration_seconds,
            "min_peak_rms": edge_config.radio_min_peak_rms,
            "release_rms_threshold": edge_config.radio_release_rms_threshold,
            "vad_enabled": edge_config.radio_vad_enabled,
            "vad_rms_threshold": edge_config.radio_vad_rms_threshold,
            "discard_no_speech": True,
            "keep_audio": edge_config.radio_keep_audio,
            "candidate_queue_max": edge_config.radio_candidate_queue_max,
            "outbox_max_items": edge_config.radio_outbox_max_items,
        },
        "qa": {
            "enabled": edge_config.radio_qa_enabled,
            "max_storage_mb": edge_config.radio_qa_max_storage_mb,
            "max_age_hours": edge_config.radio_qa_max_age_hours,
            "max_files": edge_config.radio_qa_max_files,
        },
    }
    local_defaults = deepcopy(base)
    warnings: list[str] = []
    radio = (remote_config or {}).get("radio")
    if radio is not None and not isinstance(radio, dict):
        warnings.append("Ignored malformed remote radio configuration: expected an object")
        radio = None
        base["enabled"] = False
    if isinstance(radio, dict):
        if radio.get("receive_enabled") is False:
            base["enabled"] = False
        for key in ("enabled", "mode", "profile", "receivers", "groups", "logical_channel_id", "channel_bindings"):
            if key in radio:
                base[key] = radio[key]
        for section in ("processing", "qa"):
            value = radio.get(section)
            if value is not None and not isinstance(value, dict):
                warnings.append(f"Ignored malformed remote radio.{section}: expected an object")
            elif isinstance(value, dict):
                base[section] = {**base[section], **value}
        if "keep_audio" in radio:
            base["processing"] = {**base["processing"], "keep_audio": radio["keep_audio"]}
        # The existing API console stores its binding under radio.ai_channel.
        # Use it only when its physical frequency matches the configured RX carrier.
        ai = radio.get("ai_channel")
        if (isinstance(ai, dict) and ai.get("logical_channel_id")
                and "logical_channel_id" not in radio and "channel_bindings" not in radio):
            receivers = base.get("receivers")
            try:
                selected = receivers[0]["channels"][0]
                expected_frequency = bca_frs_channel(selected).frequency_hz
            except (KeyError, IndexError, TypeError, ValueError):
                expected_frequency = None
            if expected_frequency is not None and ai.get("frequency_hz") == expected_frequency:
                base["channel_bindings"] = {selected: ai["logical_channel_id"]}
            else:
                warnings.append("Satchy logical channel has no matching physical RX frequency; left unbound")
    if isinstance(radio, dict) and radio.get("receive_enabled") is False:
        base["enabled"] = False
    try:
        resolved = RadioMonitorConfig.model_validate(base)
    except ValidationError as exc:
        warnings.append(f"Ignored invalid remote radio configuration: {exc.errors()[0]['msg']}")
        resolved = RadioMonitorConfig.model_validate({**local_defaults, "enabled": False})
    if len(resolved.receivers) > 1 or any(len(item.channels) > 1 for item in resolved.receivers):
        warnings.append(
            "Continuous vNext currently monitors the first configured receiver/channel only; "
            "additional entries are reserved for Phase 2 channelization"
        )
    return ResolvedRadioConfig(config=resolved, warnings=tuple(warnings))


@dataclass
class RadioCounters:
    receiver_state: str = "STOPPED"
    started_at: str | None = None
    uptime_seconds: int = 0
    rf_candidates: int = 0
    short_rejected: int = 0
    signal_rejected: int = 0
    tone_rejected: int = 0
    no_speech_rejected: int = 0
    transcribed: int = 0
    accepted: int = 0
    api_delivered: int = 0
    api_failed: int = 0
    outbox_depth: int = 0
    qa_storage_bytes: int = 0
    last_rf_at: str | None = None
    last_valid_transmission_at: str | None = None
    api_status: str = "UNKNOWN"
    last_error: str | None = None


class CandidateReceiver(Protocol):
    def captures(self, stop_event: threading.Event) -> Iterator[RadioAudioCapture]: ...


ReceiverFactory = Callable[
    [
        RadioReceiveSettings,
        Callable[[], Path],
        int,
        Callable[[RadioCandidateRejection], None],
    ],
    CandidateReceiver,
]


def _default_receiver_factory(
    settings: RadioReceiveSettings,
    path_factory: Callable[[], Path],
    min_peak_rms: int,
    on_rejection: Callable[[RadioCandidateRejection], None],
) -> CandidateReceiver:
    return ContinuousRtlReceiver(
        settings,
        capture_path_factory=path_factory,
        min_peak_rms=min_peak_rms,
        on_rejection=on_rejection,
    )


class RadioMonitorService:
    """Run receiver, transcription, and API delivery as independent workers."""

    def __init__(
        self,
        *,
        edge_config: EdgeConfig,
        monitor_config: RadioMonitorConfig,
        provider: SpeechToTextProvider,
        client: TerraSatchApiClient,
        callsign: str | None = None,
        hotwords: str | None = None,
        calibration: RadioCalibrationResult | None = None,
        receiver_factory: ReceiverFactory = _default_receiver_factory,
        state_dir: str | Path | None = None,
    ) -> None:
        self.edge_config = edge_config
        self.config = monitor_config
        self.provider = provider
        self.client = client
        self.callsign = callsign
        self.hotwords = hotwords
        self.calibration = calibration
        self.receiver_factory = receiver_factory
        self.state_dir = Path(state_dir or get_paths().state_dir)
        self.capture_dir = self.state_dir / "radio-processing"
        self.status_path = self.state_dir / "radio-status.json"
        self.stop_request_path = self.state_dir / "radio-stop.request"
        self.outbox = RadioOutbox(
            self.state_dir / "radio-outbox.sqlite3",
            max_items=self.config.processing.outbox_max_items,
        )
        qa_enabled = self.config.qa.enabled or self.config.processing.keep_audio
        self.qa = QaAudioRetention(
            self.state_dir / "radio-qa",
            QaRetentionSettings(
                enabled=qa_enabled,
                max_storage_mb=self.config.qa.max_storage_mb,
                max_age_hours=self.config.qa.max_age_hours,
                max_files=self.config.qa.max_files,
            ),
        )
        self.stop_event = threading.Event()
        self.candidates: queue.Queue[RadioAudioCapture] = queue.Queue(
            maxsize=self.config.processing.candidate_queue_max
        )
        self.counters = RadioCounters(outbox_depth=self.outbox.depth())
        self._lock = threading.Lock()
        self._threads: list[threading.Thread] = []
        self._last_rejection_log = 0.0
        self._started_monotonic: float | None = None

    @property
    def receiver_config(self) -> RadioReceiverConfig:
        return self.config.receivers[0]

    @property
    def channel(self) -> int:
        return self.receiver_config.channels[0]

    def _capture_path(self) -> Path:
        self.capture_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        return self.capture_dir / f"bca-ch{self.channel:02d}-{stamp}-{uuid.uuid4().hex[:8]}.wav"

    def _log(self, event: str, **fields: Any) -> None:
        logger.info(json.dumps({"event": event, **fields}, default=str, sort_keys=True))

    def _update(self, **values: Any) -> None:
        with self._lock:
            for name, value in values.items():
                setattr(self.counters, name, value)
            if self._started_monotonic is not None:
                self.counters.uptime_seconds = max(
                    int(time.monotonic() - self._started_monotonic), 0
                )
            self.counters.outbox_depth = self.outbox.depth()
            self.counters.qa_storage_bytes = self.qa.storage_bytes()
            payload = self._status_payload()
            self.status_path.parent.mkdir(parents=True, exist_ok=True)
            self.status_path.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

    def status(self) -> dict[str, Any]:
        self._update()
        with self._lock:
            return self._status_payload()

    def _status_payload(self) -> dict[str, Any]:
        calibration = self.calibration
        return {
            **asdict(self.counters),
            "receiver": self.receiver_config.name,
            "profile": self.config.profile,
            "channel": self.channel,
            "frequency_hz": bca_frs_channel(self.channel).frequency_hz,
            "audio_retention": "QA" if self.qa.settings.enabled else "OFF",
            "calibration_mode": calibration.mode if calibration else "manual",
            "calibration_attempts": calibration.attempts if calibration else 0,
            "noise_floor_rms": calibration.noise_floor_rms if calibration else None,
            "activity_rms_threshold": self.config.processing.min_peak_rms,
            "release_rms_threshold": self.config.processing.release_rms_threshold,
            "gain_db": self.edge_config.radio_gain_db,
            "squelch": self.edge_config.radio_squelch,
        }

    def _on_rejection(self, rejection: RadioCandidateRejection) -> None:
        field = "short_rejected" if rejection.reason == "short" else "signal_rejected"
        with self._lock:
            setattr(self.counters, field, getattr(self.counters, field) + 1)
        now = time.monotonic()
        if now - self._last_rejection_log >= 30:
            self._last_rejection_log = now
            self._log(
                "radio.candidate.rejected",
                receiver=self.receiver_config.name,
                channel=self.channel,
                frequency=bca_frs_channel(self.channel).frequency_hz,
                duration=rejection.duration_seconds,
                filter_stage="rf_gate",
                reject_reason=rejection.reason,
            )
        self._update()

    def _receiver_worker(self) -> None:
        settings = RadioReceiveSettings(
            channel=self.channel,
            device_index=self.receiver_config.device_index,
            output_sample_rate=self.edge_config.radio_output_sample_rate,
            demod_sample_rate=self.edge_config.radio_demod_sample_rate,
            rtl_squelch=self.edge_config.radio_squelch,
            rtl_squelch_delay=self.edge_config.radio_squelch_delay,
            gain_db=self.edge_config.radio_gain_db,
            read_chunk_seconds=self.edge_config.radio_chunk_seconds,
            end_gap_seconds=self.config.processing.end_gap_seconds,
            min_transmission_seconds=self.config.processing.min_transmission_seconds,
            max_transmission_seconds=self.config.processing.max_transmission_seconds,
            activity_rms_threshold=self.config.processing.min_peak_rms,
            release_rms_threshold=self.config.processing.release_rms_threshold,
        )
        receiver = self.receiver_factory(
            settings,
            self._capture_path,
            self.config.processing.min_peak_rms,
            self._on_rejection,
        )
        self._update(receiver_state="RUNNING")
        self._log(
            "radio.receiver.started",
            receiver=self.receiver_config.name,
            channel=self.channel,
            frequency=settings.profile.frequency_hz,
        )
        try:
            for capture in receiver.captures(self.stop_event):
                if self.stop_event.is_set():
                    self.qa.dispose_or_retain(capture.path)
                    break
                now = datetime.now(UTC).isoformat()
                with self._lock:
                    self.counters.rf_candidates += 1
                    self.counters.last_rf_at = now
                self._log(
                    "radio.candidate.detected",
                    receiver=self.receiver_config.name,
                    channel=self.channel,
                    candidate_id=capture.source_message_id,
                    duration=capture.duration_seconds,
                )
                try:
                    self.candidates.put(capture, timeout=0.1)
                except queue.Full:
                    with self._lock:
                        self.counters.signal_rejected += 1
                    self.qa.dispose_or_retain(capture.path)
                    self._log(
                        "radio.candidate.rejected",
                        candidate_id=capture.source_message_id,
                        filter_stage="candidate_queue",
                        reject_reason="queue_full",
                    )
                self._update()
        except Exception as exc:
            self._update(receiver_state="DEGRADED", last_error=str(exc))
            self._log("radio.receiver.failed", error_type=type(exc).__name__, error=str(exc))
            self.stop_event.set()

    def _payload_for(self, capture: RadioAudioCapture, transcript: Any) -> dict[str, Any]:
        profile = bca_frs_channel(capture.channel)
        privacy_code = self.receiver_config.privacy_code
        return {
            "site_id": self.edge_config.site_id,
            "text": transcript.raw_text,
            "callsign": self.callsign,
            "source_message_id": capture.source_message_id,
            "source": radio_source(self.edge_config.source, capture.channel),
            "channel_id": self.config.channel_id_for(capture.channel),
            "started_at": capture.started_at.isoformat(),
            "ended_at": capture.ended_at.isoformat(),
            "transcript_provider": transcript.provider,
            "transcript_model": transcript.model,
            "transcript_language": transcript.language,
            "transcript_confidence": transcript.language_confidence,
            "rf_metadata": {
                "receiver_device_id": self.edge_config.device_id,
                "receiver_name": self.receiver_config.name,
                "sdr_index": self.receiver_config.device_index,
                "sdr_serial": self.receiver_config.sdr_serial,
                "radio_profile": self.config.profile,
                "channel": capture.channel,
                "frequency_hz": profile.frequency_hz,
                "privacy_code": privacy_code,
                "privacy_code_source": "configured" if privacy_code is not None else None,
                "ctcss_hz": None,
                "tone_detected": False,
                "peak_rms": capture.peak_rms,
                "signal_dbfs": None,
                "snr_db": None,
                "duration_ms": capture.duration_ms,
            },
        }

    def _processing_worker(self) -> None:
        while not self.stop_event.is_set() or not self.candidates.empty():
            try:
                capture = self.candidates.get(timeout=0.25)
            except queue.Empty:
                continue
            try:
                if self.config.processing.vad_enabled and not has_voice_activity(
                    capture.path,
                    rms_threshold=self.config.processing.vad_rms_threshold,
                ):
                    with self._lock:
                        self.counters.no_speech_rejected += 1
                    self._log(
                        "radio.candidate.rejected",
                        candidate_id=capture.source_message_id,
                        filter_stage="audio_validation",
                        reject_reason="no_speech",
                    )
                    continue
                try:
                    transcript = self.provider.transcribe(
                        capture.path,
                        language=self.edge_config.speech_language,
                        hotwords=self.hotwords,
                        initial_prompt="Authorized TerraSatch field radio traffic and configured terminology.",
                    )
                except SpeechProcessingError as exc:
                    if "no speech" in str(exc).lower():
                        with self._lock:
                            self.counters.no_speech_rejected += 1
                        self._log(
                            "radio.candidate.rejected",
                            candidate_id=capture.source_message_id,
                            filter_stage="transcription",
                            reject_reason="no_speech",
                        )
                        continue
                    raise
                with self._lock:
                    self.counters.transcribed += 1
                self._log(
                    "radio.transcription.completed",
                    candidate_id=capture.source_message_id,
                    duration=capture.duration_seconds,
                )
                payload = self._payload_for(capture, transcript)
                try:
                    created = self.outbox.enqueue(capture.source_message_id, payload)
                except RadioOutboxFull as exc:
                    self._update(receiver_state="DEGRADED", last_error=str(exc))
                    self._log(
                        "radio.transmission.queue_full",
                        source_message_id=capture.source_message_id,
                        outbox_depth=self.outbox.depth(),
                    )
                    continue
                if created:
                    with self._lock:
                        self.counters.accepted += 1
                        self.counters.last_valid_transmission_at = datetime.now(UTC).isoformat()
                    self._log(
                        "radio.transmission.queued",
                        source_message_id=capture.source_message_id,
                        outbox_depth=self.outbox.depth(),
                    )
            except Exception as exc:
                self._update(last_error=str(exc))
                self._log(
                    "radio.processing.failed",
                    candidate_id=capture.source_message_id,
                    error_type=type(exc).__name__,
                )
            finally:
                self.qa.dispose_or_retain(capture.path)
                self.candidates.task_done()
                self._update()

    def _delivery_worker(self) -> None:
        while not self.stop_event.is_set():
            item = self.outbox.due()
            if item is None:
                self.stop_event.wait(0.25)
                continue
            try:
                self.client.ingest_text(**item.payload)
            except (TerraSatchApiError, OSError, ValueError) as exc:
                self.outbox.failed(item.source_message_id, str(exc))
                with self._lock:
                    self.counters.api_failed += 1
                self._update(api_status="OFFLINE", last_error=str(exc))
                self._log(
                    "radio.outbox.retry",
                    source_message_id=item.source_message_id,
                    outbox_depth=self.outbox.depth(),
                    api_status="offline",
                )
                continue
            self.outbox.delivered(item.source_message_id)
            with self._lock:
                self.counters.api_delivered += 1
            self._update(api_status="ONLINE", last_error=None)
            self._log(
                "radio.transmission.delivered",
                source_message_id=item.source_message_id,
                outbox_depth=self.outbox.depth(),
                api_status="online",
            )

    def start(self) -> None:
        if not self.config.enabled:
            raise RuntimeError("Radio monitoring is disabled by configuration")
        if not self.edge_config.site_id:
            raise RuntimeError("A paired TerraSatch site is required for radio monitoring")
        if any(thread.is_alive() for thread in self._threads):
            raise RuntimeError("Radio monitor is already running")
        if self.stop_event.is_set():
            raise RuntimeError("Create a new monitor instance after stopping")
        self.stop_request_path.unlink(missing_ok=True)
        self.qa.enforce_limits()
        self._started_monotonic = time.monotonic()
        self._update(
            receiver_state="STARTING",
            started_at=datetime.now(UTC).isoformat(),
            last_error=None,
        )
        self._threads = [
            threading.Thread(target=self._receiver_worker, name="radio-receiver", daemon=True),
            threading.Thread(target=self._processing_worker, name="radio-processing", daemon=True),
            threading.Thread(target=self._delivery_worker, name="radio-outbox", daemon=True),
        ]
        for thread in self._threads:
            thread.start()

    def stop(self, *_args: object) -> None:
        self.stop_event.set()

    def wait(self) -> None:
        try:
            while not self.stop_event.wait(0.25):
                if self.stop_request_path.exists():
                    self.stop_event.set()
                    break
                self._update()
        finally:
            for thread in self._threads:
                thread.join(timeout=10)
            self.stop_request_path.unlink(missing_ok=True)
            self._update(receiver_state="STOPPED")
            self._log("radio.receiver.stopped", receiver=self.receiver_config.name)

    def run_forever(self, *, install_signal_handlers: bool = True) -> None:
        if install_signal_handlers:
            try:
                signal.signal(signal.SIGINT, self.stop)
                if hasattr(signal, "SIGTERM"):
                    signal.signal(signal.SIGTERM, self.stop)
            except ValueError:
                pass
        self.start()
        self.wait()


def load_resolved_radio_config(edge_config: EdgeConfig) -> ResolvedRadioConfig:
    return resolve_radio_config(edge_config, load_remote_config())


def read_radio_status(state_dir: str | Path | None = None) -> dict[str, Any]:
    path = Path(state_dir or get_paths().state_dir) / "radio-status.json"
    if not path.exists():
        return {"receiver_state": "STOPPED", "outbox_depth": 0, "api_status": "UNKNOWN"}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {"receiver_state": "UNKNOWN"}
    except (OSError, json.JSONDecodeError):
        return {"receiver_state": "UNKNOWN", "last_error": "Radio status file is unreadable"}


def request_radio_stop(state_dir: str | Path | None = None) -> Path:
    path = Path(state_dir or get_paths().state_dir) / "radio-stop.request"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(datetime.now(UTC).isoformat() + "\n", encoding="utf-8")
    return path
