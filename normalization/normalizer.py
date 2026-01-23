"""
Term normalization against ontologies.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any

from .ontology import OntologyGraph, OntologyNode, OntologyLoader
from .index import OntologyIndex
from .config import NormalizationConfig

logger = logging.getLogger(__name__)


@dataclass
class NormalizationResult:
    """
    Result of normalizing a term.
    
    Attributes:
        original_term: Original input term
        ontology_id: Matched ontology term ID
        ontology_name: Matched ontology term name
        similarity: Similarity score
        matched_text: Which text was matched (name/synonym)
        candidates: Alternative matches
        entity_type: Type of entity (cell_type, tissue, etc.)
        is_normalized: Whether normalization succeeded
    """
    original_term: str
    ontology_id: Optional[str] = None
    ontology_name: Optional[str] = None
    similarity: float = 0.0
    matched_text: Optional[str] = None
    candidates: List[Tuple[str, str, float]] = field(default_factory=list)
    entity_type: str = ""
    is_normalized: bool = False
    
    @property
    def confidence(self) -> str:
        """Categorize confidence level."""
        if self.similarity >= 0.9:
            return 'high'
        elif self.similarity >= 0.7:
            return 'medium'
        else:
            return 'low'
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'original_term': self.original_term,
            'ontology_id': self.ontology_id,
            'ontology_name': self.ontology_name,
            'similarity': self.similarity,
            'matched_text': self.matched_text,
            'entity_type': self.entity_type,
            'is_normalized': self.is_normalized,
            'confidence': self.confidence,
            'num_candidates': len(self.candidates),
        }


class TermNormalizer:
    """
    Normalize terms against ontologies.
    
    Uses embedding-based search and disambiguation to find
    the best matching ontology terms.
    
    Example:
        >>> normalizer = TermNormalizer()
        >>> normalizer.load_ontology('cl', 'ontologies/cl.obo')
        >>> result = normalizer.normalize('epithelial cell', entity_type='cell_type')
    """
    
    def __init__(self, config: Optional[NormalizationConfig] = None):
        """
        Initialize normalizer.
        
        Args:
            config: Normalization configuration
        """
        self.config = config or NormalizationConfig()
        self.loader = OntologyLoader()
        self.graphs: Dict[str, OntologyGraph] = {}
        self.indices: Dict[str, OntologyIndex] = {}
    
    def load_ontology(self, 
                      ontology_id: str,
                      file_path: str,
                      use_cache: bool = True) -> None:
        """
        Load an ontology and build index.
        
        Args:
            ontology_id: Identifier for ontology (e.g., 'cl')
            file_path: Path to ontology file
            use_cache: Whether to use cached index
        """
        logger.info(f"Loading ontology: {ontology_id}")
        
        # Load graph
        graph = self.loader.load(file_path)
        self.graphs[ontology_id] = graph
        
        # Build or load index
        cache_path = self.config.get_cache_path(ontology_id)
        
        if use_cache:
            self.indices[ontology_id] = OntologyIndex.load_or_build(
                graph, str(cache_path), self.config
            )
        else:
            index = OntologyIndex(self.config)
            index.build(graph, include_synonyms=self.config.use_synonyms)
            self.indices[ontology_id] = index
    
    def load_all_ontologies(self) -> None:
        """Load all configured ontologies."""
        for ontology_id, filename in self.config.ontology_files.items():
            path = self.config.get_ontology_path(ontology_id)
            if path and path.exists():
                self.load_ontology(ontology_id, str(path))
            else:
                logger.warning(f"Ontology file not found: {path}")
    
    def get_ontology_for_entity(self, entity_type: str) -> Optional[str]:
        """Get ontology ID for entity type."""
        return self.config.entity_ontology_map.get(entity_type.lower())
    
    def normalize(self,
                  term: str,
                  entity_type: Optional[str] = None,
                  ontology_id: Optional[str] = None,
                  top_k: Optional[int] = None) -> NormalizationResult:
        """
        Normalize a term against ontology.
        
        Args:
            term: Term to normalize
            entity_type: Type of entity (determines ontology)
            ontology_id: Specific ontology to use
            top_k: Number of candidates to return
            
        Returns:
            NormalizationResult with match details
        """
        top_k = top_k or self.config.top_k
        
        # Determine ontology
        if ontology_id is None and entity_type:
            ontology_id = self.get_ontology_for_entity(entity_type)
        
        if ontology_id is None:
            return NormalizationResult(
                original_term=term,
                entity_type=entity_type or '',
                is_normalized=False
            )
        
        if ontology_id not in self.indices:
            logger.warning(f"Ontology not loaded: {ontology_id}")
            return NormalizationResult(
                original_term=term,
                entity_type=entity_type or '',
                is_normalized=False
            )
        
        # Search index
        index = self.indices[ontology_id]
        candidates = index.search(term, top_k=top_k)
        
        if not candidates:
            return NormalizationResult(
                original_term=term,
                entity_type=entity_type or '',
                is_normalized=False
            )
        
        # Get best match
        best_id, best_text, best_sim = candidates[0]
        
        # Check threshold
        is_normalized = best_sim >= self.config.similarity_threshold
        
        # Get name from graph
        graph = self.graphs.get(ontology_id)
        node = graph.get_node(best_id) if graph else None
        ontology_name = node.name if node else best_text
        
        return NormalizationResult(
            original_term=term,
            ontology_id=best_id,
            ontology_name=ontology_name,
            similarity=best_sim,
            matched_text=best_text,
            candidates=candidates,
            entity_type=entity_type or '',
            is_normalized=is_normalized
        )
    
    def normalize_batch(self,
                        terms: List[str],
                        entity_type: Optional[str] = None,
                        ontology_id: Optional[str] = None) -> List[NormalizationResult]:
        """
        Normalize multiple terms.
        
        Args:
            terms: List of terms
            entity_type: Entity type for all terms
            ontology_id: Ontology for all terms
            
        Returns:
            List of NormalizationResult objects
        """
        return [
            self.normalize(term, entity_type, ontology_id)
            for term in terms
        ]
    
    def get_parent_terms(self,
                        term_id: str,
                        ontology_id: str,
                        max_depth: int = 3) -> List[Tuple[str, str]]:
        """
        Get parent terms for enrichment.
        
        Args:
            term_id: Ontology term ID
            ontology_id: Ontology identifier
            max_depth: Maximum depth to traverse
            
        Returns:
            List of (parent_id, parent_name) tuples
        """
        if ontology_id not in self.graphs:
            return []
        
        graph = self.graphs[ontology_id]
        ancestors = graph.get_ancestors(term_id, max_depth=max_depth)
        
        results = []
        for ancestor_id in ancestors:
            node = graph.get_node(ancestor_id)
            if node:
                results.append((ancestor_id, node.name))
        
        return results
    
    def disambiguate(self,
                    candidates: List[Tuple[str, str, float]],
                    context: str,
                    ontology_id: str) -> Tuple[str, str, float]:
        """
        Disambiguate between candidates using context.
        
        Args:
            candidates: List of (id, text, similarity) candidates
            context: Additional context text
            ontology_id: Ontology identifier
            
        Returns:
            Best matching (id, text, similarity) tuple
        """
        if len(candidates) <= 1:
            return candidates[0] if candidates else ('', '', 0.0)
        
        # Simple heuristic: prefer exact matches
        for cand_id, cand_text, sim in candidates:
            if cand_text.lower() == context.lower():
                return (cand_id, cand_text, sim)
        
        # Otherwise return highest similarity
        return candidates[0]
    
    def find_common_ancestor(self,
                            term1_id: str,
                            term2_id: str,
                            ontology_id: str) -> Optional[Tuple[str, str]]:
        """
        Find common ancestor of two terms.
        
        Useful for parent enrichment when two methods disagree.
        
        Args:
            term1_id: First term ID
            term2_id: Second term ID
            ontology_id: Ontology identifier
            
        Returns:
            (ancestor_id, ancestor_name) or None
        """
        if ontology_id not in self.graphs:
            return None
        
        graph = self.graphs[ontology_id]
        common_id = graph.get_common_ancestor(term1_id, term2_id)
        
        if common_id:
            node = graph.get_node(common_id)
            if node:
                return (common_id, node.name)
        
        return None


class MultiOntologyNormalizer:
    """
    Normalize terms across multiple ontologies.
    
    Automatically selects ontology based on entity type.
    
    Example:
        >>> normalizer = MultiOntologyNormalizer()
        >>> normalizer.load_all()
        >>> result = normalizer.normalize('liver', 'tissue')
    """
    
    def __init__(self, config: Optional[NormalizationConfig] = None):
        """
        Initialize multi-ontology normalizer.
        
        Args:
            config: Configuration
        """
        self.config = config or NormalizationConfig()
        self.normalizer = TermNormalizer(config)
    
    def load_all(self) -> None:
        """Load all configured ontologies."""
        self.normalizer.load_all_ontologies()
    
    def normalize(self,
                  term: str,
                  entity_type: str) -> NormalizationResult:
        """
        Normalize term using appropriate ontology.
        
        Args:
            term: Term to normalize
            entity_type: Entity type
            
        Returns:
            NormalizationResult
        """
        return self.normalizer.normalize(term, entity_type=entity_type)
    
    def normalize_extraction_result(self,
                                   extraction: Dict[str, Any]) -> Dict[str, NormalizationResult]:
        """
        Normalize all entities in an extraction result.
        
        Args:
            extraction: Dictionary with entity fields
            
        Returns:
            Dictionary mapping field to NormalizationResult
        """
        results = {}
        
        entity_types = ['species', 'cell_type', 'tissue', 'disease', 'organism']
        
        for entity_type in entity_types:
            if entity_type in extraction:
                term = extraction[entity_type]
                if term and isinstance(term, str):
                    results[entity_type] = self.normalize(term, entity_type)
        
        return results
