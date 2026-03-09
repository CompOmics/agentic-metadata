# PRIDE Metadata Extraction Framework

An agentic pipeline for extracting and normalizing metadata from scientific manuscripts, designed for proteomics and mass spectrometry submissions to the PRIDE database.

Two pipeline backends are available:

| Backend | Entry point | Description |
|---------|-------------|-------------|
| **Original** | `main.py` | Direct LLM calls via `BaseExtractor` |
| **DocETL** | `docetl_pipeline/run_docetl.py` | DocETL-orchestrated extraction with gleaning and schema validation |

---

## Quick Start

### DocETL pipeline (recommended, `docetl` branch)

```bash
# Activate the conda environment
conda activate agentic

# Run all three agents on a directory of manuscripts
python docetl_pipeline/run_docetl.py \
    --input docs/ \
    --output framework_output/docetl/ \
    --config config.yaml

# Single agent, single file, no confidence scoring
python docetl_pipeline/run_docetl.py \
    --input docs/PXD001234.txt \
    --output framework_output/docetl/ \
    --agents biological \
    --no-confidence
```

### Original pipeline

```bash
conda activate agentic
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
               ┌──────────────────────────┐
               │ Cross-Field Consistency  │  (CLO / DOID / CL / UBERON)
               │ Checker                  │
               └──────────────────────────┘
                          │
                          ▼
               Per-agent JSON output
               framework_output/docetl/{Agent}/{PXD_ID}_{agent}.json
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
    SapBERT ontology           merges RunAssessor
    term matching              data + resolves conflicts
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
| **IntegrationAgent** *(original only)* | Rule-based | merges RunAssessor data with LLM output; PMID matching + confidence-scored conflict resolution; no LLM calls |
| **NormalizationAgent** *(original only)* | Embedding | maps extracted terms to ontology IDs using SapBERT nearest-neighbour search; no LLM calls |
| **ValidationAgent** | Rule-based* | schema format checks + evidence scoring; confidence metrics; `*`optional LLM critique in `HYBRID`/`LLM_ONLY` modes |
| **CrossFieldConsistencyChecker** | Rule-based | ontology graph lookups (CLO/DOID/CL/UBERON) to flag cross-field contradictions; no LLM calls |

---

## DocETL Pipeline Details

### Gleaning

Each DocETL agent runs **2 rounds of gleaning** after the initial extraction. Gleaning re-prompts the LLM to self-review its output and fix issues such as:
- Missing `"inferred: "` prefix on values not literally in the text
- Evidence strings that don't contain the extracted value as a substring
- `"unknown"` values with non-empty evidence

Gleaning only fires when at least one non-unknown value was extracted — it is skipped on fully-unknown outputs to avoid unnecessary LLM calls.

### Schema validation

Key fields are validated by DocETL after each map step (up to 2 retries on failure):

| Agent | Validated fields |
|-------|-----------------|
| Biological | species, tissue, cell_type, disease_state |
| Technical | instrument, cleavage agent, labeling, fragmentation method |
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
  "_hallucination_flags": []
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

## Cross-Field Ontology Consistency Checker

`validation/cross_field_checker.py` — runs automatically after each DocETL agent writes its output.

It uses four ontology-based relationships to detect fields that contradict each other:

| Check | Ontology | Relationship | Example catch |
|-------|----------|-------------|--------------|
| cell_line → species | CLO | `derives_from` (RO:0001000) | HeLa + "Mus musculus" |
| cell_line → tissue | CLO + BTO | `derives_from` | HeLa + "liver" |
| disease → tissue | DOID | `located_in` / `xref: UBERON:` | pancreatic cancer + "brain" |
| cell_type → tissue | CL | `part_of` | hepatocyte + "lung" |

Inconsistencies are appended to `_hallucination_flags` in the output JSON:

```json
"_hallucination_flags": [
  {
    "type":         "cell_line_species_mismatch",
    "field_a":      "cell_line",  "value_a": "HeLa",        "ontology_id_a": "CLO:0000148",
    "field_b":      "species",    "value_b": "Mus musculus", "ontology_id_b": null,
    "expected_b":   "Homo sapiens",
    "source":       "CLO derives_from"
  }
]
```

The checker is **fully graceful** — if an ontology file is missing, that check is silently skipped. Parsed CLO/DOID/CL relationships are cached as JSON in `ontology_cache/` so the OWL/OBO files are only parsed once.

The checker looks for ontology files in this order:

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
  base_url: "http://localhost:11434/v1/"   # OpenAI-compatible endpoint
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

## Installation

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
# Run benchmark on the 12-PXD test set
CUDA_VISIBLE_DEVICES="" python benchmark_data/run_sdrf_benchmark.py \
  --input-dir test_set

# Run on new test set with integration agent (18 PXDs)
CUDA_VISIBLE_DEVICES="" python benchmark_data/run_sdrf_benchmark.py \
  --input-dir new_test_set \
  --integrate --runassessor-dir /path/to/aggregated_results \
  --skip-conversion

# Re-evaluate without re-extracting
CUDA_VISIBLE_DEVICES="" python benchmark_data/run_sdrf_benchmark.py \
  --input-dir test_set --skip-extraction --skip-conversion
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
├── ontologies/                    # Ontology files — gitignored, download separately
└── ontology_cache/                # Cached embedding indices + derived JSON — gitignored
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
