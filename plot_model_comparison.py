"""
Consolidated multi-model benchmark comparison plot for the 23 METI-enabled
test+new_test PXDs.

Output: benchmark_data/Final_results/test_new_test_meti_integrated/model_comparison.png
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from pathlib import Path

RESULTS = {
    "llama": {
        "BiologicalAgent":        {"P": 0.985, "R": 0.827, "F1": 0.899},
        "TechnicalAgent":         {"P": 0.982, "R": 0.848, "F1": 0.911},
        "ExperimentalDesignAgent":{"P": 0.966, "R": 0.757, "F1": 0.848},
    },
    "claude": {
        "BiologicalAgent":        {"P": 0.986, "R": 0.864, "F1": 0.921},
        "TechnicalAgent":         {"P": 0.982, "R": 0.833, "F1": 0.902},
        "ExperimentalDesignAgent":{"P": 0.969, "R": 0.838, "F1": 0.899},
    },
    "gpt": {
        "BiologicalAgent":        {"P": 0.985, "R": 0.827, "F1": 0.899},
        "TechnicalAgent":         {"P": 1.000, "R": 0.803, "F1": 0.891},
        "ExperimentalDesignAgent":{"P": 0.971, "R": 0.892, "F1": 0.930},
    },
    "gemini": {
        "BiologicalAgent":        {"P": 0.986, "R": 0.889, "F1": 0.935},
        "TechnicalAgent":         {"P": 0.982, "R": 0.833, "F1": 0.902},
        "ExperimentalDesignAgent":{"P": 0.971, "R": 0.892, "F1": 0.930},
    },
}

MODELS = ["llama", "claude", "gpt", "gemini"]
AGENTS = ["BiologicalAgent", "TechnicalAgent", "ExperimentalDesignAgent"]
AGENT_LABELS = ["Biological", "Technical", "Experimental Design"]
METRICS = ["P", "R", "F1"]
METRIC_LABELS = ["Precision", "Recall", "F1"]

MODEL_COLORS = {
    "llama":  "#4C72B0",
    "claude": "#DD8452",
    "gpt":    "#55A868",
    "gemini": "#C44E52",
}

OUT_DIR = Path("benchmark_data/Final_results/test_new_test_meti_integrated")

# ── Figure 1: grouped bar chart — F1 per agent per model ─────────────────────

def plot_f1_grouped():
    fig, ax = plt.subplots(figsize=(10, 6))

    n_agents = len(AGENTS)
    n_models = len(MODELS)
    bar_w = 0.18
    group_gap = 0.85
    x = np.arange(n_agents) * group_gap

    for i, model in enumerate(MODELS):
        offsets = x + (i - (n_models - 1) / 2) * bar_w
        f1s = [RESULTS[model][a]["F1"] for a in AGENTS]
        bars = ax.bar(offsets, f1s, width=bar_w, color=MODEL_COLORS[model],
                      label=model.capitalize(), edgecolor="white", linewidth=0.5)
        for bar, val in zip(bars, f1s):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.003,
                    f"{val:.3f}", ha="center", va="bottom", fontsize=7.5, rotation=90)

    ax.set_xticks(x)
    ax.set_xticklabels(AGENT_LABELS, fontsize=12)
    ax.set_ylabel("Weighted F1", fontsize=12)
    ax.set_title("F1 Score by Agent and Model\n(23 test+new_test PXDs with METI data)", fontsize=13)
    ax.set_ylim(0.80, 1.02)
    ax.legend(title="Model", fontsize=10, title_fontsize=10)
    ax.yaxis.grid(True, linestyle="--", alpha=0.5)
    ax.set_axisbelow(True)
    fig.tight_layout()
    out = OUT_DIR / "model_comparison_f1.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"Saved: {out}")


# ── Figure 2: P / R / F1 grouped by model, one subplot per agent ─────────────

def plot_prf_per_agent():
    fig, axes = plt.subplots(1, 3, figsize=(15, 5), sharey=True)

    bar_w = 0.22
    x = np.arange(len(METRICS))

    for ax, agent, label in zip(axes, AGENTS, AGENT_LABELS):
        for i, model in enumerate(MODELS):
            vals = [RESULTS[model][agent][m] for m in METRICS]
            offset = x + (i - (len(MODELS) - 1) / 2) * bar_w
            bars = ax.bar(offset, vals, width=bar_w, color=MODEL_COLORS[model],
                          label=model.capitalize(), edgecolor="white", linewidth=0.4)
            for bar, val in zip(bars, vals):
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.003,
                        f"{val:.3f}", ha="center", va="bottom", fontsize=6.5, rotation=90)

        ax.set_xticks(x)
        ax.set_xticklabels(METRIC_LABELS, fontsize=11)
        ax.set_title(label, fontsize=12)
        ax.set_ylim(0.70, 1.06)
        ax.yaxis.grid(True, linestyle="--", alpha=0.5)
        ax.set_axisbelow(True)

    axes[0].set_ylabel("Score", fontsize=11)
    handles = [mpatches.Patch(color=MODEL_COLORS[m], label=m.capitalize()) for m in MODELS]
    fig.legend(handles=handles, title="Model", loc="lower center",
               ncol=4, fontsize=10, title_fontsize=10, bbox_to_anchor=(0.5, -0.02))
    fig.suptitle("Precision / Recall / F1 by Agent and Model\n(23 test+new_test PXDs with METI data)",
                 fontsize=13, y=1.01)
    fig.tight_layout()
    out = OUT_DIR / "model_comparison_prf.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out}")


# ── Figure 3: radar / spider chart per metric, one series per model ──────────

def plot_radar():
    categories = [f"{a_short}\n{m}" for a_short in AGENT_LABELS for m in ["P", "R", "F1"]]
    N = len(categories)
    angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
    angles += angles[:1]  # close polygon

    fig, ax = plt.subplots(figsize=(9, 9), subplot_kw=dict(polar=True))

    for model in MODELS:
        values = [RESULTS[model][a][m] for a in AGENTS for m in METRICS]
        values += values[:1]
        ax.plot(angles, values, linewidth=2, label=model.capitalize(),
                color=MODEL_COLORS[model])
        ax.fill(angles, values, alpha=0.08, color=MODEL_COLORS[model])

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories, fontsize=9)
    ax.set_ylim(0.70, 1.0)
    ax.set_yticks([0.75, 0.80, 0.85, 0.90, 0.95, 1.0])
    ax.set_yticklabels(["0.75", "0.80", "0.85", "0.90", "0.95", "1.00"], fontsize=7)
    ax.set_title("Model Comparison — All Metrics\n(23 METI test+new_test PXDs)",
                 fontsize=13, pad=20)
    ax.legend(loc="upper right", bbox_to_anchor=(1.25, 1.1), fontsize=10)
    fig.tight_layout()
    out = OUT_DIR / "model_comparison_radar.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out}")


# ── Figure 4: summary table heatmap ─────────────────────────────────────────

def plot_heatmap():
    # rows = models, cols = agent×metric
    col_labels = [f"{a_short} {m}" for a_short in AGENT_LABELS for m in METRICS]
    data = np.array([
        [RESULTS[m][a][met] for a in AGENTS for met in METRICS]
        for m in MODELS
    ])

    fig, ax = plt.subplots(figsize=(13, 3.5))
    im = ax.imshow(data, cmap="RdYlGn", vmin=0.75, vmax=1.0, aspect="auto")

    ax.set_xticks(range(len(col_labels)))
    ax.set_xticklabels(col_labels, rotation=35, ha="right", fontsize=9)
    ax.set_yticks(range(len(MODELS)))
    ax.set_yticklabels([m.capitalize() for m in MODELS], fontsize=11)

    for r in range(len(MODELS)):
        for c in range(len(col_labels)):
            ax.text(c, r, f"{data[r, c]:.3f}", ha="center", va="center",
                    fontsize=8.5, color="black")

    plt.colorbar(im, ax=ax, fraction=0.02, pad=0.02)
    ax.set_title("Score Heatmap — All Models × Agents × Metrics\n(23 METI test+new_test PXDs)",
                 fontsize=12)
    fig.tight_layout()
    out = OUT_DIR / "model_comparison_heatmap.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out}")


if __name__ == "__main__":
    plot_f1_grouped()
    plot_prf_per_agent()
    plot_radar()
    plot_heatmap()
    print("All plots saved.")
