# RTL-SDR Windows runtime bundle

TerraSatch Edge can package a trusted Windows RTL-SDR runtime inside the installer.

Do **not** commit third-party binaries here unless their provenance, license obligations, and redistribution terms have been reviewed.

For a local pilot build, place the trusted runtime in this directory or set:

```powershell
$env:TERRASATCH_RTLSDR_BUNDLE = "C:\path\to\rtl-sdr-runtime"
```

The bundle should include `rtl_sdr.exe` plus every DLL it requires. The Windows build script copies the full folder into:

```text
TerraSatch Edge\Edge\tools\rtl-sdr\
```

The Edge runtime searches this bundled directory automatically. `terrasatch-edge doctor` then runs a finite receive-only IQ probe when an RTL-SDR/Nooelec is detected.

The upstream Osmocom rtl-sdr project is GPL-licensed. Keep the applicable license/source-offer obligations with any redistributed build.
