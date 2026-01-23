"""
Normalization module for ontology-based entity normalization.

Components:
    - OntologyLoader: Load ontologies from OBO/OWL files
    - OntologyIndex: Build searchable index with embeddings
    - TermNormalizer: Normalize terms against ontologies
    - download_all_ontologies: Download required ontology files
"""

from .ontology import OntologyLoader, OntologyGraph, OntologyNode
from .index import OntologyIndex
from .normalizer import TermNormalizer, NormalizationResult
from .config import NormalizationConfig
from .download import (
    download_all_ontologies,
    download_ontology,
    check_ontologies,
    get_ontology_info,
    ONTOLOGY_SOURCES,
)

__all__ = [
    'OntologyLoader',
    'OntologyGraph',
    'OntologyNode',
    'OntologyIndex',
    'TermNormalizer',
    'NormalizationResult',
    'NormalizationConfig',
    # Download utilities
    'download_all_ontologies',
    'download_ontology',
    'check_ontologies',
    'get_ontology_info',
    'ONTOLOGY_SOURCES',
]
