# NEXUS control plane
# Local cockpit for remote-first compute. Heavy work is dispatched to cloud services.

param(
  [ValidateSet("measure", "repair-local", "dispatch-github", "dispatch-hf", "dispatch-gcloud", "drive-report", "full-health")]
  [string]$Command = "measure",
  [ValidateSet("health-check", "process-data", "compile-thesis", "clean-artifacts", "hf-job", "gcloud-health", "drive-index", "dashboard-publish")]
  [string]$RemoteTask = "health-check",
  [string]$Ref = "main",
  [switch]$Aggressive,
  [switch]$RunRemote,
  [int]$TopProcesses = 20
)

$ErrorActionPreference = "Continue"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$LogRoot = Join-Path $RepoRoot "logs\control_plane"
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
New-Item -ItemType Directory -Force -Path $LogRoot | Out-Null

function Write-Nexus {
  param([string]$Message)
  Write-Host "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') | $Message"
}

function Save-Report {
  param(
    [string]$Name,
    [object]$Data
  )
  $jsonPath = Join-Path $LogRoot "${Timestamp}_${Name}.json"
  $mdPath = Join-Path $LogRoot "${Timestamp}_${Name}.md"
  $Data | ConvertTo-Json -Depth 8 | Out-File -FilePath $jsonPath -Encoding utf8
  @(
    "# NEXUS $Name"
    ""
    "Generated: $(Get-Date -Format s)"
    ""
    '```json'
    ($Data | ConvertTo-Json -Depth 8)
    '```'
  ) | Out-File -FilePath $mdPath -Encoding utf8
  [pscustomobject]@{ Json = $jsonPath; Markdown = $mdPath }
}

function Get-ToolStatus {
  $commands = @("gh","git","gcloud","gsutil","firebase","wrangler","netlify","circleci","hf","huggingface-cli","colab","jupyter","python","node","npm","npx","docker","rclone","oci","az","aws")
  foreach ($cmd in $commands) {
    $found = Get-Command $cmd -ErrorAction SilentlyContinue
    [pscustomobject]@{
      command = $cmd
      available = [bool]$found
      path = if ($found) { $found.Source } else { $null }
    }
  }
}

function Get-SystemSnapshot {
  $os = Get-CimInstance Win32_OperatingSystem
  $cs = Get-CimInstance Win32_ComputerSystem
  $cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
  $top = Get-Process |
    Sort-Object WorkingSet64 -Descending |
    Select-Object -First $TopProcesses @{N="name";E={$_.ProcessName}}, Id, @{N="ram_mb";E={[math]::Round($_.WorkingSet64 / 1MB, 1)}}, @{N="cpu_s";E={[math]::Round(($_.CPU), 1)}}, Path

  [pscustomobject]@{
    time = Get-Date -Format s
    free_ram_gb = [math]::Round($os.FreePhysicalMemory / 1MB, 2)
    total_ram_gb = [math]::Round($cs.TotalPhysicalMemory / 1GB, 2)
    free_c_gb = [math]::Round((Get-PSDrive C).Free / 1GB, 2)
    free_g_gb = if (Get-PSDrive G -ErrorAction SilentlyContinue) { [math]::Round((Get-PSDrive G).Free / 1GB, 2) } else { $null }
    cpu_load_pct = $cpu.LoadPercentage
    drive_g = Test-Path "G:\Mi unidad"
    drive_stream = Test-Path "C:\Users\Lenovo\Streaming de Google Drive\Mi unidad"
    docker_available = [bool](Get-Command docker -ErrorAction SilentlyContinue)
    tools = @(Get-ToolStatus)
    top_processes = @($top)
  }
}

function Invoke-WorkingSetTrim {
  Add-Type -TypeDefinition 'using System;using System.Runtime.InteropServices;public class NexusTrim{[DllImport("psapi.dll")]public static extern int EmptyWorkingSet(IntPtr h);}' -ErrorAction SilentlyContinue
  $protected = @("System","Idle","smss","csrss","winlogon","services","lsass","svchost","wininit")
  Get-Process | Where-Object { $protected -notcontains $_.Name } | ForEach-Object {
    try { [NexusTrim]::EmptyWorkingSet($_.Handle) | Out-Null } catch {}
  }
}

function Invoke-LocalRepair {
  $before = Get-SystemSnapshot
  Write-Nexus "Trimming working sets and clearing old temp files"
  Invoke-WorkingSetTrim
  Get-ChildItem $env:TEMP -File -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddHours(-12) } |
    Remove-Item -Force -ErrorAction SilentlyContinue

  $stopped = @()
  if ($Aggressive) {
    Write-Nexus "Aggressive cleanup enabled; closing safe heavyweight helper processes"
    $safeNames = @("Antigravity","language_server_windows_x64")
    foreach ($name in $safeNames) {
      Get-Process -Name $name -ErrorAction SilentlyContinue | ForEach-Object {
        $stopped += [pscustomobject]@{ name = $_.ProcessName; id = $_.Id; ram_mb = [math]::Round($_.WorkingSet64 / 1MB, 1) }
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
      }
    }
  }

  Start-Sleep -Seconds 3
  $after = Get-SystemSnapshot
  $result = [pscustomobject]@{
    command = "repair-local"
    aggressive = [bool]$Aggressive
    before = $before
    after = $after
    delta_free_ram_gb = [math]::Round($after.free_ram_gb - $before.free_ram_gb, 2)
    stopped_processes = @($stopped)
  }
  Save-Report -Name "repair_local" -Data $result
  $result
}

