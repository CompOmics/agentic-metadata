"""
Run IntegrationAgent for the 23 test+new_test PXDs that have technical pipeline
outputs (METI data), across all model test folders.

Output: Final_results/test_new_test_meti_integrated/
  <model>/
    IntegratedAgent/
      BiologicalAgent/
      TechnicalAgent/
      ExperimentalDesignAgent/
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from agents.integration_agent import IntegrationAgent

# ── Config ────────────────────────────────────────────────────────────────────

FINAL_RESULTS = Path("benchmark_data/Final_results")
METI_DIR = Path("benchmark_data/Technical_pipeline_outputs_train_test/final_files")
OUTPUT_DIR = FINAL_RESULTS / "test_new_test_meti_integrated"

# test+new_test PXDs with technical pipeline output (non-null third path)
METI_PXDS = {
    # test split (11/12)
    "PXD002619", "PXD019394", "PXD041681", "PXD040176", "PXD022741",
    "PXD031991", "PXD036832", "PXD026287", "PXD018830", "PXD032098",
    "PXD029966",
    # new_test split (12/18)
    "PXD001856", "PXD006847", "PXD012439", "PXD013809", "PXD014762",
    "PXD015289", "PXD021383", "PXD028781", "PXD029997", "PXD036655",
    "PXD040722", "PXD043392",
}

MODEL_FOLDERS = {
    "llama":   FINAL_RESULTS / "test",
    "claude":  FINAL_RESULTS / "test_claude",
    "gpt":     FINAL_RESULTS / "test_gpt",
    "gemini":  FINAL_RESULTS / "test_gemini",
}

AGENT_DIRS = [
    ("BiologicalAgent",       "_biological"),
    ("TechnicalAgent",        "_technical"),
    ("ExperimentalDesignAgent", "_experimental"),
]


def load_filtered(agent_dir: Path, suffix: str) -> dict[str, dict]:
    """Load only METI-enabled PXDs from an agent output directory.

    Prefers NormalizedAgent sibling if available.
    """
    # Try NormalizedAgent first
    norm_dir = agent_dir.parent / "NormalizedAgent" / agent_dir.name
    src = norm_dir if norm_dir.exists() else agent_dir
    if not src.exists():
        return {}

    results = {}
    for json_file in sorted(src.glob(f"*{suffix}.json")):
        pxd = json_file.stem.split("_")[0]  # e.g. PXD002619
        if pxd in METI_PXDS:
            with open(json_file) as f:
                results[json_file.name] = json.load(f)
    return results


def _add_hallucination_flags(data: dict) -> None:
    """Stub — flags already embedded by integration agent."""
    pass


def run_model(model_name: str, model_dir: Path, int_agent: IntegrationAgent) -> None:
    print(f"\n{'='*60}")
    print(f"  Model: {model_name}  ({model_dir})")
    print(f"{'='*60}")

    out_base = OUTPUT_DIR / model_name / "IntegratedAgent"

    for agent_dir_name, suffix in AGENT_DIRS:
        agent_dir = model_dir / agent_dir_name
        file_results = load_filtered(agent_dir, suffix)
        if not file_results:
            print(f"  [skip] {agent_dir_name} — no files found")
            continue

        print(f"  Integrating {len(file_results)} docs for {agent_dir_name}...")

        int_dir = out_base / agent_dir_name
        int_dir.mkdir(parents=True, exist_ok=True)

        enriched = int_agent.enrich_batch(
            file_results,
            agent_name=agent_dir_name,
            output_dir=str(int_dir),
        )

        for fname, data in enriched.items():
            out = int_dir / fname
            with open(out, "w") as f:
                json.dump(data, f, indent=2)

        print(f"  Written: {int_dir.relative_to(FINAL_RESULTS)}/ ({len(enriched)} docs)")


def main() -> None:
    if not METI_DIR.exists():
        print(f"ERROR: METI dir not found: {METI_DIR}", file=sys.stderr)
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    int_agent = IntegrationAgent(str(METI_DIR))

    for model_name, model_dir in MODEL_FOLDERS.items():
        if not model_dir.exists():
            print(f"  [skip] {model_name} — folder not found: {model_dir}")
            continue
        run_model(model_name, model_dir, int_agent)

    print(f"\nDone. Results in: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
