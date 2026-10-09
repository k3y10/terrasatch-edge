[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$MsixPath,
    [Parameter(Mandatory = $true)][string]$ExpectedIdentityName,
    [Parameter(Mandatory = $true)][string]$ExpectedPublisher
)

$ErrorActionPreference = "Stop"
$PackagePath = (Resolve-Path -LiteralPath $MsixPath).Path
if ([IO.Path]::GetExtension($PackagePath) -ine ".msix") {
    throw "Provide the exact MSIX artifact, not a certificate or unsigned executable."
}
if ($ExpectedIdentityName -eq "TerraSatch.Edge.Dev") {
    throw "A development identity cannot be approved as a public Store release."
}

# Windows validates the signature, trust chain and any signing timestamp. Do not
# equate a hash/signer match or UnknownError with public Windows trust. A verified
# timestamp may keep a trusted signature valid after its leaf certificate expires.
$Signature = Get-AuthenticodeSignature -LiteralPath $PackagePath
if ($Signature.Status -ne [System.Management.Automation.SignatureStatus]::Valid) {
    throw "Public MSIX signature is not trusted by Windows: $($Signature.Status). Do not publish or ask users to bypass this result."
}
if (-not $Signature.SignerCertificate -or
    $Signature.SignerCertificate.Subject -ceq $Signature.SignerCertificate.Issuer) {
    throw "A self-signed development package cannot be offered as a trusted public download."
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
$Archive = [IO.Compression.ZipFile]::OpenRead($PackagePath)
try {
    $ManifestEntry = $Archive.GetEntry("AppxManifest.xml")
    if (-not $ManifestEntry) { throw "The package has no AppxManifest.xml." }
    $Settings = [System.Xml.XmlReaderSettings]::new()
    $Settings.DtdProcessing = [System.Xml.DtdProcessing]::Prohibit
    $Settings.XmlResolver = $null
    $Reader = [System.Xml.XmlReader]::Create($ManifestEntry.Open(), $Settings)
    try {
        $Manifest = [System.Xml.XmlDocument]::new()
        $Manifest.XmlResolver = $null
        $Manifest.Load($Reader)
    } finally { $Reader.Dispose() }
    $Identity = $Manifest.DocumentElement.Identity
    if ($Identity.Name -cne $ExpectedIdentityName -or
        $Identity.Publisher -cne $ExpectedPublisher) {
        throw "MSIX identity/publisher does not match the expected Partner Center app."
    }
    if ($Identity.Name -eq "TerraSatch.Edge.Dev") {
        throw "The package still uses the development identity."
    }
} finally { $Archive.Dispose() }

[pscustomobject]@{
    Artifact = $PackagePath
    SHA256 = (Get-FileHash -LiteralPath $PackagePath -Algorithm SHA256).Hash
    SignatureTrust = "Valid"
    IdentityName = $Identity.Name
    Publisher = $Identity.Publisher
    PackageVersion = $Identity.Version
    SignerSubject = $Signature.SignerCertificate.Subject
    SignerIssuer = $Signature.SignerCertificate.Issuer
    TimestampSignerPresent = ($null -ne $Signature.TimeStamperCertificate)
    StoreCertificationVerified = $false
    CleanInstallAndUpgradeVerified = $false
} | ConvertTo-Json

# This read-only check is one release gate. Partner Center certification and the
# installed package's SignatureKind=Store, startup, pairing and upgrade checks are
# required separately; a valid direct signature alone does not prove Store origin.
