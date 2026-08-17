# TerraSatch Edge

**Cross-platform field-device runtime for TerraSatch.**

TerraSatch Edge runs on the field computer and connects physical hardware to `https://api.terrasatch.com`.

> Current development milestone: **v0.2.1 native pilot runtime**

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

## v0.2.1 capabilities

- Windows, macOS and Linux shared runtime
- browser/device-code pairing against the TerraSatch Edge control plane
- organization/site assignment in TerraSatch Admin
- device-scoped credential provisioning
- hardware discovery and classification
- Nooelec / RTL-SDR recognition
- RTL receive readiness reporting aligned with the current API (`rtl_test` + `rtl_fm`)
- finite receive-only IQ diagnostic probe when `rtl_sdr` is available
- HackRF discovery without falsely advertising RX/TX before a provider adapter exists
- GPS/GNSS, serial, USB audio and network inventory
- periodic Edge heartbeat and hardware inventory sync
- remote Edge configuration retrieval
- running services can pick up pairing/config changes without reinstalling
- local diagnostics and status UI
- production-style test transmission ingestion
- native packaging for Windows, macOS and Debian/Ubuntu

## Pair a development checkout

```bash
terrasatch-edge setup
```

The preferred setup flow:

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

See [`docs/NATIVE_BUILDS.md`](docs/NATIVE_BUILDS.md) for the current macOS/Linux build, service, signing and clean-machine validation flow. Windows-specific details remain in [`docs/PILOT_BUILD.md`](docs/PILOT_BUILD.md).

Windows:

```powershell
.\scripts\build-windows.ps1
```

produces:

```text
release\TerraSatch-Edge-Setup-x64.exe
```

The validated v0.2.1 Windows pilot is published from `www.terrasatch.com/downloads`. A reviewed RTL-SDR Windows runtime is embedded in the tested artifact so Edge can locate `rtl_sdr`, `rtl_test` and `rtl_fm` without target-machine PATH changes.

macOS:

```bash
./scripts/build-macos.sh
```

The native package installs `com.terrasatch.edge` as a LaunchDaemon. The public download remains disabled until Apple Silicon/Intel artifacts are built and validated. Broad distribution requires Developer ID signing and notarization.

Linux:

```bash
./scripts/build-linux-deb.sh
```

The Debian/Ubuntu package installs a persistent systemd service and uses the same system registration for CLI + service. The public download remains disabled until amd64/arm64 artifacts are built and validated.

PyInstaller builds must be run on the operating system and architecture being packaged. The target user's machine does not need a Python installation.

## Receiver status

Hardware inventory and provider readiness are separate on purpose. A Nooelec/RTL-SDR can be identified before its receive tooling is ready, but the control plane receives `radio:receive` / `audio:capture` only when the required RTL receive utilities are present. HackRF is discovery-only until a TerraListen provider adapter actually implements its receive/transmit path.

The standalone Edge runtime still needs the next operational adapter phase to continuously tune configured channels, segment live radio audio, and feed those captures into TerraListen/Satchy. The API-side radio policy and bounded RTL capture work can be used as the contract for that phase.

## Security

- device pairing avoids distributing reusable organization service keys
- paired credentials are tenant scoped by the API
- Windows pilot files are ACL-hardened under ProgramData
- POSIX system packages keep config/state root-owned and require `sudo` for setup/status/doctor
- the local UI stays loopback-only by default
- production public installers should be code-signed/notarized before broad distribution

## No hosted CI required

This repository intentionally does not require GitHub Actions. Pilot build/test scripts run locally so they do not add hosted Actions usage.
