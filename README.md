# PRIDE Metadata Extraction Framework

An agentic pipeline for extracting and normalizing metadata from scientific manuscripts, designed for proteomics and mass spectrometry submissions to the PRIDE database.

Two pipeline backends are available:

| Backend | Entry point | Description |
|---------|-------------|-------------|
| **Original** | `main.py` | Direct LLM calls via `BaseExtractor` |
| **DocETL** | `docetl_pipeline/run_docetl.py` | DocETL-orchestrated extraction with gleaning and schema validation |

---

## Quick Start

### DocETL pipeline (recommended)

```bash
# Activate the DocETL venv
source docetl_pipeline/venv/bin/activate

# Run all three agents on a directory of manuscripts
python docetl_pipeline/run_docetl.py \
    --input docs/ \
    --output framework_output/docetl/

# Single agent, single file, no confidence scoring
python docetl_pipeline/run_docetl.py \
    --input docs/PXD001234.txt \
    --output framework_output/docetl/ \
    --agents biological \
    --no-confidence

# Use a different model config (e.g. Claude, GPT, Gemini)
python docetl_pipeline/run_docetl.py \
    --input docs/ \
    --output framework_output/docetl/ \
    --config benchmark_data/Testing_final/claude_config.yaml \
    --model-tag claude
```

### Original pipeline

```bash
source venv/bin/activate   # or: conda activate agentic
python main.py all --input /path/to/documents/
```

---

## Overview

The framework uses specialized LLM-based agents to extract structured metadata from scientific text, normalize extracted terms against biomedical ontologies, then run post-extraction consistency checks to flag potential hallucinations.

---

## Architecture

### DocETL pipeline

```
Input .txt files
       │
       ├──────────────────┬──────────────────┐
       ▼                  ▼                  ▼
┌─────────────┐  ┌───────────────┐  ┌─────────────────────┐
│ Biological  │  │  Technical    │  │ ExperimentalDesign  │
│ Agent       │  │  Agent        │  │ Agent               │
│ (DocETL)    │  │  (DocETL)     │  │ (DocETL)            │
└─────────────┘  └───────────────┘  └─────────────────────┘
       │                  │                  │
       │   each agent:    │                  │
       │   map → glean    │                  │
       │   → validate     │                  │
       └──────────────────┴──────────────────┘
                           │
                           ▼
                ┌──────────────────┐
                │ Confidence Score │  (ValidationAgent, schema-based)
                └──────────────────┘
                           │
                           ▼
                ┌──────────────────────────────────┐
                │ Hallucination Checks              │
                │  • Cross-field ontology (CLO/DOID)│
                │  • Negation detection (NegEx)     │
                │  • Numeric mismatch               │
                └──────────────────────────────────┘
                           │
                           ▼
                ┌──────────────────┐
                │ NormalizationAgent│  (SapBERT ontology term matching)
                └──────────────────┘
                           │
                           ▼
                ┌──────────────────┐
                │ IntegrationAgent │  (PRIDE API + METI technical pipeline enrichment)
                └──────────────────┘
                           │
                           ▼
                Per-agent JSON output
                {output_dir}/{Agent}/{PXD_ID}_{agent}.json
```

### Original pipeline

```
Input documents
       │
       ├──────────────────┬──────────────────┐
       ▼                  ▼                  ▼
BiologicalAgent   TechnicalAgent   ExperimentalDesignAgent
       │                  │                  │
       └──────────────────┴──────────────────┘
                          │
              ┌───────────┴───────────┐
              ▼                       ▼
    NormalizationAgent         IntegrationAgent
    (--normalize flag)         (--integrate flag)
    SapBERT ontology           merges METI technical
    term matching              pipeline data + resolves conflicts
              │                       │
              └───────────┬───────────┘
                          ▼
                  Structured JSON output
```

Both `--normalize` and `--integrate` are independent optional steps that run after the extraction agents. Either, both, or neither can be enabled — they do not depend on each other.

