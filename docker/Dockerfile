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

# 4. Pre-download the SapBERT embedding model used by NormalizationAgent, so
#    containers never need network access for it either. Must land under
#    /cache/huggingface (HF_HOME/TRANSFORMERS_CACHE, set just below so this
#    RUN step honours them) — that's the path the docker-compose hf_cache named
#    volume mounts over at runtime, and Docker only auto-seeds a volume from
#    the image's directory contents the first time it's used. Without this,
#    every normalization run's from_pretrained() call also re-validates the
#    cached model against the HuggingFace Hub over the network (see
#    HF_HUB_OFFLINE below) — real added latency on a slow/unreliable
#    connection, on top of the download itself being needed at all on a
#    fresh volume/machine.
ENV TRANSFORMERS_CACHE=/cache/huggingface
ENV HF_HOME=/cache/huggingface
RUN python3.12 -c "from transformers import AutoModel, AutoTokenizer; \
        m = 'cambridgeltl/SapBERT-from-PubMedBERT-fulltext'; \
        AutoTokenizer.from_pretrained(m); AutoModel.from_pretrained(m)"

# ── Application code ──────────────────────────────────────────────────────────
# Copy only source modules; data, configs, and secrets are mounted at runtime.
COPY core/           core/
COPY agents/         agents/
COPY validation/     validation/
COPY normalization/  normalization/
COPY docetl_pipeline/ docetl_pipeline/

# ── Pre-built ontology indices ────────────────────────────────────────────────
# Slim FAISS indices (embeddings stripped) for the core proteomics ontology set:
#   species, uberon, cl, clo, doid, psi-ms, unimod, pride-cv
# Built once on a GPU server; baked in so users never wait for index construction.
# Full ontology coverage (chebi, mondo, EFO, …) requires a local install — see README.
COPY docker/prebuilt_indices/ ontology_cache/

# ── Runtime environment ───────────────────────────────────────────────────────
ENV PYTHONPATH=/app
# Signals to run_docetl.py that it is running inside the Docker image so it
# can print a note about the core-only ontology set.
ENV HAMLET_DOCKER=1
# DocETL LLM-call cache (mounted as a named volume in docker-compose)
ENV DOCETL_HOME_DIR=/cache/docetl
# HuggingFace model cache (mounted as a named volume in docker-compose);
# TRANSFORMERS_CACHE/HF_HOME are already set above, before the SapBERT
# pre-download step, so both build- and run-time agree on the cache path.
# HF_HUB_OFFLINE stops transformers from re-validating the (baked-in or
# volume-cached) model against the Hub over the network on every single
# call — it's already local, there's nothing to check.
ENV HF_HUB_OFFLINE=1

# ── Entrypoint ────────────────────────────────────────────────────────────────
ENTRYPOINT ["python3.12", "docetl_pipeline/run_docetl.py"]
