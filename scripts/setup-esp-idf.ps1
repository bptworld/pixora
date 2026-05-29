param(
  [string]$Version = "v5.5.2"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$idfPath = Join-Path $repoRoot ".esp-idf"

if (!(Test-Path -LiteralPath $idfPath)) {
  git clone --depth 1 --branch $Version --recursive https://github.com/espressif/esp-idf.git $idfPath
} else {
  Write-Host "ESP-IDF already exists at $idfPath"
}

git -C $idfPath submodule update --init --recursive --jobs 8

$env:IDF_TOOLS_PATH = Join-Path $env:USERPROFILE ".espressif"
& (Join-Path $idfPath "install.bat") esp32,esp32s3

$py = Join-Path $env:IDF_TOOLS_PATH "python_env\idf5.5_py3.13_env\Scripts\python.exe"
$constraints = Join-Path $env:IDF_TOOLS_PATH "espidf.constraints.v5.5.txt"
$requirements = Join-Path $idfPath "tools\requirements\requirements.core.txt"

if ((Test-Path -LiteralPath $py) -and (Test-Path -LiteralPath $constraints)) {
  & $py -m pip install --upgrade --force-reinstall --constraint $constraints -r $requirements
}

Write-Host "ESP-IDF setup complete."

