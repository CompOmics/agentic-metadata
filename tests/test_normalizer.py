"""
Tests for the normalization module.

Tests cover:
- OntologyLoader parsing
- TermNormalizer matching
- NormalizationResult properties
"""

import pytest
from pathlib import Path


class TestOntologyLoader:
    """Tests for OntologyLoader parsing."""
    
    def test_load_obo_file(self, test_ontology_path: Path):
        """Test loading an OBO format ontology."""
        from normalization.ontology import OntologyLoader
        
        loader = OntologyLoader()
        graph = loader.load(str(test_ontology_path))
        
        assert graph is not None
        assert len(graph) > 0
    
    def test_get_node_by_id(self, test_ontology_path: Path):
        """Test retrieving a node by ID."""
        from normalization.ontology import OntologyLoader
        
        loader = OntologyLoader()
        graph = loader.load(str(test_ontology_path))
        
        node = graph.get_node("CL:0000066")
        assert node is not None
        assert node.name == "epithelial cell"
    
    def test_node_synonyms(self, test_ontology_path: Path):
        """Test that synonyms are loaded correctly."""
        from normalization.ontology import OntologyLoader
        
        loader = OntologyLoader()
        graph = loader.load(str(test_ontology_path))
        
        node = graph.get_node("CL:0000738")
        assert node is not None
        assert "white blood cell" in node.synonyms or "WBC" in node.synonyms
    
    def test_node_all_names(self, test_ontology_path: Path):
        """Test all_names includes name and synonyms."""
        from normalization.ontology import OntologyLoader
        
        loader = OntologyLoader()
        graph = loader.load(str(test_ontology_path))
        
        node = graph.get_node("NCBITaxon:9606")
        all_names = node.all_names
        
        assert "Homo sapiens" in all_names
        assert "human" in all_names


class TestNormalizationResult:
    """Tests for NormalizationResult dataclass."""
    
    def test_confidence_high(self):
        """Test high confidence classification."""
        from normalization.normalizer import NormalizationResult
        
        result = NormalizationResult(
            original_term="human",
            ontology_id="NCBITaxon:9606",
            similarity=0.95,
            is_normalized=True,
        )
        
        assert result.confidence == 'high'
    
    def test_confidence_medium(self):
        """Test medium confidence classification."""
        from normalization.normalizer import NormalizationResult
        
        result = NormalizationResult(
            original_term="epithelial",
            similarity=0.75,
            is_normalized=True,
        )
        
        assert result.confidence == 'medium'
    
    def test_confidence_low(self):
        """Test low confidence classification."""
        from normalization.normalizer import NormalizationResult
        
        result = NormalizationResult(
            original_term="unknown term",
            similarity=0.5,
            is_normalized=False,
        )
        
        assert result.confidence == 'low'
    
    def test_to_dict(self):
        """Test conversion to dictionary."""
        from normalization.normalizer import NormalizationResult
        
        result = NormalizationResult(
            original_term="human",
            ontology_id="NCBITaxon:9606",
            ontology_name="Homo sapiens",
            similarity=0.98,
            is_normalized=True,
            entity_type="species",
        )
        
        d = result.to_dict()
        
        assert d['original_term'] == "human"
        assert d['ontology_id'] == "NCBITaxon:9606"
        assert d['is_normalized'] == True
        assert 'confidence' in d


class TestTermNormalizer:
    """Tests for TermNormalizer (without embeddings)."""
    
    def test_get_ontology_for_entity(self):
        """Test entity type to ontology mapping."""
        from normalization.normalizer import TermNormalizer
        
        normalizer = TermNormalizer()
        
        assert normalizer.get_ontology_for_entity('species') == 'species'
        assert normalizer.get_ontology_for_entity('cell_type') == 'cl'
        assert normalizer.get_ontology_for_entity('tissue') == 'uberon'
        assert normalizer.get_ontology_for_entity('disease') == 'doid'
    
    def test_normalize_unknown_ontology(self):
        """Test normalization with unknown ontology returns not normalized."""
        from normalization.normalizer import TermNormalizer
        
        normalizer = TermNormalizer()
        
        result = normalizer.normalize("some term", ontology_id="nonexistent")
        
        assert result.is_normalized == False
    
    def test_normalize_no_entity_type(self):
        """Test normalization without entity type."""
        from normalization.normalizer import TermNormalizer
        
        normalizer = TermNormalizer()
        
        result = normalizer.normalize("some term")
        
        # Without entity type or ontology_id, should return not normalized
        assert result.is_normalized == False


