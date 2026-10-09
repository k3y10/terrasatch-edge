# Local-only inspection and installation gate for a TerraSatch Edge v0.2.9 beta MSIX.
# Does not build, sign, publish, launch, or call GitHub Actions.
[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = "Medium")]
param(
    [Parameter(Mandatory = $true)][string]$MsixPath,
    [string]$CertificatePath,
    [string]$ExpectedThumbprint,
    [string]$ExpectedSha256,
    [switch]$Install
)

$ErrorActionPreference = "Stop"
$IdentityName = "TerraSatch.Edge.Dev"
$PublisherName = "CN=TerraSatch Inc."
$AllowedVersions = @("1.2.9.0", "0.2.9.0")

function Normalize-Hex {
    param([Parameter(Mandatory = $true)][string]$Value)
    return ($Value -replace "[^0-9a-fA-F]", "").ToUpperInvariant()
}

function Resolve-SignTool {
    $Command = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($Command) { return $Command.Source }
    $SdkRoot = "C:\Program Files (x86)\Windows Kits\10\bin"
    if (-not (Test-Path -LiteralPath $SdkRoot)) {
        throw "Windows SDK SignTool is required for timestamp verification."
    }
    $Tool = Get-ChildItem -LiteralPath $SdkRoot -Filter signtool.exe -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match "\\x64\\signtool\.exe$" } |
        Sort-Object FullName -Descending |
        Select-Object -First 1 -ExpandProperty FullName
    if (-not $Tool) { throw "Windows SDK x64 signtool.exe was not found." }
    return $Tool
}

$MsixPath = (Resolve-Path -LiteralPath $MsixPath).Path
if ([IO.Path]::GetExtension($MsixPath) -ne ".msix") {
    throw "Expected a .msix file, not another installer type."
}

$Signature = Get-AuthenticodeSignature -LiteralPath $MsixPath
$Signer = $Signature.SignerCertificate
if (-not $Signer) { throw "MSIX is unsigned or its signer cannot be inspected." }

$Thumbprint = Normalize-Hex $Signer.Thumbprint
if ($Signer.Subject -ne $PublisherName) {
    throw "Unexpected signing certificate subject: $($Signer.Subject)"
}
$Hash = (Get-FileHash -LiteralPath $MsixPath -Algorithm SHA256).Hash.ToUpperInvariant()

# Read the manifest from the MSIX itself, not a separate source-tree copy.
Add-Type -AssemblyName System.IO.Compression.FileSystem
$Zip = [IO.Compression.ZipFile]::OpenRead($MsixPath)
try {
    $Entry = $Zip.GetEntry("AppxManifest.xml")
    if (-not $Entry) { throw "MSIX is missing AppxManifest.xml." }
    $Reader = New-Object IO.StreamReader($Entry.Open())
    try { [xml]$Manifest = $Reader.ReadToEnd() }
    finally { $Reader.Dispose() }
}
finally { $Zip.Dispose() }

$Identity = $Manifest.SelectSingleNode(
    "/*[local-name()='Package']/*[local-name()='Identity']"
)
if (-not $Identity) { throw "MSIX package identity is missing." }
$Name = $Identity.GetAttribute("Name")
$Publisher = $Identity.GetAttribute("Publisher")
$Version = $Identity.GetAttribute("Version")
$Architecture = $Identity.GetAttribute("ProcessorArchitecture")
if ($Name -ne $IdentityName -or $Publisher -ne $PublisherName) {
    throw "MSIX identity or publisher does not match the TerraSatch Edge development package."
}
if ($Version -notin $AllowedVersions -or $Architecture -ne "x64") {
    throw "Unexpected MSIX version/architecture: $Version / $Architecture."
}

# Validate startup defaults before trusting or installing this package.
$StartupNodes = @($Manifest.SelectNodes("//*[local-name()='StartupTask']"))
$Agent = @($StartupNodes | Where-Object { $_.GetAttribute("TaskId") -eq "TerraSatchEdgeAgent" })
$Radio = @($StartupNodes | Where-Object { $_.GetAttribute("TaskId") -eq "TerraSatchRadio" })
if ($StartupNodes.Count -ne 2 -or $Agent.Count -ne 1 -or $Radio.Count -ne 1) {
    throw "Expected one Edge agent and one radio startup task."
}
if ($Agent[0].GetAttribute("Enabled") -ne "true" -or
    $Radio[0].GetAttribute("Enabled") -ne "false") {
    throw "Unsafe or unexpected startup defaults in the MSIX."
}

Write-Host "TerraSatch Edge v0.2.9 beta - inspection" -ForegroundColor Cyan
Write-Host "Package: $MsixPath"
Write-Host "Identity: $Name"
Write-Host "Version: $Version"
Write-Host "Publisher: $Publisher"
Write-Host "SHA256: $Hash"
Write-Host "Signing thumbprint: $Thumbprint"
Write-Host "Signer not-before: $($Signer.NotBefore.ToUniversalTime().ToString('u'))"
Write-Host "Signer not-after:  $($Signer.NotAfter.ToUniversalTime().ToString('u'))"
Write-Host "Pre-trust signature status: $($Signature.Status)"
Write-Host "Agent startup default: ON; Radio startup default: OFF"

