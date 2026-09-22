[CmdletBinding()]
param(
    [switch]$Install,
    [switch]$KeepCertificate,
    [switch]$SkipRtlSdrStage
)

$ErrorActionPreference = "Stop"

if ($env:GITHUB_ACTIONS -eq "true") {
    throw "qa-windows-msix-local.ps1 is intentionally local-only. Do not run it in GitHub Actions."
}

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python launcher 'py' was not found. Install Python 3.12 before running local QA."
}

$ReleaseDir = Join-Path $Root "release"
New-Item -ItemType Directory -Force $ReleaseDir | Out-Null

$Version = (py -3.12 -c "import tomllib, pathlib; print(tomllib.loads(pathlib.Path('pyproject.toml').read_text())['project']['version'])").Trim()
if ($LASTEXITCODE -ne 0 -or -not $Version) {
    throw "Could not resolve the TerraSatch Edge version from pyproject.toml."
}

$Artifact = Join-Path $ReleaseDir "TerraSatch-Edge_${Version}_x64.msix"
$CertificatePath = Join-Path $ReleaseDir "TerraSatch-MSIX-LocalQA.cer"
$VerifyManifest = Join-Path $ReleaseDir "msix-verify\AppxManifest.xml"

$QaStateRoot = Join-Path $env:TEMP ("terrasatch-edge-qa-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force $QaStateRoot | Out-Null

$PreviousApiUrl = $env:TERRASATCH_EDGE_API_URL
$PreviousApiKey = $env:TERRASATCH_EDGE_API_KEY
$PreviousConfigDir = $env:TERRASATCH_EDGE_CONFIG_DIR
$PreviousStateDir = $env:TERRASATCH_EDGE_STATE_DIR
$PreviousMsixThumbprint = $env:TERRASATCH_MSIX_CERT_THUMBPRINT

$env:TERRASATCH_EDGE_API_URL = "http://127.0.0.1:18000"
Remove-Item Env:TERRASATCH_EDGE_API_KEY -ErrorAction SilentlyContinue
$env:TERRASATCH_EDGE_CONFIG_DIR = Join-Path $QaStateRoot "config"
$env:TERRASATCH_EDGE_STATE_DIR = Join-Path $QaStateRoot "state"

$Cert = $null
$TrustedCopy = $null

function Resolve-SignTool {
    $Command = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($Command) { return $Command.Source }

    $WindowsKitRoot = "C:\Program Files (x86)\Windows Kits\10\bin"
    if (-not (Test-Path -LiteralPath $WindowsKitRoot)) {
        throw "Windows SDK signing tools were not found."
    }

    $Resolved = Get-ChildItem -LiteralPath $WindowsKitRoot -Filter signtool.exe -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match "\\x64\\signtool\.exe$" } |
        Sort-Object FullName -Descending |
        Select-Object -First 1 -ExpandProperty FullName

    if (-not $Resolved) { throw "signtool.exe was not found under the Windows SDK." }
    return $Resolved
}

