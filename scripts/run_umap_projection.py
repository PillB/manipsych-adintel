"""Compute a real UMAP 2D projection of the ManiPsych corpus.

Goal: Replace the fake "radial proxy" UMAP scatter in the v2 dashboard
with a real, deterministic UMAP projection.

Inputs:
- repo/data/processed/ad_manifest.jsonl (5,738 records)
- repo/adintel/clean_body.py (strip suffix)

Outputs:
- repo/reports/adintel/umap_coords.json  (5738 × [x, y] — full, for fetch)
- repo/reports/adintel/umap_coords.b64   (Float32 packed base64, ~80KB, for inline)
- repo/reports/adintel/umap_coords_sample.json (50 records, for inline seed)

Best-practice params (per audit/solarize-rebuild/round5/research_best_in_class.md):
  n_neighbors=12, min_dist=0.1, n_components=2, metric='cosine',
  random_state=42, transform_seed=42, n_jobs=1, init='spectral'

Determinism: NUMBA_NUM_THREADS=1, n_jobs=1, random_state=42, transform_seed=42
"""
from __future__ import annotations

import base64
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
OUT_DIR = REPO / "reports" / "adintel"
OUT_JSON = OUT_DIR / "umap_coords.json"
OUT_B64 = OUT_DIR / "umap_coords.b64"
OUT_SAMPLE = OUT_DIR / "umap_coords_sample.json"
OUT_META = OUT_DIR / "umap_projection_meta.json"

sys.path.insert(0, str(REPO))
from adintel.clean_body import clean_body  # noqa: E402

import numpy as np  # noqa: E402
from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: E402
from sklearn.preprocessing import normalize  # noqa: E402
import umap  # noqa: E402


def load_corpus():
    rec_ids = []
    texts = []
    platforms = []
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
            text = (title + " " + body_clean).strip()
            if not text:
                text = title
            rec_ids.append(rid)
            texts.append(text)
            platforms.append(rec.get("source_platform", "Unknown"))
    return rec_ids, texts, platforms


def build_tfidf(texts):
    vec = TfidfVectorizer(
        sublinear_tf=True, min_df=2, max_df=0.85, ngram_range=(1, 2),
        strip_accents=None, lowercase=True,
        token_pattern=r"(?u)\b\w\w+\b",
    )
    X = vec.fit_transform(texts)
    X_norm = normalize(X, norm="l2", copy=False)
    return X_norm, vec


def run_umap(X):
    params = {
        "n_neighbors": 12,
        "min_dist": 0.1,
        "n_components": 2,
        "metric": "cosine",
        "init": "spectral",
        "random_state": 42,
        "transform_seed": 42,
        "n_jobs": 1,
        "low_memory": True,
        "verbose": False,
    }
    reducer = umap.UMAP(**params)
    t0 = time.time()
    coords = reducer.fit_transform(X)
    elapsed = time.time() - t0
    return coords, params, elapsed


