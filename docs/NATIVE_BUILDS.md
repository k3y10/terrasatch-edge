# TerraSatch Edge native builds

TerraSatch Edge is packaged on the operating system and CPU architecture that will run it. Current source package version: **0.2.3**.

Native artifacts use the release channels defined in [`RELEASE_CHANNELS.md`](RELEASE_CHANNELS.md):

- **Partner Beta** — controlled testing/evaluation; exact bytes are SHA-256 verified and may be unsigned or not fully notarized.
- **Official Release** — broad distribution after native validation and the applicable platform publisher-signing/notarization gate.

A checksum is an integrity check, not a publisher signature.

## Shared API contract

All native packages use the same Edge control-plane contract:

- `POST /api/v1/edge/pairings`
- `POST /api/v1/edge/pairings/token`
- `GET /api/v1/edge/me`
- `POST /api/v1/edge/heartbeat`
- `GET /api/v1/edge/config`

The service checks registration/config on each cycle, so a service that started before pairing can pick up the newly issued device credential without reinstalling the package.

Hardware discovery is intentionally separate from provider readiness:

- RTL-SDR / Nooelec reports `radio:receive` + `audio:capture` only when the RTL receive runtime is complete (`rtl_test` and `rtl_fm`).
- HackRF discovery reports hardware presence only until a TerraListen provider adapter actually implements supported RX/TX operations.
- TX remains off by default and provider/policy gated by the API.

## Windows x64

### Partner Beta

```powershell
.\scripts\build-windows-partner-beta.ps1
```

Expected pattern:

```text
release\TerraSatch-Edge-0.2.3-Windows-x64-partner-beta-unsigned.exe
release\TerraSatch-Edge-0.2.3-Windows-x64-partner-beta-unsigned.exe.sha256
release\TerraSatch-Edge-0.2.3-Windows-x64-partner-beta-unsigned.exe.release.json
```

The beta wrapper intentionally uses the existing unsigned QA builder, verifies Authenticode reports `NotSigned`, and promotes the artifact only into the clearly labeled controlled Partner Beta channel. Windows may display Unknown publisher or SmartScreen warnings.

### Official Release

```powershell
$env:TERRASATCH_CODESIGN_CERT_THUMBPRINT = "<CA-issued code-signing certificate thumbprint>"
.\scripts\build-windows.ps1
```

Official Windows distribution requires trusted Authenticode signing and an RFC 3161 timestamp for the native executable, service wrapper, installer, and uninstaller, plus clean-machine validation.

## macOS

Supported pilot architectures:

- Apple Silicon (`arm64`)
- Intel (`x64`, built on `x86_64`)

### Partner Beta

```bash
./scripts/build-macos-partner-beta.sh
```

Expected unsigned pattern:

```text
release/TerraSatch-Edge-0.2.3-macOS-arm64-partner-beta-unsigned.pkg
release/TerraSatch-Edge-0.2.3-macOS-arm64-partner-beta-unsigned.pkg.sha256
release/TerraSatch-Edge-0.2.3-macOS-arm64-partner-beta-unsigned.pkg.release.json
```

If a signing identity is present, the wrapper records `signed` in the filename/metadata but the package remains **Partner Beta** unless it separately passes the Official Release gate.

### Official Release

Broad macOS distribution requires Developer ID signing and Apple notarization/stapling. The native builder supports:

```bash
export TERRASATCH_MACOS_APPLICATION_IDENTITY="Developer ID Application: ..."
export TERRASATCH_MACOS_INSTALLER_IDENTITY="Developer ID Installer: ..."
export TERRASATCH_MACOS_NOTARY_PROFILE="terrasatch-notary"
./scripts/build-macos.sh
```

## Linux — Debian / Ubuntu

Supported pilot architectures:

- `amd64`
- `arm64`

### Partner Beta

```bash
./scripts/build-linux-partner-beta.sh
```

Expected pattern:

```text
release/terrasatch-edge_0.2.3_partner-beta_amd64.deb
release/terrasatch-edge_0.2.3_partner-beta_amd64.deb.sha256
release/terrasatch-edge_0.2.3_partner-beta_amd64.deb.release.json
```

The package installs a persistent systemd service and uses shared registration under:

```text
/etc/terrasatch-edge
/var/lib/terrasatch-edge
```

For Nooelec/RTL-SDR testing:

```bash
sudo apt update
sudo apt install rtl-sdr
```

The current Linux pilot pipeline publishes SHA-256 integrity metadata but does not claim that checksum as a package publisher signature.

## Validation after installation

Every distributed artifact should be installed and tested as the produced package, not from a source checkout.

```text
terrasatch-edge --version
terrasatch-edge status
terrasatch-edge doctor
```

Validate:

1. package-reported version and architecture;
2. API target and authentication;
3. organization/site assignment;
4. heartbeat visibility;
5. service restart/reboot persistence;
6. hardware discovery;
7. actual RTL receive when that capability is advertised;
8. artifact SHA-256 against the distributed `.sha256` file.

## Partner Beta distribution gate

Before sending a Partner Beta artifact to a tester or invited organization:

1. Build from the intended source revision.
2. Run the native build test suite.
3. Install the exact artifact on a clean/native target.
4. Pair and verify API/auth/heartbeat.
5. Reboot and verify the native service.
6. Test supported receive hardware where applicable.
7. Confirm the artifact filename contains `partner-beta`.
8. Confirm `.sha256` and `.release.json` are present and match the artifact.
9. Tell the recipient that it is evaluation software and may show OS publisher/security warnings.
10. Do not describe the build as an Official Release or as evidence of a formal partnership.

## Official release gate

For broad public/native distribution, follow [`PUBLIC_RELEASE_CHECKLIST.md`](PUBLIC_RELEASE_CHECKLIST.md). Windows and macOS must complete their trusted platform signing/notarization requirements before the artifact is labeled Official.
