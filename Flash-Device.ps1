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

  [int]$Baud = 460800
)

$scriptPath = Join-Path $PSScriptRoot "scripts\flash-device.ps1"
& $scriptPath -Port $Port -Target $Target -Baud $Baud
exit $LASTEXITCODE