---

## Agents

| Agent | Type | Fields / purpose |
|-------|------|-----------------|
| **BiologicalAgent** | LLM | species, tissue, cell type, disease state, cell line, sex, strain, age, BMI, anatomic site |
| **TechnicalAgent** | LLM | instrument, cleavage agent, labeling, fragmentation method, fractionation, enrichment, reduction/alkylation reagents |
| **ExperimentalDesignAgent** | LLM | experimental design, factor values, replicate counts, sample counts, fractions |
| **IntegrationAgent** *(original only)* | Rule-based | merges METI technical pipeline data with LLM output; PMID matching + confidence-scored conflict resolution; no LLM calls |
| **NormalizationAgent** *(original only)* | Embedding | maps extracted terms to ontology IDs using SapBERT nearest-neighbour search; no LLM calls |
| **ValidationAgent** | Rule-based* | schema format checks + evidence scoring; confidence metrics; `*`optional LLM critique in `HYBRID`/`LLM_ONLY` modes |
| **CrossFieldConsistencyChecker** | Rule-based | ontology graph lookups (CLO/DOID/CL/UBERON) to flag cross-field contradictions; no LLM calls |
| **NegationDetector** | Rule-based | negspacy (NegEx) on each field's evidence sentence; flags extracted values negated by their own evidence |
| **NumericMismatchDetector** | Rule-based | exact substring match for numeric values (concentrations, energies, %) — no fuzzy tolerance |

---

## DocETL Pipeline Details

### Gleaning

Each DocETL agent runs **2 rounds of gleaning** after the initial extraction. Gleaning re-prompts the LLM to self-review its output and fix issues such as:
- Missing `"inferred: "` prefix on values not literally in the text
- Evidence strings that don't contain the extracted value as a substring
- `"unknown"` values with non-empty evidence

Gleaning only fires when at least one non-unknown field has an **empty evidence string** — it is skipped when all evidence is already populated, to avoid unnecessary LLM calls and over-correction.

### Schema validation

Key fields are validated by DocETL after each map step (up to 2 retries on failure):

| Agent | Validated fields |
|-------|-----------------|
| Biological | species, tissue, cell_type, disease_state |
| Technical | instrument, cleavage_agent, labeling, fragmentation_method |
| Experimental | experimental_design, number_of_biological_replicates |

### Output field format

Every field is a 2-element list `[value, evidence]`:

```json
{
  "species":      ["Homo sapiens", "inferred: patient samples were collected"],
  "instrument":   ["Q Exactive HF", "analyzed using a Q Exactive HF instrument"],
  "cell_line":    ["HeLa", "HeLa cells were cultured in DMEM"],
  "labeling":     ["label-free", "inferred: No isobaric labels were mentioned"],
  "_confidence":  {"overall": 0.91, "evidence_score": 0.88, "completeness": 0.9, "format_score": 1.0},
  "_hallucination_flags": [
    {"type": "negated_evidence",  "field": "labeling", "value": "TMT", "evidence": "No TMT labeling was used."},
    {"type": "numeric_mismatch",  "field": "concentration", "value": "50 mM", "evidence": "reduced in 5 mM DTT"},
    {"type": "cell_line_species_mismatch", "field_a": "cell_line", "value_a": "HeLa", "field_b": "species", "value_b": "Mus musculus", "expected_b": "Homo sapiens"}
  ]
}
```

### Running the DocETL pipeline

```bash
# All three agents on all manuscripts in a directory
python docetl_pipeline/run_docetl.py \
    --input docs/ \
    --output framework_output/docetl/

# Specific agents only
python docetl_pipeline/run_docetl.py \
    --input docs/ \
    --agents biological technical

# Force fresh LLM calls (ignore DocETL's disk cache)
python docetl_pipeline/run_docetl.py \
    --input docs/ \
    --bypass-cache

# Skip confidence scoring
python docetl_pipeline/run_docetl.py \
    --input docs/ \
    --no-confidence
```

