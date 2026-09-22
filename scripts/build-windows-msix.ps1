[CmdletBinding()]
param(
    [string]$IdentityName,
    [string]$Publisher,
    [string]$PublisherDisplayName,
    [string]$CertificateThumbprint,
    [switch]$SkipRuntimeBuild,
    [switch]$StoreUpload
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (-not $IdentityName) {
    $IdentityName = if ($env:TERRASATCH_MSIX_IDENTITY_NAME) { $env:TERRASATCH_MSIX_IDENTITY_NAME } else { "TerraSatch.Edge.Dev" }
}
if (-not $Publisher) {
    $Publisher = if ($env:TERRASATCH_MSIX_PUBLISHER) { $env:TERRASATCH_MSIX_PUBLISHER } else { "CN=TerraSatch Inc." }
}
if (-not $PublisherDisplayName) {
    $PublisherDisplayName = if ($env:TERRASATCH_MSIX_PUBLISHER_DISPLAY_NAME) { $env:TERRASATCH_MSIX_PUBLISHER_DISPLAY_NAME } else { "TerraSatch Inc." }
}
if (-not $CertificateThumbprint -and $env:TERRASATCH_MSIX_CERT_THUMBPRINT) {
    $CertificateThumbprint = ($env:TERRASATCH_MSIX_CERT_THUMBPRINT -replace "\s", "").ToUpperInvariant()
}

function Resolve-WindowsSdkTool {
    param([Parameter(Mandatory = $true)][string]$Name)

    $Candidates = @()
    $Command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($Command) { $Candidates += $Command.Source }

    $WindowsKitRoot = "C:\Program Files (x86)\Windows Kits\10\bin"
    if (Test-Path -LiteralPath $WindowsKitRoot) {
        $Candidates += Get-ChildItem -LiteralPath $WindowsKitRoot -Filter $Name -Recurse -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match "\\x64\\$([regex]::Escape($Name))$" } |
            Sort-Object FullName -Descending |
            Select-Object -ExpandProperty FullName
    }

    $Resolved = $Candidates |
        Where-Object { $_ -and (Test-Path -LiteralPath $_) } |
        Select-Object -Unique |
        Select-Object -First 1
    if (-not $Resolved) {
        throw "$Name was not found. Install the Windows SDK App Certification/Signing tools."
    }
    return (Resolve-Path -LiteralPath $Resolved).Path
}

$MakeAppx = Resolve-WindowsSdkTool -Name "makeappx.exe"
$SignTool = Resolve-WindowsSdkTool -Name "signtool.exe"

if (-not $SkipRuntimeBuild) {
    Write-Host "[1/7] Building the existing Windows Edge runtime" -ForegroundColor Cyan
    $PreviousThumbprint = $env:TERRASATCH_CODESIGN_CERT_THUMBPRINT
    Remove-Item Env:\TERRASATCH_CODESIGN_CERT_THUMBPRINT -ErrorAction SilentlyContinue
    try {
        & (Join-Path $Root "scripts\build-windows.ps1") -AllowUnsigned
        if ($LASTEXITCODE -ne 0) { throw "Base Windows runtime build failed with exit code $LASTEXITCODE." }
    } finally {
        if ($PreviousThumbprint) {
            $env:TERRASATCH_CODESIGN_CERT_THUMBPRINT = $PreviousThumbprint
        }
    }
} else {
    Write-Host "[1/7] Reusing the existing Windows Edge runtime" -ForegroundColor Cyan
}

$BuildVenv = Join-Path $Root ".build-venv"
$Python = Join-Path $BuildVenv "Scripts\python.exe"
$RuntimeDir = Join-Path $Root "dist\TerraSatchEdge"
$Vendor = Join-Path $Root "packaging\windows\vendor"
$WinSW = Join-Path $Vendor "TerraSatchEdgeService.exe"
$ManifestTemplate = Join-Path $Root "packaging\windows\msix\AppxManifest.template.xml"
$IconFile = Join-Path $Root "packaging\windows\assets\TerraSatchEdge.ico"
$LogoSource = Join-Path $Root "src\terrasatch_edge\assets\terrasatch-logo.webp"

foreach ($RequiredPath in @($Python, $RuntimeDir, $WinSW, $ManifestTemplate, $IconFile, $LogoSource)) {
    if (-not (Test-Path -LiteralPath $RequiredPath)) { throw "MSIX build prerequisite missing: $RequiredPath" }
}

