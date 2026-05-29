param(
  [string]$Version,
  [switch]$Clean,
  [switch]$SkipBuild,
  [switch]$SkipFirmware,
  [switch]$SkipWindows,
  [switch]$Publish,
  [switch]$NoGitRelease,
  [string]$PublicRepoPath = "",
  [string]$GithubRepo = "bptworld/pixora"
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
if (!$PublicRepoPath) {
  $PublicRepoPath = Join-Path $repoRoot ".publish-pixora"
}

function Invoke-Step {
  param(
    [string]$Label,
    [scriptblock]$Script
  )

  Write-Host ""
  Write-Host "==> $Label"
  & $Script
  if ($LASTEXITCODE -ne 0) {
    throw "$Label failed with exit code $LASTEXITCODE"
  }
}

function Get-PixoraVersion {
  $versionPath = Join-Path $repoRoot "firmware\pixora-firmware\main\version.h"
  $text = Get-Content -LiteralPath $versionPath -Raw
  if ($text -match 'FIRMWARE_VERSION\s+"([^"]+)"') {
    return $Matches[1]
  }
  throw "Could not find FIRMWARE_VERSION in $versionPath"
}

function Set-PixoraVersion {
  param([string]$NewVersion)

  if ($NewVersion -notmatch '^\d+\.\d+\.\d+$') {
    throw "Version must look like 1.3.61"
  }

  $versionPath = Join-Path $repoRoot "firmware\pixora-firmware\main\version.h"
  $text = Get-Content -LiteralPath $versionPath -Raw
  $updated = $text -replace 'FIRMWARE_VERSION\s+"[^"]+"', "FIRMWARE_VERSION `"$NewVersion`""
  if ($updated -eq $text) {
    throw "Could not update FIRMWARE_VERSION in $versionPath"
  }
  Set-Content -LiteralPath $versionPath -Value $updated -Encoding ASCII
}

function Get-Sha256 {
  param([string]$Path)
  return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
}

function Assert-File {
  param([string]$Path)
  if (!(Test-Path -LiteralPath $Path)) {
    throw "Expected file not found: $Path"
  }
}

function Assert-PublicRepo {
  $resolved = Resolve-Path -LiteralPath $PublicRepoPath
  if (!(Test-Path -LiteralPath (Join-Path $resolved ".git"))) {
    throw "Public repo checkout not found at $resolved"
  }
  return $resolved
}

function Update-PublicReadme {
  param(
    [string]$Path,
    [string]$ReleaseVersion
  )

  $content = @"
# Pixora
*noun* | **pix-or-a**

A connected display platform for turning live data, alerts, messages, and personal dashboards into pixel-perfect cards across one or many screens.

**Definition:**
A system that collects useful information from apps, services, devices, and the internet, then presents it as clear, glanceable pixel displays.

**Origin:**
From **pix**, meaning pixels or small points of light, and **aura**, suggesting the ambient flow of information around a space.

## About
Pixora is a Windows app and firmware package for reusing Tidbyt-style LED matrix displays without the original Tidbyt cloud.

## Download

Most users should download the installer:

[PixoraSetup-v$ReleaseVersion.exe](https://github.com/$GithubRepo/releases/latest/download/PixoraSetup-v$ReleaseVersion.exe)

Run it, then launch Pixora from the Start menu or desktop shortcut.

For a no-install portable copy, download [Pixora-windows-v$ReleaseVersion.zip](https://github.com/$GithubRepo/releases/latest/download/Pixora-windows-v$ReleaseVersion.zip), unzip it, then double-click ``Pixora.exe``.

Pixora will start a local server and open the control page in your browser.

## First Flash

Use the Pixora web page to flash your display over USB the first time.

You will need:

- Windows
- Chrome or Edge
- A USB data cable
- Your Wi-Fi name and password

After the first flash, Pixora can manage cards and send updates over Wi-Fi.

## Firmware Only

The file below is for advanced/manual flashing:

[Pixora-firmware-v$ReleaseVersion.zip](https://github.com/$GithubRepo/releases/latest/download/Pixora-firmware-v$ReleaseVersion.zip)

It contains generic prebuilt firmware images. No personal Wi-Fi password, device name, or Pixora endpoint is baked into the firmware.

## Cards

Cards are not bundled in this download. Pixora downloads cards from the card registry inside the app.

Pixora cards are available in the [cards](https://github.com/bptworld/pixora/tree/main/cards) folder of this repository.

## Card Creation

The ``Card-Creation`` folder has a step-by-step starter guide for making your own Pixora cards.

## Release Files

Download files are attached to [GitHub Releases](https://github.com/$GithubRepo/releases), not stored in this repository root.
"@

  Set-Content -LiteralPath $Path -Value $content -Encoding utf8NoBOM
}

function Sync-PublicRepo {
  param([string]$ReleaseVersion)

  $publicRepo = Assert-PublicRepo
  $publicRepo = $publicRepo.Path

  Invoke-Step "Update public repo checkout" {
    Push-Location $publicRepo
    try {
      git status -sb
      git pull --ff-only
    } finally {
      Pop-Location
    }
  }

  Push-Location $publicRepo
  try {
    $dirty = git status --porcelain
    if ($dirty) {
      throw "Public repo checkout has uncommitted changes. Commit or clear them before releasing."
    }

    foreach ($pattern in @("PixoraSetup-v*.exe", "Pixora-windows-v*.zip", "Pixora-firmware-v*.zip")) {
      Get-ChildItem -LiteralPath $publicRepo -File -Filter $pattern -ErrorAction SilentlyContinue | ForEach-Object {
        git rm -f -- $_.Name | Out-Null
      }
    }

    Update-PublicReadme -Path (Join-Path $publicRepo "README.md") -ReleaseVersion $ReleaseVersion

    git add README.md

    $changes = git status --porcelain
    if (!$changes) {
      Write-Host "Public repo already matches v$ReleaseVersion."
      return
    }

    git commit -m "Release Pixora v$ReleaseVersion"
    if ($LASTEXITCODE -ne 0) {
      throw "Could not commit public release update."
    }

    if ($Publish) {
      git push origin main
      if ($LASTEXITCODE -ne 0) {
        throw "Could not push public release update."
      }
    } else {
      Write-Host "Public repo commit created locally. Re-run with -Publish to push and update the GitHub release."
    }
  } finally {
    Pop-Location
  }
}

function Publish-GitHubRelease {
  param([string]$ReleaseVersion)

  $setup = Join-Path $repoRoot "releases\PixoraSetup-v$ReleaseVersion.exe"
  $windowsZip = Join-Path $repoRoot "releases\Pixora-windows-v$ReleaseVersion.zip"
  $firmwareZip = Join-Path $repoRoot "releases\Pixora-firmware-v$ReleaseVersion.zip"
  Assert-File $setup
  Assert-File $windowsZip
  Assert-File $firmwareZip

  $notesPath = Join-Path $env:TEMP "pixora-v$ReleaseVersion-release-notes.md"
  @"
Pixora v$ReleaseVersion

Downloads:
- PixoraSetup-v$ReleaseVersion.exe: recommended Windows installer
- Pixora-windows-v$ReleaseVersion.zip: portable Windows package
- Pixora-firmware-v$ReleaseVersion.zip: firmware-only package for manual flashing

Hashes:
- PixoraSetup-v$ReleaseVersion.exe: $(Get-Sha256 $setup)
- Pixora-windows-v$ReleaseVersion.zip: $(Get-Sha256 $windowsZip)
- Pixora-firmware-v$ReleaseVersion.zip: $(Get-Sha256 $firmwareZip)
"@ | Set-Content -LiteralPath $notesPath -Encoding UTF8

  $tag = "v$ReleaseVersion"
  $exists = $false
  gh release view $tag --repo $GithubRepo *> $null
  if ($LASTEXITCODE -eq 0) {
    $exists = $true
  }

  if ($exists) {
    gh release upload $tag --repo $GithubRepo $setup $windowsZip $firmwareZip --clobber
    if ($LASTEXITCODE -ne 0) {
      throw "Could not upload release assets."
    }
    gh release edit $tag --repo $GithubRepo --title "Pixora v$ReleaseVersion" --notes-file $notesPath --latest
  } else {
    gh release create $tag --repo $GithubRepo --title "Pixora v$ReleaseVersion" --notes-file $notesPath --latest $setup $windowsZip $firmwareZip
  }

  if ($LASTEXITCODE -ne 0) {
    throw "Could not create or update GitHub release."
  }
}

if ($Version) {
  Invoke-Step "Set version to $Version" {
    Set-PixoraVersion -NewVersion $Version
  }
}

$version = Get-PixoraVersion
Write-Host "Pixora release version: $version"

if (!$SkipBuild) {
  if (!$SkipFirmware) {
    Invoke-Step "Build firmware release" {
      & (Join-Path $repoRoot "scripts\build-firmware-release.ps1") -Clean:$Clean
    }
  }

  if (!$SkipWindows) {
    Invoke-Step "Build Windows app and installer" {
      & (Join-Path $repoRoot "scripts\build-windows-app.ps1") -Clean:$Clean
    }
  }
}

$artifacts = @(
  (Join-Path $repoRoot "releases\PixoraSetup-v$version.exe"),
  (Join-Path $repoRoot "releases\Pixora-windows-v$version.zip"),
  (Join-Path $repoRoot "releases\Pixora-firmware-v$version.zip")
)

foreach ($artifact in $artifacts) {
  Assert-File $artifact
}

Sync-PublicRepo -ReleaseVersion $version

if ($Publish -and !$NoGitRelease) {
  Invoke-Step "Publish GitHub release" {
    Publish-GitHubRelease -ReleaseVersion $version
  }
}

Write-Host ""
Write-Host "Pixora release ready:"
foreach ($artifact in $artifacts) {
  $item = Get-Item -LiteralPath $artifact
  Write-Host "  $($item.Name)  $($item.Length) bytes  sha256=$(Get-Sha256 $artifact)"
}

if (!$Publish) {
  Write-Host ""
  Write-Host "Local release sync complete. Add -Publish to push the public repo and update the GitHub release."
}
