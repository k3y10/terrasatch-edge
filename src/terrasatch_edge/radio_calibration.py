"""Automatic RF calibration for the receive-only BCA/FRS pilot."""

from __future__ import annotations

import queue
import subprocess
import threading
import time
from dataclasses import dataclass, replace
from typing import BinaryIO, Callable, Sequence

from .radio_receiver import RadioReceiveError, RadioReceiveSettings, build_rtl_fm_command
from .tooling import find_executable


class RadioCalibrationError(RadioReceiveError):
    """Raised when Edge cannot establish a quiet RF baseline automatically."""


@dataclass(frozen=True)
class RadioCalibrationResult:
    settings: RadioReceiveSettings
    attempts: int
    mode: str

    @property
    def squelch(self) -> int:
        return self.settings.rtl_squelch

    @property
    def gain_db(self) -> float | None:
        return self.settings.gain_db


# Conservative R820T/R820T2 starting points. rtl_fm snaps requested gains to the
# nearest value supported by the connected tuner, so these remain portable
# across common RTL-SDR receivers without hard-coding one serial/device model.
AUTO_GAIN_CANDIDATES: tuple[float, ...] = (19.7, 12.5, 7.7, 0.0)
AUTO_SQUELCH_CANDIDATES: tuple[int, ...] = (30, 40, 50, 60, 70, 80, 90, 100)


def _pump_pcm(stream: BinaryIO, target: queue.Queue[bytes | None], chunk_size: int) -> None:
    try:
        while True:
            data = stream.read(chunk_size)
            if not data:
                break
            target.put(data)
    finally:
        target.put(None)


