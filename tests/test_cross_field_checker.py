"""
Unit tests for validation.cross_field_checker.CrossFieldConsistencyChecker.

All tests run fully offline — no ontology files are accessed.
OBO parsing and CLO map loading are mocked to inject controlled data.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock
from typing import Dict, List, Optional

import pytest

# Ensure project root is on the path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from validation.cross_field_checker import CrossFieldConsistencyChecker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _checker_with_mocks(
    clo_map:         Optional[Dict] = None,
    bto_uberon_map:  Optional[Dict] = None,
    doid_tissue_map: Optional[Dict] = None,
    cl_tissue_map:   Optional[Dict] = None,
) -> CrossFieldConsistencyChecker:
    """Return a checker whose lazy caches are pre-populated with test data."""
    c = CrossFieldConsistencyChecker()
    c._clo_map         = clo_map         or {}
    c._clo_label_idx   = {
        entry["label"].lower(): cid
        for cid, entry in (clo_map or {}).items()
        if entry.get("label")
    }
    c._bto_uberon_map  = bto_uberon_map  or {}
    c._doid_tissue_map = doid_tissue_map or {}
    c._cl_tissue_map   = cl_tissue_map   or {}
    return c


# ---------------------------------------------------------------------------
# _get_field
# ---------------------------------------------------------------------------

class TestGetField:
    def test_list_format(self):
        c = _checker_with_mocks()
        v, oid = c._get_field({"species": ["Homo sapiens", "evidence"]}, "species")
        assert v   == "Homo sapiens"
        assert oid is None

    def test_dict_value_format(self):
        c = _checker_with_mocks()
        v, oid = c._get_field(
            {"cell_type": {"value": "hepatocyte", "ontology_id": "CL:0000182"}},
            "cell_type",
        )
        assert v   == "hepatocyte"
        assert oid == "CL:0000182"

    def test_dict_resolved_format(self):
        c = _checker_with_mocks()
        v, oid = c._get_field(
            {"instrument": {"resolved": "Q Exactive", "ontology_id": "MS:1002634"}},
            "instrument",
        )
        assert v   == "Q Exactive"
        assert oid == "MS:1002634"

    def test_plain_string_format(self):
        c = _checker_with_mocks()
        v, oid = c._get_field({"tissue": "liver"}, "tissue")
        assert v   == "liver"
        assert oid is None

    def test_missing_field_returns_none_tuple(self):
        c = _checker_with_mocks()
        v, oid = c._get_field({}, "disease")
        assert v   is None
        assert oid is None

    def test_fallback_field_names(self):
        """Second field_name used when first is absent."""
        c = _checker_with_mocks()
        v, _ = c._get_field({"organism": ["Mus musculus", "ev"]}, "species", "organism")
        assert v == "Mus musculus"

    def test_empty_list_value_returns_none(self):
        c = _checker_with_mocks()
        v, _ = c._get_field({"species": ["", ""]}, "species")
        assert v is None


# ---------------------------------------------------------------------------
# _species_matches
# ---------------------------------------------------------------------------

class TestSpeciesMatches:
    @pytest.mark.parametrize("val", ["Homo sapiens", "human", "h. sapiens"])
    def test_human_aliases_match(self, val):
        assert CrossFieldConsistencyChecker._species_matches(val, "NCBITaxon_9606")

    @pytest.mark.parametrize("val", ["Mus musculus", "mouse", "m. musculus"])
    def test_mouse_aliases_match(self, val):
        assert CrossFieldConsistencyChecker._species_matches(val, "NCBITaxon_10090")

    def test_mismatch_returns_false(self):
        assert not CrossFieldConsistencyChecker._species_matches("Mus musculus", "NCBITaxon_9606")

    def test_fuzzy_match_close_name(self):
        # Slight typo should still fuzzy-match (ratio >= 0.85)
        assert CrossFieldConsistencyChecker._species_matches("Homo sapien", "NCBITaxon_9606")

    def test_completely_wrong_species(self):
        assert not CrossFieldConsistencyChecker._species_matches("yeast", "NCBITaxon_9606")


# ---------------------------------------------------------------------------
# Check 1: cell_line → species  (CLO derives_from)
# ---------------------------------------------------------------------------

class TestCloSpeciesCheck:
    """CLO entry says NCBITaxon_9606 (human); test correct and mismatched records."""

    _CLO_MAP = {
        "CLO:0000148": {
            "label":         "HeLa",
            "species_ncbi":  "NCBITaxon_9606",
            "tissue_bto":    None,
            "tissue_uberon": None,
        }
    }

    def _c(self):
        return _checker_with_mocks(clo_map=self._CLO_MAP)

    def test_no_flag_when_species_correct(self):
        record = {
            "cell_line": {"value": "HeLa", "ontology_id": "CLO:0000148"},
            "species":   ["Homo sapiens", "evidence"],
        }
        flags = self._c().check(record)
        assert flags == []

    def test_flag_when_species_wrong(self):
        record = {
            "cell_line": {"value": "HeLa", "ontology_id": "CLO:0000148"},
            "species":   ["Mus musculus", "evidence"],
        }
        flags = self._c().check(record)
        assert len(flags) == 1
        f = flags[0]
        assert f["type"] == "cell_line_species_mismatch"
        assert f["value_a"] == "HeLa"
        assert f["value_b"] == "Mus musculus"
        assert f["expected_b"] == "Homo sapiens"
        assert f["source"] == "CLO derives_from"

    def test_no_flag_when_species_unknown(self):
        record = {
            "cell_line": {"value": "HeLa", "ontology_id": "CLO:0000148"},
            "species":   ["unknown", ""],
        }
        flags = self._c().check(record)
        assert flags == []

    def test_lookup_by_label_when_no_id(self):
        """cell_line given as plain list (no ontology_id); look up by label."""
        record = {
            "cell_line": ["HeLa", "HeLa cells were used"],
            "species":   ["Mus musculus", "evidence"],
        }
        flags = self._c().check(record)
        assert any(f["type"] == "cell_line_species_mismatch" for f in flags)

    def test_no_flag_when_clo_entry_absent(self):
        """CLO map doesn't contain the cell line → skip check silently."""
        record = {
            "cell_line": {"value": "SomeUnknownLine", "ontology_id": "CLO:9999999"},
            "species":   ["Mus musculus", "evidence"],
        }
        flags = self._c().check(record)
        assert flags == []

    def test_no_flag_when_clo_has_no_species(self):
        clo_map = {
            "CLO:0000999": {"label": "CellX", "species_ncbi": None,
                            "tissue_bto": None, "tissue_uberon": None}
        }
        c = _checker_with_mocks(clo_map=clo_map)
        record = {
            "cell_line": {"value": "CellX", "ontology_id": "CLO:0000999"},
            "species":   ["Mus musculus", "evidence"],
        }
        assert c.check(record) == []