class TestTermExpansion:
    """Tests for TermNormalizer._expand_term() -- pure logic, no embeddings needed."""

    def _make_normalizer(self, aliases=None):
        from normalization.normalizer import TermNormalizer
        from normalization.config import NormalizationConfig
        config = NormalizationConfig()
        if aliases:
            config.term_aliases = aliases
        return TermNormalizer(config)

    # --- Genus-prefix heuristic (p.falciparum style) ---

    def test_expand_dotted_genus_falciparum(self):
        """p.falciparum → Plasmodium falciparum"""
        normalizer = self._make_normalizer()
        result = normalizer._expand_term("p.falciparum")
        assert result == "Plasmodium falciparum"

    def test_expand_dotted_genus_ecoli(self):
        """e.coli → Escherichia coli"""
        normalizer = self._make_normalizer()
        result = normalizer._expand_term("e.coli")
        assert result == "Escherichia coli"

    def test_expand_dotted_genus_hsapiens(self):
        """h.sapiens → Homo sapiens"""
        normalizer = self._make_normalizer()
        result = normalizer._expand_term("h.sapiens")
        assert result == "Homo sapiens"

    def test_expand_dotted_genus_musculus(self):
        """m.musculus → Mus musculus"""
        normalizer = self._make_normalizer()
        result = normalizer._expand_term("m.musculus")
        assert result == "Mus musculus"

    def test_expand_unknown_prefix_returns_none(self):
        """Unknown single-letter prefix with no alias should return None."""
        normalizer = self._make_normalizer()
        # 'y' is not in _GENUS_PREFIX_MAP
        result = normalizer._expand_term("y.species")
        assert result is None

    # --- Dot-binomial where genus is written in full ---

    def test_expand_dot_binomial_full_genus(self):
        """Plasmodium.falciparum → Plasmodium falciparum"""
        normalizer = self._make_normalizer()
        result = normalizer._expand_term("Plasmodium.falciparum")
        assert result == "Plasmodium falciparum"

    def test_expand_dot_binomial_homo_sapiens(self):
        """Homo.sapiens → Homo sapiens"""
        normalizer = self._make_normalizer()
        result = normalizer._expand_term("Homo.sapiens")
        assert result == "Homo sapiens"

    # --- Alias dict lookup ---

    def test_expand_alias_dict_exact(self):
        """Custom alias is expanded correctly."""
        normalizer = self._make_normalizer(aliases={"Pf": "Plasmodium falciparum"})
        result = normalizer._expand_term("Pf")
        assert result == "Plasmodium falciparum"

    def test_expand_alias_dict_case_insensitive(self):
        """Alias lookup is case-insensitive on the key."""
        normalizer = self._make_normalizer(aliases={"PF": "Plasmodium falciparum"})
        result = normalizer._expand_term("pf")
        assert result == "Plasmodium falciparum"

    # --- No-change cases ---

    def test_no_expansion_for_full_name(self):
        """Full binomial names should not be modified."""
        normalizer = self._make_normalizer()
        result = normalizer._expand_term("Homo sapiens")
        assert result is None

    def test_no_expansion_for_plain_word(self):
        """Plain single words with no dots should not be modified."""
        normalizer = self._make_normalizer()
        result = normalizer._expand_term("human")
        assert result is None

    # --- NormalizationResult fields ---

    def test_expanded_term_field_present_in_result(self):
        """When expansion fires, the expanded_term field is populated."""
        from normalization.normalizer import NormalizationResult
        result = NormalizationResult(
            original_term="p.falciparum",
            expanded_term="Plasmodium falciparum",
            ontology_id="NCBITaxon:5833",
            similarity=0.95,
            is_normalized=True,
        )
        d = result.to_dict()
        assert d.get('expanded_term') == "Plasmodium falciparum"

    def test_expanded_term_absent_when_none(self):
        """When no expansion, expanded_term key is absent from to_dict output."""
        from normalization.normalizer import NormalizationResult
        result = NormalizationResult(
            original_term="Homo sapiens",
            ontology_id="NCBITaxon:9606",
            similarity=0.98,
            is_normalized=True,
        )
        d = result.to_dict()
        assert 'expanded_term' not in d


class TestNormalizationConfig:
    """Tests for NormalizationConfig."""
    
    def test_default_values(self):
        """Test default configuration values."""
        from normalization.config import NormalizationConfig
        
        config = NormalizationConfig()
        
        assert config.similarity_threshold == 0.7
        assert config.top_k == 5
        assert config.use_synonyms == True
    
    def test_get_cache_path(self):
        """Test cache path generation."""
        from normalization.config import NormalizationConfig
        
        config = NormalizationConfig(cache_dir="/tmp/cache")
        
        path = config.get_cache_path("cl")
        
        assert str(path) == "/tmp/cache/cl_index.pkl"
    
    def test_entity_ontology_map(self):
        """Test entity to ontology mapping exists."""
        from normalization.config import NormalizationConfig
        
        config = NormalizationConfig()
        
        assert 'species' in config.entity_ontology_map
        assert 'cell_type' in config.entity_ontology_map
        assert 'tissue' in config.entity_ontology_map
