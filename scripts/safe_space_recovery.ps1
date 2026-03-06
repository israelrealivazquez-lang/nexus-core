param(
    [switch]$IncludeChrome = $true,
    [switch]$IncludeNpm = $true,
    [switch]$IncludeOneDriveGeminiCaches = $true,
    [switch]$ForceOneDriveOnlineOnly,
    [double]$TargetFreeGb = 2.0
)

$ErrorActionPreference = "SilentlyContinue"

function Get-FreeGb {
    return [math]::Round((Get-PSDrive C).Free / 1GB, 2)
}

function Remove-PathIfExists {
    param([string]$Path)
    if (Test-Path $Path) {
        try {
            Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
            return $true
        } catch {
            return $false
        }
    }
    return $false
}

$before = Get-FreeGb
$removed = @()
$failed = @()

$targets = @()

if ($IncludeOneDriveGeminiCaches) {
    $targets += @(
        "C:\Users\Lenovo\OneDrive\.antigravity_nexus\.gemini\antigravity-browser-profile\component_crx_cache",
        "C:\Users\Lenovo\OneDrive\.antigravity_nexus\.gemini\antigravity-browser-profile\optimization_guide_model_store",
        "C:\Users\Lenovo\OneDrive\.antigravity_nexus\.gemini\antigravity-browser-profile\SODA",
        "C:\Users\Lenovo\OneDrive\.antigravity_nexus\.gemini\antigravity-browser-profile\SODALanguagePacks",
        "C:\Users\Lenovo\OneDrive\.antigravity_nexus\.gemini\antigravity-browser-profile\Safe Browsing",
        "C:\Users\Lenovo\OneDrive\.antigravity_nexus\.gemini\antigravity-browser-profile\Default\Cache",
        "C:\Users\Lenovo\OneDrive\.antigravity_nexus\.gemini\antigravity-browser-profile\Default\Code Cache",
        "C:\Users\Lenovo\OneDrive\.antigravity_nexus\.gemini\antigravity-browser-profile\Default\GPUCache",
        "C:\Users\Lenovo\OneDrive\.antigravity_nexus\.gemini\antigravity-browser-profile\Default\Service Worker\CacheStorage",
        "C:\Users\Lenovo\OneDrive\.antigravity_nexus\.gemini\antigravity-browser-profile\GrShaderCache",
        "C:\Users\Lenovo\OneDrive\.antigravity_nexus\.gemini\antigravity-browser-profile\ShaderCache",
        "C:\Users\Lenovo\OneDrive\.gemini_cloud\antigravity-browser-profile\component_crx_cache",
        "C:\Users\Lenovo\OneDrive\.gemini_cloud\antigravity-browser-profile\optimization_guide_model_store",
        "C:\Users\Lenovo\OneDrive\.gemini_cloud\antigravity-browser-profile\SODA",
        "C:\Users\Lenovo\OneDrive\.gemini_cloud\antigravity-browser-profile\SODALanguagePacks",
        "C:\Users\Lenovo\OneDrive\.gemini_cloud\antigravity-browser-profile\Safe Browsing",
        "C:\Users\Lenovo\OneDrive\.gemini_cloud\antigravity-browser-profile\Default\Cache",
        "C:\Users\Lenovo\OneDrive\.gemini_cloud\antigravity-browser-profile\Default\Code Cache",
        "C:\Users\Lenovo\OneDrive\.gemini_cloud\antigravity-browser-profile\Default\GPUCache",
        "C:\Users\Lenovo\OneDrive\.gemini_cloud\antigravity-browser-profile\Default\Service Worker\CacheStorage",
        "C:\Users\Lenovo\OneDrive\.gemini_cloud\antigravity-browser-profile\GrShaderCache",
        "C:\Users\Lenovo\OneDrive\.gemini_cloud\antigravity-browser-profile\ShaderCache"
    )
}

if ($IncludeChrome) {
    $targets += @(
        "C:\Users\Lenovo\AppData\Local\Google\Chrome\User Data\optimization_guide_model_store",
        "C:\Users\Lenovo\AppData\Local\Google\Chrome\User Data\SODA",
        "C:\Users\Lenovo\AppData\Local\Google\Chrome\User Data\SODALanguagePacks",
        "C:\Users\Lenovo\AppData\Local\Google\Chrome\User Data\Safe Browsing",
        "C:\Users\Lenovo\AppData\Local\Google\Chrome\User Data\GrShaderCache",
        "C:\Users\Lenovo\AppData\Local\Google\Chrome\User Data\ShaderCache",
        "C:\Users\Lenovo\AppData\Local\Google\Chrome\User Data\WasmTtsEngine"
    )
}

if ($IncludeNpm) {
    $targets += @(
        "C:\Users\Lenovo\AppData\Local\npm-cache\_cacache",
        "C:\Users\Lenovo\AppData\Local\npm-cache\_logs"
    )
}

foreach ($t in $targets) {
    if (Remove-PathIfExists -Path $t) {
        $removed += $t
    } elseif (Test-Path $t) {
        $failed += $t
    }
}

# Optional: force OneDrive heavy folders to online-only (no remote deletion).
if ($ForceOneDriveOnlineOnly) {
    foreach ($od in @(
        "C:\Users\Lenovo\OneDrive\.antigravity_nexus",
        "C:\Users\Lenovo\OneDrive\.gemini_cloud"
    )) {
        if (Test-Path $od) {
            attrib -P +U "$od\*" /S /D | Out-Null
        }
    }
}

$after = Get-FreeGb
$recovered = [math]::Round($after - $before, 2)
$state = if ($after -ge $TargetFreeGb) { "target_reached" } else { "below_target" }

$repoRoot = "C:\Users\Lenovo\OneDrive\Nexus_Core"
$logsDir = Join-Path $repoRoot "logs"
New-Item -ItemType Directory -Path $logsDir -Force | Out-Null

$report = [ordered]@{
    timestamp = (Get-Date).ToString("s")
    free_before_gb = $before
    free_after_gb = $after
    recovered_gb = $recovered
    target_free_gb = $TargetFreeGb
    state = $state
    removed_count = $removed.Count
    failed_count = $failed.Count
    removed = $removed
    failed = $failed
}

$jsonPath = Join-Path $logsDir "space_recovery_last.json"
$report | ConvertTo-Json -Depth 6 | Set-Content -Path $jsonPath -Encoding UTF8

Write-Output "Free before: $before GB"
Write-Output "Free after:  $after GB"
Write-Output "Recovered:   $recovered GB"
Write-Output "State:       $state"
Write-Output "Report:      $jsonPath"