# ---------------------------------------------------------------------------
# Check 2: cell_line → tissue  (CLO derives_from)
# ---------------------------------------------------------------------------

class TestCloTissueCheck:
    _CLO_MAP_UBERON = {
        "CLO:0000148": {
            "label":         "HeLa",
            "species_ncbi":  "NCBITaxon_9606",
            "tissue_bto":    None,
            "tissue_uberon": "UBERON:0000310",  # breast
        }
    }
    _CLO_MAP_BTO = {
        "CLO:0000001": {
            "label":         "Hs766T",
            "species_ncbi":  "NCBITaxon_9606",
            "tissue_bto":    "BTO:0001234",
            "tissue_uberon": None,
        }
    }

    def test_no_flag_when_uberon_matches(self):
        c = _checker_with_mocks(clo_map=self._CLO_MAP_UBERON)
        record = {
            "cell_line": {"value": "HeLa", "ontology_id": "CLO:0000148"},
            "tissue":    {"value": "breast", "ontology_id": "UBERON:0000310"},
        }
        assert c.check(record) == []

    def test_flag_when_uberon_mismatches(self):
        c = _checker_with_mocks(clo_map=self._CLO_MAP_UBERON)
        record = {
            "cell_line": {"value": "HeLa", "ontology_id": "CLO:0000148"},
            "tissue":    {"value": "liver", "ontology_id": "UBERON:0002107"},
        }
        flags = [f for f in c.check(record) if f["type"] == "cell_line_tissue_mismatch"]
        assert len(flags) == 1
        assert flags[0]["expected_b"] == "UBERON:0000310"

    def test_no_flag_when_tissue_has_no_id(self):
        """Cannot compare without an ontology ID — skip silently."""
        c = _checker_with_mocks(clo_map=self._CLO_MAP_UBERON)
        record = {
            "cell_line": {"value": "HeLa", "ontology_id": "CLO:0000148"},
            "tissue":    ["breast", "evidence"],   # no ontology_id
        }
        assert c.check(record) == []

    def test_bto_to_uberon_mapping_used(self):
        bto_uberon = {"BTO:1234": ["UBERON:0002107"]}   # liver
        c = _checker_with_mocks(
            clo_map=self._CLO_MAP_BTO,
            bto_uberon_map=bto_uberon,
        )
        # tissue matches the BTO→UBERON resolved ID
        record = {
            "cell_line": {"value": "Hs766T", "ontology_id": "CLO:0000001"},
            "tissue":    {"value": "liver",  "ontology_id": "UBERON:0002107"},
        }
        assert c.check(record) == []

    def test_bto_mismatch_raises_flag(self):
        # BTO:0001234 is the key in the CLO map above; map it to liver (UBERON:0002107)
        bto_uberon = {"BTO:0001234": ["UBERON:0002107"]}
        c = _checker_with_mocks(
            clo_map=self._CLO_MAP_BTO,
            bto_uberon_map=bto_uberon,
        )
        record = {
            "cell_line": {"value": "Hs766T", "ontology_id": "CLO:0000001"},
            "tissue":    {"value": "brain",  "ontology_id": "UBERON:0000955"},
        }
        flags = [f for f in c.check(record) if f["type"] == "cell_line_tissue_mismatch"]
        assert len(flags) == 1


