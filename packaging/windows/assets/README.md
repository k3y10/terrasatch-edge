# TerraSatch Edge Windows branding

Place the reviewed Windows icon at:

```text
packaging/windows/assets/TerraSatchEdge.ico
```

The recommended icon is a square TerraSatch mark exported as a multi-resolution Windows ICO containing at least 16, 24, 32, 48, 64, 128 and 256 px sizes.

You can also stage an icon at build time without copying it manually:

```powershell
$env:TERRASATCH_EDGE_ICON = "C:\path\to\TerraSatchEdge.ico"
.\scripts\build-windows.ps1
```

When present, the build uses the icon for:

- the bundled `TerraSatchEdge.exe`
- the Inno Setup installer executable
- Start Menu shortcuts
- the optional desktop shortcut

The website currently uses `src/assets/terrasatch-logo.png` in the `k3y10/wasatch-ascent` production frontend. A Windows ICO should be generated from the approved square mark rather than stretching a horizontal wordmark.
