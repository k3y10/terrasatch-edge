# TerraSatch Edge Windows branding

Windows release builds use **Satchy**, TerraSatch's Sasquatch AI agent, as the application and installer icon.

By default `scripts/build-windows.ps1` downloads the approved transparent Satchy artwork from:

```text
https://www.terrasatch.com/terralisten-sasquatch.png
```

The build uses Pillow to crop the transparent artwork, place it on a square transparent canvas with safe padding, and generate:

```text
packaging/windows/assets/TerraSatchEdge.ico
```

The ICO contains 16, 24, 32, 48, 64, 128 and 256 px sizes for Windows Explorer, Start Menu, desktop shortcuts, installer/UAC surfaces and the bundled executable.

## Overrides

To use a reviewed custom Windows icon directly:

```powershell
$env:TERRASATCH_EDGE_ICON = "C:\path\to\TerraSatchEdge.ico"
.\scripts\build-windows.ps1
```

To generate the ICO from another approved local image or public image URL:

```powershell
$env:TERRASATCH_SATCHY_ICON_SOURCE = "C:\path\to\satchy.png"
# or a public https:// URL
.\scripts\build-windows.ps1
```

Release builds fail if a valid Satchy icon cannot be staged. They do not silently ship a generic Windows/Python icon.

The generated icon is used for:

- `TerraSatchEdge.exe`
- `TerraSatch-Edge-Setup-x64.exe`
- Add/Remove Programs / uninstall display
- TerraSatch Edge Status shortcut
- TerraSatch Edge Diagnostics shortcut
- TerraSatch Edge Hardware Scan shortcut
- TerraSatch Edge Setup shortcut
- the desktop TerraSatch Edge shortcut

The desktop shortcut is recreated on install/upgrade so existing pilot machines pick up the current Satchy branding.