# ---------------------------------------------------------------------------
# Check 3: disease → tissue  (DOID located_in)
# ---------------------------------------------------------------------------

class TestDoidTissueCheck:
    _DOID_MAP = {
        "DOID:1793": ["UBERON:0001264"],   # pancreatic cancer → pancreas
    }

    def _c(self):
        return _checker_with_mocks(doid_tissue_map=self._DOID_MAP)

    def test_no_flag_when_tissue_correct(self):
        record = {
            "disease": {"value": "pancreatic cancer", "ontology_id": "DOID:1793"},
            "tissue":  {"value": "pancreas",          "ontology_id": "UBERON:0001264"},
        }
        assert self._c().check(record) == []

    def test_flag_when_tissue_wrong(self):
        record = {
            "disease": {"value": "pancreatic cancer", "ontology_id": "DOID:1793"},
            "tissue":  {"value": "liver",             "ontology_id": "UBERON:0002107"},
        }
        flags = [f for f in self._c().check(record) if f["type"] == "disease_tissue_mismatch"]
        assert len(flags) == 1
        f = flags[0]
        assert "UBERON:0001264" in f["expected_b"]
        assert f["source"] == "DOID located_in"

    def test_no_flag_when_doid_not_in_map(self):
        record = {
            "disease": {"value": "unknown disease", "ontology_id": "DOID:9999"},
            "tissue":  {"value": "liver",           "ontology_id": "UBERON:0002107"},
        }
        assert self._c().check(record) == []

    def test_no_flag_when_tissue_has_no_id(self):
        record = {
            "disease": {"value": "pancreatic cancer", "ontology_id": "DOID:1793"},
            "tissue":  ["pancreas", "evidence"],
        }
        assert self._c().check(record) == []

    def test_id_normalisation_colon_underscore(self):
        """DOID:1793 and DOID_1793 should resolve to the same key."""
        c = _checker_with_mocks(
            doid_tissue_map={"DOID:1793": ["UBERON:0001264"]}
        )
        record = {
            "disease": {"value": "pancreatic cancer", "ontology_id": "DOID_1793"},
            "tissue":  {"value": "pancreas",          "ontology_id": "UBERON_0001264"},
        }
        assert c.check(record) == []


# ---------------------------------------------------------------------------
# Check 4: cell_type → tissue  (CL part_of)
# ---------------------------------------------------------------------------

