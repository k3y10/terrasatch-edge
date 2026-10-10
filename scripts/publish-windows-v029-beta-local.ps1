# Local-only publishing tool. DOES NOT use GitHub Actions.
# Validate by default; add -Publish only after Windows runtime acceptance.
[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = "High")]
param(
  [Parameter(Mandatory = $true)][string]$ReleaseDir,
  [string]$SourceDir,
  [switch]$Publish
)
$ErrorActionPreference = "Stop"
$repo = "k3y10/terrasatch-edge"
$tag = "v0.2.9-windows-beta"
$msixName = "TerraSatch-Edge_0.2.9_x64.msix"
$cerName = "TerraSatch-MSIX-Beta.cer"
$expectedHash = "BD1B57EB94B1391B6D51275FDC52AFDF74F5D1A23508D2CFBE8DE07100434CED"
$expectedThumb = "851BE292AC8201D413C9875A2EF86ED9B3779E76"

function AssertExit([string]$context) {
  if ($LASTEXITCODE -ne 0) { throw "$context failed (exit $LASTEXITCODE)." }
}
function GetSignTool {
  $cmd = Get-Command signtool.exe -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  $sdk = "C:\Program Files (x86)\Windows Kits\10\bin"
  if (-not (Test-Path $sdk)) { throw "Install Windows SDK SignTool to verify the timestamp." }
  $exe = Get-ChildItem $sdk -Recurse -Filter signtool.exe -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match "\\x64\\signtool\.exe$" } |
    Sort-Object FullName -Descending | Select-Object -First 1 -ExpandProperty FullName
  if (-not $exe) { throw "Windows SDK x64 SignTool not found." }
  return $exe
}

$ReleaseDir = (Resolve-Path -LiteralPath $ReleaseDir).Path
if (-not $SourceDir) { $SourceDir = Split-Path -Parent $ReleaseDir }
$SourceDir = (Resolve-Path -LiteralPath $SourceDir).Path
$msix = Join-Path $ReleaseDir $msixName
$cer = Join-Path $ReleaseDir $cerName
foreach ($file in @($msix, $cer)) {
  if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Missing: $file" }
}
$hash = (Get-FileHash $msix -Algorithm SHA256).Hash.ToUpperInvariant()
if ($hash -ne $expectedHash) { throw "MSIX hash mismatch: $hash" }
$certificate = [Security.Cryptography.X509Certificates.X509Certificate2]::new($cer)
if ($certificate.HasPrivateKey -or $certificate.Thumbprint.ToUpperInvariant() -ne $expectedThumb) {
  throw "Only the verified public certificate may be uploaded."
}
$signature = Get-AuthenticodeSignature -LiteralPath $msix
if (-not $signature.SignerCertificate -or $signature.Status.ToString() -ne "Valid" -or
    $signature.SignerCertificate.Thumbprint.ToUpperInvariant() -ne $expectedThumb) {
  throw "MSIX is not validly signed by the expected certificate."
}
& (GetSignTool) verify /pa /v /tw $msix
AssertExit "Signature and RFC3161 timestamp check"

# Release tag must represent reviewed, pushed v0.2.9 source—not old main.
$pyproject = Join-Path $SourceDir "pyproject.toml"
if (-not (Test-Path $pyproject)) { throw "Edge source pyproject.toml not found." }
if ((Get-Content $pyproject -Raw) -notmatch '(?m)^version\s*=\s*"0\.2\.9"\s*$') {
  throw "Local source is not declared v0.2.9. Reconcile source before release."
}
$origin = (& git -C $SourceDir remote get-url origin).Trim()
AssertExit "Git remote"
if ($origin -notmatch '(?i)(github\.com[:/])k3y10/terrasatch-edge(\.git)?$') {
  throw "Unexpected git origin: $origin"
}
$dirty = @(& git -C $SourceDir status --porcelain --untracked-files=no)
AssertExit "Git status"
if ($dirty.Count -gt 0) { throw "Tracked Edge source has uncommitted changes. Commit and review first." }
$sourceSha = (& git -C $SourceDir rev-parse HEAD).Trim()
AssertExit "Git source SHA"

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
  throw "Install GitHub CLI with: winget install --id GitHub.cli -e"
}
& gh auth status --hostname github.com
AssertExit "GitHub CLI auth"
$remoteSource = (& gh api "repos/$repo/commits/$sourceSha" --jq ".sha" 2>$null)
if ($LASTEXITCODE -ne 0 -or ($remoteSource | Out-String).Trim() -ne $sourceSha) {
  throw "Local source commit not on GitHub. Push the reviewed v0.2.9 source first."
}
& gh release view $tag --repo $repo --json tagName >$null 2>$null
if ($LASTEXITCODE -eq 0) { throw "Release already exists; refusing to overwrite it." }

