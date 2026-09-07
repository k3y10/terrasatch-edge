"""Local voice checks and bounded QA retention for disposable radio audio."""

from __future__ import annotations

import shutil
import time
import wave
from dataclasses import dataclass
from pathlib import Path

from .radio_receiver import pcm_rms


def has_voice_activity(
    path: str | Path,
    *,
    rms_threshold: int = 180,
    min_voiced_fraction: float = 0.05,
    frame_ms: int = 30,
) -> bool:
    """Apply a cheap PCM energy VAD before invoking the speech model.

    Faster Whisper's VAD remains enabled for the higher-quality second opinion.
    This check intentionally errs toward retaining speech rather than requiring
    keywords or domain-specific content.
    """

    with wave.open(str(path), "rb") as wav:
        if wav.getnchannels() != 1 or wav.getsampwidth() != 2:
            return True
        frames_per_window = max(int(wav.getframerate() * frame_ms / 1000), 1)
        total = 0
        voiced = 0
        while True:
            pcm = wav.readframes(frames_per_window)
            if not pcm:
                break
            total += 1
            if pcm_rms(pcm) >= rms_threshold:
                voiced += 1
    if total == 0:
        return False
    return voiced / total >= min(max(min_voiced_fraction, 0.0), 1.0)


@dataclass(frozen=True)
class QaRetentionSettings:
    enabled: bool = False
    max_storage_mb: int = 500
    max_age_hours: float = 24.0
    max_files: int = 100

    @property
    def max_storage_bytes(self) -> int:
        return max(self.max_storage_mb, 0) * 1024 * 1024


class QaAudioRetention:
    def __init__(self, directory: str | Path, settings: QaRetentionSettings) -> None:
        self.directory = Path(directory)
        self.settings = settings

    def dispose_or_retain(self, path: str | Path) -> Path | None:
        candidate = Path(path)
        if not candidate.exists():
            return None
        if not self.settings.enabled:
            candidate.unlink(missing_ok=True)
            return None
        self.directory.mkdir(parents=True, exist_ok=True)
        destination = self.directory / candidate.name
        if candidate.resolve() != destination.resolve():
            shutil.move(str(candidate), str(destination))
        self.enforce_limits()
        return destination if destination.exists() else None

    def enforce_limits(self, *, now: float | None = None) -> None:
        if not self.directory.exists():
            return
        current = time.time() if now is None else now
        files = sorted(
            (item for item in self.directory.iterdir() if item.is_file()),
            key=lambda item: item.stat().st_mtime,
        )
        maximum_age = max(self.settings.max_age_hours, 0) * 3600
        if maximum_age:
            for item in list(files):
                if current - item.stat().st_mtime > maximum_age:
                    item.unlink(missing_ok=True)
                    files.remove(item)

        max_files = max(self.settings.max_files, 0)
        while len(files) > max_files:
            files.pop(0).unlink(missing_ok=True)

        maximum_bytes = self.settings.max_storage_bytes
        total = sum(item.stat().st_size for item in files)
        while files and total > maximum_bytes:
            oldest = files.pop(0)
            size = oldest.stat().st_size
            oldest.unlink(missing_ok=True)
            total -= size

    def storage_bytes(self) -> int:
        if not self.directory.exists():
            return 0
        return sum(item.stat().st_size for item in self.directory.iterdir() if item.is_file())
