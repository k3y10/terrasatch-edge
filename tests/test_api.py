from __future__ import annotations

import httpx
import pytest

from terrasatch_edge.api import TerraSatchApiClient, TerraSatchApiError


def test_headers_include_bearer_key():
    client = TerraSatchApiClient("https://api.example", "abc123")
    assert client._headers()["Authorization"] == "Bearer abc123"


def test_base_url_is_normalized():
    client = TerraSatchApiClient("https://api.example/")
    assert client.base_url == "https://api.example"


def test_http_error_wraps(monkeypatch):
    def fake_request(*args, **kwargs):
        return httpx.Response(401, request=httpx.Request("GET", "https://api.example/test"), text="denied")

    monkeypatch.setattr(httpx, "request", fake_request)
    client = TerraSatchApiClient("https://api.example", "bad")
    with pytest.raises(TerraSatchApiError, match="401"):
        client.identity()
