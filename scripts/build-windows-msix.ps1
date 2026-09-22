[CmdletBinding()]
param(
    [string]$IdentityName,
    [string]$Publisher,
    [string]$PublisherDisplayName,
    [string]$CertificateThumbprint,
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
    $Resolved = $Candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -Unique | Select-Object -First 1
    if (-not $Resolved) { throw "$Name was not found. Install the Windows SDK App Packaging/Signing tools." }
    return (Resolve-Path -LiteralPath $Resolved).Path
}

function Invoke-PyInstaller {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$EntryPoint,
        [Parameter(Mandatory = $true)][string]$DistPath,
        [Parameter(Mandatory = $true)][string]$WorkPath,
        [Parameter(Mandatory = $true)][string]$SpecPath,
        [switch]$OneFile
    )
    $Arguments = @(
        "--noconfirm",
        "--clean",
        $(if ($OneFile) { "--onefile" } else { "--onedir" }),
        "--name", $Name,
        "--icon", $script:IconFile,
        "--collect-data", "terrasatch_edge",
        "--collect-all", "uvicorn",
        "--collect-all", "fastapi",
        "--distpath", $DistPath,
        "--workpath", $WorkPath,
        "--specpath", $SpecPath,
        $EntryPoint
    )
    & $script:Python -m PyInstaller @Arguments
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed for $Name with exit code $LASTEXITCODE." }
}

$MakeAppx = Resolve-WindowsSdkTool -Name "makeappx.exe"
$SignTool = Resolve-WindowsSdkTool -Name "signtool.exe"
$BuildVenv = Join-Path $Root ".build-venv"
if (-not (Test-Path -LiteralPath $BuildVenv)) { py -3.12 -m venv $BuildVenv }
$Python = Join-Path $BuildVenv "Scripts\python.exe"
& $Python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed with exit code $LASTEXITCODE." }
& $Python -m pip install -e ".[serial,usb,ui,build,dev]"
if ($LASTEXITCODE -ne 0) { throw "MSIX build dependency installation failed with exit code $LASTEXITCODE." }

$IconFile = Join-Path $Root "packaging\windows\assets\TerraSatchEdge.ico"
$LogoSource = Join-Path $Root "src\terrasatch_edge\assets\terrasatch-logo.webp"
$ManifestTemplate = Join-Path $Root "packaging\windows\msix\AppxManifest.template.xml"
foreach ($RequiredPath in @($IconFile, $LogoSource, $ManifestTemplate)) {
    if (-not (Test-Path -LiteralPath $RequiredPath)) { throw "MSIX prerequisite missing: $RequiredPath" }
}

Write-Host "[1/8] Running Edge tests" -ForegroundColor Cyan
$PytestBaseTemp = Join-Path $Root ".pytest-tmp-msix"
Remove-Item -LiteralPath $PytestBaseTemp -Recurse -Force -ErrorAction SilentlyContinue
try {
    & $Python -m pytest --basetemp $PytestBaseTemp
    if ($LASTEXITCODE -ne 0) { throw "TerraSatch Edge tests failed with exit code $LASTEXITCODE." }
} finally {
    Remove-Item -LiteralPath $PytestBaseTemp -Recurse -Force -ErrorAction SilentlyContinue
}

$Version = (& $Python -c "import terrasatch_edge; print(terrasatch_edge.__version__)").Trim()
$VersionParts = $Version.Split(".")
if ($VersionParts.Count -eq 3) { $MsixVersion = "$Version.0" }
elseif ($VersionParts.Count -eq 4) { $MsixVersion = $Version }
else { throw "MSIX requires a three- or four-part numeric TerraSatch version; received $Version." }

