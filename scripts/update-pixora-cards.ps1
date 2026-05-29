param(
  [switch]$Publish,
  [switch]$IncludeRegistry,
  [switch]$GeneratePreviews,
  [string]$CommitMessage = "Update Pixora cards",
  [string]$CardsRepoPath = ""
)

$ErrorActionPreference = "Stop"

$sourceRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
if (!$CardsRepoPath) {
  $CardsRepoPath = Join-Path $sourceRoot "cards"
}

$script = Join-Path $CardsRepoPath "scripts\update-from-pixora.ps1"
if (!(Test-Path -LiteralPath $script)) {
  throw "Card update script not found: $script"
}

& $script `
  -SourceRoot $sourceRoot `
  -Publish:$Publish `
  -IncludeRegistry:$IncludeRegistry `
  -GeneratePreviews:$GeneratePreviews `
  -CommitMessage $CommitMessage