Write-Host "PASS: preflight checks." -ForegroundColor Green
Write-Host "Package SHA256: $hash"
Write-Host "Public cert SHA1 thumbprint: $expectedThumb"
Write-Host "Source SHA: $sourceSha"
if (-not $Publish) {
  Write-Host "Inspection only. Once runtime QA passes, rerun with -Publish." -ForegroundColor Yellow
  return
}
if (-not $PSCmdlet.ShouldProcess("$repo/$tag", "Create draft, upload, round-trip verify, and publish prerelease")) {
  return
}

$tmp = Join-Path $env:TEMP ("terrasatch-release-" + [guid]::NewGuid().ToString("N"))
New-Item $tmp -ItemType Directory -Force | Out-Null
try {
  $certHash = (Get-FileHash $cer -Algorithm SHA256).Hash.ToLowerInvariant()
  $sums = Join-Path $tmp "SHA256SUMS-WINDOWS.txt"
  @("$($hash.ToLowerInvariant())  $msixName", "$certHash  $cerName") |
    Set-Content $sums -Encoding Ascii

  $install = Join-Path $tmp "WINDOWS-MSIX-INSTALL.txt"
  @"
TerraSatch Edge v0.2.9 Windows x64 development-signed beta.
This is NOT Microsoft Store certified; trust the matching public test certificate only on approved beta computers.

1. Download $msixName and $cerName from this release.
2. SHA256 of MSIX must match $expectedHash
3. Public certificate SHA1 thumbprint must match $expectedThumb
4. In PowerShell as Administrator:
   Import-Certificate -FilePath .\$cerName -CertStoreLocation Cert:\LocalMachine\TrustedPeople
5. Verify with Windows SDK:
   signtool verify /pa /v /tw .\$msixName
   Require 1 success, 0 warnings, 0 errors.
6. Install for signed-in Windows user:
   Add-AppxPackage -Path .\$msixName

Never trust this beta certificate in Trusted Root and NEVER distribute a private key or PFX.
To remove Edge: Get-AppxPackage -Name TerraSatch.Edge.Dev | Remove-AppxPackage
To revoke trust after uninstalling all packages signed with this certificate:
   Remove-Item Cert:\LocalMachine\TrustedPeople\$expectedThumb
"@ | Set-Content $install -Encoding UTF8

  $notes = Join-Path $tmp "RELEASE-NOTES.md"
  @"
TerraSatch Edge v0.2.9 Windows x64 development beta. This is NOT Microsoft Store-signed.
Package version: 1.2.9.0
MSIX SHA256: $expectedHash
Public signer SHA1 thumbprint: $expectedThumb
Signing certificate valid through September 22, 2028.
RFC3161 timestamp verified October 9, 2026.
Original local signature and MSIX installation validated on Windows with 0 warnings.
Operator console, pairing, reboot and radio hardware still require field acceptance testing.
Source commit: $sourceSha

This release contains a development-signed package and its PUBLIC certificate only.
Read WINDOWS-MSIX-INSTALL.txt before installation. No private signing key is distributed.
Linux has a separate release; existing old versions remain untouched.
"@ | Set-Content $notes -Encoding UTF8

  & gh release create $tag $msix $cer $sums $install --repo $repo --target $sourceSha --title "TerraSatch Edge v0.2.9 Windows beta" --notes-file $notes --prerelease --latest=false --draft
  AssertExit "Draft release upload"

  $roundtrip = Join-Path $tmp "roundtrip"
  New-Item $roundtrip -ItemType Directory -Force | Out-Null
  & gh release download $tag --repo $repo --dir $roundtrip --pattern $msixName --pattern $cerName
  AssertExit "Draft asset download"
  if ((Get-FileHash (Join-Path $roundtrip $msixName) -Algorithm SHA256).Hash.ToUpperInvariant() -ne $expectedHash -or
      (Get-FileHash (Join-Path $roundtrip $cerName) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $certHash) {
    throw "Round-trip asset hash mismatch: draft left unpublished."
  }

  & gh release edit $tag --repo $repo --draft=false
  AssertExit "Publish release"
  Write-Host "PUBLISHED: https://github.com/$repo/releases/tag/$tag" -ForegroundColor Green
  Write-Host "Windows MSIX: https://github.com/$repo/releases/download/$tag/$msixName"
  Write-Host "Public certificate: https://github.com/$repo/releases/download/$tag/$cerName"
}
finally {
  Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
}
