"""
Tier-level benchmarking analysis: which matching tier recovered which entities,
aggregated across all 4 models and 3 agents.
"""

import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.gridspec as gridspec
import numpy as np
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

BASE   = Path("benchmark_data/Final_results/test_new_test_meti_integrated")
OUT    = BASE
MODELS = ["llama", "claude", "gpt", "gemini"]
AGENTS = {
    "biologicalagent":          "BiologicalAgent",
    "technicalagent":           "TechnicalAgent",
    "experimentaldesignagent":  "ExperimentalDesignAgent",
}

TIER_COLORS = {
    "exact":      "#2ecc71",
    "normalized": "#27ae60",
    "semantic":   "#3498db",
    "no_match":   "#e74c3c",
}
TIER_LABELS = {
    "exact":      "Exact",
    "normalized": "Normalized",
    "semantic":   "Semantic (SciBERT)",
    "no_match":   "No Match",
}
TIER_ORDER = ["exact", "normalized", "semantic", "no_match"]

# Nicer display names for fields
DISPLAY = {
    "species": "species", "tissue": "tissue", "organ": "organ",
    "cell_type": "cell_type", "cell_line": "cell_line",
    "disease": "disease", "material_type": "material_type",
    "sex": "sex", "age": "age", "strain": "strain",
    "developmental_stage": "dev_stage", "BMI": "BMI", "ethnicity": "ethnicity",
    "instrument": "instrument", "label": "labeling", "cleavage_agent": "cleavage_agent",
    "fragmentation": "fragmentation", "fractionation": "fractionation",
    "reduction_reagent": "reduc_reagent", "mass_analyzer": "mass_analyzer",
    "ptm": "PTM", "enrichment_method": "enrichment",
    "collision_energy": "coll_energy", "acquisition_method": "acquisition",
    "fragment_tolerance": "frag_tol", "precursor_tolerance": "precur_tol",
    "replicates": "bio_replicates", "technical_replicates": "tech_replicates",
    "fractions": "n_fractions", "number_of_samples": "n_samples",
    "factor_value": "factor_value", "missed_cleavages": "missed_cleavages",
    "technology_type": "tech_type",
}


def load_all() -> pd.DataFrame:
    rows = []
    for model in MODELS:
        for agent_key, agent_label in AGENTS.items():
            csv = BASE / model / f"{agent_key}_semantic_field_metrics.csv"
            if not csv.exists():
                continue
            df = pd.read_csv(csv)
            df["model"] = model
            df["agent"] = agent_label
            rows.append(df)
    return pd.concat(rows, ignore_index=True)


