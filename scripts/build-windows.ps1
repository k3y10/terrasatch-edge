$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$BuildVenv = Join-Path $Root ".build-venv"
$Vendor = Join-Path $Root "packaging\windows\vendor"
$Assets = Join-Path $Root "packaging\windows\assets"
$IconFile = Join-Path $Assets "TerraSatchEdge.ico"
$WinSW = Join-Path $Vendor "TerraSatchEdgeService.exe"
$WinSWUrl = "https://github.com/winsw/winsw/releases/download/v2.12.0/WinSW-x64.exe"
$DefaultSatchyIconSource = "https://www.terrasatch.com/terralisten-sasquatch.png"

New-Item -ItemType Directory -Force $Assets | Out-Null

if ($env:TERRASATCH_EDGE_ICON) {
    $SuppliedIcon = (Resolve-Path $env:TERRASATCH_EDGE_ICON).Path
    if ([System.IO.Path]::GetExtension($SuppliedIcon).ToLowerInvariant() -ne ".ico") {
        throw "TERRASATCH_EDGE_ICON must point to a Windows .ico file."
    }
    Copy-Item $SuppliedIcon $IconFile -Force
    Write-Host "Staged TerraSatch icon from: $SuppliedIcon" -ForegroundColor Green
}

Write-Host "[1/7] Preparing Python build environment"
if (-not (Test-Path $BuildVenv)) {
    py -3.12 -m venv $BuildVenv
}
$Python = Join-Path $BuildVenv "Scripts\python.exe"
& $Python -m pip install --upgrade pip
& $Python -m pip install -e ".[serial,usb,ui,build,dev]"

if (-not (Test-Path $IconFile)) {
    $SatchySource = $env:TERRASATCH_SATCHY_ICON_SOURCE
    if (-not $SatchySource) {
        $SatchySource = $DefaultSatchyIconSource
    }

    $IconSource = Join-Path $env:TEMP "TerraSatch-Satchy-icon-source.png"
    Remove-Item $IconSource -Force -ErrorAction SilentlyContinue

    if ($SatchySource -match '^https?://') {
        Write-Host "Downloading approved Satchy artwork: $SatchySource"
        Invoke-WebRequest -Uri $SatchySource -OutFile $IconSource
    } elseif (Test-Path $SatchySource) {
        Copy-Item (Resolve-Path $SatchySource).Path $IconSource -Force
        Write-Host "Using local Satchy artwork: $SatchySource"
    } else {
        throw "Satchy icon source was not found: $SatchySource"
    }

    $IconBuilder = @'
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

canvas_size = 1024
padding = 92
max_size = canvas_size - (padding * 2)
image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
canvas = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
x = (canvas_size - image.width) // 2
y = (canvas_size - image.height) // 2
canvas.alpha_composite(image, (x, y))
destination.parent.mkdir(parents=True, exist_ok=True)
canvas.save(
    destination,
    format="ICO",
    sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
)
'@

    & $Python -c $IconBuilder $IconSource $IconFile
    Remove-Item $IconSource -Force -ErrorAction SilentlyContinue
    Write-Host "Generated TerraSatch Edge Satchy icon: $IconFile" -ForegroundColor Green
}

if (-not (Test-Path $IconFile)) {
    throw "TerraSatchEdge.ico was not created. Branded Windows release builds require the Satchy icon."
}
if ((Get-Item $IconFile).Length -le 0) {
    throw "TerraSatchEdge.ico is empty. Branded Windows release builds require a valid icon."
}

Write-Host "[2/7] Running local tests"
& $Python -m pytest

Write-Host "[3/7] Building native Windows Edge bundle"
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue (Join-Path $Root "build")
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue (Join-Path $Root "dist")

$PyInstallerArgs = @(
    "--noconfirm",
    "--clean",
    "--onedir",
    "--name", "TerraSatchEdge",
    "--icon", $IconFile,
    "--collect-all", "uvicorn",
    "--collect-all", "fastapi"
)
Write-Host "Using TerraSatch Edge Satchy icon: $IconFile" -ForegroundColor Green
$PyInstallerArgs += "packaging\entrypoints\edge_cli.py"
& $Python -m PyInstaller @PyInstallerArgs

