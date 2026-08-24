from __future__ import annotations

import html
import json
import socket
from dataclasses import asdict
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
        from fastapi.responses import HTMLResponse
    except ImportError as exc:
        raise RuntimeError(
            "Local UI dependencies are not installed. Run: pip install 'terrasatch-edge[ui]'"
        ) from exc

    app = FastAPI(title="TerraSatch Edge Operator Console", docs_url=None, redoc_url=None)

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
    def index() -> str:
        status = _status_payload()
        devices = status["devices"]

        def first_device(*kinds: str, capabilities: tuple[str, ...] = ()) -> dict[str, Any] | None:
            for device in devices:
                device_capabilities = set(device.get("capabilities", []))
                if str(device.get("kind")) in kinds or device_capabilities.intersection(capabilities):
                    return device
            return None

        radio_device = first_device("sdr", capabilities=("radio_rx", "iq_stream")) or first_device("serial")
        audio_device = first_device("audio", capabilities=("audio", "audio_input", "audio_capture"))
        gps_device = first_device("gps", capabilities=("gps", "location", "nmea"))
        system_device = first_device("system")

        def device_detail(device: dict[str, Any] | None, fallback: str) -> str:
            if not device:
                return fallback
            kind = str(device.get("kind") or "unknown")
            candidates = (
                (device.get("name"), device.get("product"))
                if kind == "system"
                else (device.get("product"), device.get("name"))
            )
            for candidate in candidates:
                value = str(candidate or "").strip()
                if value and value.lower() not in {"n/a", "none", "unknown"}:
                    return value
            operator_fallbacks = {
                "serial": "Serial interface detected",
                "sdr": "Radio receiver detected",
                "audio": "Audio interface detected",
                "gps": "Location receiver detected",
                "system": node_label,
            }
            return operator_fallbacks.get(kind, fallback)

        device_rows = "".join(
            f"<tr><td>{html.escape(str(d['kind']))}</td><td>{html.escape(d['name'])}</td>"
            f"<td>{html.escape(', '.join(d.get('capabilities', [])))}</td><td>{html.escape(d['status'])}</td></tr>"
            for d in devices
        )
        if not device_rows:
            device_rows = '<tr><td colspan="4" class="muted">No field hardware detected yet.</td></tr>'

        badge = "ONLINE" if status["api_online"] else "OFFLINE"
        auth = "AUTHENTICATED" if status["authenticated"] else "NOT AUTHENTICATED"
        config = _safe_config_payload(load_config())
        health_payload = html.escape(json.dumps(status["api_detail"], indent=2))
        field_state = "ONLINE" if status["api_online"] else "OFFLINE"
        field_tone = "good" if status["api_online"] else "danger"
        organization_label = "TerraSatch" if status["organization_id"] else "Awaiting pairing"
        site_label = status["site_name"] or ("Assigned field site" if status["site_id"] else "Not assigned")
        node_label = str(status["node_name"] or status["hostname"])
        heartbeat_label = (
            "Ready to send" if status["api_online"] and status["authenticated"] else "Verify connection"
        )
        radio_state = "READY" if radio_device else "WAITING"
        audio_state = "DETECTED" if audio_device else "WAITING"
        gps_state = "READY" if gps_device else "WAITING"
        learning_state = "CONFIGURED" if config["speech_model"] else "SETUP"
        adapt_state = "AVAILABLE" if status["authenticated"] else "PAIR TO SYNC"
        readiness = [
            (bool(system_device or status["device_count"]), "Hardware detected"),
            (status["api_online"], "Network available"),
            (status["api_online"], "API reachable"),
            (status["authenticated"], "Device authenticated"),
            (status["api_online"] and status["authenticated"], "Heartbeat ready"),
        ]
        readiness_rows = "".join(
            f'<li class="readiness-row {"ready" if ok else "pending"}">'
            f'<span class="check" aria-hidden="true">{"✓" if ok else "·"}</span>'
            f'<span>{html.escape(label)}</span><strong>{"OK" if ok else "CHECK"}</strong></li>'
            for ok, label in readiness
        )
        all_ready = all(ok for ok, _ in readiness)

        return f"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TerraSatch Edge Operator Console</title>
