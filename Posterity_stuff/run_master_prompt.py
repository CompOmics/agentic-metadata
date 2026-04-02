"""
Posterity run: BRAT-style annotation using master_prompt via DocETL.

Picks manuscripts from dataset_mapping.json (test + new_test splits),
runs the master_prompt pipeline (pipeline_master_prompt.yaml), and saves:
  - Raw JSON output:  Posterity_stuff/outputs/raw_json/master_prompt_output.json
  - BRAT .ann files:  Posterity_stuff/outputs/ann_files/<pxd_id>.ann

Usage:
    /path/to/venv/bin/python Posterity_stuff/run_master_prompt.py [--limit N] [--force]
"""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Paths (relative to extraction_framework root)
# ---------------------------------------------------------------------------
SCRIPT_DIR   = Path(__file__).parent
FRAMEWORK    = SCRIPT_DIR.parent
VENV_PY      = FRAMEWORK / "venv" / "bin" / "python"
DATASET_MAP  = FRAMEWORK / "benchmark_data" / "dataset_mapping.json"
PIPELINE_YAML = SCRIPT_DIR / "pipeline_master_prompt.yaml"
CONFIG_YAML  = FRAMEWORK / "config.yaml"
OUTPUT_DIR   = SCRIPT_DIR / "outputs"
RAW_JSON_DIR = OUTPUT_DIR / "raw_json"
ANN_DIR      = OUTPUT_DIR / "ann_files"

# Provider → litellm prefix mapping (same as run_docetl.py)
_PROVIDER_PREFIX = {"anthropic": "anthropic", "gemini": "gemini", "openai": "openai"}
_PROVIDER_KEY_ENV = {"anthropic": "ANTHROPIC_API_KEY", "gemini": "GEMINI_API_KEY", "openai": "OPENAI_API_KEY"}


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def load_config() -> dict:
    if CONFIG_YAML.exists():
        with open(CONFIG_YAML) as f:
            return yaml.safe_load(f) or {}
    return {}


def apply_env(cfg: dict) -> str:
    """Set env vars for the LLM provider. Returns litellm model string."""
    llm = cfg.get("llm", {})
    api_key = llm.get("api_key") or os.getenv(llm.get("api_key_env_var", "LLM_API_KEY"), "")
    model = llm.get("model", "llama-4-scout")

    if llm.get("provider"):
        provider = llm["provider"]
    elif model.startswith("claude"):
        provider = "anthropic"
    elif model.startswith("gemini"):
        provider = "gemini"
    else:
        provider = "openai"

    key_env = _PROVIDER_KEY_ENV.get(provider, "OPENAI_API_KEY")
    os.environ[key_env] = api_key or os.getenv(key_env, "")

    if provider == "openai":
        if not os.environ[key_env]:
            os.environ[key_env] = "dummy-key"
        base_url = llm.get("base_url", "")
        if base_url:
            os.environ["OPENAI_BASE_URL"] = base_url

    prefix = _PROVIDER_PREFIX.get(provider, "openai")
    return f"{prefix}/{model}"


# ---------------------------------------------------------------------------
# Manuscript loading
# ---------------------------------------------------------------------------

def load_manuscripts(limit: int) -> list[tuple[str, Path]]:
    """Return (pxd_id, manuscript_path) from test + new_test splits."""
    with open(DATASET_MAP) as f:
        dm = json.load(f)

    entries = []
    for split in ("test", "new_test"):
        for pxd, paths in dm.get(split, {}).items():
            if len(paths) >= 2 and paths[1]:
                ms = Path(paths[1])
                if ms.exists():
                    entries.append((pxd, ms))
            if len(entries) >= limit:
                break
        if len(entries) >= limit:
            break
    return entries[:limit]


# ---------------------------------------------------------------------------
# DocETL runner (mirrors _run_pipeline in run_docetl.py)
# ---------------------------------------------------------------------------

