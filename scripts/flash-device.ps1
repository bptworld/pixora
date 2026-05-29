param(
  [Parameter(Mandatory = $true)]
  [string]$Port,

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
  [string]$Target = "tidbyt-gen1",

  [switch]$EraseConfig,

  [int]$Baud = 460800
)

$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")

function Invoke-IdfExport {
  param(
    [Parameter(Mandatory = $true)]
    [string]$IdfPath
  )

  $staleEnvVars = @(
    "IDF_PYTHON_ENV_PATH",
    "ESP_IDF_PYTHON_ENV_PATH",
    "IDF_TOOLS_EXPORT_CMD",
    "IDF_DEACTIVATE_FILE_PATH",
    "VIRTUAL_ENV",
    "PYTHONHOME"
  )
  foreach ($name in $staleEnvVars) {
    Remove-Item -Path "Env:$name" -ErrorAction SilentlyContinue
  }
  $env:PATH = (($env:PATH -split ';') | Where-Object {
    $_ -and ($_ -notmatch '\\\.espressif\\python_env\\')
  }) -join ';'

  $preferredPython = Join-Path $env:USERPROFILE ".espressif\python_env\idf5.5_py3.13_env\Scripts\python.exe"
  $activatePy = Join-Path $IdfPath "tools\activate.py"
  if ((Test-Path -LiteralPath $preferredPython) -and (Test-Path -LiteralPath $activatePy)) {
    $idfExports = & $preferredPython $activatePy --export
    . $idfExports | Out-Host
    return
  }

  $exportScript = Join-Path $IdfPath "export.ps1"
  if (!(Test-Path -LiteralPath $exportScript)) {
    throw "ESP-IDF export script not found at $exportScript"
  }
  . $exportScript | Out-Host
}

$targets = @{
  "tidbyt-gen1" = @{ Chip = "esp32"; FlashFreq = "40m"; Dist = "tidbyt-gen1"; Before = "default_reset" }
  "tidbyt-gen1_swap" = @{ Chip = "esp32"; FlashFreq = "40m"; Dist = "tidbyt-gen1_swap"; Before = "default_reset" }
  "tidbyt-gen2" = @{ Chip = "esp32"; FlashFreq = "40m"; Dist = "tidbyt-gen2"; Before = "default_reset" }
  "pixora-s3" = @{ Chip = "esp32s3"; FlashFreq = "80m"; Dist = "pixora-s3"; Before = "usb_reset" }
  "pixora-s3-wide" = @{ Chip = "esp32s3"; FlashFreq = "80m"; Dist = "pixora-s3-wide"; Before = "usb_reset" }
  "pixoticker" = @{ Chip = "esp32"; FlashFreq = "40m"; Dist = "pixoticker"; Before = "default_reset" }
  "matrixportal-s3" = @{ Chip = "esp32s3"; FlashFreq = "80m"; Dist = "matrixportal-s3"; Before = "usb_reset" }
  "matrixportal-s3-waveshare" = @{ Chip = "esp32s3"; FlashFreq = "80m"; Dist = "matrixportal-s3-waveshare"; Before = "usb_reset" }
  "matrixportal-s3-128x32" = @{ Chip = "esp32s3"; FlashFreq = "80m"; Dist = "matrixportal-s3-128x32"; Before = "usb_reset" }
}

$targetInfo = $targets[$Target]
$dist = Join-Path $root "dist\firmware\$($targetInfo.Dist)"
$appBin = Join-Path $dist "firmware.bin"
$fullBin = Join-Path $dist "merged_firmware.bin"
$bin = if ($EraseConfig) { $fullBin } else { $appBin }
$beforeReset = $targetInfo.Before
$isS3 = $targetInfo.Chip -eq "esp32s3"

if (!(Test-Path -LiteralPath $bin)) {
  throw "Build firmware first: .\scripts\build-firmware.ps1 -Target $Target"
}

if (!$env:IDF_PATH) {
  $candidate = Join-Path $root ".esp-idf"
  if (Test-Path -LiteralPath $candidate) {
    $env:IDF_PATH = $candidate
  }
}

if (!$env:IDF_PATH -or !(Test-Path -LiteralPath $env:IDF_PATH)) {
  $fallback = Join-Path $env:USERPROFILE "esp\esp-idf"
  if (Test-Path -LiteralPath $fallback) {
    $env:IDF_PATH = $fallback
  }
}

if (!$env:IDF_PATH -or !(Test-Path -LiteralPath $env:IDF_PATH)) {
  throw "ESP-IDF was not found. Run .\scripts\setup-esp-idf.ps1 first."
}

Invoke-IdfExport -IdfPath $env:IDF_PATH

Write-Host ""
Write-Host "Flashing Pixora firmware:"
Write-Host "  Target:   $Target"
Write-Host "  Port:     $Port"
Write-Host "  Firmware: $bin"
Write-Host ""

function Get-ResetModes {
  param([string]$Preferred)
  $modes = @($Preferred)
  if ($isS3) {
    $modes += @("default_reset", "no_reset")
  }
  return @($modes | Where-Object { $_ } | Select-Object -Unique)
}

function Invoke-EsptoolStep {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Label,

    [Parameter(Mandatory = $true)]
    [string[]]$ArgsAfterBefore
  )

  $lastOutput = ""
  foreach ($mode in (Get-ResetModes -Preferred $beforeReset)) {
    Write-Host "$Label using $mode..."
    $output = & esptool.py --chip $targetInfo.Chip --port $Port --baud $Baud --before $mode @ArgsAfterBefore 2>&1
    $lastOutput = ($output | Out-String).Trim()
    if ($lastOutput) {
      Write-Host $lastOutput
    }
    if ($LASTEXITCODE -eq 0) {
      return
    }
  }

  if ($isS3 -and $lastOutput -match "No serial data received|Failed to connect|Wrong boot mode|could not open port") {
    throw @"
$Label failed because the ESP32-S3 did not enter download mode.

This is common on a brand-new Adafruit MatrixPortal S3 running the factory logo/demo.

Put it in download mode, then press Update Firmware by USB again:
  1. Hold BOOT.
  2. Tap RESET once.
  3. Release BOOT.
  4. Use the COM port Windows shows after that.

Last esptool error:
$lastOutput
"@
  }

  throw "$Label failed.`n$lastOutput"
}

if ($EraseConfig) {
  Invoke-EsptoolStep -Label "Erasing existing device config" -ArgsAfterBefore @("erase_flash")
}

$afterReset = if ($isS3) { "watchdog_reset" } else { "hard_reset" }

if ($EraseConfig) {
  Invoke-EsptoolStep -Label "Factory flashing full image" -ArgsAfterBefore @("--after", $afterReset, "write_flash", "--flash_mode", "dio", "--flash_size", "8MB", "--flash_freq", $targetInfo.FlashFreq, "0x0", $bin)
} else {
  Invoke-EsptoolStep -Label "Flashing application only to both OTA slots, preserving Wi-Fi and device settings" -ArgsAfterBefore @("--after", $afterReset, "write_flash", "--flash_mode", "dio", "--flash_size", "8MB", "--flash_freq", $targetInfo.FlashFreq, "0x10000", $bin, "0x400000", $bin)
}

Write-Host "Flashed successfully."