class TestClTissueCheck:
    _CL_MAP = {
        "CL:0000182": ["UBERON:0002107"],   # hepatocyte → liver
    }

    def _c(self):
        return _checker_with_mocks(cl_tissue_map=self._CL_MAP)

    def test_no_flag_when_tissue_correct(self):
        record = {
            "cell_type": {"value": "hepatocyte", "ontology_id": "CL:0000182"},
            "tissue":    {"value": "liver",      "ontology_id": "UBERON:0002107"},
        }
        assert self._c().check(record) == []

    def test_flag_when_tissue_wrong(self):
        record = {
            "cell_type": {"value": "hepatocyte", "ontology_id": "CL:0000182"},
            "tissue":    {"value": "brain",      "ontology_id": "UBERON:0000955"},
        }
        flags = [f for f in self._c().check(record) if f["type"] == "cell_type_tissue_mismatch"]
        assert len(flags) == 1
        f = flags[0]
        assert "UBERON:0002107" in f["expected_b"]
        assert f["source"] == "CL part_of"

    def test_no_flag_when_cl_not_in_map(self):
        record = {
            "cell_type": {"value": "neuron", "ontology_id": "CL:0000540"},
            "tissue":    {"value": "liver",  "ontology_id": "UBERON:0002107"},
        }
        assert self._c().check(record) == []

    def test_no_flag_when_tissue_has_no_id(self):
        record = {
            "cell_type": {"value": "hepatocyte", "ontology_id": "CL:0000182"},
            "tissue":    ["liver", "evidence"],
        }
        assert self._c().check(record) == []

    def test_no_flag_when_cell_type_has_no_id(self):
        record = {
            "cell_type": ["hepatocyte", "evidence"],   # no ontology_id
            "tissue":    {"value": "brain", "ontology_id": "UBERON:0000955"},
        }
        assert self._c().check(record) == []


# ---------------------------------------------------------------------------
# Integration: check() on combined records
# ---------------------------------------------------------------------------

class TestCheckIntegration:
    # HeLa: human, no tissue constraint in this fixture so tissue checks don't fire
    _CLO_MAP = {
        "CLO:0000148": {
            "label":         "HeLa",
            "species_ncbi":  "NCBITaxon_9606",
            "tissue_bto":    None,
            "tissue_uberon": None,
        }
    }
    _CL_MAP  = {"CL:0000182": ["UBERON:0002107"]}
    _DOID_MAP = {"DOID:1793": ["UBERON:0001264"]}

    def _c(self):
        return _checker_with_mocks(
            clo_map=self._CLO_MAP,
            cl_tissue_map=self._CL_MAP,
            doid_tissue_map=self._DOID_MAP,
        )

    def test_clean_record_produces_no_flags(self):
        record = {
            "cell_line": {"value": "HeLa",        "ontology_id": "CLO:0000148"},
            "species":   ["Homo sapiens",          "evidence"],
            "cell_type": {"value": "hepatocyte",   "ontology_id": "CL:0000182"},
            "tissue":    {"value": "liver",        "ontology_id": "UBERON:0002107"},
            "disease":   {"value": "liver cancer", "ontology_id": "DOID:3571"},
        }
        assert self._c().check(record) == []

    def test_multiple_flags_accumulated(self):
        """A record with two wrong fields should yield two flags.

        Use a CLO entry that has BOTH species and tissue constraints so that
        both checks fire when the record is incorrect.
        """
        clo_with_tissue = {
            "CLO:0000148": {
                "label":         "HeLa",
                "species_ncbi":  "NCBITaxon_9606",
                "tissue_bto":    None,
                "tissue_uberon": "UBERON:0000310",   # breast / uterine cervix
            }
        }
        c = _checker_with_mocks(
            clo_map=clo_with_tissue,
            cl_tissue_map=self._CL_MAP,
            doid_tissue_map=self._DOID_MAP,
        )
        record = {
            "cell_line": {"value": "HeLa",        "ontology_id": "CLO:0000148"},
            "species":   ["Mus musculus",          "evidence"],            # wrong species
            "tissue":    {"value": "liver",        "ontology_id": "UBERON:0002107"},  # wrong tissue
        }
        flags = c.check(record)
        types = {f["type"] for f in flags}
        assert "cell_line_species_mismatch" in types
        assert "cell_line_tissue_mismatch" in types

    def test_fully_empty_record_produces_no_flags(self):
        assert self._c().check({}) == []

    def test_record_with_only_unknown_values(self):
        record = {
            "cell_line": ["unknown", ""],
            "species":   ["unknown", ""],
            "tissue":    ["unknown", ""],
            "disease":   ["unknown", ""],
            "cell_type": ["unknown", ""],
        }
        assert self._c().check(record) == []

    def test_hela_mouse_synthetic_corruption(self):
        """Canonical corruption test: HeLa + Mus musculus should be flagged."""
        record = {
            "cell_line": {"value": "HeLa",        "ontology_id": "CLO:0000148"},
            "species":   {"value": "Mus musculus", "ontology_id": "NCBITaxon:10090"},
        }
        flags = self._c().check(record)
        assert any(f["type"] == "cell_line_species_mismatch" for f in flags)


