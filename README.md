# Agentic Metadata Extraction Framework

An agentic pipeline for extracting, normalizing, and enriching structured metadata from proteomics manuscripts, designed for PRIDE/ProteomeXchange submissions.

---

## Quick Start

```bash
# Clone
git clone https://github.com/CompOmics/agentic-metadata.git
cd agentic-metadata

# Activate the DocETL venv
source venv/bin/activate          # or: conda activate agentic

# Run all three agents on a directory of manuscripts
python docetl_pipeline/run_docetl.py \
    --input docs/ \
    --output framework_output/

# Full pipeline: extraction + normalization + METI integration
python docetl_pipeline/run_docetl.py \
    --input docs/ \
    --output framework_output/ \
    --meti-dir /path/to/final_files/

# Merge per-agent outputs into one JSON per PXD
python docetl_pipeline/run_docetl.py \
    --input docs/ \
    --output framework_output/ \
    --meti-dir /path/to/final_files/ \
    --single-output
```

---

## Architecture

```
Input .txt files
       │
       ├──────────────────┬──────────────────┐
       ▼                  ▼                  ▼
┌─────────────┐  ┌───────────────┐  ┌──────────────────────┐
│ Biological  │  │  Technical    │  │ ExperimentalDesign   │
│ Agent       │  │  Agent        │  │ Agent                │
│ (DocETL)    │  │  (DocETL)     │  │ (DocETL)             │
└─────────────┘  └───────────────┘  └──────────────────────┘
       │                  │                   │
       │  map → glean → schema validate       │
       └──────────────────┴───────────────────┘
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
               ┌──────────────────────┐
               │ NormalizationAgent   │  SapBERT ontology term matching
               └──────────────────────┘
                          │
                          ▼
               ┌──────────────────────┐
               │ IntegrationAgent     │  PRIDE API + METI enrichment
               │                      │  3-way majority-vote resolution
               └──────────────────────┘
                          │
                          ▼
               ┌──────────────────────┐  optional: --judge-dir
               │ JudgeMerge           │  attach LLM-as-judge verdicts
               └──────────────────────┘
                          │
                          ▼
               ┌──────────────────────┐  optional: --single-output
               │ SingleOutput         │  one JSON per PXD
               └──────────────────────┘
```

---

## Agents

| Agent | Fields / purpose |
|-------|-----------------|
| **BiologicalAgent** | species, tissue, cell type, cell line, disease state, sex, age, strain, BMI, developmental stage, material type, ethnicity, anatomic site |
| **TechnicalAgent** | instrument, cleavage agent, labeling, fragmentation method, fractionation, enrichment, acquisition method, collision energy, reduction/alkylation reagents, mass analyzer, PTM, modification |
| **ExperimentalDesignAgent** | experimental design, factor values, biological/technical replicates, sample count, fraction count, technology type, quantification method |
| **NormalizationAgent** | maps extracted terms to ontology IDs (SapBERT + FAISS nearest-neighbour); no LLM calls |
| **IntegrationAgent** | enriches with PRIDE API descriptors and METI technical pipeline data; 3-way majority-vote conflict resolution; no LLM calls |
| **ValidationAgent** | schema format checks + evidence-based confidence scoring |
| **CrossFieldConsistencyChecker** | ontology graph lookups (CLO/DOID/CL/UBERON) to detect cross-field contradictions |
| **NegationDetector** | NegEx (negspacy) on each field's evidence sentence |
| **NumericMismatchDetector** | exact substring match for numeric values (concentrations, energies) |

---

## CLI Reference

```
python docetl_pipeline/run_docetl.py [OPTIONS]

Required:
  --input, -i PATH        .txt file or directory of .txt manuscripts

Optional:
  --output, -o PATH       Output directory (default: framework_output/docetl/)
  --config, -c PATH       config.yaml path (default: project root)
  --agents {biological,technical,experimental} [...]
                          Agents to run (default: all three)
  --model-tag TAG         String appended to output filenames (e.g. 'llama')
  --bypass-cache          Force fresh LLM calls, ignore DocETL's disk cache

Post-processing:
  --meti-dir PATH         Directory of {PXD}_aggregated_results.json files
                          (enables IntegrationAgent; auto-detected if not set)
  --no-normalize          Skip NormalizationAgent
  --no-integrate          Skip IntegrationAgent
  --judge-dir PATH        Directory of {PXD}.json LLM-as-judge files;
                          merges judge verdicts into IntegratedAgent outputs
  --single-output         Merge all three IntegratedAgent outputs into one
                          JSON per PXD in output_dir/SingleOutput/

Scoring:
  --no-confidence         Skip ValidationAgent confidence scoring
```

