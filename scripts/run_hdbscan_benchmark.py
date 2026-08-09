"""Run real HDBSCAN benchmark on the ManiPsych corpus.

Goal: Replace the placeholder text "HDBSCAN: Not yet benchmarked"
in the v2 dashboard with real, measured metrics.

Inputs:
- repo/data/processed/ad_manifest.jsonl (5,738 records)
- repo/adintel/clean_body.py (strip "- Category - ID" suffix)

Outputs:
- repo/reports/adintel/hdbscan_benchmark.json
  {
    "n_records": 5738,
    "kmeans_baseline": {"k": 5, "silhouette": 0.0097, "stability_ari": 0.40},
    "hdbscan": {
      "params": {...},
      "n_clusters": N,
      "n_noise": M,
      "noise_fraction": 0.XX,
      "silhouette_excl_noise": 0.XX,
      "silhouette_incl_noise": 0.XX,
      "ari_vs_kmeans": 0.XX,
      "top_10_cluster_sizes": [...],
      "elapsed_ms": N
    },
    "verdict": "..."  # human-readable summary
  }

Best-practice params (per audit/solarize-rebuild/round5/research_best_in_class.md):
  min_cluster_size=8, min_samples=3, cluster_selection_epsilon=0.05,
  cluster_selection_method='leaf', metric='cosine', prediction_data=True

Determinism: random_state=42, NUMBA_NUM_THREADS=1, n_jobs=1
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# Determinism — set BEFORE importing numba-backed libs
os.environ["NUMBA_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

REPO = Path("/home/z/my-project/repo")
DATA = REPO / "data" / "processed" / "ad_manifest.jsonl"
OUT = REPO / "reports" / "adintel" / "hdbscan_benchmark.json"

# Add adintel to path
sys.path.insert(0, str(REPO))
from adintel.clean_body import clean_body  # noqa: E402

import numpy as np  # noqa: E402
from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: E402
from sklearn.preprocessing import normalize  # noqa: E402
from sklearn.cluster import KMeans  # noqa: E402
from sklearn.metrics import silhouette_score, adjusted_rand_score  # noqa: E402
import hdbscan  # noqa: E402


def load_corpus():
    """Load all 5,738 ads and return (record_ids, texts)."""
    rec_ids = []
    texts = []
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
            body_raw = rec.get("body_redacted", "")
            body_clean = clean_body(body_raw)
            # Combine title + cleaned body for clustering
            text = (title + " " + body_clean).strip()
            if not text:
                text = title  # fall back to title-only if body is empty
            rec_ids.append(rid)
            texts.append(text)
    return rec_ids, texts


def build_tfidf(texts):
    """Build L2-normalized TF-IDF matrix per research recommendations."""
    vec = TfidfVectorizer(
        sublinear_tf=True,
        min_df=2,
        max_df=0.85,
        ngram_range=(1, 2),
        strip_accents=None,  # preserve Spanish accents
        lowercase=True,
        token_pattern=r"(?u)\b\w\w+\b",
    )
    X = vec.fit_transform(texts)
    X_norm = normalize(X, norm="l2", copy=False)
    return X_norm, vec


def run_kmeans_baseline(X, k=5, random_state=42):
    """Re-run the KMeans baseline for direct comparison."""
    km = KMeans(n_clusters=k, random_state=random_state, n_init=10)
    labels = km.fit_predict(X)
    # Silhouette on a sample for speed
    n = X.shape[0]
    sample_size = min(2000, n)
    sil = silhouette_score(X, labels, metric="cosine", sample_size=sample_size, random_state=random_state)
    return labels, float(sil)


def run_hdbscan(X):
    """Run HDBSCAN with research-recommended params."""
    params = {
        "min_cluster_size": 8,
        "min_samples": 3,
        "cluster_selection_epsilon": 0.05,
        "cluster_selection_method": "leaf",
        "metric": "cosine",
        "alpha": 1.0,
        "core_dist_n_jobs": 1,
    }
    clusterer = hdbscan.HDBSCAN(**params)
    t0 = time.time()
    labels = clusterer.fit_predict(X)
    elapsed_ms = (time.time() - t0) * 1000.0

    n_total = len(labels)
    n_noise = int(np.sum(labels == -1))
    n_clusters = int(len(set(labels) - {-1}))

    # Silhouette (excluding noise) — uses cosine = 1 - dot for L2-normed rows
    mask_inlier = labels != -1
    if n_clusters >= 2 and mask_inlier.sum() > n_clusters:
        sil_excl = float(silhouette_score(
            X[mask_inlier], labels[mask_inlier],
            metric="cosine", sample_size=min(2000, mask_inlier.sum()),
            random_state=42,
        ))
    else:
        sil_excl = 0.0

    # Silhouette including noise (treats noise as its own cluster — usually ugly)
    if len(set(labels)) >= 2:
        sil_incl = float(silhouette_score(
            X, labels, metric="cosine",
            sample_size=min(2000, n_total), random_state=42,
        ))
    else:
        sil_incl = 0.0

    # Top-10 cluster sizes
    unique, counts = np.unique(labels[labels != -1], return_counts=True)
    order = np.argsort(-counts)
    top_10 = [
        {"cluster_id": int(unique[i]), "n_members": int(counts[i])}
        for i in order[:10]
    ]

    return {
        "params": params,
        "n_clusters": n_clusters,
        "n_noise": n_noise,
        "noise_fraction": round(n_noise / n_total, 4),
        "silhouette_excl_noise": round(sil_excl, 4),
        "silhouette_incl_noise": round(sil_incl, 4),
        "top_10_cluster_sizes": top_10,
        "elapsed_ms": round(elapsed_ms, 1),
        "labels": labels.tolist(),  # full labels for ARI / cross-reference
    }


def main():
    print("[1/5] Loading corpus...")
    rec_ids, texts = load_corpus()
    print(f"      Loaded {len(rec_ids):,} ads")

    print("[2/5] Building TF-IDF (sublinear, min_df=2, max_df=0.85, 1-2 grams, L2-normalized)...")
    X, vec = build_tfidf(texts)
    print(f"      Matrix shape: {X.shape}, nnz: {X.nnz:,}")

    print("[3/5] Running KMeans baseline (k=5, random_state=42)...")
    km_labels, km_sil = run_kmeans_baseline(X)
    print(f"      KMeans silhouette (cosine): {km_sil:.4f}")

    print("[4/5] Running HDBSCAN — primary config (min_cluster_size=8, leaf)...")
    hdb_primary = run_hdbscan(X)
    print(f"      Primary: {hdb_primary['n_clusters']} clusters, "
          f"{hdb_primary['n_noise']} noise ({hdb_primary['noise_fraction']*100:.1f}%), "
          f"silhouette (excl noise): {hdb_primary['silhouette_excl_noise']:.4f}, "
          f"elapsed: {hdb_primary['elapsed_ms']:.0f}ms")

    print("[5/5] Running HDBSCAN — fallback config (min_cluster_size=20, eom)...")
    hdb_fallback = run_hdbscan(X)
    # Override params for fallback
    fallback_params = {
        "min_cluster_size": 20,
        "min_samples": 5,
        "cluster_selection_epsilon": 0.1,
        "cluster_selection_method": "eom",
        "metric": "cosine",
        "alpha": 1.0,
        "core_dist_n_jobs": 1,
    }
    clusterer_fb = hdbscan.HDBSCAN(**fallback_params)
    t0 = time.time()
    fb_labels = clusterer_fb.fit_predict(X)
    fb_elapsed = (time.time() - t0) * 1000.0
    fb_n_noise = int(np.sum(fb_labels == -1))
    fb_n_clusters = int(len(set(fb_labels) - {-1}))
    fb_mask = fb_labels != -1
    if fb_n_clusters >= 2 and fb_mask.sum() > fb_n_clusters:
        fb_sil = float(silhouette_score(
            X[fb_mask], fb_labels[fb_mask], metric="cosine",
            sample_size=min(2000, fb_mask.sum()), random_state=42,
        ))
    else:
        fb_sil = 0.0
    fb_unique, fb_counts = np.unique(fb_labels[fb_labels != -1], return_counts=True)
    fb_order = np.argsort(-fb_counts)
    fb_top = [
        {"cluster_id": int(fb_unique[i]), "n_members": int(fb_counts[i])}
        for i in fb_order[:10]
    ]
    hdb_fallback = {
        "params": fallback_params,
        "n_clusters": fb_n_clusters,
        "n_noise": fb_n_noise,
        "noise_fraction": round(fb_n_noise / len(fb_labels), 4),
        "silhouette_excl_noise": round(fb_sil, 4),
        "top_10_cluster_sizes": fb_top,
        "elapsed_ms": round(fb_elapsed, 1),
    }
    print(f"      Fallback: {fb_n_clusters} clusters, "
          f"{fb_n_noise} noise ({fb_n_noise/len(fb_labels)*100:.1f}%), "
          f"silhouette (excl noise): {fb_sil:.4f}, "
          f"elapsed: {fb_elapsed:.0f}ms")

    # ARI vs KMeans (primary config)
    ari_primary = float(adjusted_rand_score(km_labels, hdb_primary["labels"]))
    ari_fallback = float(adjusted_rand_score(km_labels, fb_labels))
    print(f"      ARI (KMeans vs HDBSCAN-primary): {ari_primary:.4f}")
    print(f"      ARI (KMeans vs HDBSCAN-fallback): {ari_fallback:.4f}")

    # Pick the better config for the verdict
    if hdb_primary["silhouette_excl_noise"] >= hdb_fallback["silhouette_excl_noise"]:
        best = "primary"
        best_hdb = hdb_primary
    else:
        best = "fallback"
        best_hdb = hdb_fallback

    # Verdict
    if best_hdb["silhouette_excl_noise"] > km_sil:
        verdict = (
            f"HDBSCAN ({best} config) outperforms KMeans on silhouette "
            f"({best_hdb['silhouette_excl_noise']:.4f} vs {km_sil:.4f}, excluding noise). "
            f"Recommended as primary clusterer. Noise fraction {best_hdb['noise_fraction']*100:.1f}% "
            f"is a corpus finding worth reporting."
        )
    elif best_hdb["silhouette_excl_noise"] > 0:
        verdict = (
            f"HDBSCAN silhouette ({best_hdb['silhouette_excl_noise']:.4f}, excl noise) is comparable "
            f"to KMeans ({km_sil:.4f}). HDBSCAN's advantage is interpretable noise handling "
            f"({best_hdb['noise_fraction']*100:.1f}% flagged), not silhouette. Recommend reporting both."
        )
    else:
        verdict = (
            f"HDBSCAN produced {best_hdb['n_clusters']} clusters + {best_hdb['noise_fraction']*100:.1f}% noise; "
            f"silhouette not meaningful (n_clusters<2 or single cluster). "
            f"Tune min_cluster_size or use 'eom' method. KMeans silhouette was {km_sil:.4f}."
        )

    # Drop the full labels list before saving (it's huge)
    hdb_primary_save = {k: v for k, v in hdb_primary.items() if k != "labels"}

    report = {
        "n_records": len(rec_ids),
        "tfidf_shape": list(X.shape),
        "tfidf_nnz": int(X.nnz),
        "kmeans_baseline": {
            "k": 5,
            "silhouette_cosine": round(km_sil, 4),
            "random_state": 42,
        },
        "hdbscan_primary": hdb_primary_save,
        "hdbscan_fallback": hdb_fallback,
        "best_config": best,
        "ari_kmeans_vs_primary": round(ari_primary, 4),
        "ari_kmeans_vs_fallback": round(ari_fallback, 4),
        "verdict": verdict,
        "ran_at": int(time.time()),
        "determinism": {
            "NUMBA_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "random_state": 42,
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nReport saved to: {OUT}")
    print(f"\nVERDICT: {verdict}")

    # Also save the per-record labels for use in the dashboard
    labels_out = REPO / "reports" / "adintel" / "hdbscan_labels.jsonl"
    with open(labels_out, "w", encoding="utf-8") as f:
        for rid, km_l, hdb_l, fb_l in zip(rec_ids, km_labels, hdb_primary["labels"], fb_labels):
            f.write(json.dumps({
                "record_id": rid,
                "kmeans_cluster": int(km_l),
                "hdbscan_primary_cluster": int(hdb_l),
                "hdbscan_fallback_cluster": int(fb_l),
            }) + "\n")
    print(f"Per-record labels saved to: {labels_out}")


if __name__ == "__main__":
    main()
