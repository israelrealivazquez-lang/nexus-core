param(
    [string]$RepoRoot = "C:\Users\Lenovo\OneDrive\Nexus_Core",
    [double]$MinFreeGb = 1.0
)

$ErrorActionPreference = "SilentlyContinue"

function Resolve-PythonPath {
    $candidates = @(
        "python",
        "py -3",
        "C:\Users\Lenovo\AppData\Local\Google\Cloud SDK\google-cloud-sdk\platform\bundledpython\python.exe"
    )

    foreach ($candidate in $candidates) {
        if ($candidate -eq "python") {
            $cmd = Get-Command python -ErrorAction SilentlyContinue
            if ($cmd) {
                $out = & python --version 2>$null
                if ($LASTEXITCODE -eq 0) { return @{ cmd = "python"; version = $out } }
            }
            continue
        }
        if ($candidate -eq "py -3") {
            $out = & py -3 --version 2>$null
            if ($LASTEXITCODE -eq 0) { return @{ cmd = "py -3"; version = $out } }
            continue
        }
        if (Test-Path $candidate) {
            $out = & $candidate --version 2>$null
            if ($LASTEXITCODE -eq 0) { return @{ cmd = $candidate; version = $out } }
        }
    }
    return $null
}

function Get-CommandStatus {
    param([string]$Name)
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if ($cmd) {
        return @{ name = $Name; status = "ok"; path = $cmd.Source }
    }
    return @{ name = $Name; status = "missing"; path = $null }
}

$drive = Get-PSDrive -Name C
$freeGb = [math]::Round($drive.Free / 1GB, 2)
$diskState = if ($freeGb -lt $MinFreeGb) { "critical" } else { "ok" }

$bridgeHealth = "down"
$hubHealth = "down"
try {
    $bridgeRes = Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8765/health -TimeoutSec 3
    if ($bridgeRes.StatusCode -eq 200) { $bridgeHealth = "up" }
} catch {}
try {
    $hubRes = Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8501 -TimeoutSec 3
    if ($hubRes.StatusCode -eq 200) { $hubHealth = "up" }
} catch {}

$python = Resolve-PythonPath
$commands = @(
    Get-CommandStatus "gh"
    Get-CommandStatus "gcloud"
    Get-CommandStatus "rclone"
    Get-CommandStatus "oci"
    Get-CommandStatus "huggingface-cli"
    Get-CommandStatus "npm"
)

$gitBranch = ""
$gitStatus = ""
if (Test-Path "$RepoRoot\.git") {
    $gitBranch = (git -C $RepoRoot rev-parse --abbrev-ref HEAD 2>$null)
    $gitStatus = (git -C $RepoRoot status -sb 2>$null | Out-String).Trim()
}

$oneDrive = Get-Process OneDrive -ErrorAction SilentlyContinue | Select-Object -First 1

$report = [ordered]@{
    timestamp = (Get-Date).ToString("s")
    disk = @{
        c_free_gb = $freeGb
        c_state = $diskState
        min_free_gb = $MinFreeGb
    }
    services = @{
        bridge_8765 = $bridgeHealth
        hub_8501 = $hubHealth
        onedrive = if ($oneDrive) { "running" } else { "stopped" }
    }
    python = if ($python) { $python } else { @{ cmd = $null; version = $null } }
    commands = $commands
    git = @{
        repo = $RepoRoot
        branch = $gitBranch
        status = $gitStatus
    }
}

$logsDir = Join-Path $RepoRoot "logs"
New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
$jsonPath = Join-Path $logsDir "ops_status.json"
$report | ConvertTo-Json -Depth 6 | Set-Content -Path $jsonPath -Encoding UTF8

$md = @()
$md += "# Nexus Ops Status"
$md += ""
$md += "- Timestamp: $($report.timestamp)"
$md += "- C free: $freeGb GB ($diskState)"
$md += "- Bridge 8765: $bridgeHealth"
$md += "- Hub 8501: $hubHealth"
$md += "- OneDrive: $($report.services.onedrive)"
$md += "- Python: $($report.python.cmd) $($report.python.version)"
$md += ""
$md += "## Commands"
foreach ($c in $commands) {
    $md += "- $($c.name): $($c.status) $($c.path)"
}
$md += ""
$md += "## Git"
$md += "- Branch: $gitBranch"
$md += '```'
$md += $gitStatus
$md += '```'

$mdPath = Join-Path $logsDir "ops_status.md"
$md | Set-Content -Path $mdPath -Encoding UTF8

Write-Output "Status report: $jsonPath"
Write-Output "Status summary: $mdPath"
