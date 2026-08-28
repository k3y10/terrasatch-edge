"""Bounded receive-only RTL-SDR/BCA capture support."""

from __future__ import annotations

import array
import queue
import subprocess
import sys
import threading
import time
import uuid
import wave
from collections import deque
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import BinaryIO, Callable, Iterator

from .radio_profiles import RadioChannelProfile, bca_frs_channel
from .tooling import find_executable


class RadioReceiveError(RuntimeError):
    """Raised when the receive-only RTL-SDR adapter cannot capture a call."""


@dataclass(frozen=True)
class RadioReceiveSettings:
    channel: int
    device_index: int = 0
    output_sample_rate: int = 16_000
    demod_sample_rate: int = 24_000
    rtl_squelch: int = 20
    rtl_squelch_delay: int = 10
    gain_db: float | None = None
    read_chunk_seconds: float = 0.20
    end_gap_seconds: float = 0.90
    min_transmission_seconds: float = 0.40
    max_transmission_seconds: float = 30.0
    activity_rms_threshold: int = 180
    release_rms_threshold: int = 120

    @property
    def profile(self) -> RadioChannelProfile:
        return bca_frs_channel(self.channel)


@dataclass(frozen=True)
class RadioAudioCapture:
    path: Path
    channel: int
    duration_seconds: float
    peak_rms: int
    source_message_id: str
    started_at: datetime
    ended_at: datetime

    @property
    def duration_ms(self) -> int:
        return max(int(round(self.duration_seconds * 1000)), 0)


@dataclass(frozen=True)
class RadioCandidateRejection:
    reason: str
    duration_seconds: float
    peak_rms: int


@dataclass(frozen=True)
class SegmentedPcm:
    """One locally gated PCM transmission without its trailing quiet gap."""

    pcm: bytes
    peak_rms: int
    started_at: datetime


class PcmActivityGate:
    """Segment a continuous PCM stream using RMS hysteresis and an end gap.

    Some ``rtl_fm`` builds emit zeroed or low-energy PCM while their squelch is
    closed instead of pausing stdout. This gate therefore never treats byte
    availability as carrier activity.
    """

    def __init__(self, settings: RadioReceiveSettings) -> None:
        self.settings = settings
        self._parts: list[bytes] = []
        self._total_bytes = 0
        self._peak_rms = 0
        self._quiet_bytes = 0
        self._started_at: datetime | None = None

    @property
    def active(self) -> bool:
        return self._started_at is not None

    def _finish(self) -> SegmentedPcm | None:
        if self._started_at is None:
            return None
        pcm = b"".join(self._parts)
        if self._quiet_bytes:
            pcm = pcm[: -min(self._quiet_bytes, len(pcm))]
        result = SegmentedPcm(pcm=pcm, peak_rms=self._peak_rms, started_at=self._started_at)
        self._parts = []
        self._total_bytes = 0
        self._peak_rms = 0
        self._quiet_bytes = 0
        self._started_at = None
        return result

    def feed(self, chunk: bytes, *, observed_at: datetime | None = None) -> SegmentedPcm | None:
        """Consume one PCM chunk and return a completed transmission boundary."""

        level = pcm_rms(chunk)
        if not self.active:
            if level < self.settings.activity_rms_threshold:
                return None
            self._started_at = observed_at or datetime.now(UTC)

        self._parts.append(chunk)
        self._total_bytes += len(chunk)
        self._peak_rms = max(self._peak_rms, level)
        if level <= self.settings.release_rms_threshold:
            self._quiet_bytes += len(chunk)
        else:
            self._quiet_bytes = 0

        bytes_per_second = self.settings.output_sample_rate * 2
        total_seconds = self._total_bytes / float(bytes_per_second)
        quiet_seconds = self._quiet_bytes / float(bytes_per_second)
        if (
            total_seconds >= self.settings.max_transmission_seconds
            or quiet_seconds >= self.settings.end_gap_seconds
        ):
            return self._finish()
        return None

    def flush(self) -> SegmentedPcm | None:
        """Finish an active transmission when the upstream process stops."""

        return self._finish()


