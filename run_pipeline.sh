#!/bin/bash
# This script runs the full extraction pipeline:
# 1. Runs all agents (biological, technical, experimental)
# 2. Enables validation (The Critic)
# 3. Uses default input/output paths (unless overridden)

echo "Starting Unified Scientific Metadata Extraction Pipeline..."
echo "Mode: ALL"
echo "Validation: ENABLED"

/media/volume/bert_training_data_models/llama/reann/bin/python3 main.py all --validate --output "/media/volume/bert_training_data_models/unified_framework_output" "$@"

echo "Pipeline Complete."
