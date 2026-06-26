param(
  [string]$Version = "2.0.0-rebuild",
  [switch]$Build
)

$ErrorActionPreference = "Stop"

$projectRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
$repoRoot = Resolve-Path -LiteralPath (Join-Path $projectRoot "..\..")
$releaseDir = Join-Path $repoRoot "releases\firmware"
$dropDir = Resolve-Path -LiteralPath (Join-Path $repoRoot "..\Firmware") -ErrorAction SilentlyContinue
if (!$dropDir) {
  $dropDir = Join-Path $repoRoot "..\Firmware"
}
$pio = Join-Path $env:APPDATA "Python\Python313\Scripts\pio.exe"

if (!(Test-Path -LiteralPath $pio)) {
  throw "PlatformIO was not found at $pio. Install it with: python -m pip install --user -U platformio"
}

if ($Build) {
  Push-Location $projectRoot
  try {
    & $pio run -e matrixportal_s3_64x32 -e matrixportal_s3_128x32
  } finally {
    Pop-Location
  }
}

New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null
New-Item -ItemType Directory -Force -Path $dropDir | Out-Null

$targets = @(
  @{ Env = "matrixportal_s3_64x32"; Name = "64x32" },
  @{ Env = "matrixportal_s3_128x32"; Name = "128x32" }
)

foreach ($target in $targets) {
  $source = Join-Path $projectRoot ".pio\build\$($target.Env)\firmware.bin"
  if (!(Test-Path -LiteralPath $source)) {
    throw "Missing build output: $source. Run with -Build first."
  }
  $dest = Join-Path $releaseDir "pixora-v$Version-$($target.Name)-ota-firmware.bin"
  $drop = Join-Path $dropDir "pixora-v$Version-$($target.Name)-ota-firmware.bin"
  Copy-Item -LiteralPath $source -Destination $dest -Force
  Copy-Item -LiteralPath $source -Destination $drop -Force
  Write-Host "Wrote $dest"
  Write-Host "Wrote $drop"
}
