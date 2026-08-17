# TerraSatch Edge

**Cross-platform field-device runtime for TerraSatch.**

TerraSatch Edge runs on the field computer and connects physical hardware to `https://api.terrasatch.com`.

> Current development milestone: **v0.2.0 pilot runtime**

## Pilot architecture

```text
Nooelec / RTL-SDR   USB audio   GPS / serial   Network
          \            |            |            /
                      Edge
                       |
               pairing + heartbeat
                       |
              api.terrasatch.com
                       |
                  TerraListen / Satchy
```

## v0.2 capabilities

- Windows, macOS and Linux shared runtime
- browser/device-code pairing against the TerraSatch Edge control plane
- organization/site assignment in TerraSatch Admin
- device-scoped credential provisioning
- hardware discovery and classification
- Nooelec / RTL-SDR recognition
- optional bundled RTL-SDR runtime discovery
- finite receive-only IQ readiness probe when `rtl_sdr` is available
- GPS/GNSS, serial, USB audio and network inventory
- periodic Edge heartbeat and hardware inventory sync
- remote Edge configuration retrieval
- local diagnostics and status UI
- production-style test transmission ingestion
- native packaging definitions for Windows, macOS and Debian/Ubuntu

## Pair a development checkout

```bash
terrasatch-edge setup
```

The preferred setup flow now:

1. checks `api.terrasatch.com`
2. scans local hardware
3. creates an Edge pairing request
4. prints and optionally opens the TerraSatch Admin verification URL
5. waits while the operator chooses organization + site
6. claims the issued device credential
7. sends the first hardware heartbeat

Manual service keys remain available only as an advanced fallback:

```bash
terrasatch-edge setup --api-key "$TERRASATCH_EDGE_API_KEY" --site-id "<uuid>"
```

## Useful commands

```text
terrasatch-edge setup
terrasatch-edge scan
terrasatch-edge devices
terrasatch-edge status
terrasatch-edge doctor
terrasatch-edge run --once
terrasatch-edge run
terrasatch-edge ui
terrasatch-edge ingest-text "Wind loading near the ridgeline" --callsign "Field Test 1"
terrasatch-edge paths
terrasatch-edge logout
```

The local UI binds to `127.0.0.1:8742` by default.

## Native pilot builds

See [`docs/PILOT_BUILD.md`](docs/PILOT_BUILD.md).

Windows:

```powershell
.\scripts\build-windows.ps1
```

produces:

```text
release\TerraSatch-Edge-Setup-x64.exe
```

The Windows installer now keeps first-run setup and Start Menu diagnostics visible until the operator closes them. Setup transcripts are written to:

```text
C:\ProgramData\TerraSatch\Edge\state\logs
```

A reviewed RTL-SDR Windows runtime can be embedded by setting `TERRASATCH_RTLSDR_BUNDLE` before the build. Edge then finds the runtime inside its own `tools\rtl-sdr` directory without requiring the target user to modify PATH.

macOS:

```bash
./scripts/build-macos.sh
```

Linux:

```bash
./scripts/build-linux-deb.sh
```

PyInstaller builds must be run on the operating system being packaged. The target user's machine does not need a Python installation.

## Nooelec status

v0.2 can discover and report an RTL-SDR / Nooelec receiver and its capabilities. When a trusted `rtl_sdr` runtime is bundled or installed, `terrasatch-edge doctor` also performs a small finite IQ read to prove that Edge can actually open and receive from the hardware.

Continuous RF capture, NFM/FM demodulation, squelch/VAD, radio audio segmentation and TerraListen/Satchy transcription remain the next adapter phase.

## Security

- device pairing avoids distributing reusable organization service keys
- paired credentials are tenant scoped by the API
- Windows pilot files are ACL-hardened under ProgramData
- POSIX config/credential files use `0600`
- the local UI stays loopback-only by default
- production public installers should be code-signed/notarized before broad distribution

## No hosted CI required

This repository intentionally does not require GitHub Actions. Pilot build/test scripts run locally so they do not add hosted Actions usage.
