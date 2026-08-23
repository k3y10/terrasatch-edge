from __future__ import annotations

import html
import json
import socket
from dataclasses import asdict
from typing import Any

from pydantic import BaseModel, Field

from . import __version__
from .api import TerraSatchApiClient, TerraSatchApiError
from .config import (
    EdgeConfig,
    clear_api_key,
    get_paths,
    load_api_key,
    load_config,
    load_remote_config,
    save_api_key,
    save_config,
)
from .discovery import save_snapshot, scan_hardware
from .doctor import run_doctor


class ConfigUpdate(BaseModel):
    api_url: str | None = None
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
    device_code: str


def _status_payload() -> dict[str, Any]:
    config = load_config()
    key = load_api_key()
    client = TerraSatchApiClient(config.api_url, key)
    api_ok = False
    auth_ok = False
    api_detail: dict[str, Any] = {}
    identity_detail: dict[str, Any] = {}

    try:
        api_detail = client.health()
        api_ok = True
    except TerraSatchApiError as exc:
        api_detail = {"error": str(exc)}

    if key and api_ok:
        try:
            edge = client.edge_me()
            identity_detail = edge.model_dump(mode="json")
            auth_ok = True
        except TerraSatchApiError:
            try:
                identity_detail = client.identity().raw
                auth_ok = True
            except TerraSatchApiError as exc:
                identity_detail = {"error": str(exc)}

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
        "identity_detail": identity_detail,
        "remote_config": load_remote_config(),
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
        from fastapi import FastAPI, Header, HTTPException
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

    @app.get("/api/status")
    def api_status() -> dict[str, Any]:
        return _status_payload()

    @app.get("/api/config")
    def api_config() -> dict[str, Any]:
        return _safe_config_payload(load_config())

    @app.put("/api/config")
    def update_config(
        update: ConfigUpdate,
        _: None = require_operator_header,
    ) -> dict[str, Any]:
        current = load_config()
        changes = update.model_dump(exclude_none=True)
        if "api_url" in changes:
            selected_api = str(changes["api_url"]).strip().rstrip("/")
            if not selected_api.startswith(("https://", "http://")):
                raise HTTPException(status_code=422, detail="API URL must start with http:// or https://")
            changes["api_url"] = selected_api
        if "node_name" in changes:
            changes["node_name"] = str(changes["node_name"]).strip() or None
        if "source" in changes:
            changes["source"] = str(changes["source"]).strip() or "terrasatch-edge"

        updated = current.model_copy(update=changes)
        save_config(updated)
        return {"ok": True, "config": _safe_config_payload(updated)}

    @app.post("/api/scan")
    def rescan(_: None = require_operator_header) -> dict[str, Any]:
        snapshot = scan_hardware(include_network=False)
        path = save_snapshot(snapshot)
        return {
            "ok": True,
            "snapshot_file": str(path),
            "device_count": len(snapshot.devices),
            "devices": [device.model_dump(mode="json") for device in snapshot.devices],
        }

    @app.post("/api/verify")
    def verify(_: None = require_operator_header) -> dict[str, Any]:
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
    def doctor(_: None = require_operator_header) -> dict[str, Any]:
        checks = [asdict(check) for check in run_doctor()]
        return {
            "ok": all(bool(check["ok"]) for check in checks),
            "checks": checks,
        }

    @app.post("/api/pairing/start")
    def start_pairing(_: None = require_operator_header) -> dict[str, Any]:
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
        _: None = require_operator_header,
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
        site_changed = bool(current.site_id and current.site_id != device.site_id)
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
    def logout(_: None = require_operator_header) -> dict[str, Any]:
        clear_api_key()
        return {"ok": True}

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        status = _status_payload()
        device_rows = "".join(
            f"<tr><td>{html.escape(str(d['kind']))}</td><td>{html.escape(d['name'])}</td>"
            f"<td>{html.escape(', '.join(d.get('capabilities', [])))}</td><td>{html.escape(d['status'])}</td></tr>"
            for d in status["devices"]
        )
        if not device_rows:
            device_rows = '<tr><td colspan="4" class="muted">No field hardware detected yet.</td></tr>'

        badge = "ONLINE" if status["api_online"] else "OFFLINE"
        auth = "AUTHENTICATED" if status["authenticated"] else "NOT AUTHENTICATED"
        config = _safe_config_payload(load_config())
        config_json = html.escape(json.dumps(config))
        health_payload = html.escape(json.dumps(status["api_detail"], indent=2))

        return f"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TerraSatch Edge Operator Console</title>
