param(
    [ValidateSet("console", "status", "doctor", "scan")]
    [string]$Command = "console"
)

$ErrorActionPreference = "Continue"
$EdgeExe = Join-Path $PSScriptRoot "Edge\TerraSatchEdge.exe"

Write-Host "TerraSatch Edge - $Command" -ForegroundColor Green
Write-Host ""

if (-not (Test-Path $EdgeExe)) {
    Write-Host "TerraSatch Edge executable was not found at: $EdgeExe" -ForegroundColor Red
    $ExitCode = 2
} else {
    & $EdgeExe $Command
    $ExitCode = $LASTEXITCODE
}

if ($Command -eq "console") {
    exit $ExitCode
}

Write-Host ""
Write-Host "Service state:" -ForegroundColor Cyan
Get-Service TerraSatchEdge -ErrorAction SilentlyContinue | Format-Table Status, Name, DisplayName -AutoSize
Write-Host "Logs: $env:ProgramData\TerraSatch\Edge\state\logs"
Write-Host ""
Read-Host "Press Enter to close"
exit $ExitCode