if (-not $Install) {
    Write-Host "Inspection only: nothing installed or trusted." -ForegroundColor Green
    Write-Host "For installation, independently confirm the signer thumbprint and use -Install,"
    Write-Host "-CertificatePath <matching public .cer> and -ExpectedThumbprint <verified thumbprint>."
    return
}

if (-not $CertificatePath -or -not $ExpectedThumbprint) {
    throw "-Install requires a matching public .cer and an independently verified -ExpectedThumbprint."
}
$ExpectedThumbprint = Normalize-Hex $ExpectedThumbprint
if ($ExpectedThumbprint.Length -ne 40 -or $Thumbprint -ne $ExpectedThumbprint) {
    throw "Signing thumbprint does not match the expected fingerprint."
}
if ($ExpectedSha256) {
    $ExpectedSha256 = Normalize-Hex $ExpectedSha256
    if ($ExpectedSha256.Length -ne 64 -or $ExpectedSha256 -ne $Hash) {
        throw "MSIX SHA-256 does not match the expected release artifact."
    }
}

$CertificatePath = (Resolve-Path -LiteralPath $CertificatePath).Path
if ([IO.Path]::GetExtension($CertificatePath) -ne ".cer") {
    throw "Use a public .cer file only. Never import a private .pfx for beta trust."
}
$PublicCert = New-Object Security.Cryptography.X509Certificates.X509Certificate2($CertificatePath)
if ($PublicCert.HasPrivateKey) { throw "Certificate file must contain only the public certificate." }
if ((Normalize-Hex $PublicCert.Thumbprint) -ne $Thumbprint) {
    throw "Provided .cer does not match the exact MSIX signing certificate."
}
if ($PublicCert.Subject -ne $PublisherName) {
    throw "Unexpected subject on the public certificate."
}

$Principal = New-Object Security.Principal.WindowsPrincipal(
    [Security.Principal.WindowsIdentity]::GetCurrent()
)
if (-not $Principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Open Windows PowerShell as Administrator for -Install."
}
$SignTool = Resolve-SignTool

# Trust only this explicitly selected public signer, never the Trusted Root store.
$StorePath = "Cert:\LocalMachine\TrustedPeople\$Thumbprint"
$AddedTrust = $false
if (-not $PSCmdlet.ShouldProcess($MsixPath, "Trust matched public signer, verify timestamp, and install MSIX")) {
    return
}
try {
    if (-not (Test-Path -LiteralPath $StorePath)) {
        $Imported = Import-Certificate -FilePath $CertificatePath -CertStoreLocation "Cert:\LocalMachine\TrustedPeople"
        if (-not $Imported -or (Normalize-Hex $Imported.Thumbprint) -ne $Thumbprint) {
            throw "Exact certificate import could not be verified."
        }
        $AddedTrust = $true
    }

    # /tw warns when no timestamp exists; SignTool returns 2 for warnings.
    # Require exit code 0: both an untrusted signature and absent timestamp fail.
    Write-Host "Verifying timestamped package signature..." -ForegroundColor Cyan
    & $SignTool verify /pa /v /tw $MsixPath
    if ($LASTEXITCODE -ne 0) {
        throw "SignTool returned $LASTEXITCODE. Signature/timestamp verification failed."
    }
    $VerifiedSignature = Get-AuthenticodeSignature -LiteralPath $MsixPath
    if ($VerifiedSignature.Status.ToString() -ne "Valid" -or
        (Normalize-Hex $VerifiedSignature.SignerCertificate.Thumbprint) -ne $Thumbprint) {
        throw "Windows has not verified the exact trusted MSIX signer."
    }

    Write-Host "Signature and timestamp verification passed." -ForegroundColor Green
    Write-Host "Installing MSIX. Existing running Edge processes may close." -ForegroundColor Yellow
    Add-AppxPackage -Path $MsixPath -ForceApplicationShutdown -ErrorAction Stop

    $Installed = @(Get-AppxPackage -Name $IdentityName |
        Where-Object { $_.Version.ToString() -eq $Version })
    if ($Installed.Count -ne 1) {
        throw "Installation completed but the exact package version could not be confirmed."
    }

    $Installed | Select-Object Name, Version, Publisher, PackageFamilyName | Format-List
    Write-Host "PASS: TerraSatch Edge beta installed for this Windows user." -ForegroundColor Green
    Write-Host "The app was not launched. Verify pairing, artwork, startup, and reboot manually."
    Write-Host "After beta testing, remove this signer from LocalMachine\TrustedPeople if no longer needed: $Thumbprint"
}
catch {
    if ($AddedTrust) {
        Remove-Item -LiteralPath $StorePath -Force -ErrorAction SilentlyContinue
    }
    throw
}
