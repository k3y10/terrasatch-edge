$ErrorActionPreference = "Stop"
$Wrapper = Join-Path $PSScriptRoot "TerraSatchRadioService.exe"
$Existing = Get-Service TerraSatchRadio -ErrorAction SilentlyContinue
if (-not $Existing) {
    & $Wrapper install
    if ($LASTEXITCODE -ne 0) { throw "Radio service installation failed: $LASTEXITCODE" }
}
# Installation never starts RX. Existing SCM start mode is preserved on upgrade.
Write-Host "Radio service installed. Configure targets, then enable/start TerraSatchRadio explicitly."
