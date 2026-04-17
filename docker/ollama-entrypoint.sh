#!/bin/bash
set -e

MODEL_NAME="${MODEL_NAME:-qwen3:8b-q4_K_M}"

echo "=============================================="
echo "  PRIDE Metadata Extraction - LLM Service"
echo "  Model: ${MODEL_NAME}"
echo "=============================================="

# 1. Start Ollama server in background
echo "[llm] Starting Ollama server..."
ollama serve &
SERVER_PID=$!

# 2. Wait for server to become ready
echo "[llm] Waiting for server to start..."
MAX_WAIT=60
WAITED=0
until ollama list >/dev/null 2>&1; do
    sleep 2
    WAITED=$((WAITED + 2))
    if [ $WAITED -ge $MAX_WAIT ]; then
        echo "[llm] ERROR: Ollama server did not start within ${MAX_WAIT}s"
        exit 1
    fi
done
echo "[llm] Server ready."

# 3. Pull model if not already present
if ollama list | grep -q "${MODEL_NAME}"; then
    echo "[llm] Model '${MODEL_NAME}' already available."
else
    echo "[llm] Downloading model '${MODEL_NAME}'..."
    echo "[llm] This may take 10-30 minutes on first run."
    ollama pull "${MODEL_NAME}"
    echo "[llm] Model download complete."
fi

# 4. Warm-load the model into memory for faster first request
echo "[llm] Loading model into memory..."
ollama run "${MODEL_NAME}" "" >/dev/null 2>&1 || true
echo "[llm] Model loaded and ready for requests."

# 5. Keep container alive
wait $SERVER_PID
