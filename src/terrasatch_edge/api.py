from __future__ import annotations

from typing import Any

import httpx

from . import __version__
from .models import ApiIdentity, EdgeDevice, PairingClaim, PairingStart, SiteSummary, SystemSnapshot
from .tooling import find_executable


class TerraSatchApiError(RuntimeError):
    pass


_RADIO_CAPABILITY_ALIASES = {
    "radio_rx",
    "radio_tx",
    "radio:receive",
    "radio:rx",
    "radio:transmit",
    "radio:tx",
    "rx",
    "tx",
    "receive",
    "transmit",
    "ptt",
    "audio:capture",
}


def reported_capabilities(snapshot: SystemSnapshot) -> list[str]:
    capabilities: set[str] = set()
    rtl_detected = False
    direct_audio_detected = False

    for device in snapshot.devices:
        device_capabilities = {str(item) for item in device.capabilities}
        normalized = {item.lower() for item in device_capabilities}
        rtl_detected = rtl_detected or bool({"rtl-sdr", "nooelec"} & normalized)
        direct_audio_detected = direct_audio_detected or "audio_input" in normalized
        for capability in device_capabilities:
            if capability.lower() not in _RADIO_CAPABILITY_ALIASES:
                capabilities.add(capability)

    rtl_receive_ready = (
        rtl_detected
        and find_executable("rtl_test") is not None
        and find_executable("rtl_fm") is not None
    )
    if rtl_receive_ready:
        capabilities.update({"radio:receive", "audio:capture"})
    if direct_audio_detected:
        capabilities.add("audio:capture")
    return sorted(capabilities)


class TerraSatchApiClient:
    def __init__(self, base_url: str, api_key: str | None = None, timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = {"User-Agent": f"terrasatch-edge/{__version__}"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = httpx.request(
                method,
                f"{self.base_url}{path}",
                headers=self._headers(),
                timeout=self.timeout,
                **kwargs,
            )
        except httpx.HTTPError as exc:
            raise TerraSatchApiError(str(exc)) from exc
        if response.status_code >= 400:
            detail = response.text.strip()[:500]
            raise TerraSatchApiError(
                f"HTTP {response.status_code}: {detail or response.reason_phrase}"
            )
        return response

    def health(self) -> dict[str, Any]:
        response = self._request("GET", "/health")
        try:
            payload = response.json()
            return payload if isinstance(payload, dict) else {"value": payload}
        except ValueError:
            return {"status": "ok", "body": response.text[:500]}

    def identity(self) -> ApiIdentity:
        response = self._request("GET", "/api/v1/auth/me")
        payload = response.json()
        if not isinstance(payload, dict):
            raise TerraSatchApiError("Unexpected /api/v1/auth/me response")
        return ApiIdentity(raw=payload)

    def sites(self) -> list[SiteSummary]:
        response = self._request("GET", "/api/v1/sites")
        payload = response.json()
        rows: list[dict[str, Any]]
        if isinstance(payload, list):
            rows = [row for row in payload if isinstance(row, dict)]
        elif isinstance(payload, dict):
            candidate = payload.get("items") or payload.get("sites") or payload.get("data") or []
            rows = (
                [row for row in candidate if isinstance(row, dict)]
                if isinstance(candidate, list)
                else []
            )
        else:
            rows = []

        sites: list[SiteSummary] = []
        for row in rows:
            site_id = row.get("id") or row.get("site_id")
            name = row.get("name") or row.get("display_name") or site_id
            if site_id and name:
                sites.append(
                    SiteSummary(
                        id=str(site_id),
                        name=str(name),
                        enabled=bool(row.get("enabled", True)),
                        raw=row,
                    )
                )
        return sites

    def start_pairing(
        self,
        *,
        name: str,
        hostname: str,
        platform_name: str,
        architecture: str,
    ) -> PairingStart:
        response = self._request(
            "POST",
            "/api/v1/edge/pairings",
            json={
                "name": name,
                "hostname": hostname,
                "platform": platform_name,
                "architecture": architecture,
                "agent_version": __version__,
            },
        )
        return PairingStart.model_validate(response.json())

    def claim_pairing(self, device_code: str) -> PairingClaim:
        response = self._request(
            "POST",
            "/api/v1/edge/pairings/token",
            json={"device_code": device_code},
        )
        return PairingClaim.model_validate(response.json())

    def edge_me(self) -> EdgeDevice:
        return EdgeDevice.model_validate(self._request("GET", "/api/v1/edge/me").json())

    def heartbeat(
        self,
        snapshot: SystemSnapshot,
        *,
        telemetry: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        capabilities = reported_capabilities(snapshot)
        inventory = [device.model_dump(mode="json") for device in snapshot.devices]
        response = self._request(
            "POST",
            "/api/v1/edge/heartbeat",
            json={
                "agent_version": __version__,
                "hardware_inventory": inventory,
                "capabilities": capabilities,
                "telemetry": telemetry or {},
            },
        )
        payload = response.json()
        return payload if isinstance(payload, dict) else {"data": payload}

    def remote_config(self) -> dict[str, Any]:
        response = self._request("GET", "/api/v1/edge/config")
        payload = response.json()
        if not isinstance(payload, dict):
            raise TerraSatchApiError("Unexpected /api/v1/edge/config response")
        return payload

    def ingest_text(
        self,
        *,
        site_id: str,
        text: str,
        callsign: str | None = None,
        source_message_id: str | None = None,
        source: str = "terrasatch-edge",
        agent_id: str | None = None,
        channel_id: str | None = None,
        transcript_provider: str | None = None,
        transcript_model: str | None = None,
        transcript_language: str | None = None,
        transcript_confidence: float | None = None,
        started_at: str | None = None,
        ended_at: str | None = None,
        rf_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body = {
            "site_id": site_id,
            "agent_id": agent_id,
            "channel_id": channel_id,
            "callsign": callsign,
            "text": text,
            "source": source,
            "source_message_id": source_message_id,
            "transcript_provider": transcript_provider,
            "transcript_model": transcript_model,
            "transcript_language": transcript_language,
            "transcript_confidence": transcript_confidence,
            "started_at": started_at,
            "ended_at": ended_at,
            "rf_metadata": rf_metadata,
        }
        response = self._request("POST", "/api/v1/transmissions", json=body)
        payload = response.json()
        return payload if isinstance(payload, dict) else {"data": payload}