$ReleaseDir = Join-Path $Root "release"
$RuntimeDist = Join-Path $ReleaseDir "msix-runtime-dist"
$RuntimeBuild = Join-Path $ReleaseDir "msix-runtime-build"
$RuntimeSpec = Join-Path $ReleaseDir "msix-runtime-spec"
$LauncherDist = Join-Path $ReleaseDir "msix-launcher-dist"
$LauncherBuild = Join-Path $ReleaseDir "msix-launcher-build"
$LauncherSpec = Join-Path $ReleaseDir "msix-launcher-spec"
$Staging = Join-Path $ReleaseDir "msix-staging"
$VerifyDir = Join-Path $ReleaseDir "msix-verify"
$Artifact = Join-Path $ReleaseDir "TerraSatch-Edge_${Version}_x64.msix"

Write-Host "[2/8] Building Edge runtime" -ForegroundColor Cyan
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $RuntimeDist, $RuntimeBuild, $RuntimeSpec, $LauncherDist, $LauncherBuild, $LauncherSpec, $Staging, $VerifyDir
New-Item -ItemType Directory -Force $ReleaseDir | Out-Null
Invoke-PyInstaller `
    -Name "TerraSatchEdge" `
    -EntryPoint (Join-Path $Root "packaging\entrypoints\edge_cli.py") `
    -DistPath $RuntimeDist `
    -WorkPath $RuntimeBuild `
    -SpecPath $RuntimeSpec

$RuntimeDir = Join-Path $RuntimeDist "TerraSatchEdge"
if (-not (Test-Path -LiteralPath (Join-Path $RuntimeDir "TerraSatchEdge.exe"))) { throw "MSIX runtime executable was not built." }

Write-Host "[3/8] Staging optional RTL-SDR runtime" -ForegroundColor Cyan
$VendorRtlSdr = Join-Path $Root "packaging\windows\vendor\rtl-sdr"
if (Test-Path -LiteralPath (Join-Path $VendorRtlSdr "rtl_sdr.exe")) {
    $TargetTools = Join-Path $RuntimeDir "tools\rtl-sdr"
    New-Item -ItemType Directory -Force $TargetTools | Out-Null
    Copy-Item -Path (Join-Path $VendorRtlSdr "*") -Destination $TargetTools -Recurse -Force
    & $Python (Join-Path $Root "scripts\verify-rtlsdr-runtime.py") $TargetTools
    if ($LASTEXITCODE -ne 0) { throw "Bundled RTL-SDR runtime failed validation." }
} else {
    Write-Host "No staged RTL-SDR runtime found; MSIX will still support normal Edge pairing/inventory." -ForegroundColor Yellow
}

Write-Host "[4/8] Building Store launchers" -ForegroundColor Cyan
New-Item -ItemType Directory -Force $LauncherDist, $LauncherBuild, $LauncherSpec | Out-Null
foreach ($Launcher in @(
    @{ Name = "TerraSatchEdgeConsoleLauncher"; Entry = "edge_msix_console.py" },
    @{ Name = "TerraSatchEdgeAgentLauncher"; Entry = "edge_msix_agent.py" },
    @{ Name = "TerraSatchRadioLauncher"; Entry = "edge_msix_radio.py" }
)) {
    Invoke-PyInstaller `
        -Name $Launcher.Name `
        -EntryPoint (Join-Path $Root "packaging\entrypoints\$($Launcher.Entry)") `
        -DistPath $LauncherDist `
        -WorkPath (Join-Path $LauncherBuild $Launcher.Name) `
        -SpecPath $LauncherSpec `
        -OneFile
}

Write-Host "[5/8] Staging MSIX layout and assets" -ForegroundColor Cyan
New-Item -ItemType Directory -Force $Staging, (Join-Path $Staging "Edge"), (Join-Path $Staging "Assets") | Out-Null
Copy-Item -Path (Join-Path $RuntimeDir "*") -Destination (Join-Path $Staging "Edge") -Recurse -Force
foreach ($Name in @("TerraSatchEdgeConsoleLauncher", "TerraSatchEdgeAgentLauncher", "TerraSatchRadioLauncher")) {
    Copy-Item -LiteralPath (Join-Path $LauncherDist "$Name.exe") -Destination $Staging -Force
}

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
    if ($LASTEXITCODE -ne 0) { throw "MSIX asset generation failed with exit code $LASTEXITCODE." }
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

Write-Host "[6/8] Packing TerraSatch Edge MSIX" -ForegroundColor Cyan
Remove-Item -LiteralPath $Artifact -Force -ErrorAction SilentlyContinue
& $MakeAppx pack /d $Staging /p $Artifact /o
if ($LASTEXITCODE -ne 0) { throw "MakeAppx failed with exit code $LASTEXITCODE." }

Write-Host "[7/8] Signing or preparing Store upload package" -ForegroundColor Cyan
if ($StoreUpload) {
    Write-Host "Store-upload mode: MSIX remains unsigned locally for Microsoft Store certification/signing." -ForegroundColor Yellow
} else {
    if (-not $CertificateThumbprint) {
        throw "Local MSIX testing requires -CertificateThumbprint or TERRASATCH_MSIX_CERT_THUMBPRINT. Use -StoreUpload only after Partner Center identity is configured."
    }
    $CertificateThumbprint = ($CertificateThumbprint -replace "\s", "").ToUpperInvariant()
    $Certificate = Get-ChildItem Cert:\CurrentUser\My, Cert:\LocalMachine\My -ErrorAction SilentlyContinue |
        Where-Object { ($_.Thumbprint -replace "\s", "").ToUpperInvariant() -eq $CertificateThumbprint } |
        Select-Object -First 1
    if (-not $Certificate) { throw "MSIX signing certificate $CertificateThumbprint was not found." }
    if (-not $Certificate.HasPrivateKey) { throw "MSIX signing certificate does not expose a private key." }
    if ($Certificate.Subject -ne $Publisher) { throw "Manifest Publisher must exactly match certificate Subject. Manifest: $Publisher Certificate: $($Certificate.Subject)" }
    & $SignTool sign /v /fd SHA256 /sha1 $CertificateThumbprint $Artifact
    if ($LASTEXITCODE -ne 0) { throw "MSIX SignTool signing failed with exit code $LASTEXITCODE." }
    & $SignTool verify /pa /v $Artifact
    if ($LASTEXITCODE -ne 0) { throw "MSIX signature verification failed with exit code $LASTEXITCODE." }
}

Write-Host "[8/8] Verifying package structure and checksum" -ForegroundColor Cyan
New-Item -ItemType Directory -Force $VerifyDir | Out-Null
& $MakeAppx unpack /p $Artifact /d $VerifyDir /o
if ($LASTEXITCODE -ne 0) { throw "MakeAppx unpack verification failed with exit code $LASTEXITCODE." }
if (-not (Test-Path -LiteralPath (Join-Path $VerifyDir "AppxManifest.xml"))) { throw "MSIX verification did not recover AppxManifest.xml." }
foreach ($Required in @("TerraSatchEdgeConsoleLauncher.exe", "TerraSatchEdgeAgentLauncher.exe", "TerraSatchRadioLauncher.exe", "Edge\TerraSatchEdge.exe")) {
    if (-not (Test-Path -LiteralPath (Join-Path $VerifyDir $Required))) { throw "MSIX verification missing $Required." }
}
$Hash = Get-FileHash -LiteralPath $Artifact -Algorithm SHA256
Write-Host ""
Write-Host "Built: $Artifact" -ForegroundColor Green
Write-Host "Version: $MsixVersion"
Write-Host "Identity: $IdentityName"
Write-Host "Publisher: $Publisher"
Write-Host "SHA256: $($Hash.Hash)"
Write-Host "Startup: Edge agent enabled; radio task packaged but disabled until configured."
if ($StoreUpload) { Write-Host "Signing: Microsoft Store submission package (unsigned locally)" -ForegroundColor Yellow }
else { Write-Host "Signing: local development certificate $CertificateThumbprint" -ForegroundColor Green }
