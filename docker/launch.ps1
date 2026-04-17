# PRIDE Metadata Extraction -- Docker Launcher (Windows)
# Detects GPU availability, selects the appropriate model, and starts
# the extraction pipeline with a local LLM sidecar.
#
# Usage:
#   .\docker\launch.ps1              # auto-detect GPU
#   .\docker\launch.ps1 -CpuOnly     # force CPU mode (8B model)
#   .\docker\launch.ps1 -Gpu         # force GPU mode (35B model)

param(
    [switch]$CpuOnly,
    [switch]$Gpu,
    [switch]$Help
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir

$GpuModel = "qwen3:35b-a3b-q4_K_M"
$CpuModel = "qwen3:8b-q4_K_M"

if ($Help) {
    Write-Host "Usage: .\docker\launch.ps1 [-CpuOnly | -Gpu]"
    Write-Host "  -CpuOnly   Force CPU mode (smaller 8B model)"
    Write-Host "  -Gpu       Force GPU mode (larger 35B model)"
    Write-Host "  (default)  Auto-detect GPU"
    exit 0
}

# ── Pre-flight checks ───────────────────────────────────────────────────────
Write-Host "=============================================="
Write-Host "  PRIDE Metadata Extraction Pipeline"
Write-Host "=============================================="
Write-Host ""

# Check Docker is installed
try {
    docker info | Out-Null
} catch {
    Write-Host "ERROR: Docker is not installed or not running."
    Write-Host "  Install Docker Desktop: https://www.docker.com/products/docker-desktop/"
    exit 1
}

# ── GPU detection ────────────────────────────────────────────────────────────
$UseGpu = $false
$ComposeFiles = "-f `"$ScriptDir\docker-compose.yml`""

if ($CpuOnly) {
    Write-Host "  Mode: CPU (forced)"
    $env:MODEL_NAME = $CpuModel
} elseif ($Gpu) {
    Write-Host "  Mode: GPU (forced)"
    $env:MODEL_NAME = $GpuModel
    $UseGpu = $true
} else {
    try {
        nvidia-smi | Out-Null
        Write-Host "  Mode: GPU (NVIDIA GPU detected)"
        $env:MODEL_NAME = $GpuModel
        $UseGpu = $true
    } catch {
        Write-Host "  Mode: CPU (no NVIDIA GPU detected)"
        $env:MODEL_NAME = $CpuModel
    }
}

if ($UseGpu) {
    $ComposeFiles += " -f `"$ScriptDir\docker-compose.gpu.yml`""
}

Write-Host "  Model: $env:MODEL_NAME"
Write-Host ""

# ── Check input directory ────────────────────────────────────────────────────
$InputDir = Join-Path $ProjectDir "input"
if (-not (Test-Path $InputDir) -or (Get-ChildItem $InputDir -ErrorAction SilentlyContinue).Count -eq 0) {
    Write-Host "WARNING: No input files found in $InputDir\"
    Write-Host "  Place .txt manuscript files there before running."
    Write-Host ""
}

# ── Launch ───────────────────────────────────────────────────────────────────
Write-Host "Starting pipeline..."
Write-Host "  Results will appear in: $ProjectDir\framework_output\"
Write-Host ""

Set-Location $ProjectDir
Invoke-Expression "docker compose $ComposeFiles up --build"

Write-Host ""
Write-Host "=============================================="
Write-Host "  Pipeline complete."
Write-Host "  Results: $ProjectDir\framework_output\"
Write-Host "=============================================="