# ---------------------------------------------------------------------------
# OBO parser unit tests (no file I/O — purely logic tests with tmp files)
# ---------------------------------------------------------------------------

class TestOboXrefParser:
    def test_parses_uberon_xrefs(self, tmp_path):
        obo = tmp_path / "test.obo"
        obo.write_text(
            "[Term]\n"
            "id: BTO:0000567\n"
            "name: liver\n"
            "xref: UBERON:0002107\n"
            "xref: MESH:D008099\n"
            "\n"
            "[Term]\n"
            "id: BTO:0000002\n"
            "name: blood\n"
            "xref: UBERON:0000178\n"
        )
        result = CrossFieldConsistencyChecker._parse_obo_xrefs(str(obo), "UBERON:")
        assert result == {
            "BTO:0000567": ["UBERON:0002107"],
            "BTO:0000002": ["UBERON:0000178"],
        }

    def test_ignores_non_term_sections(self, tmp_path):
        obo = tmp_path / "test.obo"
        obo.write_text(
            "[Typedef]\n"
            "id: RO:0001000\n"
            "xref: UBERON:9999999\n"
            "\n"
            "[Term]\n"
            "id: BTO:0000001\n"
            "xref: UBERON:0001234\n"
        )
        result = CrossFieldConsistencyChecker._parse_obo_xrefs(str(obo), "UBERON:")
        assert "RO:0001000" not in result
        assert result.get("BTO:0000001") == ["UBERON:0001234"]


class TestOboRelationshipParser:
    def test_parses_part_of_uberon(self, tmp_path):
        obo = tmp_path / "test.obo"
        obo.write_text(
            "[Term]\n"
            "id: CL:0000182\n"
            "name: hepatocyte\n"
            "relationship: part_of UBERON:0002107 ! liver\n"
            "\n"
            "[Term]\n"
            "id: CL:0000540\n"
            "name: neuron\n"
            "relationship: part_of UBERON:0000955 ! cerebral cortex\n"
        )
        result = CrossFieldConsistencyChecker._parse_obo_relationship(
            str(obo), "part_of", "UBERON:"
        )
        assert result["CL:0000182"] == ["UBERON:0002107"]
        assert result["CL:0000540"] == ["UBERON:0000955"]

    def test_parses_located_in_uberon(self, tmp_path):
        obo = tmp_path / "test.obo"
        obo.write_text(
            "[Term]\n"
            "id: DOID:1793\n"
            "name: pancreatic cancer\n"
            "relationship: located_in UBERON:0001264 ! pancreas\n"
        )
        result = CrossFieldConsistencyChecker._parse_obo_relationship(
            str(obo), "located_in", "UBERON:"
        )
        assert result["DOID:1793"] == ["UBERON:0001264"]

    def test_ignores_non_matching_relations(self, tmp_path):
        obo = tmp_path / "test.obo"
        obo.write_text(
            "[Term]\n"
            "id: CL:0000001\n"
            "relationship: develops_from CL:0000000\n"
            "relationship: part_of UBERON:0001234\n"
        )
        result = CrossFieldConsistencyChecker._parse_obo_relationship(
            str(obo), "part_of", "UBERON:"
        )
        assert "CL:0000001" in result
        assert result["CL:0000001"] == ["UBERON:0001234"]

    def test_ignores_non_uberon_targets(self, tmp_path):
        obo = tmp_path / "test.obo"
        obo.write_text(
            "[Term]\n"
            "id: CL:0000001\n"
            "relationship: part_of BTO:0000001\n"
        )
        result = CrossFieldConsistencyChecker._parse_obo_relationship(
            str(obo), "part_of", "UBERON:"
        )
        assert result == {}


# ---------------------------------------------------------------------------
# Graceful degradation when ontology files are absent
# ---------------------------------------------------------------------------

