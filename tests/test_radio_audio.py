import os
import wave
from pathlib import Path

from terrasatch_edge.radio_audio import (
    QaAudioRetention,
    QaRetentionSettings,
    has_voice_activity,
)


def _wav(path: Path, amplitude: int, frames: int = 1600) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16_000)
        wav.writeframes(amplitude.to_bytes(2, "little", signed=True) * frames)


def test_voice_validation_rejects_silence_and_accepts_signal(tmp_path: Path) -> None:
    silence = tmp_path / "silence.wav"
    speech = tmp_path / "speech.wav"
    _wav(silence, 0)
    _wav(speech, 1200)
    assert not has_voice_activity(silence)
    assert has_voice_activity(speech)


def test_disposable_audio_is_removed(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.wav"
    _wav(candidate, 1000)
    retention = QaAudioRetention(tmp_path / "qa", QaRetentionSettings(enabled=False))
    assert retention.dispose_or_retain(candidate) is None
    assert not candidate.exists()


def test_qa_retention_enforces_age_count_and_quota_oldest_first(tmp_path: Path) -> None:
    qa = tmp_path / "qa"
    qa.mkdir()
    files = []
    for index in range(4):
        item = qa / f"{index}.wav"
        item.write_bytes(b"x" * 10)
        os.utime(item, (100 + index, 100 + index))
        files.append(item)
    retention = QaAudioRetention(
        qa,
        QaRetentionSettings(enabled=True, max_storage_mb=1, max_age_hours=1, max_files=2),
    )
    retention.enforce_limits(now=200)
    assert [item.name for item in sorted(qa.iterdir())] == ["2.wav", "3.wav"]

    quota = QaAudioRetention(
        qa,
        QaRetentionSettings(enabled=True, max_storage_mb=0, max_age_hours=1, max_files=10),
    )
    quota.enforce_limits(now=200)
    assert list(qa.iterdir()) == []
