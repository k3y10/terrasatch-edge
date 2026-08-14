$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Prefix = if ($env:TERRASATCH_EDGE_PREFIX) { $env:TERRASATCH_EDGE_PREFIX } else { Join-Path $env:LOCALAPPDATA "TerraSatchEdge" }
$Venv = Join-Path $Prefix "venv"

$python = Get-Command py -ErrorAction SilentlyContinue
if ($python) {
    & py -3.12 -m venv $Venv
} else {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) { throw "Python 3.12+ is required." }
    & python -m venv $Venv
}

$VenvPython = Join-Path $Venv "Scripts\python.exe"
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install "$Root[serial,usb,ui]"

$Edge = Join-Path $Venv "Scripts\terrasatch-edge.exe"
Write-Host ""
Write-Host "TerraSatch Edge installed." -ForegroundColor Green
Write-Host "Run:"
Write-Host "  $Edge setup"
Write-Host "  $Edge doctor"
