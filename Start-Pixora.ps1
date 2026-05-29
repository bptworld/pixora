param(
  [int]$Port = 8088
)

$ErrorActionPreference = "Stop"

$python = Get-Command python -ErrorAction SilentlyContinue
if (!$python) {
  throw "Python was not found. Install Python or open Pixora through any local web server."
}

& $python.Source -c "import zeroconf" 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host "Installing Pixora mDNS support..."
  & $python.Source -m pip install zeroconf
}

$url = "http://pixora.local:$Port/"
$healthUrl = "http://127.0.0.1:$Port/"
$serverScript = Join-Path $PSScriptRoot "pixora_server.py"
$arguments = @($serverScript, "$Port", "--no-browser")

$existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
foreach ($connection in $existing) {
  Stop-Process -Id $connection.OwningProcess -Force -ErrorAction SilentlyContinue
}

Start-Process `
  -FilePath $python.Source `
  -ArgumentList $arguments `
  -WorkingDirectory $PSScriptRoot `
  -WindowStyle Hidden

$started = $false
for ($i = 0; $i -lt 60; $i++) {
  try {
    $response = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 1
    if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
      $started = $true
      break
    }
  } catch {
    Start-Sleep -Milliseconds 250
  }
}

if (!$started) {
  throw "Pixora did not answer on $healthUrl. Check that the server process is still running."
}

Start-Process -FilePath "cmd.exe" -ArgumentList @("/c", "start", '""', $url) -WindowStyle Hidden

Write-Host "Pixora is running at $url"
