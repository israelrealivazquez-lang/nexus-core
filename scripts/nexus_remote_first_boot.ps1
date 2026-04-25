# NEXUS remote-first boot
# Keeps the Lenovo light and routes heavy work to cloud services.

$ErrorActionPreference = "SilentlyContinue"

$Root = "C:\Nexus_Core"
$LogDir = Join-Path $Root "logs"
$LogFile = Join-Path $LogDir "remote_first_boot.log"
$AntigravityExe = "C:\Users\Lenovo\AppData\Local\Programs\Antigravity\Antigravity.exe"
$DriveLaunch = "C:\Program Files\Google\Drive File Stream\launch.bat"
$DriveStream = "C:\Users\Lenovo\Streaming de Google Drive\Mi unidad"
$AntigravityLiteArgs = @(
  "--disable-gpu",
  "--disable-extension", "ms-azuretools.vscode-containers",
  "--disable-extension", "ms-azuretools.vscode-docker",
  "--disable-extension", "ms-python.python",
  "--disable-extension", "ms-python.debugpy",
  "--disable-extension", "ms-python.vscode-python-envs",
  "--disable-extension", "ms-toolsai.jupyter",
  "--disable-extension", "ms-toolsai.jupyter-keymap",
  "--disable-extension", "ms-toolsai.jupyter-renderers",
  "--disable-extension", "ms-toolsai.vscode-jupyter-cell-tags",
  "--disable-extension", "ms-toolsai.vscode-jupyter-slideshow",
  "--disable-extension", "google.colab",
  "--disable-extension", "openai.chatgpt"
)

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

function Write-NexusLog {
  param([string]$Message)
  $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') | $Message"
  $line | Out-File -FilePath $LogFile -Append -Encoding utf8
  Write-Host $line
}

Write-NexusLog "NEXUS remote-first boot starting"

if (-not (Test-Path -LiteralPath $Root)) {
  Write-NexusLog "ERROR: Missing workspace $Root"
  exit 1
}

Set-Location $Root

if (-not (Get-Process GoogleDriveFS -ErrorAction SilentlyContinue) -and (Test-Path -LiteralPath $DriveLaunch)) {
  Write-NexusLog "Starting Google Drive Desktop"
  Start-Process -FilePath $DriveLaunch -WindowStyle Hidden
  Start-Sleep -Seconds 8
}

$driveOk = Test-Path -LiteralPath $DriveStream
$gOk = Test-Path -LiteralPath "G:\Mi unidad"
Write-NexusLog "Drive streaming path available: $driveOk"
Write-NexusLog "G: mount available: $gOk"

$freeC = [math]::Round((Get-PSDrive C).Free / 1GB, 2)
$freeRam = [math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1MB, 2)
Write-NexusLog "Free C: ${freeC}GB"
Write-NexusLog "Free RAM before trim: ${freeRam}GB"

Add-Type -TypeDefinition 'using System;using System.Runtime.InteropServices;public class NexusTrim{[DllImport("psapi.dll")]public static extern int EmptyWorkingSet(IntPtr h);}' -ErrorAction SilentlyContinue
$protected = @("System","Idle","smss","csrss","winlogon","services","lsass","svchost","wininit")
Get-Process | Where-Object { $protected -notcontains $_.Name } | ForEach-Object {
  try { [NexusTrim]::EmptyWorkingSet($_.Handle) | Out-Null } catch {}
}

Get-ChildItem $env:TEMP -File -ErrorAction SilentlyContinue |
  Where-Object { $_.LastWriteTime -lt (Get-Date).AddHours(-12) } |
  Remove-Item -Force -ErrorAction SilentlyContinue

$git = Get-Command git -ErrorAction SilentlyContinue
if ($git) {
  git -C $Root remote set-url origin "https://github.com/israelrealivazquez-lang/nexus-core.git" 2>$null
}

$gh = Get-Command gh -ErrorAction SilentlyContinue
if ($gh) {
  $oldToken = $env:GITHUB_TOKEN
  Remove-Item Env:\GITHUB_TOKEN -ErrorAction SilentlyContinue
  gh auth switch -u israelrealivazquez-lang 2>$null | Out-Null
  $codespaces = gh codespace list --limit 3 2>$null
  if ($LASTEXITCODE -eq 0) {
    Write-NexusLog "GitHub Codespaces available through gh keyring"
  } else {
    Write-NexusLog "GitHub Codespaces not available in this shell; refresh gh auth if needed"
  }
  if ($oldToken) { $env:GITHUB_TOKEN = $oldToken }
}

$docker = Get-Command docker -ErrorAction SilentlyContinue
if ($docker) {
  Write-NexusLog "Docker exists locally, but NEXUS policy is still remote devcontainers first"
} else {
  Write-NexusLog "Docker not installed locally: devcontainers must run in Codespaces"
}

if (Test-Path -LiteralPath $AntigravityExe) {
  $ag = Get-Process Antigravity -ErrorAction SilentlyContinue
  if (-not $ag) {
    Write-NexusLog "Starting Antigravity on $Root"
    Start-Process -FilePath $AntigravityExe -ArgumentList ($AntigravityLiteArgs + @("`"$Root`"")) -WindowStyle Normal
  } else {
    Write-NexusLog "Antigravity already running; requesting workspace $Root"
    Start-Process -FilePath $AntigravityExe -ArgumentList ($AntigravityLiteArgs + @("`"$Root`"")) -WindowStyle Normal
  }
}

$freeRamAfter = [math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1MB, 2)
Write-NexusLog "Free RAM after trim: ${freeRamAfter}GB"
Write-NexusLog "NEXUS remote-first boot finished"
