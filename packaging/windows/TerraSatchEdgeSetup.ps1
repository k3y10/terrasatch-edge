$ErrorActionPreference = "Continue"

$EdgeExe = Join-Path $PSScriptRoot "Edge\TerraSatchEdge.exe"
$LogDir = Join-Path $env:ProgramData "TerraSatch\Edge\state\logs"
$ProductionApiUrl = "https://api.terrasatch.com"
$SelectedApiUrl = $ProductionApiUrl
if (-not [string]::IsNullOrWhiteSpace($env:TERRASATCH_EDGE_API_URL)) {
    $SelectedApiUrl = $env:TERRASATCH_EDGE_API_URL.Trim().TrimEnd('/')
}

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

Write-Host "TerraSatch Edge" -ForegroundColor Green
Write-Host "Checking this device registration..."
Write-Host "API target: $SelectedApiUrl"
Write-Host ""

if (-not (Test-Path $EdgeExe)) {
    Write-Host "TerraSatch Edge executable was not found at: $EdgeExe" -ForegroundColor Red
    $ExitCode = 2
} else {
    try {
        $VersionText = (& $EdgeExe --version 2>$null | Out-String).Trim()
        if ($VersionText) {
            Write-Host "Runtime: $VersionText"
            Write-Host ""
        }
    } catch {
        Write-Host "Runtime version could not be read: $($_.Exception.Message)" -ForegroundColor Yellow
    }

    $Registered = $false
    $Status = $null

    try {
        $StatusText = (& $EdgeExe status --json 2>$null | Out-String).Trim()
        if ($StatusText) {
            $Status = $StatusText | ConvertFrom-Json
            $Registered = (
                $Status.authenticated -eq $true -and
                -not [string]::IsNullOrWhiteSpace([string]$Status.device_id) -and
                -not [string]::IsNullOrWhiteSpace([string]$Status.site_id)
            )
        }
    } catch {
        Write-Host "Existing registration could not be verified: $($_.Exception.Message)" -ForegroundColor Yellow
        $Registered = $false
    }

    if ($Registered) {
        $DisplaySite = [string]$Status.site_name
        if ([string]::IsNullOrWhiteSpace($DisplaySite)) {
            $DisplaySite = [string]$Status.site_id
        }
        Write-Host "Registration verified." -ForegroundColor Green
        Write-Host "Device: $($Status.device_id)"
        Write-Host "Site: $DisplaySite"
        Write-Host "API: $($Status.api_url)"
        if (-not [string]::IsNullOrWhiteSpace([string]$Status.api_url) -and
            ([string]$Status.api_url).TrimEnd('/') -ne $SelectedApiUrl) {
            Write-Host "This saved registration targets a different API than the current installer environment." -ForegroundColor Yellow
            Write-Host "Saved: $($Status.api_url)" -ForegroundColor Yellow
            Write-Host "Installer environment: $SelectedApiUrl" -ForegroundColor Yellow
            Write-Host "The existing registration is being preserved. Run TerraSatch Edge Setup again after changing environments." -ForegroundColor Yellow
        }
        Write-Host ""
        Write-Host "This Edge node is already paired. Existing registration was preserved."
        $ExitCode = 0
    } else {
        Write-Host "This device is new, unregistered, or its saved credential is no longer valid." -ForegroundColor Yellow
        Write-Host "Starting TerraSatch Edge pairing..."
        Write-Host ""
        & $EdgeExe setup --api-url $SelectedApiUrl
        $ExitCode = $LASTEXITCODE
    }
}

if ($TranscriptStarted) {
    try { Stop-Transcript | Out-Null } catch {}
}

Write-Host ""
if ($ExitCode -eq 0) {
    Write-Host "TerraSatch Edge is ready." -ForegroundColor Green
} else {
    Write-Host "TerraSatch Edge setup/verification exited with code $ExitCode." -ForegroundColor Yellow
}
Write-Host "Setup log: $TranscriptPath"
Write-Host ""
Read-Host "Press Enter to close"
exit $ExitCode
