# TerraSatch Edge

**Local field-device agent and setup wizard for TerraSatch.**

TerraSatch Edge runs on the field computer—not on the TerraSatch Oracle server. It discovers local hardware, validates the machine, connects the device to `https://api.terrasatch.com`, saves local health snapshots, and provides the client-side bridge for future TerraListen radio/audio, GPS, sensors, and other field hardware.

> Current release: **v0.1.0 foundation**

## Architecture

```text
Field hardware
    │
    ├── RTL-SDR / Nooelec
    ├── radio audio interface
    ├── GPS / GNSS / NMEA
    ├── serial devices
    └── network interfaces
    │
    ▼
TerraSatch Edge
    ├── setup wizard
    ├── hardware discovery
    ├── adapter classification
    ├── diagnostics
    ├── local snapshots
    ├── optional localhost UI
    └── TerraSatch API client
    │
    ▼
https://api.terrasatch.com
    ├── auth
    ├── organizations/sites
    ├── transmissions
    ├── TerraListen pipeline
    └── operational events
```

## What works in v0.1.0

- Windows and Linux-friendly Python 3.12+ package
- interactive `terrasatch-edge setup` wizard
- validation against the live TerraSatch API
- service API key authentication using the current API contract
- TerraSatch site discovery and selection
- system inventory: OS, architecture, CPU, RAM, disk
- serial/COM port discovery
- USB discovery through PyUSB when available
- Linux `lsusb` discovery fallback
- Windows PnP discovery through PowerShell
- network interface inventory
- RTL-SDR / Nooelec classification
- HackRF classification
- GPS/GNSS/NMEA classification
- USB audio classification rules
- optional SDR probes through `rtl_test`, `hackrf_info`, and `SoapySDRUtil`
- local diagnostic command
- local hardware snapshot persistence
- long-running Edge loop with API health checks
- live test ingestion through the existing `/api/v1/transmissions` endpoint
- optional local status UI at `http://127.0.0.1:8742`
- Linux and Windows installation scripts
- systemd unit template for Linux field nodes

## Intentionally not implemented yet

These need corresponding API/backend or device-specific work and should be added as separate phases:

- browser/device-code account pairing
- cloud device registry
- remote Edge heartbeats and hardware inventory API
- automatic API key provisioning
- direct RTL-SDR demodulation/audio capture
- BCA radio audio capture/transcription
- channel/frequency configuration UI
- GPS NMEA stream ingestion
- local offline event queue and replay
- signed/self-updating binaries
- Windows service registration
- per-device remote configuration

The first version deliberately uses the **existing TerraSatch service API key** flow so Edge can connect to the production API before the new device-control endpoints are deployed.

## Requirements

- Python **3.12+**
- Internet access to `https://api.terrasatch.com`
- a TerraSatch service API key
- a site assigned to the key's organization for transmission ingestion

For actual ingestion, the service key should include the API's appropriate Edge ingestion scope (currently `edge:ingest`). Read access may also be needed for site selection depending on how the key is provisioned.

## Install from a checkout

### Linux

```bash
./scripts/install.sh
```

Then:

```bash
terrasatch-edge setup
terrasatch-edge doctor
terrasatch-edge status
```

### Windows PowerShell

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\install.ps1
```

The installer prints the full path of the generated executable. After a packaged Windows installer is added, this will become a normal `TerraSatch-Edge-Setup.exe` flow.

## Developer install

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,serial,usb,ui]'
```

Windows:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,serial,usb,ui]"
```

## CLI

```text
terrasatch-edge setup
terrasatch-edge scan
terrasatch-edge devices
terrasatch-edge status
terrasatch-edge doctor
terrasatch-edge ingest-text "Wind loading visible near the ridgeline" --callsign "Patrol 4"
terrasatch-edge run --once
terrasatch-edge run
terrasatch-edge ui
terrasatch-edge paths
terrasatch-edge logout
terrasatch-edge version
```

`tsedge` is also installed as a shorter alias.

## Setup wizard

Run:

```bash
terrasatch-edge setup
```

The wizard:

1. checks `api.terrasatch.com`
2. scans the local machine
3. asks for the TerraSatch service API key using hidden input
4. validates it through `/api/v1/auth/me`
5. lists available TerraSatch sites
6. lets the user choose a site
7. names the local Edge node
8. stores local configuration and credentials
9. directs the user to `terrasatch-edge doctor`

Non-interactive provisioning is also supported:

```bash
terrasatch-edge setup \
  --api-url https://api.terrasatch.com \
  --api-key "$TERRASATCH_EDGE_API_KEY" \
  --site-id "<site-uuid>" \
  --non-interactive
