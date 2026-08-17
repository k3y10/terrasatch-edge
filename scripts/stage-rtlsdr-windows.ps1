$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Target = Join-Path $Root "packaging\windows\vendor\rtl-sdr"

$MsysCandidates = @()
if ($env:MSYS2_ROOT) {
    $MsysCandidates += $env:MSYS2_ROOT
}
$MsysCandidates += @(
    "C:\msys64",
    (Join-Path $env:LOCALAPPDATA "Programs\MSYS2")
)

$MsysRoot = $MsysCandidates |
    Where-Object { $_ -and (Test-Path (Join-Path $_ "usr\bin\bash.exe")) } |
    Select-Object -First 1

if (-not $MsysRoot) {
    throw "MSYS2 was not found. Install it first with: winget install -e --id MSYS2.MSYS2"
}

$Bash = Join-Path $MsysRoot "usr\bin\bash.exe"
$UcrtBin = Join-Path $MsysRoot "ucrt64\bin"

Write-Host "Using MSYS2: $MsysRoot"
Write-Host "Installing/staging the UCRT64 rtl-sdr package..."
& $Bash -lc 'pacman -S --needed --noconfirm mingw-w64-ucrt-x86_64-rtl-sdr'
if ($LASTEXITCODE -ne 0) {
    throw "MSYS2 failed to install mingw-w64-ucrt-x86_64-rtl-sdr."
}

$RtlSdrExe = Join-Path $UcrtBin "rtl_sdr.exe"
if (-not (Test-Path $RtlSdrExe)) {
    throw "rtl_sdr.exe was not found after MSYS2 package installation: $RtlSdrExe"
}

$PackageLine = (& $Bash -lc 'pacman -Q mingw-w64-ucrt-x86_64-rtl-sdr').Trim()
$PackageVersion = ($PackageLine -split '\s+')[-1]

$LddOutput = & $Bash -lc 'PATH=/ucrt64/bin:/usr/bin ldd /ucrt64/bin/rtl_sdr.exe'
$DependencyNames = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
foreach ($Line in $LddOutput) {
    $MatchesFound = [regex]::Matches($Line, '/ucrt64/bin/([^\s]+\.dll)')
    foreach ($Match in $MatchesFound) {
        [void]$DependencyNames.Add($Match.Groups[1].Value)
    }
}

$Utilities = @(
    "rtl_sdr.exe",
    "rtl_test.exe",
    "rtl_fm.exe",
    "rtl_power.exe",
    "rtl_tcp.exe",
    "rtl_eeprom.exe",
    "rtl_biast.exe",
    "rtl_adsb.exe"
)

New-Item -ItemType Directory -Force $Target | Out-Null

foreach ($Name in $Utilities) {
    $Source = Join-Path $UcrtBin $Name
    if (Test-Path $Source) {
        Copy-Item $Source (Join-Path $Target $Name) -Force
    }
}

foreach ($Name in $DependencyNames) {
    $Source = Join-Path $UcrtBin $Name
    if (Test-Path $Source) {
        Copy-Item $Source (Join-Path $Target $Name) -Force
    }
}

$LicenseUrl = "https://raw.githubusercontent.com/osmocom/rtl-sdr/v2.0.2/COPYING"
try {
    Invoke-WebRequest -Uri $LicenseUrl -OutFile (Join-Path $Target "COPYING.rtl-sdr.txt")
} catch {
    Write-Warning "Could not download the upstream rtl-sdr license file: $($_.Exception.Message)"
}

$Provenance = @"
TerraSatch Edge RTL-SDR Windows staging provenance

MSYS2 package: mingw-w64-ucrt-x86_64-rtl-sdr
MSYS2 package version: $PackageVersion
MSYS2 package repository: ucrt64
Upstream project: https://gitea.osmocom.org/sdr/rtl-sdr/
Upstream GitHub mirror: https://github.com/osmocom/rtl-sdr
Upstream release family: v2.0.2
License: GPL-2.0-or-later

This folder was staged locally from the installed MSYS2 package. Review redistribution and source/license obligations before publishing the containing TerraSatch installer.
"@
$Provenance | Set-Content -Path (Join-Path $Target "PROVENANCE.txt") -Encoding UTF8

if (-not (Test-Path (Join-Path $Target "rtl_sdr.exe"))) {
    throw "RTL-SDR staging completed without rtl_sdr.exe."
}

Write-Host ""
Write-Host "RTL-SDR runtime staged at: $Target" -ForegroundColor Green
Write-Host "Package: $PackageLine"
Write-Host "Dependencies copied: $($DependencyNames.Count)"
Write-Host ""
Write-Host "Next: .\scripts\build-windows.ps1"
