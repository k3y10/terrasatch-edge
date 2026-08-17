$ErrorActionPreference = "Continue"

$EdgeExe = Join-Path $PSScriptRoot "Edge\TerraSatchEdge.exe"
$LogDir = Join-Path $env:ProgramData "TerraSatch\Edge\state\logs"
New-Item -ItemType Directory -Force $LogDir | Out-Null

$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$TranscriptPath = Join-Path $LogDir "setup-$Stamp.log"
$TranscriptStarted = $false

try {
    Start-Transcript -Path $TranscriptPath -Force | Out-Null
    $TranscriptStarted = $true
} catch {
    Write-Warning "Could not start setup transcript: $($_.Exception.Message)"
}

Write-Host "TerraSatch Edge Setup" -ForegroundColor Green
Write-Host "This window will remain open when setup finishes so you can review the result."
Write-Host ""

if (-not (Test-Path $EdgeExe)) {
    Write-Host "TerraSatch Edge executable was not found at: $EdgeExe" -ForegroundColor Red
    $ExitCode = 2
} else {
    & $EdgeExe setup
    $ExitCode = $LASTEXITCODE
}

if ($TranscriptStarted) {
    try { Stop-Transcript | Out-Null } catch {}
}

Write-Host ""
if ($ExitCode -eq 0) {
    Write-Host "TerraSatch Edge setup completed." -ForegroundColor Green
} else {
    Write-Host "TerraSatch Edge setup exited with code $ExitCode." -ForegroundColor Yellow
}
Write-Host "Setup log: $TranscriptPath"
Write-Host ""
Read-Host "Press Enter to close"
exit $ExitCode
