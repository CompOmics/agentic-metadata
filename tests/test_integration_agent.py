"""
Integration tests for the IntegrationAgent.

Tests the PRIDE descriptor priority logic and disagreement logging feature.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
import tempfile
import shutil

from agents.integration_agent import IntegrationAgent


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def sample_meti_data():
    """Sample METI technical pipeline data with PRIDE descriptors and tool inference."""
    return {
        "pxd_id": "PXD012345",
        "pipeline_version": "1.0",
        "pride_metadata": {
            "organisms": [
                {"name": "Homo sapiens", "accession": "9606", "cvLabel": "NCBITaxon"}
            ],
            "organismParts": [
                {"name": "liver", "accession": "UBERON:0002107"}
            ],
            "diseases": [
                {"name": "hepatocellular carcinoma", "accession": "DOID:684"}
            ],
            "instruments": [
                {"name": "Q Exactive HF", "accession": "MS:1002523"}
            ],
            "identifiedPTMStrings": [
                {"name": "Oxidation", "value": "Oxidation"}
            ],
            "experimentTypes": [
                {"name": "Shotgun proteomics", "accession": "PRIDE:0000311"}
            ],
            "quantificationMethods": [
                {"name": "Label-free quantification", "value": "Label-free"}
            ],
            "references": [
                {"pubmedID": 12345678}
            ]
        },
        "organism_identification": {
            "results": [
                {
                    "data": [
                        {"taxon_name": "Rattus norvegicus", "taxon_id": 10116, "score": 0.85},
                        {"taxon_name": "Mus musculus", "taxon_id": 10090, "score": 0.12}
                    ]
                }
            ]
        },
        "runAssessor": {
            "files": {
                "file1.raw": {
                    "instrument_model": {"name": "Orbitrap Fusion", "accession": "MS:1002416"},
                    "spectra_stats": {
                        "acquisition_type": "DDA",
                        "fragmentation_tag": "HCD",
                        "n_ms2_spectra": 50000,
                        "n_spectra": 55000
                    }
                }
            }
        }
    }


@pytest.fixture
def sample_meti_data_no_pride_org():
    """METI data WITHOUT PRIDE organisms (should fallback to tool)."""
    return {
        "pxd_id": "PXD098765",
        "pipeline_version": "1.0",
        "pride_metadata": {
            "organisms": [],  # Empty - should fallback to tool
            "instruments": [
                {"name": "Q Exactive HF", "accession": "MS:1002523"}
            ],
            "references": [{"pubmedID": 87654321}]
        },
        "organism_identification": {
            "results": [
                {
                    "data": [
                        {"taxon_name": "Drosophila melanogaster", "taxon_id": 7227, "score": 0.95}
                    ]
                }
            ]
        },
        "runAssessor": {"files": {}}
    }


@pytest.fixture
def sample_llm_extraction():
    """Sample LLM extraction output."""
    return {
        "species": {
            "value": "Homo sapiens",
            "evidence": "Human liver tissue samples were analyzed"
        },
        "tissue": {
            "value": "liver",
            "evidence": "liver tissue samples"
        },
        "disease": {
            "value": "hepatocellular carcinoma",
            "evidence": "patients with hepatocellular carcinoma"
        },
        "_confidence": {
            "overall": 0.85
        }
    }


@pytest.fixture
def mock_meti_dir(tmp_path, sample_meti_data):
    """Create temporary METI directory with sample data."""
    meti_dir = tmp_path / "meti_data"
    meti_dir.mkdir()

    with open(meti_dir / "PXD012345_aggregated_results.json", 'w') as f:
        json.dump(sample_meti_data, f)

    return meti_dir


# ============================================================================
# Source Resolution Tests
# ============================================================================

class TestSourceResolution:
    """Tests source-preserving resolution between PRIDE and tool evidence."""
    
    def test_matching_llm_and_pride_outvote_tool_organism(
        self, mock_meti_dir, sample_meti_data, sample_llm_extraction
    ):
        """LLM and PRIDE agreement should outvote a conflicting tool result."""
        agent = IntegrationAgent(str(mock_meti_dir))
        
        # Manually inject the data for testing
        result = agent.enrich("PXD012345", sample_llm_extraction, agent_type="BiologicalAgent")
        
        # LLM and PRIDE say "Homo sapiens" while the tool reports
        # "Rattus norvegicus", so majority vote resolves to Homo sapiens.
        assert result["species"]["resolved"] == "Homo sapiens"
        assert result["species"]["sources"]["meti"]["value"] == "Rattus norvegicus"
        assert result["species"]["sources"]["pride"]["value"] == "Homo sapiens"
    
    def test_tool_used_when_no_pride_organisms(
        self, tmp_path, sample_meti_data_no_pride_org, sample_llm_extraction
    ):
        """Tool inference should be used when no PRIDE organisms exist."""
        meti_dir = tmp_path / "meti_data"
        meti_dir.mkdir()

        with open(meti_dir / "PXD098765_aggregated_results.json", 'w') as f:
            json.dump(sample_meti_data_no_pride_org, f)

        agent = IntegrationAgent(str(meti_dir))
        result = agent.enrich("PXD098765", sample_llm_extraction, agent_type="BiologicalAgent")
        
        # No PRIDE organisms, should fallback to tool
        assert result["species"]["resolved"] == "Drosophila melanogaster"
    
    def test_tool_instrument_selected_when_llm_value_is_unknown(
        self, mock_meti_dir, sample_meti_data
    ):
        """Direct RunAssessor instrument evidence should take precedence."""
        agent = IntegrationAgent(str(mock_meti_dir))
        
        tech_extraction = {
            "instrument": {"value": "unknown", "evidence": ""}
        }
        
        result = agent.enrich("PXD012345", tech_extraction, agent_type="TechnicalAgent")
        
        # PRIDE says "Q Exactive HF", while RunAssessor identifies
        # "Orbitrap Fusion". With no LLM value, direct tool evidence wins.
        assert result["instrument"]["resolved"] == "Orbitrap Fusion"
        assert result["instrument"]["sources"]["pride"]["value"] == "Q Exactive HF"


# ============================================================================
# Disagreement Detection Tests
# ============================================================================

class TestDisagreementDetection:
    """Tests for PRIDE vs Tool disagreement detection."""
    
    def test_disagreement_detected_for_species(
        self, mock_meti_dir, sample_llm_extraction
    ):
        """Should detect disagreement between PRIDE and tool for species."""
        agent = IntegrationAgent(str(mock_meti_dir))
        
        result = agent.enrich("PXD012345", sample_llm_extraction, agent_type="BiologicalAgent")
        
        # Should have detected disagreement (PRIDE: Homo sapiens, Tool: Rattus norvegicus)
        assert "_ra_disagreements" in result
        
        disagreements = result["_ra_disagreements"]
        species_disagreement = next(
            (d for d in disagreements if d["field"] == "species"), None
        )
        
        assert species_disagreement is not None
        assert species_disagreement["type"] == "PRIDE_VS_TOOL"
        assert species_disagreement["pride_value"] == "Homo sapiens"
        assert species_disagreement["tool_value"] == "Rattus norvegicus"
        assert species_disagreement["tool_name"] == "organism_identification (Peptonizer)"
    
    def test_no_disagreement_when_values_match(self, tmp_path, sample_llm_extraction):
        """No disagreement should be logged when PRIDE and tool agree."""
        ra_data = {
            "pxd_id": "PXD111111",
            "pride_metadata": {
                "organisms": [{"name": "Homo sapiens", "accession": "9606"}],
                "references": [{"pubmedID": 11111111}]
            },
            "organism_identification": {
                "results": [{"data": [{"taxon_name": "Homo sapiens", "taxon_id": 9606, "score": 0.99}]}]
            }
        }
        
        meti_dir = tmp_path / "meti_data"
        meti_dir.mkdir()
        with open(meti_dir / "PXD111111_aggregated_results.json", 'w') as f:
            json.dump(ra_data, f)

        agent = IntegrationAgent(str(meti_dir))
        result = agent.enrich("PXD111111", sample_llm_extraction, agent_type="BiologicalAgent")
        
        # No disagreement - values match
        assert "_ra_disagreements" not in result or len(result.get("_ra_disagreements", [])) == 0


# ============================================================================
# Disagreement Log File Tests
# ============================================================================

class TestDisagreementLogFile:
    """Tests for ra_disagreements.json log file creation."""
    
    def test_batch_creates_disagreement_log(self, mock_meti_dir, sample_llm_extraction, tmp_path):
        """enrich_batch should create ra_disagreements.json file."""
        agent = IntegrationAgent(str(mock_meti_dir))
        
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        
        results = {
            "test_ra_priority/PXD012345_test.txt": sample_llm_extraction
        }
        
        enriched = agent.enrich_batch(results, agent_name="BiologicalAgent", output_dir=str(output_dir))
        
        # Check log file was created
        log_path = output_dir / "ra_disagreements.json"
        assert log_path.exists()
        
        # Check log content
        with open(log_path) as f:
            log_data = json.load(f)
        
        assert len(log_data) > 0
        first_file = list(log_data.keys())[0]
        assert len(log_data[first_file]) > 0
        assert log_data[first_file][0]["type"] == "PRIDE_VS_TOOL"
    
    def test_batch_removes_disagreements_from_individual_outputs(
        self, mock_meti_dir, sample_llm_extraction, tmp_path
    ):
        """Disagreements should be in log file only, not in individual outputs."""
        agent = IntegrationAgent(str(mock_meti_dir))
        
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        
        results = {
            "test_ra_priority/PXD012345_test.txt": sample_llm_extraction
        }
        
        enriched = agent.enrich_batch(results, agent_name="BiologicalAgent", output_dir=str(output_dir))
        
        # Individual outputs should NOT have _ra_disagreements
        for filename, data in enriched.items():
            assert "_ra_disagreements" not in data
    
    def test_no_log_file_when_no_disagreements(self, tmp_path, sample_llm_extraction):
        """No log file should be created when there are no disagreements."""
        # Create data where PRIDE and tool agree
        ra_data = {
            "pxd_id": "PXD222222",
            "pride_metadata": {
                "organisms": [{"name": "Homo sapiens", "accession": "9606"}],
                "references": [{"pubmedID": 22222222}]
            },
            "organism_identification": {
                "results": [{"data": [{"taxon_name": "Homo sapiens", "taxon_id": 9606, "score": 0.99}]}]
            }
        }
        
        meti_dir = tmp_path / "meti_data"
        meti_dir.mkdir()
        with open(meti_dir / "PXD222222_aggregated_results.json", 'w') as f:
            json.dump(ra_data, f)

        agent = IntegrationAgent(str(meti_dir))
        
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        
        results = {"test/PXD222222_test.txt": sample_llm_extraction}
        agent.enrich_batch(results, agent_name="BiologicalAgent", output_dir=str(output_dir))
        
        # No log file since no disagreements
        log_path = output_dir / "ra_disagreements.json"
        assert not log_path.exists()


# ============================================================================
# PRIDE_TOOL_MAP Tests
# ============================================================================

class TestPRIDEToolMap:
    """Tests for PRIDE_TOOL_MAP configuration."""
    
    def test_all_mapped_fields_have_getters(self):
        """All fields in PRIDE_TOOL_MAP should have valid getter methods."""
        agent = IntegrationAgent("/tmp")  # Path doesn't matter for this test
        
        for field, (pride_getter, tool_getter, tool_name) in agent.PRIDE_TOOL_MAP.items():
            # Check PRIDE getter exists
            if pride_getter:
                assert hasattr(agent, pride_getter), f"Missing PRIDE getter: {pride_getter}"
            
            # Check tool getter exists (if specified)
            if tool_getter:
                assert hasattr(agent, tool_getter), f"Missing tool getter: {tool_getter}"
                assert tool_name is not None, f"Tool name missing for {field}"
    
    def test_species_and_organism_share_getters(self):
        """species and organism should use the same PRIDE getter."""
        agent = IntegrationAgent("/tmp")
        
        species_pride, _, _ = agent.PRIDE_TOOL_MAP["species"]
        organism_pride, _, _ = agent.PRIDE_TOOL_MAP["organism"]
        
        assert species_pride == organism_pride == "_get_pride_organisms"


# ============================================================================
# Edge Cases
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""
    
    def test_missing_meti_file(self, tmp_path, sample_llm_extraction):
        """Should handle missing METI file gracefully."""
        meti_dir = tmp_path / "empty_meti"
        meti_dir.mkdir()

        agent = IntegrationAgent(str(meti_dir))
        
        # Enrich with non-existent file - should fallback to LLM only
        result = agent.enrich("PXD999999", sample_llm_extraction, agent_type="BiologicalAgent")
        
        # Should still return valid result with LLM values
        assert "species" in result
        assert result["species"]["status"] == "LLM_ONLY"
    
    def test_empty_pride_metadata(self, tmp_path, sample_llm_extraction):
        """Should handle empty PRIDE metadata gracefully."""
        ra_data = {
            "pxd_id": "PXD333333",
            "pride_metadata": {},  # Empty
            "organism_identification": {"results": []}
        }
        
        meti_dir = tmp_path / "meti_data"
        meti_dir.mkdir()
        with open(meti_dir / "PXD333333_aggregated_results.json", 'w') as f:
            json.dump(ra_data, f)

        agent = IntegrationAgent(str(meti_dir))
        result = agent.enrich("PXD333333", sample_llm_extraction, agent_type="BiologicalAgent")
        
        # Should fallback to LLM values
        assert result["species"]["resolved"] == "Homo sapiens"
        assert result["species"]["status"] == "LLM_ONLY"


# ============================================================================
# Per-RAW HAMLET Contract Tests
# ============================================================================

class TestPerRawRunAssessorEvidence:
    """Tests direct per-file RunAssessor export for HAMLET SDRF rendering."""

    def test_technical_output_preserves_distinct_per_raw_values(self, tmp_path):
        meti_data = {
            "pxd_id": "PXD777777",
            "pride_metadata": {
                "files": [
                    {"fileName": "control.raw"},
                    {"fileName": "treated.raw"},
                ]
            },
            "runAssessor": {
                "files": {
                    "PXD777777/control.mzML": {
                        "instrument_model": {"name": "Orbitrap Exploris 480", "accession": "MS:1003029"},
                        "spectra_stats": {
                            "acquisition_type": "DDA",
                            "fragmentation_tag": "HR HCD",
                            "ms2_analyzer": "Orbitrap",
                        },
                        "summary": {
                            "labeling": {"call": "label-free"},
                            "combined summary": {
                                "recommended precursor tolerance (ppm)": 8,
                                "fragmentation tolerance": {
                                    "recommended fragment tolerance": 20,
                                    "recommended fragment tolerance units": "ppm",
                                },
                            },
                        },
                    },
                    "PXD777777/treated.mzML": {
                        "instrument_model": {"name": "LTQ Orbitrap Velos", "accession": "MS:1001742"},
                        "spectra_stats": {
                            "acquisition_type": "DIA",
                            "fragmentation_tag": "LR IT CID",
                        },
                        "summary": {
                            "labeling": {"call": "TMT10plex"},
                            "combined summary": {
                                "recommended precursor tolerance (ppm)": 12,
                                "fragmentation tolerance": {
                                    "recommended fragment tolerance": 0.6,
                                    "recommended fragment tolerance units": "m/z",
                                },
                            },
                        },
                    },
                }
            },
        }
        meti_dir = tmp_path / "meti"
        meti_dir.mkdir()
        with open(meti_dir / "PXD777777_aggregated_results.json", "w") as handle:
            json.dump(meti_data, handle)

        result = IntegrationAgent(str(meti_dir)).enrich(
            "PXD777777",
            {
                "instrument": ["unknown", ""],
                "precursor tolerance": ["10 ppm", "The precursor tolerance was set to 10 ppm."],
                "fragment tolerance": ["0.7 Da", "The fragment tolerance was set to 0.7 Da."],
            },
            agent_type="TechnicalAgent",
        )

        per_raw = result["per_raw_file"]
        assert set(per_raw) == {"control", "treated"}
        assert per_raw["control"]["instrument"]["resolved"] == "Orbitrap Exploris 480"
        assert per_raw["treated"]["instrument"]["resolved"] == "LTQ Orbitrap Velos"
        assert per_raw["control"]["acquisition"]["resolved"] == "DDA"
        assert per_raw["treated"]["acquisition"]["resolved"] == "DIA"
        assert per_raw["control"]["dissociation"]["resolved"] == "HR HCD"
        assert per_raw["treated"]["dissociation"]["resolved"] == "LR IT CID"
        assert result["precursor_tolerance"]["resolved"] == "10 ppm"
        assert result["fragment_tolerance"]["resolved"] == "0.7 Da"
        precursor_diagnostic = per_raw["control"]["runassessor_diagnostics"]["precursor_tolerance_recommendation"]
        assert precursor_diagnostic["status"] == "DIAGNOSTIC_ONLY"
        assert precursor_diagnostic["candidates"][0]["source_value"] == 8
        assert not precursor_diagnostic["candidates"][0]["valid"]
        assert per_raw["treated"]["ms2_analyzer"]["resolved"] is None
        assert per_raw["treated"]["instrument"]["candidates"][0]["source_path"].endswith(
            "PXD777777/treated.mzML.instrument_model.name"
        )

    def test_invalid_per_raw_tolerance_is_not_replaced(self, tmp_path):
        meti_data = {
            "pxd_id": "PXD888888",
            "pride_metadata": {"files": [{"fileName": "invalid.raw"}]},
            "runAssessor": {
                "files": {
                    "PXD888888/invalid.mzML": {
                        "spectra_stats": {},
                        "summary": {
                            "combined summary": {
                                "recommended precursor tolerance (ppm)": -1,
                                "fragmentation tolerance": {
                                    "recommended fragment tolerance": "N/A",
                                    "recommended fragment tolerance units": "ppm",
                                },
                            },
                        },
                    },
                },
            },
        }
        meti_dir = tmp_path / "meti"
        meti_dir.mkdir()
        with open(meti_dir / "PXD888888_aggregated_results.json", "w") as handle:
            json.dump(meti_data, handle)

        result = IntegrationAgent(str(meti_dir)).enrich(
            "PXD888888",
            {},
            agent_type="TechnicalAgent",
        )

        per_raw = result["per_raw_file"]["invalid"]
        precursor_diagnostic = per_raw["runassessor_diagnostics"]["precursor_tolerance_recommendation"]
        fragment_diagnostic = per_raw["runassessor_diagnostics"]["fragment_tolerance_recommendation"]
        assert precursor_diagnostic["candidates"][0]["source_value"] == -1
        assert not precursor_diagnostic["candidates"][0]["valid"]
        assert fragment_diagnostic["candidates"][0]["source_value"] == "N/A"

    def test_legacy_string_fragment_tolerance_is_ignored(self, tmp_path):
        meti_data = {
            "pxd_id": "PXD888889",
            "pride_metadata": {"files": [{"fileName": "legacy.raw"}]},
            "runAssessor": {
                "files": {
                    "PXD888889/legacy.mzML": {
                        "spectra_stats": {},
                        "summary": {
                            "combined summary": {
                                "fragmentation tolerance": "unavailable",
                            },
                        },
                    },
                },
            },
        }
        meti_dir = tmp_path / "meti"
        meti_dir.mkdir()
        with open(meti_dir / "PXD888889_aggregated_results.json", "w") as handle:
            json.dump(meti_data, handle)

        result = IntegrationAgent(str(meti_dir)).enrich(
            "PXD888889",
            {},
            agent_type="TechnicalAgent",
        )

        diagnostic = result["per_raw_file"]["legacy"]["runassessor_diagnostics"][
            "fragment_tolerance_recommendation"
        ]
        assert diagnostic["status"] == "DIAGNOSTIC_ONLY"
        assert diagnostic["candidates"] == []


class TestProjectLevelPridePtmIntegration:
    """Tests current PRIDE project nesting for author-supplied PTM declarations."""

    def test_reads_identified_ptms_from_project_metadata(self, tmp_path):
        meti_data = {
            "pxd_id": "PXD999998",
            "pride_metadata": {
                "project": {
                    "identifiedPTMStrings": [
                        {"name": "Carbamidomethyl", "accession": "UNIMOD:4"},
                        {"name": "Oxidation", "accession": "UNIMOD:35"},
                    ],
                },
            },
        }
        meti_dir = tmp_path / "meti"
        meti_dir.mkdir()
        with open(meti_dir / "PXD999998_aggregated_results.json", "w") as handle:
            json.dump(meti_data, handle)

        result = IntegrationAgent(str(meti_dir)).enrich(
            "PXD999998",
            {},
            agent_type="TechnicalAgent",
        )

        assert result["_meti_data"]["ptms"]["values"] == [
            "Carbamidomethyl", "Oxidation",
        ]
        assert result["ptm"]["sources"]["pride"]["value"] == "Carbamidomethyl"
        assert result["_meti_data"]["ptms"]["records"] == [
            {
                "name": "Carbamidomethyl",
                "accession": "UNIMOD:4",
                "target": None,
                "modification_type": None,
                "source": "pride",
                "scope": "study",
                "source_path": "pride_metadata.project.identifiedPTMStrings[0]",
                "source_value": "Carbamidomethyl",
            },
            {
                "name": "Oxidation",
                "accession": "UNIMOD:35",
                "target": None,
                "modification_type": None,
                "source": "pride",
                "scope": "study",
                "source_path": "pride_metadata.project.identifiedPTMStrings[1]",
                "source_value": "Oxidation",
            },
        ]
