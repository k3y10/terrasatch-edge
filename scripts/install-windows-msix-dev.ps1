[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$MsixPath,
    [Parameter(Mandatory = $true)][string]$CertificatePath,
    [string]$IdentityName = "TerraSatch.Edge.Dev"
)

$ErrorActionPreference = "Stop"

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Packaged Windows services require an elevated PowerShell session for this development install test."
}

$MsixPath = (Resolve-Path -LiteralPath $MsixPath).Path
$CertificatePath = (Resolve-Path -LiteralPath $CertificatePath).Path

Write-Host "Trusting TerraSatch MSIX development certificate in LocalMachine\TrustedPeople" -ForegroundColor Cyan
$imported = Import-Certificate `
    -FilePath $CertificatePath `
    -CertStoreLocation "Cert:\LocalMachine\TrustedPeople"
if (-not $imported) { throw "Development certificate import failed." }

Write-Host "Installing $MsixPath" -ForegroundColor Cyan
Add-AppxPackage -Path $MsixPath -ForceApplicationShutdown

$package = Get-AppxPackage -Name $IdentityName -ErrorAction Stop
Write-Host ""
Write-Host "MSIX installed:" -ForegroundColor Green
$package | Select-Object Name, Version, Publisher, PackageFamilyName, InstallLocation | Format-List

Write-Host "Packaged service registration:" -ForegroundColor Cyan
$services = Get-Service TerraSatchEdge, TerraSatchRadio -ErrorAction SilentlyContinue
if (-not $services -or $services.Count -lt 2) {
    throw "Expected TerraSatchEdge and TerraSatchRadio services were not both registered by MSIX."
}
$services | Format-Table Status, StartType, Name, DisplayName -AutoSize

Write-Host ""
Write-Host "Launch the packaged operator console from Start, or run:" -ForegroundColor Green
Write-Host "  explorer.exe shell:AppsFolder\$($package.PackageFamilyName)!TerraSatchEdge"
Write-Host ""
Write-Host "After testing, uninstall with:" -ForegroundColor Yellow
Write-Host "  Get-AppxPackage -Name $IdentityName | Remove-AppxPackage"
Write-Host "The development certificate can then be removed from LocalMachine\TrustedPeople by thumbprint: $($imported.Thumbprint)"
