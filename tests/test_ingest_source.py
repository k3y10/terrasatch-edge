from __future__ import annotations

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


def test_default_stt_source_is_unchanged(tmp_path) -> None:
    audio = tmp_path / "radio.wav"
    audio.write_bytes(b"fake")
    client = FakeClient()
    ingest_audio_file(
        client=client,
        config=EdgeConfig(site_id="site-1"),
        provider=FakeProvider(),
        audio_path=audio,
    )
    assert client.payload["source"] == "terrasatch-edge-stt"


def test_radio_source_override_survives_ingestion(tmp_path) -> None:
    audio = tmp_path / "radio.wav"
    audio.write_bytes(b"fake")
    client = FakeClient()
    ingest_audio_file(
        client=client,
        config=EdgeConfig(site_id="site-1"),
        provider=FakeProvider(),
        audio_path=audio,
        source="terrasatch-edge-radio-bca-ch05",
    )
    assert client.payload["source"] == "terrasatch-edge-radio-bca-ch05"