---

## Output Format

### Extraction output (`BiologicalAgent/`, `TechnicalAgent/`, `ExperimentalDesignAgent/`)

Each field is a 2-element list `[value, evidence]`:

```json
{
  "species":    ["Homo sapiens", "patient samples were collected from donors"],
  "instrument": ["Q Exactive HF", "analyzed using a Q Exactive HF mass spectrometer"],
  "labeling":   ["TMT 10-plex", "samples were labeled using TMT 10-plex reagents"],
  "cell_line":  ["unknown", ""],
  "_confidence": {"overall": 0.91, "evidence_score": 0.88, "completeness": 0.9},
  "_hallucination_flags": [...]
}
```

`"unknown"` with empty evidence = field not found. Evidence prefixed with `"inferred: "` = value inferred from context, not verbatim.

### Integration output (`IntegratedAgent/`)

Each field is resolved against PRIDE API and METI tool data:

```json
{
  "fragmentation_method": {
    "resolved":   "HCD",
    "confidence": 1.0,
    "status":     "AGREE",
    "sources": {
      "meti":  {"value": "HCD", "score": 1.0},
      "pride": {"value": "HCD", "score": 0.9},
      "llm":   {"value": "HCD", "evidence": "fragmented using HCD"}
    }
  }
}
```

#### Conflict resolution statuses

| Status | Meaning |
|--------|---------|
| `AGREE` | All available sources agree |
| `DISAGREE_TOOL_OUTVOTED` | LLM + PRIDE agree, tool is the outlier → LLM value accepted |
| `DISAGREE_LLM_OUTVOTED` | Tool + PRIDE agree, LLM is the outlier → tool value accepted |
| `DISAGREE_PRIDE_OUTVOTED` | LLM + tool agree, PRIDE is the outlier → tool value accepted |
| `DISAGREE_SPLIT` | All three differ → tool value accepted (fallback) |
| `DISAGREE` | Tool and LLM disagree, no PRIDE data → tool wins |
| `LLM_ONLY` | Only LLM extracted a value |
| `METI_ONLY` | Only METI/tool has a value |

#### LLM-as-judge annotations (`--judge-dir`)

When judge files are provided, each field gets a `_judge` sub-key:

```json
{
  "fragmentation_method": {
    "resolved": "HCD",
    "status":   "AGREE",
    "_judge": {
      "verdict":       "high",
      "type_mismatch": false,
      "judged_value":  "HCD",
      "issue_summary": {
        "TYPE_CHECK":        "...",
        "SOURCE_CHECK":      "...",
        "TRUTH_CHECK":       "...",
        "COMPLETENESS_CHECK":"..."
      }
    }
  }
}
```

---

## DocETL Pipeline Details

### Gleaning

Each agent runs **2 rounds of gleaning** after the initial extraction. Gleaning re-prompts the LLM to self-review and fix issues such as missing `"inferred: "` prefixes, empty evidence strings, and `"unknown"` values with non-empty evidence.

### Schema validation

| Agent | Validated fields |
|-------|-----------------|
| Biological | species, tissue, cell_type, disease_state |
| Technical | instrument, cleavage_agent, labeling, fragmentation_method |
| Experimental | experimental_design, number_of_biological_replicates |

Up to 2 retries on validation failure.

---

## Hallucination Checks

Three complementary rule-based checks populate `_hallucination_flags`. All are zero-LLM and non-fatal.

### Cross-Field Ontology Consistency

| Check | Ontology | Example catch |
|-------|----------|--------------|
| cell_line → species | CLO `derives_from` | HeLa + "Mus musculus" |
| cell_line → tissue | CLO + BTO | HeLa + "liver" |
| disease → tissue | DOID `located_in` | pancreatic cancer + "brain" |
| cell_type → tissue | CL `part_of` | hepatocyte + "lung" |

