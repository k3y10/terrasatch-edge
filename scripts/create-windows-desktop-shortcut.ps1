# Creates a shortcut for an already installed Edge MSIX without changing its signature.
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory = $true)]
    [string]$PackageFamilyName
)

$ErrorActionPreference = "Stop"
$Packages = @(Get-AppxPackage | Where-Object PackageFamilyName -EQ $PackageFamilyName)
if ($Packages.Count -ne 1) { throw "Install the requested Edge package for this Windows user first." }
$Package = $Packages[0]
[xml]$Manifest = Get-AppxPackageManifest -Package $Package
$Apps = @($Manifest.Package.Applications.Application | Where-Object Id -EQ "TerraSatchEdge")
if ($Apps.Count -ne 1) { throw "The selected package does not contain the TerraSatchEdge application." }

# Windows resolves redirected/OneDrive desktops and the current package version.
$Desktop = [Environment]::GetFolderPath("DesktopDirectory")
if (-not $Desktop -or -not (Test-Path -LiteralPath $Desktop)) { throw "Desktop folder unavailable." }
$ShortcutPath = Join-Path $Desktop "TerraSatch Edge.lnk"
if (Test-Path -LiteralPath $ShortcutPath) { throw "A TerraSatch Edge shortcut already exists; leaving it unchanged." }
$AppTarget = "shell:AppsFolder\$PackageFamilyName!TerraSatchEdge"
$Executable = Join-Path $Package.InstallLocation $Apps[0].Executable
if (-not (Test-Path -LiteralPath $Executable)) { throw "Packaged launcher unavailable: $Executable" }

if ($PSCmdlet.ShouldProcess($ShortcutPath, "Create shortcut for $AppTarget")) {
    $Shell = New-Object -ComObject WScript.Shell
    $Shortcut = $Shell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = Join-Path $env:WINDIR "explorer.exe"
    $Shortcut.Arguments = $AppTarget
    $Shortcut.IconLocation = "$Executable,0"
    $Shortcut.Description = "Open TerraSatch Edge"
    $Shortcut.Save()
    Write-Output $ShortcutPath
}
