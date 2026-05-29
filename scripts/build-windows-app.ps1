param(
  [switch]$Clean,
  [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$versionFile = Join-Path $root "firmware\pixora-firmware\main\version.h"
$versionText = Get-Content -Raw $versionFile
if ($versionText -notmatch 'FIRMWARE_VERSION\s+"([^"]+)"') {
  throw "Could not read firmware version from $versionFile"
}
$version = $Matches[1]

$python = Get-Command python -ErrorAction SilentlyContinue
if (!$python) {
  throw "Python is required to build the Windows app package on the developer machine."
}

if ($Clean) {
  Remove-Item -Recurse -Force (Join-Path $root "build\Pixora") -ErrorAction SilentlyContinue
  Remove-Item -Recurse -Force (Join-Path $root "dist\Pixora") -ErrorAction SilentlyContinue
}

Write-Host "Installing packager dependencies..."
& $python.Source -m pip install -r (Join-Path $root "requirements.txt")
if ($LASTEXITCODE -ne 0) {
  throw "Could not install app dependencies."
}
& $python.Source -m pip install -r (Join-Path $root "requirements-build.txt")
if ($LASTEXITCODE -ne 0) {
  throw "Could not install packager dependencies."
}

Write-Host "Building Pixora.exe..."
& $python.Source -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --name Pixora `
  --hidden-import zeroconf `
  --hidden-import paho `
  --hidden-import paho.mqtt `
  --hidden-import paho.mqtt.client `
  --collect-all PIL `
  --distpath (Join-Path $root "dist\Pixora") `
  --workpath (Join-Path $root "build\Pixora") `
  (Join-Path $root "pixora_server.py")
if ($LASTEXITCODE -ne 0) {
  throw "PyInstaller failed."
}

$packageDir = Join-Path $root "releases\Pixora-windows-v$version"
$zipPath = "$packageDir.zip"
Remove-Item -Recurse -Force $packageDir -ErrorAction SilentlyContinue
Remove-Item -Force $zipPath -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $packageDir | Out-Null

Copy-Item (Join-Path $root "dist\Pixora\Pixora.exe") $packageDir
Set-Content -Encoding ASCII -Path (Join-Path $packageDir "VERSION") -Value $version

$files = @(
  "index.html",
  "setup.html",
  "setup-success.html",
  "getting-started.html",
  "flash.html",
  "Silkscreen-Regular.ttf",
  "Silkscreen-Bold.ttf",
  "PixelifySans.ttf",
  "PixelifySans-Bold.ttf"
)
foreach ($file in $files) {
  Copy-Item (Join-Path $root $file) $packageDir
}

foreach ($dir in @("dist\firmware", "docs")) {
  $source = Join-Path $root $dir
  if (Test-Path $source) {
    Copy-Item $source (Join-Path $packageDir $dir) -Recurse
  }
}

New-Item -ItemType Directory -Force (Join-Path $packageDir "data") | Out-Null
New-Item -ItemType Directory -Force (Join-Path $packageDir "scripts") | Out-Null

$addonsSource = Join-Path $root "addons"
if (Test-Path $addonsSource) {
  Copy-Item $addonsSource (Join-Path $packageDir "addons") -Recurse
  Get-ChildItem -Path (Join-Path $packageDir "addons") -Directory -Filter "__pycache__" -Recurse -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
} else {
  New-Item -ItemType Directory -Force (Join-Path $packageDir "addons") | Out-Null
}

foreach ($script in @("configure-device-usb.ps1", "flash-device.ps1")) {
  $source = Join-Path $root "scripts\$script"
  if (Test-Path $source) {
    Copy-Item $source (Join-Path $packageDir "scripts")
  }
}

@{
  registry = "pixora"
  version = "1"
  cards = @()
} | ConvertTo-Json -Depth 4 | Set-Content -Encoding ASCII (Join-Path $packageDir "registry.json")

@"
Pixora for Windows
=================

1. Double-click Pixora.exe.
2. Your browser should open to http://pixora.local:8088/.
3. Use Flash Device for the first USB flash.

No Python install is required for normal use.

Installed Pixora stores settings, devices, groups, and downloaded cards in:
%LOCALAPPDATA%\Pixora

If Windows Firewall asks, allow Pixora on your private network so devices can reach it.
"@ | Set-Content -Encoding ASCII (Join-Path $packageDir "START HERE.txt")

Compress-Archive -Path (Join-Path $packageDir "*") -DestinationPath $zipPath

$installerPath = $null
if (!$SkipInstaller) {
  $iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
  if (!$iscc) {
    $candidates = @(
      "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
      "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
      "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    )
    foreach ($candidate in $candidates) {
      if ($candidate -and (Test-Path -LiteralPath $candidate)) {
        $iscc = Get-Item -LiteralPath $candidate
        break
      }
    }
  }

  if ($iscc) {
    $installerOut = Join-Path $root "releases"
    & $iscc.FullName `
      "/DMyAppVersion=$version" `
      "/DPackageDir=$packageDir" `
      "/DOutputDir=$installerOut" `
      (Join-Path $root "installer\Pixora.iss")
    if ($LASTEXITCODE -ne 0) {
      throw "Inno Setup failed."
    }
    $installerPath = Join-Path $installerOut "PixoraSetup-v$version.exe"
  } else {
    throw "Inno Setup 6 was not found, so the Windows installer cannot be built. Install Inno Setup 6 or pass -SkipInstaller to build only the portable zip."
  }
}

Write-Host ""
Write-Host "Pixora Windows package complete:"
Write-Host "  Folder: $packageDir"
Write-Host "  Zip:    $zipPath"
if ($installerPath) {
  Write-Host "  Setup:  $installerPath"
}