def plot_overall_tier_pie(all_df: pd.DataFrame):
    """Pie chart of overall tier distribution."""
    totals = {t: int(all_df[t].sum()) for t in TIER_ORDER}

    fig, ax = plt.subplots(figsize=(6, 6))
    sizes  = [totals[t] for t in TIER_ORDER]
    colors = [TIER_COLORS[t] for t in TIER_ORDER]
    labels = [f"{TIER_LABELS[t]}\n({totals[t]:,})" for t in TIER_ORDER]
    wedges, texts, autotexts = ax.pie(
        sizes, labels=labels, colors=colors, autopct="%1.1f%%",
        startangle=140, pctdistance=0.7,
        wedgeprops={"edgecolor": "white", "linewidth": 1.5}
    )
    for at in autotexts:
        at.set_fontsize(10)
        at.set_fontweight("bold")
        at.set_color("white")
    ax.set_title(
        f"Overall Match Tier Distribution\n"
        f"(4 models × 3 agents × 23 PXDs — {sum(sizes):,} comparisons)",
        fontsize=12, fontweight="bold"
    )
    fig.tight_layout()
    fig.savefig(OUT / "tier_overall_pie.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("Saved: tier_overall_pie.png")


def plot_per_agent_tier_bars(all_df: pd.DataFrame):
    """
    One subplot per agent.
    Horizontal stacked bar per field, sorted by exact% descending.
    Fields with zero total are excluded.
    """
    fig, axes = plt.subplots(1, 3, figsize=(22, 10), gridspec_kw={"wspace": 0.5})

    for ax, (agent_key, agent_label) in zip(axes, AGENTS.items()):
        agent_label_nice = agent_label
        sub = (all_df[all_df["agent"] == agent_label]
               .groupby("field")[TIER_ORDER + ["total"]]
               .sum())
        sub = sub[sub["total"] > 0]

        # Convert to percentages
        for t in TIER_ORDER:
            sub[f"{t}_pct"] = sub[t] / sub["total"] * 100

        sub = sub.sort_values("exact_pct", ascending=True)
        fields = [DISPLAY.get(f, f) for f in sub.index]
        y = np.arange(len(fields))
        bar_h = 0.65

        lefts = np.zeros(len(fields))
        for tier in TIER_ORDER:
            vals = sub[f"{tier}_pct"].values
            bars = ax.barh(y, vals, left=lefts, height=bar_h,
                           color=TIER_COLORS[tier], label=TIER_LABELS[tier])
            for i, (v, l) in enumerate(zip(vals, lefts)):
                if v >= 8:
                    ax.text(l + v / 2, i, f"{v:.0f}%",
                            ha="center", va="center", fontsize=6.5,
                            color="white", fontweight="bold")
            lefts += vals

        # Annotate total comparisons
        for i, (field_raw, total) in enumerate(zip(sub.index, sub["total"])):
            ax.text(101, i, f"n={int(total)}", va="center", fontsize=6.5, color="grey")

        ax.set_yticks(y)
        ax.set_yticklabels(fields, fontsize=8.5)
        ax.set_xlim(0, 115)
        ax.set_xlabel("% of comparisons", fontsize=9)
        ax.set_title(agent_label_nice, fontsize=11, fontweight="bold")
        ax.xaxis.grid(True, linestyle="--", alpha=0.4)
        ax.set_axisbelow(True)

    handles = [mpatches.Patch(color=TIER_COLORS[t], label=TIER_LABELS[t])
               for t in TIER_ORDER]
    fig.legend(handles=handles, loc="lower center", ncol=4, fontsize=10,
               bbox_to_anchor=(0.5, -0.04))
    fig.suptitle(
        "Match Tier Distribution per Field and Agent\n"
        "(4 models × 23 PXDs, sorted by Exact% ascending)",
        fontsize=13, fontweight="bold", y=1.01
    )
    fig.savefig(OUT / "tier_per_field.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("Saved: tier_per_field.png")


def plot_semantic_spotlight(all_df: pd.DataFrame):
    """
    Highlight the fields where SEMANTIC is doing the most work.
    Grouped bar: exact count vs semantic count per field (top semantic fields).
    """
    agg = all_df.groupby(["field", "agent"])[TIER_ORDER + ["total"]].sum().reset_index()
    agg["sem_pct"]   = agg["semantic"] / agg["total"] * 100
    agg["exact_pct"] = agg["exact"]    / agg["total"] * 100

    # Keep only fields where semantic > 5% of comparisons
    top = agg[agg["sem_pct"] > 5].sort_values("sem_pct", ascending=False)

    fig, ax = plt.subplots(figsize=(12, 6))
    bar_w = 0.35
    x = np.arange(len(top))

    b1 = ax.bar(x - bar_w / 2, top["exact_pct"],   width=bar_w,
                color="#2ecc71", label="Exact", alpha=0.9)
    b2 = ax.bar(x + bar_w / 2, top["sem_pct"],     width=bar_w,
                color="#3498db", label="Semantic (SciBERT)", alpha=0.9)

    for bar in list(b1) + list(b2):
        h = bar.get_height()
        if h > 3:
            ax.text(bar.get_x() + bar.get_width() / 2, h + 0.5,
                    f"{h:.0f}%", ha="center", fontsize=7.5, fontweight="bold")

    xtick_labels = [
        f"{DISPLAY.get(row.field, row.field)}\n({row.agent.replace('Agent','')})"
        for _, row in top.iterrows()
    ]
    ax.set_xticks(x)
    ax.set_xticklabels(xtick_labels, fontsize=8.5, rotation=20, ha="right")
    ax.set_ylabel("% of comparisons", fontsize=10)
    ax.set_ylim(0, 80)
    ax.set_title(
        "Fields Where SciBERT Semantic Matching Does Most Work\n"
        "(fields with >5% semantic match rate, all models combined)",
        fontsize=12, fontweight="bold"
    )
    ax.legend(fontsize=10)
    ax.yaxis.grid(True, linestyle="--", alpha=0.4)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(OUT / "tier_semantic_spotlight.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("Saved: tier_semantic_spotlight.png")


def plot_tier_by_model(all_df: pd.DataFrame):
    """
    Grouped bar: tier distribution per model (summed across agents and fields).
    Shows whether different models rely on different tiers.
    """
    model_agg = all_df.groupby("model")[TIER_ORDER + ["total"]].sum()
    for t in TIER_ORDER:
        model_agg[f"{t}_pct"] = model_agg[t] / model_agg["total"] * 100

    fig, ax = plt.subplots(figsize=(10, 5))
    models = ["llama", "claude", "gpt", "gemini"]
    x = np.arange(len(models))
    bar_w = 0.18

    for i, tier in enumerate(TIER_ORDER):
        vals = [model_agg.loc[m, f"{tier}_pct"] for m in models]
        offset = x + (i - 1.5) * bar_w
        bars = ax.bar(offset, vals, width=bar_w, color=TIER_COLORS[tier],
                      label=TIER_LABELS[tier], alpha=0.9)
        for bar, v in zip(bars, vals):
            if v > 3:
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.3,
                        f"{v:.0f}%", ha="center", fontsize=7.5, fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels([m.capitalize() for m in models], fontsize=12)
    ax.set_ylabel("% of all comparisons", fontsize=10)
    ax.set_title(
        "Match Tier Distribution by Model\n(summed across all agents and fields)",
        fontsize=12, fontweight="bold"
    )
    ax.legend(fontsize=9)
    ax.yaxis.grid(True, linestyle="--", alpha=0.4)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(OUT / "tier_by_model.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("Saved: tier_by_model.png")


if __name__ == "__main__":
    all_df = load_all()
    plot_overall_tier_pie(all_df)
    plot_per_agent_tier_bars(all_df)
    plot_semantic_spotlight(all_df)
    plot_tier_by_model(all_df)
    print("Done.")
