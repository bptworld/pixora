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

$scriptPath = Join-Path $PSScriptRoot "scripts\update-device-wifi.ps1"
& $scriptPath -DeviceIp $DeviceIp -Target $Target
exit $LASTEXITCODE