def pcm_rms(pcm: bytes) -> int:
    """Return RMS amplitude for little-endian signed 16-bit mono PCM."""

    usable = pcm[: len(pcm) - (len(pcm) % 2)]
    if not usable:
        return 0
    samples = array.array("h")
    samples.frombytes(usable)
    if sys.byteorder != "little":
        samples.byteswap()
    if not samples:
        return 0
    mean_square = sum(int(sample) * int(sample) for sample in samples) / len(samples)
    return int(mean_square**0.5)


def build_rtl_fm_command(
    settings: RadioReceiveSettings,
    *,
    executable: str | Path = "rtl_fm",
) -> list[str]:
    """Build the receive-only rtl_fm command for one BCA/FRS carrier."""

    if settings.rtl_squelch < 1:
        raise ValueError("rtl_fm squelch must be greater than zero for bounded capture")
    profile = settings.profile
    command = [
        str(executable),
        "-d",
        str(settings.device_index),
        "-M",
        "fm",
        "-f",
        str(profile.frequency_hz),
        "-s",
        str(settings.demod_sample_rate),
        "-r",
        str(settings.output_sample_rate),
        "-l",
        str(settings.rtl_squelch),
        "-t",
        str(settings.rtl_squelch_delay),
        "-E",
        "deemp",
        "-E",
        "dc",
    ]
    if settings.gain_db is not None:
        command.extend(["-g", f"{settings.gain_db:g}"])
    command.append("-")
    return command


def _pump_pcm(stream: BinaryIO, target: queue.Queue[bytes | None], chunk_size: int) -> None:
    try:
        while True:
            data = stream.read(chunk_size)
            if not data:
                break
            target.put(data)
    finally:
        target.put(None)


def _pump_stderr(stream: BinaryIO, tail: deque[bytes]) -> None:
    """Continuously drain rtl_fm diagnostics so its stderr pipe cannot fill."""

    while True:
        data = stream.read(256)
        if not data:
            return
        tail.append(data)


def _finalize_capture(
    pcm_parts: list[bytes],
    *,
    output_path: Path,
    settings: RadioReceiveSettings,
    peak_rms: int,
    source_message_id: str,
    started_at: datetime,
) -> RadioAudioCapture:
    pcm = b"".join(pcm_parts)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(settings.output_sample_rate)
        wav.writeframes(pcm)
    duration_seconds = len(pcm) / float(settings.output_sample_rate * 2)
    ended_at = started_at + timedelta(seconds=duration_seconds)
    return RadioAudioCapture(
        path=output_path,
        channel=settings.channel,
        duration_seconds=duration_seconds,
        peak_rms=peak_rms,
        source_message_id=source_message_id,
        started_at=started_at,
        ended_at=ended_at,
    )


