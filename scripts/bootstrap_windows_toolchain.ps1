param(
    [string]$RepoRoot = "C:\Users\Lenovo\OneDrive\Nexus_Core",
    [switch]$WriteLocalNomadConfig = $true
)

$ErrorActionPreference = "SilentlyContinue"

function Test-Python {
    param([string]$Command, [switch]$IsPath)
    if ($IsPath) {
        if (-not (Test-Path $Command)) { return $null }
        $out = & $Command --version 2>$null
        if ($LASTEXITCODE -eq 0) { return @{ cmd = $Command; version = $out } }
        return $null
    }

    if ($Command -eq "python") {
        $cmd = Get-Command python -ErrorAction SilentlyContinue
        if ($cmd) {
            $out = & python --version 2>$null
            if ($LASTEXITCODE -eq 0) { return @{ cmd = "python"; version = $out } }
        }
        return $null
    }
    if ($Command -eq "py -3") {
        $out = & py -3 --version 2>$null
        if ($LASTEXITCODE -eq 0) { return @{ cmd = "py -3"; version = $out } }
        return $null
    }
    return $null
}

function Resolve-Python {
    $candidates = @(
        @{ val = "python"; isPath = $false },
        @{ val = "py -3"; isPath = $false },
        @{ val = "C:\Users\Lenovo\AppData\Local\Google\Cloud SDK\google-cloud-sdk\platform\bundledpython\python.exe"; isPath = $true }
    )
    foreach ($c in $candidates) {
        $r = Test-Python -Command $c.val -IsPath:$c.isPath
        if ($r) { return $r }
    }
    return $null
}

function Ensure-Command {
    param([string]$Name)
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if ($cmd) {
        return @{ name = $Name; status = "ok"; path = $cmd.Source }
    }
    return @{ name = $Name; status = "missing"; path = $null }
}

$python = Resolve-Python
if (-not $python) {
    Write-Output "No usable Python found. Install Python 3.11+ or keep Cloud SDK bundled python available."
    exit 1
}

[Environment]::SetEnvironmentVariable("NEXUS_PYTHON", $python.cmd, "User")

$statuses = @(
    Ensure-Command "gh"
    Ensure-Command "gcloud"
    Ensure-Command "rclone"
    Ensure-Command "oci"
    Ensure-Command "huggingface-cli"
)

$summary = [ordered]@{
    timestamp = (Get-Date).ToString("s")
    python = $python
    commands = $statuses
}

if ($WriteLocalNomadConfig) {
    $examplePath = Join-Path $RepoRoot "configs\nomad_config.example.json"
    $targetPath = Join-Path $RepoRoot "configs\nomad_config.json"
    if (Test-Path $examplePath) {
        $cfg = Get-Content -Raw $examplePath | ConvertFrom-Json

        $backupCmd = if ($python.cmd -like "* *") { "`"$($python.cmd)`" scripts/auto_backup.py --once" } else { "$($python.cmd) scripts/auto_backup.py --once" }
        $restoreCmd = if ($python.cmd -like "* *") { "`"$($python.cmd)`" scripts/auto_restore.py" } else { "$($python.cmd) scripts/auto_restore.py" }

        $cfg.backup_command = $backupCmd
        $cfg.restore_command = $restoreCmd

        $cfg | ConvertTo-Json -Depth 10 | Set-Content -Path $targetPath -Encoding UTF8
        $summary["nomad_config"] = $targetPath
    }
}

$logsDir = Join-Path $RepoRoot "logs"
New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
$summaryPath = Join-Path $logsDir "bootstrap_windows_toolchain.json"
$summary | ConvertTo-Json -Depth 8 | Set-Content -Path $summaryPath -Encoding UTF8

Write-Output "Python selected: $($python.cmd) ($($python.version))"
Write-Output "Saved NEXUS_PYTHON (User env)."
Write-Output "Summary: $summaryPath"
