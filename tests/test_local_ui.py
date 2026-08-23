from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

import terrasatch_edge.local_ui as local_ui
from terrasatch_edge.config import EdgeConfig, load_api_key, load_config, save_config
from terrasatch_edge.models import EdgeDevice, PairingClaim, SystemSnapshot


OPERATOR_HEADERS = {"X-TerraSatch-Edge-UI": "1"}


def _snapshot() -> SystemSnapshot:
    return SystemSnapshot(
        hostname="edge-test",
        platform="Linux",
        platform_release="test",
        architecture="x86_64",
        python_version="3.12",
        devices=[],
    )


def _configure_paths(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TERRASATCH_EDGE_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("TERRASATCH_EDGE_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("TERRASATCH_EDGE_API_KEY", raising=False)


def test_mutating_routes_require_operator_header(tmp_path, monkeypatch):
    _configure_paths(tmp_path, monkeypatch)
    save_config(EdgeConfig())
    monkeypatch.setattr(local_ui, "scan_hardware", lambda include_network=False: _snapshot())

    client = TestClient(local_ui.build_app())
    response = client.post("/api/scan")

    assert response.status_code == 403
    assert "operator confirmation" in response.json()["detail"].lower()


def test_config_update_preserves_pairing_assignment(tmp_path, monkeypatch):
    _configure_paths(tmp_path, monkeypatch)
    save_config(
        EdgeConfig(
            api_url="https://api.terrasatch.com",
            device_id="device-1",
            organization_id="org-1",
            site_id="site-1",
            site_name="Field Site",
            node_name="old-node",
        )
    )

    client = TestClient(local_ui.build_app())
    response = client.put(
        "/api/config",
        headers=OPERATOR_HEADERS,
        json={
            "node_name": "field-kit-07",
            "scan_interval_seconds": 45,
            "speech_model": "small.en",
        },
    )

    assert response.status_code == 200
    saved = load_config()
    assert saved.node_name == "field-kit-07"
    assert saved.scan_interval_seconds == 45
    assert saved.speech_model == "small.en"
    assert saved.device_id == "device-1"
    assert saved.organization_id == "org-1"
    assert saved.site_id == "site-1"
    assert saved.site_name == "Field Site"


def test_config_update_rejects_non_http_api_url(tmp_path, monkeypatch):
    _configure_paths(tmp_path, monkeypatch)
    save_config(EdgeConfig())

    client = TestClient(local_ui.build_app())
    response = client.put(
        "/api/config",
        headers=OPERATOR_HEADERS,
        json={"api_url": "file:///tmp/not-an-api"},
    )

    assert response.status_code == 422
    assert load_config().api_url == "https://api.terrasatch.com"


def test_pairing_claim_saves_device_credential_and_assignment(tmp_path, monkeypatch):
    _configure_paths(tmp_path, monkeypatch)
    save_config(EdgeConfig(api_url="https://api.terrasatch.com", node_name="edge-test"))
    monkeypatch.setattr(local_ui, "scan_hardware", lambda include_network=False: _snapshot())

    device = EdgeDevice(
        id="device-2",
        organization_id="org-2",
        site_id="site-2",
        name="paired-edge",
    )

    class FakeClient:
        def __init__(self, base_url: str, api_key: str | None = None, timeout: float = 10.0) -> None:
            self.base_url = base_url
            self.api_key = api_key

        def claim_pairing(self, device_code: str) -> PairingClaim:
            assert device_code == "pair-code"
            return PairingClaim(status="approved", token="device-secret", device=device)

        def heartbeat(self, snapshot: SystemSnapshot) -> dict[str, object]:
            assert snapshot.hostname == "edge-test"
            assert self.api_key == "device-secret"
            return {"ok": True}

    monkeypatch.setattr(local_ui, "TerraSatchApiClient", FakeClient)

    client = TestClient(local_ui.build_app())
    response = client.post(
        "/api/pairing/claim",
        headers=OPERATOR_HEADERS,
        json={"device_code": "pair-code"},
    )

    assert response.status_code == 200
    assert response.json()["paired"] is True
    assert response.json()["heartbeat"] is True
    assert load_api_key() == "device-secret"
    saved = load_config()
    assert saved.device_id == "device-2"
    assert saved.organization_id == "org-2"
    assert saved.site_id == "site-2"
    assert saved.node_name == "paired-edge"