class ContinuousRtlReceiver:
    """Keep one ``rtl_fm`` process open and yield bounded RF candidates."""

    def __init__(
        self,
        settings: RadioReceiveSettings,
        *,
        capture_path_factory: Callable[[], Path],
        min_peak_rms: int = 0,
        on_rejection: Callable[[RadioCandidateRejection], None] | None = None,
    ) -> None:
        activity_threshold = max(settings.activity_rms_threshold, min_peak_rms, 1)
        release_threshold = min(settings.release_rms_threshold, activity_threshold - 1)
        self.settings = replace(
            settings,
            activity_rms_threshold=activity_threshold,
            release_rms_threshold=release_threshold,
        )
        self.capture_path_factory = capture_path_factory
        self.on_rejection = on_rejection

    def _reject(self, reason: str, duration: float, peak_rms: int) -> None:
        if self.on_rejection is not None:
            self.on_rejection(
                RadioCandidateRejection(
                    reason=reason,
                    duration_seconds=duration,
                    peak_rms=peak_rms,
                )
            )

    def captures(self, stop_event: threading.Event) -> Iterator[RadioAudioCapture]:
        executable = find_executable("rtl_fm")
        if executable is None:
            raise RadioReceiveError(
                "rtl_fm executable not found; install rtl-sdr or configure TERRASATCH_EDGE_TOOLS"
            )
        try:
            process = subprocess.Popen(
                build_rtl_fm_command(self.settings, executable=executable),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
            )
        except OSError as exc:
            raise RadioReceiveError(f"Could not start rtl_fm: {exc}") from exc
        if process.stdout is None:
            process.kill()
            raise RadioReceiveError("rtl_fm did not expose a PCM output stream")

        bytes_per_second = self.settings.output_sample_rate * 2
        chunk_size = max(2, int(bytes_per_second * self.settings.read_chunk_seconds))
        if chunk_size % 2:
            chunk_size += 1
        chunks: queue.Queue[bytes | None] = queue.Queue(maxsize=64)
        reader = threading.Thread(
            target=_pump_pcm,
            args=(process.stdout, chunks, chunk_size),
            name="terrasatch-rtl-fm-reader",
            daemon=True,
        )
        reader.start()
        stderr_tail: deque[bytes] = deque(maxlen=8)
        stderr_reader: threading.Thread | None = None
        if process.stderr is not None:
            stderr_reader = threading.Thread(
                target=_pump_stderr,
                args=(process.stderr, stderr_tail),
                name="terrasatch-rtl-fm-stderr",
                daemon=True,
            )
            stderr_reader.start()

        gate = PcmActivityGate(self.settings)
        last_chunk_at: float | None = None

        def finish_candidate(segment: SegmentedPcm | None) -> RadioAudioCapture | None:
            if segment is None:
                return None
            duration = len(segment.pcm) / float(bytes_per_second)
            result: RadioAudioCapture | None = None
            if duration < self.settings.min_transmission_seconds:
                self._reject("short", duration, segment.peak_rms)
            elif segment.pcm:
                result = _finalize_capture(
                    [segment.pcm],
                    output_path=self.capture_path_factory(),
                    settings=self.settings,
                    peak_rms=segment.peak_rms,
                    source_message_id=(
                        f"edge-radio-bca-ch{self.settings.channel:02d}-{uuid.uuid4()}"
                    ),
                    started_at=segment.started_at,
                )
            return result

        try:
            while not stop_event.is_set():
                try:
                    chunk = chunks.get(timeout=0.25)
                except queue.Empty:
                    if (
                        gate.active
                        and last_chunk_at is not None
                        and time.monotonic() - last_chunk_at >= self.settings.end_gap_seconds
                    ):
                        candidate = finish_candidate(gate.flush())
                        last_chunk_at = None
                        if candidate is not None:
                            yield candidate
                        continue
                    if not gate.active and process.poll() is not None:
                        detail = b"".join(stderr_tail).decode("utf-8", errors="replace")[-800:]
                        raise RadioReceiveError(
                            f"rtl_fm exited while monitoring (code {process.returncode})"
                            + (f": {detail}" if detail else "")
                        )
                    continue
                if chunk is None:
                    candidate = finish_candidate(gate.flush())
                    if candidate is not None:
                        yield candidate
                    if stop_event.is_set():
                        break
                    detail = b"".join(stderr_tail).decode("utf-8", errors="replace")[-800:]
                    raise RadioReceiveError(
                        "rtl_fm stopped while continuous monitoring was active"
                        + (f": {detail}" if detail else "")
                    )
                candidate = finish_candidate(gate.feed(chunk))
                last_chunk_at = time.monotonic() if gate.active else None
                if candidate is not None:
                    yield candidate
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
            try:
                process.stdout.close()
            except OSError:
                pass
            if process.stderr is not None:
                try:
                    process.stderr.close()
                except OSError:
                    pass
            reader.join(timeout=1)
            if stderr_reader is not None:
                stderr_reader.join(timeout=1)


