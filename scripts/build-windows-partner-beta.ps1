[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$VersionMatch = Select-String -Path (Join-Path $Root "pyproject.toml") -Pattern '^version = "([^"]+)"' | Select-Object -First 1
if (-not $VersionMatch) {
    throw "Unable to determine TerraSatch Edge version from pyproject.toml."
}
$Version = $VersionMatch.Matches[0].Groups[1].Value
$SourceRevision = (& git rev-parse HEAD).Trim()
$LegacyInstaller = Join-Path $Root "release\TerraSatch-Edge-Setup-x64.exe"
$BetaName = "TerraSatch-Edge-$Version-Windows-x64-partner-beta-unsigned.exe"
$BetaInstaller = Join-Path $Root "release\$BetaName"

Write-Host "TerraSatch Edge Partner Beta build" -ForegroundColor Cyan
Write-Host "Version: $Version"
Write-Host "Channel: PARTNER BETA"
Write-Host "Publisher signature: UNSIGNED"
Write-Host "Integrity: SHA-256 checksum will be generated"
Write-Host "This is not the official signed TerraSatch Edge installer." -ForegroundColor Yellow
Write-Host "Windows may show Unknown publisher or SmartScreen warnings." -ForegroundColor Yellow
Write-Host ""

Remove-Item -LiteralPath $BetaInstaller -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath "$BetaInstaller.sha256" -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath "$BetaInstaller.release.json" -Force -ErrorAction SilentlyContinue

# The underlying builder keeps its strict official-release gate. Partner Beta is
# the only wrapper allowed to promote an -AllowUnsigned QA artifact into a
# clearly named, checksum-verified controlled evaluation artifact.
& (Join-Path $Root "scripts\build-windows.ps1") -AllowUnsigned

if (-not (Test-Path -LiteralPath $LegacyInstaller)) {
    throw "Windows builder completed without the expected installer: $LegacyInstaller"
}

$Signature = Get-AuthenticodeSignature -LiteralPath $LegacyInstaller
if ($Signature.Status -ne "NotSigned") {
    throw "Partner Beta unsigned build expected Authenticode status NotSigned, got $($Signature.Status)."
}

Move-Item -LiteralPath $LegacyInstaller -Destination $BetaInstaller -Force
$Hash = Get-FileHash -LiteralPath $BetaInstaller -Algorithm SHA256
$HashText = $Hash.Hash.ToLowerInvariant()
Set-Content -LiteralPath "$BetaInstaller.sha256" -Value "$HashText  $BetaName" -Encoding ascii

$Metadata = [ordered]@{
    product = "TerraSatch Edge"
    version = $Version
    channel = "partner-beta"
    intended_use = "controlled testing and evaluation"
    official_release = $false
    code_signature = "unsigned"
    integrity = "sha256"
    sha256 = $HashText
    source_revision = $SourceRevision
    artifact = $BetaName
    notice = "Not the official signed TerraSatch Edge installer. Windows may display publisher or SmartScreen warnings."
}
$Metadata | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath "$BetaInstaller.release.json" -Encoding utf8

Write-Host ""
Write-Host "Partner Beta artifact ready:" -ForegroundColor Green
Write-Host "  $BetaInstaller"
Write-Host "  $BetaInstaller.sha256"
Write-Host "  $BetaInstaller.release.json"
Write-Host "SHA256: $HashText"
Write-Host "Distribution: controlled beta / partner evaluation only; not an Official Release." -ForegroundColor Yellow
