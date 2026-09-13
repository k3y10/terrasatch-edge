# TerraSatch Edge native builds

TerraSatch Edge is packaged on the operating system and CPU architecture that will run it. The public downloads page must not activate a build until that exact artifact has been installed and tested on native hardware or an appropriate clean VM.

Current development package version: **0.2.4**. RX candidate builds remain in pilot status until a trusted-signed Windows artifact and native field installations pass the release gate.

## Shared API contract

All native packages use the same Edge control-plane contract:

- `POST /api/v1/edge/pairings`
- `POST /api/v1/edge/pairings/token`
- `GET /api/v1/edge/me`
- `POST /api/v1/edge/heartbeat`
- `GET /api/v1/edge/config`

The service checks registration/config on each cycle, so a service that started before pairing can pick up the newly issued device credential without reinstalling the package.

Hardware discovery is intentionally separate from provider readiness:

- RTL-SDR / Nooelec is reported as `radio:receive` + `audio:capture` only when the RTL receive runtime is complete (`rtl_test` and `rtl_fm`).
- HackRF discovery is reported as `hardware:hackrf`; it does **not** report RX/TX until a TerraListen provider adapter actually implements those operations.
- TX remains off by default and provider-gated by the API.

## Linux — Debian / Ubuntu

Build on the same target architecture you intend to publish.

```bash
./scripts/build-linux-deb.sh
```

Supported public pilot architectures:

- `amd64`
- `arm64`

The build runs the Python test suite, creates a PyInstaller runtime, installs a systemd service, and emits an architecture-specific `.deb` plus SHA-256.

Expected artifact names:

```text
release/terrasatch-edge_0.2.2_amd64.deb
release/terrasatch-edge_0.2.2_arm64.deb
```

The package uses shared system paths so the CLI and background service see the same registration:

```text
/etc/terrasatch-edge
/var/lib/terrasatch-edge
```

After installation:

```bash
sudo terrasatch-edge setup
sudo terrasatch-edge status
sudo terrasatch-edge doctor
systemctl status terrasatch-edge
```

The Debian package recommends `rtl-sdr`. Install it when using Nooelec/RTL-SDR hardware:

```bash
sudo apt update
sudo apt install rtl-sdr
```

Do not enable the Linux website button until the exact `.deb` has passed install, pairing, heartbeat, reboot/service-start, hardware discovery, and (when applicable) RTL receive tests on that architecture.

## macOS

Build natively on the target Mac architecture:

```bash
./scripts/build-macos.sh
```

Supported public pilot architectures:

- Apple Silicon (`arm64`)
- Intel (`x64`, built on `x86_64`)

Expected artifact names:

```text
release/TerraSatch-Edge-0.2.2-macOS-arm64.pkg
release/TerraSatch-Edge-0.2.2-macOS-x64.pkg
```

The package installs a `LaunchDaemon` (`com.terrasatch.edge`) and uses shared system state under:

```text
/Library/Application Support/TerraSatch/Edge
```

After installation:

```bash
sudo terrasatch-edge setup
sudo terrasatch-edge status
sudo terrasatch-edge doctor
sudo launchctl print system/com.terrasatch.edge
```

For Nooelec/RTL-SDR testing, install the RTL-SDR utilities in a standard Homebrew location. The package runtime checks both Apple Silicon and Intel Homebrew paths:

```text
/opt/homebrew/bin
/usr/local/bin
```

### Signing and notarization

Unsigned packages are acceptable only for controlled internal pilot testing. Broad public macOS distribution should use a Developer ID-signed executable/package and Apple notarization.

Optional build variables:

```bash
export TERRASATCH_MACOS_APPLICATION_IDENTITY="Developer ID Application: ..."
export TERRASATCH_MACOS_INSTALLER_IDENTITY="Developer ID Installer: ..."
export TERRASATCH_MACOS_NOTARY_PROFILE="terrasatch-notary"
./scripts/build-macos.sh
```

When a notary profile is supplied, the build submits with `notarytool`, waits for acceptance, staples the ticket, and validates the stapled package.

