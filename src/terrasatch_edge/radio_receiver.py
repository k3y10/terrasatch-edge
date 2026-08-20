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
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from .radio_profiles import RadioChannelProfile, bca_frs_channel
from .tooling import find_executable


class RadioReceiveError(RuntimeError):
    """Raised when the receive-only RTL-SDR adapter cannot capture a call."""


@dataclass(frozen=True)
class RadioReceiveSettings:
    channel: int
    output_sample_rate: int = 16_000
    demod_sample_rate: int = 24_000
    rtl_squelch: int = 20
    rtl_squelch_delay: int = 10
    gain_db: float | None = None
    read_chunk_seconds: float = 0.20
    end_gap_seconds: float = 0.90
    min_transmission_seconds: float = 0.40
    max_transmission_seconds: float = 30.0

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


def _finalize_capture(
    pcm_parts: list[bytes],
    *,
    output_path: Path,
    settings: RadioReceiveSettings,
    peak_rms: int,
    source_message_id: str,
) -> RadioAudioCapture:
    pcm = b"".join(pcm_parts)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(settings.output_sample_rate)
        wav.writeframes(pcm)
    duration_seconds = len(pcm) / float(settings.output_sample_rate * 2)
    return RadioAudioCapture(
        path=output_path,
        channel=settings.channel,
        duration_seconds=duration_seconds,
        peak_rms=peak_rms,
        source_message_id=source_message_id,
    )


def capture_one_transmission(
    settings: RadioReceiveSettings,
    *,
    output_path: str | Path,
    wait_timeout_seconds: float | None = None,
) -> RadioAudioCapture:
    """Capture one carrier-gated BCA/FRS transmission to a bounded WAV file.

    Upstream ``rtl_fm`` suppresses output when its squelch closes. The adapter
    therefore treats a sustained gap in the PCM pipe *after* audio has started
    as end-of-transmission instead of waiting for literal zero-valued silence.
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
    pcm_parts: list[bytes] = []
    peak_rms = 0
    transmission_started: float | None = None
    source_message_id = f"edge-radio-bca-ch{settings.channel:02d}-{uuid.uuid4()}"

    try:
        while True:
            if transmission_started is None:
                if wait_timeout_seconds is None:
                    timeout = 0.5
                else:
                    remaining = wait_timeout_seconds - (time.monotonic() - started_waiting)
                    if remaining <= 0:
                        raise RadioReceiveError(
                            f"No carrier-gated audio received on BCA/FRS channel {settings.channel} "
                            f"within {wait_timeout_seconds:g}s"
                        )
                    timeout = min(0.5, remaining)
            else:
                elapsed = time.monotonic() - transmission_started
                if elapsed >= settings.max_transmission_seconds:
                    if pcm_parts:
                        return _finalize_capture(
                            pcm_parts,
                            output_path=Path(output_path),
                            settings=settings,
                            peak_rms=peak_rms,
                            source_message_id=source_message_id,
                        )
                timeout = min(
                    settings.end_gap_seconds,
                    max(settings.max_transmission_seconds - elapsed, 0.01),
                )

            try:
                chunk = chunks.get(timeout=timeout)
            except queue.Empty:
                if transmission_started is None:
                    if process.poll() is not None:
                        stderr = process.stderr.read() if process.stderr else b""
                        detail = stderr.decode("utf-8", errors="replace")[-800:]
                        raise RadioReceiveError(
                            f"rtl_fm exited before audio was received (code {process.returncode})"
                            + (f": {detail}" if detail else "")
                        )
                    continue

                duration = sum(len(part) for part in pcm_parts) / float(bytes_per_second)
                if duration >= settings.min_transmission_seconds:
                    return _finalize_capture(
                        pcm_parts,
                        output_path=Path(output_path),
                        settings=settings,
                        peak_rms=peak_rms,
                        source_message_id=source_message_id,
                    )

                pcm_parts.clear()
                peak_rms = 0
                transmission_started = None
                started_waiting = time.monotonic()
                continue

            if chunk is None:
                if pcm_parts:
                    duration = sum(len(part) for part in pcm_parts) / float(bytes_per_second)
                    if duration >= settings.min_transmission_seconds:
                        return _finalize_capture(
                            pcm_parts,
                            output_path=Path(output_path),
                            settings=settings,
                            peak_rms=peak_rms,
                            source_message_id=source_message_id,
                        )
                stderr = process.stderr.read() if process.stderr else b""
                detail = stderr.decode("utf-8", errors="replace")[-800:]
                raise RadioReceiveError(
                    "rtl_fm stopped before a complete transmission was captured"
                    + (f": {detail}" if detail else "")
                )

            if transmission_started is None:
                transmission_started = time.monotonic()
            pcm_parts.append(chunk)
            peak_rms = max(peak_rms, pcm_rms(chunk))

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
