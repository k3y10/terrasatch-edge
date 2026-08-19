import httpx

from terrasatch_edge.api import TerraSatchApiClient


def test_api_client_sends_stt_provenance(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_request(method, url, **kwargs):
        captured.update(kwargs["json"])
        return httpx.Response(200, json={"accepted": True}, request=httpx.Request(method, url))

    monkeypatch.setattr(httpx, "request", fake_request)
    client = TerraSatchApiClient("https://api.terrasatch.com", "key")
    client.ingest_text(
        site_id="site",
        text="hello",
        source_message_id="msg",
        transcript_provider="faster_whisper",
        transcript_model="base.en",
        transcript_language="en",
        transcript_confidence=0.91,
    )

    assert captured["transcript_provider"] == "faster_whisper"
    assert captured["transcript_model"] == "base.en"
    assert captured["transcript_language"] == "en"
    assert captured["transcript_confidence"] == 0.91
