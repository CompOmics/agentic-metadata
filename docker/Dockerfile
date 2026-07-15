# DocETL Metadata Extraction Pipeline
# Base: CUDA 12.8 runtime (matches venv nvidia-cuda-runtime-cu12==12.8.90)
FROM nvidia/cuda:12.8.0-runtime-ubuntu22.04

# ── System packages ──────────────────────────────────────────────────────────
# Ubuntu 22.04 ships Python 3.10; use deadsnakes PPA for Python 3.12.
# python3.12-distutils is NOT listed — distutils was removed in Python 3.12;
# setuptools (installed via pip below) provides it instead.
# DEBIAN_FRONTEND=noninteractive prevents apt from prompting for timezone/locale
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC
RUN apt-get update && apt-get install -y --no-install-recommends \
        software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y --no-install-recommends \
        python3.12 \
        python3.12-dev \
        python3-pip \
        build-essential \
        curl \
        git \
    && rm -rf /var/lib/apt/lists/*

# Make python3.12 the default python3 / python
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1 \
    && update-alternatives --install /usr/bin/python  python  /usr/bin/python3.12 1

# Bootstrap pip for 3.12 (python3-pip installs pip for the system 3.10)
RUN curl -sS https://bootstrap.pypa.io/get-pip.py | python3.12

WORKDIR /app

# ── Python dependencies ───────────────────────────────────────────────────────
# 1. Install PyTorch. Default index is the CUDA 12.8 wheel server.
#    Override with --build-arg TORCH_INDEX=https://download.pytorch.org/whl/cpu
#    for CI builds (avoids ~8 GB of nvidia-* packages on disk-constrained runners).
ARG TORCH_INDEX=https://download.pytorch.org/whl/cu128
RUN python3.12 -m pip install --no-cache-dir \
        torch==2.10.0 \
        --index-url ${TORCH_INDEX}

# 2. Install all other pipeline dependencies
COPY docker/requirements-docker.txt .
RUN python3.12 -m pip install --no-cache-dir -r requirements-docker.txt

# 3. Pre-download spaCy model so containers start without network access
RUN python3.12 -m spacy download en_core_web_sm

# ── Application code ──────────────────────────────────────────────────────────
# Copy only source modules; data, configs, and secrets are mounted at runtime.
COPY core/           core/
COPY agents/         agents/
COPY validation/     validation/
COPY normalization/  normalization/
COPY docetl_pipeline/ docetl_pipeline/

# ── Runtime environment ───────────────────────────────────────────────────────
ENV PYTHONPATH=/app
# DocETL LLM-call cache (mounted as a named volume in docker-compose)
ENV DOCETL_HOME_DIR=/cache/docetl
# HuggingFace model cache (mounted as a named volume in docker-compose)
ENV TRANSFORMERS_CACHE=/cache/huggingface
ENV HF_HOME=/cache/huggingface

# ── Entrypoint ────────────────────────────────────────────────────────────────
ENTRYPOINT ["python3.12", "docetl_pipeline/run_docetl.py"]
