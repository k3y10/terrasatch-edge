# TerraSatch Edge

**Cross-platform field-device runtime for TerraSatch.**

TerraSatch Edge runs on a field computer and connects supported physical hardware to `https://api.terrasatch.com`.

> Current source milestone: **v0.2.3 receive-only BCA/FRS pilot + native operator experience**  
> Newer evaluation artifacts: **Partner Beta — SHA-256 verified; may be unsigned or not fully notarized**  
> Official public/native release: remains separately gated until the exact artifact passes platform signing/notarization and clean-machine validation.

## Release channels

TerraSatch Edge intentionally distinguishes newer working evaluation builds from an official signed release.

| Channel | Intended use | Trust state |
| --- | --- | --- |
| **Partner Beta** | Controlled testing, pilot validation, invited organization/tester evaluation | Versioned + SHA-256 verified; may be unsigned or not fully notarized |
| **Official Release** | Broad/native distribution after the release gate | Platform-appropriate publisher signing/notarization + SHA-256 |

A SHA-256 checksum verifies that the downloaded bytes match the artifact TerraSatch published. **It is not a code signature.** Partner Beta packages must not be described as “hash signed” or as the official signed installer.

Partner Beta naming is intentionally explicit, for example:

```text
TerraSatch-Edge-0.2.3-Windows-x64-partner-beta-unsigned.exe
TerraSatch-Edge-0.2.3-macOS-arm64-partner-beta-unsigned.pkg
terrasatch-edge_0.2.3_partner-beta_amd64.deb
```

Each distributable beta artifact includes:

```text
<artifact>.sha256
<artifact>.release.json
```

The release metadata records the version, source revision, channel, signature state, checksum, and a notice that the artifact is not an Official Release.

See [`docs/RELEASE_CHANNELS.md`](docs/RELEASE_CHANNELS.md) for the channel contract and [`docs/PUBLIC_RELEASE_CHECKLIST.md`](docs/PUBLIC_RELEASE_CHECKLIST.md) for the official release gate.

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

## v0.2.3 capabilities

- Windows, macOS and Linux shared runtime
- guided local Operator Console plus terminal/CLI mode
- browser/device-code pairing against the TerraSatch Edge control plane
- organization/site assignment in TerraSatch Admin
- device-scoped credential provisioning
- hardware discovery and classification
- Nooelec / RTL-SDR recognition
- RTL receive readiness reporting aligned with the current API (`rtl_test` + `rtl_fm`)
- receive-only BCA / North American FRS channel profile for channels 1-22
- bounded `listen-radio` capture using `rtl_fm`, local speech transcription, and the canonical transmission-ingest path
- radio source provenance such as `terrasatch-edge-radio-bca-ch05`
- temporary successful radio captures removed by default, with explicit QA retention
- HackRF discovery without falsely advertising RX/TX before a provider adapter exists
- GPS/GNSS, serial, USB audio and network inventory
- periodic Edge heartbeat and hardware inventory sync
- remote Edge configuration retrieval
- local diagnostics and status UI
- native packaging for Windows, macOS and Debian/Ubuntu

The current BCA/FRS path is **receive-only**. It does not transmit through the Nooelec/RTL-SDR. BCA privacy/sub-channel codes do not change the carrier frequency, and the current pilot listens channel-wide rather than filtering CTCSS/DCS codes.

## Recommended operator setup

For a packaged field device or a development checkout with UI dependencies:

```bash
terrasatch-edge console
```

The Operator Console opens locally at `127.0.0.1:8742` and provides hardware discovery, pairing, API/auth verification, heartbeat visibility, diagnostics, assignment visibility, and terminal reference.

The console is loopback-only by default. A non-loopback bind requires the explicit `--allow-remote` flag and should only be used on a trusted, controlled network.

See [`docs/OPERATOR_SETUP.md`](docs/OPERATOR_SETUP.md) for the full workflow.

## Terminal setup

```bash
terrasatch-edge setup
```

The setup flow checks the API, scans local hardware, creates a short pairing request, opens or prints the Admin verification URL, waits for organization/site approval, claims the device credential, and sends the first heartbeat.

Useful commands:

```text
terrasatch-edge console
terrasatch-edge setup
terrasatch-edge scan
terrasatch-edge devices
terrasatch-edge status
terrasatch-edge doctor
terrasatch-edge radio-channels
terrasatch-edge listen-radio --channel 5 --once --callsign "BCA TEST"
terrasatch-edge run --once
terrasatch-edge run
terrasatch-edge ingest-text "Wind loading near the ridgeline" --callsign "Field Test 1"
terrasatch-edge paths
terrasatch-edge logout
```

## Native Partner Beta builds

Use the channel-specific wrappers when preparing a newer artifact for controlled beta/partner evaluation.

### Windows x64

```powershell
.\scripts\build-windows-partner-beta.ps1
```

The wrapper uses the existing tested Windows builder in unsigned mode, verifies that the resulting installer is actually unsigned, renames it with `partner-beta-unsigned`, and creates SHA-256 + release metadata. Windows may display **Unknown publisher** or SmartScreen warnings. That is expected for this channel.

The raw command below remains a local QA primitive and should not be distributed directly:

```powershell
.\scripts\build-windows.ps1 -AllowUnsigned
```

An Official Windows release continues to require the TerraSatch Authenticode certificate and RFC 3161 timestamp through the normal `build-windows.ps1` release path.

### macOS

```bash
./scripts/build-macos-partner-beta.sh
```

The wrapper preserves the exact native package generated by the existing macOS builder, labels it as Partner Beta, records whether the package is signed, and generates SHA-256 + release metadata. Broad Official distribution still requires Developer ID signing and Apple notarization/stapling.

### Debian / Ubuntu

```bash
./scripts/build-linux-partner-beta.sh
```

The wrapper creates the normal native `.deb`, relabels it as Partner Beta, and generates SHA-256 + release metadata. A checksum verifies integrity; it is not a package publisher signature.

PyInstaller/native builds must be run on the operating system and architecture being packaged. The target user's machine does not need a Python installation.

## Public source and release verification

The Edge source can be reviewed before installation. Release artifacts are versioned and should be immutable once published. New bytes require a new artifact path rather than silently replacing an existing package.

For controlled Partner Beta distribution, publish the exact reviewed artifact together with its `.sha256` and `.release.json` files and label it clearly as beta/evaluation software.

For an Official Release, follow [`docs/PUBLIC_RELEASE_CHECKLIST.md`](docs/PUBLIC_RELEASE_CHECKLIST.md), including API readiness, native clean-machine validation, platform signing/notarization where applicable, checksum recording, immutable publication, and post-upload verification.

## Security

- source can be reviewed before installation
- exact distributed artifacts are identified by SHA-256
- SHA-256 is integrity verification, not publisher authentication
- device pairing avoids distributing reusable organization service keys
- paired credentials are tenant scoped by the API
- organization/site assignment is not locally editable in the Operator Console
- API target is read-only in the field-operator browser
- arbitrary shell execution is not exposed in the browser
- the Operator Console binds to loopback by default and rejects remote binds without explicit opt-in
- Windows pilot files are ACL-hardened under ProgramData
- POSIX system packages keep config/state root-owned and require `sudo` for setup/status/doctor
- Official Windows installers must pass trusted Authenticode signing and timestamp verification before broad publication

## Build automation

This repository does not require GitHub Actions. Native pilot builds can run locally; the existing Codemagic macOS jobs are explicitly labeled as Partner Beta build/verification workflows.
