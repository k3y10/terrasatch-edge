"""Provider-neutral local speech-to-text support for TerraSatch Edge."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Callable, Protocol

from pydantic import BaseModel, Field


class SpeechProviderUnavailable(RuntimeError):
    """Raised when an optional speech provider cannot be loaded."""


class SpeechProcessingError(RuntimeError):
    """Raised when audio cannot produce a usable transcript."""


class SpeechSegment(BaseModel):
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(ge=0)
    text: str
    confidence: float | None = Field(default=None, ge=0, le=1)


class SpeechTranscript(BaseModel):
    raw_text: str
    normalized_text: str
    language: str | None = None
    language_confidence: float | None = Field(default=None, ge=0, le=1)
    provider: str
    model: str
    segments: list[SpeechSegment] = Field(default_factory=list)


class SpeechToTextProvider(Protocol):
    def transcribe(
        self,
        audio_path: str | Path,
        *,
        language: str | None = None,
        hotwords: str | None = None,
        initial_prompt: str | None = None,
    ) -> SpeechTranscript: ...


def _probability_from_avg_logprob(value: Any) -> float | None:
    if not isinstance(value, (float, int)) or not math.isfinite(float(value)):
        return None
    return min(max(math.exp(float(value)), 0.0), 1.0)


class FasterWhisperSpeechProvider:
    """Lazy local faster-whisper provider suitable for CPU field nodes."""

    name = "faster_whisper"

    def __init__(
        self,
        *,
        model_name: str = "base.en",
        device: str = "cpu",
        compute_type: str = "int8",
        vad_filter: bool = True,
        local_files_only: bool = False,
        model_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self.vad_filter = vad_filter
        self.local_files_only = local_files_only
        self._model_factory = model_factory
        self._model: Any | None = None

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model
        factory = self._model_factory
        if factory is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise SpeechProviderUnavailable(
                    "faster-whisper is not installed; install TerraSatch Edge with the 'speech' extra"
                ) from exc
            factory = WhisperModel
        try:
            self._model = factory(
                self.model_name,
                device=self.device,
                compute_type=self.compute_type,
                local_files_only=self.local_files_only,
            )
        except Exception as exc:
            raise SpeechProviderUnavailable(
                f"Unable to load speech model '{self.model_name}': {exc}"
            ) from exc
        return self._model

    def transcribe(
        self,
        audio_path: str | Path,
        *,
        language: str | None = None,
        hotwords: str | None = None,
        initial_prompt: str | None = None,
    ) -> SpeechTranscript:
        path = Path(audio_path).expanduser()
        if not path.is_file():
            raise SpeechProcessingError(f"Audio file not found: {path}")

        model = self._load_model()
        try:
            segment_iter, info = model.transcribe(
                str(path),
                language=language,
                beam_size=1,
                vad_filter=self.vad_filter,
                word_timestamps=False,
                hotwords=hotwords,
                initial_prompt=initial_prompt,
            )
            raw_segments = list(segment_iter)
        except Exception as exc:
            raise SpeechProcessingError(f"Speech transcription failed: {exc}") from exc

        segments: list[SpeechSegment] = []
        text_parts: list[str] = []
        for item in raw_segments:
            text = str(getattr(item, "text", "")).strip()
            if not text:
                continue
            text_parts.append(text)
            segments.append(
                SpeechSegment(
                    start_seconds=max(float(getattr(item, "start", 0.0)), 0.0),
                    end_seconds=max(float(getattr(item, "end", 0.0)), 0.0),
                    text=text,
                    confidence=_probability_from_avg_logprob(
                        getattr(item, "avg_logprob", None)
                    ),
                )
            )

        raw_text = " ".join(text_parts).strip()
        normalized_text = " ".join(raw_text.split())
        if not normalized_text:
            raise SpeechProcessingError("No speech was detected in the audio segment")

        language_value = getattr(info, "language", None)
        language_probability = getattr(info, "language_probability", None)
        return SpeechTranscript(
            raw_text=raw_text,
            normalized_text=normalized_text,
            language=str(language_value) if language_value else language,
            language_confidence=(
                min(max(float(language_probability), 0.0), 1.0)
                if isinstance(language_probability, (float, int))
                else None
            ),
            provider=self.name,
            model=self.model_name,
            segments=segments,
        )
