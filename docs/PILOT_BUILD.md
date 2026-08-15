# TerraSatch Edge v0.2 Pilot Build

## What v0.2 changes

TerraSatch Edge now uses the production Edge control plane:

1. Edge scans the local machine.
2. `POST /api/v1/edge/pairings` creates a short pairing code.
3. The operator opens the returned TerraSatch Admin URL and assigns organization + site.
4. Edge polls `POST /api/v1/edge/pairings/token`.
5. The issued device credential is stored locally.
6. Edge sends hardware inventory and capabilities to `POST /api/v1/edge/heartbeat`.
7. Edge reads `GET /api/v1/edge/config` after each heartbeat.
8. Test radio-style observations still use `POST /api/v1/transmissions`.

The manual service-key setup path remains only as an advanced fallback.

## Windows pilot artifact

Build on a Windows x64 machine:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\build-windows.ps1
```

Build-machine requirements:

- Python 3.12
- Inno Setup 6 or 7
- Internet access for Python dependencies and the pinned WinSW 2.12.0 service wrapper

Result:

```text
release\TerraSatch-Edge-Setup-x64.exe
```

The target field computer does **not** need Python installed.

The installer:

- installs the bundled Edge runtime under Program Files
- installs TerraSatch Edge as an automatic Windows service
- creates Setup/Status shortcuts
- launches `TerraSatchEdge setup` after installation
- uses ProgramData for shared configuration/state

## macOS

Build on macOS:

```bash
./scripts/build-macos.sh
```

Result:

```text
release/TerraSatch-Edge-0.2.0.pkg
```

The pilot `.pkg` is intentionally unsigned. Public distribution should use an Apple Developer ID Installer certificate and notarization.

## Debian/Ubuntu Linux

Build on the target architecture:

```bash
./scripts/build-linux-deb.sh
```

Result examples:

```text
release/terrasatch-edge_0.2.0_amd64.deb
release/terrasatch-edge_0.2.0_arm64.deb
```

The package installs a `systemd` service.

## Website distribution

Do not link TerraSatch.com to a source checkout or Python installer.

Publish native release artifacts and their SHA-256 hashes, then expose:

```text
Windows x64  → TerraSatch-Edge-Setup-x64.exe
macOS        → TerraSatch-Edge-0.2.0.pkg
Linux AMD64  → terrasatch-edge_0.2.0_amd64.deb
Linux ARM64  → terrasatch-edge_0.2.0_arm64.deb
```

For controlled pilots, GitHub Releases can host the files and TerraSatch.com can point to those assets. For broader distribution, use a TerraSatch-controlled download/CDN path and code-sign each artifact.

## Not yet in v0.2

- actual RTL-SDR IQ capture/demodulation
- BCA radio audio capture/transcription
- channel/frequency profiles
- offline SQLite replay queue
- automatic binary updater
- production code signing/notarization

Those belong in the radio adapter/distribution hardening phase after pairing + device health are proven on real field laptops.