function Invoke-GitHubDispatch {
  param([string]$Task)
  $oldToken = $env:GITHUB_TOKEN
  Remove-Item Env:\GITHUB_TOKEN -ErrorAction SilentlyContinue
  try {
    gh auth switch -u israelrealivazquez-lang *> $null
    $auth = gh auth status -h github.com 2>&1
    $runOutput = $null
    if ($RunRemote) {
      gh workflow run nexus-cloud-engine.yml --repo israelrealivazquez-lang/nexus-core --ref $Ref -f task=$Task -f chapter_range=1-40
      Start-Sleep -Seconds 4
    }
    $runs = gh run list --repo israelrealivazquez-lang/nexus-core --workflow nexus-cloud-engine.yml --limit 5 2>&1
    $codespaces = gh codespace list --limit 5 2>&1
    $result = [pscustomobject]@{
      command = "dispatch-github"
      task = $Task
      ref = $Ref
      run_remote = [bool]$RunRemote
      auth = @($auth)
      runs = @($runs)
      codespaces = @($codespaces)
      output = @($runOutput)
    }
    Save-Report -Name "dispatch_github" -Data $result
    $result
  }
  finally {
    if ($oldToken) { $env:GITHUB_TOKEN = $oldToken }
  }
}

function Invoke-GCloudDispatch {
  $gcloud = Get-Command gcloud -ErrorAction SilentlyContinue
  $gsutil = Get-Command gsutil -ErrorAction SilentlyContinue
  $result = [pscustomobject]@{
    command = "dispatch-gcloud"
    gcloud_available = [bool]$gcloud
    gsutil_available = [bool]$gsutil
    gcloud_config = if ($gcloud) { @(gcloud config list --format=json 2>&1) } else { @("gcloud not available") }
    auth_accounts = if ($gcloud) { @(gcloud auth list --format=json 2>&1) } else { @() }
  }
  Save-Report -Name "dispatch_gcloud" -Data $result
  $result
}

function Invoke-DriveReport {
  $paths = @(
    "G:\Mi unidad",
    "C:\Users\Lenovo\Streaming de Google Drive\Mi unidad"
  )
  $items = foreach ($path in $paths) {
    if (Test-Path $path) {
      $children = Get-ChildItem -LiteralPath $path -Force -ErrorAction SilentlyContinue | Select-Object -First 80 Name, Mode, LastWriteTime
      [pscustomobject]@{ path = $path; available = $true; sample = @($children) }
    } else {
      [pscustomobject]@{ path = $path; available = $false; sample = @() }
    }
  }
  $result = [pscustomobject]@{
    command = "drive-report"
    note = "Shallow report only. It avoids recursive downloads from streaming storage."
    paths = @($items)
    root_git_present = Test-Path "G:\.git"
  }
  Save-Report -Name "drive_report" -Data $result
  $result
}

function Invoke-HFDispatch {
  $result = [pscustomobject]@{
    command = "dispatch-hf"
    local_hf_cli = [bool](Get-Command huggingface-cli -ErrorAction SilentlyContinue)
    policy = "Use Codex Hugging Face connector or remote runners. Do not install local HF tooling on the Lenovo by default."
    recommended_remote_task = "Use HF Jobs for corpus NLP, embeddings, batch parsing, and report generation."
  }
  Save-Report -Name "dispatch_hf" -Data $result
  $result
}

switch ($Command) {
  "measure" { Save-Report -Name "measure" -Data (Get-SystemSnapshot) }
  "repair-local" { Invoke-LocalRepair }
  "dispatch-github" { Invoke-GitHubDispatch -Task $RemoteTask }
  "dispatch-hf" { Invoke-HFDispatch }
  "dispatch-gcloud" { Invoke-GCloudDispatch }
  "drive-report" { Invoke-DriveReport }
  "full-health" {
    $measure = Get-SystemSnapshot
    $repair = Invoke-LocalRepair
    $github = Invoke-GitHubDispatch -Task $RemoteTask
    $hf = Invoke-HFDispatch
    $gcloud = Invoke-GCloudDispatch
    $drive = Invoke-DriveReport
    Save-Report -Name "full_health" -Data ([pscustomobject]@{
      command = "full-health"
      measure = $measure
      repair = $repair
      github = $github
      hf = $hf
      gcloud = $gcloud
      drive = $drive
    })
  }
}