class TestGracefulDegradation:
    """Checker should return [] when ontology files cannot be found."""

    def test_no_clo_file_no_crash(self, tmp_path):
        c = CrossFieldConsistencyChecker(
            ontology_dir=str(tmp_path / "missing"),
            cache_dir=str(tmp_path / "cache"),
        )
        record = {
            "cell_line": ["HeLa", "evidence"],
            "species":   ["Mus musculus", "evidence"],
        }
        assert c.check(record) == []

    def test_no_doid_file_no_crash(self, tmp_path):
        c = CrossFieldConsistencyChecker(
            ontology_dir=str(tmp_path / "missing"),
            cache_dir=str(tmp_path / "cache"),
        )
        record = {
            "disease": {"value": "pancreatic cancer", "ontology_id": "DOID:1793"},
            "tissue":  {"value": "liver",             "ontology_id": "UBERON:0002107"},
        }
        assert c.check(record) == []

    def test_no_cl_file_no_crash(self, tmp_path):
        c = CrossFieldConsistencyChecker(
            ontology_dir=str(tmp_path / "missing"),
            cache_dir=str(tmp_path / "cache"),
        )
        record = {
            "cell_type": {"value": "hepatocyte", "ontology_id": "CL:0000182"},
            "tissue":    {"value": "brain",      "ontology_id": "UBERON:0000955"},
        }
        assert c.check(record) == []

    def test_clo_cache_loaded_if_present(self, tmp_path):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        clo_cache = {
            "CLO:0000148": {
                "label": "HeLa",
                "species_ncbi": "NCBITaxon_9606",
                "tissue_bto": None,
                "tissue_uberon": None,
            }
        }
        (cache_dir / "clo_derives_from.json").write_text(json.dumps(clo_cache))

        c = CrossFieldConsistencyChecker(
            ontology_dir=str(tmp_path / "missing"),
            cache_dir=str(cache_dir),
        )
        record = {
            "cell_line": {"value": "HeLa",        "ontology_id": "CLO:0000148"},
            "species":   ["Mus musculus", "evidence"],
        }
        flags = c.check(record)
        assert any(f["type"] == "cell_line_species_mismatch" for f in flags)


# ---------------------------------------------------------------------------
# run_docetl integration: _add_hallucination_flags
# ---------------------------------------------------------------------------

class TestRunDocetlIntegration:
    """Test that _add_hallucination_flags in run_docetl works end-to-end."""

    def test_flags_added_to_record(self):
        import docetl_pipeline.run_docetl as runner
        import importlib

        # Reset module-level checker so it re-initialises
        runner._cross_field_checker = None

        # Patch CrossFieldConsistencyChecker to return a synthetic flag
        fake_flag = {
            "type": "cell_line_species_mismatch",
            "field_a": "cell_line", "value_a": "HeLa", "ontology_id_a": "CLO:0000148",
            "field_b": "species",   "value_b": "Mus musculus", "ontology_id_b": None,
            "expected_b": "Homo sapiens",
            "source": "CLO derives_from",
        }
        mock_checker = MagicMock()
        mock_checker.check.return_value = [fake_flag]

        with patch(
            "validation.cross_field_checker.CrossFieldConsistencyChecker",
            return_value=mock_checker,
        ):
            runner._cross_field_checker = None
            record = {
                "cell_line": ["HeLa", "ev"],
                "species":   ["Mus musculus", "ev"],
            }
            runner._add_hallucination_flags(record)

        assert "_hallucination_flags" in record
        assert record["_hallucination_flags"][0]["type"] == "cell_line_species_mismatch"

    def test_no_flags_key_when_empty(self):
        import docetl_pipeline.run_docetl as runner

        runner._cross_field_checker = None

        mock_checker = MagicMock()
        mock_checker.check.return_value = []

        with patch(
            "validation.cross_field_checker.CrossFieldConsistencyChecker",
            return_value=mock_checker,
        ):
            runner._cross_field_checker = None
            record = {"species": ["Homo sapiens", "ev"]}
            runner._add_hallucination_flags(record)

        assert "_hallucination_flags" not in record

    def test_exception_does_not_propagate(self):
        import docetl_pipeline.run_docetl as runner

        runner._cross_field_checker = None

        mock_checker = MagicMock()
        mock_checker.check.side_effect = RuntimeError("boom")

        with patch(
            "validation.cross_field_checker.CrossFieldConsistencyChecker",
            return_value=mock_checker,
        ):
            runner._cross_field_checker = None
            record = {"species": ["Homo sapiens", "ev"]}
            # Should not raise
            runner._add_hallucination_flags(record)
