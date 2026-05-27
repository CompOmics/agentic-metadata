"""
Field-level coverage analysis: LLM-only vs METI-pipeline contribution,
grouped by agent. Aggregated across all 4 models × 23 METI PXDs (92 docs/field).

Output: benchmark_data/Final_results/test_new_test_meti_integrated/coverage_*.png
"""

import json
import collections
import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from core.field_mappings import AGENT_FIELDS

BASE     = Path("benchmark_data/Final_results/test_new_test_meti_integrated")
OUT_DIR  = BASE
MODELS   = ["llama", "claude", "gpt", "gemini"]

AGENTS = {
    "BiologicalAgent": "Biological Agent",
    "TechnicalAgent": "Technical Agent",
    "ExperimentalDesignAgent": "Experimental Design Agent",
}

# Display labels: strip verbose suffixes for readability
FIELD_LABELS = {
    "modification_site_fractions": "mod_site_fractions",
    "number_of_biological_replicates": "n_bio_replicates",
    "number_of_technical_replicates": "n_tech_replicates",
    "number_of_fractions": "n_fractions",
    "number_of_samples": "n_samples",
    "biological_replicate": "bio_replicate",
    "technical_replicate": "tech_replicate",
    "experimental_design": "exp_design",
    "anatomic_site_tumor": "anat_site_tumor",
    "fragmentation_method": "fragmentation",
    "fractionation_method": "fractionation",
    "alkylation_concentration": "alkyl_conc",
    "alkylation_reagent": "alkyl_reagent",
    "reduction_concentration": "reduc_conc",
    "reduction_reagent": "reduc_reagent",
    "ionization_type": "ionization",
    "acquisition_method": "acquisition",
    "enrichment_method": "enrichment",
    "collision_energy": "coll_energy",
    "quantification_method": "quant_method",
    "technology_type": "tech_type",
    "experiment_type": "exp_type",
    "factor_value": "factor_value",
    "sample_source": "sample_source",
    "material_type": "material_type",
    "disease_state": "disease",
    "cell_type": "cell_type",
    "cell_line": "cell_line",
    "developmental_stage": "dev_stage",
    "modification": "modification",
    "mass_analyzer": "mass_analyzer",
}

# Status groupings for the two-bar view
STATUS_COLORS = {
    "NULL":             "#D3D3D3",   # light grey — no value
    "LLM_ONLY":         "#4C72B0",   # blue — agent extracted, METI absent
    "AGREE":            "#55A868",   # green — both sources agree
    "DISAGREE":         "#C44E52",   # red — conflict
    "METI_ONLY":        "#DD8452",   # orange — METI-only (LLM missed)
    "RUNASSESSOR_ONLY": "#9467BD",   # purple — RunAssessor-only
}

STATUS_ORDER = ["NULL", "LLM_ONLY", "AGREE", "DISAGREE", "METI_ONLY", "RUNASSESSOR_ONLY"]
STATUS_LABELS = {
    "NULL":             "No value",
    "LLM_ONLY":         "LLM only",
    "AGREE":            "LLM + METI agree",
    "DISAGREE":         "LLM + METI conflict",
    "METI_ONLY":        "METI only (LLM missed)",
    "RUNASSESSOR_ONLY": "RunAssessor only",
}


def collect_statuses() -> dict[str, dict[str, collections.Counter]]:
    """Return {agent_dir_name: {field: Counter(status → count)}} aggregated over all models."""
    agg: dict[str, dict[str, collections.Counter]] = {a: collections.defaultdict(collections.Counter)
                                                       for a in AGENTS}
    for model in MODELS:
        int_dir = BASE / model / "IntegratedAgent"
        for agent_dir_name in AGENTS:
            agent_dir = int_dir / agent_dir_name
            if not agent_dir.exists():
                continue
            for jf in sorted(agent_dir.glob("*.json")):
                if jf.name == "ra_disagreements.json":
                    continue
                data = json.loads(jf.read_text())
                allowed = set(AGENT_FIELDS[agent_dir_name])
                for field, val in data.items():
                    if field not in allowed:
                        continue
                    if isinstance(val, dict):
                        resolved = val.get("resolved")
                        if resolved is None or str(resolved).lower() in (
                                "none", "null", "not applicable", "n/a", ""):
                            status = "NULL"
                        else:
                            status = val.get("status", "LLM_ONLY")
                    else:
                        status = "NULL"
                    agg[agent_dir_name][field][status] += 1
    return agg


def label(f: str) -> str:
    return FIELD_LABELS.get(f, f)


