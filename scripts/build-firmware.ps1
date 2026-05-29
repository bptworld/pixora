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
  [string]$Target = "tidbyt-gen1",

  [string]$WifiSsid,
  [string]$WifiPassword,
  [string]$RemoteUrl,

  [switch]$Clean
)

$ErrorActionPreference = "Stop"

function Invoke-CheckedNative {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Command,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$NativeArgs
  )

  & $Command @NativeArgs
  if ($LASTEXITCODE -ne 0) {
    throw "Command failed with exit code ${LASTEXITCODE}: $Command $($NativeArgs -join ' ')"
  }
}

function Invoke-IdfExport {
  param(
    [Parameter(Mandatory = $true)]
    [string]$IdfPath,

    [Parameter(Mandatory = $true)]
    [string]$ExportScript
  )

  $preferredPython = Join-Path $env:USERPROFILE ".espressif\python_env\idf5.5_py3.13_env\Scripts\python.exe"
  if (Test-Path -LiteralPath $preferredPython) {
    $activatePy = Join-Path $IdfPath "tools\activate.py"
    $idfExports = & $preferredPython $activatePy --export
    . $idfExports | Out-Host
    return
  }

  . $ExportScript | Out-Host
}

function Get-PixoraHostname {
  param([string]$Url)

  try {
    $uri = [Uri]$Url
    $segments = $uri.AbsolutePath.Trim("/") -split "/"
    $candidate = if ($segments.Length -gt 0 -and $segments[0]) { $segments[0] } else { "pixora" }
  } catch {
    $candidate = "pixora"
  }

  $hostname = ($candidate.ToLowerInvariant() -replace '[^a-z0-9-]', '-')
  $hostname = ($hostname -replace '-+', '-').Trim('-')
  if (!$hostname) { $hostname = "pixora" }
  if ($hostname.Length -gt 32) { $hostname = $hostname.Substring(0, 32).Trim('-') }
  if (!$hostname) { $hostname = "pixora" }
  return $hostname
}

