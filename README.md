# TerraSatch Edge

**Cross-platform field-device runtime for TerraSatch.**

TerraSatch Edge runs on the field computer and connects physical hardware to `https://api.terrasatch.com`.

> Current source milestone: **v0.2.4 simulation-only Satchy command client + unchanged v0.2.3 BCA/FRS receive pilot**
> Current public Windows installer: **v0.2.2** while the v0.2.3 Windows artifact completes the signed native release gate.  
> Public source: [`github.com/k3y10/terrasatch-edge`](https://github.com/k3y10/terrasatch-edge) · exact v0.2.3 source snapshot: [`87961ce`](https://github.com/k3y10/terrasatch-edge/commit/87961cea7d2cdd8ad57b8d48b0732f0c694b0c97)

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

## v0.2.4 development capabilities

- Windows, macOS and Linux shared runtime
- guided local Operator Console plus terminal/CLI mode
- browser/device-code pairing against the TerraSatch Edge control plane
- organization/site assignment in TerraSatch Admin
- device-scoped credential provisioning
- safe local Edge configuration without exposing tenant reassignment or API-redirection controls
- hardware discovery and classification
- Nooelec / RTL-SDR recognition
- RTL receive readiness reporting aligned with the current API (`rtl_test` + `rtl_fm`)
- finite receive-only IQ diagnostic probe when `rtl_sdr` is available
- receive-only BCA / North American FRS channel profile for channels 1-22
- `radio-channels` channel/frequency reference command
- bounded `listen-radio` capture using `rtl_fm`, local speech transcription, and the canonical TerraSatch transmission-ingest path
- persistent `radio start/status/stop` monitoring with local filtering, bounded QA retention, and a durable offline outbox
- radio source provenance such as `terrasatch-edge-radio-bca-ch05`
- successful temporary radio captures removed by default, with explicit `--keep-audio` support for QA
- HackRF discovery without falsely advertising RX/TX before a provider adapter exists
- GPS/GNSS, serial, USB audio and network inventory
- periodic Edge heartbeat and hardware inventory sync
- remote Edge configuration retrieval
- device/site-bound Edge command polling
- idempotent command acknowledgement and retry after interrupted result delivery
- simulation-only `radio_reply` completion with explicit refusal of physical RF/PTT work
- running services can pick up pairing/config changes without reinstalling
- local diagnostics and status UI
- production-style test transmission ingestion through the CLI
- native packaging for Windows, macOS and Debian/Ubuntu

The v0.2.3 BCA/FRS path remains **receive-only** in v0.2.4. It does not transmit through the SDR. BCA privacy/sub-channel codes do not change the carrier frequency, and the current pilot listens channel-wide rather than filtering CTCSS/DCS codes. The new command client only acknowledges API work and reports `simulated`; it never opens a TX/PTT provider.

See [`docs/SATCHY_COMMAND_CLIENT.md`](docs/SATCHY_COMMAND_CLIENT.md) for the paired API/Edge validation flow and the simulation-only safety boundary.

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

Advanced development/test environments can continue to select another API with the existing terminal `--api-url` flow. The field-operator browser intentionally does not expose API-target editing, which prevents an existing device credential from being accidentally redirected to another host.

## Useful commands

```text
terrasatch-edge console
terrasatch-edge setup
terrasatch-edge scan
terrasatch-edge devices
terrasatch-edge status
terrasatch-edge doctor
terrasatch-edge radio-channels
terrasatch-edge listen-radio --channel 5 --once --callsign "BCA TEST"
terrasatch-edge radio start --channel 5
terrasatch-edge radio status
terrasatch-edge run --once
terrasatch-edge run
terrasatch-edge commands
terrasatch-edge ui
terrasatch-edge ingest-text "Wind loading near the ridgeline" --callsign "Field Test 1"
terrasatch-edge paths
terrasatch-edge logout
```

See [Continuous radio monitoring](docs/RADIO_MONITORING.md) for filtering, QA retention,
offline delivery, remote configuration, and Raspberry Pi/systemd operation.

Continuous and legacy radio commands auto-calibrate RTL gain, squelch, and local PCM activity
gates at startup. Keep the selected channel clear during the brief calibration. The resulting
noise floor and thresholds are visible in `terrasatch-edge radio status`; use
`--no-auto-calibrate` only for deliberate manual tuning.

`console` is the recommended guided experience. The older `ui` command remains available for compatibility; terminal commands remain the automation and advanced-administration interface.

For the receive-only BCA/FRS pilot, a field validation command is:

```bash
terrasatch-edge listen-radio \
  --channel 5 \
  --once \
  --callsign "BCA TEST" \
  --hotwords "TerraSatch, Cardiff Bowl, BCA"
```

Use `--keep-audio` only for the legacy single-call QA workflow. Continuous mode deletes all
temporary audio unless bounded QA retention is explicitly enabled.

## Native pilot builds

See [`docs/NATIVE_BUILDS.md`](docs/NATIVE_BUILDS.md) for the current macOS/Linux build, service, signing and clean-machine validation flow. Windows-specific details remain in [`docs/PILOT_BUILD.md`](docs/PILOT_BUILD.md).

Windows:

```powershell
$env:TERRASATCH_CODESIGN_CERT_THUMBPRINT = "<CA-issued code-signing certificate thumbprint>"
.\scripts\build-windows.ps1
```

The production build signs and verifies the native Edge executable, service wrapper, installer, and uninstaller with SHA-256 plus an RFC 3161 timestamp. The certificate must be installed with its private key in the current-user or local-machine Personal certificate store. Use `.\scripts\build-windows.ps1 -AllowUnsigned` only for local QA; that artifact must not be uploaded or published.

The build produces:

```text
release\TerraSatch-Edge-Setup-x64.exe
```

The installer is UI-first: the desktop/Start Menu TerraSatch Edge entry opens the Operator Console, while status, diagnostics, hardware scan, and terminal setup remain separate shortcuts. The v0.2.3 source includes the receive-only BCA/FRS radio path, but the public Windows download must stay on the previously validated artifact until the exact v0.2.3 signed installer passes the release checklist.

macOS:

```bash
./scripts/build-macos.sh
```

The native package installs `com.terrasatch.edge` as a LaunchDaemon. New native packages derive their version from the source package. Broad distribution requires Developer ID signing and notarization.

Linux:

```bash
./scripts/build-linux-deb.sh
```

The Debian/Ubuntu package installs a persistent systemd service and uses the same system registration for CLI + service. New native packages derive their version from the source package.

PyInstaller builds must be run on the operating system and architecture being packaged. The target user's machine does not need a Python installation.

## Public source and release verification

TerraSatch Edge source is publicly reviewable in this repository. Reviewers can inspect the runtime, native packaging scripts, Windows installer definition, radio receive adapter, tests, and release controls before installing a binary.

For a public Windows release, TerraSatch uses immutable versioned Blob objects and publishes the SHA-256 of the exact validated installer. A new version is published at a new path rather than replacing older bytes in place.

See [`docs/PUBLIC_RELEASE_CHECKLIST.md`](docs/PUBLIC_RELEASE_CHECKLIST.md) for the public release gate, including API readiness, clean-machine install validation, Authenticode verification, checksum recording, Blob publication, and post-upload verification.

## Configuration ownership

The Operator Console exposes local device/runtime concerns such as node name, heartbeat interval, source label, and speech runtime settings.

API target selection, organization assignment, site assignment, credential scope, remote configuration, and future organization workflow/channel policy stay terminal/Admin/control-plane concerns. This keeps Edge reusable across UAC, CAIC, ski patrol, wildfire, SAR, utilities, and other organizations instead of embedding one partner's assumptions into the field runtime.

## Receiver status

Hardware inventory and provider readiness are separate on purpose. A Nooelec/RTL-SDR can be identified before its receive tooling is ready, but the control plane receives `radio:receive` / `audio:capture` only when the required RTL receive utilities are present. HackRF is discovery-only until a TerraListen provider adapter actually implements its receive/transmit path.

The v0.2.3 receive pilot can tune a selected BCA/FRS channel, capture a bounded carrier-gated call with `rtl_fm`, transcribe it locally, and submit it through the existing TerraSatch transmission ingest path. Continuous unattended channel operation, privacy-code filtering, and additional radio-provider adapters remain later operational phases.

## Security

- source code is publicly reviewable before installation
- exact public release artifacts are identified by published SHA-256 checksums
- versioned release objects are immutable by policy; new bytes require a new version/path
- device pairing avoids distributing reusable organization service keys
- paired credentials are tenant scoped by the API
- organization/site assignment is not locally editable in the Operator Console
- API target is read-only in the field-operator browser
- mutating UI requests require an Edge-specific operator header
- arbitrary shell execution is not exposed in the browser
- the Operator Console binds to loopback by default and rejects remote binds without explicit opt-in
- Windows pilot files are ACL-hardened under ProgramData
- POSIX system packages keep config/state root-owned and require `sudo` for setup/status/doctor
- production public Windows installers must pass trusted Authenticode signing and timestamp verification before publication

## No hosted CI required

This repository intentionally does not require GitHub Actions. Pilot build/test scripts run locally so they do not add hosted Actions usage.

## Channel-aware development QA

See [branch integration, validation results, and remaining bidirectional gates](docs/EDGE_UPDATE_QA.md).
