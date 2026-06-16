#!/usr/bin/env python3
"""
Scatter plot: Llama count vs GPT count per PXD.
Left: master_prompt  Right: specialized agents
Tight diagonal cluster = consistency; scatter = instability.
"""

import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import pearsonr

BASE  = Path(__file__).parent.parent
POST  = BASE / "Posterity_stuff" / "outputs"
AGENTS_DIR = BASE / "benchmark_data" / "Final_results" / "test_v2_nopride"
OUT   = BASE / "benchmark_data"

SKIP_KEYS = {"_confidence","_hallucination_flags","_sources","_provenance",
             "_meti_data","_enrichment","modification_site_fractions",
             "pxd_id","pipeline_version"}
AGENT_DIRS = ["BiologicalAgent","TechnicalAgent","ExperimentalDesignAgent"]


def count_master(ann_dir):
    return {f.stem: sum(1 for l in f.read_text().splitlines() if l.startswith("T"))
            for f in sorted(ann_dir.glob("*.ann"))}


def count_agents(model):
    counts = {}
    base = AGENTS_DIR / model / "IntegratedAgent"
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
                if isinstance(v, list) and len(v) >= 1 and v[0] in ("unknown","",None):
                    continue
                total += 1
        counts[pxd] = total
    return counts


ml = count_master(POST / "ann_files")
mg = count_master(POST / "ann_files_gpt")
al = count_agents("llama")
ag = count_agents("gpt")

pxds = sorted(set(ml) & set(mg) & set(al) & set(ag))

x_m = np.array([ml[p] for p in pxds])
y_m = np.array([mg[p] for p in pxds])
x_a = np.array([al[p] for p in pxds])
y_a = np.array([ag[p] for p in pxds])

r_m, _ = pearsonr(x_m, y_m)
r_a, _ = pearsonr(x_a, y_a)

fig, axes = plt.subplots(1, 2, figsize=(12, 5.5))
fig.suptitle("Model Consistency: Llama vs GPT per PXD\n"
             "Master Prompt vs Specialized Agents",
             fontsize=13, fontweight="bold")

panels = [
    (axes[0], x_m, y_m, "#2166ac", "Master Prompt\n(single monolithic prompt)", r_m),
    (axes[1], x_a, y_a, "#d6604d", "Specialized Agents\n(structured schema)", r_a),
]

for ax, x, y, color, title, r in panels:
    ax.scatter(x, y, color=color, alpha=0.75, s=55, edgecolors="white", linewidth=0.5)

    # diagonal reference line
    lim = max(x.max(), y.max()) * 1.08
    ax.plot([0, lim], [0, lim], color="gray", lw=1, ls="--", alpha=0.5, label="y = x")
    ax.set_xlim(-2, lim)
    ax.set_ylim(-2, lim)

    ax.set_xlabel("Llama — count per PXD", fontsize=11)
    ax.set_ylabel("GPT — count per PXD", fontsize=11)
    ax.set_title(title, fontsize=12, fontweight="bold", pad=8)

    # annotate r and stats
    ax.text(0.97, 0.05,
            f"r = {r:.2f}\nLlama μ={x.mean():.0f} σ={x.std():.0f}\nGPT   μ={y.mean():.0f} σ={y.std():.0f}",
            transform=ax.transAxes, ha="right", va="bottom",
            fontsize=9, bbox=dict(boxstyle="round,pad=0.4", fc="white", alpha=0.8))

    ax.spines[["top","right"]].set_visible(False)
    ax.yaxis.grid(True, alpha=0.25, ls="--")
    ax.xaxis.grid(True, alpha=0.25, ls="--")
    ax.set_axisbelow(True)

plt.tight_layout()
out = OUT / "plots_stability_scatter.png"
plt.savefig(out, dpi=150, bbox_inches="tight")
print(f"Saved: {out}")