def probe_radio_activity(
    settings: RadioReceiveSettings,
    *,
    probe_seconds: float = 0.45,
    startup_grace_seconds: float = 0.35,
    minimum_activity_seconds: float = 0.12,
) -> bool:
    """Return True when rtl_fm still emits carrier-gated audio at these settings.

    The calibration deliberately probes rtl_fm's own squelch behavior instead
    of guessing from post-demodulated WAV volume. A quiet result means the
    selected gain/squelch pair closes on the current ambient RF environment.
    """

    if probe_seconds <= 0 or startup_grace_seconds < 0 or minimum_activity_seconds <= 0:
        raise ValueError("radio calibration timing values must be positive")

    executable = find_executable("rtl_fm")
    if executable is None:
        raise RadioCalibrationError("rtl_fm executable not found; cannot auto-calibrate radio")

    command = build_rtl_fm_command(settings, executable=executable)
    try:
        process = subprocess.Popen(
            command,
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

    chunks: queue.Queue[bytes | None] = queue.Queue()
    reader = threading.Thread(
        target=_pump_pcm,
        args=(process.stdout, chunks, chunk_size),
        name="terrasatch-rtl-fm-calibration-reader",
        daemon=True,
    )
    reader.start()

    def _stopped_detail(prefix: str) -> RadioCalibrationError:
        stderr = process.stderr.read() if process.stderr else b""
        detail = stderr.decode("utf-8", errors="replace")[-800:]
        return RadioCalibrationError(prefix + (f": {detail}" if detail else ""))

    try:
        # Drain startup transients before deciding whether the channel is open.
        grace_deadline = time.monotonic() + startup_grace_seconds
        while time.monotonic() < grace_deadline:
            remaining = grace_deadline - time.monotonic()
            try:
                chunk = chunks.get(timeout=max(0.01, min(0.05, remaining)))
            except queue.Empty:
                continue
            if chunk is None:
                raise _stopped_detail("rtl_fm stopped during RF calibration")

        activity_bytes = 0
        required_activity_bytes = max(2, int(bytes_per_second * minimum_activity_seconds))
        probe_deadline = time.monotonic() + probe_seconds

        while time.monotonic() < probe_deadline:
            remaining = probe_deadline - time.monotonic()
            try:
                chunk = chunks.get(timeout=max(0.01, min(0.05, remaining)))
            except queue.Empty:
                if process.poll() is not None:
                    raise _stopped_detail("rtl_fm exited during RF calibration")
                continue

            if chunk is None:
                raise _stopped_detail("rtl_fm stopped during RF calibration")

            activity_bytes += len(chunk)
            if activity_bytes >= required_activity_bytes:
                return True

        return False
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


def _lowest_quiet_squelch(
    settings: RadioReceiveSettings,
    *,
    gain_db: float,
    squelch_candidates: Sequence[int],
    activity_probe: Callable[[RadioReceiveSettings], bool],
) -> tuple[int | None, int]:
    """Binary-search the lowest squelch candidate that closes on ambient RF."""

    candidates = tuple(sorted(set(int(value) for value in squelch_candidates if 1 <= int(value) <= 100)))
    if not candidates:
        raise ValueError("at least one valid squelch candidate is required")

    low = 0
    high = len(candidates) - 1
    found: int | None = None
    attempts = 0

    while low <= high:
        middle = (low + high) // 2
        threshold = candidates[middle]
        probe_settings = replace(settings, gain_db=gain_db, rtl_squelch=threshold)
        attempts += 1
        active = activity_probe(probe_settings)
        if active:
            low = middle + 1
        else:
            found = threshold
            high = middle - 1

    return found, attempts


def auto_calibrate_radio(
    settings: RadioReceiveSettings,
    *,
    fixed_squelch: int | None = None,
    fixed_gain_db: float | None = None,
    gain_candidates: Sequence[float] = AUTO_GAIN_CANDIDATES,
    squelch_candidates: Sequence[int] = AUTO_SQUELCH_CANDIDATES,
    preferred_max_squelch: int = 90,
    activity_probe: Callable[[RadioReceiveSettings], bool] | None = None,
) -> RadioCalibrationResult:
    """Choose a quiet receive gain/squelch pair for the current RF environment.

    Manual CLI values remain authoritative. Supplying one value lets Edge
    calibrate only the missing half; supplying both skips probing entirely.
    """

    if fixed_squelch is not None and not 1 <= fixed_squelch <= 100:
        raise ValueError("fixed squelch must be between 1 and 100")
    if fixed_gain_db is not None and fixed_gain_db < 0:
        raise ValueError("fixed gain must be non-negative")

    probe = activity_probe or probe_radio_activity

    if fixed_squelch is not None and fixed_gain_db is not None:
        return RadioCalibrationResult(
            settings=replace(settings, rtl_squelch=fixed_squelch, gain_db=fixed_gain_db),
            attempts=0,
            mode="manual",
        )

    gains = (fixed_gain_db,) if fixed_gain_db is not None else tuple(float(value) for value in gain_candidates)
    if not gains:
        raise ValueError("at least one gain candidate is required")

    attempts = 0
    fallback: RadioCalibrationResult | None = None

    if fixed_squelch is not None:
        for gain in gains:
            probe_settings = replace(settings, gain_db=gain, rtl_squelch=fixed_squelch)
            attempts += 1
            if not probe(probe_settings):
                return RadioCalibrationResult(
                    settings=probe_settings,
                    attempts=attempts,
                    mode="auto-gain",
                )
        raise RadioCalibrationError(
            f"RF channel remained open at squelch {fixed_squelch}; "
            "reduce local RF noise or choose a higher manual squelch"
        )

    for gain in gains:
        quiet_squelch, used_attempts = _lowest_quiet_squelch(
            settings,
            gain_db=gain,
            squelch_candidates=squelch_candidates,
            activity_probe=probe,
        )
        attempts += used_attempts
        if quiet_squelch is None:
            continue

        result = RadioCalibrationResult(
            settings=replace(settings, gain_db=gain, rtl_squelch=quiet_squelch),
            attempts=attempts,
            mode="auto",
        )
        if quiet_squelch <= preferred_max_squelch:
            return result
        if fallback is None:
            fallback = result

    if fallback is not None:
        return fallback

    raise RadioCalibrationError(
        "Could not find a quiet RF baseline automatically; "
        "use --squelch/--gain-db for diagnostics"
    )