try {
    Write-Host "[1/8] Parsing Windows release PowerShell" -ForegroundColor Cyan
    foreach ($ScriptPath in @(
        (Join-Path $Root "scripts\build-windows-msix.ps1"),
        (Join-Path $Root "scripts\install-windows-msix-dev.ps1")
    )) {
        $ParseTokens = $null
        $ParseErrors = $null
        [System.Management.Automation.Language.Parser]::ParseFile(
            $ScriptPath,
            [ref]$ParseTokens,
            [ref]$ParseErrors
        ) | Out-Null
        if ($ParseErrors.Count -ne 0) {
            $Details = ($ParseErrors | ForEach-Object { $_.Message }) -join "; "
            throw "PowerShell parse validation failed for ${ScriptPath}: $Details"
        }
    }

    Write-Host "[2/8] Checking pull-request diff whitespace" -ForegroundColor Cyan
    $MergeBase = (git merge-base HEAD origin/main).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $MergeBase) {
        throw "Could not resolve merge-base with origin/main. Run 'git fetch origin main' and retry."
    }
    git diff --check "$MergeBase...HEAD"
    if ($LASTEXITCODE -ne 0) { throw "git diff --check failed for the branch diff." }

    if (-not $SkipRtlSdrStage) {
        Write-Host "[3/8] Staging and validating RTL-SDR runtime" -ForegroundColor Cyan
        & (Join-Path $Root "scripts\stage-rtlsdr-windows.ps1")
        if ($LASTEXITCODE -ne 0) { throw "RTL-SDR staging failed." }
    } else {
        Write-Host "[3/8] RTL-SDR staging intentionally skipped" -ForegroundColor Yellow
    }

    Write-Host "[4/8] Creating short-lived local MSIX QA certificate" -ForegroundColor Cyan
    $Cert = New-SelfSignedCertificate `
        -Type CodeSigningCert `
        -Subject "CN=TerraSatch Inc." `
        -FriendlyName "TerraSatch Edge Local MSIX QA" `
        -CertStoreLocation "Cert:\CurrentUser\My" `
        -KeyExportPolicy Exportable `
        -KeyLength 3072 `
        -HashAlgorithm SHA256 `
        -NotAfter (Get-Date).AddDays(2)

    Export-Certificate -Cert $Cert -FilePath $CertificatePath | Out-Null
    $TrustedCopy = Import-Certificate `
        -FilePath $CertificatePath `
        -CertStoreLocation "Cert:\CurrentUser\TrustedPeople"

    $env:TERRASATCH_MSIX_CERT_THUMBPRINT = $Cert.Thumbprint

    Write-Host "[5/8] Building development-signed MSIX and running repository tests" -ForegroundColor Cyan
    & (Join-Path $Root "scripts\build-windows-msix.ps1")
    if ($LASTEXITCODE -ne 0) { throw "MSIX build failed." }

    $BuildPython = Join-Path $Root ".build-venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $BuildPython)) {
        throw "MSIX build environment was not created at $BuildPython."
    }

    Write-Host "[6/8] Ruff and compile/import QA" -ForegroundColor Cyan
    & $BuildPython -m ruff check src tests
    if ($LASTEXITCODE -ne 0) { throw "Ruff failed." }
    & $BuildPython -m compileall -q src tests
    if ($LASTEXITCODE -ne 0) { throw "compileall failed." }
    & $BuildPython -c "import terrasatch_edge; from terrasatch_edge.cli import app; print(f'terrasatch-edge {terrasatch_edge.__version__} import OK')"
    if ($LASTEXITCODE -ne 0) { throw "Import smoke failed." }

    Write-Host "[7/8] Validating unpacked Store-compatible manifest" -ForegroundColor Cyan
    if (-not (Test-Path -LiteralPath $VerifyManifest)) {
        throw "Expected unpacked manifest was not found: $VerifyManifest"
    }
    [xml]$Manifest = Get-Content -LiteralPath $VerifyManifest
    $Ns = New-Object System.Xml.XmlNamespaceManager($Manifest.NameTable)
    $Ns.AddNamespace("f", "http://schemas.microsoft.com/appx/manifest/foundation/windows10")
    $Ns.AddNamespace("desktop", "http://schemas.microsoft.com/appx/manifest/desktop/windows10")
    $Ns.AddNamespace("rescap", "http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities")

    $Identity = $Manifest.SelectSingleNode("/f:Package/f:Identity", $Ns)
    if ($Identity.Name -ne "TerraSatch.Edge.Dev") { throw "Unexpected local QA identity: $($Identity.Name)" }
    if ($Identity.Publisher -ne "CN=TerraSatch Inc.") { throw "Unexpected local QA publisher: $($Identity.Publisher)" }

    $RuntimeVersionParts = @($Version.Split(".") | ForEach-Object { [int]$_ })
    $ExpectedMsixVersion = "$($RuntimeVersionParts[0] + 1).$($RuntimeVersionParts[1]).$($RuntimeVersionParts[2]).0"
    if ($Identity.Version -ne $ExpectedMsixVersion) {
        throw "Unexpected MSIX package version: $($Identity.Version). Expected $ExpectedMsixVersion for Edge $Version."
    }

    $Startup = $Manifest.SelectNodes("//desktop:Extension[@Category='windows.startupTask']/desktop:StartupTask", $Ns)
    if ($Startup.Count -ne 2) { throw "Expected two startup tasks; found $($Startup.Count)." }
    $EdgeTask = @($Startup | Where-Object { $_.TaskId -eq "TerraSatchEdgeAgent" })
    $RadioTask = @($Startup | Where-Object { $_.TaskId -eq "TerraSatchRadio" })
    if ($EdgeTask.Count -ne 1 -or $EdgeTask[0].Enabled -ne "true") { throw "TerraSatchEdgeAgent must default enabled." }
    if ($RadioTask.Count -ne 1 -or $RadioTask[0].Enabled -ne "false") { throw "TerraSatchRadio must default disabled." }

    $Capabilities = @($Manifest.SelectNodes("//rescap:Capability", $Ns) | ForEach-Object { $_.Name })
    if ("runFullTrust" -notin $Capabilities) { throw "runFullTrust capability missing." }
    if ("packagedServices" -in $Capabilities -or "localSystemServices" -in $Capabilities) {
        throw "Store-compatible MSIX must not declare Windows service restricted capabilities."
    }

    Write-Host "[8/8] Verifying exact package signature and SHA-256" -ForegroundColor Cyan
    if (-not (Test-Path -LiteralPath $Artifact)) { throw "Expected MSIX was not created: $Artifact" }
    $SignTool = Resolve-SignTool
    & $SignTool verify /pa /v $Artifact
    if ($LASTEXITCODE -ne 0) { throw "MSIX signature verification failed." }

    $Hash = Get-FileHash -LiteralPath $Artifact -Algorithm SHA256
    Write-Host ""
    Write-Host "PASS: TerraSatch Edge Windows MSIX local QA" -ForegroundColor Green
    Write-Host "Artifact: $Artifact"
    Write-Host "Version: $Version"
    Write-Host "SHA256: $($Hash.Hash)"
    Write-Host "GitHub Actions used: no"

    if ($Install) {
        Write-Host ""
        Write-Host "Running local install/startup-task validation..." -ForegroundColor Cyan
        & (Join-Path $Root "scripts\install-windows-msix-dev.ps1") `
            -MsixPath $Artifact `
            -CertificatePath $CertificatePath
    }
}
finally {
    if ($null -eq $PreviousApiUrl) { Remove-Item Env:TERRASATCH_EDGE_API_URL -ErrorAction SilentlyContinue }
    else { $env:TERRASATCH_EDGE_API_URL = $PreviousApiUrl }

    if ($null -eq $PreviousApiKey) { Remove-Item Env:TERRASATCH_EDGE_API_KEY -ErrorAction SilentlyContinue }
    else { $env:TERRASATCH_EDGE_API_KEY = $PreviousApiKey }

    if ($null -eq $PreviousConfigDir) { Remove-Item Env:TERRASATCH_EDGE_CONFIG_DIR -ErrorAction SilentlyContinue }
    else { $env:TERRASATCH_EDGE_CONFIG_DIR = $PreviousConfigDir }

    if ($null -eq $PreviousStateDir) { Remove-Item Env:TERRASATCH_EDGE_STATE_DIR -ErrorAction SilentlyContinue }
    else { $env:TERRASATCH_EDGE_STATE_DIR = $PreviousStateDir }

    if ($null -eq $PreviousMsixThumbprint) { Remove-Item Env:TERRASATCH_MSIX_CERT_THUMBPRINT -ErrorAction SilentlyContinue }
    else { $env:TERRASATCH_MSIX_CERT_THUMBPRINT = $PreviousMsixThumbprint }

    Remove-Item -LiteralPath $QaStateRoot -Recurse -Force -ErrorAction SilentlyContinue

    if (-not $KeepCertificate) {
        if ($TrustedCopy) {
            Remove-Item -LiteralPath ("Cert:\CurrentUser\TrustedPeople\" + $TrustedCopy.Thumbprint) -Force -ErrorAction SilentlyContinue
        }
        if ($Cert) {
            Remove-Item -LiteralPath ("Cert:\CurrentUser\My\" + $Cert.Thumbprint) -Force -ErrorAction SilentlyContinue
        }
    } elseif ($Cert) {
        Write-Host "Kept local QA certificate: $($Cert.Thumbprint)" -ForegroundColor Yellow
    }
}
