# TerraSatch Edge v0.2.9 Windows beta — local QA only

This is a preparation and verification procedure, **not** a public release claim.

- No GitHub Actions or hosted CI workflows are required.
- Nothing here publishes a GitHub release, submits to Microsoft Store, updates the downloads page, or deploys production.
- Previous published v0.2.x release files remain untouched.
- The previously reported v0.2.9 signed installer is on the original Windows builder, not in this repository.
- The base branch still declares project version 0.2.8; preserve and reconcile any uncommitted local v0.2.9 files before rebuilding. **Do not check out over local release work.**
- The local inspection helper accepts package versions 0.2.9.0 and 1.2.9.0 due to earlier dev and newer Store-compatible MSIX version mappings.

## A. Inspect the existing beta

Run in Windows PowerShell from the original Windows checkout, without elevation:

    .\scripts\verify-install-windows-v029-beta.ps1 -MsixPath ".\release\TerraSatch-Edge_0.2.9_x64.msix"

Record the package identity, MSIX SHA-256, signer SHA-1 thumbprint and validity dates. **Compare the signer fingerprint against the separately recorded intended TerraSatch signing certificate identity.** A certificate read from an untrusted MSIX is not independent verification.

If a matching public-only certificate file is absent, it may be exported from the embedded signer for the matching-file check:

    $msix = ".\release\TerraSatch-Edge_0.2.9_x64.msix"
    $signer = (Get-AuthenticodeSignature -LiteralPath $msix).SignerCertificate
    if (-not $signer) { throw "MSIX signer not present." }
    Export-Certificate -Cert $signer -FilePath ".\release\TerraSatch-MSIX-v029.cer"

Never export, upload, distribute or trust a private-key .pfx for this procedure. Do not import the signing certificate into Trusted Root.

## B. Verify timestamp and install with administrator approval

After independently confirming the signer and retaining the correct public certificate, open **Windows PowerShell as Administrator** and run the following as one command:

    .\scripts\verify-install-windows-v029-beta.ps1 -MsixPath ".\release\TerraSatch-Edge_0.2.9_x64.msix" -CertificatePath ".\release\TerraSatch-MSIX-v029.cer" -ExpectedThumbprint "<verified signer SHA-1 thumbprint>" -ExpectedSha256 "<independently recorded MSIX SHA-256>" -Install

The helper checks the embedded MSIX manifest, exact signing certificate and public .cer, package hash, x64 architecture and radio-off startup defaults **before** changing machine trust. It imports the verified public certificate into LocalMachine\TrustedPeople only when absent. Next, SignTool must verify package trust and its timestamp with **exit code 0** (no warnings). Windows Authenticode must also say Valid; otherwise installation is blocked and newly added trust is removed.

The helper installs only the already-built package. It does not sign, rebuild, publish, launch the app, or enable radio operations.

## C. Test the exact installed package

- Confirm package version in Windows PowerShell: Get-AppxPackage -Name TerraSatch.Edge.Dev
- Launch Edge from Start and confirm full TerraSatch/Satchy artwork.
- Test the local operator console, persisted pairing, workspace API connection, and fresh authenticated heartbeat.
- Confirm Edge agent autostart behavior after first launch; verify radio startup remains OFF until operator enablement.
- Test receive-capable hardware only with approved local devices. No automatic transmission.
- Reboot and confirm startup, pairing persistence and a new heartbeat.
- Save console output, exact MSIX SHA-256, signer thumbprint, Windows version and results.

Do not publish v0.2.9 until all checks pass against the exact package.

## New signatures and certificate expiry

The staging branch also hardens scripts/build-windows-msix.ps1:

- Reject signing with a certificate not valid **at the time of signing**.
- Require RFC 3161 timestamp signing via SignTool /tr URL /td SHA256.
- Default time server: http://timestamp.digicert.com (may override with -TimestampUrl).
- Fail immediately if timestamping fails. Do not distribute an untimestamped fallback.
- Preserve the separate, unsigned -StoreUpload behavior.

A verified timestamp can preserve a signature that was valid **when created** after the certificate expires. It cannot make a new signature made using an already-expired certificate valid.

## Limitations

The GitHub connector cannot inspect the original Windows desktop, local signing key, actual v0.2.9 MSIX or administrator installation. This staging branch is **source preparation only**; passing source review is not equivalent to native Windows QA. No GitHub Actions are needed or used.
