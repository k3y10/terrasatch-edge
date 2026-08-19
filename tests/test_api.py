from __future__ import annotations

from pathlib import Path

import httpx
import pytest

import terrasatch_edge.api as edge_api
from terrasatch_edge.adapters import classify_device
from terrasatch_edge.api import TerraSatchApiClient, TerraSatchApiError, reported_capabilities
from terrasatch_edge.models import DeviceKind, HardwareDevice, SystemSnapshot


def _snapshot(*devices: HardwareDevice) -> SystemSnapshot:
    return SystemSnapshot(
        hostname="edge-test",
        platform="test",
        platform_release="1",
        architecture="x86_64",
        python_version="3.12",
        devices=list(devices),
    )


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


def test_rtl_receive_capability_requires_complete_receive_runtime(monkeypatch):
    receiver = classify_device(
        HardwareDevice(
            kind=DeviceKind.USB,
            name="Nooelec NESDR SMArt v5",
            identifier="usb:0bda:2838",
        )
    )
    monkeypatch.setattr(edge_api, "find_executable", lambda _name: None)

    capabilities = reported_capabilities(_snapshot(receiver))

    assert "rtl-sdr" in capabilities
    assert "nooelec" in capabilities
    assert "radio:receive" not in capabilities
    assert "audio:capture" not in capabilities


def test_rtl_test_and_fm_report_receive_and_demodulated_audio(monkeypatch):
    receiver = classify_device(
        HardwareDevice(
            kind=DeviceKind.USB,
            name="Nooelec NESDR SMArt v5",
            identifier="usb:0bda:2838",
        )
    )

    def fake_find(name: str):
        if name in {"rtl_test", "rtl_fm"}:
            return Path(f"/tools/{name}")
        return None

    monkeypatch.setattr(edge_api, "find_executable", fake_find)

    capabilities = reported_capabilities(_snapshot(receiver))

    assert "radio:receive" in capabilities
    assert "audio:capture" in capabilities
    assert "radio:transmit" not in capabilities


def test_partial_rtl_runtime_does_not_claim_receive_ready(monkeypatch):
    receiver = classify_device(
        HardwareDevice(
            kind=DeviceKind.USB,
            name="Nooelec NESDR SMArt v5",
            identifier="usb:0bda:2838",
        )
    )
    monkeypatch.setattr(
        edge_api,
        "find_executable",
        lambda name: Path("/tools/rtl_fm") if name == "rtl_fm" else None,
    )

    capabilities = reported_capabilities(_snapshot(receiver))

    assert "radio:receive" not in capabilities
    assert "audio:capture" not in capabilities


def test_hackrf_discovery_does_not_report_rx_or_tx(monkeypatch):
    receiver = classify_device(
        HardwareDevice(
            kind=DeviceKind.USB,
            name="HackRF One",
            identifier="usb:hackrf",
        )
    )
    monkeypatch.setattr(edge_api, "find_executable", lambda _name: None)

    capabilities = reported_capabilities(_snapshot(receiver))

    assert "hardware:hackrf" in capabilities
    assert "radio:receive" not in capabilities
    assert "radio:transmit" not in capabilities
