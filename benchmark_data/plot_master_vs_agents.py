#!/usr/bin/env python3
"""
Compare master_prompt vs specialized agents using the same model (GPT).
Same-model comparison isolates the effect of prompt strategy.
"""

import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

BASE      = Path(__file__).parent.parent  # extraction_framework/
POST      = BASE / "Posterity_stuff" / "outputs"
AGENTS    = BASE / "benchmark_data" / "Final_results" / "test_v2_nopride"
OUT       = BASE / "benchmark_data"

SKIP_KEYS = {"_confidence", "_hallucination_flags", "_sources", "_provenance",
             "_meti_data", "_enrichment", "modification_site_fractions",
             "pxd_id", "pipeline_version"}

AGENT_DIRS = ["BiologicalAgent", "TechnicalAgent", "ExperimentalDesignAgent"]


def count_master_prompt(ann_dir):
    counts = {}
    for f in sorted(ann_dir.glob("*.ann")):
        lines = [l for l in f.read_text().splitlines() if l.startswith("T")]
        counts[f.stem] = len(lines)
    return counts


def count_agent_fields(model):
    counts = {}
    base = AGENTS / model / "IntegratedAgent"
    pxds = set()
    for ag in AGENT_DIRS:
        pxds.update(f.stem.split("_")[0] for f in (base / ag).glob("*.json"))
    for pxd in sorted(pxds):
        total = 0
        for ag in AGENT_DIRS:
            matches = list((base / ag).glob(f"{pxd}_*.json"))
            if not matches:
                continue
            d = json.loads(matches[0].read_text())
            for k, v in d.items():
                if k in SKIP_KEYS:
                    continue
                if v in (None, "", "unknown", []):
                    continue
                if isinstance(v, list) and len(v) >= 1 and v[0] in ("unknown", "", None):
                    continue
                total += 1
        counts[pxd] = total
    return counts


# ── Load GPT series only (same model, different prompt strategy) ──────────────
master_gpt = count_master_prompt(POST / "ann_files_gpt")
agents_gpt = count_agent_fields("gpt")

pxds = sorted(set(master_gpt) & set(agents_gpt))
print(f"PXDs in common: {len(pxds)}")

mg = np.array([master_gpt[p] for p in pxds])
ag = np.array([agents_gpt[p] for p in pxds])

x = np.arange(len(pxds))
w = 0.35

fig, axes = plt.subplots(2, 1, figsize=(17, 10), sharex=True)
fig.suptitle("Master Prompt vs Specialized Agents — GPT-4o, 30-PXD Test Set",
             fontsize=13, fontweight="bold")

# ── Top: master prompt ────────────────────────────────────────────────────────
ax = axes[0]
ax.bar(x, mg, w, color="#2166ac", alpha=0.88, edgecolor="white", lw=0.4)
ax.axhline(np.mean(mg), color="#2166ac", ls="--", lw=1.4, alpha=0.8)
ax.text(0.01, np.mean(mg) + 1,
        f"mean={np.mean(mg):.0f}  std={np.std(mg):.0f}  zeros={np.sum(mg==0)}",
        transform=ax.get_yaxis_transform(), fontsize=9, color="#2166ac", va="bottom")
ax.set_ylabel("BRAT annotation spans", fontsize=10)
ax.set_title("Master Prompt (single monolithic prompt)", fontsize=11, fontweight="bold", pad=6)
ax.spines[["top", "right"]].set_visible(False)
ax.yaxis.grid(True, alpha=0.3, ls="--")
ax.set_axisbelow(True)

# ── Bottom: specialized agents ────────────────────────────────────────────────
ax = axes[1]
ax.bar(x, ag, w, color="#d6604d", alpha=0.88, edgecolor="white", lw=0.4)
ax.axhline(np.mean(ag), color="#d6604d", ls="--", lw=1.4, alpha=0.8)
ax.text(0.01, np.mean(ag) + 0.3,
        f"mean={np.mean(ag):.0f}  std={np.std(ag):.0f}  zeros={np.sum(ag==0)}",
        transform=ax.get_yaxis_transform(), fontsize=9, color="#d6604d", va="bottom")
ax.set_ylabel("Non-empty metadata fields", fontsize=10)
ax.set_title("Specialized Agents (Biological + Technical + Experimental)",
             fontsize=11, fontweight="bold", pad=6)
ax.spines[["top", "right"]].set_visible(False)
ax.yaxis.grid(True, alpha=0.3, ls="--")
ax.set_axisbelow(True)

ax.set_xticks(x)
ax.set_xticklabels(pxds, rotation=45, ha="right", fontsize=8)

plt.tight_layout()
out = OUT / "plots_master_vs_agents.png"
plt.savefig(out, dpi=150, bbox_inches="tight")
print(f"Saved: {out}")

print(f"\nMaster prompt  — mean={np.mean(mg):.1f}  std={np.std(mg):.1f}  zeros={np.sum(mg==0)}")
print(f"Specialized    — mean={np.mean(ag):.1f}  std={np.std(ag):.1f}  zeros={np.sum(ag==0)}")