Write-Host "[4/7] Staging optional RTL-SDR runtime"
$VendorRtlSdr = Join-Path $Vendor "rtl-sdr"
$RtlSdrBundle = $env:TERRASATCH_RTLSDR_BUNDLE
if (-not $RtlSdrBundle -and (Test-Path (Join-Path $VendorRtlSdr "rtl_sdr.exe"))) {
    $RtlSdrBundle = $VendorRtlSdr
}

if ($RtlSdrBundle) {
    $RtlSdrBundle = (Resolve-Path $RtlSdrBundle).Path
    $RtlSdrExe = Join-Path $RtlSdrBundle "rtl_sdr.exe"
    if (-not (Test-Path $RtlSdrExe)) {
        throw "TERRASATCH_RTLSDR_BUNDLE must point to a folder containing rtl_sdr.exe."
    }
    $TargetTools = Join-Path $Root "dist\TerraSatchEdge\tools\rtl-sdr"
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $TargetTools
    New-Item -ItemType Directory -Force $TargetTools | Out-Null
    Copy-Item -Path (Join-Path $RtlSdrBundle "*") -Destination $TargetTools -Recurse -Force
    Write-Host "Bundled RTL-SDR runtime from: $RtlSdrBundle" -ForegroundColor Green
} else {
    Write-Host "No RTL-SDR runtime bundle supplied; PnP detection will work but active IQ probing will remain unavailable." -ForegroundColor Yellow
    Write-Host "To bundle one, set TERRASATCH_RTLSDR_BUNDLE to a trusted folder containing rtl_sdr.exe and its DLLs."
}

Write-Host "[5/7] Staging WinSW service wrapper"
New-Item -ItemType Directory -Force $Vendor | Out-Null
if (-not (Test-Path $WinSW)) {
    Invoke-WebRequest -Uri $WinSWUrl -OutFile $WinSW
}

Write-Host "[6/7] Locating Inno Setup compiler"
$Candidates = @()

$ISCCCommand = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if ($ISCCCommand) {
    $Candidates += $ISCCCommand.Source
}

$Candidates += @(
    "${env:ProgramFiles(x86)}\Inno Setup 7\ISCC.exe",
    "${env:ProgramFiles}\Inno Setup 7\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles}\Inno Setup 6\ISCC.exe",
    "${env:LOCALAPPDATA}\Programs\Inno Setup 7\ISCC.exe",
    "${env:LOCALAPPDATA}\Programs\Inno Setup 6\ISCC.exe",
    "${env:LOCALAPPDATA}\Inno Setup 7\ISCC.exe",
    "${env:LOCALAPPDATA}\Inno Setup 6\ISCC.exe"
)

$UninstallRoots = @(
    "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
    "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
    "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*"
)
foreach ($RegistryPath in $UninstallRoots) {
    Get-ItemProperty $RegistryPath -ErrorAction SilentlyContinue |
        Where-Object { $_.DisplayName -like "Inno Setup*" -and $_.InstallLocation } |
        ForEach-Object {
            $Candidates += (Join-Path $_.InstallLocation "ISCC.exe")
        }
}

$ISCC = $Candidates |
    Where-Object { $_ -and (Test-Path $_) } |
    Select-Object -Unique |
    Select-Object -First 1

if (-not $ISCC) {
    throw "Inno Setup is installed but ISCC.exe could not be located. Run: Get-ChildItem `$env:LOCALAPPDATA,`${env:ProgramFiles},`${env:ProgramFiles(x86)} -Filter ISCC.exe -Recurse -ErrorAction SilentlyContinue"
}
Write-Host "Using Inno Setup compiler: $ISCC"

Write-Host "[7/7] Building TerraSatch Edge installer"
New-Item -ItemType Directory -Force (Join-Path $Root "release") | Out-Null
& $ISCC "packaging\windows\TerraSatchEdge.iss"

$Installer = Join-Path $Root "release\TerraSatch-Edge-Setup-x64.exe"
if (-not (Test-Path $Installer)) {
    throw "Installer build completed without expected artifact: $Installer"
}
$Hash = Get-FileHash $Installer -Algorithm SHA256
Write-Host ""
Write-Host "Built: $Installer" -ForegroundColor Green
Write-Host "SHA256: $($Hash.Hash)"