$Version = (& $Python -c "import terrasatch_edge; print(terrasatch_edge.__version__)").Trim()
$VersionParts = $Version.Split(".")
if ($VersionParts.Count -eq 3) {
    $MsixVersion = "$Version.0"
} elseif ($VersionParts.Count -eq 4) {
    $MsixVersion = $Version
} else {
    throw "MSIX requires a three- or four-part numeric TerraSatch version; received $Version."
}

$ReleaseDir = Join-Path $Root "release"
$Staging = Join-Path $ReleaseDir "msix-staging"
$LauncherDist = Join-Path $ReleaseDir "msix-launcher-dist"
$LauncherBuild = Join-Path $ReleaseDir "msix-launcher-build"
$LauncherSpec = Join-Path $ReleaseDir "msix-launcher-spec"
$VerifyDir = Join-Path $ReleaseDir "msix-verify"
$Artifact = Join-Path $ReleaseDir "TerraSatch-Edge_${Version}_x64.msix"

Write-Host "[2/7] Staging MSIX package layout" -ForegroundColor Cyan
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $Staging, $LauncherDist, $LauncherBuild, $LauncherSpec, $VerifyDir
New-Item -ItemType Directory -Force $Staging, (Join-Path $Staging "Edge"), (Join-Path $Staging "Assets") | Out-Null
Copy-Item -Path (Join-Path $RuntimeDir "*") -Destination (Join-Path $Staging "Edge") -Recurse -Force
Copy-Item -LiteralPath $WinSW -Destination (Join-Path $Staging "TerraSatchEdgeService.exe") -Force
Copy-Item -LiteralPath $WinSW -Destination (Join-Path $Staging "TerraSatchRadioService.exe") -Force
Copy-Item -LiteralPath (Join-Path $Root "packaging\windows\TerraSatchEdgeService.xml") -Destination (Join-Path $Staging "TerraSatchEdgeService.xml") -Force
Copy-Item -LiteralPath (Join-Path $Root "packaging\windows\TerraSatchRadioService.xml") -Destination (Join-Path $Staging "TerraSatchRadioService.xml") -Force

Write-Host "[3/7] Building the Store/Start launcher" -ForegroundColor Cyan
& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --name TerraSatchEdgeConsoleLauncher `
    --icon $IconFile `
    --collect-data terrasatch_edge `
    --collect-all uvicorn `
    --collect-all fastapi `
    --distpath $LauncherDist `
    --workpath $LauncherBuild `
    --specpath $LauncherSpec `
    (Join-Path $Root "packaging\entrypoints\edge_msix_console.py")
if ($LASTEXITCODE -ne 0) { throw "MSIX launcher PyInstaller build failed with exit code $LASTEXITCODE." }
Copy-Item -LiteralPath (Join-Path $LauncherDist "TerraSatchEdgeConsoleLauncher.exe") -Destination $Staging -Force

Write-Host "[4/7] Generating MSIX visual assets and manifest" -ForegroundColor Cyan
$AssetScript = Join-Path $env:TEMP "terrasatch-msix-assets.py"
$AssetPython = @'
from pathlib import Path
import sys
from PIL import Image

source = Path(sys.argv[1])
destination = Path(sys.argv[2])
image = Image.open(source).convert("RGBA")
alpha = image.getchannel("A")
bbox = alpha.getbbox()
if bbox:
    image = image.crop(bbox)

