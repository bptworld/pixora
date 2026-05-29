param(
  [ValidateSet(
    "tidbyt-gen1",
    "tidbyt-gen1_swap",
    "tidbyt-gen2",
    "pixora-s3",
    "pixora-s3-wide",
    "pixoticker",
    "matrixportal-s3",
    "matrixportal-s3-waveshare",
    "matrixportal-s3-128x32"
  )]
  [string[]]$Target = @("tidbyt-gen1", "matrixportal-s3-waveshare", "matrixportal-s3-128x32"),

  [switch]$Clean,

  [switch]$NoZip
)

$ErrorActionPreference = "Stop"

function Get-FirmwareVersion {
  param([string]$RepoRoot)

  $versionPath = Join-Path $RepoRoot "firmware\pixora-firmware\main\version.h"
  $text = Get-Content -LiteralPath $versionPath -Raw
  if ($text -match 'FIRMWARE_VERSION\s+"([^"]+)"') {
    return $Matches[1]
  }
  throw "Could not find FIRMWARE_VERSION in $versionPath"
}

function Get-FileSha256 {
  param([string]$Path)
  return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Assert-NoPrivateProvisioning {
  param([string]$Path)

  $bytes = [System.IO.File]::ReadAllBytes($Path)
  $privateStrings = @(
    "bptworld3",
    "wgcandle",
    "192.168.4.72"
  )

  foreach ($value in $privateStrings) {
    $needle = [System.Text.Encoding]::ASCII.GetBytes($value)
    for ($i = 0; $i -le $bytes.Length - $needle.Length; $i++) {
      $found = $true
      for ($j = 0; $j -lt $needle.Length; $j++) {
        if ($bytes[$i + $j] -ne $needle[$j]) {
          $found = $false
          break
        }
      }
      if ($found) {
        throw "Release firmware contains private provisioning string '$value': $Path"
      }
    }
  }
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$version = Get-FirmwareVersion -RepoRoot $repoRoot
$releaseRoot = Join-Path $repoRoot "releases\Pixora-firmware-v$version"
$buildScript = Join-Path $repoRoot "scripts\build-firmware.ps1"

New-Item -ItemType Directory -Force -Path $releaseRoot | Out-Null

$manifest = [ordered]@{
  name = "Pixora firmware"
  version = $version
  createdAt = (Get-Date).ToUniversalTime().ToString("o")
  provisioning = "generic setup-page firmware"
  notes = @(
    "No Wi-Fi SSID, Wi-Fi password, Pixora endpoint, or device hostname is baked into these images.",
    "First flash uses merged_firmware.bin over USB.",
    "After setup, Wi-Fi updates use firmware.bin."
  )
  targets = @()
}

foreach ($targetName in $Target) {
  Write-Host ""
  Write-Host "Building generic release firmware for $targetName..."
  & $buildScript -Target $targetName -Clean:$Clean
  if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
  }

  $distDir = Join-Path $repoRoot "dist\firmware\$targetName"
  $targetReleaseDir = Join-Path $releaseRoot $targetName
  New-Item -ItemType Directory -Force -Path $targetReleaseDir | Out-Null

  $files = @(
    "merged_firmware.bin",
    "firmware.bin",
    "bootloader.bin",
    "partition-table.bin",
    "flash_args"
  )

  $targetFiles = @()
  foreach ($file in $files) {
    $src = Join-Path $distDir $file
    if (!(Test-Path -LiteralPath $src)) {
      throw "Expected build output not found: $src"
    }

    if ($file -like "*.bin") {
      Assert-NoPrivateProvisioning -Path $src
    }

    $dest = Join-Path $targetReleaseDir $file
    Copy-Item -Force -LiteralPath $src -Destination $dest
    $item = Get-Item -LiteralPath $dest
    $targetFiles += [ordered]@{
      name = $file
      bytes = $item.Length
      sha256 = Get-FileSha256 -Path $dest
    }
  }

  $readme = @"
Pixora firmware v$version - $targetName

This is a generic setup-page firmware image.

Files:
- merged_firmware.bin: first USB flash image
- firmware.bin: Wi-Fi update image after Pixora is already installed
- bootloader.bin, partition-table.bin, flash_args: advanced/manual flashing files

No personal Wi-Fi, password, endpoint, or device name is baked into this build.

After first flash, configure the device from the Pixora Windows app.
"@
  Set-Content -LiteralPath (Join-Path $targetReleaseDir "README.txt") -Value $readme -Encoding UTF8

  $manifest.targets += [ordered]@{
    target = $targetName
    files = $targetFiles
  }
}

$manifestPath = Join-Path $releaseRoot "manifest.json"
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

$checksums = @()
Get-ChildItem -Path $releaseRoot -File -Recurse | Where-Object { $_.Name -ne "SHA256SUMS.txt" } | ForEach-Object {
  $relative = $_.FullName.Substring($releaseRoot.Length + 1).Replace("\", "/")
  $checksums += "$(Get-FileSha256 -Path $_.FullName)  $relative"
}
Set-Content -LiteralPath (Join-Path $releaseRoot "SHA256SUMS.txt") -Value $checksums -Encoding ASCII

if (!$NoZip) {
  $zipPath = "$releaseRoot.zip"
  Remove-Item -Force -LiteralPath $zipPath -ErrorAction SilentlyContinue
  Compress-Archive -Path (Join-Path $releaseRoot "*") -DestinationPath $zipPath
}

Write-Host ""
Write-Host "Pixora firmware release package complete:"
Write-Host "  Version: $version"
Write-Host "  Folder:  $releaseRoot"
if (!$NoZip) {
  Write-Host "  Zip:     $releaseRoot.zip"
}

