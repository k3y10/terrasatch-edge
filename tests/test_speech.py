from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from terrasatch_edge.speech import (
    FasterWhisperSpeechProvider,
    SpeechProcessingError,
    SpeechProviderUnavailable,
)


class FakeSegment:
    def __init__(self, start: float, end: float, text: str, avg_logprob: float = -0.1) -> None:
        self.start = start
        self.end = end
        self.text = text
        self.avg_logprob = avg_logprob


class FakeModel:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def transcribe(self, path: str, **kwargs):
        self.calls.append({"path": path, **kwargs})
        return iter(
            [
                FakeSegment(0.0, 1.2, " Patrol Four reports"),
                FakeSegment(1.2, 2.4, "shooting cracks near Cardiff Bowl. "),
            ]
        ), SimpleNamespace(language="en", language_probability=0.99)


def test_faster_whisper_provider_normalizes_transcript_and_preserves_segments(tmp_path: Path) -> None:
    audio = tmp_path / "radio.wav"
    audio.write_bytes(b"RIFF-fake")
    fake_model = FakeModel()
    created: dict[str, object] = {}

    def factory(model_name: str, **kwargs):
        created["model_name"] = model_name
        created.update(kwargs)
        return fake_model

    provider = FasterWhisperSpeechProvider(
        model_name="base.en",
        device="cpu",
        compute_type="int8",
        model_factory=factory,
    )
    transcript = provider.transcribe(
        audio,
        language="en",
        hotwords="TerraSatch Cardiff Patrol",
        initial_prompt="Backcountry radio traffic.",
    )

    assert transcript.normalized_text == "Patrol Four reports shooting cracks near Cardiff Bowl."
    assert transcript.provider == "faster_whisper"
    assert transcript.model == "base.en"
    assert transcript.language == "en"
    assert transcript.language_confidence == pytest.approx(0.99)
    assert len(transcript.segments) == 2
    assert transcript.segments[0].confidence is not None
    assert created == {
        "model_name": "base.en",
        "device": "cpu",
        "compute_type": "int8",
        "local_files_only": False,
    }
    assert fake_model.calls[0]["beam_size"] == 1
    assert fake_model.calls[0]["vad_filter"] is True
    assert fake_model.calls[0]["hotwords"] == "TerraSatch Cardiff Patrol"


def test_speech_provider_reuses_loaded_model(tmp_path: Path) -> None:
    audio = tmp_path / "radio.wav"
    audio.write_bytes(b"RIFF-fake")
    created = 0

    def factory(*args, **kwargs):
        nonlocal created
        created += 1
        return FakeModel()

    provider = FasterWhisperSpeechProvider(model_factory=factory)
    provider.transcribe(audio)
    provider.transcribe(audio)
    assert created == 1


def test_missing_audio_is_rejected_before_model_load(tmp_path: Path) -> None:
    provider = FasterWhisperSpeechProvider(model_factory=lambda *a, **k: FakeModel())
    with pytest.raises(SpeechProcessingError, match="Audio file not found"):
        provider.transcribe(tmp_path / "missing.wav")


def test_empty_speech_is_rejected(tmp_path: Path) -> None:
    audio = tmp_path / "silent.wav"
    audio.write_bytes(b"RIFF-fake")

    class SilentModel:
        def transcribe(self, path: str, **kwargs):
            return iter([]), SimpleNamespace(language="en", language_probability=0.5)

    provider = FasterWhisperSpeechProvider(model_factory=lambda *a, **k: SilentModel())
    with pytest.raises(SpeechProcessingError, match="No speech was detected"):
        provider.transcribe(audio)


def test_model_load_failure_is_wrapped(tmp_path: Path) -> None:
    audio = tmp_path / "radio.wav"
    audio.write_bytes(b"RIFF-fake")

    def bad_factory(*args, **kwargs):
        raise RuntimeError("model cache unavailable")

    provider = FasterWhisperSpeechProvider(model_factory=bad_factory)
    with pytest.raises(SpeechProviderUnavailable, match="model cache unavailable"):
        provider.transcribe(audio)
