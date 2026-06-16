#!/usr/bin/env python3
"""Stacked bar chart of match type distribution per agent."""

import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

MODEL = "gemma"
CSV = Path(f"benchmark_data/reports_test_v2_{MODEL}_nopride/sdrf_benchmark_detailed.csv")
OUT = Path(f"benchmark_data/plots_match_distribution_{MODEL}.png")

AGENTS = {
    "BiologicalAgent":         "Biological",
    "TechnicalAgent":          "Technical",
    "ExperimentalDesignAgent": "Exp. Design",
}

TIERS   = ["EXACT", "NORMALIZED", "SEMANTIC", "NO_MATCH"]
COLORS  = ["#27ae60", "#82e0aa", "#f39c12", "#e74c3c"]
LABELS  = ["Exact", "Normalized", "Semantic", "No Match"]

df = pd.read_csv(CSV)

def tier_counts(sub):
    total = len(sub)
    counts = {mt: sub["match_type"].eq(mt).sum() / total * 100 for mt in TIERS}
    return counts

data = {}
for agent_key, agent_label in AGENTS.items():
    data[agent_label] = tier_counts(df[df["agent"] == agent_key])

data["Overall"] = tier_counts(df)

groups = list(data.keys())
x = np.arange(len(groups))
width = 0.5

fig, ax = plt.subplots(figsize=(9, 5.5))

bottoms = np.zeros(len(groups))
for mt, color, label in zip(TIERS, COLORS, LABELS):
    vals = np.array([data[g][mt] for g in groups])
    bars = ax.bar(x, vals, width, bottom=bottoms, color=color,
                  label=label, edgecolor="white", linewidth=0.6)
    # Label segments that are wide enough to read
    for bar, v, b in zip(bars, vals, bottoms):
        if v >= 4:
            ax.text(bar.get_x() + bar.get_width() / 2,
                    b + v / 2,
                    f"{v:.1f}%", ha="center", va="center",
                    fontsize=9, color="white", fontweight="bold")
    bottoms += vals

ax.set_xticks(x)
ax.set_xticklabels(groups, fontsize=12)
ax.set_ylim(0, 105)
ax.set_ylabel("Entities (%)", fontsize=12)
ax.set_title(
    f"SDRF Benchmark — Gemma-4-31B  |  Entity Capture by Match Level\n30 PXDs",
    fontsize=12, fontweight="bold"
)
ax.legend(loc="upper right", fontsize=10, framealpha=0.9)
ax.spines[["top", "right"]].set_visible(False)
ax.yaxis.grid(True, alpha=0.25, linestyle="--")
ax.set_axisbelow(True)

plt.tight_layout()
plt.savefig(OUT, dpi=150, bbox_inches="tight")
print(f"Saved: {OUT}")

# Print table
print(f"\n{'Agent':<16}", "  ".join(f"{l:>10}" for l in LABELS))
print("-" * 60)
for g in groups:
    row = "  ".join(f"{data[g][mt]:>9.1f}%" for mt in TIERS)
    print(f"{g:<16}  {row}")
