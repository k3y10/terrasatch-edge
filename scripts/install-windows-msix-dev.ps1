[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$MsixPath,
    [Parameter(Mandatory = $true)][string]$CertificatePath,
    [string]$IdentityName = "TerraSatch.Edge.Dev"
)

$ErrorActionPreference = "Stop"

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run this development install test from an elevated PowerShell session. Elevation is only needed to trust the temporary test certificate in LocalMachine\TrustedPeople."
}

$MsixPath = (Resolve-Path -LiteralPath $MsixPath).Path
$CertificatePath = (Resolve-Path -LiteralPath $CertificatePath).Path

Write-Host "Trusting the temporary TerraSatch development certificate in LocalMachine\\TrustedPeople" -ForegroundColor Cyan
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

[xml]$manifest = Get-AppxPackageManifest -Package $package
$ns = New-Object System.Xml.XmlNamespaceManager($manifest.NameTable)
$ns.AddNamespace("desktop", "http://schemas.microsoft.com/appx/manifest/desktop/windows10")
$startup = $manifest.SelectNodes("//desktop:Extension[@Category='windows.startupTask']/desktop:StartupTask", $ns)
if ($startup.Count -ne 2) { throw "Expected two TerraSatch startup tasks; found $($startup.Count)." }

Write-Host "Packaged startup tasks:" -ForegroundColor Cyan
$startup | ForEach-Object {
    [PSCustomObject]@{
        TaskId = $_.TaskId
        EnabledByDefault = $_.Enabled
        DisplayName = $_.DisplayName
    }
} | Format-Table -AutoSize

Write-Host "Launching TerraSatch Edge once so Windows registers the startup tasks..." -ForegroundColor Cyan
$appTarget = "shell:AppsFolder\$($package.PackageFamilyName)!TerraSatchEdge"
Start-Process explorer.exe $appTarget

Write-Host ""
Write-Host "Local MSIX install test is ready." -ForegroundColor Green
Write-Host "Edge background startup defaults ON after the first app launch."
Write-Host "Radio startup defaults OFF. Pair/configure a receive target first, then enable TerraSatch Radio in Settings > Apps > Startup or Task Manager > Startup apps."
Write-Host ""
Write-Host "State is per-user under: $env:LOCALAPPDATA\TerraSatch\Edge"
Write-Host ""
Write-Host "After testing, uninstall with:" -ForegroundColor Yellow
Write-Host "  Get-AppxPackage -Name $IdentityName | Remove-AppxPackage"
Write-Host "Then remove the temporary development certificate from LocalMachine\TrustedPeople by thumbprint: $($imported.Thumbprint)"
