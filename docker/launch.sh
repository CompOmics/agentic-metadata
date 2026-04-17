#!/bin/bash
# PRIDE Metadata Extraction -- Docker Launcher
# Detects GPU availability, selects the appropriate model, and starts
# the extraction pipeline with a local LLM sidecar.
#
# Usage:
#   ./docker/launch.sh              # auto-detect GPU
#   ./docker/launch.sh --cpu-only   # force CPU mode (8B model)
#   ./docker/launch.sh --gpu        # force GPU mode (35B model)

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

GPU_MODEL="qwen3:35b-a3b-q4_K_M"
CPU_MODEL="qwen3:8b-q4_K_M"

# ── Parse flags ──────────────────────────────────────────────────────────────
FORCE_CPU=false
FORCE_GPU=false
for arg in "$@"; do
    case "$arg" in
        --cpu-only) FORCE_CPU=true ;;
        --gpu)      FORCE_GPU=true ;;
        --help|-h)
            echo "Usage: $0 [--cpu-only | --gpu]"
            echo "  --cpu-only   Force CPU mode (smaller 8B model)"
            echo "  --gpu        Force GPU mode (larger 35B model)"
            echo "  (default)    Auto-detect GPU"
            exit 0
            ;;
    esac
done

# ── Pre-flight checks ───────────────────────────────────────────────────────
echo "=============================================="
echo "  PRIDE Metadata Extraction Pipeline"
echo "=============================================="
echo ""

# Check Docker is installed
if ! command -v docker &>/dev/null; then
    echo "ERROR: Docker is not installed."
    echo "  Install Docker Desktop: https://www.docker.com/products/docker-desktop/"
    exit 1
fi

# Check Docker daemon is running
if ! docker info &>/dev/null; then
    echo "ERROR: Docker daemon is not running."
    echo "  Please start Docker Desktop and try again."
    exit 1
fi

# Check docker compose availability (V2 plugin vs V1 standalone)
if docker compose version &>/dev/null; then
    COMPOSE="docker compose"
elif command -v docker-compose &>/dev/null; then
    COMPOSE="docker-compose"
else
    echo "ERROR: Docker Compose is not available."
    echo "  Install Docker Desktop (includes Compose) or install the compose plugin."
    exit 1
fi

# Check disk space (warn if <30GB free in Docker root)
DOCKER_ROOT=$(docker info --format '{{.DockerRootDir}}' 2>/dev/null || echo "/var/lib/docker")
if command -v df &>/dev/null; then
    FREE_GB=$(df -BG "$DOCKER_ROOT" 2>/dev/null | awk 'NR==2 {gsub(/G/,"",$4); print $4}')
    if [ -n "$FREE_GB" ] && [ "$FREE_GB" -lt 30 ] 2>/dev/null; then
        echo "WARNING: Only ${FREE_GB}GB free disk space in ${DOCKER_ROOT}."
        echo "  The LLM model requires 5-20GB. Consider freeing space."
        echo ""
    fi
fi

# ── GPU detection ────────────────────────────────────────────────────────────
USE_GPU=false
COMPOSE_FILES="-f ${SCRIPT_DIR}/docker-compose.yml"

if [ "$FORCE_CPU" = true ]; then
    echo "  Mode: CPU (forced)"
    export MODEL_NAME="$CPU_MODEL"
elif [ "$FORCE_GPU" = true ]; then
    echo "  Mode: GPU (forced)"
    export MODEL_NAME="$GPU_MODEL"
    USE_GPU=true
elif [[ "$(uname)" == "Darwin" ]]; then
    # macOS: Docker cannot pass through Metal GPU
    echo "  Mode: CPU (macOS -- Docker does not support Metal GPU)"
    echo "  Tip:  For Metal acceleration, install Ollama natively:"
    echo "        brew install ollama && ollama serve"
    export MODEL_NAME="$CPU_MODEL"
elif command -v nvidia-smi &>/dev/null && nvidia-smi &>/dev/null; then
    echo "  Mode: GPU (NVIDIA GPU detected)"
    export MODEL_NAME="$GPU_MODEL"
    USE_GPU=true
else
    echo "  Mode: CPU (no NVIDIA GPU detected)"
    export MODEL_NAME="$CPU_MODEL"
fi

if [ "$USE_GPU" = true ]; then
    COMPOSE_FILES="${COMPOSE_FILES} -f ${SCRIPT_DIR}/docker-compose.gpu.yml"
fi

echo "  Model: ${MODEL_NAME}"
echo ""

# ── Check for first run ─────────────────────────────────────────────────────
# Named volumes persist across runs. On first run, the model download can
# take 10-30 minutes depending on connection speed.
if ! docker volume inspect pride-extraction_ollama_models &>/dev/null 2>&1; then
    echo "  First run detected. The LLM model will be downloaded."
    if [ "$USE_GPU" = true ]; then
        echo "  Download size: ~20 GB (GPU model). This may take 10-30 minutes."
    else
        echo "  Download size: ~5 GB (CPU model). This may take 5-15 minutes."
    fi
    echo ""
fi

# ── Check input directory ────────────────────────────────────────────────────
INPUT_DIR="${PROJECT_DIR}/input"
if [ ! -d "$INPUT_DIR" ] || [ -z "$(ls -A "$INPUT_DIR" 2>/dev/null)" ]; then
    echo "WARNING: No input files found in ${INPUT_DIR}/"
    echo "  Place .txt manuscript files there before running."
    echo ""
fi

# ── Launch ───────────────────────────────────────────────────────────────────
echo "Starting pipeline..."
echo "  Results will appear in: ${PROJECT_DIR}/framework_output/"
echo ""

cd "$PROJECT_DIR"
$COMPOSE $COMPOSE_FILES up --build

echo ""
echo "=============================================="
echo "  Pipeline complete."
echo "  Results: ${PROJECT_DIR}/framework_output/"
echo "=============================================="
