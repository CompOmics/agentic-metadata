#!/usr/bin/env python3
"""
DocETL Biological Agent Runner
==============================
Thin wrapper that runs the DocETL BiologicalAgent pipeline on a directory of
manuscript `.txt` files and writes outputs in exactly the same JSON format as
the existing ``BiologicalAgent`` — compatible with the normalization pipeline,
benchmark evaluator, and integration agent downstream.

Usage
-----
::

    python docetl/run_docetl.py \\
        --input  docs/ \\
        --output framework_output/docetl/ \\
        --config config.yaml

    # Or test on a single file:
    python docetl/run_docetl.py \\
        --input  docs/PXD001234.txt \\
        --output framework_output/docetl/

Environment
-----------
Reads ``LLM_API_KEY`` (or the key configured in ``config.yaml``) from the
environment and passes it to DocETL via ``OPENAI_API_KEY`` (litellm uses this
for OpenAI-compatible endpoints).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

import yaml

# ── Resolve project root for imports ──────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

PIPELINE_YAML = Path(__file__).parent / "pipeline_biological.yaml"
AGENT_NAME = "BiologicalAgent"


def _load_config(config_path: str | None) -> dict:
    """Load the project config.yaml (or return empty dict if not found)."""
    if config_path:
        path = Path(config_path)
    else:
        path = PROJECT_ROOT / "config.yaml"

    if not path.exists():
        return {}

    with open(path) as f:
        return yaml.safe_load(f) or {}


def _build_environment(cfg: dict) -> dict:
    """Return env vars needed by litellm / DocETL."""
    env = dict(os.environ)

    llm_cfg = cfg.get("llm", {})

    # API key: from config env_var reference or direct value
    api_key_env = llm_cfg.get("api_key_env_var", "LLM_API_KEY")
    api_key = llm_cfg.get("api_key") or os.getenv(api_key_env, "")

    # DocETL/litellm reads OPENAI_API_KEY for openai-compat endpoints
    env["OPENAI_API_KEY"] = api_key

    # Custom base URL for the Jetstream / local endpoint
    base_url = llm_cfg.get("base_url", "")
    if base_url:
        env["OPENAI_BASE_URL"] = base_url

    return env


def _collect_manuscripts(input_path: Path) -> list[Path]:
    """Return list of manuscript .txt files from a file or directory."""
    if input_path.is_file():
        return [input_path]
    return sorted(input_path.glob("*.txt"))


def _build_docetl_dataset(manuscripts: list[Path]) -> list[dict]:
    """Convert manuscript files to DocETL input records."""
    records = []
    for path in manuscripts:
        text = path.read_text(encoding="utf-8", errors="replace")
        records.append({
            "id": path.stem,        # PXD id / filename stem used as record key
            "text": text,
        })
    return records


def _run_pipeline(records: list[dict], cfg: dict, output_dir: Path) -> list[dict]:
    """Run the DocETL pipeline and return the result records."""
    from docetl.runner import DSLRunner

    llm_cfg = cfg.get("llm", {})
    model_name = llm_cfg.get("model", "llama-4-scout")
    # DocETL model strings follow litellm convention: "openai/<model>"
    docetl_model = f"openai/{model_name}"

    # Write a temporary input JSONL that DocETL expects
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, dir=output_dir
    ) as tmp_in:
        json.dump(records, tmp_in, indent=2)
        tmp_in_path = tmp_in.name

    tmp_out_path = str(output_dir / "_docetl_raw_output.json")

    # Build the pipeline config with resolved paths & model
    with open(PIPELINE_YAML) as f:
        raw_yaml = f.read()

    pipeline_cfg = yaml.safe_load(raw_yaml)
    pipeline_cfg["default_model"] = docetl_model
    pipeline_cfg["datasets"]["manuscripts"]["path"] = tmp_in_path
    pipeline_cfg["pipeline"]["output"]["path"] = tmp_out_path

    # Persist resolved config to a temp file for the runner
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, dir=output_dir
    ) as tmp_cfg:
        yaml.dump(pipeline_cfg, tmp_cfg)
        tmp_cfg_path = tmp_cfg.name

    # Set env (API key, base URL)
    env = _build_environment(cfg)
    os.environ.update(env)

    print(f"  Running DocETL pipeline  ({len(records)} manuscripts)…")
    runner = DSLRunner.from_yaml(tmp_cfg_path)
    runner.load_run_save()

    # Read raw output
    with open(tmp_out_path) as f:
        results = json.load(f)

    # Cleanup temp files
    for p in (tmp_in_path, tmp_cfg_path, tmp_out_path):
        try:
            os.unlink(p)
        except OSError:
            pass

    return results


def _write_agent_outputs(results: list[dict], output_dir: Path) -> None:
    """
    Write one JSON per PXD in the same format as existing BiologicalAgent.

    Existing format::

        {
          "species":      ["Homo sapiens", "Human plasma samples..."],
          "tissue":       ["liver", "..."],
          ...
        }

    DocETL adds the original input keys alongside the extracted fields, so we
    strip `id` and `text` before writing.
    """
    agent_dir = output_dir / AGENT_NAME
    agent_dir.mkdir(parents=True, exist_ok=True)

    SKIP_KEYS = {"id", "text"}

    for record in results:
        pxd_id = record.get("id", "unknown")
        payload = {k: v for k, v in record.items() if k not in SKIP_KEYS}

        out_file = agent_dir / f"{pxd_id}_biological.json"
        with open(out_file, "w") as f:
            json.dump(payload, f, indent=2)

        print(f"  Written: {out_file.name}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run DocETL BiologicalAgent pipeline on manuscript text files"
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="Path to a .txt manuscript file or directory of .txt files",
    )
    parser.add_argument(
        "--output", "-o",
        default="framework_output/docetl",
        help="Output directory (default: framework_output/docetl/)",
    )
    parser.add_argument(
        "--config", "-c",
        default=None,
        help="Path to project config.yaml (default: auto-detect in project root)",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    cfg = _load_config(args.config)

    manuscripts = _collect_manuscripts(input_path)
    if not manuscripts:
        print(f"No .txt files found at: {input_path}", file=sys.stderr)
        sys.exit(1)

    print(f"\nDocETL BiologicalAgent")
    print(f"  Input : {input_path}  ({len(manuscripts)} files)")
    print(f"  Output: {output_dir}")
    print(f"  Model : {cfg.get('llm', {}).get('model', 'llama-4-scout')}")

    records = _build_docetl_dataset(manuscripts)
    results = _run_pipeline(records, cfg, output_dir)
    _write_agent_outputs(results, output_dir)

    print(f"\nDone. {len(results)} document(s) processed.")


if __name__ == "__main__":
    main()
