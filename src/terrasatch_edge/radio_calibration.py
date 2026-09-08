"""Linux-compatible automatic RF calibration for RTL-SDR radio monitoring."""

from __future__ import annotations

import queue
import subprocess
import threading
import time
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

from .radio_receiver import (
    RadioReceiveError,
    RadioReceiveSettings,
    _pump_pcm,
    _pump_stderr,
    build_rtl_fm_command,
    pcm_rms,
)
from .tooling import find_executable


class RadioCalibrationError(RadioReceiveError):
    """Raised when Edge cannot sample the configured RTL-SDR receiver."""


@dataclass(frozen=True)
class RadioNoiseSample:
    """Observed quiet-channel PCM levels for one gain/squelch pair."""

    levels: tuple[int, ...]

    @property
    def noise_floor_rms(self) -> int:
        if not self.levels:
            return 0
        ordered = sorted(self.levels)
        index = min(int(round((len(ordered) - 1) * 0.90)), len(ordered) - 1)
        return ordered[index]


@dataclass(frozen=True)
class RadioCalibrationResult:
    """Resolved RF and local PCM gate settings."""

    settings: RadioReceiveSettings
    attempts: int
    mode: str
    noise_floor_rms: int

    @property
    def activity_rms_threshold(self) -> int:
        return self.settings.activity_rms_threshold

    @property
    def release_rms_threshold(self) -> int:
        return self.settings.release_rms_threshold


AUTO_GAIN_CANDIDATES: tuple[float, ...] = (19.7, 12.5, 7.7, 0.0)
AUTO_SQUELCH_CANDIDATES: tuple[int, ...] = (30, 40, 50, 60, 70, 80, 90, 100)

NoiseProbe = Callable[[RadioReceiveSettings], RadioNoiseSample]


def probe_radio_noise(
    settings: RadioReceiveSettings,
    *,
    probe_seconds: float = 0.40,
    startup_grace_seconds: float = 0.30,
) -> RadioNoiseSample:
    """Measure PCM RMS even when rtl_fm continuously emits squelched samples."""

    if probe_seconds <= 0 or startup_grace_seconds < 0:
        raise ValueError("radio calibration timing values must be positive")
    executable = find_executable("rtl_fm")
    if executable is None:
        raise RadioCalibrationError("rtl_fm executable not found; cannot auto-calibrate radio")
    try:
        process = subprocess.Popen(
            build_rtl_fm_command(settings, executable=executable),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
    except OSError as exc:
        raise RadioCalibrationError(f"Could not start rtl_fm for calibration: {exc}") from exc
    if process.stdout is None:
        process.kill()
        raise RadioCalibrationError("rtl_fm did not expose PCM during calibration")

    bytes_per_second = settings.output_sample_rate * 2
    chunk_size = max(2, int(bytes_per_second * 0.10))
    if chunk_size % 2:
        chunk_size += 1
    chunks: queue.Queue[bytes | None] = queue.Queue(maxsize=64)
    reader = threading.Thread(
        target=_pump_pcm,
        args=(process.stdout, chunks, chunk_size),
        name="terrasatch-radio-calibration-pcm",
        daemon=True,
    )
    reader.start()
    stderr_tail: deque[bytes] = deque(maxlen=8)
    stderr_reader: threading.Thread | None = None
    if process.stderr is not None:
        stderr_reader = threading.Thread(
            target=_pump_stderr,
            args=(process.stderr, stderr_tail),
            name="terrasatch-radio-calibration-stderr",
            daemon=True,
        )
        stderr_reader.start()

    levels: list[int] = []
    started = time.monotonic()
    grace_deadline = started + startup_grace_seconds
    deadline = grace_deadline + probe_seconds
    try:
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            try:
                chunk = chunks.get(timeout=max(0.01, min(0.05, remaining)))
            except queue.Empty:
                if process.poll() is not None:
                    detail = b"".join(stderr_tail).decode("utf-8", errors="replace")[-800:]
                    raise RadioCalibrationError(
                        f"rtl_fm exited during RF calibration (code {process.returncode})"
                        + (f": {detail}" if detail else "")
                    )
                continue
            if chunk is None:
                detail = b"".join(stderr_tail).decode("utf-8", errors="replace")[-800:]
                raise RadioCalibrationError(
                    "rtl_fm stopped during RF calibration" + (f": {detail}" if detail else "")
                )
            if time.monotonic() >= grace_deadline:
                levels.append(pcm_rms(chunk))
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1)
        try:
            process.stdout.close()
        except OSError:
            pass
        if process.stderr is not None:
            try:
                process.stderr.close()
            except OSError:
                pass
        reader.join(timeout=0.5)
        if stderr_reader is not None:
            stderr_reader.join(timeout=0.5)
    return RadioNoiseSample(tuple(levels))


