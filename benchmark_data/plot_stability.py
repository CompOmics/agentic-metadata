#!/usr/bin/env python3
"""
Scatter plot: Llama count vs GPT count per PXD.
Blue = master prompt, Red = specialized agents.
Both series in one panel; diagonal = perfect agreement.
"""

import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from scipy.stats import pearsonr

BASE       = Path(__file__).parent.parent
POST       = BASE / "Posterity_stuff" / "outputs"
AGENTS_DIR = BASE / "benchmark_data" / "Final_results" / "test_v2_nopride"
OUT        = BASE / "benchmark_data"

SKIP_KEYS  = {"_confidence","_hallucination_flags","_sources","_provenance",
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
try:
    r_a, _ = pearsonr(x_a, y_a)
except Exception:
    r_a = float("nan")

fig, ax = plt.subplots(figsize=(7, 6.5))
fig.suptitle("Model Consistency: Llama vs GPT per PXD\nMaster Prompt vs Specialized Agents",
             fontsize=13, fontweight="bold")

# diagonal reference (fit to full range)
lim = max(x_m.max(), y_m.max()) * 1.08
ax.plot([0, lim], [0, lim], color="gray", lw=1, ls="--", alpha=0.5, zorder=0)

ax.scatter(x_m, y_m, color="#2166ac", alpha=0.75, s=60,
           edgecolors="white", linewidth=0.5, label="Master Prompt", zorder=2)

rng = np.random.default_rng(42)
jitter = rng.normal(0, 2.0, size=len(x_a))
ax.scatter(x_a + jitter, y_a + jitter, color="#d6604d", alpha=0.7, s=60,
           edgecolors="white", linewidth=0.5, label="Specialized Agents", zorder=2)

ax.set_xlim(-2, lim)
ax.set_ylim(-2, lim)
ax.set_xlabel("Llama — count per PXD", fontsize=11)
ax.set_ylabel("GPT — count per PXD", fontsize=11)

r_a_str = f"{r_a:.2f}" if r_a == r_a else "nan"
stats_text = (f"Master Prompt:  r = {r_m:.2f}  "
              f"(Llama μ={x_m.mean():.0f}, GPT μ={y_m.mean():.0f})\n"
              f"Spec. Agents:   r = {r_a_str}  "
              f"(Llama μ={x_a.mean():.0f}, GPT μ={y_a.mean():.0f})")
ax.text(0.03, 0.97, stats_text, transform=ax.transAxes,
        ha="left", va="top", fontsize=8.5,
        bbox=dict(boxstyle="round,pad=0.4", fc="white", alpha=0.85))

ax.legend(fontsize=10, loc="lower right")
ax.spines[["top","right"]].set_visible(False)
ax.yaxis.grid(True, alpha=0.25, ls="--")
ax.xaxis.grid(True, alpha=0.25, ls="--")
ax.set_axisbelow(True)

plt.tight_layout()
out = OUT / "plots_stability_scatter.png"
plt.savefig(out, dpi=150, bbox_inches="tight")
print(f"Saved: {out}")
