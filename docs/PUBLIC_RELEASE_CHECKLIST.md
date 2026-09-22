# TerraSatch Edge public release checklist

Use this checklist before enabling a new Edge artifact on the public downloads page.

## 1. API release gate

Production Edge clients target:

```text
https://api.terrasatch.com
```

The API production environment must set:

```text
TERRASATCH_API_BASE_URL=https://api.terrasatch.com
```

Before publishing an Edge build:

1. Deploy the intended API `main` revision.
2. Confirm `/health/ready` is healthy over HTTPS and reports the intended revision.
3. Confirm an already-paired Edge service can send authenticated heartbeats after the API deployment without reinstalling or re-pairing.
4. Start a disposable pairing and confirm `verification_url` begins with `https://api.terrasatch.com/admin/edge/pair?code=`.

Do not publish a client build to work around an API-side pairing or heartbeat regression. Keep the client/API responsibility boundary explicit.

## 2. Edge environment contract

The Edge runtime defaults to:

```text
TERRASATCH_EDGE_API_URL=https://api.terrasatch.com
```

`TERRASATCH_EDGE_API_URL` is an operator/deployment override and takes precedence over saved config. The Windows Setup Wizard uses the same environment contract for new pairing while preserving a valid existing registration.

Verify on every native package:

```text
terrasatch-edge --version
terrasatch-edge status
terrasatch-edge doctor
```

`status` must show the expected API URL, `API: ONLINE`, and `Auth: OK` after pairing.

## 3. Native artifact gate

For each exact artifact:

1. Build from the intended Edge release commit.
2. Run the full test suite as part of the native build.
3. Install the produced artifact, not a source checkout.
4. Pair once and record the Device ID/site.
5. Confirm the background service picks up registration and sends heartbeats.
6. Restart/reboot and confirm registration persists.
7. For the Microsoft Store path, build and locally validate the MSIX package, confirm the manifest uses the exact Partner Center identity, and confirm it declares startup tasks rather than packaged Windows services.
8. For any direct `.exe` compatibility artifact, keep it labeled beta/unsigned unless it has a separately trusted Authenticode signature.
9. Record SHA-256 from the exact artifact that passed validation.
10. Verify the GitHub build-provenance attestation for direct GitHub artifacts with `gh attestation verify <downloaded-file> --repo k3y10/terrasatch-edge`.
11. Test real supported receive hardware when that platform is advertised as receiver-ready.

TX remains provider/hardware gated and must never be inferred from hardware discovery alone.

## 4. Public Blob layout

Keep immutable versioned objects in the public release store. Recommended paths:

```text
edge/windows/v<version>/TerraSatch-Edge-Setup-x64.exe
edge/linux/v<version>/terrasatch-edge_<version>_amd64.deb
edge/linux/v<version>/terrasatch-edge_<version>_arm64.deb
edge/macos/v<version>/TerraSatch-Edge-<version>-macOS-arm64.pkg
edge/macos/v<version>/TerraSatch-Edge-<version>-macOS-x64.pkg
```

Never overwrite a validated versioned object with different bytes. Publish a new version/path instead.

After upload, verify the public URL from a machine/session that is not authenticated to Vercel and compare its SHA-256 to the locally validated artifact.

## 5. Downloads page contract

The TerraSatch downloads page currently supports these release URL environment variables:

```text
VITE_EDGE_WINDOWS_X64_URL
VITE_EDGE_MACOS_ARM64_URL
VITE_EDGE_MACOS_X64_URL
VITE_EDGE_LINUX_AMD64_URL
VITE_EDGE_LINUX_ARM64_URL
```

Do not enable a platform button until its exact public URL and checksum have passed the gates above. Keep the page version label aligned with the artifact version being advertised.

For the primary no-cost Windows route, Microsoft Store identity values are required instead of a private production signing key:

```text
TERRASATCH_MSIX_IDENTITY_NAME
TERRASATCH_MSIX_PUBLISHER
TERRASATCH_MSIX_PUBLISHER_DISPLAY_NAME
```

Run the normal Windows release-candidate QA locally first:

```powershell
.\scripts\qa-windows-msix-local.ps1
```

Copy `Identity Name` and `Publisher` exactly from Partner Center after reserving the TerraSatch Edge product. The Store build refuses the development identity and requires all three Partner Center identity values explicitly before it will package:

```powershell
.\scripts\build-windows-msix.ps1 -StoreUpload
```

The Store-upload MSIX is intentionally unsigned locally. Microsoft Store applies the production package signature after certification. The package uses per-user `windows.startupTask` extensions for the Edge agent and optional radio monitor and must not declare `packagedServices` or `localSystemServices`.

The existing PFX/Authenticode release path is optional only for a future separately signed direct-download `.exe` lane; it is not required for the free Microsoft Store route.

## 6. Final public verification

From a clean browser/session:

1. Open the TerraSatch downloads page.
2. Confirm the intended platform button is enabled and points to the immutable versioned Blob object.
3. Download the artifact through the public URL.
4. Confirm SHA-256 matches the validated local artifact.
5. Verify the GitHub attestation for direct GitHub artifacts.
6. For the Store route, install the Microsoft Store-certified MSIX and confirm Windows reports the expected trusted package publisher.
7. Confirm the operator console launches, the Edge startup task is enabled by default after first launch, and the radio startup task remains disabled until explicitly enabled.
8. Confirm `--version`, setup/pairing, `status`, service heartbeat, and radio-service behavior on the clean target.

Only then treat the native artifact as publicly released.
