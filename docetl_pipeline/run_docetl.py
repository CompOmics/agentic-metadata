#!/usr/bin/env python3
"""
DocETL Pipeline Runner — All Agents
=====================================
Runs DocETL extraction pipelines for all three agents (BiologicalAgent,
TechnicalAgent, ExperimentalDesignAgent) and optionally computes
ValidationAgent confidence scores — producing output in the same JSON
format as the existing ``BaseExtractor`` pipeline.

Post-processing steps (run after extraction):
- NormalizationAgent: maps extracted terms to ontology IDs
- IntegrationAgent: enriches with PRIDE/METI data from final_files

Usage
-----
::

    # All agents on a directory of manuscripts
    python docetl_pipeline/run_docetl.py \\
        --input  docs/ \\
        --output framework_output/docetl/ \\
        --config config.yaml

    # Full pipeline including normalization + integration
    python docetl_pipeline/run_docetl.py \\
        --input  docs/ \\
        --output framework_output/docetl/ \\
        --meti-dir benchmark_data/Technical_pipeline_outputs_train_test/final_files/

    # Single agent, single file, extraction only
    python docetl_pipeline/run_docetl.py \\
        --input  docs/PXD001234.txt \\
        --output framework_output/docetl/ \\
        --agents biological \\
        --no-confidence \\
        --no-normalize \\
        --no-integrate

Environment
-----------
Set the API key for the configured provider before running:

  - OpenAI/compat (default) : ``OPENAI_API_KEY``
  - Anthropic (Claude)      : ``ANTHROPIC_API_KEY``
  - Gemini                  : ``GEMINI_API_KEY``

The key can also be placed in the ``llm.api_key_env_var`` field of the config.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

import yaml

# Suppress LiteLLM's noisy stdout feedback/info messages
import litellm
litellm.suppress_debug_info = True
litellm.verbose = False
import logging
logging.getLogger("LiteLLM").setLevel(logging.ERROR)
logging.getLogger("LiteLLM Router").setLevel(logging.ERROR)
logging.getLogger("LiteLLM Proxy").setLevel(logging.ERROR)

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


# Map provider → litellm env var name
_PROVIDER_KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini":    "GEMINI_API_KEY",
    "openai":    "OPENAI_API_KEY",
}
# litellm model prefix per provider
_PROVIDER_PREFIX = {
    "anthropic": "anthropic",
    "gemini":    "gemini",
    "openai":    "openai",
}


def _apply_env(cfg: dict) -> None:
    """Export the correct API key env var(s) for the configured provider.

    DocETL delegates to litellm, which reads provider-specific env vars:
      - OpenAI/compat  → OPENAI_API_KEY  (+ optionally OPENAI_BASE_URL)
      - Anthropic      → ANTHROPIC_API_KEY
      - Gemini         → GEMINI_API_KEY
    """
    llm = cfg.get("llm", {})

    # Resolve API key from config or env var
    api_key = llm.get("api_key") or os.getenv(
        llm.get("api_key_env_var", "LLM_API_KEY"), ""
    )

    # Auto-detect provider (same logic as core/llm.py)
    model = llm.get("model", "")
    if llm.get("provider"):
        provider = llm["provider"]
    elif model.startswith("claude"):
        provider = "anthropic"
    elif model.startswith("gemini"):
        provider = "gemini"
    else:
        provider = "openai"

    # Set the provider-specific key
    key_env = _PROVIDER_KEY_ENV.get(provider, "OPENAI_API_KEY")
    os.environ[key_env] = api_key or os.getenv(key_env, "")

    if provider == "openai":
        # litellm rejects empty string for OpenAI-compat endpoints
        if not os.environ["OPENAI_API_KEY"]:
            os.environ["OPENAI_API_KEY"] = "dummy-key"
        base_url = llm.get("base_url", "")
        if base_url:
            os.environ.setdefault("OPENAI_BASE_URL", base_url)

    # Store resolved provider for use in _run_pipeline
    cfg.setdefault("_resolved", {})["provider"] = provider



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

    provider = cfg.get("_resolved", {}).get("provider", "openai")
    litellm_prefix = _PROVIDER_PREFIX.get(provider, "openai")
    model = litellm_prefix + "/" + cfg.get("llm", {}).get("model", "llama-4-scout")

    in_path  = tmp_dir / "input.json"
    out_path = tmp_dir / "output.json"
    cfg_path = tmp_dir / "pipeline.yaml"

    in_path.write_text(json.dumps(records, indent=2))

    with open(yaml_file) as f:
        pipeline_cfg = yaml.safe_load(f)

    pipeline_cfg["default_model"] = model
    pipeline_cfg["datasets"]["manuscripts"]["path"] = str(in_path)
    pipeline_cfg["pipeline"]["output"]["path"] = str(out_path)

    # Read timeout from config (concurrency.request_timeout), fall back to 120s.
    # Always override the YAML value so config.yaml is the single source of truth.
    timeout_secs = cfg.get("concurrency", {}).get("request_timeout", 120)

    for op in pipeline_cfg.get("operations", []):
        if bypass_cache:
            op["bypass_cache"] = True
        # Always override timeout — docetl defaults to 120s which is too short for
        # large local models. No retries on timeout: a slow model won't get faster
        # on retry; the timeout itself signals something is wrong.
        op["timeout"] = timeout_secs
        op["max_retries_per_timeout"] = 0

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
    model_tag: str = "",
) -> None:
    agent_dir = output_dir / agent_dir_name
    agent_dir.mkdir(parents=True, exist_ok=True)

    tag = f"_{model_tag}" if model_tag else ""

    for record in results:
        pxd_id = record.get("id", "unknown")
        payload = {k: v for k, v in record.items() if k not in SKIP_KEYS}

        if use_confidence and pxd_id in text_lookup:
            _add_confidence(payload, text_lookup[pxd_id])

        _add_hallucination_flags(payload)

        out_file = agent_dir / f"{pxd_id}{suffix}{tag}.json"
        with open(out_file, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"  Written: {out_file.relative_to(output_dir)}")


# ─────────────────────────────────────────────────────────────────────────────
# Post-processing: Normalization + Integration
# ─────────────────────────────────────────────────────────────────────────────

def _load_agent_outputs(agent_dir: Path) -> dict[str, dict]:
    """Load all per-doc JSON files from an agent output directory."""
    results = {}
    for json_file in sorted(agent_dir.glob("*.json")):
        with open(json_file) as f:
            results[json_file.name] = json.load(f)
    return results


def _run_normalization(
    output_dir: Path,
    agents_run: list[tuple[str, str, str]],  # (yaml_name, agent_dir_name, suffix)
) -> dict[str, dict[str, dict]]:
    """
    Run NormalizationAgent over all per-doc extraction outputs.

    Returns:
        {agent_dir_name: {filename: normalized_data}}
    """
    from agents.normalization_agent import NormalizationAgent

    norm_agent = NormalizationAgent()
    all_normalized: dict[str, dict[str, dict]] = {}

    for _, agent_dir_name, suffix in agents_run:
        agent_dir = output_dir / agent_dir_name
        if not agent_dir.exists():
            print(f"  [Normalization] Skipping {agent_dir_name} — dir not found")
            continue

        raw = _load_agent_outputs(agent_dir)
        if not raw:
            continue

        print(f"  Normalizing {len(raw)} docs for {agent_dir_name}...")
        normalized = norm_agent.normalize_batch(raw)

        # Write normalized outputs (with hallucination flags)
        norm_dir = output_dir / "NormalizedAgent" / agent_dir_name
        norm_dir.mkdir(parents=True, exist_ok=True)
        for fname, data in normalized.items():
            _add_hallucination_flags(data)
            out = norm_dir / fname
            with open(out, "w") as f:
                json.dump(data, f, indent=2)
        print(f"  Written: NormalizedAgent/{agent_dir_name}/ ({len(normalized)} docs)")

        all_normalized[agent_dir_name] = normalized

    return all_normalized


def _run_integration(
    output_dir: Path,
    agents_run: list[tuple[str, str, str]],
    meti_dir: Path,
    normalized: dict[str, dict[str, dict]],
) -> None:
    """
    Run IntegrationAgent over normalized (or raw) extraction outputs.

    Uses normalized outputs when available; falls back to raw extraction.
    """
    from agents.integration_agent import IntegrationAgent

    int_agent = IntegrationAgent(str(meti_dir))

    for _, agent_dir_name, suffix in agents_run:
        # Prefer normalized, fall back to raw extraction
        if agent_dir_name in normalized:
            file_results = normalized[agent_dir_name]
            src_label = "normalized"
        else:
            agent_dir = output_dir / agent_dir_name
            if not agent_dir.exists():
                print(f"  [Integration] Skipping {agent_dir_name} — dir not found")
                continue
            file_results = _load_agent_outputs(agent_dir)
            src_label = "raw extraction"

        if not file_results:
            continue

        print(f"  Integrating {len(file_results)} docs for {agent_dir_name} (from {src_label})...")

        int_dir = output_dir / "IntegratedAgent" / agent_dir_name
        int_dir.mkdir(parents=True, exist_ok=True)

        enriched = int_agent.enrich_batch(
            file_results,
            agent_name=agent_dir_name,
            output_dir=str(int_dir),
        )

        for fname, data in enriched.items():
            _add_hallucination_flags(data)
            out = int_dir / fname
            with open(out, "w") as f:
                json.dump(data, f, indent=2)
        print(f"  Written: IntegratedAgent/{agent_dir_name}/ ({len(enriched)} docs)")


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
    parser.add_argument("--meti-dir", default=None,
                        help="Directory containing final_files aggregated_results JSONs "
                             "(default: auto-detect benchmark_data/Technical_pipeline_outputs_train_test/final_files/)")
    parser.add_argument("--no-normalize", action="store_true",
                        help="Skip NormalizationAgent post-processing")
    parser.add_argument("--no-integrate", action="store_true",
                        help="Skip IntegrationAgent post-processing")
    parser.add_argument("--model-tag", default="",
                        help="String appended to every output filename, e.g. 'llama' → PXD000312_manuscript_biological_llama.json")
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
    do_normalize = not args.no_normalize
    do_integrate = not args.no_integrate
    model_name   = cfg.get("llm", {}).get("model", "llama-4-scout")

    # Resolve METI dir
    meti_dir: Optional[Path] = None
    if do_integrate:
        if args.meti_dir:
            meti_dir = Path(args.meti_dir)
        else:
            default_ra = PROJECT_ROOT / "benchmark_data" / "Technical_pipeline_outputs_train_test" / "final_files"
            if default_ra.exists():
                meti_dir = default_ra
        if not meti_dir or not meti_dir.exists():
            print("  [Integration] WARNING: METI dir not found - skipping integration.")
            do_integrate = False

    print(f"\nDocETL Extraction Runner")
    print(f"  Input        : {input_path}  ({len(manuscripts)} files)")
    print(f"  Output       : {output_dir}")
    print(f"  Model        : {model_name}")
    print(f"  Agents       : {', '.join(args.agents)}")
    print(f"  Confidence   : {'yes' if use_conf else 'no'}")
    print(f"  Normalize    : {'yes' if do_normalize else 'no'}")
    print(f"  Integrate    : {'yes' if do_integrate else 'no'}")
    if do_integrate:
        print(f"  METI dir     : {meti_dir}")
    print(f"  Bypass cache : {'yes' if bypass_cache else 'no'}\n")

    agents_run = []
    with tempfile.TemporaryDirectory(prefix="docetl_") as tmp:
        tmp_dir = Path(tmp)

        for agent_key in args.agents:
            yaml_name, agent_dir_name, suffix = AGENTS[agent_key]
            yaml_file = PIPELINE_DIR / yaml_name

            print(f"─── [{agent_dir_name}] ──────────────────────────────────")
            max_retries = 5
            for attempt in range(1, max_retries + 1):
                try:
                    results = _run_pipeline(records, yaml_file, cfg, tmp_dir,
                                            bypass_cache=bypass_cache)
                    break
                except Exception as e:
                    if attempt < max_retries and ("InternalServerError" in type(e).__name__
                                                   or "Connection" in str(e)):
                        wait = 30 * attempt
                        print(f"  [retry {attempt}/{max_retries}] server error, "
                              f"waiting {wait}s: {e}")
                        time.sleep(wait)
                    else:
                        raise
            _write_outputs(
                results, text_lookup, output_dir,
                agent_dir_name, suffix, use_conf,
                model_tag=args.model_tag,
            )
            agents_run.append((yaml_name, agent_dir_name, suffix))
            print(f"─── [{agent_dir_name}] done ({len(results)} docs)\n")

    # ── Post-processing ────────────────────────────────────────────────────
    normalized: dict[str, dict[str, dict]] = {}

    if do_normalize and agents_run:
        print("─── [NormalizationAgent] ──────────────────────────────────")
        try:
            normalized = _run_normalization(output_dir, agents_run)
        except Exception as exc:
            print(f"  WARNING: Normalization failed — {exc}")
            import traceback; traceback.print_exc()
        print("─── [NormalizationAgent] done\n")

    if do_integrate and agents_run:
        print("─── [IntegrationAgent] ──────────────────────────────────")
        try:
            _run_integration(output_dir, agents_run, meti_dir, normalized)
        except Exception as exc:
            print(f"  WARNING: Integration failed — {exc}")
            import traceback; traceback.print_exc()
        print("─── [IntegrationAgent] done\n")

    print(f"All done. Output: {output_dir}")


if __name__ == "__main__":
    main()
