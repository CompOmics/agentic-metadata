"""
Evidence Grounding Checker
==========================
Flags fields whose evidence text (after stripping an "inferred: " prefix, if
present) has no real grounding in the source manuscript — i.e. the "supporting"
text was not actually said anywhere in the manuscript, exact or close enough
to call it a paraphrase.

This is deliberately kept separate from the "inferred: " convention rather than
folded into it. "inferred: <quote>" means the model reasoned from a real,
quoted sentence to reach a synthesized value (e.g. "treated vs control" from
"mice were treated ... compared to controls") — that quote should genuinely
appear in the text, paraphrased or not. Evidence with no grounding at all is
closer to fabrication than legitimate inference, and conflating the two would
hide real hallucinations behind a label that's supposed to mean "trustworthy
but not verbatim".

Output flag type: "ungrounded_evidence"
"""

from __future__ import annotations

import re
import logging
from difflib import SequenceMatcher
from typing import Any, Optional

logger = logging.getLogger(__name__)

_INFERRED_PREFIX = "inferred: "

# Below this similarity, the closest manuscript sentence isn't close enough to
# call the evidence grounded. Matches evidenceMatch.ts's FUZZY_THRESHOLD so the
# pipeline and the review UI agree on what counts as "found in the text".
_FUZZY_THRESHOLD = 0.65


def _is_inferred(evidence: str) -> bool:
    return isinstance(evidence, str) and evidence.lower().startswith(_INFERRED_PREFIX)


def _extract_val_evidence(value: Any):
    """Return (value_str, evidence_str) from list or dict format."""
    if isinstance(value, list) and len(value) == 2:
        return value[0], value[1]
    if isinstance(value, dict):
        v = value.get("value") or value.get("resolved", "")
        e = value.get("evidence", "")
        return v, e
    return None, None


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def _split_sentences(text: str) -> list[str]:
    """Naive sentence splitter, mirroring the one in evidenceMatch.ts."""
    return [s for s in re.findall(r"[^.!?]+(?:[.!?]+(?:\s+|$)|$)", text) if s.strip()]


def _whitespace_tolerant_pattern(s: str) -> str:
    """Escape regex metacharacters, then loosen whitespace runs to `\\s+`."""
    escaped = re.sub(r"[.*+?^${}()|\[\]\\]", lambda m: "\\" + m.group(0), s)
    return re.sub(r"\s+", r"\\s+", escaped)


def _is_grounded(quote: str, manuscript_text: str) -> bool:
    """
    True if `quote` is found verbatim (whitespace-tolerant) in the manuscript,
    or is close enough to the manuscript's most similar sentence.
    """
    quote = quote.strip()
    if not quote:
        return False

    pattern = _whitespace_tolerant_pattern(quote)
    if re.search(pattern, manuscript_text, re.IGNORECASE):
        return True

    normalized_quote = _normalize(quote)
    best_score = 0.0
    for sentence in _split_sentences(manuscript_text):
        score = SequenceMatcher(None, normalized_quote, _normalize(sentence)).ratio()
        if score > best_score:
            best_score = score
    return best_score >= _FUZZY_THRESHOLD


class EvidenceGroundingChecker:
    """
    Flag fields whose evidence has no real grounding in the source manuscript.

    Usage::

        checker = EvidenceGroundingChecker()
        flags = checker.check(record, manuscript_text)

    Each flag::

        {
            "type":     "ungrounded_evidence",
            "field":    "technology_type",
            "value":    "shotgun proteomics",
            "evidence": "The study describes a phosphoproteomics approach ..."
        }
    """

    def check(self, record: dict, manuscript_text: Optional[str]) -> list[dict]:
        if not manuscript_text:
            return []

        flags: list[dict] = []
        for field_name, field_value in record.items():
            if field_name.startswith("_"):
                continue

            val, evidence = _extract_val_evidence(field_value)
            if not val or not evidence:
                continue
            if not isinstance(val, str) or not isinstance(evidence, str):
                continue
            if val.strip().lower() in ("unknown", ""):
                continue

            quote = evidence[len(_INFERRED_PREFIX):] if _is_inferred(evidence) else evidence
            if not _is_grounded(quote, manuscript_text):
                flags.append({
                    "type":     "ungrounded_evidence",
                    "field":    field_name,
                    "value":    val,
                    "evidence": evidence,
                })

        return flags
