from __future__ import annotations

import socket
from dataclasses import asdict
from functools import lru_cache
from importlib.resources import files
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from . import __version__
from .api import TerraSatchApiClient, TerraSatchApiError
from .config import (
    EdgeConfig,
    clear_api_key,
    get_paths,
    load_api_key,
    load_config,
    save_api_key,
    save_config,
)
from .discovery import save_snapshot, scan_hardware
from .doctor import run_doctor
from .operator_page import render_operator_page


@lru_cache(maxsize=2)
def _brand_asset(name: str) -> bytes:
    """Load bundled brand artwork once for the offline operator console."""
    return files("terrasatch_edge").joinpath("assets", name).read_bytes()


class ConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_name: str | None = None
    scan_interval_seconds: int | None = Field(default=None, ge=5, le=3600)
    source: str | None = None
    speech_model: str | None = None
    speech_device: str | None = None
    speech_compute_type: str | None = None
    speech_language: str | None = None
    speech_vad_filter: bool | None = None
    speech_local_files_only: bool | None = None


class PairingClaimRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_code: str


def _status_payload() -> dict[str, Any]:
    config = load_config()
    key = load_api_key()
    client = TerraSatchApiClient(config.api_url, key)
    api_ok = False
    auth_ok = False
    api_detail: dict[str, Any] = {}

    try:
        api_detail = client.health()
        api_ok = True
    except TerraSatchApiError as exc:
        api_detail = {"error": str(exc)}

    if key and api_ok:
        try:
            client.edge_me()
            auth_ok = True
        except TerraSatchApiError:
            try:
                client.identity()
                auth_ok = True
            except TerraSatchApiError:
                auth_ok = False

    snapshot = scan_hardware(include_network=False)
    return {
        "version": __version__,
        "configured": bool(key and config.device_id),
        "api_url": config.api_url,
        "api_online": api_ok,
        "authenticated": auth_ok,
        "device_id": config.device_id,
        "organization_id": config.organization_id,
        "site_id": config.site_id,
        "site_name": config.site_name,
        "node_name": config.node_name,
        "hostname": snapshot.hostname,
        "platform": snapshot.platform,
        "architecture": snapshot.architecture,
        "device_count": len(snapshot.devices),
        "devices": [device.model_dump(mode="json") for device in snapshot.devices],
        "api_detail": api_detail,
        "snapshot_file": str(get_paths().snapshot_file),
    }


def _safe_config_payload(config: EdgeConfig) -> dict[str, Any]:
    return {
        "api_url": config.api_url,
        "node_name": config.node_name,
        "scan_interval_seconds": config.scan_interval_seconds,
        "source": config.source,
        "speech_model": config.speech_model,
        "speech_device": config.speech_device,
        "speech_compute_type": config.speech_compute_type,
        "speech_language": config.speech_language,
        "speech_vad_filter": config.speech_vad_filter,
        "speech_local_files_only": config.speech_local_files_only,
    }


