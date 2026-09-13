"""Optional, bounded directory discovery; never changes configured targets or identity."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .radio_targets import RadioTarget, RepeaterMetadata, parse_frequency


class DiscoveryQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    radius: float = Field(default=75, gt=0, le=500)
    region: str | None = Field(default=None, min_length=1, max_length=200)
    mode: Literal["fm", "nfm"] = "nfm"
    limit: int = Field(default=20, ge=1, le=100)
    location_source: Literal["cli", "site", "receiver", "region"] = "cli"

    @model_validator(mode="after")
    def location(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Both latitude and longitude are required")
        if self.latitude is None and not self.region:
            raise ValueError("Configure coordinates or pass --latitude/--longitude or --region")
        return self


class DirectoryError(RuntimeError):
    pass


class DirectoryRateLimit(DirectoryError):
    pass


class RepeaterDirectoryProvider(Protocol):
    name: str

    def search(self, query: DiscoveryQuery) -> list[RadioTarget]: ...
    def get(self, provider_id: str) -> RadioTarget: ...
    def normalize(self, data: dict) -> RadioTarget: ...


class ManualRepeaterProvider:
    name = "manual"

    def __init__(self, targets: list[RadioTarget]):
        self.targets = targets

    def normalize(self, data: dict) -> RadioTarget:
        return RadioTarget.model_validate(data)

    def search(self, query: DiscoveryQuery) -> list[RadioTarget]:
        return [t for t in self.targets if t.modulation == query.mode and
                (not query.region or query.region.lower() in t.name.lower())][:query.limit]

    def get(self, provider_id: str) -> RadioTarget:
        for target in self.targets:
            if target.id == provider_id:
                return target
        raise DirectoryError("Configured target not found")


class OrganizationRepeaterProvider(ManualRepeaterProvider):
    name = "organization"


class OpenRepeaterProvider:
    name = "open-repeater"
    base_url = "https://www.openrepeater.org/api/v1"

    def __init__(self, api_key: str | None = None, *, transport=None):
        self.api_key = api_key or os.environ.get("TERRASATCH_OPEN_REPEATER_API_KEY")
        self.transport = transport

    def _request(self, path: str, params: dict | None = None):
        if not self.api_key:
            raise DirectoryError("Set TERRASATCH_OPEN_REPEATER_API_KEY for optional directory access")
        try:
            with httpx.Client(timeout=10, follow_redirects=False, transport=self.transport) as client:
                with client.stream("GET", self.base_url + path, params=params,
                                   headers={"X-API-Key": self.api_key}) as response:
                    if response.status_code == 429:
                        raise DirectoryRateLimit("Directory daily rate limit reached; use cached/manual targets")
                    response.raise_for_status()
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > 1_000_000:
                            raise DirectoryError("Directory response exceeded 1 MB")
                    return json.loads(body)
        except (httpx.HTTPError, ValueError) as exc:
            # No URLs, headers, credentials or external error bodies in logs.
            raise DirectoryError("Directory unavailable or returned invalid JSON") from exc

    def normalize(self, data: dict) -> RadioTarget:
        if not isinstance(data, dict) or str(data.get("mode", "")).upper() not in {"FM", "NFM"}:
            raise ValueError("Only explicit analog FM directory records are supported")
        if data.get("status") != "active":
            raise ValueError("Directory record is not active")
        provider_id = str(UUID(data["id"]))
        hz = parse_frequency(f"{data['frequency']}M")
        # Provider documents frequency in MHz; offset is metadata only.
        offset = data.get("offset")
        offset_hz = None
        if offset is not None:
            from decimal import Decimal, InvalidOperation
            try:
                raw_offset = Decimal(str(offset)) * 1_000_000
            except InvalidOperation as exc:
                raise ValueError("Invalid repeater offset") from exc
            if not raw_offset.is_finite() or raw_offset != raw_offset.to_integral_value():
                raise ValueError("Invalid repeater offset")
            offset_hz = int(raw_offset)
        name = data.get("callsign")
        return RadioTarget(id=f"open-repeater:{provider_id}", name=name,
                           profile="repeater", source_type="repeater", frequency_hz=hz,
                           modulation="nfm" if data["mode"].upper() == "NFM" else "fm",
                           enabled=False, discovered=True, ctcss_hz=data.get("ctcss"),
                           repeater=RepeaterMetadata(
                               provider=self.name, provider_id=provider_id, name=name,
                               output_frequency_hz=hz,
                               input_frequency_hz=hz + offset_hz if offset_hz is not None else None,
                               offset_hz=offset_hz, location_text=data.get("city"),
                               last_verified_at=data.get("last_verified")))

    def search(self, query: DiscoveryQuery) -> list[RadioTarget]:
        params = {"limit": query.limit, "page": 1}
        if query.latitude is not None:
            params.update(lat=query.latitude, lng=query.longitude, radius=query.radius)
        else:
            params["q"] = query.region
        payload = self._request("/search", params)
        # The documentation shows a record but not a list envelope. Accept only
        # explicit list forms, and fail safely if the provider changes its contract.
        rows = payload if isinstance(payload, list) else payload.get("repeaters", payload.get("data")) if isinstance(payload, dict) else None
        if not isinstance(rows, list) or len(rows) > 200:
            raise DirectoryError("Unrecognized directory response envelope")
        targets = []
        for row in rows:
            try:
                target = self.normalize(row)
                if query.mode == "fm" or target.modulation in {"fm", "nfm"}:
                    targets.append(target)
            except (ValueError, KeyError, TypeError):
                continue
        return targets[:query.limit]

    def get(self, provider_id: str) -> RadioTarget:
        return self.normalize(self._request(f"/repeater/{UUID(provider_id)}"))


class DirectoryCache:
    """Separate SQLite file; 24-hour cache and a persisted conservative daily budget."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, data TEXT, retrieved REAL, expires REAL)")
            db.execute("CREATE TABLE IF NOT EXISTS budget (day TEXT PRIMARY KEY, count INTEGER)")

    def _connect(self):
        return sqlite3.connect(self.path, timeout=2)

    def search(self, provider: RepeaterDirectoryProvider, query: DiscoveryQuery, *, now: float | None = None) -> dict:
        now = time.time() if now is None else now
        key = hashlib.sha256(json.dumps([provider.name, query.model_dump()], sort_keys=True).encode()).hexdigest()
        with self._connect() as db:
            row = db.execute("SELECT data, retrieved, expires FROM cache WHERE key=?", (key,)).fetchone()
        cached = None
        if row:
            try:
                cached = [RadioTarget.model_validate(t).model_dump() for t in json.loads(row[0])]
            except (ValueError, TypeError):
                row = None
        def result(targets, retrieved, expires, stale=False, warning=None):
            return dict(provider=provider.name, query=query.model_dump(), targets=targets,
                        retrieved_at=datetime.fromtimestamp(retrieved, UTC).isoformat(),
                        expires_at=datetime.fromtimestamp(expires, UTC).isoformat(), stale=stale, warning=warning)
        if row and row[2] > now:
            return result(cached, row[1], row[2])
        try:
            if provider.name == "open-repeater":
                day = datetime.fromtimestamp(now, UTC).date().isoformat()
                with self._connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    count = db.execute("SELECT count FROM budget WHERE day=?", (day,)).fetchone()
                    if count and count[0] >= 30:
                        raise DirectoryError("Local directory daily request budget exhausted")
                    db.execute("INSERT INTO budget VALUES (?,1) ON CONFLICT(day) DO UPDATE SET count=count+1", (day,))
                    db.execute("DELETE FROM budget WHERE day < ?", (day,))
            try:
                targets = [target.model_dump() for target in provider.search(query)]
            except DirectoryRateLimit:
                if provider.name == "open-repeater":
                    with self._connect() as db:
                        db.execute("UPDATE budget SET count=30 WHERE day=?", (day,))
                raise
            with self._connect() as db:
                db.execute("INSERT OR REPLACE INTO cache VALUES (?,?,?,?)", (key, json.dumps(targets), now, now + 86400))
                db.execute("DELETE FROM cache WHERE key NOT IN (SELECT key FROM cache ORDER BY retrieved DESC LIMIT 100)")
            return result(targets, now, now + 86400)
        except (DirectoryError, ValueError, OSError) as exc:
            if row:
                return result(cached, row[1], row[2], True, str(exc))
            raise DirectoryError(str(exc)) from exc
