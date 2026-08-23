# TerraSatch Edge

**Cross-platform field-device runtime for TerraSatch.**

TerraSatch Edge runs on the field computer and connects physical hardware to `https://api.terrasatch.com`.

> Current development milestone: **v0.2.2 native compatibility + operator experience pilot**  
> Current public Windows build: **v0.2.1**

## Pilot architecture

```text
Nooelec / RTL-SDR   USB audio   GPS / serial   Network
          \            |            |            /
                      Edge
                       |
        local operator console / CLI
                       |
               pairing + heartbeat
                       |
              api.terrasatch.com
                       |
                  TerraListen / Satchy
```

## v0.2.2 development capabilities

- Windows, macOS and Linux shared runtime
- guided local Operator Console plus terminal/CLI mode
- browser/device-code pairing against the TerraSatch Edge control plane
- organization/site assignment in TerraSatch Admin
- device-scoped credential provisioning
- safe local Edge configuration without exposing tenant reassignment controls
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
- production-style test transmission ingestion through the CLI
- native packaging for Windows, macOS and Debian/Ubuntu

## Recommended operator setup

For a packaged field device or a development checkout with UI dependencies:

```bash
terrasatch-edge console
```

The Operator Console opens locally at `127.0.0.1:8742` and provides:

1. hardware discovery/rescan
2. pairing to the correct TerraSatch organization + site
3. API/authentication verification
4. first/current hardware heartbeat
5. supported local runtime settings
6. diagnostics and assignment visibility
7. terminal reference for advanced work

The console is loopback-only by default. A non-loopback bind requires the explicit `--allow-remote` flag and should only be used on a trusted, controlled network.

See [`docs/OPERATOR_SETUP.md`](docs/OPERATOR_SETUP.md) for the full UI/terminal workflow and configuration ownership rules.

## Terminal setup

The existing CLI pairing path remains fully supported:

```bash
terrasatch-edge setup
```

It:

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
terrasatch-edge console
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

`console` is the recommended guided experience. The older `ui` command remains available for compatibility; terminal commands remain the automation and advanced-administration interface.

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

The v0.2.2 development installer is UI-first: the desktop/Start Menu TerraSatch Edge entry opens the Operator Console, while status, diagnostics, hardware scan, and terminal setup remain separate shortcuts. The validated v0.2.1 Windows pilot remains the current public build until the v0.2.2 artifact is built and clean-machine validated.

macOS:

```bash
./scripts/build-macos.sh
```

The native package installs `com.terrasatch.edge` as a LaunchDaemon. New native packages derive v0.2.2 from the source package. The public download remains disabled until Apple Silicon/Intel artifacts are built and validated. Broad distribution requires Developer ID signing and notarization.

Linux:

```bash
./scripts/build-linux-deb.sh
```

The Debian/Ubuntu package installs a persistent systemd service and uses the same system registration for CLI + service. New native packages derive v0.2.2 from the source package. The public download remains disabled until amd64/arm64 artifacts are built and validated.

PyInstaller builds must be run on the operating system and architecture being packaged. The target user's machine does not need a Python installation.

## Configuration ownership

Local Edge configuration covers device/runtime concerns such as API URL, node name, heartbeat interval, source label, and speech runtime settings.

Organization assignment, site assignment, credential scope, remote configuration, and future organization workflow/channel policy stay API/Admin controlled. This keeps Edge reusable across UAC, CAIC, ski patrol, wildfire, SAR, utilities, and other organizations instead of embedding one partner's assumptions into the field runtime.

## Receiver status

Hardware inventory and provider readiness are separate on purpose. A Nooelec/RTL-SDR can be identified before its receive tooling is ready, but the control plane receives `radio:receive` / `audio:capture` only when the required RTL receive utilities are present. HackRF is discovery-only until a TerraListen provider adapter actually implements its receive/transmit path.

The standalone Edge runtime still needs the next operational adapter phase to continuously tune configured channels, segment live radio audio, and feed those captures into TerraListen/Satchy. The API-side radio policy, remote Edge configuration, and bounded RTL capture work should remain the contract for that phase.

## Security

- device pairing avoids distributing reusable organization service keys
- paired credentials are tenant scoped by the API
- organization/site assignment is not locally editable in the Operator Console
- mutating UI requests require an Edge-specific operator header
- arbitrary shell execution is not exposed in the browser
- the Operator Console binds to loopback by default and rejects remote binds without explicit opt-in
- Windows pilot files are ACL-hardened under ProgramData
- POSIX system packages keep config/state root-owned and require `sudo` for setup/status/doctor
- production public installers should be code-signed/notarized before broad distribution

## No hosted CI required

This repository intentionally does not require GitHub Actions. Pilot build/test scripts run locally so they do not add hosted Actions usage.