### Negation Detection

Uses negspacy (NegEx) on the evidence sentence.

```
"No TMT labeling was used."  →  TMT flagged
"samples were labeled with TMT"  →  clean
```

`label-free` and `unknown` values are skipped.

### Numeric Mismatch

Requires an exact substring match for numeric values. `"50 mM"` will not match evidence containing `"5 mM"`.

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

`config.yaml` at the project root:

```yaml
llm:
  model: "llama-4-scout"
  base_url: "https://llm.jetstream-cloud.org/llama-4-scout/v1/"
  api_key_env_var: "LLM_API_KEY"

normalization:
  backend: "faiss"            # faiss (fastest), sklearn, annoy
  use_quantization: true
  use_gpu: true
  similarity_threshold: 0.7
```

Set the API key for your provider before running:

```bash
export LLM_API_KEY=your-key       # OpenAI-compatible endpoints (default)
export ANTHROPIC_API_KEY=your-key  # Claude
export GEMINI_API_KEY=your-key     # Gemini
export OPENROUTER_API_KEY=your-key # OpenRouter
```

---

## Benchmarking

### Running the benchmark

```bash
cd /path/to/extraction_framework

# Run benchmark on an existing pipeline output directory
python benchmark/compare_llm_golden.py \
  --input-dir pipeline_output/IntegratedAgent \
  --golden-set benchmark_data/sdrf_golden \
  --output-dir reports/

# Run with a specific model tag
python docetl_pipeline/run_docetl.py \
    --input docs/ \
    --output framework_output/ \
    --model-tag llama \
    --meti-dir benchmark_data/.../final_files/

python benchmark/compare_llm_golden.py \
  --input-dir framework_output/IntegratedAgent \
  --golden-set benchmark_data/sdrf_golden \
  --output-dir reports/llama/
```

---

## Installation

### Local (Python)

```bash
git clone https://github.com/CompOmics/agentic-metadata.git
cd agentic-metadata

# DocETL venv (required for pipeline)
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Download ontologies (required for normalization)
python -m normalization.download

# Pre-build ontology indices (optional — built automatically on first --normalize run)
python -m normalization.build_index
```

### Docker (recommended for desktop use)

The Docker setup bundles the pipeline with a local Ollama LLM. No API keys needed.

**Prerequisites:**

| Platform | Required |
|----------|---------|
| Linux | Docker Engine |
| Linux + NVIDIA GPU | Docker + [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) |
| macOS / Windows | Docker Desktop |

**Start:**

```bash
# Linux / macOS
./docker/launch.sh

# Windows (PowerShell)
.\docker\launch.ps1
```

The launcher auto-detects GPU availability and selects the model:

| Mode | Model | GPU RAM | Disk |
|------|-------|---------|------|
| GPU | Gemma 4 31B (Q4) | NVIDIA CUDA | ~20 GB |
| CPU | Gemma 4 12B (Q4) | None | ~7 GB |

```bash
./docker/launch.sh --cpu-only   # Force CPU mode
./docker/launch.sh --gpu        # Force GPU mode
```

**macOS native Ollama (Metal acceleration):**

```bash
brew install ollama && ollama serve
ollama pull gemma4:12b-it-q4_K_M
OPENAI_BASE_URL=http://host.docker.internal:11434/v1/ \
  docker compose -f docker/docker-compose.yml up docetl
```

#### Ontology coverage in Docker

The Docker image ships pre-built FAISS indices for the **core proteomics ontology set**:

| Ontology | Coverage | Terms |
|----------|----------|-------|
| `uberon` | tissues / anatomical sites | 90 K |
| `cl` | cell types | 67 K |
| `clo` | cell lines | 43 K |
| `doid` | diseases | 31 K |
| `psi-ms` | instruments, fragmentation methods | 4 K |
| `unimod` | PTMs / labeling reagents | 2 K |
| `species` | organisms | 95 |
| `pride-cv` | PRIDE controlled vocabulary | 864 |

These cover the fields extracted from typical DDA/DIA proteomics manuscripts.
**Larger ontologies — ChEBI, Mondo, EFO, and species-specific anatomies — are not
included in the Docker image.** If you need normalization against those ontologies,
run the pipeline from a local install:

