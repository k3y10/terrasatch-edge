from __future__ import annotations

import html
import json
import os
from typing import Any


def render_operator_page(
    *,
    status: dict[str, Any],
    config: dict[str, Any],
    version: str,
) -> str:
    """Render the simple, Windows-first Edge setup and readiness surface."""
    devices = status["devices"]
    is_windows = (
        os.environ.get("TERRASATCH_EDGE_WINDOWS_CONSOLE") == "1"
        or "windows" in str(status.get("platform") or "").lower()
    )
    ready = bool(status["api_online"] and status["authenticated"])
    context_label = (
        ("Windows console" if is_windows else "Local console")
        if ready
        else ("Windows setup" if is_windows else "Local setup")
    )
    node_label = str(status["node_name"] or status["hostname"])
    site_label = status["site_name"] or (
        "Assigned field site" if status["site_id"] else "Not assigned"
    )
    device_label = (
        f"{status['device_count']} device connected"
        if status["device_count"] == 1
        else f"{status['device_count']} devices connected"
    )

    device_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(device.get('kind') or 'unknown'))}</td>"
        f"<td>{html.escape(str(device.get('name') or 'Unnamed device'))}</td>"
        f"<td>{html.escape(str(device.get('status') or 'unknown'))}</td>"
        "</tr>"
        for device in devices
    )
    if not device_rows:
        device_rows = (
            '<tr><td colspan="3" class="muted">'
            "No additional field hardware is connected.</td></tr>"
        )

    device_groups: dict[str, dict[str, Any]] = {}
    for device in devices:
        kind = str(device.get("kind") or "unknown").strip().lower()
        group = device_groups.setdefault(kind, {"count": 0, "name": None})
        group["count"] += 1
        candidate = str(device.get("name") or "").strip()
        if candidate.lower() not in {"", "n/a", "none", "unknown"} and not group["name"]:
            group["name"] = candidate

    device_items = "".join(
        '<li class="device-row">'
        f"<span><strong>{html.escape(_group_label(kind, group))}</strong>"
        f"<small>{group['count']} detected</small></span>"
        "<span>Ready</span>"
        "</li>"
        for kind, group in device_groups.items()
    )
    if not device_items:
        device_items = (
            '<li class="device-empty">No additional field hardware found. '
            "Connect equipment and check this PC again.</li>"
        )

    check_rows = "".join(
        [
            _check_row("TerraSatch console", "Running on this PC", True),
            _check_row(
                "Internet connection",
                "TerraSatch is reachable"
                if status["api_online"]
                else "TerraSatch is not reachable",
                bool(status["api_online"]),
            ),
            _check_row(
                "Connected hardware",
                device_label if status["device_count"] else "No additional equipment found",
                bool(status["device_count"]),
            ),
        ]
    )

    active_step = 1 if not status["api_online"] else (2 if not status["configured"] else 3)
    steps = "".join(
        [
            _step(
                1,
                "Check this PC",
                done=bool(status["api_online"]),
                active=not ready and active_step == 1,
                body=f"""
                <div class="check-list">{check_rows}</div>
                <button class="primary-action" type="button" onclick="checkThisPC(this)">Check this PC</button>
                <button class="text-action" type="button" onclick="openDialog('detailsDialog')">Open device details</button>
                """,
            ),
            _step(
                2,
                "Pair with TerraSatch",
                done=bool(status["configured"]),
                active=not ready and active_step == 2,
                body="""
                <p class="step-note">Pair this PC to the correct TerraSatch organization and field site.</p>
                <button class="primary-action" type="button" onclick="startPairing(this)">Pair with TerraSatch</button>
                <button class="text-action" type="button" onclick="openDialog('detailsDialog')">Open device details</button>
                <div id="pairing" class="pairing-panel" aria-live="polite"></div>
                """,
            ),
            _step(
                3,
                "Verify and finish",
                done=bool(status["authenticated"]),
                active=not ready and active_step == 3,
                body="""
                <p class="step-note">Registration was found. Verify the saved credential and send a first heartbeat.</p>
                <button class="primary-action" type="button" onclick="verifyEdge(this)">Verify and finish</button>
                <button class="text-action" type="button" onclick="runDiagnostics(this)">Run diagnostics</button>
                <button class="text-action" type="button" onclick="openDialog('detailsDialog')">Open device details</button>
                """,
            ),
        ]
    )

    setup_content = f"""
    <h1>Set up this Edge</h1>
    <p class="lead">Follow these three steps. You only need to do this once.</p>
    <ol class="setup-steps">{steps}</ol>
    """
    ready_content = f"""
    <div class="ready-mark" aria-hidden="true"></div>
    <h1>This Edge is ready</h1>
    <p class="lead">Connected to TerraSatch and ready for field operation.</p>
    <dl class="ready-facts">
      <div><dt>This PC</dt><dd>{html.escape(node_label)}</dd></div>
      <div><dt>Assigned site</dt><dd>{html.escape(str(site_label))}</dd></div>
      <div><dt>Connection</dt><dd class="positive">Online</dd></div>
      <div><dt>Hardware</dt><dd>{html.escape(device_label)}</dd></div>
    </dl>
    <button class="primary-action" type="button" onclick="runQuickCheck(this)">Run a quick check</button>
    <div class="quiet-actions">
      <button class="text-action" type="button" onclick="openDialog('settingsDialog')">Device settings</button>
      <button class="text-action" type="button" onclick="openDialog('detailsDialog')">Advanced details</button>
    </div>
    """
    health_payload = html.escape(json.dumps(status["api_detail"], indent=2))

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TerraSatch Edge</title>
<style>
:root{{color-scheme:dark;--bg:#080a09;--surface:#111412;--surface2:#151816;--line:#303531;--soft:#242925;--text:#f7f7f4;--muted:#a9aeaa;--orange:#ff9416;--green:#35d778;--amber:#f0b44c;--red:#ff625c;--ui:"Segoe UI",Inter,system-ui,sans-serif;--display:"Arial Narrow","Roboto Condensed","Segoe UI",sans-serif}}
*{{box-sizing:border-box}}html{{background:var(--bg)}}body{{min-width:320px;min-height:100vh;margin:0;background:radial-gradient(circle at 50% 42%,rgba(255,255,255,.025),transparent 34%),var(--bg);color:var(--text);font:16px var(--ui)}}
button,input,summary{{font:inherit}}button{{color:inherit}}button:focus-visible,input:focus-visible,summary:focus-visible{{outline:2px solid var(--orange);outline-offset:3px}}
.shell{{min-height:100vh;max-width:1440px;margin:auto;padding:22px 38px 16px;display:flex;flex-direction:column}}
.app-header{{display:flex;align-items:center;justify-content:space-between;gap:24px}}.brand{{display:flex;align-items:center;gap:14px}}
.brand-mark{{width:58px;height:58px;display:grid;place-items:center;flex:0 0 auto}}.brand-mark img{{display:block;width:100%;height:100%;object-fit:contain;filter:drop-shadow(0 5px 14px rgba(0,0,0,.34))}}
.brand-name{{font:950 clamp(1.35rem,2.6vw,2rem)/1 var(--display);letter-spacing:.025em;text-transform:uppercase}}.brand-name span{{color:var(--orange);font-weight:800;text-transform:none}}
.context{{margin-top:7px;color:var(--muted);font-size:.95rem}}.version{{color:#777e79;font-size:.78rem}}
.workspace{{width:min(100%,920px);margin:24px auto 12px;padding:34px 64px 26px;border:1px solid var(--line);border-radius:10px;background:linear-gradient(145deg,rgba(255,255,255,.018),rgba(255,255,255,.004)),var(--surface);box-shadow:0 24px 80px rgba(0,0,0,.2)}}
.workspace h1{{margin:0;text-align:center;font-size:clamp(2rem,4vw,2.65rem);line-height:1.1;letter-spacing:-.025em}}.lead{{max-width:620px;margin:12px auto 20px;text-align:center;color:#c3c7c4;font-size:1.05rem;line-height:1.55}}
.setup-steps{{list-style:none;margin:6px auto 0;padding:0;max-width:720px}}.setup-step{{position:relative;display:grid;grid-template-columns:52px 1fr;gap:16px;padding-bottom:18px}}
.setup-step:not(:last-child)::before{{content:"";position:absolute;left:25px;top:46px;bottom:-2px;width:1px;background:#4a504c}}
.step-marker{{position:relative;z-index:1;width:52px;height:52px;border:2px solid #555b57;border-radius:50%;display:grid;place-items:center;background:var(--surface);font-size:1.16rem;font-weight:650}}
.setup-step.active .step-marker{{border-color:var(--orange)}}.setup-step.done .step-marker{{border-color:var(--green);color:var(--green)}}.step-copy h2{{min-height:52px;margin:0;display:flex;align-items:center;font-size:1.2rem}}.step-body{{padding-top:2px}}
.check-list{{display:grid;gap:8px;margin-bottom:18px}}.check-row{{display:grid;grid-template-columns:24px 1fr auto;align-items:center;gap:13px;min-height:56px;padding:9px 15px;border:1px solid var(--line);border-radius:8px;background:rgba(255,255,255,.012)}}
.check-row span:nth-child(2){{display:grid;gap:2px}}.check-row strong{{font-weight:600}}.check-row small{{color:var(--muted);font-size:.78rem}}.check-row b{{color:var(--amber);font-size:.74rem;text-transform:uppercase;letter-spacing:.08em}}.check-row.pass b{{color:var(--green)}}
.check-dot{{width:19px;height:19px;border:2px solid currentColor;border-radius:50%;color:var(--amber);position:relative}}.check-row.pass .check-dot{{color:var(--green)}}.check-row.pass .check-dot::after{{content:"";position:absolute;left:4px;top:1px;width:5px;height:9px;border:solid currentColor;border-width:0 2px 2px 0;transform:rotate(45deg)}}
.step-note{{margin:0 0 16px;color:#c2c6c3;line-height:1.55}}.primary-action{{display:block;width:min(100%,440px);min-height:54px;margin:auto;border:0;border-radius:8px;background:var(--orange);color:#080908;font-weight:700;cursor:pointer;transition:.16s ease}}.primary-action:hover{{background:#ff9f2f;transform:translateY(-1px)}}.primary-action:disabled{{opacity:.7;cursor:wait;transform:none}}
.text-action{{display:block;margin:15px auto 0;padding:3px 5px;border:0;background:transparent;color:var(--orange);text-decoration:underline;text-underline-offset:4px;cursor:pointer}}.text-action:hover{{color:#ffae4d}}
.pairing-panel,.result-panel{{display:none;margin:18px 0 0;padding:16px;border:1px solid var(--line);border-radius:8px;background:var(--surface2)}}.pairing-code{{font:1.25rem ui-monospace,Consolas,monospace;color:var(--orange);letter-spacing:.06em}}.pairing-panel p{{margin:7px 0 14px;color:var(--muted)}}.inline-action{{display:inline-flex;min-height:42px;align-items:center;padding:0 16px;border-radius:7px;background:var(--orange);color:#080908;font-weight:700;text-decoration:none}}
.ready-content{{text-align:center}}.ready-mark{{width:96px;height:96px;margin:4px auto 28px;border:2px solid var(--green);border-radius:50%;position:relative}}.ready-mark::after{{content:"";position:absolute;left:29px;top:22px;width:24px;height:42px;border:solid var(--green);border-width:0 5px 5px 0;transform:rotate(45deg)}}
.ready-facts{{display:grid;grid-template-columns:1fr 1fr;gap:0 28px;width:min(100%,680px);margin:32px auto 34px;text-align:left}}.ready-facts div{{padding:17px 4px;border-bottom:1px solid var(--line)}}.ready-facts dt{{color:var(--muted);font-size:.87rem}}.ready-facts dd{{margin:6px 0 0;font-size:1.08rem;font-weight:600;overflow-wrap:anywhere}}.positive{{color:var(--green)}}.quiet-actions{{display:flex;justify-content:center;gap:42px}}
.result-panel{{max-width:680px;margin:22px auto 0;text-align:left}}.result-row{{display:flex;justify-content:space-between;gap:16px;padding:10px 0;border-bottom:1px solid var(--soft)}}.result-row:last-child{{border:0}}.result-row b{{color:var(--green);font-size:.75rem;text-transform:uppercase;letter-spacing:.08em}}.result-row.fail b{{color:var(--red)}}
.service-note{{margin:auto auto 0;padding-top:14px;color:#858b87;text-align:center;font-size:.88rem}}#notice{{position:fixed;z-index:20;left:50%;top:18px;transform:translateX(-50%);display:none;width:min(calc(100% - 32px),720px);padding:13px 17px;border:1px solid #346447;border-radius:8px;background:#152d1e;box-shadow:0 14px 40px rgba(0,0,0,.35)}}
dialog{{width:min(calc(100% - 32px),760px);max-height:88vh;padding:0;border:1px solid var(--line);border-radius:10px;background:var(--surface);color:var(--text);box-shadow:0 28px 90px rgba(0,0,0,.7)}}dialog::backdrop{{background:rgba(0,0,0,.76)}}.dialog-head{{position:sticky;top:0;z-index:2;display:flex;align-items:center;justify-content:space-between;padding:20px 24px;border-bottom:1px solid var(--line);background:var(--surface)}}.dialog-head h2{{margin:0;font-size:1.25rem}}.icon-button{{width:40px;height:40px;border:1px solid var(--line);border-radius:7px;background:transparent;color:var(--muted);font-size:1.35rem;cursor:pointer}}.dialog-body{{padding:24px;overflow:auto}}.dialog-intro{{margin:0 0 20px;color:var(--muted);line-height:1.5}}
.device-list{{list-style:none;margin:0;padding:0}}.device-row{{display:flex;justify-content:space-between;gap:20px;padding:14px 0;border-bottom:1px solid var(--soft)}}.device-row span:first-child{{display:grid;gap:3px}}.device-row small{{color:var(--muted);text-transform:capitalize}}.device-empty{{padding:18px;border:1px dashed var(--line);border-radius:8px;color:var(--muted);line-height:1.5}}
.form-grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}label{{display:block;margin-bottom:6px;color:#c9cdca;font-size:.82rem}}input{{width:100%;min-height:44px;padding:10px 12px;border:1px solid #3b413d;border-radius:7px;background:#0b0d0c;color:var(--text)}}input[readonly]{{color:#858b87}}.form-actions{{margin-top:22px}}.form-actions .primary-action{{margin:0}}
details{{border-top:1px solid var(--line)}}details:first-of-type{{border-top:0}}summary{{position:relative;padding:16px 2px;cursor:pointer;font-weight:600;list-style:none}}summary::-webkit-details-marker{{display:none}}summary::after{{content:"+";position:absolute;right:4px;color:var(--muted)}}details[open] summary::after{{content:"−"}}.detail-content{{padding:0 2px 18px}}.brand-lockup{{display:block;width:min(100%,560px);height:auto;margin:4px auto 18px;border-radius:8px}}.id-list{{display:grid;gap:12px}}.id-list div{{display:grid;gap:5px}}.id-list span{{color:var(--muted);font-size:.78rem}}code,pre{{font-family:ui-monospace,Consolas,monospace}}code{{overflow-wrap:anywhere}}pre{{margin:0;padding:14px;border-radius:7px;background:#090b0a;color:#cbd0cc;overflow:auto;font-size:.78rem;line-height:1.55}}table{{width:100%;border-collapse:collapse;font-size:.85rem}}th,td{{padding:10px;text-align:left;border-bottom:1px solid var(--soft)}}th{{color:var(--muted);font-weight:600}}.danger{{min-height:44px;padding:0 16px;border:1px solid #7b3735;border-radius:7px;background:#331918;color:#ffaaa6;cursor:pointer}}.muted{{color:var(--muted)}}
@media(max-width:720px){{.shell{{padding:20px 16px 16px}}.app-header{{align-items:flex-start}}.brand{{gap:10px}}.brand-mark{{width:50px;height:50px}}.brand-name{{font-size:1.3rem}}.version{{display:none}}.workspace{{margin-top:24px;padding:30px 20px 26px}}.workspace h1{{font-size:2rem}}.lead{{font-size:.95rem}}.setup-step{{grid-template-columns:46px 1fr;gap:12px}}.step-marker{{width:46px;height:46px}}.setup-step:not(:last-child)::before{{left:22px;top:42px}}.step-copy h2{{min-height:46px;font-size:1.08rem}}.check-row{{grid-template-columns:21px 1fr}}.check-row b{{grid-column:2}}.ready-mark{{width:78px;height:78px}}.ready-mark::after{{left:24px;top:18px;width:19px;height:34px}}.ready-facts,.form-grid{{grid-template-columns:1fr}}.quiet-actions{{gap:4px;flex-direction:column}}.service-note{{padding-bottom:4px}}}}
@media(prefers-reduced-motion:reduce){{*{{scroll-behavior:auto!important;transition:none!important}}}}
</style>
</head>
<body>
<main class="shell">
<header class="app-header">
  <div>
    <div class="brand"><span class="brand-mark"><img src="/assets/terrasatch-logo.webp" alt="TerraSatch Satchy"></span><div class="brand-name">TerraSatch <span>Edge</span></div></div>
    <div class="context">{html.escape(context_label)}</div>
  </div>
  <div class="version">v{html.escape(version)}</div>
</header>
<div id="notice" role="status" aria-live="polite"></div>
<section class="workspace"><div class="{"ready-content" if ready else "setup-content"}">{ready_content if ready else setup_content}<div id="quickResult" class="result-panel" aria-live="polite"></div></div></section>
<p class="service-note">The Edge service keeps running when you close this window.</p>

<dialog id="settingsDialog">
  <div class="dialog-head"><h2>Device settings</h2><button class="icon-button" type="button" aria-label="Close settings" onclick="closeDialog('settingsDialog')">×</button></div>
  <div class="dialog-body"><p class="dialog-intro">These settings affect only this Edge computer. Pairing controls the organization and field-site assignment.</p>
  <form id="configForm"><div class="form-grid">
    <div><label for="node_name">This PC name</label><input id="node_name" name="node_name" value="{html.escape(str(config['node_name'] or ''))}" placeholder="field-kit-01"></div>
    <div><label for="scan_interval_seconds">Check-in interval (seconds)</label><input id="scan_interval_seconds" name="scan_interval_seconds" type="number" min="5" max="3600" value="{int(config['scan_interval_seconds'])}"></div>
    <div><label for="source">Source label</label><input id="source" name="source" value="{html.escape(str(config['source']))}"></div>
    <div><label for="speech_model">Speech model</label><input id="speech_model" name="speech_model" value="{html.escape(str(config['speech_model']))}"></div>
    <div><label for="speech_device">Speech device</label><input id="speech_device" name="speech_device" value="{html.escape(str(config['speech_device']))}"></div>
    <div><label for="speech_compute_type">Speech compute type</label><input id="speech_compute_type" name="speech_compute_type" value="{html.escape(str(config['speech_compute_type']))}"></div>
    <div><label for="speech_language">Speech language</label><input id="speech_language" name="speech_language" value="{html.escape(str(config['speech_language'] or ''))}" placeholder="en"></div>
    <div><label for="api_url">TerraSatch API</label><input id="api_url" value="{html.escape(str(config['api_url']))}" readonly></div>
  </div><div class="form-actions"><button class="primary-action" type="submit">Save device settings</button></div></form></div>
</dialog>

<dialog id="detailsDialog">
  <div class="dialog-head"><h2>Device details</h2><button class="icon-button" type="button" aria-label="Close details" onclick="closeDialog('detailsDialog')">×</button></div>
  <div class="dialog-body"><p class="dialog-intro">Hardware and technical information for troubleshooting this computer.</p>
    <img class="brand-lockup" src="/assets/terrasatch-black-logo.png" alt="TerraSatch — Field Intelligence — Listen, Watch, Learn, Adapt">
    <details open><summary>Connected hardware</summary><div class="detail-content"><ul class="device-list">{device_items}</ul></div></details>
    <details><summary>Developer identifiers</summary><div class="detail-content id-list">
      <div><span>Device ID</span><code>{html.escape(str(status['device_id'] or 'Not paired'))}</code></div>
      <div><span>Organization ID</span><code>{html.escape(str(status['organization_id'] or 'Not assigned'))}</code></div>
      <div><span>Site ID</span><code>{html.escape(str(status['site_id'] or 'Not assigned'))}</code></div>
      <div><span>Platform</span><code>{html.escape(str(status.get('platform') or 'Unknown'))} / {html.escape(str(status.get('architecture') or 'Unknown'))}</code></div>
    </div></details>
    <details><summary>Raw hardware inventory</summary><div class="detail-content"><table><thead><tr><th>Type</th><th>Device</th><th>Status</th></tr></thead><tbody>{device_rows}</tbody></table></div></details>
    <details><summary>API health</summary><div class="detail-content"><pre>{health_payload}</pre></div></details>
    <details><summary>Terminal reference</summary><div class="detail-content"><pre>terrasatch-edge setup
terrasatch-edge scan
terrasatch-edge status
terrasatch-edge doctor
terrasatch-edge run --once
terrasatch-edge paths</pre></div></details>
    <details><summary>Credential management</summary><div class="detail-content"><p class="dialog-intro">Removing the credential requires this Edge to be paired again.</p><button class="danger" type="button" onclick="logoutEdge()">Remove local credential</button></div></details>
  </div>
</dialog>
</main>
<script>
const headers={{"Content-Type":"application/json","X-TerraSatch-Edge-UI":"1"}};
let pairingTimer=null;
function notify(message,error=false){{const el=document.getElementById("notice");el.textContent=message;el.style.display="block";el.style.background=error?"#351918":"#152d1e";el.style.borderColor=error?"#783b37":"#346447";window.setTimeout(()=>{{el.style.display="none";}},7000)}}
async function request(path,options={{}}){{const response=await fetch(path,options);let body={{}};try{{body=await response.json()}}catch(_error){{}}if(!response.ok)throw new Error(body.detail||("HTTP "+response.status));return body}}
function busy(button,isBusy,label){{if(!button)return;if(isBusy){{button.dataset.original=button.textContent;button.textContent=label;button.disabled=true}}else{{button.textContent=button.dataset.original||button.textContent;button.disabled=false}}}}
function openDialog(id){{const dialog=document.getElementById(id);if(dialog&&!dialog.open)dialog.showModal()}}
function closeDialog(id){{const dialog=document.getElementById(id);if(dialog&&dialog.open)dialog.close()}}
async function checkThisPC(button){{busy(button,true,"Checking this PC…");try{{const scan=await request("/api/scan",{{method:"POST",headers}});const current=await request("/api/status");if(current.api_online){{notify("This PC is ready to pair. "+scan.device_count+" hardware record(s) found.");window.setTimeout(()=>location.reload(),650)}}else{{notify("This PC is running, but TerraSatch cannot be reached. Check the internet connection and try again.",true)}}}}catch(error){{notify("This PC could not be checked: "+error.message,true)}}finally{{busy(button,false,"")}}}}
async function verifyEdge(button){{busy(button,true,"Verifying…");try{{const data=await request("/api/verify",{{method:"POST",headers}});if(data.api_online&&data.authenticated&&data.heartbeat){{notify("Setup complete. This Edge is ready.");window.setTimeout(()=>location.reload(),650)}}else{{notify("Verification needs attention: "+(data.error||data.heartbeat_error||"run diagnostics"),true)}}}}catch(error){{notify("Verification failed: "+error.message,true)}}finally{{busy(button,false,"")}}}}
function showResults(checks){{const panel=document.getElementById("quickResult");panel.replaceChildren();panel.style.display="block";checks.forEach(check=>{{const row=document.createElement("div");row.className="result-row"+(check.ok?"":" fail");const label=document.createElement("span");label.textContent=check.label;const value=document.createElement("b");value.textContent=check.ok?"Pass":"Check";row.append(label,value);panel.appendChild(row)}})}}
async function runQuickCheck(button){{busy(button,true,"Running check…");try{{const verification=await request("/api/verify",{{method:"POST",headers}});const doctor=await request("/api/doctor",{{method:"POST",headers}});const checks=[{{label:"TerraSatch connection",ok:Boolean(verification.api_online)}},{{label:"Device registration",ok:Boolean(verification.authenticated)}},{{label:"Heartbeat",ok:Boolean(verification.heartbeat)}},{{label:"Local diagnostics",ok:Boolean(doctor.ok)}}];showResults(checks);const failures=checks.filter(check=>!check.ok);notify(failures.length?"Quick check found "+failures.length+" item(s) that need attention.":"Quick check passed. This Edge is ready.",Boolean(failures.length))}}catch(error){{notify("Quick check failed: "+error.message,true)}}finally{{busy(button,false,"")}}}}
async function runDiagnostics(button){{busy(button,true,"Running diagnostics…");try{{const doctor=await request("/api/doctor",{{method:"POST",headers}});showResults(doctor.checks.map(check=>({{label:check.name,ok:Boolean(check.ok)}})));notify(doctor.ok?"Diagnostics passed.":"Diagnostics found items that need attention.",!doctor.ok)}}catch(error){{notify("Diagnostics failed: "+error.message,true)}}finally{{busy(button,false,"")}}}}
async function startPairing(button){{const panel=document.getElementById("pairing");busy(button,true,"Starting pairing…");try{{const data=await request("/api/pairing/start",{{method:"POST",headers}});panel.replaceChildren();panel.style.display="block";const code=document.createElement("strong");code.className="pairing-code";code.textContent="Pairing code: "+data.user_code;const detail=document.createElement("p");detail.textContent="Approve this PC for the correct organization and field site.";panel.append(code,detail);try{{const target=new URL(data.verification_url);if(target.protocol==="https:"||target.protocol==="http:"){{const link=document.createElement("a");link.className="inline-action";link.target="_blank";link.rel="noreferrer";link.href=target.href;link.textContent="Open TerraSatch";panel.appendChild(link)}}}}catch(_error){{}}if(pairingTimer)window.clearInterval(pairingTimer);const interval=Math.max(2000,(data.interval_seconds||5)*1000);pairingTimer=window.setInterval(()=>claimPairing(data.device_code),interval);await claimPairing(data.device_code)}}catch(error){{notify("Pairing could not start: "+error.message,true)}}finally{{busy(button,false,"")}}}}
async function claimPairing(deviceCode){{try{{const data=await request("/api/pairing/claim",{{method:"POST",headers,body:JSON.stringify({{device_code:deviceCode}})}});if(data.paired){{if(pairingTimer)window.clearInterval(pairingTimer);notify(data.heartbeat?"Pairing complete. This Edge is ready.":"Pairing complete. Finish verification next.",!data.heartbeat);window.setTimeout(()=>location.reload(),700)}}else if(["expired","claimed"].includes(data.status)){{if(pairingTimer)window.clearInterval(pairingTimer);notify("Pairing ended with status: "+data.status,true)}}}}catch(error){{if(pairingTimer)window.clearInterval(pairingTimer);notify("Pairing check failed: "+error.message,true)}}}}
const configForm=document.getElementById("configForm");if(configForm)configForm.addEventListener("submit",async event=>{{event.preventDefault();const form=new FormData(event.target);const payload={{node_name:form.get("node_name"),scan_interval_seconds:Number(form.get("scan_interval_seconds")),source:form.get("source"),speech_model:form.get("speech_model"),speech_device:form.get("speech_device"),speech_compute_type:form.get("speech_compute_type"),speech_language:form.get("speech_language")||null}};const button=event.submitter;busy(button,true,"Saving…");try{{await request("/api/config",{{method:"PUT",headers,body:JSON.stringify(payload)}});notify("Device settings saved.");closeDialog("settingsDialog")}}catch(error){{notify("Settings were not saved: "+error.message,true)}}finally{{busy(button,false,"")}}}});
async function logoutEdge(){{if(!confirm("Remove the local Edge credential? This computer will need to be paired again."))return;try{{await request("/api/logout",{{method:"POST",headers}});notify("Credential removed. Returning to setup.");window.setTimeout(()=>location.reload(),500)}}catch(error){{notify("Credential could not be removed: "+error.message,true)}}}}
</script>
</body>
</html>"""


def _check_row(label: str, detail: str, ok: bool) -> str:
    return (
        f'<div class="check-row {"pass" if ok else "pending"}">'
        '<span class="check-dot" aria-hidden="true"></span>'
        f"<span><strong>{html.escape(label)}</strong><small>{html.escape(detail)}</small></span>"
        f'<b>{"Ready" if ok else "Check"}</b></div>'
    )


def _group_label(kind: str, group: dict[str, Any]) -> str:
    if group["name"]:
        return str(group["name"])
    labels = {
        "audio": "Audio capture",
        "gps": "GPS receiver",
        "sdr": "Radio interface",
        "serial": "Serial interface",
        "system": "Edge computer",
    }
    label = labels.get(kind, kind.replace("_", " ").title() or "Unknown device")
    return f"{label}s" if group["count"] != 1 and not label.endswith("s") else label


def _step(
    number: int,
    title: str,
    *,
    done: bool,
    active: bool,
    body: str,
) -> str:
    marker = "✓" if done else str(number)
    active_body = f'<div class="step-body">{body}</div>' if active else ""
    return (
        f'<li class="setup-step {"active" if active else ""} {"done" if done else ""}">'
        f'<div class="step-marker" aria-hidden="true">{marker}</div>'
        f'<div class="step-copy"><h2>{html.escape(title)}</h2>{active_body}</div>'
        "</li>"
    )
