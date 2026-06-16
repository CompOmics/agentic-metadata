#!/usr/bin/env python3
"""Plot F1 uplift across matching levels for a single model."""

import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

MODEL = "gemma"
CSV = Path(f"benchmark_data/reports_test_v2_{MODEL}_nopride/sdrf_benchmark_detailed.csv")
OUT = Path(f"benchmark_data/plots_matching_levels_{MODEL}.png")

LEVEL_LABELS = ["String\n(Exact only)", "+ Normalization", "+ Semantic"]
AGENTS = {
    "BiologicalAgent":        "Biological",
    "TechnicalAgent":         "Technical",
    "ExperimentalDesignAgent":"Exp. Design",
}
COLORS = ["#5b9bd5", "#70ad47", "#ed7d31"]

df = pd.read_csv(CSV)
df["llm_has_value"] = df["llm"].notna() & (df["llm"].astype(str).str.strip() != "")
df["golden_has_value"] = df["golden"].notna() & (df["golden"].astype(str).str.strip() != "")

MATCH_THRESHOLD = 0.5

def compute_prf(sub, is_match_col):
    """Return (precision, recall, f1) per benchmark's calculate_weighted_metrics logic."""
    both = sub["llm_has_value"] & sub["golden_has_value"]
    tp = (both & sub[is_match_col]).sum()
    fp = (both & ~sub[is_match_col]).sum()
    fn = fp + (~sub["llm_has_value"] & sub["golden_has_value"]).sum()
    p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
    return p, r, f1

# Pre-compute match columns
df["m_exact"]    = df["match_type"] == "EXACT"
df["m_semantic"] = df["score"] >= MATCH_THRESHOLD

# rows[agent_label] = {"before": (p,r,f1), "after": (p,r,f1)}
rows = {}
for agent_key, agent_label in AGENTS.items():
    sub = df[df["agent"] == agent_key]
    rows[agent_label] = {
        "before": compute_prf(sub, "m_exact"),
        "after":  compute_prf(sub, "m_semantic"),
    }

# Overall = macro average across agents
for panel in ("before", "after"):
    avg = tuple(np.mean([rows[a][panel][i] for a in AGENTS.values()]) for i in range(3))
    rows.setdefault("Overall", {})[panel] = avg


groups = list(rows.keys())   # Bio, Technical, Exp. Design, Overall
x = np.arange(len(groups))
width = 0.22
metric_labels = ["Precision", "Recall", "F1 Score"]
metric_colors = ["#5b9bd5", "#70ad47", "#9b59b6"]

panels = [
    ("before", "Before (String Exact only)"),
    ("after",  "After (Full Semantic Matching)"),
]

fig, axes = plt.subplots(1, 2, figsize=(14, 6), sharey=True)
fig.suptitle("SDRF Benchmark — Gemma-4-31B  |  30 PXDs\nBefore vs After Semantic Matching",
             fontsize=13, fontweight="bold")

for ax, (panel_key, title) in zip(axes, panels):
    for i, (label, color) in enumerate(zip(metric_labels, metric_colors)):
        vals = [rows[g][panel_key][i] for g in groups]
        offset = (i - 1) * width
        bars = ax.bar(x + offset, vals, width, label=label,
                      color=color, alpha=0.85, edgecolor="white", linewidth=0.5)
        for bar, v, g in zip(bars, vals, groups):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01,
                    f"{v:.3f}", ha="center", va="bottom", fontsize=7.5,
                    fontweight="bold" if (label == "F1 Score") else "normal")

    ax.set_xticks(x)
    ax.set_xticklabels(groups, fontsize=11)
    ax.set_ylim(0, 1.12)
    ax.set_ylabel("Score", fontsize=11)
    ax.set_title(title, fontsize=11, fontweight="bold", pad=8)
    ax.spines[["top", "right"]].set_visible(False)
    ax.yaxis.grid(True, alpha=0.3, linestyle="--")
    ax.set_axisbelow(True)
    if ax == axes[0]:
        ax.legend(fontsize=9, loc="upper left", framealpha=0.9)

plt.tight_layout()
plt.savefig(OUT, dpi=150, bbox_inches="tight")
print(f"Saved: {OUT}")

# Print numbers
print(f"\n{'Agent':<20} {'Before P':>9} {'Before R':>9} {'Before F1':>10} {'After P':>8} {'After R':>8} {'After F1':>9}")
print("-" * 75)
for g in groups:
    bp, br, bf = rows[g]["before"]
    ap, ar, af = rows[g]["after"]
    print(f"{g:<20} {bp:>9.3f} {br:>9.3f} {bf:>10.3f} {ap:>8.3f} {ar:>8.3f} {af:>9.3f}")