for filename, size in [
    ("StoreLogo.png", 50),
    ("Square44x44Logo.png", 44),
    ("Square150x150Logo.png", 150),
]:
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    working = image.copy()
    padding = max(2, int(size * 0.08))
    working.thumbnail((size - 2 * padding, size - 2 * padding), Image.Resampling.LANCZOS)
    canvas.alpha_composite(working, ((size - working.width) // 2, (size - working.height) // 2))
    canvas.save(destination / filename, "PNG")
'@
Set-Content -LiteralPath $AssetScript -Value $AssetPython -Encoding UTF8
try {
    & $Python $AssetScript $LogoSource (Join-Path $Staging "Assets")
    if ($LASTEXITCODE -ne 0) { throw "MSIX visual asset generation failed with exit code $LASTEXITCODE." }
} finally {
    Remove-Item -LiteralPath $AssetScript -Force -ErrorAction SilentlyContinue
}

function Escape-XmlValue {
    param([Parameter(Mandatory = $true)][string]$Value)
    return [System.Security.SecurityElement]::Escape($Value)
}

$Manifest = Get-Content -LiteralPath $ManifestTemplate -Raw
$Manifest = $Manifest.Replace("__IDENTITY_NAME__", (Escape-XmlValue $IdentityName))
$Manifest = $Manifest.Replace("__PUBLISHER__", (Escape-XmlValue $Publisher))
$Manifest = $Manifest.Replace("__PUBLISHER_DISPLAY_NAME__", (Escape-XmlValue $PublisherDisplayName))
$Manifest = $Manifest.Replace("__VERSION__", (Escape-XmlValue $MsixVersion))
Set-Content -LiteralPath (Join-Path $Staging "AppxManifest.xml") -Value $Manifest -Encoding UTF8

Write-Host "[5/7] Packing TerraSatch Edge MSIX" -ForegroundColor Cyan
Remove-Item -LiteralPath $Artifact -Force -ErrorAction SilentlyContinue
& $MakeAppx pack /d $Staging /p $Artifact /o
if ($LASTEXITCODE -ne 0) { throw "MakeAppx failed with exit code $LASTEXITCODE." }

Write-Host "[6/7] Signing or preparing Store upload package" -ForegroundColor Cyan
if ($StoreUpload) {
    Write-Host "Store-upload mode: package remains unsigned so Microsoft Store can apply the production signature." -ForegroundColor Yellow
} else {
    if (-not $CertificateThumbprint) {
        throw "Local-install MSIX builds require -CertificateThumbprint or TERRASATCH_MSIX_CERT_THUMBPRINT. Use -StoreUpload only for a Partner Center submission package."
    }
    $CertificateThumbprint = ($CertificateThumbprint -replace "\s", "").ToUpperInvariant()
    $Certificate = Get-ChildItem Cert:\CurrentUser\My, Cert:\LocalMachine\My -ErrorAction SilentlyContinue |
        Where-Object { ($_.Thumbprint -replace "\s", "").ToUpperInvariant() -eq $CertificateThumbprint } |
        Select-Object -First 1
    if (-not $Certificate) { throw "MSIX signing certificate $CertificateThumbprint was not found in CurrentUser or LocalMachine Personal stores." }
    if (-not $Certificate.HasPrivateKey) { throw "MSIX signing certificate does not expose a private key." }
    if ($Certificate.Subject -ne $Publisher) {
        throw "MSIX Publisher must exactly match the signing certificate Subject. Manifest: $Publisher Certificate: $($Certificate.Subject)"
    }

    & $SignTool sign /v /fd SHA256 /sha1 $CertificateThumbprint $Artifact
    if ($LASTEXITCODE -ne 0) { throw "MSIX SignTool signing failed with exit code $LASTEXITCODE." }
    & $SignTool verify /pa /v $Artifact
    if ($LASTEXITCODE -ne 0) { throw "MSIX signature verification failed with exit code $LASTEXITCODE." }
}

Write-Host "[7/7] Verifying package structure and checksum" -ForegroundColor Cyan
New-Item -ItemType Directory -Force $VerifyDir | Out-Null
& $MakeAppx unpack /p $Artifact /d $VerifyDir /o
if ($LASTEXITCODE -ne 0) { throw "MakeAppx unpack verification failed with exit code $LASTEXITCODE." }
if (-not (Test-Path -LiteralPath (Join-Path $VerifyDir "AppxManifest.xml"))) { throw "MSIX verification did not recover AppxManifest.xml." }

$Hash = Get-FileHash -LiteralPath $Artifact -Algorithm SHA256
Write-Host ""
Write-Host "Built: $Artifact" -ForegroundColor Green
Write-Host "Version: $MsixVersion"
Write-Host "Identity: $IdentityName"
Write-Host "Publisher: $Publisher"
Write-Host "SHA256: $($Hash.Hash)"
if ($StoreUpload) {
    Write-Host "Signing: Microsoft Store submission package (unsigned locally)" -ForegroundColor Yellow
} else {
    Write-Host "Signing: local development certificate $CertificateThumbprint" -ForegroundColor Green
}
