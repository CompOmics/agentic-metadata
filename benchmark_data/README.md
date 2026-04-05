# SDRF Benchmark

Evaluates the extraction framework against SDRF ground truth annotations using semantic matching. Compares LLM-extracted metadata fields against per-sample SDRF values to measure precision, recall, and F1.

## Quick Start

```bash
# From the extraction_framework root directory:

# 1. Run full benchmark on 107-PXD train set (converts SDRFs → goldens, extracts, compares, plots)
python benchmark_data/run_sdrf_benchmark.py \
  --input-dir matched

# 2. Run on 29-PXD test set (test + new_test splits combined)
python benchmark_data/run_sdrf_benchmark.py \
  --input-dir test_set \
  --dataset-label "Test Set"

# 3. Re-evaluate without re-extracting (fast, for prompt/evaluation changes)
python benchmark_data/run_sdrf_benchmark.py \
  --input-dir test_set \
  --skip-extraction \
  --dataset-label "Test Set"

# 4. Force re-extraction (e.g., after prompt changes)
python benchmark_data/run_sdrf_benchmark.py \
  --input-dir test_set \
  --force-extraction

# 5. Benchmark pre-existing DocETL outputs for a specific model
python benchmark_data/run_sdrf_benchmark.py \
  --input-dir test_set \
  --skip-extraction \
  --model-label claude \
  --extraction-dir benchmark_data/Testing_final/test_set/claude \
  --config benchmark_data/Testing_final/claude_config.yaml \
  --dataset-label "Test Set"
```

> **Note:** `CUDA_VISIBLE_DEVICES=""` forces the semantic matcher (SciBERT) to use CPU, which avoids conflicts if GPU is running the LLM server.

## Pipeline Steps

| Step | Description | Flag to skip |
|------|-------------|------|
| **1. Convert SDRFs → Goldens** | Parses `.sdrf.tsv` files into golden-set JSONs (3 per PXD: Biological, Technical, Experimental Design) | `--skip-conversion` |
| **2. Run Extraction** | Runs the full DocETL extraction pipeline (`run_docetl.py`) on each PXD manuscript | `--skip-extraction` |
| **3. Compare** | Compares LLM outputs against golden set using exact, normalized, ontology, hierarchical, and semantic matching | — |
| **4. Generate Plots** | Creates per-agent field metrics plots, summary charts, and overall metrics | — |

## Arguments

| Flag | Description | Default |
|------|-------------|---------|
| `--input-dir` | Input directory within `benchmark_data/` | `matched` |
| `--config` | Path to LLM config YAML | `config.yaml` |
| `--model-label` | Model name for output dirs/plots (e.g. `claude`, `gpt`) | auto-detect |
| `--extraction-dir` | Path to pre-existing DocETL outputs (use with `--skip-extraction`) | auto |
| `--output-dir` | Path to save reports/plots (absolute or relative) | auto |
| `--dataset-label` | Label shown in plot titles (e.g. `"Test Set"`) | none |
| `--workers` | Parallel extraction workers | `4` |
| `--limit` | Limit to N PXDs (for testing) | all |
| `--force-extraction` | Clear and re-extract all PXDs | off |
| `--skip-extraction` | Skip extraction, only compare+plot | off |
| `--skip-conversion` | Skip SDRF→golden conversion | off |
| `--no-filter` | Include metadata-only fields | off |
| `--integrate` | Enable integration agent | off |
| `--runassessor-dir` | Aggregated results directory for integration | — |

## Data Splits

| Split | Directory | PXDs | Description |
|-------|-----------|------|-------------|
| **Train** | `matched/` | 107 | Full training set with SDRF `.tsv` files |
| **Test** | `test_set/` | 12 | Held-out test set with SDRF `.tsv` files |
| **New Test** | `new_test_set/` | 18 | Additional datasets with JSON annotation goldens |

> The **test** and **new_test** splits are benchmarked together as a combined 30-PXD test set. Pass `--input-dir test_set` to run on this combined set.

## Outputs

All outputs are saved to `reports_{input_dir}/` (or `reports_{input_dir}_{model_label}/`):

```
reports_test_set/
├── plots/
│   ├── biologicalagent_sdrf_benchmark.png      # Per-field metrics (Biological)
│   ├── technicalagent_sdrf_benchmark.png       # Per-field metrics (Technical)
│   ├── experimentaldesignagent_sdrf_benchmark.png  # Per-field metrics (Exp. Design)
│   ├── sdrf_benchmark_summary.png              # Match type distribution
│   ├── sdrf_benchmark_overall.png              # Overall P/R/F1 bars
│   └── overall_agent_metrics.png               # Per-agent grouped P/R/F1
├── sdrf_benchmark_summary.json                 # Machine-readable metrics
├── sdrf_benchmark_detailed.csv                 # Per-PXD per-field results
├── biologicalagent_sdrf_field_metrics.csv       # Field-level stats
├── technicalagent_sdrf_field_metrics.csv
└── experimentaldesignagent_sdrf_field_metrics.csv
```

## Benchmark Scripts

| Script | Purpose |
|--------|---------|
| `run_sdrf_benchmark.py` | Main benchmark runner (orchestrates all steps) |
| `sdrf_to_golden.py` | Converts `.sdrf.tsv` → golden-set JSON |
| `annotation_to_golden.py` | Converts annotation JSON → golden-set JSON (for `new_test_set`) |
| `dataset_mapping.json` | Maps PXD IDs to their SDRF, manuscript, and aggregated result paths |

## Evaluated Fields

### BiologicalAgent
`species`, `organ`, `cell_type`, `cell_line`, `disease`, `strain`, `BMI`, `developmental_stage`, `ethnicity`, `material_type`

> `age` and `sex` are extracted by the pipeline but excluded from evaluation by default (metadata-only — typically not stated in manuscripts). Use `--no-filter` to include them.

### TechnicalAgent
`instrument`, `cleavage_agent`, `label`, `fragmentation`, `ptm`, `reduction_reagent`, `collision_energy`, `acquisition_method`, `enrichment_method`, `fractionation`, `mass_analyzer`, `precursor_tolerance`, `fragment_tolerance`

> `precursor_tolerance` and `fragment_tolerance` are excluded by default (metadata-only). Use `--no-filter` to include them.

### ExperimentalDesignAgent
`replicates`, `technical_replicates`, `number_of_samples`, `fractions`, `factor_value`, `experimental_design`, `technology_type`, `missed_cleavages`

> Fields are only compared when the golden annotation has non-null values.

## Semantic Matching

The evaluator uses a 5-tier matching hierarchy:

1. **Exact** — Case-insensitive string match
2. **Normalized** — After removing common suffixes, abbreviation expansion
3. **Ontology** — Accession-based lookup (e.g., `CL:0000084` matches `T cell`)
4. **Hierarchical** — Parent/child ontology relationships (e.g., `HeLa` is-a `cell line`)
5. **Semantic** — SciBERT cosine similarity above threshold
