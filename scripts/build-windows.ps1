[CmdletBinding()]
param(
    [switch]$AllowUnsigned
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$BuildVenv = Join-Path $Root ".build-venv"
$Vendor = Join-Path $Root "packaging\windows\vendor"
$Assets = Join-Path $Root "packaging\windows\assets"
$IconFile = Join-Path $Assets "TerraSatchEdge.ico"
$WinSW = Join-Path $Vendor "TerraSatchEdgeService.exe"
$WinSWUrl = "https://github.com/winsw/winsw/releases/download/v2.12.0/WinSW-x64.exe"
$DefaultSatchyIconSource = Join-Path $Root "src\terrasatch_edge\assets\terrasatch-logo.webp"
$CertificateThumbprint = ($env:TERRASATCH_CODESIGN_CERT_THUMBPRINT -replace '\s', '').ToUpperInvariant()
$TimestampUrl = if ($env:TERRASATCH_CODESIGN_TIMESTAMP_URL) {
    $env:TERRASATCH_CODESIGN_TIMESTAMP_URL
} else {
    "http://timestamp.digicert.com"
}
$SignTool = $null
$CertificateStore = $null

function Resolve-SignTool {
    $Candidates = @()
    if ($env:TERRASATCH_SIGNTOOL_PATH) {
        $Candidates += $env:TERRASATCH_SIGNTOOL_PATH
    }

    $Command = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($Command) {
        $Candidates += $Command.Source
    }

    $WindowsKitRoot = "C:\Program Files (x86)\Windows Kits\10\bin"
    if (Test-Path -LiteralPath $WindowsKitRoot) {
        $Candidates += Get-ChildItem -LiteralPath $WindowsKitRoot -Filter signtool.exe -Recurse -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match '\\x64\\signtool\.exe$' } |
            Sort-Object FullName -Descending |
            Select-Object -ExpandProperty FullName
    }

    $Resolved = $Candidates |
        Where-Object { $_ -and (Test-Path -LiteralPath $_) } |
        Select-Object -Unique |
        Select-Object -First 1
    if (-not $Resolved) {
        throw "A trusted release certificate was selected, but signtool.exe was not found. Install the Windows SDK Signing Tools or set TERRASATCH_SIGNTOOL_PATH."
    }
    return (Resolve-Path -LiteralPath $Resolved).Path
}

function Resolve-CodeSigningCertificate {
    param([Parameter(Mandatory = $true)][string]$Thumbprint)

    foreach ($Store in @("CurrentUser", "LocalMachine")) {
        $CertificatePath = "Cert:\$Store\My\$Thumbprint"
        if (-not (Test-Path -LiteralPath $CertificatePath)) {
            continue
        }

        $Certificate = Get-Item -LiteralPath $CertificatePath
        if (-not $Certificate.HasPrivateKey) {
            throw "The TerraSatch code-signing certificate does not expose its private key."
        }
        if ($Certificate.NotBefore -gt (Get-Date) -or $Certificate.NotAfter -le (Get-Date)) {
            throw "The TerraSatch code-signing certificate is not currently valid."
        }
        if (-not ($Certificate.EnhancedKeyUsageList.ObjectId -contains "1.3.6.1.5.5.7.3.3")) {
            throw "The selected certificate is not valid for Code Signing."
        }
        return [PSCustomObject]@{ Certificate = $Certificate; Store = $Store }
    }

    throw "The certificate in TERRASATCH_CODESIGN_CERT_THUMBPRINT was not found in the CurrentUser or LocalMachine Personal store."
}

function Assert-AuthenticodeSignature {
    param([Parameter(Mandatory = $true)][string]$Path)

    $Signature = Get-AuthenticodeSignature -LiteralPath $Path
    if ($Signature.Status -ne "Valid") {
        throw "Authenticode verification failed for $Path. Status: $($Signature.Status). $($Signature.StatusMessage)"
    }
    if (($Signature.SignerCertificate.Thumbprint -replace '\s', '').ToUpperInvariant() -ne $CertificateThumbprint) {
        throw "Authenticode verification used an unexpected signer for $Path."
    }
    Write-Host "Verified TerraSatch Authenticode signature: $Path" -ForegroundColor Green
}

