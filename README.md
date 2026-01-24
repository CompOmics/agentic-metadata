# PRIDE Metadata Extraction Framework

An agentic pipeline for extracting and normalizing metadata from scientific manuscripts, specifically designed for proteomics and mass spectrometry data submissions to the PRIDE database.

## Quick Start

```bash
# Clone the repository
git clone https://github.com/CompOmics/agentic-metadata.git
cd agentic-metadata/extraction_framework

# Run setup (creates venv, installs deps, downloads ontologies)
# Requires 'faiss-cpu' for high-performance indexing
./setup.sh

# Activate environment and run
source venv/bin/activate
python main.py all --input /path/to/documents/
```

## Overview

This framework uses specialized LLM-based agents to extract structured metadata from scientific text, normalize terms against biomedical ontologies, and integrate data from multiple sources.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Input Documents                          │
└─────────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│ Biological      │ │ Technical       │ │ Experimental    │
│ Agent           │ │ Agent           │ │ Design Agent    │
└─────────────────┘ └─────────────────┘ └─────────────────┘
          │                   │                   │
          └───────────────────┼───────────────────┘
                              ▼
                    ┌─────────────────┐
                    │ Integration     │
                    │ Agent           │
                    └─────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │ Normalization   │
                    │ (Ontology-based)│
                    └─────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │ Structured      │
                    │ Output (JSON)   │
                    └─────────────────┘
```

## Agents

| Agent | Description |
|-------|-------------|
| **BiologicalAgent** | Extracts species, cell types, tissues, diseases |
| **TechnicalAgent** | Extracts instruments, modifications, labelling methods |
| **ExperimentalDesignAgent** | Extracts experimental design, sample preparation |
| **IntegrationAgent** | Merges multi-source data, resolves conflicts |
| **NormalizationAgent** | Maps terms to ontologies using SapBERT embeddings |

## Supported Ontologies

19 biomedical ontologies are supported for term normalization:

| Category | Ontologies |
|----------|------------|
| Cell/Tissue | CL, CLO, BTO, UBERON |
| Species | Curated NCBITaxon subset, Rat Strains |
| Disease | DOID, Mondo |
| Mass Spec | PSI-MS, PRIDE-CV, UNIMOD, PSI-Mod |
| Other | ChEBI, EFO, PATO, Plant Ontology, FlyBase, ZFA, FBbt |

## Configuration

The pipeline is configured via a `config.yaml` file in the root directory. You can customize paths, backend settings, and agent parameters here:

```yaml
paths:
  input_dir: "./docs"            # Relative path to input documents
  output_dir: "./framework_output"
  ontology_dir: "ontologies"

normalization:
  backend: "faiss"               # Options: faiss (fastest), sklearn, annoy
  use_quantization: true         # Reduces memory usage by ~90%
  use_gpu: true                  # Use GPU for embeddings if available

agents:
  temperatures: [0.0]            # LLM sampling settings
  validate: true                 # Enable the standard Validation Agent
```

## Installation

### Option 1: Automated Setup (Recommended)

```bash
# Clone and enter directory
git clone https://github.com/CompOmics/agentic-metadata.git
cd agentic-metadata/extraction_framework

# Run the setup script
./setup.sh

# For full setup including pre-built indices (~10 min):
./setup.sh --full

# For quick setup (skip large ontologies like ChEBI):
./setup.sh --quick
```

### Option 2: Manual Setup

```bash
# Clone the repository
git clone https://github.com/CompOmics/agentic-metadata.git
cd agentic-metadata/extraction_framework

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
# Includes faiss-cpu for indexing and requests for robust downloads
pip install -r requirements.txt

# Download ontologies
python -m normalization.download

# Build ontology indices (optional, ~10 min)
# Indices are also built automatically on first --normalize run
python -m normalization.build_index
```

### Disk Space Requirements

| Component | Size |
|-----------|------|
| Core dependencies | ~2 GB (PyTorch, transformers) |
| Ontology files | ~500 MB |
| Ontology indices | ~4 GB |

## Usage

### Basic Extraction

```bash
# Run all agents
python main.py all --input /path/to/documents/

# Run specific agent
python main.py biological --input /path/to/documents/

# With ontology normalization (uses FAISS backend by default)
python main.py all --input /path/to/documents/ --normalize

# With integration from external source
python main.py all --input /path/to/documents/ --integrate --runassessor-dir /path/to/data/
```

### Configuration Overrides

You can override `config.yaml` defaults using CLI arguments:
-   `--ontology-dir`: Custom ontology location
-   `--validate`: Force validation on/off
-   `--output`: Custom output directory

### Using the Pipeline Script

```bash
# Run with default settings
./run_pipeline.sh

# With custom input directory
./run_pipeline.sh --input /path/to/documents/

# With normalization
./run_pipeline.sh --normalize
```

### Command Line Options

| Option | Description |
|--------|-------------|
| `mode` | `biological`, `technical`, `experimental`, or `all` |
| `--input` | Input directory with `.txt` files |
| `--output` | Output directory (default: `framework_output/`) |
| `--normalize` | Enable ontology normalization |
| `--integrate` | Enable integration with external data |
| `--validate` | Enable validation agent |
| `--temperatures` | LLM sampling temperatures |

## Output Format

Extractions are saved as JSON with provenance:

```json
{
  "species": {
    "value": "Homo sapiens",
    "ontology_id": "NCBITaxon:9606",
    "similarity": 0.98,
    "is_normalized": true,
    "evidence": "Human plasma samples were collected..."
  }
}
```

## Project Structure

```
extraction_framework/
├── main.py                 # Pipeline entry point
├── setup.sh                # First-run setup script
├── run_pipeline.sh         # Pipeline runner with checks
├── requirements.txt        # Python dependencies
├── agents/                 # Extraction agents
│   ├── biological_agent.py
│   ├── technical_agent.py
│   ├── experimental_agent.py
│   ├── integration_agent.py
│   └── normalization_agent.py
├── core/                   # Core modules
│   ├── extractor.py
│   ├── llm.py
│   └── prompts.py
├── normalization/          # Ontology normalization
│   ├── config.py
│   ├── normalizer.py
│   ├── ontology.py
│   ├── index.py
│   ├── download.py
│   └── build_index.py
├── validation/             # Output validation
│   └── validator.py
├── ontologies/             # Ontology files (gitignored)
└── ontology_cache/         # Cached indices (gitignored)
```

## Troubleshooting

### "Module not found" errors

Make sure you've activated the virtual environment:
```bash
source venv/bin/activate
```

### Ontology download fails

Some ontology servers may be temporarily unavailable. Try:
```bash
# Retry failed downloads
python -m normalization.download

# Check which ontologies exist
python -m normalization.download --check
```

### Normalization is slow on first run

The first `--normalize` run builds embedding indices (~10 min). Subsequent runs use cached indices. To pre-build:
```bash
python -m normalization.build_index
```

### GPU out of memory

Disable GPU for embeddings in `config.yaml`:
```yaml
normalization:
  use_gpu: false
```
or via code:
```python
# In your script
from normalization.config import NormalizationConfig
config = NormalizationConfig(use_gpu=False)
```

### Installation fails on "faiss"

If `faiss-cpu` fails to install, ensure you have a compatible Python version (3.8-3.11 recommended). You can fallback to the legacy backend by editing `config.yaml`:
```yaml
normalization:
  backend: "sklearn"  # Slower but fewer dependencies
```

## License

[Specify license]

## Citation

[Add citation if applicable]
