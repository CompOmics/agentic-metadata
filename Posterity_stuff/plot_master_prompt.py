"""
Visualize master_prompt BRAT annotation results across the 30-PXD test set.
Saves plots to Posterity_stuff/outputs/plots/
"""

from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

# ---------------------------------------------------------------------------
ANN_DIR   = Path(__file__).parent / "outputs" / "ann_files"
PLOTS_DIR = Path(__file__).parent / "outputs" / "plots"
PLOTS_DIR.mkdir(parents=True, exist_ok=True)

# Predefined valid entity types from master_prompt
VALID_TYPES = {
    "AcquisitionMethod", "Age", "AlkylationReagent", "AnatomicSiteTumor",
    "AncestryCategory", "AssayName", "Bait", "BMI", "BiologicalReplicate",
    "CellLine", "CellPart", "CellType", "CleavageAgent", "CollisionEnergy",
    "Compound", "ConcentrationOfCompound", "Depletion", "DevelopmentalStage",
    "Disease", "DiseaseTreatment", "EnrichmentMethod", "Experiment",
    "FactorValue", "FlowRateChromatogram", "FractionationMethod",
    "FractionIdentifier", "FractionationFraction", "FragmentationMethod",
    "FragmentMassTolerance", "GeneticModification", "Genotype", "GradientTime",
    "GrowthRate", "Instrument", "IonizationType", "Label", "MaterialType",
    "Modification", "MS2MassAnalyzer", "NumberOfMissedCleavages",
    "NumberOfFractions", "NumberOfTechnicalReplicates", "NumberOfSamples",
    "NumberOfBiologicalReplicates", "Organism", "OrganismPart",
    "OriginSiteDisease", "PrecursorMassTolerance", "PooledSample",
    "ReductionReagent", "SamplingTime", "SampleTreatment", "Separation",
    "Sex", "SourceName", "Specimen", "SpikedCompound", "Staining", "Strain",
    "SupplementaryFile", "SyntheticPeptide", "TumorCellularity", "TumorGrade",
    "TumorSize", "TumorSite", "TumorStage", "Time", "Temperature",
    "Treatment", "TechnicalReplicate",
}

# Broad category groupings for valid types
CATEGORIES = {
    "Biological": {"Organism", "OrganismPart", "Tissue", "CellLine", "CellType",
                   "CellPart", "Disease", "Strain", "Sex", "Age", "BMI",
                   "DevelopmentalStage", "AncestryCategory", "MaterialType",
                   "Specimen", "GeneticModification", "Genotype"},
    "Technical":  {"Instrument", "CleavageAgent", "AlkylationReagent",
                   "ReductionReagent", "EnrichmentMethod", "FractionationMethod",
                   "FractionIdentifier", "FractionationFraction", "Separation",
                   "Label", "Modification", "FragmentationMethod",
                   "AcquisitionMethod", "MS2MassAnalyzer", "IonizationType",
                   "CollisionEnergy", "PrecursorMassTolerance",
                   "FragmentMassTolerance", "GradientTime", "FlowRateChromatogram",
                   "NumberOfMissedCleavages", "NumberOfFractions",
                   "ConcentrationOfCompound", "Compound", "SpikedCompound",
                   "SyntheticPeptide", "Depletion", "Bait"},
    "Experimental": {"BiologicalReplicate", "TechnicalReplicate",
                     "NumberOfBiologicalReplicates", "NumberOfTechnicalReplicates",
                     "NumberOfSamples", "FactorValue", "AssayName", "Experiment",
                     "SourceName", "PooledSample", "Treatment", "DiseaseTreatment",
                     "SampleTreatment", "SamplingTime", "Time", "Temperature",
                     "GrowthRate", "Staining"},
    "Tumor":      {"AnatomicSiteTumor", "OriginSiteDisease", "TumorSite",
                   "TumorStage", "TumorGrade", "TumorSize", "TumorCellularity"},
}

def load_annotations():
    per_pxd = {}
    for f in sorted(ANN_DIR.glob("*.ann")):
        annotations = []
        for line in f.read_text().strip().splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                etype = parts[1].split()[0]
                span  = parts[2] if len(parts) >= 3 else ""
                annotations.append((etype, span))
        per_pxd[f.stem] = annotations
    return per_pxd


