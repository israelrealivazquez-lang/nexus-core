param(
    [string]$RepoRoot = "C:\Users\Lenovo\OneDrive\Nexus_Core",
    [string]$Branch = "main",
    [string]$Message = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Message)) {
    $Message = "snapshot " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
}

git -C $RepoRoot add -A
$status = git -C $RepoRoot status --porcelain
if ([string]::IsNullOrWhiteSpace($status)) {
    Write-Output "Sin cambios para snapshot."
    exit 0
}

git -C $RepoRoot commit -m $Message | Out-Null
git -C $RepoRoot push origin $Branch | Out-Null
Write-Output "Snapshot enviado: $Message"
