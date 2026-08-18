from __future__ import annotations

from pathlib import Path

import pytest

from terrasatch_edge.config import EdgeConfig
from terrasatch_edge.ingest import ingest_audio_file
from terrasatch_edge.speech import SpeechTranscript


class FakeProvider:
    def transcribe(self, audio_path, *, language=None, hotwords=None, initial_prompt=None):
        return SpeechTranscript(
            raw_text="Patrol Four reports shooting cracks.",
            normalized_text="Patrol Four reports shooting cracks.",
            language="en",
            language_confidence=0.96,
            provider="faster_whisper",
            model="base.en",
        )


class FakeClient:
    def __init__(self) -> None:
        self.payload = None

    def ingest_text(self, **kwargs):
        self.payload = kwargs
        return {"accepted": True}


def test_audio_ingest_preserves_stt_provenance_and_uses_canonical_text_endpoint(tmp_path: Path) -> None:
    audio = tmp_path / "radio.wav"
    audio.write_bytes(b"RIFF-fake")
    client = FakeClient()
    result = ingest_audio_file(
        client=client,
        config=EdgeConfig(site_id="site-1"),
        provider=FakeProvider(),
        audio_path=audio,
        callsign="Patrol 4",
        source_message_id="audio-1",
    )
    assert result.api_response == {"accepted": True}
    assert client.payload["site_id"] == "site-1"
    assert client.payload["text"] == "Patrol Four reports shooting cracks."
    assert client.payload["source"] == "terrasatch-edge-stt"
    assert client.payload["transcript_provider"] == "faster_whisper"
    assert client.payload["transcript_model"] == "base.en"
    assert client.payload["transcript_language"] == "en"
    assert client.payload["transcript_confidence"] == pytest.approx(0.96)


def test_audio_ingest_requires_site(tmp_path: Path) -> None:
    audio = tmp_path / "radio.wav"
    audio.write_bytes(b"RIFF-fake")
    with pytest.raises(ValueError, match="site"):
        ingest_audio_file(
            client=FakeClient(),
            config=EdgeConfig(site_id=None),
            provider=FakeProvider(),
            audio_path=audio,
        )