<style>
:root{{color-scheme:dark;--bg:#070908;--panel:#0e1210;--panel-2:#121714;--line:#303833;--line-soft:#202723;--text:#f4f1e9;--muted:#9ba59f;--orange:#ff8a00;--orange-soft:#a95d08;--green:#2ed477;--red:#ff5a54;--amber:#f4b942;--radius:12px;--display:"Arial Narrow","Roboto Condensed","Segoe UI",sans-serif;--ui:Inter,"Segoe UI",system-ui,sans-serif}}
*{{box-sizing:border-box}}
html{{scroll-behavior:smooth}}
body{{font-family:var(--ui);background:var(--bg);color:var(--text);margin:0;min-width:320px}}
body::before{{content:"";position:fixed;inset:0;pointer-events:none;opacity:.36;background:radial-gradient(circle at 15% 8%,rgba(255,138,0,.08),transparent 24%),radial-gradient(circle at 87% 38%,rgba(46,212,119,.035),transparent 28%),repeating-linear-gradient(132deg,transparent 0 58px,rgba(255,255,255,.012) 59px 60px)}}
button,input,summary{{font:inherit}}
button,a,summary{{-webkit-tap-highlight-color:transparent}}
a{{color:inherit;text-decoration:none}}
button:focus-visible,a:focus-visible,input:focus-visible,summary:focus-visible{{outline:2px solid var(--orange);outline-offset:3px}}
.shell{{position:relative;max-width:1440px;margin:0 auto;padding:0 22px 28px}}
.masthead{{min-height:108px;display:grid;grid-template-columns:minmax(240px,.9fr) minmax(360px,1.1fr) minmax(300px,.8fr);align-items:center;gap:24px;border-bottom:2px solid var(--orange);padding:18px 18px 15px}}
.brand-lockup{{display:flex;align-items:center;gap:13px;min-width:0}}
.brand-mark{{width:58px;height:58px;display:grid;place-items:center;border:2px solid var(--orange);border-radius:50%;background:#090c0a;box-shadow:0 0 30px rgba(255,138,0,.1)}}
.brand-mark svg{{width:42px;height:42px;color:var(--text)}}
.brand-copy{{min-width:0}}
.brand-kicker,.eyebrow,.section-title,.mode-name,.status-label{{font-family:var(--display);font-weight:900;letter-spacing:.12em;text-transform:uppercase}}
.brand-kicker{{color:var(--orange);font-size:.62rem;white-space:nowrap}}
.brand-name{{font-family:var(--display);font-size:clamp(1.65rem,3vw,2.5rem);font-weight:950;letter-spacing:.025em;line-height:.95;white-space:nowrap}}
.console-title{{text-align:center}}
.console-title h1{{font-family:var(--display);font-size:clamp(1.25rem,2.3vw,1.75rem);letter-spacing:.12em;line-height:1.1;margin:0;text-transform:uppercase;white-space:nowrap}}
.console-title p{{font-family:var(--display);color:#c4cbc7;font-size:.72rem;font-weight:800;letter-spacing:.3em;margin:12px 0 0;text-transform:uppercase}}
.console-title p b{{color:var(--orange)}}
.system-badges{{display:grid;grid-template-columns:1fr auto;gap:7px 12px;justify-self:end;width:min(100%,340px)}}
.system-badge{{display:flex;align-items:center;gap:9px;min-height:34px;border:1px solid var(--line);border-radius:7px;padding:7px 11px;background:linear-gradient(90deg,rgba(255,255,255,.025),transparent);font-family:var(--display);font-size:.71rem;font-weight:900;letter-spacing:.13em;text-transform:uppercase}}
.system-badge::before{{content:"";width:8px;height:8px;border-radius:50%;background:currentColor;box-shadow:0 0 10px currentColor}}
.system-badge.online{{color:var(--green)}}.system-badge.warn{{color:var(--amber)}}
.version{{grid-column:2;grid-row:1 / span 2;display:grid;place-items:center;min-width:80px;color:#bec5c1}}.version::before{{display:none}}
#notice{{position:sticky;top:10px;z-index:20;display:none;margin:12px 0 0;padding:13px 16px;border:1px solid #2f7049;border-left:4px solid var(--green);border-radius:8px;background:#10251a;color:#eafff1;box-shadow:0 16px 40px rgba(0,0,0,.35)}}
.dashboard{{padding-top:12px}}
.primary-grid{{display:grid;grid-template-columns:1fr 1.08fr;gap:14px}}
.panel{{position:relative;border:1px solid var(--line);border-radius:var(--radius);background:linear-gradient(145deg,rgba(18,23,20,.98),rgba(10,13,11,.98));overflow:hidden}}
.panel::after{{content:"";position:absolute;inset:auto 0 0;height:3px;background:linear-gradient(90deg,var(--orange),transparent 72%);opacity:.78}}
.panel-pad{{padding:20px}}
.section-title{{display:flex;align-items:center;justify-content:space-between;gap:16px;color:var(--orange);font-size:.88rem;margin:0 0 16px}}
.section-title .count{{color:var(--muted);font-family:var(--ui);font-size:.72rem;letter-spacing:.05em}}
.field-status{{display:grid;grid-template-columns:132px 1fr;gap:26px;align-items:center;min-height:268px}}
.field-emblem{{width:132px;height:132px;display:grid;place-items:center;border:2px solid var(--orange);border-radius:50%;background:radial-gradient(circle,rgba(255,138,0,.12),transparent 64%)}}
.field-emblem svg{{width:86px;height:86px;color:var(--text)}}
.field-copy{{border-left:1px solid #4a534e;padding-left:28px;min-width:0}}
.field-state{{font-family:var(--display);font-size:clamp(2.8rem,6vw,4.6rem);font-weight:950;letter-spacing:.05em;line-height:.88;margin:0 0 24px;text-transform:uppercase;text-shadow:0 0 22px currentColor}}
.field-state.good{{color:var(--green)}}.field-state.danger{{color:var(--red)}}
.status-facts{{display:grid;grid-template-columns:max-content 1fr;gap:10px 24px;margin:0}}
.status-facts dt{{color:var(--muted);font-family:var(--display);font-size:.66rem;font-weight:850;letter-spacing:.1em;text-transform:uppercase}}
.status-facts dd{{font-family:var(--display);font-size:.8rem;letter-spacing:.04em;margin:0;overflow-wrap:anywhere}}
.readiness-list{{list-style:none;margin:0;padding:0;display:grid;gap:5px}}
.readiness-row{{display:grid;grid-template-columns:24px 1fr auto;align-items:center;gap:10px;min-height:35px;padding:6px 10px;border:1px solid var(--line);border-radius:7px;background:rgba(255,255,255,.018);font-family:var(--display);font-size:.75rem;letter-spacing:.055em}}
.readiness-row .check{{width:21px;height:21px;display:grid;place-items:center;border-radius:50%;font-family:var(--ui);font-weight:950}}
.readiness-row strong{{font-size:.65rem;letter-spacing:.11em}}
.readiness-row.ready .check{{background:var(--green);color:#082413}}.readiness-row.ready strong{{color:var(--green)}}
.readiness-row.pending .check{{border:1px solid var(--amber);color:var(--amber)}}.readiness-row.pending strong{{color:var(--amber)}}
.ready-banner{{display:flex;align-items:center;justify-content:center;gap:10px;margin-top:8px;min-height:44px;border:1px solid {'var(--green)' if all_ready else 'var(--amber)'};border-radius:7px;color:{'var(--green)' if all_ready else 'var(--amber)'};font-family:var(--display);font-size:.82rem;font-weight:900;letter-spacing:.12em;text-align:center;text-transform:uppercase}}
.command-nav{{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:10px 0}}
.command-link,.command-button{{display:flex;align-items:center;justify-content:center;gap:9px;min-height:48px;border:1px solid var(--line);border-radius:8px;background:linear-gradient(180deg,#161b18,#0e1210);color:#dce1de;font-family:var(--display);font-size:.78rem;font-weight:850;letter-spacing:.1em;cursor:pointer}}
.command-link:hover,.command-button:hover{{border-color:var(--orange);color:var(--orange)}}
.command-link.primary{{border-bottom:3px solid var(--orange);color:var(--orange)}}
.mode-rail{{display:grid;grid-template-columns:repeat(4,1fr);margin-bottom:10px;border:1px solid var(--line);border-radius:10px;background:#0c100e}}
.mode{{display:grid;grid-template-columns:40px 1fr;align-items:center;gap:12px;padding:15px 18px;min-height:86px}}
.mode + .mode{{border-left:1px solid #47504b}}
.mode svg{{width:31px;height:31px;color:var(--text)}}
.mode-name{{color:var(--orange);font-size:.79rem;margin-bottom:5px}}
.mode-detail{{color:var(--muted);font-family:var(--display);font-size:.63rem;letter-spacing:.06em}}
.mode-detail strong{{color:var(--green);font-size:.61rem;letter-spacing:.1em;margin-left:7px}}
.mode-detail strong.pending{{color:var(--amber)}}
.hardware-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}}
.hardware-card{{display:grid;grid-template-columns:48px 1fr auto;gap:12px;align-items:center;min-height:105px;border:1px solid var(--line);border-left:3px solid var(--orange);border-radius:8px;padding:14px;background:linear-gradient(135deg,rgba(255,255,255,.025),transparent)}}
.hardware-card svg{{width:38px;height:38px;color:var(--text)}}
.hardware-name{{font-family:var(--display);font-size:.72rem;font-weight:850;letter-spacing:.06em}}
.hardware-detail{{color:var(--muted);font-size:.69rem;margin-top:5px;overflow-wrap:anywhere}}
.hardware-state{{align-self:start;color:var(--green);font-family:var(--display);font-size:.61rem;font-weight:900;letter-spacing:.1em}}
.hardware-state.pending{{color:var(--amber)}}
.section-stack{{display:grid;gap:10px;margin-top:10px}}
.section-panel{{padding:20px}}
.split{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}
.setup-actions{{display:flex;flex-wrap:wrap;gap:9px;margin-bottom:16px}}
button{{border:1px solid var(--orange-soft);border-radius:7px;padding:10px 14px;background:var(--orange);color:#15100a;font-family:var(--display);font-size:.72rem;font-weight:900;letter-spacing:.07em;cursor:pointer}}
button:hover{{filter:brightness(1.08)}}button.secondary{{background:#171c19;color:var(--text);border-color:#4a544e}}button.danger{{background:#2a1515;color:#ffd8d6;border-color:#7c3532}}button:disabled{{opacity:.5;cursor:not-allowed}}
.pairing-panel,.diagnostic-panel{{display:none;margin:12px 0 0;padding:14px;border:1px solid var(--orange-soft);border-radius:8px;background:#0b0f0d}}
.pairing-panel strong{{display:block;color:var(--orange);font-family:var(--display);letter-spacing:.08em;margin-bottom:5px}}
.diagnostic-list{{display:grid;gap:6px}}
.diagnostic-row{{display:flex;justify-content:space-between;gap:20px;padding:8px 10px;border:1px solid var(--line-soft);border-radius:6px;color:var(--muted);font-size:.75rem}}
.diagnostic-row strong{{color:var(--green);font-family:var(--display);letter-spacing:.08em}}.diagnostic-row.fail strong{{color:var(--red)}}
.form-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:13px}}
label{{display:block;color:#c2cac5;font-family:var(--display);font-size:.63rem;font-weight:800;letter-spacing:.08em;margin-bottom:6px;text-transform:uppercase}}
input{{width:100%;min-height:40px;border:1px solid #3b4540;border-radius:7px;background:#090c0b;color:var(--text);padding:9px 11px}}
input[readonly]{{color:#828c86;cursor:not-allowed}}
.help{{color:var(--muted);font-size:.72rem;line-height:1.55}}
.form-actions{{margin-top:14px}}
details{{border:1px solid var(--line);border-radius:8px;background:rgba(255,255,255,.012)}}
details + details{{margin-top:7px}}
summary{{position:relative;list-style:none;padding:12px 42px 12px 14px;color:#d7ddd9;font-family:var(--display);font-size:.72rem;font-weight:820;letter-spacing:.065em;cursor:pointer}}
summary::-webkit-details-marker{{display:none}}summary::after{{content:"⌄";position:absolute;right:15px;color:var(--muted)}}details[open] summary::after{{content:"⌃"}}
.details-body{{border-top:1px solid var(--line);padding:14px}}
.id-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:9px}}
.id-cell{{padding:11px;border:1px solid var(--line-soft);border-radius:7px;background:#090c0b}}
.id-cell span{{display:block;color:var(--muted);font-family:var(--display);font-size:.59rem;letter-spacing:.08em;margin-bottom:5px;text-transform:uppercase}}
.id-cell code{{font-size:.68rem;overflow-wrap:anywhere}}
table{{width:100%;border-collapse:collapse;font-size:.72rem}}th,td{{padding:9px;border-bottom:1px solid var(--line-soft);text-align:left;vertical-align:top}}th{{color:var(--orange);font-family:var(--display);font-size:.61rem;letter-spacing:.08em;text-transform:uppercase}}
code,pre{{white-space:pre-wrap;word-break:break-word}}pre{{max-height:320px;overflow:auto;margin:0;border:1px solid var(--line-soft);border-radius:7px;background:#080a09;color:#b9c4bd;padding:13px;font-size:.7rem}}
.mode-cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:9px}}
.mode-card{{padding:13px;border:1px solid var(--line-soft);border-radius:7px}}
.mode-card h3{{font-family:var(--display);font-size:.72rem;letter-spacing:.08em;margin:0 0 6px;text-transform:uppercase}}
.muted{{color:var(--muted)}}.small{{font-size:.75rem}}
.footer{{display:flex;justify-content:space-between;gap:20px;margin-top:12px;border:1px solid var(--line);border-radius:8px;padding:15px 20px;color:#747f78;font-family:var(--display);font-size:.61rem;letter-spacing:.06em}}
.footer strong{{color:var(--green)}}
@media(max-width:1050px){{.masthead{{grid-template-columns:1fr 1fr}}.console-title{{text-align:right}}.system-badges{{grid-column:1/-1;justify-self:stretch;width:100%;grid-template-columns:1fr 1fr auto}}.version{{grid-column:3;grid-row:1}}.primary-grid,.split{{grid-template-columns:1fr}}.hardware-grid{{grid-template-columns:repeat(2,1fr)}}}}
@media(max-width:720px){{.shell{{padding:0 12px 18px}}.masthead{{grid-template-columns:1fr;padding:16px 4px;gap:14px}}.brand-lockup{{justify-content:center}}.console-title{{text-align:center}}.console-title h1{{font-size:clamp(1.05rem,5.5vw,1.3rem);letter-spacing:.09em}}.system-badges{{grid-column:auto;grid-template-columns:1fr auto}}.version{{grid-column:2;grid-row:1 / span 2}}.field-status{{grid-template-columns:1fr;min-height:210px;text-align:center}}.field-emblem{{display:none}}.field-copy{{border-left:0;padding-left:0}}.status-facts{{text-align:left}}.command-nav{{grid-template-columns:1fr 1fr}}.mode-rail{{grid-template-columns:1fr 1fr}}.mode:nth-child(3){{border-left:0;border-top:1px solid #47504b}}.mode:nth-child(4){{border-top:1px solid #47504b}}.hardware-grid,.form-grid,.id-grid,.mode-cards{{grid-template-columns:1fr}}.footer{{flex-direction:column;text-align:center}}}}
@media(max-width:420px){{.brand-kicker{{white-space:normal}}.system-badges{{grid-template-columns:1fr}}.version{{grid-column:auto;grid-row:auto}}.mode-rail{{grid-template-columns:1fr}}.mode + .mode{{border-left:0;border-top:1px solid #47504b}}.hardware-card{{grid-template-columns:42px 1fr}}.hardware-state{{grid-column:2}}}}
@media(prefers-reduced-motion:reduce){{html{{scroll-behavior:auto}}}}
</style>
</head>
<body><main class="shell">
<header class="masthead">
<div class="brand-lockup">
<div class="brand-mark" aria-hidden="true"><svg viewBox="0 0 48 48" fill="none"><path d="M6 33 17 17l7 8 5-7 13 15" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M9 36h30M13 29v7m22-7v7" stroke="currentColor" stroke-width="3" stroke-linecap="round"/><path d="M7 15c5-5 10-5 15 0M10 20c3-3 6-3 9 0" stroke="#ff8a00" stroke-width="2.5" stroke-linecap="round"/></svg></div>
<div class="brand-copy"><div class="brand-kicker">Field Intelligence Gateway</div><div class="brand-name">TERRASATCH</div></div>
</div>
<div class="console-title"><h1>Edge Operator Console</h1><p>Listen <b>•</b> Watch <b>•</b> Learn <b>•</b> Adapt</p></div>
<div class="system-badges">
<div class="system-badge {'online' if status['api_online'] else 'warn'}">API {badge}</div>
<div class="system-badge {'online' if status['authenticated'] else 'warn'}">{auth}</div>
<div class="system-badge version">v{html.escape(__version__)}</div>
</div>
</header>

<div id="notice" role="status" aria-live="polite"></div>
<div class="dashboard">
<section class="primary-grid" aria-label="Field overview">
<article class="panel panel-pad">
<h2 class="section-title">Field Status</h2>
<div class="field-status">
<div class="field-emblem" aria-hidden="true"><svg viewBox="0 0 96 96" fill="none"><path d="M18 69V39c0-8 6-14 14-14h16c8 0 14 6 14 14v30" stroke="currentColor" stroke-width="5" stroke-linecap="round"/><path d="M29 39h22M28 50h24M28 61h15" stroke="currentColor" stroke-width="4" stroke-linecap="round"/><path d="M62 29c8 4 13 10 16 18M66 18c13 6 21 16 25 28" stroke="#ff8a00" stroke-width="5" stroke-linecap="round"/><path d="M26 25V11m0 0-5 7m5-7 5 7" stroke="currentColor" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/></svg></div>
<div class="field-copy">
<p class="field-state {field_tone}">{field_state}</p>
<dl class="status-facts">
<dt>Device</dt><dd>Edge Node {html.escape(node_label)}</dd>
<dt>Assignment</dt><dd>{html.escape(organization_label)} / {html.escape(str(site_label))}</dd>
<dt>Heartbeat</dt><dd>{html.escape(heartbeat_label)}</dd>
<dt>Hardware</dt><dd>{status['device_count']} detected record(s)</dd>
</dl>
</div>
</div>
</article>

<article class="panel panel-pad">
<h2 class="section-title">Edge Readiness</h2>
<ul class="readiness-list">{readiness_rows}</ul>
<div class="ready-banner">{'✓ Ready for field operations' if all_ready else 'Complete checks before field use'}</div>
</article>
</section>

<nav class="command-nav" aria-label="Console sections">
<a class="command-link primary" href="#setup">Setup</a>
<a class="command-link" href="#hardware">Hardware</a>
<button class="command-button" type="button" onclick="runDoctor()">Diagnostics</button>
<a class="command-link" href="#advanced">Advanced</a>
</nav>

<section class="mode-rail" aria-label="TerraSatch operating status">
<article class="mode"><svg viewBox="0 0 32 32" fill="none" aria-hidden="true"><path d="M9 27V12c0-3 2-5 5-5h4c3 0 5 2 5 5v15M12 14h8m-8 5h8m-8 5h5M16 7V2" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg><div><div class="mode-name">Listen</div><div class="mode-detail">Radio input <strong class="{'pending' if not radio_device else ''}">{radio_state}</strong></div></div></article>
<article class="mode"><svg viewBox="0 0 32 32" fill="none" aria-hidden="true"><path d="m16 8-6 20h12L16 8Zm-3 10h6M8 5c-3 3-4 7-4 11m20-11c3 3 4 7 4 11M11 9c-2 2-2 4-2 7m12-7c2 2 2 4 2 7" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg><div><div class="mode-name">Watch</div><div class="mode-detail">Connectivity <strong class="{'pending' if not status['api_online'] else ''}">{badge}</strong></div></div></article>
<article class="mode"><svg viewBox="0 0 32 32" fill="none" aria-hidden="true"><path d="M13 6c-4-3-9 0-8 5-4 2-3 8 1 9-1 5 5 8 9 4V8c0-1-1-2-2-2Zm6 0c4-3 9 0 8 5 4 2 3 8-1 9 1 5-5 8-9 4V8c0-1 1-2 2-2ZM10 12c3 0 5 2 5 5m7-5c-3 0-5 2-5 5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg><div><div class="mode-name">Learn</div><div class="mode-detail">AI processing <strong class="{'pending' if not config['speech_model'] else ''}">{learning_state}</strong></div></div></article>
<article class="mode"><svg viewBox="0 0 32 32" fill="none" aria-hidden="true"><path d="M5 9h22M5 16h22M5 23h22M11 6v6m10 1v6m-6 1v6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><circle cx="11" cy="9" r="2" fill="currentColor"/><circle cx="21" cy="16" r="2" fill="currentColor"/><circle cx="15" cy="23" r="2" fill="currentColor"/></svg><div><div class="mode-name">Adapt</div><div class="mode-detail">Remote config <strong class="{'pending' if not status['authenticated'] else ''}">{adapt_state}</strong></div></div></article>
</section>

<section id="hardware" class="panel section-panel">
<h2 class="section-title">Connected Hardware <span class="count">{status['device_count']} raw record(s)</span></h2>
<div class="hardware-grid">
<article class="hardware-card"><svg viewBox="0 0 40 40" fill="none" aria-hidden="true"><path d="M10 35V17c0-4 3-7 7-7h6c4 0 7 3 7 7v18M15 18h10m-10 6h10m-10 6h6M20 10V3" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/><path d="M29 8c3 2 5 5 6 8" stroke="#ff8a00" stroke-width="2.4" stroke-linecap="round"/></svg><div><div class="hardware-name">Radio Interface</div><div class="hardware-detail">{html.escape(device_detail(radio_device, 'No radio or serial interface found'))}</div></div><div class="hardware-state {'pending' if not radio_device else ''}">{radio_state}</div></article>
<article class="hardware-card"><svg viewBox="0 0 40 40" fill="none" aria-hidden="true"><rect x="14" y="4" width="12" height="23" rx="6" stroke="currentColor" stroke-width="2.4"/><path d="M9 20c0 6 5 11 11 11s11-5 11-11M20 31v6m-6 0h12" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/></svg><div><div class="hardware-name">Audio Capture</div><div class="hardware-detail">{html.escape(device_detail(audio_device, 'No dedicated audio input found'))}</div></div><div class="hardware-state {'pending' if not audio_device else ''}">{audio_state}</div></article>
<article class="hardware-card"><svg viewBox="0 0 40 40" fill="none" aria-hidden="true"><path d="M20 36s12-10 12-21A12 12 0 0 0 8 15c0 11 12 21 12 21Z" stroke="currentColor" stroke-width="2.4"/><circle cx="20" cy="15" r="4" stroke="currentColor" stroke-width="2.4"/></svg><div><div class="hardware-name">GPS</div><div class="hardware-detail">{html.escape(device_detail(gps_device, 'Waiting for location receiver'))}</div></div><div class="hardware-state {'pending' if not gps_device else ''}">{gps_state}</div></article>
<article class="hardware-card"><svg viewBox="0 0 40 40" fill="none" aria-hidden="true"><rect x="7" y="6" width="26" height="21" rx="2" stroke="currentColor" stroke-width="2.4"/><path d="M4 34h32l-3-7H7l-3 7Z" stroke="currentColor" stroke-width="2.4" stroke-linejoin="round"/></svg><div><div class="hardware-name">Edge Computer</div><div class="hardware-detail">{html.escape(device_detail(system_device, node_label))}</div></div><div class="hardware-state">ONLINE</div></article>
</div>
</section>

<div class="section-stack">
<section id="setup" class="panel section-panel">
<h2 class="section-title">Setup</h2>
<div class="setup-actions">
<button type="button" onclick="rescan()">Rescan Hardware</button>
<button type="button" onclick="startPairing()">Pair This Edge</button>
<button type="button" onclick="verifyEdge()">Verify Connection</button>
<button class="secondary" type="button" onclick="runDoctor()">Run Diagnostics</button>
</div>
<div id="pairing" class="pairing-panel"></div>
<div id="diagnostics" class="diagnostic-panel" aria-live="polite"></div>
<details open>
<summary>Local device settings</summary>
<div class="details-body">
<form id="configForm">
<div class="form-grid">
<div><label for="api_url">TerraSatch API (terminal/admin controlled)</label><input id="api_url" value="{html.escape(str(config['api_url']))}" readonly></div>
<div><label for="node_name">Node name</label><input id="node_name" name="node_name" value="{html.escape(str(config['node_name'] or ''))}" placeholder="field-kit-01"></div>
<div><label for="scan_interval_seconds">Heartbeat / scan interval (seconds)</label><input id="scan_interval_seconds" name="scan_interval_seconds" type="number" min="5" max="3600" value="{int(config['scan_interval_seconds'])}"></div>
<div><label for="source">Source label</label><input id="source" name="source" value="{html.escape(str(config['source']))}"></div>
<div><label for="speech_model">Speech model</label><input id="speech_model" name="speech_model" value="{html.escape(str(config['speech_model']))}"></div>
<div><label for="speech_device">Speech device</label><input id="speech_device" name="speech_device" value="{html.escape(str(config['speech_device']))}"></div>
<div><label for="speech_compute_type">Speech compute type</label><input id="speech_compute_type" name="speech_compute_type" value="{html.escape(str(config['speech_compute_type']))}"></div>
<div><label for="speech_language">Speech language</label><input id="speech_language" name="speech_language" value="{html.escape(str(config['speech_language'] or ''))}" placeholder="en"></div>
</div>
<div class="form-actions"><button type="submit">Save Settings</button></div>
</form>
<p class="help">Assignment is controlled by TerraSatch pairing/Admin. API target changes remain a terminal/admin action so an existing device credential cannot be redirected accidentally.</p>
</div>
</details>
</section>

<section id="advanced" class="panel section-panel">
<h2 class="section-title">Advanced <span class="count">Developer and service detail</span></h2>
<details><summary>Developer identifiers</summary><div class="details-body id-grid">
<div class="id-cell"><span>Device ID</span><code>{html.escape(str(status['device_id'] or 'Not paired'))}</code></div>
<div class="id-cell"><span>Organization ID</span><code>{html.escape(str(status['organization_id'] or 'Not assigned'))}</code></div>
<div class="id-cell"><span>Site ID</span><code>{html.escape(str(status['site_id'] or 'Not assigned'))}</code></div>
</div></details>
<details><summary>Raw hardware inventory</summary><div class="details-body" style="overflow:auto"><table><thead><tr><th>Type</th><th>Device</th><th>Capabilities</th><th>Status</th></tr></thead><tbody>{device_rows}</tbody></table></div></details>
<details><summary>API health JSON</summary><div class="details-body"><pre>{health_payload}</pre></div></details>
<details><summary>Terminal reference</summary><div class="details-body"><pre>terrasatch-edge setup
terrasatch-edge scan
terrasatch-edge devices
terrasatch-edge status
terrasatch-edge doctor
terrasatch-edge run --once
terrasatch-edge run
terrasatch-edge paths</pre><p class="help">The browser console intentionally does not execute arbitrary shell commands. Use your system terminal for custom scripts and advanced operations.</p></div></details>
<details><summary>Operator modes</summary><div class="details-body mode-cards"><div class="mode-card"><h3>UI Mode</h3><span class="help">Pairing, supported configuration, hardware scans, diagnostics, and connection verification.</span></div><div class="mode-card"><h3>Terminal Mode</h3><span class="help">Automation, scripting, service control, logs, and advanced operations using the same saved configuration.</span></div><div class="mode-card"><h3>Field Mode</h3><span class="help">Persistent unattended Edge agent with heartbeat and remote-config retrieval.</span></div></div></details>
<details><summary>Credential management</summary><div class="details-body"><p class="help">Removing the local credential unpairs this console until an administrator approves a new pairing request.</p><button class="danger" type="button" onclick="logoutEdge()">Remove Local Credential</button></div></details>
</section>
</div>

<footer class="footer"><span>TerraSatch Edge Operator Console v{html.escape(__version__)}</span><strong>{'All readiness checks passed' if all_ready else 'Setup attention required'}</strong><span>Field Intelligence Gateway</span></footer>
</div>

<script>
const headers = {{"Content-Type":"application/json","X-TerraSatch-Edge-UI":"1"}};
let pairingTimer = null;

function notify(message, error=false) {{
  const el = document.getElementById("notice");
  el.textContent = message;
  el.style.display = "block";
  el.style.background = error ? "#3a1d1d" : "#183124";
  el.style.borderColor = error ? "#6b3434" : "#2e5a40";
  window.scrollTo({{top:0,behavior:"smooth"}});
}}

async function request(path, options={{}}) {{
  const response = await fetch(path, options);
  let body = {{}};
  try {{ body = await response.json(); }} catch (_) {{}}
  if (!response.ok) throw new Error(body.detail || `HTTP ${{response.status}}`);
  return body;
}}

async function rescan() {{
  try {{
    const data = await request("/api/scan", {{method:"POST",headers}});
    notify(`Hardware scan complete: ${{data.device_count}} records. Reloading…`);
    setTimeout(()=>location.reload(), 500);
  }} catch (err) {{ notify(`Hardware scan failed: ${{err.message}}`, true); }}
}}

async function verifyEdge() {{
  try {{
    const data = await request("/api/verify", {{method:"POST",headers}});
    if (data.api_online && data.authenticated && data.heartbeat) {{
      notify("Edge verified: API online, credential accepted, heartbeat synced.");
    }} else {{
      notify(`Verification incomplete: ${{data.error || data.heartbeat_error || "check pairing and diagnostics"}}`, true);
    }}
  }} catch (err) {{ notify(`Verification failed: ${{err.message}}`, true); }}
}}

async function runDoctor() {{
  const panel = document.getElementById("diagnostics");
  try {{
    const data = await request("/api/doctor", {{method:"POST",headers}});
    panel.replaceChildren();
    panel.style.display = "block";
    const heading = document.createElement("strong");
    heading.textContent = "Diagnostic results";
    const list = document.createElement("div");
    list.className = "diagnostic-list";
    for (const check of data.checks) {{
      const row = document.createElement("div");
      row.className = `diagnostic-row ${{check.ok ? "" : "fail"}}`;
      const name = document.createElement("span");
      name.textContent = check.name;
      const result = document.createElement("strong");
      result.textContent = check.ok ? "PASS" : "CHECK";
      row.append(name, result);
      list.appendChild(row);
    }}
    panel.append(heading, list);
    panel.scrollIntoView({{behavior:"smooth",block:"nearest"}});
    const failed = data.checks.filter(c=>!c.ok);
    if (!failed.length) notify("Diagnostics complete: all checks passed.");
    else notify(`Diagnostics found ${{failed.length}} item(s): ${{failed.map(c=>c.name).join(", ")}}`, true);
  }} catch (err) {{ notify(`Diagnostics failed: ${{err.message}}`, true); }}
}}

async function startPairing() {{
  const panel = document.getElementById("pairing");
  try {{
    const data = await request("/api/pairing/start", {{method:"POST",headers}});
    panel.replaceChildren();
    panel.style.display = "block";

    const code = document.createElement("strong");
    code.textContent = `Pairing code: ${{data.user_code}}`;
    const detail = document.createElement("div");
    detail.className = "muted small";
    detail.textContent = "Approve the organization and site in TerraSatch Admin.";
    const actions = document.createElement("div");
    actions.className = "actions";
    const link = document.createElement("a");
    link.target = "_blank";
    link.rel = "noreferrer";
    link.href = data.verification_url;
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "Open TerraSatch Admin";
    link.appendChild(button);
    actions.appendChild(link);
    panel.append(code, detail, actions);

    if (pairingTimer) clearInterval(pairingTimer);
    const interval = Math.max(2000, (data.interval_seconds || 5) * 1000);
    pairingTimer = setInterval(()=>claimPairing(data.device_code), interval);
    await claimPairing(data.device_code);
  }} catch (err) {{ notify(`Pairing could not start: ${{err.message}}`, true); }}
}}

async function claimPairing(deviceCode) {{
  try {{
    const data = await request("/api/pairing/claim", {{method:"POST",headers,body:JSON.stringify({{device_code:deviceCode}})}});
    if (data.paired) {{
      if (pairingTimer) clearInterval(pairingTimer);
      notify(data.heartbeat ? "Pairing complete and first heartbeat synced." : `Pairing complete; heartbeat needs attention: ${{data.heartbeat_error || "unknown error"}}`, !data.heartbeat);
      setTimeout(()=>location.reload(), 700);
    }} else if (["expired","claimed"].includes(data.status)) {{
      if (pairingTimer) clearInterval(pairingTimer);
      notify(`Pairing ended with status: ${{data.status}}`, true);
    }}
  }} catch (err) {{
    if (pairingTimer) clearInterval(pairingTimer);
    notify(`Pairing check failed: ${{err.message}}`, true);
  }}
}}

document.getElementById("configForm").addEventListener("submit", async (event)=>{{
  event.preventDefault();
  const form = new FormData(event.target);
  const payload = {{
    node_name: form.get("node_name"),
    scan_interval_seconds: Number(form.get("scan_interval_seconds")),
    source: form.get("source"),
    speech_model: form.get("speech_model"),
    speech_device: form.get("speech_device"),
    speech_compute_type: form.get("speech_compute_type"),
    speech_language: form.get("speech_language") || null
  }};
  try {{
    await request("/api/config", {{method:"PUT",headers,body:JSON.stringify(payload)}});
    notify("Local Edge settings saved. Run Verify Connection before field use.");
  }} catch (err) {{ notify(`Settings were not saved: ${{err.message}}`, true); }}
}});

async function logoutEdge() {{
  if (!confirm("Remove the local Edge credential? The device will need to be paired again.")) return;
  try {{
    await request("/api/logout", {{method:"POST",headers}});
    notify("Local credential removed. Reloading…");
    setTimeout(()=>location.reload(), 500);
  }} catch (err) {{ notify(`Could not remove credential: ${{err.message}}`, true); }}
}}
</script>
</main></body></html>
"""

    return app
