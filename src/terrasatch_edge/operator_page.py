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
    """Render the Edge field-gateway setup and connection surface."""
    devices = status["devices"]
    is_windows = (
        os.environ.get("TERRASATCH_EDGE_WINDOWS_CONSOLE") == "1"
        or "windows" in str(status.get("platform") or "").lower()
    )
    ready = bool(status["api_online"] and status["authenticated"])
    context_label = (
        ("Windows field gateway" if is_windows else "Local field gateway")
        if ready
        else ("Windows gateway setup" if is_windows else "Local gateway setup")
    )
    node_label = str(status["node_name"] or status["hostname"])
    site_label = status["site_name"] or (
        "Assigned field site" if status["site_id"] else "Not assigned"
    )
    device_label = (
        f"{status['device_count']} local device detected"
        if status["device_count"] == 1
        else f"{status['device_count']} local devices detected"
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
            "No additional local field hardware is connected.</td></tr>"
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
        f"<small>{group['count']} detected locally</small></span>"
        '<span class="status status-good">Ready</span>'
        "</li>"
        for kind, group in device_groups.items()
    )
    if not device_items:
        device_items = (
            '<li class="device-empty">No additional local hardware found. '
            "Phone and provider integrations can still use this workspace without "
            "being physically attached to this PC.</li>"
        )

    check_rows = "".join(
        [
            _check_row("TerraSatch Edge", "Field gateway is running on this PC", True),
            _check_row(
                "TerraSatch cloud",
                "API is reachable"
                if status["api_online"]
                else "API is not reachable",
                bool(status["api_online"]),
            ),
            _check_row(
                "Workspace pairing",
                "Gateway credential is saved"
                if status["configured"]
                else "Pair this gateway to a workspace",
                bool(status["configured"]),
            ),
        ]
    )

    active_step = 1 if not status["api_online"] else (2 if not status["configured"] else 3)
    steps = "".join(
        [
            _step(
                1,
                "Check the gateway",
                done=bool(status["api_online"]),
                active=not ready and active_step == 1,
                body=f"""
                <p class="step-note">Confirm this computer can reach TerraSatch. Local field hardware is optional during setup.</p>
                <div class="check-list">{check_rows}</div>
                <button class="primary-action" type="button" onclick="checkThisPC(this)">Check gateway</button>
                """,
            ),
            _step(
                2,
                "Pair your workspace",
                done=bool(status["configured"]),
                active=not ready and active_step == 2,
                body="""
                <p class="step-note">Pair this field gateway to the correct TerraSatch organization and site. Use your phone to scan a short-lived QR code, or open the approval page in this browser.</p>
                <button class="primary-action" type="button" onclick="startPairing(this)">Pair with phone or browser</button>
                <div id="pairing" class="pairing-panel" aria-live="polite"></div>
                """,
            ),
            _step(
                3,
                "Verify the connection",
                done=bool(status["authenticated"]),
                active=not ready and active_step == 3,
                body="""
                <p class="step-note">Verify the saved credential and send the first heartbeat. After this passes, connect only the field devices your team uses.</p>
                <button class="primary-action" type="button" onclick="verifyEdge(this)">Verify gateway</button>
                <button class="text-action" type="button" onclick="runDiagnostics(this)">Run diagnostics</button>
                """,
            ),
        ]
    )

    setup_content = f"""
    <div class="eyebrow">Satchy field gateway</div>
    <h1>Connect this Edge to TerraSatch</h1>
    <p class="lead">Pair the gateway first. Then add phones, radios, Meshtastic, Garmin, or other field inputs without rebuilding the core setup.</p>
    <ol class="setup-steps">{steps}</ol>
    """

    radio_detected = any(
        kind in {"sdr", "audio", "serial", "radio"} for kind in device_groups
    )
    mesh_detected = any(
        kind in {"meshtastic", "lora", "lorawan", "mesh"} for kind in device_groups
    )
    local_detected = bool(status["device_count"])

    connection_cards = "".join(
        [
            _connection_card(
                "mobile",
                "Phone / TerraSatch Mobile",
                "Companion",
                "Voice, notes, photos, GPS, and field observations can sync through the workspace. The phone does not need to be physically attached to this PC.",
                "Workspace ready" if ready else "Pair workspace first",
                "good" if ready else "warn",
                "Direct to TerraSatch",
                "View setup",
            ),
            _connection_card(
                "radio",
                "Radio / SDR",
                "Local",
                "Connect an SDR, handheld audio interface, or supported radio path to this gateway for local radio capture.",
                "Detected" if radio_detected else "Not detected",
                "good" if radio_detected else "warn",
                "Through this Edge",
                "Set up radio",
            ),
            _connection_card(
                "meshtastic",
                "Meshtastic / LoRa",
                "Local or network",
                "Use a local or network adapter for low-bandwidth field messages and location data once the TerraSatch adapter is enabled.",
                "Detected" if mesh_detected else "Adapter planned",
                "good" if mesh_detected else "neutral",
                "Adapter via Edge",
                "View connection path",
            ),
            _connection_card(
                "garmin",
                "Garmin / inReach",
                "Provider",
                "Garmin is workspace-managed through its provider integration. It does not need to be plugged into this Edge computer.",
                "Partner setup",
                "neutral",
                "Provider to TerraSatch",
                "View provider setup",
            ),
            _connection_card(
                "other",
                "Other field devices",
                "Local",
                "Sensors, GPS receivers, serial devices, cameras, and future adapters can attach through the Edge connector layer.",
                device_label if local_detected else "No local devices",
                "good" if local_detected else "neutral",
                "Through this Edge",
                "Inspect devices",
            ),
        ]
    )

    ready_content = f"""
    <div class="gateway-status">
      <span class="satchy-dot" aria-hidden="true"></span>
      <span>Satchy approved</span>
    </div>
    <h1>Your field gateway is online</h1>
    <p class="lead">This Edge is paired to TerraSatch. Add only the connections your team needs; phones and provider integrations do not have to be physically connected to this PC.</p>
    <dl class="ready-facts">
      <div><dt>This gateway</dt><dd>{html.escape(node_label)}</dd></div>
      <div><dt>Assigned site</dt><dd>{html.escape(str(site_label))}</dd></div>
      <div><dt>TerraSatch</dt><dd class="positive">Connected</dd></div>
      <div><dt>Local hardware</dt><dd>{html.escape(device_label)}</dd></div>
    </dl>
    <section class="mobile-field-flow" aria-labelledby="mobileFlowTitle">
      <div class="section-head">
        <div>
          <div class="eyebrow">Phone in the field</div>
          <h2 id="mobileFlowTitle">Capture once. Share the same Satchy context.</h2>
        </div>
        <span class="status status-good">Workspace ready</span>
      </div>
      <div class="capture-grid">
        <article class="capture-card"><span class="capture-icon">TXT</span><div><strong>Field note</strong><small>Typed observation → workspace → Satchy</small></div></article>
        <article class="capture-card"><span class="capture-icon">VOX</span><div><strong>Voice observation</strong><small>Voice transcript → canonical field input</small></div></article>
        <article class="capture-card"><span class="capture-icon">IMG</span><div><strong>Photo note</strong><small>Photo-note record + media reference</small></div></article>
        <article class="capture-card"><span class="capture-icon">GPS</span><div><strong>Location</strong><small>Latitude, longitude, altitude and accuracy</small></div></article>
      </div>
      <p class="capture-note"><strong>Current mobile path:</strong> TerraSatch Mobile signs into the same workspace and submits field observations directly. Arbitrary SMS/iMessage/third-party chat ingestion, binary media upload, and offline phone-to-Edge sync are separate future transports and are not shown as active here.</p>
    </section>
    <section class="connection-center" aria-labelledby="connectionsTitle">
      <div class="section-head">
        <div>
          <div class="eyebrow">Connection center</div>
          <h2 id="connectionsTitle">Connect field inputs</h2>
        </div>
        <button class="secondary-action" type="button" onclick="scanConnections(this)">Scan local hardware</button>
      </div>
      <div class="sequence" aria-label="Recommended setup sequence">
        <span class="sequence-done">1 Workspace paired</span>
        <b>→</b>
        <span>2 Connect field inputs</span>
        <b>→</b>
        <span>3 Verify the signal path</span>
      </div>
      <div class="signal-path" aria-label="TerraSatch field signal path">
        <span class="path-node">Field device</span>
        <b>→</b>
        <span class="path-node path-edge">Edge when local</span>
        <b>→</b>
        <span class="path-node path-satchy">Satchy</span>
        <b>→</b>
        <span class="path-node">TerraSatch intelligence</span>
      </div>
      <p class="path-note">Local radios, SDRs, sensors, and supported adapters use this Edge gateway. Mobile and provider integrations may send directly to the same TerraSatch workspace and still become available to Satchy.</p>
      <div class="connection-grid">{connection_cards}</div>
    </section>
    <div class="finish-actions">
      <button class="primary-action" type="button" onclick="runQuickCheck(this)">Test gateway flow</button>
      <div class="quiet-actions">
        <button class="text-action" type="button" onclick="openDialog('settingsDialog')">Gateway settings</button>
        <button class="text-action" type="button" onclick="openDialog('detailsDialog')">Advanced details</button>
      </div>
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
:root{{color-scheme:dark;--bg:#111317;--surface:#1b1e23;--surface2:#24282f;--surface3:#15171b;--line:#343942;--soft:#292e36;--text:#f0eee9;--muted:#8e96a3;--orange:#f2960d;--orange-hover:#ffab2e;--positive:#42d17b;--amber:#f2a51a;--red:#ff625c;--neutral:#9aa2ad;--ui:"Segoe UI",Inter,system-ui,sans-serif;--display:"Arial Narrow","Roboto Condensed","Segoe UI",sans-serif}}
*{{box-sizing:border-box}}html{{background:var(--bg)}}body{{min-width:320px;min-height:100vh;margin:0;background:radial-gradient(circle at 50% 24%,rgba(242,150,13,.045),transparent 30%),var(--bg);color:var(--text);font:16px var(--ui)}}
button,input,summary{{font:inherit}}button{{color:inherit}}button:focus-visible,input:focus-visible,summary:focus-visible{{outline:2px solid var(--orange);outline-offset:3px}}
.shell{{min-height:100vh;max-width:1440px;margin:auto;padding:22px 38px 18px;display:flex;flex-direction:column}}
.app-header{{display:flex;align-items:center;justify-content:space-between;gap:24px}}.brand{{display:flex;align-items:center;gap:14px}}
.brand-mark{{width:58px;height:58px;display:grid;place-items:center;flex:0 0 auto}}.brand-mark img{{display:block;width:100%;height:100%;object-fit:contain;filter:drop-shadow(0 5px 14px rgba(0,0,0,.34))}}
.brand-name{{font:950 clamp(1.35rem,2.6vw,2rem)/1 var(--display);letter-spacing:.025em;text-transform:uppercase}}.brand-name span{{color:var(--orange);font-weight:800;text-transform:none}}
.context{{margin-top:7px;color:var(--muted);font-size:.95rem}}.version{{color:#777f8b;font-size:.78rem}}
.workspace{{width:min(100%,1080px);margin:24px auto 12px;padding:34px 54px 30px;border:1px solid var(--line);border-radius:12px;background:linear-gradient(145deg,rgba(255,255,255,.018),rgba(255,255,255,.004)),var(--surface);box-shadow:0 24px 80px rgba(0,0,0,.24)}}
.workspace h1{{margin:0;text-align:center;font-size:clamp(2rem,4vw,2.75rem);line-height:1.08;letter-spacing:-.025em}}.workspace h2{{margin:0;font-size:1.35rem}}.lead{{max-width:760px;margin:12px auto 24px;text-align:center;color:#c6cbd2;font-size:1.03rem;line-height:1.55}}.eyebrow{{color:var(--orange);font-size:.72rem;font-weight:800;text-transform:uppercase;letter-spacing:.16em}}
.setup-content>.eyebrow{{text-align:center;margin-bottom:9px}}
.setup-steps{{list-style:none;margin:6px auto 0;padding:0;max-width:760px}}.setup-step{{position:relative;display:grid;grid-template-columns:52px 1fr;gap:16px;padding-bottom:18px}}
.setup-step:not(:last-child)::before{{content:"";position:absolute;left:25px;top:46px;bottom:-2px;width:1px;background:#4a5059}}
.step-marker{{position:relative;z-index:1;width:52px;height:52px;border:2px solid #555d68;border-radius:50%;display:grid;place-items:center;background:var(--surface);font-size:1.16rem;font-weight:650}}
.setup-step.active .step-marker{{border-color:var(--orange)}}.setup-step.done .step-marker{{border-color:var(--positive);color:var(--positive)}}.step-copy h2{{min-height:52px;margin:0;display:flex;align-items:center;font-size:1.2rem}}.step-body{{padding-top:2px}}
.check-list{{display:grid;gap:8px;margin-bottom:18px}}.check-row{{display:grid;grid-template-columns:24px 1fr auto;align-items:center;gap:13px;min-height:56px;padding:9px 15px;border:1px solid var(--line);border-radius:8px;background:rgba(255,255,255,.012)}}
.check-row span:nth-child(2){{display:grid;gap:2px}}.check-row strong{{font-weight:600}}.check-row small{{color:var(--muted);font-size:.78rem}}.check-row b{{color:var(--amber);font-size:.74rem;text-transform:uppercase;letter-spacing:.08em}}.check-row.pass b{{color:var(--positive)}}
.check-dot{{width:19px;height:19px;border:2px solid currentColor;border-radius:50%;color:var(--amber);position:relative}}.check-row.pass .check-dot{{color:var(--positive)}}.check-row.pass .check-dot::after{{content:"";position:absolute;left:4px;top:1px;width:5px;height:9px;border:solid currentColor;border-width:0 2px 2px 0;transform:rotate(45deg)}}
.step-note{{margin:0 0 16px;color:#c5cad1;line-height:1.55}}.primary-action{{display:block;width:min(100%,440px);min-height:54px;margin:auto;border:0;border-radius:8px;background:var(--orange);color:#111317;font-weight:800;cursor:pointer;transition:.16s ease}}.primary-action:hover{{background:var(--orange-hover);transform:translateY(-1px)}}.primary-action:disabled{{opacity:.7;cursor:wait;transform:none}}
.secondary-action{{min-height:42px;padding:0 15px;border:1px solid #5b4525;border-radius:8px;background:#211a10;color:#f7b64c;font-weight:700;cursor:pointer}}.secondary-action:hover{{border-color:var(--orange);color:#ffd08a}}
.text-action{{display:block;margin:15px auto 0;padding:3px 5px;border:0;background:transparent;color:var(--orange);text-decoration:underline;text-underline-offset:4px;cursor:pointer}}.text-action:hover{{color:var(--orange-hover)}}
.pairing-panel,.result-panel{{display:none;margin:18px 0 0;padding:18px;border:1px solid var(--line);border-radius:10px;background:var(--surface2)}}.pairing-grid{{display:grid;grid-template-columns:minmax(180px,230px) minmax(0,1fr);gap:20px;align-items:center}}.pairing-qr-wrap{{display:grid;place-items:center;padding:14px;border:1px solid #3b414a;border-radius:10px;background:#f7f5ef}}.pairing-qr{{display:block;width:min(100%,210px);aspect-ratio:1;object-fit:contain}}.pairing-copy{{display:grid;gap:11px;min-width:0}}.pairing-kicker{{color:var(--orange);font-size:.7rem;font-weight:850;text-transform:uppercase;letter-spacing:.12em}}.pairing-code-row{{display:flex;align-items:center;gap:9px;flex-wrap:wrap}}.pairing-code{{font:1.25rem ui-monospace,Consolas,monospace;color:var(--orange);letter-spacing:.06em;overflow-wrap:anywhere}}.pairing-panel p{{margin:0;color:var(--muted);line-height:1.5}}.pairing-actions{{display:flex;align-items:center;gap:9px;flex-wrap:wrap}}.inline-action{{display:inline-flex;min-height:42px;align-items:center;padding:0 16px;border-radius:7px;background:var(--orange);color:#111317;font-weight:700;text-decoration:none}}.ghost-action{{min-height:42px;padding:0 14px;border:1px solid #4a515b;border-radius:7px;background:#191c21;color:#d5d9de;font-weight:700;cursor:pointer}}.ghost-action:hover{{border-color:#747d89}}.pairing-wait{{display:flex;align-items:center;gap:8px;margin-top:3px;color:#9ce7b6;font-size:.78rem}}.pairing-pulse{{width:8px;height:8px;border-radius:50%;background:var(--positive);box-shadow:0 0 0 0 rgba(66,209,123,.45);animation:pairingPulse 1.8s infinite}}@keyframes pairingPulse{{0%{{box-shadow:0 0 0 0 rgba(66,209,123,.4)}}70%{{box-shadow:0 0 0 9px rgba(66,209,123,0)}}100%{{box-shadow:0 0 0 0 rgba(66,209,123,0)}}}}
.gateway-status{{width:max-content;margin:2px auto 12px;padding:7px 11px;border:1px solid rgba(66,209,123,.32);border-radius:999px;background:rgba(66,209,123,.08);color:#8ce8ae;font-size:.76rem;font-weight:800;text-transform:uppercase;letter-spacing:.1em;display:flex;align-items:center;gap:8px}}.satchy-dot{{width:8px;height:8px;border-radius:50%;background:var(--positive);box-shadow:0 0 14px rgba(66,209,123,.5)}}
.ready-facts{{display:grid;grid-template-columns:1fr 1fr;gap:0 28px;width:min(100%,760px);margin:28px auto 32px;text-align:left}}.ready-facts div{{padding:15px 4px;border-bottom:1px solid var(--line)}}.ready-facts dt{{color:var(--muted);font-size:.85rem}}.ready-facts dd{{margin:6px 0 0;font-size:1.05rem;font-weight:650;overflow-wrap:anywhere}}.positive{{color:var(--positive)}}
.mobile-field-flow,.connection-center{{margin:18px 0 0;padding:24px;border:1px solid var(--line);border-radius:11px;background:var(--surface3);text-align:left}}.mobile-field-flow{{background:linear-gradient(145deg,rgba(242,150,13,.035),transparent 55%),#15171b}}.section-head{{display:flex;align-items:end;justify-content:space-between;gap:20px}}.section-head .eyebrow{{margin-bottom:6px}}.capture-grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-top:18px}}.capture-card{{display:flex;align-items:center;gap:10px;padding:13px;border:1px solid #303640;border-radius:9px;background:#191c21;min-width:0}}.capture-icon{{width:38px;height:38px;display:grid;place-items:center;flex:0 0 auto;border:1px solid #6f5321;border-radius:9px;background:#211a10;color:#ffc66b;font:800 .68rem ui-monospace,Consolas,monospace;letter-spacing:.04em}}.capture-card div{{display:grid;gap:3px;min-width:0}}.capture-card strong{{font-size:.86rem}}.capture-card small{{color:#8e96a3;font-size:.7rem;line-height:1.35}}.capture-note{{margin:14px 0 0;padding:12px 14px;border:1px solid #343a43;border-radius:8px;background:#101216;color:#9da5af;font-size:.76rem;line-height:1.55}}.capture-note strong{{color:#d5d9df}}
.sequence{{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:17px 0 14px;padding:11px 13px;border:1px solid #303640;border-radius:8px;background:#101216;color:var(--muted);font-size:.8rem}}.sequence b{{color:#58606b}}.sequence-done{{color:#8ce8ae}}
.signal-path{{display:flex;align-items:center;justify-content:center;gap:9px;flex-wrap:wrap;margin:0 0 8px;padding:14px;border:1px solid #343a43;border-radius:9px;background:#111419}}.signal-path b{{color:#5c6470}}.path-node{{padding:7px 10px;border:1px solid #3a4049;border-radius:999px;color:#c9ced5;font-size:.72rem;font-weight:750;letter-spacing:.035em}}.path-edge{{border-color:#6f5321;color:#ffc66b;background:#211a10}}.path-satchy{{border-color:rgba(66,209,123,.32);color:#8ce8ae;background:rgba(66,209,123,.07)}}.path-note{{margin:0 0 20px;color:#929aa5;font-size:.78rem;line-height:1.5;text-align:center}}
.connection-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}}.connection-card{{min-width:0;padding:17px;border:1px solid #303640;border-radius:9px;background:#191c21;display:flex;flex-direction:column;gap:12px}}.connection-card:hover{{border-color:#414853}}.connection-top{{display:flex;align-items:flex-start;justify-content:space-between;gap:14px}}.connection-card h3{{margin:0;font-size:1rem}}.connection-type{{display:inline-block;margin-top:5px;color:var(--muted);font-size:.7rem;text-transform:uppercase;letter-spacing:.08em}}.connection-card p{{margin:0;color:#aeb5bf;font-size:.84rem;line-height:1.45}}.connection-route{{display:flex;align-items:center;gap:7px;color:#858e99;font-size:.72rem}}.connection-route::before{{content:"";width:7px;height:7px;border-radius:50%;background:var(--orange);box-shadow:0 0 0 3px rgba(242,150,13,.08)}}.connection-footer{{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:auto}}.card-action{{padding:0;border:0;background:transparent;color:var(--orange);font-size:.8rem;font-weight:700;cursor:pointer;text-align:right}}.card-action:hover{{color:var(--orange-hover)}}
.status{{display:inline-flex;align-items:center;min-height:25px;padding:0 9px;border-radius:999px;font-size:.68rem;font-weight:800;white-space:nowrap}}.status-good{{color:#8ce8ae;background:rgba(66,209,123,.1);border:1px solid rgba(66,209,123,.28)}}.status-warn{{color:#ffc96f;background:rgba(242,165,26,.09);border:1px solid rgba(242,165,26,.3)}}.status-neutral{{color:#b4bbc5;background:rgba(154,162,173,.08);border:1px solid rgba(154,162,173,.24)}}.status-bad{{color:#ffaaa6;background:rgba(255,98,92,.08);border:1px solid rgba(255,98,92,.28)}}
.finish-actions{{margin-top:24px}}.quiet-actions{{display:flex;justify-content:center;gap:42px}}
.result-panel{{max-width:760px;margin:22px auto 0;text-align:left}}.result-row{{display:flex;justify-content:space-between;gap:16px;padding:10px 0;border-bottom:1px solid var(--soft)}}.result-row:last-child{{border:0}}.result-row b{{color:var(--positive);font-size:.75rem;text-transform:uppercase;letter-spacing:.08em}}.result-row.fail b{{color:var(--red)}}
.service-note{{margin:auto auto 0;padding-top:14px;color:#858d98;text-align:center;font-size:.88rem}}#notice{{position:fixed;z-index:20;left:50%;top:18px;transform:translateX(-50%);display:none;width:min(calc(100% - 32px),720px);padding:13px 17px;border:1px solid #765415;border-radius:8px;background:#2a2112;box-shadow:0 14px 40px rgba(0,0,0,.35)}}
dialog{{width:min(calc(100% - 32px),780px);max-height:88vh;padding:0;border:1px solid var(--line);border-radius:10px;background:var(--surface);color:var(--text);box-shadow:0 28px 90px rgba(0,0,0,.7)}}dialog::backdrop{{background:rgba(0,0,0,.76)}}.dialog-head{{position:sticky;top:0;z-index:2;display:flex;align-items:center;justify-content:space-between;padding:20px 24px;border-bottom:1px solid var(--line);background:var(--surface)}}.dialog-head h2{{margin:0;font-size:1.25rem}}.icon-button{{width:40px;height:40px;border:1px solid var(--line);border-radius:7px;background:transparent;color:var(--muted);font-size:1.35rem;cursor:pointer}}.dialog-body{{padding:24px;overflow:auto}}.dialog-intro{{margin:0 0 20px;color:var(--muted);line-height:1.5}}.connection-help{{display:grid;gap:12px}}.connection-help h3{{margin:0;font-size:1.35rem}}.connection-help p{{margin:0;color:#bcc2ca;line-height:1.55}}.connection-dialog-meta{{display:flex;justify-content:flex-start}}.connection-path-box{{display:grid;gap:6px;padding:13px 14px;border:1px solid #343a43;border-radius:8px;background:#111419}}.connection-path-box span{{color:var(--muted);font-size:.7rem;text-transform:uppercase;letter-spacing:.1em}}.connection-path-box strong{{color:#f1eee7;font-size:.9rem;line-height:1.45}}.connection-steps{{display:grid;gap:9px;margin:2px 0;padding:0;counter-reset:connectstep;list-style:none}}.connection-steps li{{position:relative;padding:11px 12px 11px 42px;border:1px solid #303640;border-radius:8px;background:#181b20;color:#c7ccd3;line-height:1.45}}.connection-steps li::before{{counter-increment:connectstep;content:counter(connectstep);position:absolute;left:12px;top:10px;width:21px;height:21px;display:grid;place-items:center;border:1px solid #6a4e1d;border-radius:50%;color:#ffc66b;font-size:.68rem;font-weight:800}}.connection-result{{padding:11px 13px;border:1px solid rgba(66,209,123,.25);border-radius:8px;background:rgba(66,209,123,.06);color:#9ce7b6!important}}.connection-help .helper-note{{padding:12px 14px;border-left:3px solid var(--orange);background:#191710;color:#d6c6aa}}.dialog-actions{{display:flex;gap:10px;flex-wrap:wrap}}
.device-list{{list-style:none;margin:0;padding:0}}.device-row{{display:flex;justify-content:space-between;gap:20px;padding:14px 0;border-bottom:1px solid var(--soft)}}.device-row span:first-child{{display:grid;gap:3px}}.device-row small{{color:var(--muted);text-transform:capitalize}}.device-empty{{padding:18px;border:1px dashed var(--line);border-radius:8px;color:var(--muted);line-height:1.5}}
.form-grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}.form-span{{grid-column:1/-1}}label{{display:block;margin-bottom:6px;color:#c9cdd3;font-size:.82rem}}input{{width:100%;min-height:44px;padding:10px 12px;border:1px solid #3b414a;border-radius:7px;background:#0b0d10;color:var(--text)}}input[readonly]{{color:#858d98}}.settings-section{{padding:16px 0 20px;border-bottom:1px solid var(--line)}}.settings-section:first-of-type{{padding-top:0}}.settings-section-head{{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:12px}}.settings-section-head h3{{margin:3px 0 0;font-size:1.05rem}}.settings-kicker{{color:var(--orange);font-size:.67rem;font-weight:800;text-transform:uppercase;letter-spacing:.12em}}.settings-help{{margin:0 0 14px;color:var(--muted);font-size:.78rem;line-height:1.5}}.toggle-field{{display:flex;align-items:center;gap:10px;min-height:58px;margin:0;padding:10px 12px;border:1px solid #3b414a;border-radius:7px;background:#0b0d10;cursor:pointer}}.toggle-field input{{width:18px;min-height:18px;margin:0;accent-color:var(--orange)}}.toggle-field span{{display:grid;gap:2px}}.toggle-field strong{{font-size:.82rem}}.toggle-field small{{color:var(--muted);font-size:.7rem}}.settings-details{{margin-top:4px}}.settings-details summary{{color:#d5d9df}}.form-actions{{margin-top:22px}}.form-actions .primary-action{{margin:0}}
details{{border-top:1px solid var(--line)}}details:first-of-type{{border-top:0}}summary{{position:relative;padding:16px 2px;cursor:pointer;font-weight:600;list-style:none}}summary::-webkit-details-marker{{display:none}}summary::after{{content:"+";position:absolute;right:4px;color:var(--muted)}}details[open] summary::after{{content:"−"}}.detail-content{{padding:0 2px 18px}}.brand-lockup{{display:grid;grid-template-columns:minmax(92px,148px) minmax(0,1fr);align-items:center;gap:18px;width:min(100%,620px);margin:2px auto 20px}}.brand-lockup-mark{{display:block;width:100%;aspect-ratio:1;object-fit:contain;filter:drop-shadow(0 7px 18px rgba(0,0,0,.32))}}.brand-lockup-copy{{min-width:0;text-align:left;text-transform:uppercase}}.brand-lockup-kicker{{color:var(--orange);font:800 clamp(.58rem,1.6vw,.82rem)/1.15 ui-monospace,Consolas,monospace;letter-spacing:.3em;white-space:nowrap}}.brand-lockup-name{{margin:7px 0 8px;color:var(--text);font:950 clamp(2rem,7.2vw,3.75rem)/.88 var(--display);letter-spacing:-.035em}}.brand-lockup-values{{display:flex;align-items:center;justify-content:space-between;gap:7px;color:var(--text);font:850 clamp(.58rem,1.65vw,.88rem)/1 var(--display);letter-spacing:.1em;white-space:nowrap}}.brand-lockup-values b{{color:var(--orange);font-weight:900}}.id-list{{display:grid;gap:12px}}.id-list div{{display:grid;gap:5px}}.id-list span{{color:var(--muted);font-size:.78rem}}code,pre{{font-family:ui-monospace,Consolas,monospace}}code{{overflow-wrap:anywhere}}pre{{margin:0;padding:14px;border-radius:7px;background:#090b0d;color:#cbd0d6;overflow:auto;font-size:.78rem;line-height:1.55}}table{{width:100%;border-collapse:collapse;font-size:.85rem}}th,td{{padding:10px;text-align:left;border-bottom:1px solid var(--soft)}}th{{color:var(--muted);font-weight:600}}.danger{{min-height:44px;padding:0 16px;border:1px solid #7b3735;border-radius:7px;background:#331918;color:#ffaaa6;cursor:pointer}}.muted{{color:var(--muted)}}
@media(max-width:980px){{.capture-grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}
@media(max-width:820px){{.connection-grid{{grid-template-columns:1fr}}.section-head{{align-items:flex-start;flex-direction:column}}.pairing-grid{{grid-template-columns:1fr}}.pairing-qr-wrap{{width:min(100%,280px);margin:auto}}}}
@media(max-width:720px){{.shell{{padding:20px 16px 16px}}.app-header{{align-items:flex-start}}.brand{{gap:10px}}.brand-mark{{width:50px;height:50px}}.brand-name{{font-size:1.3rem}}.version{{display:none}}.workspace{{margin-top:24px;padding:30px 20px 26px}}.workspace h1{{font-size:2rem}}.lead{{font-size:.95rem}}.setup-step{{grid-template-columns:46px 1fr;gap:12px}}.step-marker{{width:46px;height:46px}}.setup-step:not(:last-child)::before{{left:22px;top:42px}}.step-copy h2{{min-height:46px;font-size:1.08rem}}.check-row{{grid-template-columns:21px 1fr}}.check-row b{{grid-column:2}}.ready-facts,.form-grid{{grid-template-columns:1fr}}.quiet-actions{{gap:4px;flex-direction:column}}.sequence b{{display:none}}.capture-grid{{grid-template-columns:1fr}}.pairing-actions{{align-items:stretch;flex-direction:column}}.pairing-actions .inline-action,.pairing-actions .ghost-action{{width:100%;justify-content:center}}.service-note{{padding-bottom:4px}}.brand-lockup{{grid-template-columns:68px minmax(0,1fr);gap:10px}}.brand-lockup-kicker{{font-size:.48rem;letter-spacing:.2em}}.brand-lockup-name{{font-size:1.45rem;letter-spacing:-.045em}}.brand-lockup-values{{font-size:.45rem;gap:2px;letter-spacing:.035em}}}}
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
<p class="service-note">TerraSatch Edge keeps the field gateway running when you close this window.</p>

<dialog id="connectionDialog">
  <div class="dialog-head"><h2 id="connectionTitle">Field connection</h2><button class="icon-button" type="button" aria-label="Close connection help" onclick="closeDialog('connectionDialog')">×</button></div>
  <div class="dialog-body">
    <div class="connection-help">
      <div class="connection-dialog-meta"><span id="connectionMode" class="status status-neutral"></span></div>
      <h3 id="connectionHeading"></h3>
      <p id="connectionBody"></p>
      <div class="connection-path-box">
        <span>Signal path</span>
        <strong id="connectionPath"></strong>
      </div>
      <ol id="connectionSteps" class="connection-steps"></ol>
      <p id="connectionResult" class="connection-result"></p>
      <p id="connectionNote" class="helper-note"></p>
      <div class="dialog-actions">
        <button id="connectionScan" class="secondary-action" type="button" onclick="scanConnections(this)">Scan local hardware</button>
        <button class="secondary-action" type="button" onclick="closeDialog('connectionDialog');runQuickCheck(document.querySelector('.finish-actions .primary-action'))">Test TerraSatch path</button>
      </div>
    </div>
  </div>
</dialog>

<dialog id="settingsDialog">
  <div class="dialog-head"><h2>Gateway settings</h2><button class="icon-button" type="button" aria-label="Close settings" onclick="closeDialog('settingsDialog')">×</button></div>
  <div class="dialog-body"><p class="dialog-intro">Start with the field connection. Advanced speech/runtime tuning stays out of the way unless you need it.</p>
  <form id="configForm">
    <section class="settings-section">
      <div class="settings-section-head"><div><span class="settings-kicker">Gateway</span><h3>This Edge</h3></div><span class="status status-good">Paired</span></div>
      <div class="form-grid">
        <div><label for="node_name">Gateway name</label><input id="node_name" name="node_name" value="{html.escape(str(config['node_name'] or ''))}" placeholder="field-kit-01"></div>
        <div><label for="scan_interval_seconds">Check-in interval (seconds)</label><input id="scan_interval_seconds" name="scan_interval_seconds" type="number" min="5" max="3600" value="{int(config['scan_interval_seconds'])}"></div>
        <div class="form-span"><label for="api_url">TerraSatch API</label><input id="api_url" value="{html.escape(str(config['api_url']))}" readonly></div>
      </div>
    </section>
    <section class="settings-section">
      <div class="settings-section-head"><div><span class="settings-kicker">Local device</span><h3>Radio receive</h3></div><span class="status status-neutral">RX only</span></div>
      <p class="settings-help">Configure the receive path after Edge detects your SDR/radio interface. This does not enable transmit.</p>
      <div class="form-grid">
        <div><label for="radio_profile">Radio profile</label><input id="radio_profile" name="radio_profile" value="{html.escape(str(config['radio_profile']))}" placeholder="bca-frs-na"></div>
        <div><label for="radio_channel">Channel</label><input id="radio_channel" name="radio_channel" type="number" min="1" max="22" value="{html.escape(str(config['radio_channel'] or ''))}" placeholder="1–22"></div>
        <div><label for="radio_squelch">Squelch</label><input id="radio_squelch" name="radio_squelch" type="number" min="1" max="100" value="{int(config['radio_squelch'])}"></div>
        <label class="toggle-field" for="radio_auto_calibrate"><input id="radio_auto_calibrate" name="radio_auto_calibrate" type="checkbox" {"checked" if config["radio_auto_calibrate"] else ""}><span><strong>Auto-calibrate receiver</strong><small>Recommended for field setup</small></span></label>
      </div>
    </section>
    <details class="settings-details">
      <summary>Speech & advanced processing</summary>
      <div class="detail-content">
        <div class="form-grid">
          <div><label for="source">Source label</label><input id="source" name="source" value="{html.escape(str(config['source']))}"></div>
          <div><label for="speech_model">Speech model</label><input id="speech_model" name="speech_model" value="{html.escape(str(config['speech_model']))}"></div>
          <div><label for="speech_device">Speech device</label><input id="speech_device" name="speech_device" value="{html.escape(str(config['speech_device']))}"></div>
          <div><label for="speech_compute_type">Speech compute type</label><input id="speech_compute_type" name="speech_compute_type" value="{html.escape(str(config['speech_compute_type']))}"></div>
          <div><label for="speech_language">Speech language</label><input id="speech_language" name="speech_language" value="{html.escape(str(config['speech_language'] or ''))}" placeholder="en"></div>
        </div>
      </div>
    </details>
    <div class="form-actions"><button class="primary-action" type="submit">Save gateway settings</button></div>
  </form></div>
</dialog>

<dialog id="detailsDialog">
  <div class="dialog-head"><h2>Advanced gateway details</h2><button class="icon-button" type="button" aria-label="Close details" onclick="closeDialog('detailsDialog')">×</button></div>
  <div class="dialog-body"><p class="dialog-intro">Hardware and technical information for troubleshooting this field gateway.</p>
    <div class="brand-lockup" role="img" aria-label="TerraSatch — Field Intelligence — Listen, Watch, Learn, Adapt">
      <img class="brand-lockup-mark" src="/assets/terrasatch-logo.webp" alt="">
      <div class="brand-lockup-copy"><div class="brand-lockup-kicker">Field Intelligence</div><div class="brand-lockup-name">TerraSatch</div><div class="brand-lockup-values"><span>Listen</span><b>|</b><span>Watch</span><b>|</b><span>Learn</span><b>|</b><span>Adapt</span></div></div>
    </div>
    <details open><summary>Connected local hardware</summary><div class="detail-content"><ul class="device-list">{device_items}</ul></div></details>
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
const connectionHelp={{
  mobile:{{
    title:"Phone / TerraSatch Mobile",
    mode:"Workspace companion",
    body:"A phone can act as a first-class field input without being physically tethered to this computer. Notes, voice transcripts, photos, and GPS observations land in the same paired workspace that this Edge uses.",
    path:"Phone → TerraSatch workspace → Satchy → shared observations, map, timeline and reports",
    steps:["Sign in to the same TerraSatch organization on the phone.","Select the same field site assigned to this Edge.","Create a note, voice observation, photo note, or GPS observation.","Confirm the observation appears in the shared workspace and is available to Satchy."],
    result:"Expected result: phone and Edge observations coexist in the same TerraSatch operational context.",
    note:"Normal mobile sync is direct to TerraSatch. A future local/offline phone-to-Edge transport can be added without changing the canonical field-input model.",
    scan:false
  }},
  radio:{{
    title:"Radio / SDR",
    mode:"Local Edge connection",
    body:"Radio and SDR hardware are local gateway connections. Edge discovers supported USB, serial, audio, and SDR interfaces, then the radio runtime handles receive/capture using the configured target.",
    path:"Radio / SDR → this Edge → TerraSatch API → Satchy → radio log and operational events",
    steps:["Plug the SDR, radio interface, or audio device into this Edge computer.","Run the local hardware scan and confirm the intended device is detected.","Open Gateway settings / radio tooling and select the intended receive path and target.","Keep TerraSatch Radio disabled until the target is configured, then test receive before enabling unattended startup."],
    result:"Expected result: a field call becomes a TerraSatch transmission/transcript and is available to Satchy.",
    note:"Do not run the old Edge radio service and the MSIX radio runtime against the same receiver at the same time.",
    scan:true
  }},
  meshtastic:{{
    title:"Meshtastic / LoRa",
    mode:"Planned Edge adapter",
    body:"Meshtastic belongs in the Edge connector layer, but the dedicated TerraSatch adapter is not implemented yet. The UI shows the intended local/network path without claiming the integration is already active.",
    path:"Meshtastic node → Edge adapter (planned) → TerraSatch → Satchy",
    steps:["Pair the Meshtastic node with its normal phone/USB/network transport.","Enable the future TerraSatch Meshtastic adapter when available.","Map node identity, message/location payloads, and site context into the Edge connector.","Verify a test mesh message appears in the TerraSatch workspace."],
    result:"Current result: architecture is reserved, but Meshtastic traffic is not yet ingested by Edge.",
    note:"A generic USB/serial detection is not proof that Meshtastic message ingestion is configured.",
    scan:true
  }},
  garmin:{{
    title:"Garmin / inReach",
    mode:"Provider connection",
    body:"Garmin inReach uses the TerraSatch provider layer rather than a physical Edge-PC connection. The current API receiver supports Garmin IPC ingestion, while provider access remains partner-gated.",
    path:"Garmin inReach / Portal Connect → TerraSatch provider endpoint → Satchy → shared workspace",
    steps:["Obtain/confirm Garmin Portal Connect access for the organization.","Create the Garmin provider connection for the TerraSatch organization/site.","Configure the provider callback/static token and optional device allowlist.","Send a test inReach message or location event and confirm it reaches the shared workspace."],
    result:"Expected result after provider approval: Garmin field messages enter the same canonical intelligence pipeline as Edge and mobile inputs.",
    note:"Do not plug the Garmin device into this Edge PC just to make the provider integration work.",
    scan:false
  }},
  other:{{
    title:"Other field devices",
    mode:"Local Edge connector",
    body:"GPS receivers, serial devices, sensors, cameras, and future adapters can use the Edge connector layer when a matching local adapter exists.",
    path:"Local device → this Edge → adapter/canonical input → TerraSatch → Satchy",
    steps:["Connect the device by USB, serial, audio, Bluetooth/network bridge, or another supported local interface.","Run the hardware scan and identify the device in Advanced details.","Enable or configure the matching TerraSatch adapter when one exists.","Send a controlled test observation and verify the resulting TerraSatch event."],
    result:"Expected result: supported device data is normalized into the TerraSatch field-input pipeline.",
    note:"Detection and permission are separate: seeing hardware does not automatically enable capture, transmit, or device control.",
    scan:true
  }}
}};
function notify(message,error=false){{const el=document.getElementById("notice");el.textContent=message;el.style.display="block";el.style.background=error?"#351918":"#17271e";el.style.borderColor=error?"#783b37":"#2f6f48";window.setTimeout(()=>{{el.style.display="none";}},7000)}}
async function request(path,options={{}}){{const response=await fetch(path,options);let body={{}};try{{body=await response.json()}}catch(_error){{}}if(!response.ok)throw new Error(body.detail||("HTTP "+response.status));return body}}
function busy(button,isBusy,label){{if(!button)return;if(isBusy){{button.dataset.original=button.textContent;button.textContent=label;button.disabled=true}}else{{button.textContent=button.dataset.original||button.textContent;button.disabled=false}}}}
function openDialog(id){{const dialog=document.getElementById(id);if(dialog&&!dialog.open)dialog.showModal()}}
function closeDialog(id){{const dialog=document.getElementById(id);if(dialog&&dialog.open)dialog.close()}}
function openConnection(kind){{const data=connectionHelp[kind];if(!data)return;document.getElementById("connectionHeading").textContent=data.title;document.getElementById("connectionMode").textContent=data.mode;document.getElementById("connectionBody").textContent=data.body;document.getElementById("connectionPath").textContent=data.path;document.getElementById("connectionResult").textContent=data.result;document.getElementById("connectionNote").textContent=data.note;const steps=document.getElementById("connectionSteps");steps.replaceChildren();data.steps.forEach(step=>{{const item=document.createElement("li");item.textContent=step;steps.appendChild(item)}});document.getElementById("connectionScan").style.display=data.scan?"inline-flex":"none";openDialog("connectionDialog")}}
async function checkThisPC(button){{busy(button,true,"Checking gateway…");try{{const scan=await request("/api/scan",{{method:"POST",headers}});const current=await request("/api/status");if(current.api_online){{notify("Gateway can reach TerraSatch. "+scan.device_count+" local hardware record(s) found.");window.setTimeout(()=>location.reload(),650)}}else{{notify("This gateway is running, but TerraSatch cannot be reached. Check the internet connection and try again.",true)}}}}catch(error){{notify("Gateway check failed: "+error.message,true)}}finally{{busy(button,false,"")}}}}
async function scanConnections(button){{busy(button,true,"Scanning…");try{{const scan=await request("/api/scan",{{method:"POST",headers}});notify("Local scan complete. "+scan.device_count+" hardware record(s) found.");window.setTimeout(()=>location.reload(),650)}}catch(error){{notify("Hardware scan failed: "+error.message,true)}}finally{{busy(button,false,"")}}}}
async function verifyEdge(button){{busy(button,true,"Verifying…");try{{const data=await request("/api/verify",{{method:"POST",headers}});if(data.api_online&&data.authenticated&&data.heartbeat){{notify("Gateway verified. Satchy is ready for field connections.");window.setTimeout(()=>location.reload(),650)}}else{{notify("Verification needs attention: "+(data.error||data.heartbeat_error||"run diagnostics"),true)}}}}catch(error){{notify("Verification failed: "+error.message,true)}}finally{{busy(button,false,"")}}}}
function showResults(checks){{const panel=document.getElementById("quickResult");panel.replaceChildren();panel.style.display="block";checks.forEach(check=>{{const row=document.createElement("div");row.className="result-row"+(check.ok?"":" fail");const label=document.createElement("span");label.textContent=check.label;const value=document.createElement("b");value.textContent=check.ok?"Pass":"Check";row.append(label,value);panel.appendChild(row)}})}}
async function runQuickCheck(button){{busy(button,true,"Testing flow…");try{{const verification=await request("/api/verify",{{method:"POST",headers}});const doctor=await request("/api/doctor",{{method:"POST",headers}});const checks=[{{label:"TerraSatch connection",ok:Boolean(verification.api_online)}},{{label:"Workspace registration",ok:Boolean(verification.authenticated)}},{{label:"Gateway heartbeat",ok:Boolean(verification.heartbeat)}},{{label:"Local diagnostics",ok:Boolean(doctor.ok)}}];showResults(checks);const failures=checks.filter(check=>!check.ok);notify(failures.length?"Gateway test found "+failures.length+" item(s) that need attention.":"Gateway flow passed. Satchy is ready.",Boolean(failures.length))}}catch(error){{notify("Gateway test failed: "+error.message,true)}}finally{{busy(button,false,"")}}}}
async function runDiagnostics(button){{busy(button,true,"Running diagnostics…");try{{const doctor=await request("/api/doctor",{{method:"POST",headers}});showResults(doctor.checks.map(check=>({{label:check.name,ok:Boolean(check.ok)}})));notify(doctor.ok?"Diagnostics passed.":"Diagnostics found items that need attention.",!doctor.ok)}}catch(error){{notify("Diagnostics failed: "+error.message,true)}}finally{{busy(button,false,"")}}}}
async function startPairing(button){{const panel=document.getElementById("pairing");busy(button,true,"Creating secure pairing…");try{{const data=await request("/api/pairing/start",{{method:"POST",headers}});panel.replaceChildren();panel.style.display="block";const grid=document.createElement("div");grid.className="pairing-grid";const qrWrap=document.createElement("div");qrWrap.className="pairing-qr-wrap";if(data.qr_data_uri){{const qr=document.createElement("img");qr.className="pairing-qr";qr.alt="QR code to approve this TerraSatch Edge";qr.src=data.qr_data_uri;qrWrap.appendChild(qr)}}else{{const fallback=document.createElement("p");fallback.textContent="QR unavailable. Use the browser approval option.";qrWrap.appendChild(fallback)}}const copy=document.createElement("div");copy.className="pairing-copy";const kicker=document.createElement("div");kicker.className="pairing-kicker";kicker.textContent="Scan with your phone";const title=document.createElement("strong");title.textContent="Approve this Edge in TerraSatch";const detail=document.createElement("p");detail.textContent="The QR only contains the short-lived TerraSatch approval URL. It does not contain your API key, Edge credential, or a long-lived secret.";const codeRow=document.createElement("div");codeRow.className="pairing-code-row";const code=document.createElement("span");code.className="pairing-code";code.textContent=data.user_code;const copyButton=document.createElement("button");copyButton.type="button";copyButton.className="ghost-action";copyButton.textContent="Copy code";copyButton.onclick=async()=>{{try{{await navigator.clipboard.writeText(data.user_code);copyButton.textContent="Copied";window.setTimeout(()=>copyButton.textContent="Copy code",1600)}}catch(_error){{notify("Could not copy the pairing code.",true)}}}};codeRow.append(code,copyButton);const actions=document.createElement("div");actions.className="pairing-actions";try{{const target=new URL(data.verification_url);if(target.protocol==="https:"||target.protocol==="http:"){{const link=document.createElement("a");link.className="inline-action";link.target="_blank";link.rel="noreferrer";link.href=target.href;link.textContent="Open TerraSatch on this PC";actions.appendChild(link)}}}}catch(_error){{}}const wait=document.createElement("div");wait.className="pairing-wait";const pulse=document.createElement("span");pulse.className="pairing-pulse";const waitText=document.createElement("span");waitText.textContent="Waiting for approval…";wait.append(pulse,waitText);copy.append(kicker,title,detail,codeRow,actions,wait);grid.append(qrWrap,copy);panel.appendChild(grid);if(pairingTimer)window.clearInterval(pairingTimer);const interval=Math.max(2000,(data.interval_seconds||5)*1000);pairingTimer=window.setInterval(()=>claimPairing(data.device_code),interval);await claimPairing(data.device_code)}}catch(error){{notify("Pairing could not start: "+error.message,true)}}finally{{busy(button,false,"")}}}}
async function claimPairing(deviceCode){{try{{const data=await request("/api/pairing/claim",{{method:"POST",headers,body:JSON.stringify({{device_code:deviceCode}})}});if(data.paired){{if(pairingTimer)window.clearInterval(pairingTimer);notify(data.heartbeat?"Pairing complete. Field gateway is online.":"Pairing complete. Finish gateway verification next.",!data.heartbeat);window.setTimeout(()=>location.reload(),700)}}else if(["expired","claimed"].includes(data.status)){{if(pairingTimer)window.clearInterval(pairingTimer);notify("Pairing ended with status: "+data.status,true)}}}}catch(error){{if(pairingTimer)window.clearInterval(pairingTimer);notify("Pairing check failed: "+error.message,true)}}}}
const configForm=document.getElementById("configForm");if(configForm)configForm.addEventListener("submit",async event=>{{event.preventDefault();const form=new FormData(event.target);const channel=form.get("radio_channel");const payload={{node_name:form.get("node_name"),scan_interval_seconds:Number(form.get("scan_interval_seconds")),radio_profile:form.get("radio_profile"),radio_channel:channel?Number(channel):null,radio_squelch:Number(form.get("radio_squelch")),radio_auto_calibrate:form.get("radio_auto_calibrate")==="on",source:form.get("source"),speech_model:form.get("speech_model"),speech_device:form.get("speech_device"),speech_compute_type:form.get("speech_compute_type"),speech_language:form.get("speech_language")||null}};const button=event.submitter;busy(button,true,"Saving…");try{{await request("/api/config",{{method:"PUT",headers,body:JSON.stringify(payload)}});notify("Gateway settings saved. Re-run the radio/device test after changing receive settings.");closeDialog("settingsDialog")}}catch(error){{notify("Settings were not saved: "+error.message,true)}}finally{{busy(button,false,"")}}}});
async function logoutEdge(){{if(!confirm("Remove the local Edge credential? This gateway will need to be paired again."))return;try{{await request("/api/logout",{{method:"POST",headers}});notify("Credential removed. Returning to gateway setup.");window.setTimeout(()=>location.reload(),500)}}catch(error){{notify("Credential could not be removed: "+error.message,true)}}}}
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


def _connection_card(
    kind: str,
    title: str,
    connection_type: str,
    description: str,
    status: str,
    state: str,
    route: str,
    action: str,
) -> str:
    safe_kind = html.escape(kind, quote=True)
    return (
        '<article class="connection-card">'
        '<div class="connection-top"><div>'
        f"<h3>{html.escape(title)}</h3>"
        f'<span class="connection-type">{html.escape(connection_type)}</span>'
        "</div>"
        f'<span class="status status-{html.escape(state)}">{html.escape(status)}</span>'
        "</div>"
        f"<p>{html.escape(description)}</p>"
        f'<div class="connection-route">{html.escape(route)}</div>'
        '<div class="connection-footer">'
        f'<button class="card-action" type="button" onclick="openConnection(\'{safe_kind}\')">{html.escape(action)}</button>'
        "</div></article>"
    )


def _group_label(kind: str, group: dict[str, Any]) -> str:
    if group["name"]:
        return str(group["name"])
    labels = {
        "audio": "Audio capture",
        "gps": "GPS receiver",
        "sdr": "Radio interface",
        "radio": "Radio interface",
        "serial": "Serial interface",
        "meshtastic": "Meshtastic node",
        "lora": "LoRa interface",
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
