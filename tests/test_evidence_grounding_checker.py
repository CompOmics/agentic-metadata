"""
Unit tests for validation.evidence_grounding_checker.EvidenceGroundingChecker.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from validation.evidence_grounding_checker import EvidenceGroundingChecker, _is_grounded

MANUSCRIPT = (
    "We analysed the Plasmodium falciparum schizont phosphoproteome using for the first "
    "time, a data-dependent neutral loss-triggered-ETD (DDNL) strategy and a conventional "
    "decision-tree method. Proteins were digested with trypsin and the resulting peptides "
    "were analyzed using a Q Exactive HF mass spectrometer."
)


class TestIsGrounded:
    def test_exact_verbatim_quote_is_grounded(self):
        assert _is_grounded(
            "Proteins were digested with trypsin and the resulting peptides were analyzed using a Q Exactive HF mass spectrometer.",
            MANUSCRIPT,
        )

    def test_whitespace_tolerant(self):
        assert _is_grounded(
            "Proteins   were digested\nwith trypsin and the resulting peptides were analyzed using a Q Exactive HF mass spectrometer.",
            MANUSCRIPT,
        )

    def test_close_paraphrase_of_a_real_sentence_is_grounded(self):
        # Real example: experimental_design's evidence paraphrases a real sentence.
        assert _is_grounded(
            "Analyses were performed using a data-dependent neutral loss-triggered ETD (DDNL) strategy and a conventional decision-tree method.",
            MANUSCRIPT,
        )

    def test_fully_synthesized_explanation_is_not_grounded(self):
        # Real example: technology_type's evidence never appears in the manuscript at all.
        assert not _is_grounded(
            "The study describes a phosphoproteomics approach using bottom-up digestion and LC-MS/MS analysis, commonly referred to as shotgun proteomics.",
            MANUSCRIPT,
        )

    def test_empty_quote_is_not_grounded(self):
        assert not _is_grounded("", MANUSCRIPT)
        assert not _is_grounded("   ", MANUSCRIPT)


class TestEvidenceGroundingChecker:
    def test_no_manuscript_text_skips_check_entirely(self):
        checker = EvidenceGroundingChecker()
        record = {"technology_type": ["shotgun proteomics", "made up evidence"]}
        assert checker.check(record, None) == []
        assert checker.check(record, "") == []

    def test_flags_ungrounded_evidence(self):
        checker = EvidenceGroundingChecker()
        record = {
            "technology_type": [
                "shotgun proteomics",
                "The study describes a phosphoproteomics approach using bottom-up digestion and LC-MS/MS analysis, commonly referred to as shotgun proteomics.",
            ],
        }
        flags = checker.check(record, MANUSCRIPT)
        assert len(flags) == 1
        assert flags[0]["type"] == "ungrounded_evidence"
        assert flags[0]["field"] == "technology_type"

    def test_does_not_flag_a_grounded_verbatim_quote(self):
        checker = EvidenceGroundingChecker()
        record = {
            "cleavage_agent": [
                "trypsin",
                "Proteins were digested with trypsin and the resulting peptides were analyzed using a Q Exactive HF mass spectrometer.",
            ],
        }
        assert checker.check(record, MANUSCRIPT) == []

    def test_does_not_flag_a_legitimately_inferred_field(self):
        checker = EvidenceGroundingChecker()
        record = {
            "experimental_design": [
                "treated vs control",
                "inferred: Analyses were performed using a data-dependent neutral loss-triggered ETD (DDNL) strategy and a conventional decision-tree method.",
            ],
        }
        assert checker.check(record, MANUSCRIPT) == []

    def test_flags_a_fabricated_inferred_prefix_too(self):
        # "inferred: " isn't a free pass — the quote after the prefix must still ground.
        checker = EvidenceGroundingChecker()
        record = {
            "technology_type": [
                "shotgun proteomics",
                "inferred: this technique is universally known as shotgun proteomics in the field.",
            ],
        }
        flags = checker.check(record, MANUSCRIPT)
        assert len(flags) == 1
        assert flags[0]["type"] == "ungrounded_evidence"

    def test_skips_unknown_values_and_dict_shape(self):
        checker = EvidenceGroundingChecker()
        record = {
            "species": {"value": "unknown", "evidence": ""},
            "instrument": {"value": "Q Exactive HF", "evidence": "analyzed using a Q Exactive HF mass spectrometer"},
        }
        assert checker.check(record, MANUSCRIPT) == []
