# TerraSatch Edge

**Cross-platform field-device runtime for TerraSatch.**

TerraSatch Edge runs on the field computer and connects physical hardware to `https://api.terrasatch.com`.

> Current source milestone: **v0.2.5 release-trust + Satchy command/control runtime + receive-first BCA/FRS monitoring**
> Field-asset mission support is provider-neutral infrastructure only; no drone, robot, or relay provider is installed by default.
> The existing v0.2.4 Windows installer remains an unsigned beta compatibility build. For v0.2.5, the primary no-cost public Windows route is Microsoft Store MSIX; direct `.exe` distribution remains a compatibility/beta lane unless it is separately trusted-signed.  
> Public source: [`github.com/k3y10/terrasatch-edge`](https://github.com/k3y10/terrasatch-edge)

## Current TerraSatch connection surface

TerraSatch Edge is one field-input/runtime layer inside the broader TerraSatch platform. The current platform now includes:

- **TerraSatch Edge** — pairing, heartbeat, hardware inventory, receive-first radio ingestion, offline outbox, and controlled Satchy commands.
- **TerraSatch Mobile** — authenticated notes, voice transcripts, photo-note references, GPS, and client idempotency into the canonical field-ingest pipeline.
- **Garmin inReach Portal Connect** — partner-gated receive path for professional inReach messaging into that same canonical pipeline.
- **20 supported API integration providers** for documents, communications, calendars, work management, mapping, storage, weather, and data.
- **2 TerraSatch-managed providers** — TerraSatch Edge and Mapbox.
- **Coming soon** — onX Backcountry, Gaia GPS, and AllTrails where provider access permits.

Third-party runtime readiness still depends on each organization's credentials, administrator configuration, and provider access. Garmin remains partner-gated until a live approved tenant is available for acceptance testing.

## Verify public downloads

For every public Edge release, verify the exact downloaded artifact rather than trusting the filename alone:

- compare its **SHA-256** with the release `SHA256SUMS.txt`;
- verify its GitHub build provenance with `gh attestation verify <downloaded-file> --repo k3y10/terrasatch-edge`;
- on Windows, verify **Authenticode** with `Get-AuthenticodeSignature` and confirm a valid expected TerraSatch signer before treating the installer as signed.

SHA-256 confirms integrity and GitHub attestation confirms build provenance. Neither substitutes for Windows publisher signing or SmartScreen reputation.

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
- negotiated `radio_reply` handling with existing RF policy/capability safeguards
- provider-neutral, policy-gated `asset_mission` command support with durable at-most-once effect journaling
- running services can pick up pairing/config changes without reinstalling
- local diagnostics and status UI
- production-style test transmission ingestion through the CLI
- native packaging for Windows, macOS and Debian/Ubuntu

The BCA/FRS path remains **receive-only** through the Nooelec/RTL-SDR receiver. It does not transmit through the SDR. BCA privacy/sub-channel codes do not change the carrier frequency, and the current pilot listens channel-wide rather than filtering CTCSS/DCS codes. RF transmission remains separately capability- and policy-gated. Field-asset missions also remain inert unless an explicit installed provider adapter is wired into the Edge runtime.

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

Windows — primary free Store/MSIX route:

```powershell
# Local development package using an installed TerraSatch test certificate.
$env:TERRASATCH_MSIX_CERT_THUMBPRINT = "<development certificate thumbprint>"
.\scripts\build-windows-msix.ps1

# Partner Center submission package after reserving the Store product identity.
$env:TERRASATCH_MSIX_IDENTITY_NAME = "<Partner Center Package/Identity/Name>"
$env:TERRASATCH_MSIX_PUBLISHER = "<Partner Center Package/Identity/Publisher>"
$env:TERRASATCH_MSIX_PUBLISHER_DISPLAY_NAME = "TerraSatch Inc."
.\scripts\build-windows-msix.ps1 -StoreUpload
```

The MSIX contains the TerraSatch operator launcher plus two per-user startup processes: the Edge agent is enabled by default after the first app launch, while the receive-only radio process is packaged but disabled until the operator has paired Edge and configured a receive target. Local development MSIX files are signed with a local test certificate so they can be installed on a controlled machine. The Partner Center submission package is intentionally unsigned locally; Microsoft Store applies the production package signature after certification.

The free Store path preserves TerraSatch's proprietary license and avoids placing a private production signing key in GitHub. The Store package deliberately avoids `packagedServices` and `localSystemServices`; it uses the standard packaged-desktop `runFullTrust` declaration and Windows startup-task extension instead.

The existing Inno Setup compatibility build remains available for controlled beta/direct-download testing:

```powershell
.\scripts\build-windows.ps1 -AllowUnsigned
```

That direct `.exe` must remain clearly labeled unsigned unless TerraSatch later chooses a separate trusted-signing provider.

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

For public Windows distribution, TerraSatch prefers the Microsoft Store MSIX route and publishes checksums/provenance for any direct compatibility artifacts. Versioned direct-download objects remain immutable; new bytes require a new version/path.

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
- public Microsoft Store MSIX packages must pass Store certification and Microsoft signing before being presented as the trusted Windows install path
- direct Windows `.exe` artifacts remain compatibility/beta downloads unless separately trusted-signed

## QA

The Satchy feature branch uses a focused GitHub Actions gate for Python 3.12 compile, Ruff, and pytest validation. Native Windows/Linux release builds remain separately gated by the platform-specific build and clean-machine validation procedures.

## Channel-aware development QA

See [branch integration, validation results, and remaining bidirectional gates](docs/EDGE_UPDATE_QA.md).


## Generalized Windows/Linux receive monitoring

Nooelec NESDR SMArt v5 is receive-only. BCA channel 19 and `--frequency 462.650M`
resolve into the same continuous receiver/STT/outbox pipeline. Repeater outputs can
be monitored without transmitting; discovery never grants transmit authorization.

```console
terrasatch-edge radio devices
terrasatch-edge radio targets
terrasatch-edge radio probe --frequency 462.650M --seconds 10
terrasatch-edge radio start --frequency 462.650M
terrasatch-edge radio start --channel 19
```

[Target configuration and scanning](docs/RADIO_TARGETS.md),
[optional repeater discovery](docs/REPEATER_DISCOVERY.md), and
[RX validation status](docs/RX_HARDENING_QA.md) describe the current boundaries.
The independent radio service is installed but must be enabled after configuring a target.
Windows/Linux are the priority; macOS hardening is deferred.