def main():
    print("[1/4] Loading corpus...")
    rec_ids, texts, platforms = load_corpus()
    print(f"      Loaded {len(rec_ids):,} ads")

    print("[2/4] Building TF-IDF (sublinear, min_df=2, max_df=0.85, 1-2 grams, L2-normalized)...")
    X, vec = build_tfidf(texts)
    print(f"      Matrix shape: {X.shape}, nnz: {X.nnz:,}")

    print("[3/4] Running UMAP (n_neighbors=12, min_dist=0.1, cosine, random_state=42)...")
    coords, params, elapsed = run_umap(X)
    print(f"      UMAP shape: {coords.shape}, elapsed: {elapsed:.1f}s")
    print(f"      Coord range: x=[{coords[:,0].min():.2f}, {coords[:,0].max():.2f}], "
          f"y=[{coords[:,1].min():.2f}, {coords[:,1].max():.2f}]")

    # Normalize coords to a [0, 1] box for stable rendering
    x_min, x_max = coords[:, 0].min(), coords[:, 0].max()
    y_min, y_max = coords[:, 1].min(), coords[:, 1].max()
    coords_norm = np.empty_like(coords, dtype=np.float32)
    coords_norm[:, 0] = (coords[:, 0] - x_min) / (x_max - x_min + 1e-9)
    coords_norm[:, 1] = (coords[:, 1] - y_min) / (y_max - y_min + 1e-9)

    print("[4/4] Saving outputs...")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Save full coords as JSON (for fetch / debug)
    full_json = {
        "n_records": len(rec_ids),
        "params": params,
        "coord_range_raw": {
            "x_min": float(x_min), "x_max": float(x_max),
            "y_min": float(y_min), "y_max": float(y_max),
        },
        "coords_normalized": [
            {"record_id": rid, "platform": p, "x": float(coords_norm[i, 0]), "y": float(coords_norm[i, 1])}
            for i, (rid, p) in enumerate(zip(rec_ids, platforms))
        ],
        "elapsed_seconds": round(elapsed, 2),
        "ran_at": int(time.time()),
        "determinism": {
            "NUMBA_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "random_state": 42,
            "transform_seed": 42,
        },
    }
    OUT_JSON.write_text(json.dumps(full_json, ensure_ascii=False))
    print(f"      Full JSON: {OUT_JSON} ({OUT_JSON.stat().st_size / 1024:.1f} KB)")

    # Save packed Float32 base64 (for inline embedding in dashboard)
    packed = coords_norm.astype(np.float32).tobytes()
    b64 = base64.b64encode(packed).decode("ascii")
    OUT_B64.write_text(b64)
    print(f"      Packed Float32 b64: {OUT_B64} ({OUT_B64.stat().st_size / 1024:.1f} KB)")

    # Save 50-record sample (for inline seed in dashboard)
    # Pick a stratified sample: 10 per KMeans cluster (computed inline for sampling)
    from sklearn.cluster import KMeans
    km = KMeans(n_clusters=5, random_state=42, n_init=10)
    km_labels = km.fit_predict(X)
    sample_idx = []
    for cluster_id in range(5):
        cluster_members = np.where(km_labels == cluster_id)[0]
        if len(cluster_members) > 0:
            chosen = np.random.RandomState(42).choice(
                cluster_members, size=min(10, len(cluster_members)), replace=False
            )
            sample_idx.extend(chosen.tolist())
    sample_idx = sorted(set(sample_idx))[:50]
    sample_records = []
    for i in sample_idx:
        sample_records.append({
            "r": rec_ids[i],
            "x": float(coords_norm[i, 0]),
            "y": float(coords_norm[i, 1]),
            "p": platforms[i],
            "c": int(km_labels[i]),
        })
    OUT_SAMPLE.write_text(json.dumps(sample_records, ensure_ascii=False))
    print(f"      50-record sample: {OUT_SAMPLE} ({OUT_SAMPLE.stat().st_size / 1024:.1f} KB)")

    # Save metadata
    meta = {
        "n_records": len(rec_ids),
        "params": params,
        "tfidf_shape": list(X.shape),
        "tfidf_nnz": int(X.nnz),
        "coord_range_raw": {
            "x_min": float(x_min), "x_max": float(x_max),
            "y_min": float(y_min), "y_max": float(y_max),
        },
        "coord_range_normalized": {"x": [0.0, 1.0], "y": [0.0, 1.0]},
        "elapsed_seconds": round(elapsed, 2),
        "ran_at": int(time.time()),
        "determinism": {
            "NUMBA_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "random_state": 42,
            "transform_seed": 42,
        },
        "files": {
            "full_json": str(OUT_JSON.relative_to(REPO)),
            "packed_b64": str(OUT_B64.relative_to(REPO)),
            "sample_50": str(OUT_SAMPLE.relative_to(REPO)),
        },
    }
    OUT_META.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    print(f"      Metadata: {OUT_META}")

    print("\nDone. UMAP projection computed and saved.")


if __name__ == "__main__":
    main()
