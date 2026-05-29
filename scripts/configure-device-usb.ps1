param(
  [Parameter(Mandatory = $true)]
  [string]$Port,

  [Parameter(Mandatory = $true)]
  [string]$WifiSsid,

  [Parameter(Mandatory = $true)]
  [string]$WifiPassword,

  [Parameter(Mandatory = $true)]
  [string]$RemoteUrl,

  [string]$Hostname = "",

  [switch]$SwapColors
)

$ErrorActionPreference = "Stop"

$payload = @{
  wifiSsid = $WifiSsid
  wifiPassword = $WifiPassword
  imageUrl = $RemoteUrl
  hostname = $Hostname
  swapColors = [bool]$SwapColors
} | ConvertTo-Json -Compress

$line = "PIXORA_CONFIG $payload`n"

function Get-SerialCandidates {
  param([string]$PreferredPort)

  $ports = @()
  if ($PreferredPort) {
    $ports += $PreferredPort.ToUpperInvariant()
  }

  try {
    $ports += Get-CimInstance Win32_PnPEntity |
      Where-Object {
        $_.Name -match "\(COM\d+\)" -and (
          $_.PNPDeviceID -match "VID_303A|VID_239A|VID_10C4|VID_1A86|VID_0403" -or
          $_.Name -match "USB Serial|CP210|Silicon Labs|CH340|CH910|FTDI|UART"
        )
      } |
      ForEach-Object {
        if ($_.Name -match "(COM\d+)") { $Matches[1].ToUpperInvariant() }
      }
  } catch {
  }

  return @($ports | Where-Object { $_ } | Select-Object -Unique)
}

function Send-ConfigToPort {
  param([string]$CandidatePort)

  $serial = [System.IO.Ports.SerialPort]::new($CandidatePort, 115200, [System.IO.Ports.Parity]::None, 8, [System.IO.Ports.StopBits]::One)
  $serial.NewLine = "`n"
  $serial.ReadTimeout = 350
  $serial.WriteTimeout = 2000

  try {
    try {
      $serial.Open()
    } catch {
      return @{ Ok = $false; Response = ""; Error = $_.Exception.Message }
    }

    Start-Sleep -Milliseconds 900
    try { $serial.DiscardInBuffer() } catch {}

    $deadline = [DateTime]::UtcNow.AddSeconds(18)
    $nextWrite = [DateTime]::UtcNow
    $response = ""
    while ([DateTime]::UtcNow -lt $deadline) {
      try {
        $response += $serial.ReadExisting()
      } catch {
      }

      if ($response -match "PIXORA_CONFIG_SAVED") {
        return @{ Ok = $true; Response = $response; Error = "" }
      }
      if ($response -match "PIXORA_CONFIG_ERROR|PIXORA_CONFIG_SAVE_FAILED") {
        return @{ Ok = $false; Response = $response; Error = "Device rejected USB setup." }
      }

      if ([DateTime]::UtcNow -ge $nextWrite) {
        try {
          $serial.Write($line)
        } catch {
          return @{ Ok = $false; Response = $response; Error = $_.Exception.Message }
        }
        $nextWrite = [DateTime]::UtcNow.AddSeconds(2)
      }

      Start-Sleep -Milliseconds 200
    }

    return @{ Ok = $false; Response = $response; Error = "" }
  } finally {
    if ($serial.IsOpen) {
      $serial.Close()
    }
  }
}

$deadline = [DateTime]::UtcNow.AddSeconds(90)
$lastResponse = ""
$lastError = ""

while ([DateTime]::UtcNow -lt $deadline) {
  foreach ($candidate in (Get-SerialCandidates -PreferredPort $Port)) {
    Write-Host "Trying USB setup on $candidate..."
    $result = Send-ConfigToPort -CandidatePort $candidate
    $lastResponse = $result.Response
    $lastError = $result.Error
    if ($result.Ok) {
      Write-Host "Wi-Fi settings saved over USB. Device is rebooting."
      exit 0
    }
    if ($lastError -and $lastError -match "Device rejected") {
      throw "$lastError Response: $lastResponse"
    }
  }
  Start-Sleep -Seconds 2
}

throw "No confirmation from device. Last error: $lastError Response: $lastResponse"