def run_pipeline(records: list[dict], litellm_model: str, tmp_dir: Path) -> list[dict]:
    """Execute the master_prompt DocETL pipeline via DSLRunner."""
    from docetl.runner import DSLRunner

    in_path  = tmp_dir / "input.json"
    out_path = tmp_dir / "output.json"
    cfg_path = tmp_dir / "pipeline.yaml"

    in_path.write_text(json.dumps(records, indent=2))

    with open(PIPELINE_YAML) as f:
        pipeline_cfg = yaml.safe_load(f)

    # Inject paths and model (same pattern as run_docetl._run_pipeline)
    pipeline_cfg["default_model"] = litellm_model
    pipeline_cfg["datasets"]["manuscripts"]["path"] = str(in_path)
    pipeline_cfg["pipeline"]["output"]["path"] = str(out_path)
    # Always bypass cache so failed/empty previous runs don't persist
    for op in pipeline_cfg.get("operations", []):
        op["bypass_cache"] = True

    with open(cfg_path, "w") as f:
        yaml.dump(pipeline_cfg, f)

    runner = DSLRunner.from_yaml(str(cfg_path))
    runner.load_run_save()

    with open(out_path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def write_outputs(results: list[dict], raw_json_path: Path, ann_dir: Path) -> int:
    """Save raw JSON and extract .ann files. Returns count of .ann files written."""
    raw_json_path.write_text(json.dumps(results, indent=2))
    print(f"[INFO] Raw JSON saved to {raw_json_path}")

    written = 0
    for rec in results:
        doc_id = rec.get("id", rec.get("filename", f"doc_{written}"))
        if doc_id.endswith(".txt"):
            doc_id = doc_id[:-4]

        ann_content = rec.get("ann_output", "").strip()
        # Convert ||| placeholder back to real tab characters (LLM avoids raw tabs in JSON)
        ann_content = ann_content.replace("|||", "\t")
        ann_path = ann_dir / f"{doc_id}.ann"
        ann_path.write_text(ann_content + "\n" if ann_content else "")
        n_lines = len(ann_content.splitlines()) if ann_content else 0
        print(f"  {doc_id}.ann  ({n_lines} annotations)")
        written += 1

    return written


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Posterity run: master_prompt BRAT annotation via DocETL")
    parser.add_argument("--limit", type=int, default=5,
                        help="Number of manuscripts to process (default: 5)")
    parser.add_argument("--force", action="store_true",
                        help="Clear previous outputs before running")
    parser.add_argument("--config", type=str, default=None,
                        help="Path to LLM config YAML (default: extraction_framework/config.yaml)")
    parser.add_argument("--output-suffix", type=str, default="",
                        help="Suffix appended to output dirs, e.g. '_gpt'")
    args = parser.parse_args()

    # Resolve output dirs (allow suffix for multi-model runs)
    suffix = args.output_suffix
    raw_json_dir = OUTPUT_DIR / f"raw_json{suffix}"
    ann_dir      = OUTPUT_DIR / f"ann_files{suffix}"

    if args.force:
        import shutil
        for d in (raw_json_dir, ann_dir):
            if d.exists():
                shutil.rmtree(d)
                print(f"[INFO] Cleared {d}")

    raw_json_dir.mkdir(parents=True, exist_ok=True)
    ann_dir.mkdir(parents=True, exist_ok=True)

    # 1. Config
    global CONFIG_YAML
    if args.config:
        CONFIG_YAML = Path(args.config)
    cfg = load_config()
    litellm_model = apply_env(cfg)
    print(f"[INFO] Model: {litellm_model}")

    # 2. Manuscripts
    entries = load_manuscripts(args.limit)
    if not entries:
        print("[ERROR] No manuscripts found in test/new_test splits.", file=sys.stderr)
        sys.exit(1)
    print(f"[INFO] Processing {len(entries)} manuscripts: {[e[0] for e in entries]}")

    # 3. Build records
    records = []
    for pxd, ms_path in entries:
        text = ms_path.read_text(encoding="utf-8", errors="replace")
        records.append({"id": pxd, "text": text})

    # 4. Run DocETL
    with tempfile.TemporaryDirectory(prefix="posterity_") as tmp:
        tmp_dir = Path(tmp)
        print(f"[INFO] Running DocETL pipeline...")
        results = run_pipeline(records, litellm_model, tmp_dir)

    # 5. Write outputs
    raw_json_path = raw_json_dir / "master_prompt_output.json"
    n = write_outputs(results, raw_json_path, ann_dir)
    print(f"\n[DONE] {n} .ann files written to {ann_dir}/")


if __name__ == "__main__":
    main()
