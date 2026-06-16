#!/usr/bin/env python3
"""
Compare master_prompt vs specialized agents: annotation counts per PXD.
Shows instability of master_prompt across models vs consistency of specialized agents.
"""

import json
import re
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
    """Count BRAT annotation spans per PXD."""
    counts = {}
    for f in sorted(ann_dir.glob("*.ann")):
        lines = [l for l in f.read_text().splitlines() if l.startswith("T")]
        counts[f.stem] = len(lines)
    return counts


def count_agent_fields(model):
    """Count non-empty fields across all 3 agents per PXD."""
    counts = {}
    base = AGENTS / model / "IntegratedAgent"
    # collect all PXDs from any agent dir
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


# ── Load all four series ──────────────────────────────────────────────────────
master_llama = count_master_prompt(POST / "ann_files")
master_gpt   = count_master_prompt(POST / "ann_files_gpt")
agents_llama = count_agent_fields("llama")
agents_gpt   = count_agent_fields("gpt")

# Align on shared PXDs (all 30 test PXDs present in all four)
pxds = sorted(set(master_llama) & set(master_gpt) & set(agents_llama) & set(agents_gpt))
print(f"PXDs in common: {len(pxds)}")

ml = np.array([master_llama[p] for p in pxds])
mg = np.array([master_gpt[p]   for p in pxds])
al = np.array([agents_llama[p] for p in pxds])
ag = np.array([agents_gpt[p]   for p in pxds])

x = np.arange(len(pxds))
w = 0.2

fig, axes = plt.subplots(2, 1, figsize=(17, 10), sharex=True)
fig.suptitle("Master Prompt vs Specialized Agents — Extraction Volume per PXD\n"
             "30-PXD Test Set", fontsize=13, fontweight="bold")

# ── Top: master prompt ────────────────────────────────────────────────────────
ax = axes[0]
ax.bar(x - w/2, ml, w, color="#4393c3", alpha=0.9, label="Master prompt — Llama", edgecolor="white", lw=0.4)
ax.bar(x + w/2, mg, w, color="#2166ac", alpha=0.9, label="Master prompt — GPT",   edgecolor="white", lw=0.4)
ax.axhline(np.mean(ml), color="#4393c3", ls="--", lw=1.2, alpha=0.7)
ax.axhline(np.mean(mg), color="#2166ac", ls="--", lw=1.2, alpha=0.7)
ax.text(0.01, np.mean(ml)+1, f"Llama mean: {np.mean(ml):.0f}", transform=ax.get_yaxis_transform(),
        fontsize=8, color="#4393c3", va="bottom")
ax.text(0.01, np.mean(mg)+1, f"GPT mean: {np.mean(mg):.0f}", transform=ax.get_yaxis_transform(),
        fontsize=8, color="#2166ac", va="bottom")
ax.set_ylabel("BRAT annotation spans", fontsize=10)
ax.set_title("Master Prompt (single monolithic prompt)", fontsize=11, fontweight="bold", pad=6)
ax.legend(fontsize=9, loc="upper right")
ax.spines[["top","right"]].set_visible(False)
ax.yaxis.grid(True, alpha=0.3, ls="--")
ax.set_axisbelow(True)

# ── Bottom: specialized agents ────────────────────────────────────────────────
ax = axes[1]
ax.bar(x - w/2, al, w, color="#f4a582", alpha=0.9, label="Specialized agents — Llama", edgecolor="white", lw=0.4)
ax.bar(x + w/2, ag, w, color="#d6604d", alpha=0.9, label="Specialized agents — GPT",   edgecolor="white", lw=0.4)
ax.axhline(np.mean(al), color="#f4a582", ls="--", lw=1.2, alpha=0.7)
ax.axhline(np.mean(ag), color="#d6604d", ls="--", lw=1.2, alpha=0.7)
ax.text(0.01, np.mean(al)+0.2, f"Llama mean: {np.mean(al):.0f}", transform=ax.get_yaxis_transform(),
        fontsize=8, color="#c07040", va="bottom")
ax.text(0.01, np.mean(ag)+0.2, f"GPT mean: {np.mean(ag):.0f}", transform=ax.get_yaxis_transform(),
        fontsize=8, color="#d6604d", va="bottom")
ax.set_ylabel("Non-empty metadata fields", fontsize=10)
ax.set_title("Specialized Agents (Biological + Technical + Experimental)", fontsize=11, fontweight="bold", pad=6)
ax.legend(fontsize=9, loc="upper right")
ax.spines[["top","right"]].set_visible(False)
ax.yaxis.grid(True, alpha=0.3, ls="--")
ax.set_axisbelow(True)

ax.set_xticks(x)
ax.set_xticklabels(pxds, rotation=45, ha="right", fontsize=8)

plt.tight_layout()
out = OUT / "plots_master_vs_agents.png"
plt.savefig(out, dpi=150, bbox_inches="tight")
print(f"Saved: {out}")

print(f"\nMaster prompt  — Llama mean={np.mean(ml):.1f}  std={np.std(ml):.1f}  zeros={np.sum(ml==0)}")
print(f"Master prompt  — GPT   mean={np.mean(mg):.1f}  std={np.std(mg):.1f}  zeros={np.sum(mg==0)}")
print(f"Specialized    — Llama mean={np.mean(al):.1f}  std={np.std(al):.1f}  zeros={np.sum(al==0)}")
print(f"Specialized    — GPT   mean={np.mean(ag):.1f}  std={np.std(ag):.1f}  zeros={np.sum(ag==0)}")
