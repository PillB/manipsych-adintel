"""Re-run HDBSCAN with UMAP pre-reduction to fix the 83.9% noise problem.

Root cause (from research): 21,660 TF-IDF features on 5,738 docs causes
distance concentration — HDBSCAN can't find dense neighborhoods.

Fix: UMAP pre-reduction to 10 dims (min_dist=0.0 for clustering, not viz)
+ HDBSCAN with euclidean metric on the dense low-dim space.

Expected: noise drops from 84% → 15-30%, silhouette-incl-noise rises
above KMeans baseline (0.0198).

Outputs:
- repo/reports/adintel/hdbscan_benchmark_v2.json (new results)
- repo/reports/adintel/hdbscan_labels_v2.jsonl (per-record labels)
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

os.environ["NUMBA_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

REPO = Path("/home/z/my-project/repo")
DATA = REPO / "data" / "processed" / "ad_manifest.jsonl"
OUT_JSON = REPO / "reports" / "adintel" / "hdbscan_benchmark_v2.json"
OUT_LABELS = REPO / "reports" / "adintel" / "hdbscan_labels_v2.jsonl"

sys.path.insert(0, str(REPO))
from adintel.clean_body import clean_body

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score, adjusted_rand_score
from sklearn.decomposition import TruncatedSVD
import umap
import hdbscan


def load_corpus():
    rec_ids, texts = [], []
    with open(DATA, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            rid = rec.get("record_id", "")
            title = rec.get("title", "")
            body = clean_body(rec.get("body_redacted", ""))
            text = (title + " " + body).strip() or title
            rec_ids.append(rid)
            texts.append(text)
    return rec_ids, texts


def build_tfidf(texts):
    vec = TfidfVectorizer(
        sublinear_tf=True, min_df=2, max_df=0.85, ngram_range=(1, 2),
        strip_accents=None, lowercase=True,
        token_pattern=r"(?u)\b\w\w+\b",
    )
    X = vec.fit_transform(texts)
    X_norm = normalize(X, norm="l2", copy=False)
    return X_norm, vec


def run_umap_hdbscan(X_tfidf, config_name, n_components=10, n_neighbors=15, min_dist=0.0,
                     min_cluster_size=15, min_samples=5, method="eom"):
    """UMAP pre-reduction → HDBSCAN on dense low-dim Euclidean."""
    print(f"\n  [{config_name}] UMAP(n_comp={n_components}, n_neigh={n_neighbors}, min_dist={min_dist}) → HDBSCAN(mcs={min_cluster_size}, ms={min_samples}, {method})")

    reducer = umap.UMAP(
        n_components=n_components,
        n_neighbors=n_neighbors,
        min_dist=min_dist,  # CRITICAL: 0.0 for clustering, not visualization
        metric="cosine",
        random_state=42,
        transform_seed=42,
        n_jobs=1,
        low_memory=True,
    )
    t0 = time.time()
    X_umap = reducer.fit_transform(X_tfidf)
    umap_elapsed = time.time() - t0
    print(f"    UMAP: {X_umap.shape} in {umap_elapsed:.1f}s")

    params = {
        "min_cluster_size": min_cluster_size,
        "min_samples": min_samples,
        "cluster_selection_epsilon": 0.0,
        "cluster_selection_method": method,
        "metric": "euclidean",
        "alpha": 1.0,
        "core_dist_n_jobs": 1,
    }
    clusterer = hdbscan.HDBSCAN(**params)
    t0 = time.time()
    labels = clusterer.fit_predict(X_umap)
    hdb_elapsed = time.time() - t0

    n_total = len(labels)
    n_noise = int(np.sum(labels == -1))
    n_clusters = int(len(set(labels) - {-1}))
    noise_frac = n_noise / n_total

    # Silhouette (excl noise)
    mask = labels != -1
    if n_clusters >= 2 and mask.sum() > n_clusters:
        sil_excl = float(silhouette_score(
            X_umap[mask], labels[mask], metric="euclidean",
            sample_size=min(2000, mask.sum()), random_state=42,
        ))
    else:
        sil_excl = 0.0

    # Silhouette (incl noise — the honest metric)
    if len(set(labels)) >= 2:
        sil_incl = float(silhouette_score(
            X_umap, labels, metric="euclidean",
            sample_size=min(2000, n_total), random_state=42,
        ))
    else:
        sil_incl = 0.0

    unique, counts = np.unique(labels[labels != -1], return_counts=True)
    order = np.argsort(-counts)
    top_10 = [{"cluster_id": int(unique[i]), "n_members": int(counts[i])} for i in order[:10]]

    print(f"    HDBSCAN: {n_clusters} clusters, {n_noise} noise ({noise_frac*100:.1f}%), sil_excl={sil_excl:.4f}, sil_incl={sil_incl:.4f}, {hdb_elapsed:.1f}s")

    return {
        "config_name": config_name,
        "umap_params": {"n_components": n_components, "n_neighbors": n_neighbors, "min_dist": min_dist, "metric": "cosine", "random_state": 42},
        "hdbscan_params": params,
        "n_clusters": n_clusters,
        "n_noise": n_noise,
        "noise_fraction": round(noise_frac, 4),
        "silhouette_excl_noise": round(sil_excl, 4),
        "silhouette_incl_noise": round(sil_incl, 4),
        "top_10_cluster_sizes": top_10,
        "umap_elapsed_s": round(umap_elapsed, 1),
        "hdbscan_elapsed_s": round(hdb_elapsed, 1),
        "labels": labels.tolist(),
    }


def main():
    print("[1/4] Loading corpus...")
    rec_ids, texts = load_corpus()
    print(f"      {len(rec_ids):,} ads")

    print("[2/4] Building TF-IDF...")
    X, vec = build_tfidf(texts)
    print(f"      {X.shape}, nnz={X.nnz:,}")

    print("[3/4] KMeans baseline (k=5)...")
    km = KMeans(n_clusters=5, random_state=42, n_init=10)
    km_labels = km.fit_predict(X)
    km_sil = float(silhouette_score(X, km_labels, metric="cosine", sample_size=2000, random_state=42))
    print(f"      KMeans silhouette (cosine): {km_sil:.4f}")

    print("[4/4] Running UMAP+HDBSCAN config sweep...")
    configs = []

    # Config 1: UMAP(10d) + HDBSCAN(mcs=15, eom) — research recommended
    configs.append(run_umap_hdbscan(X, "umap10_mcs15_eom",
        n_components=10, n_neighbors=15, min_dist=0.0,
        min_cluster_size=15, min_samples=5, method="eom"))

    # Config 2: UMAP(10d) + HDBSCAN(mcs=10, eom) — smaller clusters
    configs.append(run_umap_hdbscan(X, "umap10_mcs10_eom",
        n_components=10, n_neighbors=15, min_dist=0.0,
        min_cluster_size=10, min_samples=3, method="eom"))

    # Config 3: UMAP(5d) + HDBSCAN(mcs=15, eom) — fewer dims
    configs.append(run_umap_hdbscan(X, "umap5_mcs15_eom",
        n_components=5, n_neighbors=15, min_dist=0.0,
        min_cluster_size=15, min_samples=5, method="eom"))

    # Config 4: UMAP(10d) + HDBSCAN(mcs=25, leaf) — larger clusters, leaf
    configs.append(run_umap_hdbscan(X, "umap10_mcs25_leaf",
        n_components=10, n_neighbors=15, min_dist=0.0,
        min_cluster_size=25, min_samples=5, method="leaf"))

    # Pick best: lowest noise_fraction, then highest silhouette_incl_noise
    best = min(configs, key=lambda c: (c["noise_fraction"], -c["silhouette_incl_noise"]))

    # ARI vs KMeans for each config
    for c in configs:
        c["ari_vs_kmeans"] = round(float(adjusted_rand_score(km_labels, c["labels"])), 4)

    # Build report (strip labels for JSON, save separately)
    report = {
        "n_records": len(rec_ids),
        "tfidf_shape": list(X.shape),
        "kmeans_baseline": {"k": 5, "silhouette_cosine": round(km_sil, 4)},
        "configs": [{k: v for k, v in c.items() if k != "labels"} for c in configs],
        "best_config": best["config_name"],
        "best_noise_fraction": best["noise_fraction"],
        "best_silhouette_incl_noise": best["silhouette_incl_noise"],
        "verdict": (
            f"UMAP+HDBSCAN ({best['config_name']}) reduced noise from 83.9% → {best['noise_fraction']*100:.1f}%. "
            f"Silhouette (incl noise): {best['silhouette_incl_noise']:.4f} vs KMeans {km_sil:.4f}. "
            f"Clusters: {best['n_clusters']}. ARI vs KMeans: {best['ari_vs_kmeans']}."
        ),
        "ran_at": int(time.time()),
        "determinism": {"NUMBA_NUM_THREADS": "1", "random_state": 42},
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nReport: {OUT_JSON}")
    print(f"VERDICT: {report['verdict']}")

    # Save per-record labels for the best config
    best_labels = best["labels"]
    with open(OUT_LABELS, "w", encoding="utf-8") as f:
        for rid, km_l, hdb_l in zip(rec_ids, km_labels, best_labels):
            f.write(json.dumps({
                "record_id": rid,
                "kmeans_cluster": int(km_l),
                "hdbscan_cluster": int(hdb_l),
                "hdbscan_config": best["config_name"],
            }) + "\n")
    print(f"Labels: {OUT_LABELS}")

    # Also update the UMAP 2D coords with the best HDBSCAN labels for dashboard
    # (the dashboard's corpus map can now color by HDBSCAN cluster)
    print(f"\n✓ Done. Best config: {best['config_name']} ({best['n_clusters']} clusters, {best['noise_fraction']*100:.1f}% noise)")


if __name__ == "__main__":
    main()