function Invoke-AuthenticodeSign {
    param([Parameter(Mandatory = $true)][string]$Path)

    $Arguments = @(
        "sign", "/v", "/fd", "SHA256",
        "/tr", $TimestampUrl, "/td", "SHA256",
        "/sha1", $CertificateThumbprint,
        "/d", "TerraSatch Edge",
        "/du", "https://www.terrasatch.com/edge"
    )
    if ($CertificateStore -eq "LocalMachine") {
        $Arguments += "/sm"
    }
    $Arguments += $Path

    & $SignTool @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Authenticode signing failed for $Path with exit code $LASTEXITCODE."
    }
    Assert-AuthenticodeSignature -Path $Path
}

if ($CertificateThumbprint) {
    $SigningIdentity = Resolve-CodeSigningCertificate -Thumbprint $CertificateThumbprint
    $CertificateStore = $SigningIdentity.Store
    $SignTool = Resolve-SignTool
    Write-Host "Trusted signing enabled for: $($SigningIdentity.Certificate.Subject)" -ForegroundColor Green
} elseif (-not $AllowUnsigned) {
    throw "Trusted Authenticode signing is required. Install the TerraSatch code-signing certificate, set TERRASATCH_CODESIGN_CERT_THUMBPRINT, and run again. Use -AllowUnsigned only for local QA builds that will not be published."
} else {
    Write-Host "Unsigned local QA build explicitly allowed. Do not publish this artifact." -ForegroundColor Yellow
}

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
if ($LASTEXITCODE -ne 0) {
    throw "pip upgrade failed with exit code $LASTEXITCODE."
}
& $Python -m pip install -e ".[serial,usb,ui,build,dev]"
if ($LASTEXITCODE -ne 0) {
    throw "TerraSatch Edge build dependency installation failed with exit code $LASTEXITCODE."
}

