import httpx
import pytest

from terrasatch_edge.repeater_directory import DirectoryCache, DirectoryError, DiscoveryQuery, OpenRepeaterProvider


RECORD = dict(id="a1b2c3d4-e5f6-7890-abcd-ef1234567890", callsign="GB3DA", frequency=145.6375,
              offset=-0.6, ctcss=118.8, mode="FM", status="active", city="Dartford",
              last_verified="2026-06-02")


def test_normalize_untrusted_metadata_cannot_enable_rx_tx_or_change_identity():
    target = OpenRepeaterProvider().normalize(RECORD | {"enabled": True, "transmit_authorized": True,
                                                      "organization_id": "evil", "api_key": "secret"})
    assert target.frequency_hz == 145637500
    assert target.repeater.input_frequency_hz == 145037500
    assert not target.enabled and not target.transmit_authorized and target.discovered
    assert "evil" not in target.model_dump_json()
    assert "secret" not in target.model_dump_json()


@pytest.mark.parametrize("changes", [dict(mode="DMR"), dict(status="inactive"), dict(frequency="bad"),
                                      dict(id="../../evil"), dict(offset="NaN"), dict(offset="bad"), dict(callsign="x"*201)])
def test_malformed_or_unsupported_provider_records(changes):
    with pytest.raises((ValueError, TypeError)):
        OpenRepeaterProvider().normalize(RECORD | changes)


def test_api_search_headers_bounds_and_malformed_rows():
    def handler(request):
        assert request.url.host == "www.openrepeater.org"
        assert request.headers["X-API-Key"] == "test-key"
        assert "test-key" not in str(request.url)
        assert float(request.url.params["radius"]) == 75
        return httpx.Response(200, json={"repeaters": [RECORD, {"bad": "row"}]})
    provider = OpenRepeaterProvider("test-key", transport=httpx.MockTransport(handler))
    query = DiscoveryQuery(latitude=40, longitude=-111)
    assert len(provider.search(query)) == 1


@pytest.mark.parametrize("payload", ["bad", 42, {"unexpected": []}, {"repeaters": "bad"}])
def test_unknown_envelope_fails_safely(payload):
    provider = OpenRepeaterProvider("test", transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)))
    with pytest.raises(DirectoryError):
        provider.search(DiscoveryQuery(region="Dartford"))


def test_cached_discovery_offline_fallback_and_expiry(tmp_path):
    calls = []
    def handler(request):
        calls.append(request)
        if len(calls) > 1:
            raise httpx.ConnectError("offline")
        return httpx.Response(200, json=[RECORD])
    provider = OpenRepeaterProvider("test", transport=httpx.MockTransport(handler))
    cache = DirectoryCache(tmp_path / "directory.sqlite")
    query = DiscoveryQuery(region="Dartford", location_source="region")
    first = cache.search(provider, query, now=100000)
    assert cache.search(provider, query, now=100001)["targets"] == first["targets"]
    assert len(calls) == 1
    stale = cache.search(provider, query, now=200000)
    assert stale["stale"] and stale["retrieved_at"] == first["retrieved_at"]
    assert not stale["targets"][0]["enabled"]


def test_daily_budget_persists_and_stops_network(tmp_path):
    calls = []
    provider = OpenRepeaterProvider("test", transport=httpx.MockTransport(
        lambda r: calls.append(r) or httpx.Response(200, json=[])))
    path = tmp_path / "cache.sqlite"
    for i in range(30):
        DirectoryCache(path).search(provider, DiscoveryQuery(region=f"city-{i}"), now=100000)
    with pytest.raises(DirectoryError, match="budget"):
        DirectoryCache(path).search(provider, DiscoveryQuery(region="extra"), now=100000)
    assert len(calls) == 30


def test_provider_rate_limit_blocks_new_queries_until_next_utc_day(tmp_path):
    calls = []
    provider = OpenRepeaterProvider("test", transport=httpx.MockTransport(
        lambda r: calls.append(r) or httpx.Response(429)))
    cache = DirectoryCache(tmp_path / "cache.sqlite")
    with pytest.raises(DirectoryError, match="rate limit"):
        cache.search(provider, DiscoveryQuery(region="one"), now=100000)
    with pytest.raises(DirectoryError, match="budget"):
        cache.search(provider, DiscoveryQuery(region="two"), now=100001)
    assert len(calls) == 1
    with pytest.raises(DirectoryError, match="rate limit"):
        cache.search(provider, DiscoveryQuery(region="two"), now=200000)
    assert len(calls) == 2


@pytest.mark.parametrize("values", [{}, {"latitude": 40}, {"latitude": 91, "longitude": 1},
                                     {"latitude": float("nan"), "longitude": 1}])
def test_location_requires_explicit_valid_context(values):
    with pytest.raises(ValueError):
        DiscoveryQuery(**values)