def load_agent_counts(pxds, model="llama"):
    """Count non-unknown fields across all 3 agents per PXD."""
    import json
    base = Path("/media/volume/bert_training_data_models/llama/codes/extraction_framework"
                f"/benchmark_data/Testing_final/test_set/{model}")
    agents = {
        "BiologicalAgent": "biological",
        "TechnicalAgent": "technical",
        "ExperimentalDesignAgent": "experimental",
    }
    counts = {}
    for pxd in pxds:
        total = 0
        for agent_dir, label in agents.items():
            f = base / agent_dir / f"{pxd}_manuscript_{label}_{model}.json"
            if f.exists():
                d = json.loads(f.read_text())
                total += sum(
                    1 for k, v in d.items()
                    if k not in ("_confidence", "_hallucination_flags")
                    and isinstance(v, list) and len(v) >= 1
                    and v[0] not in ("unknown", "")
                )
        counts[pxd] = total
    return counts


def load_ann_counts(suffix=""):
    ann_dir = ANN_DIR.parent / f"ann_files{suffix}"
    return {f.stem: len(f.read_text().strip().splitlines())
            for f in sorted(ann_dir.glob("*.ann"))}


def plot_annotations_per_pxd(per_pxd):
    pxds = sorted(per_pxd.keys())

    llama_master = [len(per_pxd[p]) for p in pxds]
    gpt_master   = [load_ann_counts("_gpt").get(p, 0) for p in pxds]
    llama_agents = [load_agent_counts(pxds, "llama").get(p, 0) for p in pxds]
    gpt_agents   = [load_agent_counts(pxds, "gpt").get(p, 0) for p in pxds]

    x = np.arange(len(pxds))
    width = 0.2

    # ── master_prompt Llama vs GPT (standalone) ───────────────────────────
    fig, ax = plt.subplots(figsize=(16, 5))
    ax.bar(x - width/2, llama_master, width, color="#4393c3", label="master_prompt — Llama", edgecolor="white", linewidth=0.3)
    ax.bar(x + width/2, gpt_master,   width, color="#2166ac", label="master_prompt — GPT",  edgecolor="white", linewidth=0.3)
    for i, c in enumerate(llama_master):
        if c == 0:
            ax.bar(x[i] - width/2, max(gpt_master)*0.02, width, color="#d73027", edgecolor="white", linewidth=0.3)
    ax.axhline(np.mean(llama_master), color="#4393c3", linestyle="--", linewidth=1, alpha=0.6)
    ax.axhline(np.mean(gpt_master),   color="#2166ac", linestyle="--", linewidth=1, alpha=0.6)
    ax.annotate(f"Llama mean: {np.mean(llama_master):.0f}", xy=(0.01, np.mean(llama_master)),
                xycoords=("axes fraction", "data"), fontsize=8, color="#4393c3", va="bottom")
    ax.annotate(f"GPT mean: {np.mean(gpt_master):.0f}", xy=(0.01, np.mean(gpt_master)),
                xycoords=("axes fraction", "data"), fontsize=8, color="#2166ac", va="bottom")
    ax.set_xticks(x)
    ax.set_xticklabels(pxds, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("Annotation spans")
    ax.set_title("master_prompt: Llama vs GPT — BRAT annotation counts (30-PXD test set)", fontweight="bold")
    ax.legend(fontsize=9)
    plt.tight_layout()
    out = PLOTS_DIR / "annotations_per_pxd.png"
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"Saved: {out}")

    # ── Agents Llama vs GPT (standalone) ──────────────────────────────────
    fig, ax = plt.subplots(figsize=(16, 5))
    ax.bar(x - width/2, llama_agents, width, color="#f4a582", label="Agents — Llama", edgecolor="white", linewidth=0.3)
    ax.bar(x + width/2, gpt_agents,   width, color="#d6604d", label="Agents — GPT",   edgecolor="white", linewidth=0.3)
    ax.axhline(np.mean(llama_agents), color="#f4a582", linestyle="--", linewidth=1, alpha=0.6)
    ax.axhline(np.mean(gpt_agents),   color="#d6604d", linestyle="--", linewidth=1, alpha=0.6)
    ax.annotate(f"Llama mean: {np.mean(llama_agents):.0f}", xy=(0.01, np.mean(llama_agents)),
                xycoords=("axes fraction", "data"), fontsize=8, color="#f4a582", va="bottom")
    ax.annotate(f"GPT mean: {np.mean(gpt_agents):.0f}", xy=(0.01, np.mean(gpt_agents)),
                xycoords=("axes fraction", "data"), fontsize=8, color="#d6604d", va="bottom")
    ax.set_xticks(x)
    ax.set_xticklabels(pxds, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("Non-unknown fields")
    ax.set_title("Agents (Biological + Technical + Experimental): Llama vs GPT", fontweight="bold")
    ax.legend(fontsize=9)
    plt.tight_layout()
    out = PLOTS_DIR / "agents_per_pxd.png"
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"Saved: {out}")


