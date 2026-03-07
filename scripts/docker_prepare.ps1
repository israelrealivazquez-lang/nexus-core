param(
    [string]$RepoRoot = "C:\Users\Lenovo\OneDrive\Nexus_Core",
    [string]$DataRoot = "D:\AntigravityData",
    [switch]$CreateEnvIfMissing = $true
)

$ErrorActionPreference = "Stop"

function Ensure-Dir {
    param([string]$Path)
    if (-not (Test-Path $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

Ensure-Dir $DataRoot
foreach ($sub in @("antigravity", "backups", "logs", "datasets", "cache")) {
    Ensure-Dir (Join-Path $DataRoot $sub)
}

$envPath = Join-Path $RepoRoot ".env"
if (-not (Test-Path $envPath) -and $CreateEnvIfMissing) {
    Copy-Item (Join-Path $RepoRoot ".env.template") $envPath -Force
}

if (Test-Path $envPath) {
    $content = Get-Content -Raw $envPath
    if ($content -notmatch "(?m)^NEXUS_DATA_HOST=") {
        Add-Content -Path $envPath -Value "`r`nNEXUS_DATA_HOST=$DataRoot"
    } else {
        $updated = [regex]::Replace($content, "(?m)^NEXUS_DATA_HOST=.*$", "NEXUS_DATA_HOST=$DataRoot")
        Set-Content -Path $envPath -Value $updated -Encoding UTF8
    }
}

$docker = Get-Command docker -ErrorAction SilentlyContinue
if (-not $docker) {
    Write-Output "Docker no instalado. Instala Docker Desktop y vuelve a ejecutar."
    Write-Output "winget install -e --id Docker.DockerDesktop"
    exit 0
}

Write-Output "Preparacion completada."
Write-Output "Data root: $DataRoot"
Write-Output "Siguiente:"
Write-Output "  docker compose -f `"$RepoRoot\\docker-compose.nexus.yml`" up -d"