if (-not $env:TERRASATCH_EDGE_ICON) {
    $SatchySource = $env:TERRASATCH_SATCHY_ICON_SOURCE
    if (-not $SatchySource) {
        $SatchySource = $DefaultSatchyIconSource
    }

    $IconSource = Join-Path $env:TEMP "TerraSatch-Satchy-icon-source.png"
    $IconBuilderPath = Join-Path $env:TEMP "TerraSatch-build-satchy-icon.py"
    Remove-Item $IconSource -Force -ErrorAction SilentlyContinue
    Remove-Item $IconBuilderPath -Force -ErrorAction SilentlyContinue

    if ($SatchySource -match '^https?://') {
        Write-Host "Downloading approved Satchy artwork: $SatchySource"
        Invoke-WebRequest -Uri $SatchySource -OutFile $IconSource
    } elseif (Test-Path $SatchySource) {
        Copy-Item (Resolve-Path $SatchySource).Path $IconSource -Force
        Write-Host "Using local Satchy artwork: $SatchySource"
    } else {
        throw "Satchy icon source was not found: $SatchySource"
    }

    if (-not (Test-Path $IconSource) -or (Get-Item $IconSource).Length -le 0) {
        throw "Satchy artwork could not be staged from: $SatchySource"
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

    Set-Content -Path $IconBuilderPath -Value $IconBuilder -Encoding UTF8

    try {
        & $Python $IconBuilderPath $IconSource $IconFile
        if ($LASTEXITCODE -ne 0) {
            throw "Satchy icon conversion failed with exit code $LASTEXITCODE."
        }
    } finally {
        Remove-Item $IconBuilderPath -Force -ErrorAction SilentlyContinue
        Remove-Item $IconSource -Force -ErrorAction SilentlyContinue
    }

    if (-not (Test-Path $IconFile)) {
        throw "TerraSatchEdge.ico was not created. Branded Windows release builds require the Satchy icon."
    }
    if ((Get-Item $IconFile).Length -le 0) {
        throw "TerraSatchEdge.ico is empty. Branded Windows release builds require a valid icon."
    }

    Write-Host "Generated TerraSatch Edge Satchy icon: $IconFile" -ForegroundColor Green
}

if (-not (Test-Path $IconFile)) {
    throw "TerraSatchEdge.ico was not created. Branded Windows release builds require the Satchy icon."
}
if ((Get-Item $IconFile).Length -le 0) {
    throw "TerraSatchEdge.ico is empty. Branded Windows release builds require a valid icon."
}

Write-Host "[2/7] Running local tests"
$PytestBaseTemp = Join-Path $Root ".pytest-tmp-build"
Remove-Item -LiteralPath $PytestBaseTemp -Recurse -Force -ErrorAction SilentlyContinue
try {
    & $Python -m pytest --basetemp $PytestBaseTemp
    if ($LASTEXITCODE -ne 0) {
        throw "TerraSatch Edge tests failed with exit code $LASTEXITCODE."
    }
} finally {
    Remove-Item -LiteralPath $PytestBaseTemp -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "[3/7] Building native Windows Edge bundle"
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue (Join-Path $Root "build")
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue (Join-Path $Root "dist")

$PyInstallerArgs = @(
    "--noconfirm",
    "--clean",
    "--onedir",
    "--name", "TerraSatchEdge",
    "--icon", $IconFile,
    "--collect-data", "terrasatch_edge",
    "--collect-all", "uvicorn",
    "--collect-all", "fastapi"
)
Write-Host "Using TerraSatch Edge Satchy icon: $IconFile" -ForegroundColor Green
$PyInstallerArgs += "packaging\entrypoints\edge_cli.py"
& $Python -m PyInstaller @PyInstallerArgs
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE."
}

$EdgeExecutable = Join-Path $Root "dist\TerraSatchEdge\TerraSatchEdge.exe"
if (-not (Test-Path -LiteralPath $EdgeExecutable)) {
    throw "PyInstaller completed without the expected executable: $EdgeExecutable"
}
if ($SignTool) {
    Invoke-AuthenticodeSign -Path $EdgeExecutable
}

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
if ($SignTool) {
    Invoke-AuthenticodeSign -Path $WinSW
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
$InnoArguments = @()
if ($SignTool) {
    $InnoQuote = '$q'
    $InnoFile = '$f'
    $MachineStoreArgument = if ($CertificateStore -eq "LocalMachine") { "/sm " } else { "" }
    $InnoSignCommand = "$InnoQuote$SignTool$InnoQuote sign /v /fd SHA256 /tr $InnoQuote$TimestampUrl$InnoQuote /td SHA256 /sha1 $CertificateThumbprint $MachineStoreArgument/d ${InnoQuote}TerraSatch Edge${InnoQuote} /du ${InnoQuote}https://www.terrasatch.com/edge${InnoQuote} $InnoFile"
    $InnoArguments += "/DSignedRelease=1"
    $InnoArguments += "/STerraSatch=$InnoSignCommand"
}
$InnoArguments += "packaging\windows\TerraSatchEdge.iss"
& $ISCC @InnoArguments
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup failed with exit code $LASTEXITCODE."
}

$Installer = Join-Path $Root "release\TerraSatch-Edge-Setup-x64.exe"
if (-not (Test-Path $Installer)) {
    throw "Installer build completed without expected artifact: $Installer"
}
$Hash = Get-FileHash $Installer -Algorithm SHA256
if ($SignTool) {
    Assert-AuthenticodeSignature -Path $Installer
} else {
    $UnsignedStatus = (Get-AuthenticodeSignature -LiteralPath $Installer).Status
    if ($UnsignedStatus -ne "NotSigned") {
        throw "Expected an unsigned QA installer, but Authenticode reported: $UnsignedStatus"
    }
}
Write-Host ""
Write-Host "Built: $Installer" -ForegroundColor Green
Write-Host "SHA256: $($Hash.Hash)"