def plot_entity_type_frequency(per_pxd):
    all_types = Counter()
    for anns in per_pxd.values():
        for etype, _ in anns:
            all_types[etype] += 1

    # Separate valid vs hallucinated
    valid   = {k: v for k, v in all_types.items() if k in VALID_TYPES}
    invalid = {k: v for k, v in all_types.items() if k not in VALID_TYPES}

    # Top 25 valid + all invalid
    top_valid   = sorted(valid.items(), key=lambda x: -x[1])[:25]
    top_invalid = sorted(invalid.items(), key=lambda x: -x[1])

    labels = [x[0] for x in top_valid] + [x[0] for x in top_invalid]
    values = [x[1] for x in top_valid] + [x[1] for x in top_invalid]
    colors = ["#4393c3"] * len(top_valid) + ["#d73027"] * len(top_invalid)

    fig, ax = plt.subplots(figsize=(14, 6))
    ax.barh(range(len(labels)), values, color=colors, edgecolor="white", linewidth=0.5)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("Count across all 30 manuscripts")
    ax.set_title("master_prompt: Entity type frequency — valid vs hallucinated types", fontweight="bold")

    valid_patch   = mpatches.Patch(color="#4393c3", label=f"Valid types ({len(valid)} unique)")
    invalid_patch = mpatches.Patch(color="#d73027", label=f"Hallucinated types ({len(invalid)} unique)")
    ax.legend(handles=[valid_patch, invalid_patch])

    # Divider line
    ax.axhline(y=len(top_valid) - 0.5, color="black", linewidth=1.5, linestyle="--")

    plt.tight_layout()
    out = PLOTS_DIR / "entity_type_frequency.png"
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"Saved: {out}")


def plot_category_breakdown(per_pxd):
    """Stacked bar: for each PXD, how many annotations fall into each category."""
    pxds = sorted(per_pxd.keys())
    cat_names = list(CATEGORIES.keys()) + ["Other/Hallucinated"]
    cat_colors = ["#4393c3", "#f4a582", "#92c5de", "#b2182b", "#d9d9d9"]

    data = {c: [] for c in cat_names}
    for pxd in pxds:
        counts = {c: 0 for c in cat_names}
        for etype, _ in per_pxd[pxd]:
            placed = False
            for cat, members in CATEGORIES.items():
                if etype in members:
                    counts[cat] += 1
                    placed = True
                    break
            if not placed:
                counts["Other/Hallucinated"] += 1
        for c in cat_names:
            data[c].append(counts[c])

    fig, ax = plt.subplots(figsize=(14, 5))
    bottoms = np.zeros(len(pxds))
    for cat, color in zip(cat_names, cat_colors):
        vals = np.array(data[cat])
        ax.bar(range(len(pxds)), vals, bottom=bottoms, color=color,
               label=cat, edgecolor="white", linewidth=0.3)
        bottoms += vals

    ax.set_xticks(range(len(pxds)))
    ax.set_xticklabels(pxds, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("Annotations")
    ax.set_title("master_prompt: Annotation category breakdown per manuscript", fontweight="bold")
    ax.legend(loc="upper right", fontsize=8)
    plt.tight_layout()
    out = PLOTS_DIR / "category_breakdown.png"
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"Saved: {out}")


def main():
    per_pxd = load_annotations()
    total = sum(len(v) for v in per_pxd.values())
    print(f"Loaded {len(per_pxd)} PXDs, {total} total annotations")

    plot_annotations_per_pxd(per_pxd)
    plot_entity_type_frequency(per_pxd)
    plot_category_breakdown(per_pxd)
    print("Done.")


if __name__ == "__main__":
    main()
