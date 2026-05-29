param(
  [string]$SourceRoot = "",
  [switch]$Publish,
  [switch]$IncludeRegistry,
  [switch]$GeneratePreviews,
  [string]$CommitMessage = "Update Pixora cards"
)

$ErrorActionPreference = "Stop"

$cardsRepo = Resolve-Path (Join-Path $PSScriptRoot "..")
if (!$SourceRoot) {
  $SourceRoot = Resolve-Path (Join-Path $cardsRepo "..")
} else {
  $SourceRoot = Resolve-Path -LiteralPath $SourceRoot
}

function Invoke-Step {
  param(
    [string]$Label,
    [scriptblock]$Script
  )

  Write-Host ""
  Write-Host "==> $Label"
  & $Script
  if ($LASTEXITCODE -ne 0) {
    throw "$Label failed with exit code $LASTEXITCODE"
  }
}

function Assert-File {
  param([string]$Path)
  if (!(Test-Path -LiteralPath $Path)) {
    throw "Expected file not found: $Path"
  }
}

function Get-RegistryCardCount {
  param([string]$Path)
  if (!(Test-Path -LiteralPath $Path)) {
    return 0
  }
  $json = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
  return @($json.cards).Count
}

function Copy-IfPresent {
  param(
    [string]$RelativePath,
    [switch]$Required
  )

  $source = Join-Path $SourceRoot $RelativePath
  $dest = Join-Path $cardsRepo $RelativePath
  if (!(Test-Path -LiteralPath $source)) {
    if ($Required) {
      throw "Required source file not found: $source"
    }
    return
  }

  $destDir = Split-Path -Parent $dest
  New-Item -ItemType Directory -Force -Path $destDir | Out-Null
  Copy-Item -LiteralPath $source -Destination $dest -Force
}

function Assert-UnderPath {
  param(
    [string]$Child,
    [string]$Parent
  )

  $childFull = [System.IO.Path]::GetFullPath($Child)
  $parentFull = [System.IO.Path]::GetFullPath($Parent)
  if (!$parentFull.EndsWith([System.IO.Path]::DirectorySeparatorChar)) {
    $parentFull += [System.IO.Path]::DirectorySeparatorChar
  }
  if (!$childFull.StartsWith($parentFull, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to modify path outside cards checkout: $childFull"
  }
}

function Sync-Directory {
  param(
    [string]$RelativePath,
    [switch]$Required
  )

  $source = Join-Path $SourceRoot $RelativePath
  $dest = Join-Path $cardsRepo $RelativePath
  if (!(Test-Path -LiteralPath $source)) {
    if ($Required) {
      throw "Required source directory not found: $source"
    }
    return
  }

  Assert-UnderPath -Child $dest -Parent $cardsRepo
  if (Test-Path -LiteralPath $dest) {
    Remove-Item -LiteralPath $dest -Recurse -Force
  }
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dest) | Out-Null
  Copy-Item -LiteralPath $source -Destination $dest -Recurse -Force
}

function Convert-TextFilesToLf {
  param([string[]]$RelativePaths)

  $textExtensions = @(".json", ".md", ".ps1", ".py", ".yaml", ".yml")
  foreach ($relativePath in $RelativePaths) {
    $path = Join-Path $cardsRepo $relativePath
    if (!(Test-Path -LiteralPath $path)) {
      continue
    }

    $item = Get-Item -LiteralPath $path
    $files = if ($item.PSIsContainer) {
      Get-ChildItem -LiteralPath $path -Recurse -File
    } else {
      @($item)
    }

    foreach ($file in $files) {
      if ($textExtensions -notcontains $file.Extension.ToLowerInvariant()) {
        continue
      }
      $text = [System.IO.File]::ReadAllText($file.FullName)
      $normalized = $text -replace "`r`n", "`n" -replace "`r", "`n"
      if ($normalized -ne $text) {
        $utf8NoBom = [System.Text.UTF8Encoding]::new($false)
        [System.IO.File]::WriteAllText($file.FullName, $normalized, $utf8NoBom)
      }
    }
  }
}

Invoke-Step "Update card repo checkout" {
  Push-Location $cardsRepo
  try {
    git status -sb
    git pull --ff-only
  } finally {
    Pop-Location
  }
}

Push-Location $cardsRepo
try {
  $dirty = git status --porcelain
  if ($dirty) {
    throw "Card repo checkout has uncommitted changes. Commit or clear them before syncing."
  }

  Assert-File (Join-Path $SourceRoot "addons")
  Sync-Directory -RelativePath "addons" -Required
  Get-ChildItem -Path (Join-Path $cardsRepo "addons") -Directory -Filter "__pycache__" -Recurse -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

  Copy-IfPresent -RelativePath "card_utils.py" -Required
  Copy-IfPresent -RelativePath "event_sport_utils.py" -Required
  Copy-IfPresent -RelativePath "Pixora-Codex-Card-Brief.md"
  foreach ($assetDir in @("assets\airlines", "assets\fonts", "assets\previews")) {
    Sync-Directory -RelativePath $assetDir
  }

  if ($IncludeRegistry) {
    $sourceRegistry = Join-Path $SourceRoot "registry.json"
    $publicRegistry = Join-Path $cardsRepo "registry.json"
    $sourceCount = Get-RegistryCardCount -Path $sourceRegistry
    $publicCount = Get-RegistryCardCount -Path $publicRegistry
    if ($sourceCount -lt $publicCount) {
      throw "Refusing to replace public registry ($publicCount cards) with smaller source registry ($sourceCount cards)."
    }
    Copy-IfPresent -RelativePath "registry.json" -Required
  } else {
    Write-Host "Registry left unchanged. Use -IncludeRegistry only when the source registry is the public catalog."
  }

  $textPaths = @("addons", "assets\airlines", "card_utils.py", "event_sport_utils.py", "Pixora-Codex-Card-Brief.md")
  if ($IncludeRegistry) {
    $textPaths += "registry.json"
  }
  Convert-TextFilesToLf -RelativePaths $textPaths

  if ($GeneratePreviews) {
    Invoke-Step "Generate card previews" {
      python (Join-Path $cardsRepo "scripts\generate-card-previews.py")
    }
  }

  Invoke-Step "Compile cards" {
    $files = Get-ChildItem -Path (Join-Path $cardsRepo "addons") -Filter "*.py" -File
    python -m py_compile (Join-Path $cardsRepo "card_utils.py") (Join-Path $cardsRepo "event_sport_utils.py") @($files.FullName)
    Write-Host "Compiled $($files.Count) cards plus shared utilities."
  }

  git add addons assets/airlines assets/fonts assets/previews card_utils.py event_sport_utils.py Pixora-Codex-Card-Brief.md
  if ($IncludeRegistry) {
    git add registry.json
  }
  if ($GeneratePreviews) {
    git add assets/previews
  }

  $changes = git status --porcelain
  if (!$changes) {
    Write-Host ""
    Write-Host "Pixora cards already match the source files."
    return
  }

  git status -sb
  git commit -m $CommitMessage
  if ($LASTEXITCODE -ne 0) {
    throw "Could not commit card updates."
  }

  if ($Publish) {
    git push origin main
    if ($LASTEXITCODE -ne 0) {
      throw "Could not push card updates."
    }
  } else {
    Write-Host ""
    Write-Host "Card update commit created locally. Re-run with -Publish to push it."
  }
} finally {
  Pop-Location
}
