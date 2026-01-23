# PRIDE Metadata Extraction Framework

An agentic pipeline for extracting and normalizing metadata from scientific manuscripts, specifically designed for proteomics and mass spectrometry data submissions to the PRIDE database.

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
| **Normalization** | Maps terms to ontologies using SapBERT embeddings |

## Supported Ontologies

19 biomedical ontologies are supported for term normalization:

| Category | Ontologies |
|----------|------------|
| Cell/Tissue | CL, CLO, BTO, UBERON |
| Species | Curated NCBITaxon subset, Rat Strains |
| Disease | DOID, Mondo |
| Mass Spec | PSI-MS, PRIDE-CV, UNIMOD, PSI-Mod |
| Other | ChEBI, EFO, PATO, Plant Ontology, FlyBase, ZFA, FBbt |

## Installation

```bash
# Clone the repository
git clone https://github.com/CompOmics/agentic-metadata.git
cd agentic-metadata
cd extraction_framework

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Download ontologies
python -m normalization.download

# Build ontology indices (first time only, ~10 min)
python -m normalization.build_index
```

## Usage

### Basic Extraction

```bash
# Run all agents
python main.py all --input /path/to/documents/

# Run specific agent
python main.py biological --input /path/to/documents/

# With ontology normalization
python main.py all --input /path/to/documents/ --normalize

# With integration from external source
python main.py all --input /path/to/documents/ --integrate --runassessor-dir /path/to/data/
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
├── agents/                 # Extraction agents
│   ├── biological_agent.py
│   ├── technical_agent.py
│   ├── experimental_agent.py
│   └── integration_agent.py
├── core/                   # Core modules
│   ├── extractor.py
│   ├── llm.py
│   └── prompts.py
├── normalization/          # Ontology normalization
│   ├── config.py
│   ├── normalizer.py
│   ├── ontology.py
│   ├── index.py
│   └── build_index.py
└── validation/             # Output validation
    └── validator.py
```

## License

[Specify license]

## Citation

[Add citation if applicable]
