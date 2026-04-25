# NEXUS cloud dispatcher
# Runs cloud work without opening a browser or requiring local Docker.

param(
  [ValidateSet("health-check", "process-data", "compile-thesis", "clean-artifacts", "hf-job", "gcloud-health", "drive-index", "dashboard-publish", "list-codespaces")]
  [string]$Task = "health-check",
  [string]$Ref = "main",
  [string]$ChapterRange = "1-40",
  [int]$Limit = 10
)

$ErrorActionPreference = "Stop"
$Root = "C:\Nexus_Core"
Set-Location $Root

function Write-Nexus {
  param([string]$Message)
  Write-Host "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') | $Message"
}

$gh = Get-Command gh -ErrorAction SilentlyContinue
if (-not $gh) {
  throw "GitHub CLI is required. Install gh first, then rerun this script."
}

$oldToken = $env:GITHUB_TOKEN
Remove-Item Env:\GITHUB_TOKEN -ErrorAction SilentlyContinue

try {
  $oldPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  gh auth switch -u israelrealivazquez-lang *> $null
  $ErrorActionPreference = $oldPreference
  if ($LASTEXITCODE -ne 0) {
    Write-Nexus "Could not switch gh account automatically; continuing with current gh account"
  }

  gh auth status -h github.com

  if ($Task -eq "list-codespaces") {
    Write-Nexus "Listing remote Codespaces. Local Docker stays unused."
    gh codespace list --limit $Limit
    return
  }

  Write-Nexus "Dispatching GitHub Actions task '$Task' on ref '$Ref'"
  gh workflow run nexus-cloud-engine.yml --ref $Ref -f task=$Task -f chapter_range=$ChapterRange

  Write-Nexus "Recent Nexus Remote Engine runs"
  gh run list --workflow nexus-cloud-engine.yml --limit 5
}
finally {
  if ($oldToken) { $env:GITHUB_TOKEN = $oldToken }
}