Do not enable either macOS website button until the exact package for that architecture has passed clean install, pairing, heartbeat, reboot/service-start, hardware discovery, Gatekeeper/signing validation for public distribution, and the relevant radio receive tests.

## Release checklist

For every new artifact:

1. Build from the intended Edge release commit.
2. Confirm package-reported version.
3. Record SHA-256.
4. Install on a clean/native target.
5. Pair using the human-readable code + Admin URL.
6. Confirm the assigned Device ID/site and `Auth: OK`.
7. Confirm heartbeat appears online in the current API/Admin health view.
8. Reboot and confirm the native service comes back automatically.
9. Run `doctor` and hardware scan.
10. Test actual RTL receive when shipping RTL-SDR support.
11. Upload the exact tested artifact to the TerraSatch public release store.
12. Publish that exact URL + SHA-256 on `www.terrasatch.com/downloads`.

Native builds are intentionally manual for the pilot; no GitHub Actions workflow is required.


## Independent native radio services

The Debian package installs `terrasatch-radio.service` using `/usr/local/bin/terrasatch-edge`
and `/etc/terrasatch-edge` / `/var/lib/terrasatch-edge`. The unit has its own recovery
policy, journal identifier, SIGTERM shutdown and process-group cleanup. It is installed
without enabling or starting RX. Configure targets and pairing, then:

```bash
sudo systemctl enable --now terrasatch-radio.service
sudo systemctl restart terrasatch-radio.service
sudo journalctl -u terrasatch-radio.service -f
```

`terrasatch-edge.service` continues heartbeat/inventory independently. Use `systemctl stop`
for an operator service stop. Package removal stops/disables both services while preserving
registration. Existing radio enablement survives upgrades; operators should restart radio
after upgrading the package. Development venv users can install
`deploy/systemd/user/terrasatch-radio.service` as a user unit and use `systemctl --user`;
it retains XDG paths and is not shipped as the native system service.

Windows installs `TerraSatchRadioService.exe` (WinSW) with service ID `TerraSatchRadio`,
separate from `TerraSatchEdge`. The radio wrapper uses the existing ProgramData registration,
UTF-8 logs in the same state/logs folder, bounded log rotation and `radio stop` for graceful
shutdown. Its initial SCM start mode is Manual. After configuring a target, an administrator runs:

```powershell
Set-Service -Name TerraSatchRadio -StartupType Automatic
Start-Service TerraSatchRadio
Restart-Service TerraSatchRadio
Get-Service TerraSatchEdge, TerraSatchRadio
```

Missing target/pairing fails clearly. Runtime/USB process failures return a nonzero exit
for supervisor recovery. USB reconnection may permit the next service restart to reopen
the SDR; automatic hotplug recovery and reboot persistence require physical validation.
Windows upgrades stop both services before replacing their shared executable and preserve
an existing radio service start mode. Start the radio service explicitly after an upgrade.

Bundled Windows RTL runtime validation requires `rtl_sdr.exe`, `rtl_fm.exe`, `rtl_test.exe`
and their matching trusted DLL bundle. The staging script inspects dependencies of every
shipped utility, including `rtl_fm`'s `libwinpthread-1.dll`. The build launches each required
tool with `-h` and an isolated PATH before accepting the bundle, so a developer's MSYS2
installation cannot hide a missing DLL. These checks do not open the receiver. No runtime means no usable radio monitoring;
a build without that optional bundle remains useful for normal Edge inventory/pairing.

## Raspberry Pi / ARM64 Linux

Use the same ARM64 Debian build and receiver provider. Build on the target architecture;
no separate Pi implementation or cross-architecture validation is claimed. Install `rtl-sdr`
(the package recommends it), use the distribution udev rules, and grant the intended
non-root operator membership in `plugdev` where the distro uses that group. Re-login after
group changes. Inspect `lsusb`, USB permissions and `rtl_test` before radio setup. Reliable
USB power and a suitable powered hub matter on field nodes. A DVB kernel driver can claim
the dongle: use the distro RTL-SDR guidance to resolve `dvb_usb_rtl28xxu` conflicts for a
dedicated SDR, rather than blindly changing drivers on a shared machine.