---

## Hallucination Checks

Three complementary rule-based checks run automatically after each agent writes its output, all contributing to `_hallucination_flags`. All checks are **zero-LLM** and **non-fatal** — a missing dependency silently disables that check.

### 1 — Cross-Field Ontology Consistency

`validation/cross_field_checker.py` — uses CLO, DOID, CL and UBERON ontologies to detect fields that biologically contradict each other.

| Check | Ontology | Relationship | Example catch |
|-------|----------|-------------|--------------|
| cell_line → species | CLO | `derives_from` (RO:0001000) | HeLa + "Mus musculus" |
| cell_line → tissue | CLO + BTO | `derives_from` | HeLa + "liver" |
| disease → tissue | DOID | `located_in` / `xref: UBERON:` | pancreatic cancer + "brain" |
| cell_type → tissue | CL | `part_of` | hepatocyte + "lung" |

Parsed relationships are cached in `ontology_cache/` (JSON) so the OWL/OBO files are only parsed once.

### 2 — Negation Detection

`validation/negation_detector.py` — uses **negspacy** (NegEx algorithm) on the evidence sentence to detect when the extracted value is *negated* by its own evidence.

Requires: `pip install spacy negspacy && python -m spacy download en_core_web_sm`

| Evidence sentence | Extracted value | Flag? |
|-------------------|----------------|-------|
| `"No TMT labeling was used."` | `TMT` | ✅ flagged |
| `"Samples were labeled with TMT."` | `TMT` | clean |
| `"without SILAC labeling"` | `SILAC` | ✅ flagged |
| `"inferred: patient samples..."` | `Homo sapiens` | skipped (inferred) |

`label-free` and `unknown` values are explicitly skipped — absence-of-label IS the positive evidence.

### 3 — Numeric Mismatch

`validation/numeric_mismatch_detector.py` — requires an **exact substring match** for numeric values (concentrations, energies, percentages). No fuzzy tolerance: `"50 mM"` will not match an evidence sentence containing `"5 mM"`.

Detected units: `mM`, `µM`, `nM`, `ng/ml`, `%`, `NCE`, `eV`, `amu`, `rpm`, `min`, `ms`, …

> [!NOTE]
> This also tightens the `_confidence.evidence_score`: numeric values bypass the fuzzy fallback in `ValidationAgent.validate_evidence`, so a digit-off extraction scores low in confidence *and* appears in `_hallucination_flags`.

### Combined output

All three checks merge into the same list:

```json
"_hallucination_flags": [
  {
    "type":     "negated_evidence",
    "field":    "labeling",
    "value":    "TMT",
    "evidence": "No TMT labeling was used in this study."
  },
  {
    "type":     "numeric_mismatch",
    "field":    "alkylation concentration",
    "value":    "50 mM",
    "evidence": "alkylated in 5 mM iodoacetamide for 45 min"
  },
  {
    "type":       "cell_line_species_mismatch",
    "field_a":    "cell_line",  "value_a": "HeLa",
    "field_b":    "species",    "value_b": "Mus musculus",
    "expected_b": "Homo sapiens",
    "source":     "CLO derives_from"
  }
]
```

Filter by `"type"` to handle each class of issue differently downstream.

### Ontology files used

| File | Used for |
|------|----------|
| `ontologies/clo.owl` | cell line → species / tissue (cached as `ontology_cache/clo_derives_from.json`) |
| `ontologies/bto.obo` | BTO → UBERON tissue ID mapping |
| `ontologies/doid.obo` | disease → tissue (cached as `ontology_cache/doid_tissue.json`) |
| `ontologies/cl.obo` | cell type → tissue (cached as `ontology_cache/cl_tissue.json`) |

---

## Supported Ontologies

19 biomedical ontologies for term normalization:

