#!/usr/bin/env python3
"""
Reproduce pairwise inter-annotator agreement heatmaps.
Two panels: string (exact) matching and semantic (SciBERT) matching.
"""

import glob
import itertools
import os
import numpy as np
import pandas as pd
from collections import defaultdict
from sklearn.metrics import f1_score
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns

DATA_DIR = "/media/volume/bert_training_data_models/Intelligent-metadata-compilation/NLP_metadata_extraction/NLP_Trainingset_annotation/data/Select_27_Pubs/MultiHuman"
OUT_DIR  = os.path.dirname(os.path.abspath(__file__))  # benchmark_data/
os.makedirs(OUT_DIR, exist_ok=True)

ANNOTATORS = ["Ian", "Julian", "Karolina", "Magnus", "Maike", "Marta", "Samuel", "Tim", "Tine"]
ANON_LABELS = [f"A{i+1}" for i in range(len(ANNOTATORS))]

IGNORE_TYPES = {
    "TumorGrade", "DevelopmentalStage", "TumorStage", "FlowRateChromatogram",
    "AnatomicSiteTumor", "GrowthRate", "MaterialType", "Bait", "AssayName",
    "GeneticModification", "SampleTreatment", "SourceName", "Specimen",
    "SupplementaryFile", "TechnologyType", "OriginSiteDisease", "SyntheticPeptide"
}
MERGE = {"FractionationMethod": "Separation"}

SEMANTIC_THRESHOLD = 0.85


def parse_ann(path):
    entities = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split("\t")
            if not parts[0].startswith("T") or len(parts) < 3:
                continue
            label = parts[1].split()[0]
            text  = parts[2].lower().strip()
            if label in IGNORE_TYPES:
                continue
            label = MERGE.get(label, label)
            entities.add((label, text))
    return entities


def load_all_annotations():
    # {annotator: {doc_id: set of (label, text)}}
    data = defaultdict(dict)
    for ann in ANNOTATORS:
        for path in glob.glob(os.path.join(DATA_DIR, ann, "**", "*.ann"), recursive=True):
            doc_id = os.path.basename(path).replace(".ann", "")
            data[ann][doc_id] = parse_ann(path)
    return data


def pairwise_f1_exact(set1, set2):
    union = list(set1 | set2)
    if not union:
        return 0.0
    y1 = [1 if e in set1 else 0 for e in union]
    y2 = [1 if e in set2 else 0 for e in union]
    if sum(y1) == 0 or sum(y2) == 0:
        return 0.0
    return f1_score(y1, y2, zero_division=0)


def pairwise_f1_semantic(set1, set2, model, threshold=SEMANTIC_THRESHOLD):
    if not set1 or not set2:
        return 0.0
    texts1 = [f"{l}: {t}" for l, t in set1]
    texts2 = [f"{l}: {t}" for l, t in set2]
    emb1 = model.encode(texts1, convert_to_numpy=True, show_progress_bar=False)
    emb2 = model.encode(texts2, convert_to_numpy=True, show_progress_bar=False)
    sim = cosine_similarity(emb1, emb2)
    # greedy assignment: each entity in set1 matched to best in set2
    tp = sum(1 for row in sim if row.max() >= threshold)
    fp = len(set1) - tp
    fn = sum(1 for col in sim.T if col.max() < threshold)
    p  = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    r  = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    return 2 * p * r / (p + r) if (p + r) > 0 else 0.0


def build_matrix(data, score_fn):
    n = len(ANNOTATORS)
    mat = np.full((n, n), np.nan)
    for i, a1 in enumerate(ANNOTATORS):
        for j, a2 in enumerate(ANNOTATORS):
            if i == j:
                continue
            shared = set(data[a1]) & set(data[a2])
            if not shared:
                mat[i, j] = 0.0
                continue
            scores = []
            for doc in shared:
                s = score_fn(data[a1][doc], data[a2][doc])
                scores.append(s)
            mat[i, j] = np.mean(scores)
    return mat


def plot_heatmap(mat, title, ax):
    mask = np.eye(len(ANNOTATORS), dtype=bool)
    df = pd.DataFrame(mat, index=ANON_LABELS, columns=ANON_LABELS)
    sns.heatmap(
        df, ax=ax, mask=mask,
        cmap="Greens",
        vmin=0, vmax=1,
        annot=True, fmt=".2f", annot_kws={"size": 10},
        linewidths=0.5, linecolor="white",
        cbar_kws={"label": "Pairwise F1 Score"},
        square=True
    )
    ax.set_title(title, fontsize=13, fontweight="bold", pad=12)
    ax.set_xlabel("Annotator", fontsize=11)
    ax.set_ylabel("Annotator", fontsize=11)
    ax.tick_params(axis="x", rotation=45)
    ax.tick_params(axis="y", rotation=0)


# ── Main ──────────────────────────────────────────────────────────────────────
print("Loading annotations...")
data = load_all_annotations()
for ann in ANNOTATORS:
    print(f"  {ann}: {len(data[ann])} docs")

print("\nBuilding string (exact) matrix...")
exact_mat = build_matrix(data, pairwise_f1_exact)

print("\nLoading SciBERT model...")
model = SentenceTransformer("jordyvl/scibert_scivocab_uncased_sentence_transformer")

print("Building semantic matrix...")
sem_mat = build_matrix(data, lambda s1, s2: pairwise_f1_semantic(s1, s2, model))

# Save matrices (with anonymized labels)
pd.DataFrame(exact_mat, index=ANON_LABELS, columns=ANON_LABELS).to_csv(
    os.path.join(OUT_DIR, "iaa_exact_f1.csv"))
pd.DataFrame(sem_mat, index=ANON_LABELS, columns=ANON_LABELS).to_csv(
    os.path.join(OUT_DIR, "iaa_semantic_f1.csv"))

print("\nPlotting...")
fig, axes = plt.subplots(1, 2, figsize=(22, 9))
fig.suptitle("Pairwise Inter-Annotator Agreement", fontsize=15, fontweight="bold", y=1.01)

plot_heatmap(exact_mat, "String Matching (Exact)", axes[0])
plot_heatmap(sem_mat,   "Semantic Matching (SciBERT)", axes[1])

plt.tight_layout()
out = os.path.join(OUT_DIR, "iaa_pairwise_heatmaps.png")
plt.savefig(out, dpi=150, bbox_inches="tight")
print(f"Saved: {out}")

# Print summary
print(f"\nMean exact F1 (off-diagonal): {np.nanmean(exact_mat[~np.eye(len(ANNOTATORS), dtype=bool)]):.3f}")
print(f"Mean semantic F1 (off-diagonal): {np.nanmean(sem_mat[~np.eye(len(ANNOTATORS), dtype=bool)]):.3f}")
