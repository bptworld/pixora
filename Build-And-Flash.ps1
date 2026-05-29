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

$scriptPath = Join-Path $PSScriptRoot "scripts\build-and-flash.ps1"
& $scriptPath -Target $Target -WifiSsid $WifiSsid -WifiPassword $WifiPassword -RemoteUrl $RemoteUrl -Clean:$Clean
exit $LASTEXITCODE

