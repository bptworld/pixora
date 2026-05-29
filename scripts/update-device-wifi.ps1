param(
  [Parameter(Mandatory = $true)]
  [string]$DeviceIp,

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
  [string]$Target = "tidbyt-gen1"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$firmwarePath = Join-Path $repoRoot "dist\firmware\$Target\firmware.bin"

if (!(Test-Path -LiteralPath $firmwarePath)) {
  throw "Firmware not found at $firmwarePath. Build it first with .\scripts\build-firmware.ps1 -Target $Target"
}

$normalizedIp = $DeviceIp.Trim()
$updateUrl = if ($normalizedIp -match '^https?://') {
  "$($normalizedIp.TrimEnd('/'))/update"
} else {
  "http://$normalizedIp/update"
}

Write-Host ""
Write-Host "Updating Pixora firmware over Wi-Fi:"
Write-Host "  Target:   $Target"
Write-Host "  Device:   $updateUrl"
Write-Host "  Firmware: $firmwarePath"
Write-Host ""

$response = Invoke-WebRequest `
  -Uri $updateUrl `
  -Method Post `
  -InFile $firmwarePath `
  -ContentType "application/octet-stream" `
  -TimeoutSec 300

if ($response.StatusCode -lt 200 -or $response.StatusCode -ge 300) {
  throw "Wi-Fi update failed with HTTP $($response.StatusCode)"
}

Write-Host "Wi-Fi update sent. The device should reboot into the new firmware."