| Category | Ontologies |
|----------|------------|
| Cell / Tissue | CL, CLO, BTO, UBERON |
| Species | Curated NCBITaxon subset, Rat Strains |
| Disease | DOID, Mondo |
| Mass Spec | PSI-MS, PRIDE-CV, UNIMOD, PSI-Mod |
| Other | ChEBI, EFO, PATO, Plant Ontology, FlyBase, ZFA, FBbt |

---

## Configuration

The pipeline reads `config.yaml` at the project root:

```yaml
paths:
  input_dir: "./docs"
  output_dir: "./framework_output"
  ontology_dir: "ontologies"

llm:
  model: "llama-4-scout"
  base_url: "https://llm.jetstream-cloud.org/llama-4-scout/v1/"  # OpenAI-compatible endpoint
  api_key_env_var: "LLM_API_KEY"

normalization:
  backend: "faiss"            # faiss (fastest), sklearn, annoy
  use_quantization: true
  use_gpu: true
  similarity_threshold: 0.7
```

---

## Abbreviation Expansion

Abbreviated species names (e.g. `p.falciparum`, `Plasmodium.falciparum`) are handled by injecting them as **synthetic synonyms directly into the ontology graph** before the embedding index is built.

| Node name | Injected synonyms |
|-----------|------------------|
| `Plasmodium falciparum` | `p.falciparum`, `Plasmodium.falciparum` |
| `Homo sapiens` | `h.sapiens`, `Homo.sapiens` |
| `Mus musculus` | `m.musculus`, `Mus.musculus` |

> [!IMPORTANT]
> Delete `ontology_cache/` and rebuild if you update the ontology files:
> ```bash
> rm -rf ontology_cache/ && python -m normalization.build_index
> ```

### Registering new synonyms at runtime

```python
normalizer.register_synonym("p.falciparum", "Plasmodium falciparum", "species")
```

The synonym is added to the live FAISS index immediately and persisted to `ontology_cache/custom_synonyms.json` for future runs.

---

## Local Installation (Python)

For development or running without Docker.

```bash
# Clone the repository and switch to the docetl branch
git clone https://github.com/CompOmics/agentic-metadata.git
cd agentic-metadata
git checkout docetl

# Create and activate the conda environment
conda create -n agentic python=3.12 -y
conda activate agentic

# Install all dependencies
pip install -r requirements.txt

# Download ontologies
python -m normalization.download

# Build ontology indices (optional — built automatically on first --normalize run)
python -m normalization.build_index
```

---

## Docker Installation (Recommended for Desktop Use)

