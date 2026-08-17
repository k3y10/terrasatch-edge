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
- creates Setup, Status, Diagnostics, and Hardware Scan shortcuts
- launches a first-run PowerShell setup wrapper after installation
- keeps first-run setup visible until the operator closes it
- writes setup transcripts to `C:\ProgramData\TerraSatch\Edge\state\logs`
- uses ProgramData for shared configuration/state

## RTL-SDR / Nooelec runtime

PnP detection and the radio runtime are separate checks. Windows may identify a Nooelec NESDR correctly even when the command-line RTL-SDR runtime is not present.

Edge looks for `rtl_sdr` in:

1. the normal system `PATH`
2. `TERRASATCH_EDGE_TOOLS`
3. bundled Edge tool directories such as `Edge\tools\rtl-sdr`
4. the ProgramData TerraSatch tool directory

When an RTL-SDR/Nooelec is detected and `rtl_sdr` is available, `terrasatch-edge doctor` performs a finite receive-only IQ probe. The probe tunes to 100 MHz, reads a small sample, writes it to a temporary file, and deletes it when complete. This verifies that the runtime can actually open and read the receiver rather than only seeing the Windows PnP record.

### Recommended pilot staging path: MSYS2 UCRT64 package

For a repeatable Windows pilot build, use the packaged UCRT64 rtl-sdr runtime from MSYS2 rather than downloading an arbitrary binary archive.

Install MSYS2 once on the build machine:

```powershell
winget install -e --id MSYS2.MSYS2
```

Then from the TerraSatch Edge repository:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\stage-rtlsdr-windows.ps1
.\scripts\build-windows.ps1
```

`stage-rtlsdr-windows.ps1`:

- installs `mingw-w64-ucrt-x86_64-rtl-sdr` through MSYS2 `pacman`
- locates `rtl_sdr.exe`
- uses `ldd` to discover the UCRT64 DLL dependencies required by the executable
- copies the RTL-SDR utilities + resolved DLLs into `packaging\windows\vendor\rtl-sdr`
- records the installed package version and upstream provenance
- attempts to include the matching upstream `COPYING` file

The normal Windows build then detects that vendor folder automatically and embeds it in:

```text
C:\Program Files\TerraSatch\Edge\Edge\tools\rtl-sdr\
```

### Alternate reviewed runtime

A different reviewed runtime can be supplied explicitly:

```powershell
$env:TERRASATCH_RTLSDR_BUNDLE = "C:\path\to\trusted\rtl-sdr-runtime"
.\scripts\build-windows.ps1
```

The folder must contain `rtl_sdr.exe` and every DLL it requires.

The upstream Osmocom rtl-sdr project is GPL-licensed. Review and satisfy the applicable redistribution/source obligations before shipping a TerraSatch installer that embeds those binaries. The locally staged vendor binaries are ignored by Git by default so the repository does not accidentally publish them.

## Windows pilot verification

After installing and pairing:

```powershell
& "C:\Program Files\TerraSatch\Edge\Edge\TerraSatchEdge.exe" status
& "C:\Program Files\TerraSatch\Edge\Edge\TerraSatchEdge.exe" doctor
& "C:\Program Files\TerraSatch\Edge\Edge\TerraSatchEdge.exe" scan
Get-Service TerraSatchEdge
```

Expected lifecycle result:

- API online
- Edge credential accepted
- device + site persisted
- Windows service running
- Nooelec/RTL-SDR hardware recognized
- RTL-SDR runtime located when bundled
- SDR receive probe succeeds when the WinUSB driver and runtime can claim the device

GPS and direct radio-audio interfaces remain optional for the RTL-SDR receive-only pilot.

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

For controlled pilots, publish the reviewed native artifacts to a public TerraSatch-controlled release location and point TerraSatch.com to those assets. Code-sign each artifact before broad public distribution.

## Not yet in v0.2

- continuous RTL-SDR IQ capture
- channel/frequency profiles
- NFM/FM radio-audio pipeline into TerraListen/Satchy
- BCA radio audio capture/transcription
- offline SQLite replay queue
- automatic binary updater
- production code signing/notarization

The finite IQ readiness probe is intentionally narrower than the continuous radio adapter. It proves that Edge can open and read the receiver before the streaming/demodulation layer is added.