def _thresholds(settings: RadioReceiveSettings, noise_floor: int) -> tuple[int, int]:
    activity = max(
        settings.activity_rms_threshold,
        noise_floor + max(120, int(noise_floor * 0.15)),
    )
    release = max(
        settings.release_rms_threshold,
        noise_floor + max(60, int(noise_floor * 0.05)),
    )
    return min(activity, 32_767), min(release, activity - 1)


def auto_calibrate_radio(
    settings: RadioReceiveSettings,
    *,
    fixed_squelch: int | None = None,
    fixed_gain_db: float | None = None,
    gain_candidates: Sequence[float] = AUTO_GAIN_CANDIDATES,
    squelch_candidates: Sequence[int] = AUTO_SQUELCH_CANDIDATES,
    preferred_max_squelch: int = 90,
    quiet_rms: int = 64,
    noise_probe: NoiseProbe | None = None,
    probe_seconds: float = 0.40,
) -> RadioCalibrationResult:
    """Choose a quiet RF pair and derive hysteretic local PCM gate levels."""

    if fixed_squelch is not None and not 1 <= fixed_squelch <= 100:
        raise ValueError("fixed squelch must be between 1 and 100")
    if fixed_gain_db is not None and fixed_gain_db < 0:
        raise ValueError("fixed gain must be non-negative")
    gains = (
        (float(fixed_gain_db),)
        if fixed_gain_db is not None
        else tuple(float(value) for value in gain_candidates)
    )
    squelches = (
        (int(fixed_squelch),)
        if fixed_squelch is not None
        else tuple(sorted(set(int(value) for value in squelch_candidates)))
    )
    if not gains or not squelches:
        raise ValueError("auto-calibration requires gain and squelch candidates")
    probe = noise_probe or (
        lambda candidate: probe_radio_noise(candidate, probe_seconds=probe_seconds)
    )

    attempts = 0
    observed: list[tuple[RadioReceiveSettings, RadioNoiseSample]] = []
    fallback: tuple[RadioReceiveSettings, RadioNoiseSample] | None = None
    for gain in gains:
        low = 0
        high = len(squelches) - 1
        quiet: tuple[RadioReceiveSettings, RadioNoiseSample] | None = None
        while low <= high:
            middle = (low + high) // 2
            candidate = replace(settings, gain_db=gain, rtl_squelch=squelches[middle])
            sample = probe(candidate)
            attempts += 1
            observed.append((candidate, sample))
            if sample.noise_floor_rms <= quiet_rms:
                quiet = (candidate, sample)
                high = middle - 1
            else:
                low = middle + 1
        if quiet is None:
            continue
        if quiet[0].rtl_squelch <= preferred_max_squelch:
            selected = quiet
            mode = "auto"
            break
        if fallback is None:
            fallback = quiet
    else:
        if fallback is not None:
            selected = fallback
            mode = "auto-high-squelch"
        elif observed:
            selected = min(observed, key=lambda item: item[1].noise_floor_rms)
            mode = "adaptive-rms"
        else:
            raise RadioCalibrationError("RF calibration did not produce any PCM samples")

    noise_floor = selected[1].noise_floor_rms
    activity, release = _thresholds(settings, noise_floor)
    calibrated = replace(
        selected[0],
        activity_rms_threshold=activity,
        release_rms_threshold=release,
    )
    return RadioCalibrationResult(
        settings=calibrated,
        attempts=attempts,
        mode=mode,
        noise_floor_rms=noise_floor,
    )