function Get-FirmwareBuildStamp {
  $versionPath = Join-Path $PSScriptRoot "..\firmware\pixora-firmware\main\version.h"
  if (Test-Path -LiteralPath $versionPath) {
    $text = Get-Content -LiteralPath $versionPath -Raw
    if ($text -match 'FIRMWARE_VERSION\s+"([^"]+)"') {
      return $Matches[1]
    }
    return (Get-Item -LiteralPath $versionPath).LastWriteTimeUtc.Ticks.ToString()
  }
  return "unknown"
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$firmwareDir = Join-Path $repoRoot "firmware\pixora-firmware"
$idfPath = Join-Path $repoRoot ".esp-idf"

if (!(Test-Path -LiteralPath $firmwareDir)) {
  throw "Firmware source not found at $firmwareDir"
}

if (!(Test-Path -LiteralPath $idfPath)) {
  $idfPath = Join-Path $env:USERPROFILE "esp\esp-idf"
}

if (!(Test-Path -LiteralPath $idfPath)) {
  $localClone = Join-Path $repoRoot ".esp-idf"
  throw "ESP-IDF was not found. Expected $localClone or $idfPath"
}

$secretsPath = Join-Path $firmwareDir "secrets.json"
$hasAnyProvisioningValue = $WifiSsid -or $WifiPassword -or $RemoteUrl

if ($hasAnyProvisioningValue) {
  if (!$WifiSsid -or !$WifiPassword -or !$RemoteUrl) {
    throw "When baking provisioning values into firmware, WifiSsid, WifiPassword, and RemoteUrl must all be supplied. Omit all three for generic setup-page firmware."
  }

  $secrets = [ordered]@{
    WIFI_SSID = $WifiSsid
    WIFI_PASSWORD = $WifiPassword
    REMOTE_URL = $RemoteUrl
    HOSTNAME = Get-PixoraHostname -Url $RemoteUrl
  }

  $secretsJson = $secrets | ConvertTo-Json -Depth 3
  Set-Content -LiteralPath $secretsPath -Value $secretsJson -Encoding UTF8
} else {
  Remove-Item -Force -LiteralPath $secretsPath -ErrorAction SilentlyContinue
}

$defaultsByTarget = @{
  "tidbyt-gen1" = @{ Chip = "esp32"; Defaults = "sdkconfig.defaults.tidbyt-gen1" }
  "tidbyt-gen1_swap" = @{ Chip = "esp32"; Defaults = "sdkconfig.defaults.tidbyt-gen1_swap" }
  "tidbyt-gen2" = @{ Chip = "esp32"; Defaults = "sdkconfig.defaults.tidbyt-gen2" }
  "pixora-s3" = @{ Chip = "esp32s3"; Defaults = "sdkconfig.defaults.pixora-s3" }
  "pixora-s3-wide" = @{ Chip = "esp32s3"; Defaults = "sdkconfig.defaults.pixora-s3-wide" }
  "pixoticker" = @{ Chip = "esp32"; Defaults = "sdkconfig.defaults.pixoticker" }
  "matrixportal-s3" = @{ Chip = "esp32s3"; Defaults = "sdkconfig.defaults.matrixportal-s3" }
  "matrixportal-s3-waveshare" = @{ Chip = "esp32s3"; Defaults = "sdkconfig.defaults.matrixportal-s3-waveshare" }
  "matrixportal-s3-128x32" = @{ Chip = "esp32s3"; Defaults = "sdkconfig.defaults.matrixportal-s3-128x32" }
}

$targetInfo = $defaultsByTarget[$Target]
$env:IDF_PATH = $idfPath

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

$exportScript = Join-Path $idfPath "export.ps1"
if (!(Test-Path -LiteralPath $exportScript)) {
  throw "ESP-IDF export script not found at $exportScript"
}

Push-Location $firmwareDir
try {
  Invoke-IdfExport -IdfPath $idfPath -ExportScript $exportScript

  $buildPath = Join-Path $firmwareDir "build"
  if (Test-Path -LiteralPath $buildPath) {
    $resolvedBuild = (Resolve-Path -LiteralPath $buildPath).Path
    $resolvedFirmware = (Resolve-Path -LiteralPath $firmwareDir).Path
    if (!$resolvedBuild.StartsWith($resolvedFirmware, [System.StringComparison]::OrdinalIgnoreCase)) {
      throw "Refusing to remove build directory outside firmware source: $resolvedBuild"
    }
    Remove-Item -Recurse -Force -LiteralPath $resolvedBuild
  }

  if ($Clean) {
    Remove-Item -Force -LiteralPath ".\sdkconfig" -ErrorAction SilentlyContinue
  }

  Remove-Item -Force -LiteralPath ".\sdkconfig" -ErrorAction SilentlyContinue

$env:IDF_TARGET = $targetInfo.Chip
$env:IDF_COMPONENT_MANAGER = "0"
Invoke-CheckedNative "idf.py" "-D" "SDKCONFIG_DEFAULTS=sdkconfig.defaults;$($targetInfo.Defaults)" "set-target" $targetInfo.Chip
Invoke-CheckedNative "idf.py" "build"

  Push-Location ".\build"
  try {
    Invoke-CheckedNative "esptool.py" "--chip" $targetInfo.Chip "merge_bin" "-o" "merged_firmware.bin" "@flash_args"
  } finally {
    Pop-Location
  }
} finally {
  Pop-Location
}

$distDir = Join-Path $repoRoot "dist\firmware\$Target"
New-Item -ItemType Directory -Force -Path $distDir | Out-Null

$filesToCopy = @(
  "build\merged_firmware.bin",
  "build\firmware.bin",
  "build\bootloader\bootloader.bin",
  "build\partition_table\partition-table.bin",
  "build\flash_args"
)

foreach ($rel in $filesToCopy) {
  $src = Join-Path $firmwareDir $rel
  if (Test-Path -LiteralPath $src) {
    Copy-Item -Force -LiteralPath $src -Destination (Join-Path $distDir (Split-Path -Leaf $src))
  }
}

$provisioningHashFiles = @(
  "provisioning.ps1.sha256",
  "provisioning.sha256"
)

foreach ($hashFile in $provisioningHashFiles) {
  Remove-Item -Force -LiteralPath (Join-Path $distDir $hashFile) -ErrorAction SilentlyContinue
}

if ($hasAnyProvisioningValue) {
  $cacheInput = "$Target`n$WifiSsid`n$WifiPassword`n$RemoteUrl`n$(Get-FirmwareBuildStamp)"
  $bytes = [System.Text.Encoding]::UTF8.GetBytes($cacheInput)
  $hash = [System.BitConverter]::ToString([System.Security.Cryptography.SHA256]::HashData($bytes)).Replace("-", "").ToLowerInvariant()
  Set-Content -LiteralPath (Join-Path $distDir "provisioning.ps1.sha256") -Value $hash -Encoding ASCII
  Set-Content -LiteralPath (Join-Path $distDir "provisioning.sha256") -Value $hash -Encoding ASCII
}

Write-Host ""
Write-Host "Pixora firmware build complete:"
Write-Host "  Target:     $Target"
if ($RemoteUrl) {
  Write-Host "  Remote URL: $RemoteUrl"
} else {
  Write-Host "  Provisioning: generic setup-page firmware"
}
Write-Host "  Output:     $distDir"


