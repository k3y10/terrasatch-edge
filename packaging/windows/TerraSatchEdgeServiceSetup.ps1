$ErrorActionPreference = "Stop"

$Wrapper = Join-Path $PSScriptRoot "TerraSatchEdgeService.exe"
$ServiceName = "TerraSatchEdge"

if (-not (Test-Path $Wrapper)) {
    throw "TerraSatch Edge service wrapper was not found at: $Wrapper"
}

$ExistingService = Get-Service $ServiceName -ErrorAction SilentlyContinue
if ($ExistingService) {
    Write-Host "Existing TerraSatch Edge service detected; refreshing service registration."

    if ($ExistingService.Status -ne "Stopped") {
        & $Wrapper stop
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Service stop returned exit code $LASTEXITCODE; continuing with refresh."
        }
    }

    & $Wrapper uninstall
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Service uninstall returned exit code $LASTEXITCODE; waiting for Windows service state."
    }

    $Deadline = (Get-Date).AddSeconds(15)
    while ((Get-Service $ServiceName -ErrorAction SilentlyContinue) -and (Get-Date) -lt $Deadline) {
        Start-Sleep -Milliseconds 300
    }

    if (Get-Service $ServiceName -ErrorAction SilentlyContinue) {
        throw "Existing TerraSatch Edge service could not be removed during upgrade."
    }
}

& $Wrapper install
if ($LASTEXITCODE -ne 0) {
    throw "TerraSatch Edge service install failed with exit code $LASTEXITCODE."
}

& $Wrapper start
if ($LASTEXITCODE -ne 0) {
    throw "TerraSatch Edge service start failed with exit code $LASTEXITCODE."
}

$Service = Get-Service $ServiceName -ErrorAction Stop
if ($Service.Status -ne "Running") {
    $Service.WaitForStatus("Running", [TimeSpan]::FromSeconds(15))
    $Service.Refresh()
}

Write-Host "TerraSatch Edge service is $($Service.Status)."
