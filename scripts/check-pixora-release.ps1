param(
  [string]$Version = "",
  [string]$GithubRepo = "bptworld/pixora",
  [switch]$RequireNoRootDownloads
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")

function Get-PixoraVersion {
  $versionPath = Join-Path $repoRoot "firmware\pixora-firmware\main\version.h"
  $text = Get-Content -LiteralPath $versionPath -Raw
  if ($text -match 'FIRMWARE_VERSION\s+"([^"]+)"') {
    return $Matches[1]
  }
  throw "Could not find FIRMWARE_VERSION in $versionPath"
}

function Assert-File {
  param([string]$Path)
  if (!(Test-Path -LiteralPath $Path)) {
    throw "Expected file not found: $Path"
  }
}

function Get-Sha256Lower {
  param([string]$Path)
  return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

if (!$Version) {
  $Version = Get-PixoraVersion
}

$tag = "v$Version"
$expected = @(
  "PixoraSetup-v$Version.exe",
  "Pixora-windows-v$Version.zip",
  "Pixora-firmware-v$Version.zip"
)

Write-Host "Checking Pixora release $tag in $GithubRepo..."

$release = gh release view $tag --repo $GithubRepo --json tagName,name,assets,isDraft,isPrerelease,url | ConvertFrom-Json
if (!$release -or $release.tagName -ne $tag) {
  throw "GitHub release $tag was not found."
}
if ($release.isDraft) {
  throw "GitHub release $tag is still a draft."
}

foreach ($name in $expected) {
  $localPath = Join-Path $repoRoot "releases\$name"
  Assert-File $localPath
  $localHash = Get-Sha256Lower $localPath
  $asset = @($release.assets | Where-Object { $_.name -eq $name })[0]
  if (!$asset) {
    throw "Missing GitHub release asset: $name"
  }
  if ($asset.size -ne (Get-Item -LiteralPath $localPath).Length) {
    throw "Size mismatch for ${name}: local=$((Get-Item -LiteralPath $localPath).Length) github=$($asset.size)"
  }
  if ($asset.digest -and $asset.digest -ne "sha256:$localHash") {
    throw "SHA256 mismatch for ${name}: local=$localHash github=$($asset.digest)"
  }
  Write-Host "OK $name $localHash"
}

if ($RequireNoRootDownloads) {
  $rootFiles = gh api "repos/$GithubRepo/contents" | ConvertFrom-Json |
    Where-Object { $_.type -eq "file" -and $_.name -match '^Pixora.*\.(zip|exe)$' }
  if ($rootFiles) {
    $names = ($rootFiles | Select-Object -ExpandProperty name) -join ", "
    throw "Download artifacts are still stored in the repo root: $names"
  }
  Write-Host "OK repo root has no Pixora zip/exe downloads."
}

Write-Host "OK GitHub release: $($release.url)"