def build_app() -> Any:
    try:
        from fastapi import Depends, FastAPI, Header, HTTPException
        from fastapi.responses import HTMLResponse, Response
    except ImportError as exc:
        raise RuntimeError(
            "Local UI dependencies are not installed. Run: pip install 'terrasatch-edge[ui]'"
        ) from exc

    app = FastAPI(title="TerraSatch Edge Operator Console", docs_url=None, redoc_url=None)

    @app.get("/assets/terrasatch-logo.webp", include_in_schema=False)
    def brand_mark() -> Response:
        return Response(
            content=_brand_asset("terrasatch-logo.webp"),
            media_type="image/webp",
            headers={"Cache-Control": "public, max-age=31536000, immutable"},
        )

    @app.get("/assets/terrasatch-black-logo.png", include_in_schema=False)
    def brand_lockup() -> Response:
        return Response(
            content=_brand_asset("terrasatch-black-logo.png"),
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=31536000, immutable"},
        )

    def require_operator_header(
        x_terrasatch_edge_ui: str | None = Header(default=None),
    ) -> None:
        if x_terrasatch_edge_ui != "1":
            raise HTTPException(status_code=403, detail="Local operator confirmation header required")

    operator_guard = Depends(require_operator_header)

    @app.get("/api/status")
    def api_status() -> dict[str, Any]:
        return _status_payload()

    @app.get("/api/config")
    def api_config() -> dict[str, Any]:
        return _safe_config_payload(load_config())

    @app.put("/api/config")
    def update_config(
        update: ConfigUpdate,
        _: None = operator_guard,
    ) -> dict[str, Any]:
        current = load_config()
        changes = update.model_dump(exclude_unset=True)

        if "node_name" in changes:
            value = changes["node_name"]
            changes["node_name"] = str(value).strip() if value is not None and str(value).strip() else None

        if "source" in changes:
            value = changes["source"]
            changes["source"] = str(value).strip() if value is not None and str(value).strip() else "terrasatch-edge"

        merged = current.model_dump()
        merged.update(changes)
        try:
            updated = EdgeConfig.model_validate(merged)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        save_config(updated)
        return {"ok": True, "config": _safe_config_payload(updated)}

    @app.post("/api/scan")
    def rescan(_: None = operator_guard) -> dict[str, Any]:
        snapshot = scan_hardware(include_network=False)
        path = save_snapshot(snapshot)
        return {
            "ok": True,
            "snapshot_file": str(path),
            "device_count": len(snapshot.devices),
            "devices": [device.model_dump(mode="json") for device in snapshot.devices],
        }

    @app.post("/api/verify")
    def verify(_: None = operator_guard) -> dict[str, Any]:
        config = load_config()
        key = load_api_key()
        client = TerraSatchApiClient(config.api_url, key)
        result: dict[str, Any] = {"api_online": False, "authenticated": False, "heartbeat": False}

        try:
            result["health"] = client.health()
            result["api_online"] = True
        except TerraSatchApiError as exc:
            result["error"] = str(exc)
            return result

        if not key:
            result["error"] = "No Edge credential configured"
            return result

        try:
            edge = client.edge_me()
            result["authenticated"] = True
            result["device"] = edge.model_dump(mode="json")
        except TerraSatchApiError:
            try:
                client.identity()
                result["authenticated"] = True
            except TerraSatchApiError as exc:
                result["error"] = str(exc)
                return result

        snapshot = scan_hardware(include_network=False)
        save_snapshot(snapshot)
        try:
            result["heartbeat_response"] = client.heartbeat(snapshot)
            result["heartbeat"] = True
        except TerraSatchApiError as exc:
            result["heartbeat_error"] = str(exc)
        return result

    @app.post("/api/doctor")
    def doctor(_: None = operator_guard) -> dict[str, Any]:
        checks = [asdict(check) for check in run_doctor()]
        return {
            "ok": all(bool(check["ok"]) for check in checks),
            "checks": checks,
        }

    @app.post("/api/pairing/start")
    def start_pairing(_: None = operator_guard) -> dict[str, Any]:
        config = load_config()
        snapshot = scan_hardware(include_network=False)
        node_name = config.node_name or f"{socket.gethostname()}-edge"
        client = TerraSatchApiClient(config.api_url)
        try:
            pairing = client.start_pairing(
                name=node_name,
                hostname=snapshot.hostname,
                platform_name=snapshot.platform,
                architecture=snapshot.architecture,
            )
        except TerraSatchApiError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return pairing.model_dump(mode="json")

    @app.post("/api/pairing/claim")
    def claim_pairing(
        request: PairingClaimRequest,
        _: None = operator_guard,
    ) -> dict[str, Any]:
        current = load_config()
        client = TerraSatchApiClient(current.api_url)
        try:
            claim = client.claim_pairing(request.device_code)
        except TerraSatchApiError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        if claim.status != "approved" or not claim.token or not claim.device:
            return {"status": claim.status, "paired": False}

        device = claim.device
        site_changed = current.site_id != device.site_id
        updated = current.model_copy(
            update={
                "device_id": device.id,
                "organization_id": device.organization_id,
                "site_id": device.site_id,
                "site_name": None if site_changed else current.site_name,
                "node_name": device.name or current.node_name,
            }
        )
        save_config(updated)
        save_api_key(claim.token)

        snapshot = scan_hardware(include_network=False)
        save_snapshot(snapshot)
        heartbeat_ok = False
        heartbeat_error: str | None = None
        try:
            TerraSatchApiClient(updated.api_url, claim.token).heartbeat(snapshot)
            heartbeat_ok = True
        except TerraSatchApiError as exc:
            heartbeat_error = str(exc)

        return {
            "status": claim.status,
            "paired": True,
            "heartbeat": heartbeat_ok,
            "heartbeat_error": heartbeat_error,
            "device": device.model_dump(mode="json"),
        }

    @app.post("/api/logout")
    def logout(_: None = operator_guard) -> dict[str, Any]:
        clear_api_key()
        return {"ok": True}

    @app.get("/", response_class=HTMLResponse)
    def operator_index() -> str:
        return render_operator_page(
            status=_status_payload(),
            config=_safe_config_payload(load_config()),
            version=__version__,
        )

    return app
