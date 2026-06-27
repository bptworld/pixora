param(
  [string]$Version = "2.0.0-rebuild",
  [switch]$Build
)

$ErrorActionPreference = "Stop"

$projectRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
$repoRoot = Resolve-Path -LiteralPath (Join-Path $projectRoot "..\..")
$releaseDir = Join-Path $repoRoot "releases\firmware"
$dropDir = Join-Path $repoRoot "firmware"
$pio = Join-Path $env:APPDATA "Python\Python313\Scripts\pio.exe"

if (!(Test-Path -LiteralPath $pio)) {
  throw "PlatformIO was not found at $pio. Install it with: python -m pip install --user -U platformio"
}

if ($Build) {
  Push-Location $projectRoot
  try {
    & $pio run `
      -e matrixportal_s3_64x32 `
      -e matrixportal_s3_128x32 `
      -e matrixportal_s3_64x32_reset `
      -e matrixportal_s3_128x32_reset
  } finally {
    Pop-Location
  }
}

New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null
New-Item -ItemType Directory -Force -Path $dropDir | Out-Null

$targets = @(
  @{ PreserveEnv = "matrixportal_s3_64x32"; ResetEnv = "matrixportal_s3_64x32_reset"; Name = "64x32" },
  @{ PreserveEnv = "matrixportal_s3_128x32"; ResetEnv = "matrixportal_s3_128x32_reset"; Name = "128x32" }
)

foreach ($target in $targets) {
  $preserveSource = Join-Path $projectRoot ".pio\build\$($target.PreserveEnv)\firmware.bin"
  $resetSource = Join-Path $projectRoot ".pio\build\$($target.ResetEnv)\firmware.bin"
  if (!(Test-Path -LiteralPath $preserveSource)) {
    throw "Missing build output: $preserveSource. Run with -Build first."
  }
  if (!(Test-Path -LiteralPath $resetSource)) {
    throw "Missing build output: $resetSource. Run with -Build first."
  }
  $outputs = @(
    @{ Source = $preserveSource; Name = "pixora-v$Version-$($target.Name)-user-ota-firmware.bin" },
    @{ Source = $resetSource; Name = "pixora-v$Version-$($target.Name)-factory-firmware.bin" },
    @{ Source = $resetSource; Name = "pixora-v$Version-$($target.Name)-ota-firmware.bin" }
  )
  foreach ($output in $outputs) {
    $name = $output.Name
    $dest = Join-Path $releaseDir $name
    $drop = Join-Path $dropDir $name
    Copy-Item -LiteralPath $output.Source -Destination $dest -Force
    Copy-Item -LiteralPath $output.Source -Destination $drop -Force
    Write-Host "Wrote $dest"
    Write-Host "Wrote $drop"
  }
}