The Docker setup bundles the extraction pipeline with a local LLM, so no external API keys or cloud services are needed. It uses [Ollama](https://ollama.com/) as a sidecar to serve a Qwen model locally, with automatic GPU detection and model download.

### Prerequisites

| Platform | Required software |
|----------|-------------------|
| **Linux** | [Docker Engine](https://docs.docker.com/engine/install/) or [Docker Desktop](https://www.docker.com/products/docker-desktop/) |
| **Linux + NVIDIA GPU** | Docker + [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) |
| **macOS** | [Docker Desktop](https://www.docker.com/products/docker-desktop/) |
| **Windows** | [Docker Desktop](https://www.docker.com/products/docker-desktop/) with WSL2 backend |

### Hardware requirements

| Mode | GPU | RAM | Disk | Model |
|------|-----|-----|------|-------|
| **GPU** (automatic when NVIDIA GPU detected) | NVIDIA GPU with CUDA support | 32 GB | 30 GB free | Qwen3 35B-A3B (Q4, ~20 GB) |
| **CPU** (automatic fallback) | None | 16 GB | 15 GB free | Qwen3 8B (Q4, ~5 GB) |

> **Note:** macOS Docker cannot pass through Apple Silicon GPU (Metal). The CPU model is used automatically. For Metal acceleration, see [macOS native Ollama](#macos-native-ollama-optional) below.

### Setup

```bash
git clone https://github.com/CompOmics/agentic-metadata.git
cd agentic-metadata
```

### Starting the pipeline

**Linux / macOS:**

```bash
./docker/launch.sh
```

**Windows (PowerShell):**

```powershell
.\docker\launch.ps1
```

The launcher script will:
1. Check that Docker is installed and running.
2. Detect whether an NVIDIA GPU is available.
3. Select the appropriate model (35B for GPU, 8B for CPU).
4. On first run, download the model weights. This happens once and takes 10--30 minutes depending on your connection.
5. Start the LLM service and the extraction pipeline.

You can override GPU detection:

```bash
./docker/launch.sh --cpu-only   # Force CPU mode (8B model)
./docker/launch.sh --gpu        # Force GPU mode (35B model)
```

### macOS native Ollama (optional)

Docker on macOS cannot use the Apple Silicon GPU. If you want Metal-accelerated inference:

1. Install Ollama natively:
   ```bash
   brew install ollama
   ```
2. Start the Ollama server:
   ```bash
   ollama serve
   ```
3. Pull the model:
   ```bash
   ollama pull qwen3:8b-q4_K_M
   ```
4. Run only the extraction container, pointing it at the host Ollama:
   ```bash
   OPENAI_BASE_URL=http://host.docker.internal:11434/v1/ \
   docker compose -f docker/docker-compose.yml up docetl
   ```

### Docker architecture

```
  +-------------------+         +------------------+
  |   llm (Ollama)    |  HTTP   |     docetl       |
  |   port 11434      | <------ |  (extraction)    |
  |   auto-pulls model|         |  Python pipeline |
  +-------------------+         +------------------+
         |                              |
    [ollama_models]              [hf_cache, docetl_cache]
     named volume                 named volumes
```

- **llm**: Ollama container that serves the Qwen model via an OpenAI-compatible API. Downloads the model on first run and caches it in a persistent Docker volume.
- **docetl**: The extraction pipeline container. Waits for the LLM to be ready before starting. Reads manuscripts from `input/` and writes results to `framework_output/`.

---

## Running Your Own Papers

After installation (either Docker or local), follow these steps to extract metadata from your own manuscripts.

### 1. Prepare your manuscripts

Each manuscript should be a plain text (`.txt`) file. PDFs must be converted to text first. Name files with the PRIDE accession if available (e.g., `PXD012345.txt`), otherwise use any descriptive name.

Place all `.txt` files in the `input/` directory:

```
agentic-metadata/
  input/
    PXD012345.txt
    PXD067890.txt
    my_paper.txt
```

### 2. Run the extraction

**With Docker (recommended):**

```bash
# Run on all files in input/
./docker/launch.sh
```

Results appear in `framework_output/` once the pipeline completes.

**With Docker on specific files:**

To override the default input/output directories, use `docker compose run`:

```bash
# GPU mode
docker compose -f docker/docker-compose.yml -f docker/docker-compose.gpu.yml \
  run docetl \
  --input /app/input \
  --output /app/framework_output \
  --agents biological technical experimental

# CPU mode
docker compose -f docker/docker-compose.yml \
  run docetl \
  --input /app/input \
  --output /app/framework_output \
  --agents biological
```

**Without Docker (local Python):**

```bash
source docetl_env/bin/activate

python docetl_pipeline/run_docetl.py \
    --input input/ \
    --output framework_output/
```

### 3. Understand the output

Results are organized by agent in `framework_output/`:

```
framework_output/
  BiologicalAgent/
    PXD012345_manuscript_biological.json
    PXD067890_manuscript_biological.json
  TechnicalAgent/
    PXD012345_manuscript_technical.json
  ExperimentalDesignAgent/
    PXD012345_manuscript_experimental.json
```

Each JSON file contains extracted fields as `[value, evidence]` pairs:

```json
{
  "species": ["Homo sapiens", "inferred: patient samples were collected from donors"],
  "instrument": ["Q Exactive HF", "analyzed using a Q Exactive HF mass spectrometer"],
  "cell_line": ["unknown", ""],
  "labeling": ["TMT 10-plex", "samples were labeled using TMT 10-plex reagents"]
}
```

- `"unknown"` with empty evidence means the field was not found in the manuscript.
- Evidence prefixed with `"inferred: "` indicates the value was not stated verbatim but inferred from context.

### 4. Run specific agents only

If you only need biological metadata (species, tissue, disease, etc.):

```bash
# Docker
docker compose -f docker/docker-compose.yml run docetl \
  --input /app/input --output /app/framework_output --agents biological

# Local
python docetl_pipeline/run_docetl.py --input input/ --agents biological
```

Available agents: `biological`, `technical`, `experimental`.

### 5. Optional post-processing

**Normalization** maps extracted terms to ontology IDs (e.g., "liver" to UBERON:0002107):

```bash
python docetl_pipeline/run_docetl.py \
    --input input/ \
    --output framework_output/ \
    --no-integrate
```

**Integration** enriches results with data from the PRIDE API and METI technical pipeline:

```bash
python docetl_pipeline/run_docetl.py \
    --input input/ \
    --output framework_output/ \
    --meti-dir benchmark_data/Technical_pipeline_outputs_train_test/final_files/
```

---

### Disk space requirements

| Component | Size |
|-----------|------|
| Core dependencies (PyTorch, transformers) | ~2 GB |
| Ontology files | ~500 MB |
| Ontology indices | ~4 GB |

### Reproducibility

```bash
# Exact version pins
pip install -r requirements-frozen.txt

# Run with explicit seed
python main.py all --input ./docs --seed 42
```

---

## Testing

```bash
# All tests
conda run -n agentic python -m pytest tests/ -v

# Cross-field checker only (fully offline, no ontology files needed)
conda run -n agentic python -m pytest tests/test_cross_field_checker.py -v

# DocETL pipeline runner tests (mocked, no LLM calls)
conda run -n agentic python -m pytest tests/test_docetl_pipeline.py -v
```

---

## Benchmarking

```bash
# Run full benchmark on the 29-PXD test set (test + new_test splits)
python benchmark_data/run_sdrf_benchmark.py \
  --input-dir test_set \
  --dataset-label "Test Set"

# Re-evaluate without re-extracting (reuse existing LLM outputs)
python benchmark_data/run_sdrf_benchmark.py \
  --input-dir test_set \
  --skip-extraction \
  --dataset-label "Test Set"

# Benchmark a specific model's outputs
python benchmark_data/run_sdrf_benchmark.py \
  --input-dir test_set \
  --skip-extraction \
  --model-label claude \
  --extraction-dir benchmark_data/Testing_final/test_set/claude \
  --dataset-label "Test Set"
```

---

## Project Structure

```
agentic-metadata/
├── config.yaml                    # Centralized configuration
├── main.py                        # Original pipeline entry point
├── requirements.txt
├── requirements-frozen.txt
│
├── docetl_pipeline/               # DocETL pipeline (docetl branch)
│   ├── run_docetl.py              # Runner: loads YAML, calls DocETL, writes JSON
│   ├── pipeline_biological.yaml   # BiologicalAgent: map + gleaning
│   ├── pipeline_technical.yaml    # TechnicalAgent: map + gleaning
│   └── pipeline_experimental.yaml # ExperimentalDesignAgent: map + gleaning
│
├── agents/                        # Original pipeline agents
│   ├── biological_agent.py
│   ├── technical_agent.py
│   ├── experimental_agent.py
│   ├── integration_agent.py
│   └── normalization_agent.py
│
├── core/                          # Shared LLM client, prompts, logging
│   ├── extractor.py
│   ├── llm.py
│   └── prompts.py
│
├── normalization/                 # Ontology normalization (both pipelines)
│   ├── config.py                  # NormalizationConfig, 19-ontology mapping
│   ├── normalizer.py              # TermNormalizer (SapBERT + FAISS)
│   ├── ontology.py                # OntologyGraph, OntologyLoader (OBO + OWL)
│   ├── index.py                   # Embedding index (FAISS / sklearn / annoy)
│   ├── download.py                # Ontology file downloader
│   └── build_index.py             # Pre-build embedding indices
│
├── validation/                    # Quality assurance layer
│   ├── validator.py               # ValidationAgent: schema + confidence scoring
│   ├── cross_field_checker.py     # CrossFieldConsistencyChecker (CLO/DOID/CL/UBERON)
│   └── schema.py
│
├── benchmark_data/                # SDRF benchmark pipeline
│   ├── run_sdrf_benchmark.py
│   ├── sdrf_to_golden.py
│   └── annotation_to_golden.py
│
├── tests/
│   ├── test_docetl_pipeline.py    # DocETL runner tests (55 cases, fully mocked)
│   ├── test_cross_field_checker.py # Cross-field checker tests (55 cases, fully mocked)
│   ├── test_normalizer.py
│   └── test_validator.py
│
├── docker/                        # Docker deployment
│   ├── Dockerfile                 # Extraction pipeline image (CUDA 12.8 + Python 3.12)
│   ├── docker-compose.yml         # Two-service stack: Ollama LLM + extraction pipeline
│   ├── docker-compose.gpu.yml     # GPU overlay (NVIDIA device reservation)
│   ├── config.docker.yaml         # Docker-specific LLM config (Ollama sidecar URL)
│   ├── ollama-entrypoint.sh       # Ollama startup: serve, pull model, warm-load
│   ├── launch.sh                  # Linux/macOS launcher (GPU detection + docker compose)
│   ├── launch.ps1                 # Windows PowerShell launcher
│   └── requirements-docker.txt    # Frozen Python deps for the Docker image
│
├── ontologies/                    # Ontology files -- gitignored, download separately
└── ontology_cache/                # Cached embedding indices + derived JSON -- gitignored
```

---

## Troubleshooting

### Ontology download fails

```bash
python -m normalization.download        # Retry all
python -m normalization.download --check  # Check which files are present
```

### Cross-field checker finds no flags (no ontologies downloaded)

The checker silently disables each check when the corresponding ontology file is absent. Download the relevant files and delete the stale JSON caches to enable them:

```bash
python -m normalization.download
rm -f ontology_cache/clo_derives_from.json \
      ontology_cache/doid_tissue.json \
      ontology_cache/cl_tissue.json
```

### Normalization is slow on first run

The first run builds SapBERT embedding indices (~10 min). Pre-build them:

```bash
python -m normalization.build_index
```

### Stale ontology index after updates

```bash
rm -rf ontology_cache/ && python -m normalization.build_index
```

### Docker: model download is slow or stalls

The first run downloads the LLM weights (5--20 GB). If the download stalls, you can pre-pull the model manually:

```bash
docker compose -f docker/docker-compose.yml run llm ollama pull qwen3:8b-q4_K_M
```

### Docker: GPU not detected

On Linux, ensure the NVIDIA Container Toolkit is installed:

```bash
# Check if nvidia-container-cli is available
nvidia-container-cli --version

# If not, install: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html
```

On Windows, ensure Docker Desktop is using the WSL2 backend and that NVIDIA drivers are installed in WSL.

### Docker: "depends_on" timeout

If the extraction container exits because the LLM is still downloading, increase the healthcheck retries in `docker/docker-compose.yml` or pre-pull the model as shown above.

### GPU out of memory

```yaml
# config.yaml
normalization:
  use_gpu: false
```

### FAISS install fails

```yaml
# config.yaml — fall back to the sklearn backend
normalization:
  backend: "sklearn"
```

---

## License

[Specify license]

## Citation

[Add citation if applicable]