```

For automated deployments, prefer passing the key through the `TERRASATCH_EDGE_API_KEY` environment variable rather than placing it in shell history.

## Hardware scan

```bash
terrasatch-edge scan
```

Machine-readable output:

```bash
terrasatch-edge scan --json
```

The scanner is designed to be **best effort**. A driver can be installed correctly even when an optional probe tool is not. `terrasatch-edge doctor` explains what Edge can currently see and which additional driver/tool would improve detection.

## Diagnostics

```bash
terrasatch-edge doctor
```

Checks currently include:

- config
- credentials
- API reachability
- authentication
- SDR recognition
- GPS recognition
- radio/audio-adjacent hardware
- optional SDR command-line tools

## Test the existing TerraSatch API pipeline

Once setup has selected a site:

```bash
terrasatch-edge ingest-text \
  "Wind loading is visible near the ridgeline on the east aspect around 9800 feet." \
  --callsign "Patrol 4"
```

This uses the current production-style TerraSatch transmission ingestion path. It is useful for validating an Edge machine/account before direct radio audio support is connected.

## Local interface

Install the UI extra and run:

```bash
terrasatch-edge ui
```

Open:

```text
http://127.0.0.1:8742
```

The first UI is intentionally local-only. It shows:

- Edge node
- API status
- authentication status
- selected site
- detected hardware
- hardware capabilities
- API health details

Do **not** bind the current local UI to a public interface without adding authentication and TLS controls.

## Background agent

One cycle:

```bash
terrasatch-edge run --once
```

Persistent:

```bash
terrasatch-edge run
```

The current loop scans local hardware, persists a snapshot, and checks API health. It does not pretend a cloud heartbeat endpoint exists yet. Once the API adds Edge registry/heartbeat endpoints, the same loop becomes the remote device-health channel.

## Configuration locations

Run:

```bash
terrasatch-edge paths
```

Linux defaults:

```text
~/.config/terrasatch-edge/config.json
~/.config/terrasatch-edge/credentials.json
~/.local/state/terrasatch-edge/hardware-snapshot.json
```

Windows defaults use `%APPDATA%\TerraSatchEdge` and `%LOCALAPPDATA%\TerraSatchEdge`.

On POSIX systems, TerraSatch Edge applies mode `0600` to config and credential files. A future Windows build should move credentials into Windows Credential Manager/DPAPI before broad customer distribution.

## API compatibility

TerraSatch Edge v0.1.0 intentionally uses API functionality that already exists:

```text
GET  /health
GET  /api/v1/auth/me
GET  /api/v1/sites
POST /api/v1/transmissions
```

Planned API additions for the next phase:

```text
POST /api/v1/edge/device-codes
POST /api/v1/edge/device-tokens
POST /api/v1/edge/nodes/{node_id}/heartbeat
PUT  /api/v1/edge/nodes/{node_id}/inventory
GET  /api/v1/edge/nodes/{node_id}/configuration
```

Those names are a proposed contract, not a statement that the current production API already exposes them.

## Security notes

- Never commit TerraSatch API keys.
- Use tenant-scoped service credentials.
- Give Edge only the scopes it needs.
- Keep the localhost UI bound to `127.0.0.1` until it has its own auth layer.
- Treat radio recordings, transcripts, operational events, and precise field locations as operational data subject to each partner's retention/access policy.
- Use signed installers and update manifests before distributing Edge broadly outside controlled pilots.

## No GitHub Actions required

This repository does **not** include GitHub Actions workflows. Local tests/linting are sufficient for the current pilot phase and avoid adding hosted CI usage.

## Development checks

```bash
python -m pip install -e '.[dev]'
pytest
ruff check src tests
```

## Near-term roadmap

### Phase 1 — Foundation (this repository)

- setup wizard
- API auth
- hardware scan
- diagnostics
- local UI
- local agent loop

### Phase 2 — TerraSatch API Edge control plane

- node registration
- browser pairing codes
- scoped Edge token issuance
- heartbeats
- inventory
- remote configuration

### Phase 3 — TerraListen radio adapters

- RTL-SDR/Nooelec capture
- frequency/channel profiles
- radio audio input
- VAD
- clip buffering
- transmission upload
- transcript/event mapping

### Phase 4 — Field adapters

- GPS/NMEA
- weather stations
- drone telemetry
- LoRa/Meshtastic
- serial sensors
- additional SDR families

### Phase 5 — Distribution

- Windows installer
- signed binaries
- Linux packages
- automatic updater
- support bundle export

---

**TerraSatch Edge** is the field-side bridge between physical equipment and the TerraSatch API.