```bash
# Local install: download ontologies and build the full index set
python -m normalization.download
python -m normalization.build_index        # all 19 ontologies, uses GPU if available

# Or build only specific ontologies
python -m normalization.build_index --ontologies chebi mondo experimentalfactor
```

The pre-built indices were generated with `normalization/build_index.py --slim`, which
strips raw embeddings from the `.pkl` files (the FAISS binary is sufficient for search).
To regenerate them (e.g. after an ontology update):

```bash
python -m normalization.build_index \
    --ontologies species pride-cv psi-ms unimod doid cl uberon clo \
    --output-dir docker/prebuilt_indices \
    --slim
# Then copy the output into docker/prebuilt_indices/ and rebuild the image.
```

---

## Project Structure

```
agentic-metadata/
├── config.yaml                    # Centralized LLM + normalization config
├── requirements.txt
│
├── docetl_pipeline/               # Main pipeline
│   ├── run_docetl.py              # Runner: all agents + post-processing
│   ├── pipeline_biological.yaml   # BiologicalAgent: map + gleaning
│   ├── pipeline_technical.yaml    # TechnicalAgent: map + gleaning
│   └── pipeline_experimental.yaml # ExperimentalDesignAgent: map + gleaning
│
├── agents/
│   ├── integration_agent.py       # PRIDE + METI enrichment, conflict resolution
│   └── normalization_agent.py     # SapBERT ontology term matching
│
├── core/
│   ├── field_mappings.py          # LLM_TO_GOLDEN, AGENT_FIELDS, SDRF mappings
│   ├── extractor.py               # Base extractor with retry + normalize
│   └── llm.py
│
├── normalization/                 # Ontology normalization
│   ├── normalizer.py              # TermNormalizer (SapBERT + FAISS)
│   ├── ontology.py                # OntologyGraph (OBO + OWL)
│   ├── index.py                   # Embedding index (FAISS / sklearn / annoy)
│   └── download.py                # Ontology file downloader
│
├── validation/                    # Quality assurance
│   ├── validator.py               # ValidationAgent + confidence scoring
│   ├── cross_field_checker.py     # Cross-field ontology consistency
│   ├── negation_detector.py       # NegEx negation detection
│   └── numeric_mismatch_detector.py
│
├── benchmark/
│   └── compare_llm_golden.py      # Benchmark evaluation (SciBERT matching)
│
├── benchmark_data/
│   ├── sdrf_golden/               # 411 SDRF-derived golden-set JSONs
│   ├── dataset_mapping.json       # train/test/new_test splits (137 PXDs)
│   └── sdrf_to_golden.py          # SDRF .tsv → golden JSON converter
│
├── judge_integration/             # LLM-as-judge output files ({PXD}.json)
│
├── docker/                        # Docker deployment
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── docker-compose.gpu.yml
│   ├── launch.sh
│   ├── launch.ps1
│   └── prebuilt_indices/          # Slim FAISS indices baked into the image (core set, git-lfs)
│
├── ontologies/                    # Ontology files (gitignored, download separately)
└── ontology_cache/                # Cached embedding indices (gitignored)
```

---

## Troubleshooting

**Ontology download fails:**
```bash
python -m normalization.download        # Retry all
python -m normalization.download --check  # Check which files are present
```

**Normalization slow on first run:**
```bash
python -m normalization.build_index                     # all 19 ontologies
python -m normalization.build_index --ontologies cl uberon doid   # selective
python -m normalization.build_index --no-gpu            # force CPU
```

**Stale ontology index after updates:**
```bash
rm -rf ontology_cache/ && python -m normalization.build_index
```

**Cross-field checker finds no flags:**
```bash
python -m normalization.download
rm -f ontology_cache/clo_derives_from.json \
      ontology_cache/doid_tissue.json \
      ontology_cache/cl_tissue.json
```

**GPU out of memory (normalization):**
```yaml
# config.yaml
normalization:
  use_gpu: false
```

**FAISS install fails:**
```yaml
# config.yaml
normalization:
  backend: "sklearn"
```

**Docker: model download stalls:**
```bash
docker compose -f docker/docker-compose.yml run llm ollama pull gemma4:12b-it-q4_K_M
```

---

## License

[Specify license]

## Citation

[Add citation if applicable]
