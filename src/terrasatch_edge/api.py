from __future__ import annotations

from typing import Any

import httpx

from . import __version__
from .models import ApiIdentity, SiteSummary


class TerraSatchApiError(RuntimeError):
    pass


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
            raise TerraSatchApiError(f"HTTP {response.status_code}: {detail or response.reason_phrase}")
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
            rows = [row for row in candidate if isinstance(row, dict)] if isinstance(candidate, list) else []
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
        }
        response = self._request("POST", "/api/v1/transmissions", json=body)
        payload = response.json()
        return payload if isinstance(payload, dict) else {"data": payload}
