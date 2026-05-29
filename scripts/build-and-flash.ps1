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

  [Parameter(Mandatory = $true)]
  [string]$WifiSsid,

  [Parameter(Mandatory = $true)]
  [string]$WifiPassword,

  [Parameter(Mandatory = $true)]
  [string]$RemoteUrl,

  [switch]$Clean
)

$ErrorActionPreference = "Stop"

function Get-PixoraSerialPort {
  $ports = Get-CimInstance Win32_PnPEntity |
    Where-Object {
      $_.Name -match "\(COM\d+\)" -and (
        $_.Name -match "CP210|Silicon Labs|USB.*Serial|UART|CH340|CH910|FTDI" -or
        $_.PNPDeviceID -match "VID_10C4|VID_1A86|VID_0403|VID_303A"
      )
    } |
    ForEach-Object {
      if ($_.Name -match "(COM\d+)") {
        [pscustomobject]@{
          Port = $Matches[1]
          Name = $_.Name
          PNPDeviceID = $_.PNPDeviceID
        }
      }
    }

  if (!$ports) {
    throw "No USB serial device was found. Plug in the display and try again."
  }

  if (@($ports).Count -gt 1) {
    $portList = ($ports | ForEach-Object { "$($_.Port) - $($_.Name)" }) -join "`n"
    throw "More than one USB serial device was found. Unplug extras or use Flash-Device.ps1 with a specific port.`n$portList"
  }

  return $ports[0]
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
$buildScript = Join-Path $repoRoot "scripts\build-firmware.ps1"
$flashScript = Join-Path $repoRoot "Flash-Device.ps1"
$distDir = Join-Path $repoRoot "dist\firmware\$Target"
$firmwarePath = Join-Path $distDir "merged_firmware.bin"
$cachePath = Join-Path $distDir "provisioning.ps1.sha256"
$cacheInput = "$Target`n$WifiSsid`n$WifiPassword`n$RemoteUrl`n$(Get-FirmwareBuildStamp)"
$bytes = [System.Text.Encoding]::UTF8.GetBytes($cacheInput)
$expectedHash = [System.BitConverter]::ToString([System.Security.Cryptography.SHA256]::HashData($bytes)).Replace("-", "").ToLowerInvariant()

Write-Host "Finding USB serial device..."
$port = Get-PixoraSerialPort
Write-Host "Using $($port.Port): $($port.Name)"

Write-Host ""
if (!$Clean -and (Test-Path -LiteralPath $firmwarePath) -and (Test-Path -LiteralPath $cachePath) -and ((Get-Content -LiteralPath $cachePath -Raw).Trim() -eq $expectedHash)) {
  Write-Host "Using cached provisioned firmware."
} else {
  Write-Host "Building provisioned firmware..."
  & $buildScript -Target $Target -WifiSsid $WifiSsid -WifiPassword $WifiPassword -RemoteUrl $RemoteUrl -Clean:$Clean
  if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
  }
}

Write-Host ""
Write-Host "Flashing over USB..."
& $flashScript -Port $port.Port -Target $Target
exit $LASTEXITCODE

