$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$BuildVenv = Join-Path $Root ".build-venv"
$Vendor = Join-Path $Root "packaging\windows\vendor"
$WinSW = Join-Path $Vendor "TerraSatchEdgeService.exe"
$WinSWUrl = "https://github.com/winsw/winsw/releases/download/v2.12.0/WinSW-x64.exe"

Write-Host "[1/7] Preparing Python build environment"
if (-not (Test-Path $BuildVenv)) {
    py -3.12 -m venv $BuildVenv
}
$Python = Join-Path $BuildVenv "Scripts\python.exe"
& $Python -m pip install --upgrade pip
& $Python -m pip install -e ".[serial,usb,ui,build,dev]"

Write-Host "[2/7] Running local tests"
& $Python -m pytest

Write-Host "[3/7] Building native Windows Edge bundle"
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue (Join-Path $Root "build")
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue (Join-Path $Root "dist")
& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --name TerraSatchEdge `
    --collect-all uvicorn `
    --collect-all fastapi `
    "packaging\entrypoints\edge_cli.py"

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