def plot_stacked_coverage(agg: dict):
    """One subplot per agent — stacked horizontal bar per field."""
    n_agents = len(AGENTS)
    total_docs = len(MODELS) * 23  # 92

    fig, axes = plt.subplots(1, n_agents, figsize=(20, 9),
                              gridspec_kw={"wspace": 0.45})

    for ax, (agent_dir_name, agent_label) in zip(axes, AGENTS.items()):
        field_counts = agg[agent_dir_name]
        fields = sorted(field_counts.keys())
        y = np.arange(len(fields))
        bar_h = 0.65

        lefts = np.zeros(len(fields))
        for status in STATUS_ORDER:
            vals = np.array([field_counts[f].get(status, 0) for f in fields], dtype=float)
            pct  = vals / total_docs * 100
            ax.barh(y, pct, left=lefts, height=bar_h,
                    color=STATUS_COLORS[status], label=STATUS_LABELS[status])
            # annotate non-trivial segments
            for i, (p, l) in enumerate(zip(pct, lefts)):
                if p >= 4:
                    ax.text(l + p / 2, i, f"{p:.0f}%",
                            ha="center", va="center", fontsize=6.5,
                            color="white" if p > 12 else "black", fontweight="bold")
            lefts += pct

        ax.set_yticks(y)
        ax.set_yticklabels([label(f) for f in fields], fontsize=8.5)
        ax.set_xlim(0, 100)
        ax.set_xlabel("% of documents (4 models × 23 PXDs = 92)", fontsize=8)
        ax.set_title(agent_label, fontsize=11, fontweight="bold", pad=8)
        ax.xaxis.grid(True, linestyle="--", alpha=0.4)
        ax.set_axisbelow(True)

    # Shared legend at bottom
    handles = [mpatches.Patch(color=STATUS_COLORS[s], label=STATUS_LABELS[s])
               for s in STATUS_ORDER]
    fig.legend(handles=handles, loc="lower center", ncol=3, fontsize=9,
               bbox_to_anchor=(0.5, -0.06), frameon=True)
    fig.suptitle("Field Coverage: LLM Agent vs METI Technical Pipeline\n"
                 "(23 test+new_test PXDs with METI data, all 4 models)",
                 fontsize=13, fontweight="bold", y=1.01)

    out = OUT_DIR / "coverage_stacked.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out}")


def plot_source_comparison(agg: dict):
    """
    Two-bar view per field:
      Bar 1 = % docs where LLM had ANY value  (LLM_ONLY + AGREE + DISAGREE)
      Bar 2 = % docs where METI had ANY value (METI_ONLY + AGREE + DISAGREE + RUNASSESSOR_ONLY)
    Grouped by agent, sorted by LLM coverage desc.
    """
    total_docs = len(MODELS) * 23

    fig, axes = plt.subplots(1, len(AGENTS), figsize=(20, 9),
                              gridspec_kw={"wspace": 0.45})

    for ax, (agent_dir_name, agent_label) in zip(axes, AGENTS.items()):
        field_counts = agg[agent_dir_name]

        llm_statuses  = {"LLM_ONLY", "AGREE", "DISAGREE"}
        meti_statuses = {"METI_ONLY", "AGREE", "DISAGREE", "RUNASSESSOR_ONLY"}

        rows = []
        for f, counts in field_counts.items():
            llm_cov  = sum(counts.get(s, 0) for s in llm_statuses)  / total_docs * 100
            meti_cov = sum(counts.get(s, 0) for s in meti_statuses) / total_docs * 100
            rows.append((f, llm_cov, meti_cov))
        rows.sort(key=lambda r: r[1], reverse=True)

        fields   = [r[0] for r in rows]
        llm_cov  = [r[1] for r in rows]
        meti_cov = [r[2] for r in rows]
        y = np.arange(len(fields))
        bar_h = 0.35

        ax.barh(y + bar_h / 2, llm_cov,  height=bar_h, color="#4C72B0",
                label="LLM agent coverage", alpha=0.9)
        ax.barh(y - bar_h / 2, meti_cov, height=bar_h, color="#DD8452",
                label="METI pipeline coverage", alpha=0.9)

        for i, (lv, mv) in enumerate(zip(llm_cov, meti_cov)):
            if lv > 3:
                ax.text(lv + 1, i + bar_h / 2, f"{lv:.0f}%", va="center",
                        fontsize=7, color="#4C72B0", fontweight="bold")
            if mv > 3:
                ax.text(mv + 1, i - bar_h / 2, f"{mv:.0f}%", va="center",
                        fontsize=7, color="#DD8452", fontweight="bold")

        ax.set_yticks(y)
        ax.set_yticklabels([label(f) for f in fields], fontsize=8.5)
        ax.set_xlim(0, 115)
        ax.set_xlabel("% documents with a value", fontsize=8)
        ax.set_title(agent_label, fontsize=11, fontweight="bold", pad=8)
        ax.xaxis.grid(True, linestyle="--", alpha=0.4)
        ax.set_axisbelow(True)
        ax.axvline(50, color="grey", linestyle=":", linewidth=0.8, alpha=0.6)

    handles = [
        mpatches.Patch(color="#4C72B0", label="LLM agent output"),
        mpatches.Patch(color="#DD8452", label="METI technical pipeline"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=2, fontsize=10,
               bbox_to_anchor=(0.5, -0.04), frameon=True)
    fig.suptitle("Coverage per Field: LLM Agent Output vs METI Technical Pipeline\n"
                 "(23 test+new_test PXDs with METI data, all 4 models — sorted by LLM coverage)",
                 fontsize=13, fontweight="bold", y=1.01)

    out = OUT_DIR / "coverage_llm_vs_meti.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out}")


if __name__ == "__main__":
    agg = collect_statuses()
    plot_stacked_coverage(agg)
    plot_source_comparison(agg)
    print("Done.")
