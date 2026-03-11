#!/usr/bin/env python3
"""
DocETL Pipeline Runner — All Agents
=====================================
Runs DocETL extraction pipelines for all three agents (BiologicalAgent,
TechnicalAgent, ExperimentalDesignAgent) and optionally computes
ValidationAgent confidence scores — producing output in the same JSON
format as the existing ``BaseExtractor`` pipeline.

Usage
-----
::

    # All agents on a directory of manuscripts
    python docetl_pipeline/run_docetl.py \\
        --input  docs/ \\
        --output framework_output/docetl/ \\
        --config config.yaml

    # Single agent, single file
    python docetl_pipeline/run_docetl.py \\
        --input  docs/PXD001234.txt \\
        --output framework_output/docetl/ \\
        --agents biological \\
        --no-confidence

Environment
-----------
``LLM_API_KEY`` (or the key/env-var in ``config.yaml``) must be set.
DocETL reads it via ``OPENAI_API_KEY`` (litellm convention).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Optional

import yaml

# ── Project root on path for internal imports ─────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Module-level singleton for the cross-field checker (lazy init)
_cross_field_checker = None
# Module-level singleton for the negation detector (lazy init)
_negation_detector = None
# Module-level singleton for the numeric mismatch detector (lazy init)
_numeric_mismatch_detector = None

PIPELINE_DIR = Path(__file__).parent

# Agent configuration: name → (yaml filename, output subdir key)
AGENTS = {
    "biological": (
        "pipeline_biological.yaml",
        "BiologicalAgent",
        "_biological",          # output filename suffix
    ),
    "technical": (
        "pipeline_technical.yaml",
        "TechnicalAgent",
        "_technical",
    ),
    "experimental": (
        "pipeline_experimental.yaml",
        "ExperimentalDesignAgent",
        "_experimental",
    ),
}

SKIP_KEYS = {"id", "text"}   # DocETL passes these through; strip before writing


# ─────────────────────────────────────────────────────────────────────────────
# Config helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_config(config_path: Optional[str]) -> dict:
    path = Path(config_path) if config_path else PROJECT_ROOT / "config.yaml"
    if path.exists():
        with open(path) as f:
            return yaml.safe_load(f) or {}
    return {}


def _apply_env(cfg: dict) -> None:
    """Set OPENAI_API_KEY / OPENAI_BASE_URL from project config."""
    llm = cfg.get("llm", {})
    api_key = llm.get("api_key") or os.getenv(
        llm.get("api_key_env_var", "LLM_API_KEY"), ""
    )
    # litellm rejects an empty string — use a placeholder for endpoints
    # (e.g. Jetstream) that don't require a real OpenAI key.
    os.environ["OPENAI_API_KEY"] = api_key or os.getenv("OPENAI_API_KEY", "dummy-key")
    base_url = llm.get("base_url", "")
    if base_url:
        os.environ["OPENAI_BASE_URL"] = base_url



# ─────────────────────────────────────────────────────────────────────────────
# Manuscript loading
# ─────────────────────────────────────────────────────────────────────────────

def _collect_manuscripts(input_path: Path) -> list[Path]:
    if input_path.is_file():
        return [input_path]
    return sorted(input_path.glob("*.txt"))


def _build_records(manuscripts: list[Path]) -> list[dict]:
    records = []
    for path in manuscripts:
        text = path.read_text(encoding="utf-8", errors="replace")
        records.append({"id": path.stem, "text": text})
    return records


# ─────────────────────────────────────────────────────────────────────────────
# DocETL runner
# ─────────────────────────────────────────────────────────────────────────────

def _run_pipeline(
    records: list[dict],
    yaml_file: Path,
    cfg: dict,
    tmp_dir: Path,
    bypass_cache: bool = False,
) -> list[dict]:
    """Load + execute one DocETL pipeline; return result records."""
    from docetl.runner import DSLRunner

    model = "openai/" + cfg.get("llm", {}).get("model", "llama-4-scout")

    in_path  = tmp_dir / "input.json"
    out_path = tmp_dir / "output.json"
    cfg_path = tmp_dir / "pipeline.yaml"

    in_path.write_text(json.dumps(records, indent=2))

    with open(yaml_file) as f:
        pipeline_cfg = yaml.safe_load(f)

    pipeline_cfg["default_model"] = model
    pipeline_cfg["datasets"]["manuscripts"]["path"] = str(in_path)
    pipeline_cfg["pipeline"]["output"]["path"] = str(out_path)

    if bypass_cache:
        for op in pipeline_cfg.get("operations", []):
            op["bypass_cache"] = True

    with open(cfg_path, "w") as f:
        yaml.dump(pipeline_cfg, f)

    runner = DSLRunner.from_yaml(str(cfg_path))
    runner.load_run_save()

    with open(out_path) as f:
        results = json.load(f)

    # Cleanup temp artefacts
    for p in (in_path, out_path, cfg_path):
        try:
            p.unlink()
        except OSError:
            pass

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Confidence estimation
# ─────────────────────────────────────────────────────────────────────────────

def _add_hallucination_flags(record: dict) -> dict:
    """
    Append ``_hallucination_flags`` to *record* in-place.

    Combines results from three complementary checks:
    - Cross-field ontology consistency (CLO / DOID / CL / UBERON)
    - Negation detection via NegEx (negspacy)
    - Numeric exact-match check (e.g. 50 mM extracted vs 5 mM in evidence)
    """
    global _cross_field_checker, _negation_detector, _numeric_mismatch_detector
    flags: list[dict] = []

    # ── Cross-field ontology consistency ─────────────────────────────────
    try:
        if _cross_field_checker is None:
            from validation.cross_field_checker import CrossFieldConsistencyChecker
            _cross_field_checker = CrossFieldConsistencyChecker()
        flags.extend(_cross_field_checker.check(record))
    except Exception as exc:
        import logging
        logging.getLogger(__name__).debug("Cross-field check error: %s", exc)

    # ── Negation detection (negspacy / NegEx) ─────────────────────────────
    try:
        if _negation_detector is None:
            from validation.negation_detector import NegationDetector
            _negation_detector = NegationDetector()
        flags.extend(_negation_detector.check(record))
    except Exception as exc:
        import logging
        logging.getLogger(__name__).debug("Negation check error: %s", exc)

    # ── Numeric mismatch (exact-only for concentrations/energies) ────────────
    try:
        if _numeric_mismatch_detector is None:
            from validation.numeric_mismatch_detector import NumericMismatchDetector
            _numeric_mismatch_detector = NumericMismatchDetector()
        flags.extend(_numeric_mismatch_detector.check(record))
    except Exception as exc:
        import logging
        logging.getLogger(__name__).debug("Numeric mismatch check error: %s", exc)

    if flags:
        record["_hallucination_flags"] = flags
    return record


def _add_confidence(
    record: dict,
    text: str,
) -> dict:
    """Attach ValidationAgent confidence metrics to a record in-place."""
    try:
        from validation.validator import ValidationAgent, ValidationMode
        validator = ValidationAgent(mode=ValidationMode.SCHEMA_ONLY)
        # strip input pass-through keys before scoring
        scoreable = {k: v for k, v in record.items() if k not in SKIP_KEYS}
        scored = validator._add_confidence(scoreable, text)
        record["_confidence"] = scored["_confidence"]
    except Exception as exc:
        # Non-fatal — confidence is optional
        record["_confidence"] = {"error": str(exc)}
    return record


# ─────────────────────────────────────────────────────────────────────────────
# Output writing
# ─────────────────────────────────────────────────────────────────────────────

def _write_outputs(
    results: list[dict],
    text_lookup: dict[str, str],
    output_dir: Path,
    agent_dir_name: str,
    suffix: str,
    use_confidence: bool,
) -> None:
    agent_dir = output_dir / agent_dir_name
    agent_dir.mkdir(parents=True, exist_ok=True)

    for record in results:
        pxd_id = record.get("id", "unknown")
        payload = {k: v for k, v in record.items() if k not in SKIP_KEYS}

        if use_confidence and pxd_id in text_lookup:
            _add_confidence(payload, text_lookup[pxd_id])

        _add_hallucination_flags(payload)

        out_file = agent_dir / f"{pxd_id}{suffix}.json"
        with open(out_file, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"  Written: {out_file.relative_to(output_dir)}")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run DocETL extraction pipelines for all three agents"
    )
    parser.add_argument("--input", "-i", required=True,
                        help=".txt file or directory of .txt manuscript files")
    parser.add_argument("--output", "-o", default="framework_output/docetl",
                        help="Output directory (default: framework_output/docetl/)")
    parser.add_argument("--config", "-c", default=None,
                        help="Path to config.yaml (default: auto-detect in project root)")
    parser.add_argument(
        "--agents", nargs="+",
        choices=list(AGENTS.keys()),
        default=list(AGENTS.keys()),
        help="Which agents to run (default: all three)",
    )
    parser.add_argument("--no-confidence", action="store_true",
                        help="Skip ValidationAgent confidence scoring")
    parser.add_argument("--bypass-cache", action="store_true",
                        help="Force fresh LLM calls, ignoring DocETL's disk cache")
    args = parser.parse_args()

    input_path  = Path(args.input)
    output_dir  = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    cfg = _load_config(args.config)
    _apply_env(cfg)

    manuscripts = _collect_manuscripts(input_path)
    if not manuscripts:
        print(f"No .txt files found at: {input_path}", file=sys.stderr)
        sys.exit(1)

    records      = _build_records(manuscripts)
    text_lookup  = {r["id"]: r["text"] for r in records}
    use_conf     = not args.no_confidence
    bypass_cache = args.bypass_cache
    model_name  = cfg.get("llm", {}).get("model", "llama-4-scout")

    print(f"\nDocETL Extraction Runner")
    print(f"  Input   : {input_path}  ({len(manuscripts)} files)")
    print(f"  Output  : {output_dir}")
    print(f"  Model   : {model_name}")
    print(f"  Agents  : {', '.join(args.agents)}")
    print(f"  Confidence: {'yes' if use_conf else 'no'}")
    print(f"  Bypass cache: {'yes' if bypass_cache else 'no'}\n")

    with tempfile.TemporaryDirectory(prefix="docetl_") as tmp:
        tmp_dir = Path(tmp)

        for agent_key in args.agents:
            yaml_name, agent_dir_name, suffix = AGENTS[agent_key]
            yaml_file = PIPELINE_DIR / yaml_name

            print(f"─── [{agent_dir_name}] ──────────────────────────────────")
            results = _run_pipeline(records, yaml_file, cfg, tmp_dir,
                                    bypass_cache=bypass_cache)
            _write_outputs(
                results, text_lookup, output_dir,
                agent_dir_name, suffix, use_conf,
            )
            print(f"─── [{agent_dir_name}] done ({len(results)} docs)\n")

    print(f"All done. Output: {output_dir}")


if __name__ == "__main__":
    main()