def capture_one_transmission(
    settings: RadioReceiveSettings,
    *,
    output_path: str | Path,
    wait_timeout_seconds: float | None = None,
) -> RadioAudioCapture:
    """Capture one RMS-gated BCA/FRS transmission to a bounded WAV file.

    The local RMS gate supports both ``rtl_fm`` behaviors seen in the field:
    pausing stdout when squelch closes and continuously emitting quiet PCM.
    """

    executable = find_executable("rtl_fm")
    if executable is None:
        raise RadioReceiveError(
            "rtl_fm executable not found; install rtl-sdr or configure TERRASATCH_EDGE_TOOLS"
        )

    command = build_rtl_fm_command(settings, executable=executable)
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
    except OSError as exc:
        raise RadioReceiveError(f"Could not start rtl_fm: {exc}") from exc

    if process.stdout is None:
        process.kill()
        raise RadioReceiveError("rtl_fm did not expose a PCM output stream")

    bytes_per_second = settings.output_sample_rate * 2
    chunk_size = max(2, int(bytes_per_second * settings.read_chunk_seconds))
    if chunk_size % 2:
        chunk_size += 1

    chunks: queue.Queue[bytes | None] = queue.Queue()
    reader = threading.Thread(
        target=_pump_pcm,
        args=(process.stdout, chunks, chunk_size),
        name="terrasatch-rtl-fm-reader",
        daemon=True,
    )
    reader.start()

    started_waiting = time.monotonic()
    gate = PcmActivityGate(settings)
    last_chunk_at: float | None = None
    source_message_id = f"edge-radio-bca-ch{settings.channel:02d}-{uuid.uuid4()}"

    def finish_segment(segment: SegmentedPcm | None) -> RadioAudioCapture | None:
        if segment is None:
            return None
        duration = len(segment.pcm) / float(bytes_per_second)
        if duration < settings.min_transmission_seconds:
            return None
        return _finalize_capture(
            [segment.pcm],
            output_path=Path(output_path),
            settings=settings,
            peak_rms=segment.peak_rms,
            source_message_id=source_message_id,
            started_at=segment.started_at,
        )

    try:
        while True:
            if not gate.active and wait_timeout_seconds is not None:
                remaining = wait_timeout_seconds - (time.monotonic() - started_waiting)
                if remaining <= 0:
                    raise RadioReceiveError(
                        f"No RMS-gated audio received on BCA/FRS channel {settings.channel} "
                        f"within {wait_timeout_seconds:g}s"
                    )
                timeout = min(0.25, remaining)
            else:
                timeout = 0.25

            try:
                chunk = chunks.get(timeout=timeout)
            except queue.Empty:
                if (
                    gate.active
                    and last_chunk_at is not None
                    and time.monotonic() - last_chunk_at >= settings.end_gap_seconds
                ):
                    capture = finish_segment(gate.flush())
                    last_chunk_at = None
                    if capture is not None:
                        return capture
                    started_waiting = time.monotonic()
                    source_message_id = f"edge-radio-bca-ch{settings.channel:02d}-{uuid.uuid4()}"
                    continue
                if not gate.active and process.poll() is not None:
                    stderr = process.stderr.read() if process.stderr else b""
                    detail = stderr.decode("utf-8", errors="replace")[-800:]
                    raise RadioReceiveError(
                        f"rtl_fm exited before audio was received (code {process.returncode})"
                        + (f": {detail}" if detail else "")
                    )
                continue

            if chunk is None:
                capture = finish_segment(gate.flush())
                if capture is not None:
                    return capture
                stderr = process.stderr.read() if process.stderr else b""
                detail = stderr.decode("utf-8", errors="replace")[-800:]
                raise RadioReceiveError(
                    "rtl_fm stopped before a complete transmission was captured"
                    + (f": {detail}" if detail else "")
                )

            segment = gate.feed(chunk)
            last_chunk_at = time.monotonic() if gate.active else None
            if segment is None:
                continue
            capture = finish_segment(segment)
            if capture is None:
                started_waiting = time.monotonic()
                source_message_id = f"edge-radio-bca-ch{settings.channel:02d}-{uuid.uuid4()}"
                continue
            return capture

    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        try:
            process.stdout.close()
        except OSError:
            pass
        if process.stderr is not None:
            try:
                process.stderr.close()
            except OSError:
                pass
        reader.join(timeout=1)
