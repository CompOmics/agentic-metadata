#!/bin/bash
# PRIDE Metadata Extraction Framework - Setup Script
#
# This script sets up the environment for first-time users:
# 1. Creates a Python virtual environment
# 2. Installs dependencies
# 3. Downloads ontology files
# 4. Optionally builds ontology indices
#
# Usage:
#   ./setup.sh           # Interactive setup
#   ./setup.sh --full    # Full setup including index building
#   ./setup.sh --quick   # Quick setup, skip large ontologies

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}"
echo "============================================================"
echo "  PRIDE Metadata Extraction Framework - Setup"
echo "============================================================"
echo -e "${NC}"

# Parse arguments
FULL_SETUP=false
QUICK_SETUP=false
SKIP_VENV=false

for arg in "$@"; do
    case $arg in
        --full)
            FULL_SETUP=true
            ;;
        --quick)
            QUICK_SETUP=true
            ;;
        --skip-venv)
            SKIP_VENV=true
            ;;
        --help|-h)
            echo "Usage: ./setup.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --full       Full setup including building ontology indices (~10 min)"
            echo "  --quick      Quick setup, skip large ontologies (chebi, efo)"
            echo "  --skip-venv  Skip virtual environment creation"
            echo "  --help       Show this help message"
            exit 0
            ;;
    esac
done

# Step 1: Python virtual environment
echo -e "${YELLOW}Step 1: Python Environment${NC}"

if [ "$SKIP_VENV" = true ]; then
    echo "  Skipping virtual environment (--skip-venv)"
elif [ -d "venv" ]; then
    echo -e "  ${GREEN}✓${NC} Virtual environment already exists"
else
    echo "  Creating virtual environment..."
    python3 -m venv venv
    echo -e "  ${GREEN}✓${NC} Created virtual environment"
fi

# Activate venv if it exists and we're not skipping
if [ -d "venv" ] && [ "$SKIP_VENV" = false ]; then
    source venv/bin/activate
    echo -e "  ${GREEN}✓${NC} Activated virtual environment"
fi

# Step 2: Install dependencies
echo -e "\n${YELLOW}Step 2: Installing Dependencies${NC}"

if [ -f "requirements.txt" ]; then
    echo "  Installing from requirements.txt..."
    pip install -q --upgrade pip
    pip install -q -r requirements.txt
    echo -e "  ${GREEN}✓${NC} Dependencies installed"
else
    echo -e "  ${RED}✗${NC} requirements.txt not found!"
    exit 1
fi

# Step 3: Download ontologies
echo -e "\n${YELLOW}Step 3: Downloading Ontologies${NC}"

if [ -d "ontologies" ] && [ "$(ls -A ontologies 2>/dev/null)" ]; then
    ONT_COUNT=$(ls -1 ontologies/*.obo ontologies/*.owl 2>/dev/null | wc -l)
    echo -e "  ${GREEN}✓${NC} Ontology directory exists ($ONT_COUNT files found)"
    
    # Check if we should download more
    if [ "$FULL_SETUP" = true ]; then
        echo "  Checking for missing ontologies..."
        if [ "$QUICK_SETUP" = true ]; then
            python -m normalization.download --skip-large
        else
            python -m normalization.download
        fi
    fi
else
    echo "  Downloading ontology files..."
    echo "  (This may take several minutes depending on your connection)"
    echo ""
    
    if [ "$QUICK_SETUP" = true ]; then
        python -m normalization.download --skip-large
    else
        python -m normalization.download
    fi
    
    echo -e "  ${GREEN}✓${NC} Ontologies downloaded"
fi

# Step 4: Build indices (optional)
echo -e "\n${YELLOW}Step 4: Ontology Indices${NC}"

if [ -d "ontology_cache" ] && [ "$(ls -A ontology_cache 2>/dev/null)" ]; then
    CACHE_COUNT=$(ls -1 ontology_cache/*.pkl 2>/dev/null | wc -l)
    echo -e "  ${GREEN}✓${NC} Index cache exists ($CACHE_COUNT indices found)"
elif [ "$FULL_SETUP" = true ]; then
    echo "  Building ontology indices..."
    echo "  (This takes ~10 minutes on first run)"
    echo ""
    python -m normalization.build_index
    echo -e "  ${GREEN}✓${NC} Indices built"
else
    echo -e "  ${YELLOW}!${NC} No cached indices found"
    echo "      Indices will be built automatically on first --normalize run"
    echo "      Or run: python -m normalization.build_index"
fi

# Summary
echo -e "\n${BLUE}============================================================${NC}"
echo -e "${GREEN}Setup Complete!${NC}"
echo -e "${BLUE}============================================================${NC}"
echo ""
echo "To run the pipeline:"
echo "  source venv/bin/activate  # if using venv"
echo "  python main.py all --input /path/to/documents/"
echo ""
echo "With normalization:"
echo "  python main.py all --input /path/to/documents/ --normalize"
echo ""
echo "For more options:"
echo "  python main.py --help"
echo ""