<style>
:root{{color-scheme:dark}}
*{{box-sizing:border-box}}
body{{font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#0b0d0c;color:#f4f7f5;margin:0;padding:24px}}
main{{max-width:1180px;margin:auto}}
header{{display:flex;justify-content:space-between;gap:20px;align-items:flex-start;flex-wrap:wrap;margin-bottom:18px}}
h1{{margin:0 0 4px;font-size:clamp(1.8rem,4vw,2.7rem)}} h2{{margin-top:0}} h3{{margin:0 0 8px}}
.card{{background:#151917;border:1px solid #2a332e;border-radius:18px;padding:22px;margin:16px 0;box-shadow:0 12px 35px rgba(0,0,0,.12)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}}
.tile{{background:#101311;border-radius:14px;padding:16px;border:1px solid #29312d}}
.muted{{color:#a7b0aa}} .small{{font-size:.88rem}}
.badge{{display:inline-block;padding:6px 10px;border-radius:999px;background:#26332b;margin:0 8px 8px 0}}
.badge.online{{background:#173a28}} .badge.warn{{background:#3a2e17}}
table{{width:100%;border-collapse:collapse}} th,td{{padding:10px;border-bottom:1px solid #2a332e;text-align:left;vertical-align:top}}
code,pre{{white-space:pre-wrap;word-break:break-word}} pre{{background:#0d100e;border:1px solid #252d29;border-radius:12px;padding:14px}}
label{{display:block;font-size:.86rem;color:#c5cec8;margin-bottom:6px}}
input,select{{width:100%;padding:11px 12px;border-radius:10px;border:1px solid #35403a;background:#0d100e;color:#f4f7f5}}
.form-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px}}
.actions{{display:flex;flex-wrap:wrap;gap:10px;margin-top:16px}}
button{{padding:11px 15px;border-radius:11px;border:1px solid #4b5a52;background:#f4f7f5;color:#111;font-weight:700;cursor:pointer}}
button.secondary{{background:#1b211e;color:#f4f7f5}} button.danger{{background:#341d1d;color:#ffdede;border-color:#5b2d2d}}
button:disabled{{opacity:.5;cursor:not-allowed}}
#notice{{position:sticky;top:12px;z-index:5;display:none;padding:12px 14px;border-radius:12px;background:#183124;border:1px solid #2e5a40;margin-bottom:12px}}
.step{{display:flex;gap:10px;align-items:flex-start}} .step strong{{display:block}}
.num{{width:28px;height:28px;display:grid;place-items:center;border-radius:999px;background:#26332b;flex:0 0 auto;font-weight:800}}
@media(max-width:700px){{body{{padding:14px}}.card{{padding:16px}}table{{font-size:.86rem}}}}
</style>
</head>
<body><main>
<div id="notice"></div>
<header>
<div><h1>TerraSatch Edge</h1><div class="muted">Operator Console · LISTEN · WATCH · LEARN · ADAPT</div></div>
<div><span class="badge">v{html.escape(__version__)}</span><span class="badge {'online' if status['api_online'] else 'warn'}">API {badge}</span><span class="badge {'online' if status['authenticated'] else 'warn'}">{auth}</span></div>
</header>

<div class="card">
<h2>Setup & Readiness</h2>
<div class="grid">
<div class="tile step"><span class="num">1</span><div><strong>Connect</strong><span class="muted small">Attach radio/SDR, GPS, USB audio, and network hardware.</span></div></div>
<div class="tile step"><span class="num">2</span><div><strong>Pair</strong><span class="muted small">Authorize this Edge against the correct organization and site.</span></div></div>
<div class="tile step"><span class="num">3</span><div><strong>Verify</strong><span class="muted small">Validate API authentication and send the current hardware heartbeat.</span></div></div>
<div class="tile step"><span class="num">4</span><div><strong>Operate</strong><span class="muted small">Use UI mode or terminal/service mode without changing the API contract.</span></div></div>
</div>
<div class="actions">
<button onclick="rescan()">Rescan Hardware</button>
<button onclick="startPairing()">Pair This Edge</button>
<button onclick="verifyEdge()">Verify Connection</button>
<button class="secondary" onclick="runDoctor()">Run Diagnostics</button>
</div>
<div id="pairing" class="tile" style="display:none;margin-top:14px"></div>
</div>

<div class="card">
<h2>Current Assignment</h2>
<div class="grid">
<div class="tile"><span class="muted small">Node</span><br><strong>{html.escape(str(status['node_name'] or status['hostname']))}</strong></div>
<div class="tile"><span class="muted small">Device ID</span><br><strong>{html.escape(str(status['device_id'] or 'Not paired'))}</strong></div>
<div class="tile"><span class="muted small">Organization</span><br><strong>{html.escape(str(status['organization_id'] or 'Not assigned'))}</strong></div>
<div class="tile"><span class="muted small">Site</span><br><strong>{html.escape(str(status['site_name'] or status['site_id'] or 'Not assigned'))}</strong></div>
</div>
<p class="muted small">Organization and site assignment are controlled by TerraSatch pairing/Admin. The local console does not expose tenant reassignment controls.</p>
</div>

<div class="card">
<h2>Local Device Settings</h2>
<form id="configForm">
<div class="form-grid">
<div><label for="api_url">TerraSatch API</label><input id="api_url" name="api_url" value="{html.escape(str(config['api_url']))}"></div>
<div><label for="node_name">Node name</label><input id="node_name" name="node_name" value="{html.escape(str(config['node_name'] or ''))}" placeholder="field-kit-01"></div>
<div><label for="scan_interval_seconds">Heartbeat / scan interval (seconds)</label><input id="scan_interval_seconds" name="scan_interval_seconds" type="number" min="5" max="3600" value="{int(config['scan_interval_seconds'])}"></div>
<div><label for="source">Source label</label><input id="source" name="source" value="{html.escape(str(config['source']))}"></div>
<div><label for="speech_model">Speech model</label><input id="speech_model" name="speech_model" value="{html.escape(str(config['speech_model']))}"></div>
<div><label for="speech_device">Speech device</label><input id="speech_device" name="speech_device" value="{html.escape(str(config['speech_device']))}"></div>
<div><label for="speech_compute_type">Speech compute type</label><input id="speech_compute_type" name="speech_compute_type" value="{html.escape(str(config['speech_compute_type']))}"></div>
<div><label for="speech_language">Speech language</label><input id="speech_language" name="speech_language" value="{html.escape(str(config['speech_language'] or ''))}" placeholder="en"></div>
</div>
<div class="actions"><button type="submit">Save Settings</button></div>
</form>
</div>

<div class="card"><h2>Detected Hardware <span class="muted small">({status['device_count']})</span></h2><div style="overflow:auto"><table><thead><tr><th>Type</th><th>Device</th><th>Capabilities</th><th>Status</th></tr></thead><tbody>{device_rows}</tbody></table></div></div>

<div class="card">
<h2>Operator Modes</h2>
<div class="grid">
<div class="tile"><h3>UI Mode</h3><span class="muted small">Pairing, supported configuration, hardware scans, diagnostics, and connection verification.</span></div>
<div class="tile"><h3>Terminal Mode</h3><span class="muted small">Automation, scripting, service control, logs, and advanced operations using the same saved configuration.</span></div>
<div class="tile"><h3>Field Mode</h3><span class="muted small">Persistent unattended Edge agent with heartbeat and remote-config retrieval.</span></div>
</div>
</div>

<div class="card">
<h2>Terminal Reference</h2>
<pre>terrasatch-edge setup
terrasatch-edge scan
terrasatch-edge devices
terrasatch-edge status
terrasatch-edge doctor
terrasatch-edge run --once
terrasatch-edge run
terrasatch-edge paths</pre>
<p class="muted small">The browser console intentionally does not execute arbitrary shell commands. Use your system terminal for custom scripts and advanced operations.</p>
</div>

<div class="card"><h2>API Health Detail</h2><pre>{health_payload}</pre></div>
<div class="card"><button class="danger" onclick="logoutEdge()">Remove Local Credential</button></div>

<script>
const initialConfig = JSON.parse("{config_json.replace('\\', '\\\\').replace(chr(34), '\\"')}");
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
  try {{
    const data = await request("/api/doctor", {{method:"POST",headers}});
    const failed = data.checks.filter(c=>!c.ok);
    if (!failed.length) notify("Diagnostics complete: all checks passed.");
    else notify(`Diagnostics found ${{failed.length}} item(s): ${{failed.map(c=>c.name).join(", ")}}`, true);
  }} catch (err) {{ notify(`Diagnostics failed: ${{err.message}}`, true); }}
}}

async function startPairing() {{
  const panel = document.getElementById("pairing");
  try {{
    const data = await request("/api/pairing/start", {{method:"POST",headers}});
    panel.style.display = "block";
    panel.innerHTML = `<strong>Pairing code: ${{data.user_code}}</strong><br><span class="muted small">Approve the organization and site in TerraSatch Admin.</span><div class="actions"><a href="${{data.verification_url}}" target="_blank" rel="noreferrer"><button type="button">Open TerraSatch Admin</button></a></div>`;
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
    api_url: form.get("api_url"),
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
