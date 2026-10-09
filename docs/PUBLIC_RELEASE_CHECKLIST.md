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

The Store-upload MSIX is intentionally unsigned locally. Microsoft Store applies the production package signature after certification. The package uses per-user `windows.startupTask` extensions for the Edge agent and optional radio monitor and must not declare `packagedServices` or `localSystemServices`. Never publish the local QA certificate or a development-signed MSIX as the public Windows release; those artifacts exist only to validate packaging/install behavior before Store submission.

The existing PFX/Authenticode release path is optional only for a future separately signed direct-download `.exe` lane; it is not required for the free Microsoft Store route.

### Retire the expired Windows development artifact

The historical `v0.2.8-windows-beta` MSIX and `TerraSatch-MSIX-Dev.cer` used a self-signed
`CN=TerraSatch Inc.` certificate that expired September 29, 2026. The inspected package
has development identity `TerraSatch.Edge.Dev`, SHA-256
`12a86ef9dab92cb925b37376302d05d2ccad1185e1498f2cf27cfcd4a8250c49`, and no timestamp
signer exposed by Windows. Keep historical assets immutable; remove its installation
and certificate-trust links until a verified replacement is available. Do not renew only
the `.cer`, change the clock, trust a new root, or label a development signature as
Microsoft Store signing.

On October 9, 2026 the owner explicitly selected a terminal beta rebuild using the
existing self-signed certificate valid through September 22, 2028. This is an exception
to the default Store-only public Windows lane: label the replacement as a test-signed
beta requiring manual trust, use a new immutable release/version, verify the exact
matching certificate and a trusted signing timestamp, and retain the old artifacts.
The certificate still has an expiry date; a verified timestamp records signing time
and does not make the certificate immortal or provide Microsoft Store certification.
Never publish the signing private key or its PFX. Install the public certificate only
in Trusted People as documented for testing, not as a new trusted root. The public
trust verifier below intentionally does not certify self-signed beta artifacts.

After Store certification, check the exact delivered replacement, using the identity
from Partner Center (not guessed development values):

```powershell
.\scripts\verify-windows-msix-release.ps1 -MsixPath "<delivered Store MSIX path>" -ExpectedIdentityName "<Partner Center Package/Identity/Name>" -ExpectedPublisher "<Partner Center Package/Identity/Publisher>"
```

This gate requires Windows signature status `Valid`, rejects self-signed/development
packages and mismatched identities, and reports the exact artifact hash. It does not
claim Store certification or install/upgrade acceptance: verify these independently,
including the installed package's `SignatureKind` of `Store`. Verify the new package
family and preserve existing Edge state before switching from a development identity;
different package identities do not establish an in-place upgrade. Do not uninstall
the prior runtime or remove its data until the transition is verified.

Microsoft Store re-signing can change the final package hash. Verify and document the
delivered package, not only the unsigned submission archive. Public direct signing,
when used, must have a verified timestamp; Windows trust validation handles certificate
expiry at signing time. A checksum or `UnknownError` alone is not public signing proof.

## 6. Final public verification

From a clean browser/session:

1. Open the TerraSatch downloads page.
2. Confirm the intended platform route is the one actually being released.
3. For direct GitHub/Blob artifacts, download through the public URL and confirm SHA-256 matches the exact validated direct artifact.
4. Verify the GitHub attestation for direct GitHub artifacts.
5. For the Store route, install the Microsoft Store-certified MSIX and confirm Windows reports the expected package identity, package version, and trusted Microsoft Store signature. Do not require its SHA-256 to equal the locally submitted unsigned MSIX because Store publishing re-signs the package.
6. Confirm the operator console launches, the Edge startup task is enabled by default after first launch, and the radio startup task remains disabled until explicitly enabled.
7. Confirm `--version`, setup/pairing, `status`, service heartbeat, and radio-service behavior on the clean target.

Only then treat the native artifact as publicly released.
