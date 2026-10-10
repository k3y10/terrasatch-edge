# Local Windows PowerShell publisher for Linux AMD64 v0.2.9.
# Requires exact WSL-built .deb, SHA256SUMS and metadata; never uses Actions.
[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = "High")]
param(
  [Parameter(Mandatory=$true)][string]$AssetDir,
  [Parameter(Mandatory=$true)][string]$SourceDir,
  [switch]$Publish
)
$ErrorActionPreference = "Stop"
$repo = "k3y10/terrasatch-edge"
$tag = "v0.2.9-linux-beta"
$sha = "f3918dd023e3862eb9bd4dc183be4c6cbeb36644"
$name = "terrasatch-edge_0.2.9_amd64.deb"
$AssetDir = (Resolve-Path -LiteralPath $AssetDir).Path
$SourceDir = (Resolve-Path -LiteralPath $SourceDir).Path
$deb = Join-Path $AssetDir $name
$sumFile = Join-Path $AssetDir "SHA256SUMS-LINUX.txt"
$metaFile = Join-Path $AssetDir "LINUX-V029-BUILD-METADATA.txt"
function AssertExit([string]$context) {
  if ($LASTEXITCODE -ne 0) { throw "$context failed with exit code $LASTEXITCODE." }
}
foreach ($p in @($deb,$sumFile,$metaFile)) {
  if (-not (Test-Path -LiteralPath $p -PathType Leaf)) { throw "Missing build output: $p" }
}
$actual = (Get-FileHash -LiteralPath $deb -Algorithm SHA256).Hash.ToLowerInvariant()
$sum = (Get-Content -LiteralPath $sumFile -Raw).Trim()
if ($sum -ne "$actual  $name") { throw "SHA256SUMS-LINUX.txt disagrees with the package bytes." }
$meta = Get-Content -LiteralPath $metaFile -Raw
foreach ($line in @(
  "release_version=0.2.9",
  "package_filename=$name",
  "package_sha256=$actual",
  "source_commit=$sha",
  "build_os=Ubuntu 24.04",
  "architecture=amd64",
  "full_pytest=passed",
  "pyinstaller_branding_check=passed",
  "debian_metadata_and_services=passed",
  "extracted_binary_smoke=passed",
  "radio_autostart=disabled"
)) {
  if ($meta -notmatch "(?m)^$([regex]::Escape($line))\r?$") {
    throw "Build metadata missing: $line"
  }
}
$localSha = (& git -C $SourceDir rev-parse HEAD).Trim()
AssertExit "Local source verification"
if ($localSha -ne $sha) { throw "Clean source checkout is not the v0.2.9 source commit." }
$dirty = @(& git -C $SourceDir status --porcelain --untracked-files=no)
AssertExit "Clean source inspection"
if ($dirty.Count -gt 0) { throw "Release source checkout has uncommitted changes." }
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
  throw "GitHub CLI not found in PATH. Reopen PowerShell after installing gh."
}
& gh auth status --hostname github.com
AssertExit "GitHub CLI auth"
$remote = (& gh api "repos/$repo/commits/$sha" --jq ".sha").Trim()
AssertExit "Remote source commit"
if ($remote -ne $sha) { throw "v0.2.9 source not found on GitHub." }
# A missing release is normal. Do not query it with redirected stderr under PowerShell 5.1.
$releaseListJson = & gh release list --repo $repo --limit 100 --json tagName
AssertExit "GitHub release listing"
$releases = $releaseListJson | ConvertFrom-Json
if (@($releases | Where-Object { $_.tagName -eq $tag }).Count -gt 0) {
  throw "Release $tag already exists; refusing to overwrite."
}
$existingTag = @(& git -C $SourceDir ls-remote --refs --tags origin "refs/tags/$tag")
AssertExit "Remote tag inspection"
if ($existingTag.Count -gt 0) { throw "Tag $tag already exists; refusing to retag." }

Write-Host "PASS: Linux v0.2.9 release preflight checks." -ForegroundColor Green
Write-Host "Artifact: $deb"
Write-Host "SHA256: $actual"
Write-Host "Source SHA: $sha"
Write-Host "Native systemd install and reboot acceptance remain separate."
if (-not $Publish) {
  Write-Host "Inspection only. Nothing uploaded."
  return
}
if (-not $PSCmdlet.ShouldProcess("$repo/$tag", "Create Linux prerelease, upload and round-trip verify Debian package")) {
  return
}
$temp = Join-Path $env:TEMP ("tsedge-linux-release-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $temp -Force | Out-Null
try {
  $install = Join-Path $temp "LINUX-DEB-INSTALL.txt"
  @"
TerraSatch Edge v0.2.9 Linux AMD64 beta
Supported release build host: Ubuntu 24.04 AMD64.
SHA256: $actual
Git source: $sha

Download $name and verify: sha256sum $name
Install only on an approved Ubuntu 24.04 field pilot:
  sudo apt install ./$name
  sudo terrasatch-edge setup
  sudo terrasatch-edge status
  sudo terrasatch-edge doctor
  sudo systemctl status terrasatch-edge.service
  systemctl is-enabled terrasatch-radio.service

Radio service is installed but not automatically enabled on first install;
a previously operator-enabled radio service may remain enabled after upgrade.
Native install/paired heartbeat/reboot checks remain required on target devices.
Do not assume RF reception or TX without authorized hardware validation.
"@ | Set-Content -LiteralPath $install -Encoding UTF8
  $notes = Join-Path $temp "LINUX-RELEASE-NOTES.md"
  @"
TerraSatch Edge **v0.2.9 Linux AMD64 beta**, built locally on Ubuntu 24.04 without GitHub Actions.
Artifact: $name
SHA-256: $actual
Source commit: $sha

Automated local native build checks: full pytest regression suite, PyInstaller branded binary,
Debian identity/version/architecture/services, extracted payload --version smoke,
and radio automatic-startup guard.
Native systemd install, API pairing, heartbeat and reboot persistence have not yet been
signed off. Check these on an approved Ubuntu 24.04 field computer.
Receive-first RF features require explicitly configured supported hardware.
Existing Linux v0.2.8 and Windows v0.2.9 assets remain immutable.
"@ | Set-Content -LiteralPath $notes -Encoding UTF8
  $createArgs = @(
    "release", "create", $tag, $deb, $sumFile, $metaFile, $install,
    "--repo", $repo, "--target", $sha,
    "--title", "TerraSatch Edge v0.2.9 Linux AMD64 beta",
    "--notes-file", $notes, "--prerelease", "--latest=false", "--draft"
  )
  & gh @createArgs
  AssertExit "Create Linux prerelease draft"
  $roundtrip = Join-Path $temp "download"
  New-Item -ItemType Directory -Path $roundtrip -Force | Out-Null
  & gh release download $tag --repo $repo --dir $roundtrip --pattern $name
  AssertExit "Download uploaded Linux beta"
  $downloadedHash = (Get-FileHash (Join-Path $roundtrip $name) -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($downloadedHash -ne $actual) {
    throw "Uploaded Debian artifact failed SHA-256 round-trip. Draft remains unpublished."
  }
  & gh release edit $tag --repo $repo --draft=false
  AssertExit "Publish Linux beta"
  Write-Host "PUBLISHED: https://github.com/$repo/releases/tag/$tag" -ForegroundColor Green
  Write-Host "Debian AMD64: https://github.com/$repo/releases/download/$tag/$name"
}
finally {
  Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue
}
