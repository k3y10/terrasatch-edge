from __future__ import annotations

import html
import json
from typing import Any

from .api import TerraSatchApiClient, TerraSatchApiError
from .config import get_paths, load_api_key, load_config
from .discovery import scan_hardware


def build_app() -> Any:
    try:
        from fastapi import FastAPI
        from fastapi.responses import HTMLResponse
    except ImportError as exc:
        raise RuntimeError(
            "Local UI dependencies are not installed. Run: pip install 'terrasatch-edge[ui]'"
        ) from exc

    app = FastAPI(title="TerraSatch Edge Operator Console", docs_url=None, redoc_url=None)

    @app.get("/api/status")
    def api_status() -> dict[str, Any]:
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
                client.identity()
                auth_ok = True
            except TerraSatchApiError:
                auth_ok = False

        snapshot = scan_hardware(include_network=False)
        return {
            "api_url": config.api_url,
            "api_online": api_ok,
            "authenticated": auth_ok,
            "site_id": config.site_id,
            "node_name": config.node_name,
            "hostname": snapshot.hostname,
            "device_count": len(snapshot.devices),
            "devices": [device.model_dump(mode="json") for device in snapshot.devices],
            "api_detail": api_detail,
            "snapshot_file": str(get_paths().snapshot_file),
        }

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        status = api_status()
        device_rows = "".join(
            f"<tr><td>{html.escape(str(d['kind']))}</td><td>{html.escape(d['name'])}</td>"
            f"<td>{html.escape(', '.join(d.get('capabilities', [])))}</td><td>{html.escape(d['status'])}</td></tr>"
            for d in status["devices"]
        )

        badge = "ONLINE" if status["api_online"] else "OFFLINE"
        auth = "AUTHENTICATED" if status["authenticated"] else "NOT AUTHENTICATED"
        payload = html.escape(json.dumps(status["api_detail"], indent=2))

        return f"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TerraSatch Edge Operator Console</title>
<style>
body{{font-family:system-ui,-apple-system,sans-serif;background:#0b0d0c;color:#f4f7f5;margin:0;padding:32px}}
main{{max-width:1100px;margin:auto}}
.card{{background:#151917;border:1px solid #2a332e;border-radius:18px;padding:22px;margin:16px 0}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}}
.tile{{background:#101311;border-radius:14px;padding:16px;border:1px solid #29312d}}
.muted{{color:#a7b0aa}}
.badge{{display:inline-block;padding:6px 10px;border-radius:999px;background:#26332b;margin-right:8px}}
table{{width:100%;border-collapse:collapse}} th,td{{padding:10px;border-bottom:1px solid #2a332e;text-align:left}}
code,pre{{white-space:pre-wrap;word-break:break-word}}
button{{padding:12px 16px;border-radius:12px;border:0;background:#f4f7f5;color:#111;font-weight:600}}
</style>
</head>
<body><main>
<h1>TerraSatch Edge Operator Console</h1>
<div class="muted">LISTEN · WATCH · LEARN · ADAPT</div>

<div class="card">
<h2>Quick Setup</h2>
<div class="grid">
<div class="tile"><strong>1. Connect</strong><br>Attach radio, SDR, GPS, USB audio, and network hardware.</div>
<div class="tile"><strong>2. Pair</strong><br>Run <code>terrasatch-edge setup</code> or complete pairing from Admin.</div>
<div class="tile"><strong>3. Verify</strong><br>Confirm heartbeat, credentials, and device capabilities.</div>
<div class="tile"><strong>4. Operate</strong><br>Enable terminal workflows or keep using this local UI.</div>
</div>
</div>

<div class="card">
<span class="badge">API {badge}</span><span class="badge">{auth}</span>
<p><strong>Node:</strong> {html.escape(str(status['node_name'] or status['hostname']))}</p>
<p><strong>API:</strong> {html.escape(status['api_url'])}</p>
<p><strong>Site:</strong> {html.escape(str(status['site_id'] or 'Not selected'))}</p>
</div>

<div class="card">
<h2>Operator Modes</h2>
<div class="grid">
<div class="tile"><strong>UI Mode</strong><br>Setup, diagnostics, hardware status, and pairing.</div>
<div class="tile"><strong>Terminal Mode</strong><br>Automation, scripting, service control, and advanced configuration.</div>
<div class="tile"><strong>Field Mode</strong><br>Run unattended services with heartbeat reporting.</div>
</div>
</div>

<div class="card"><h2>Detected Hardware</h2><table><thead><tr><th>Type</th><th>Device</th><th>Capabilities</th><th>Status</th></tr></thead><tbody>{device_rows}</tbody></table></div>
<div class="card"><h2>API Health</h2><pre>{payload}</pre></div>

<div class="card">
<h2>Terminal Commands</h2>
<pre>terrasatch-edge setup
terrasatch-edge scan
terrasatch-edge doctor
terrasatch-edge status
terrasatch-edge run</pre>
</div>

</main></body></html>
"""

    return app
