"""Compute t-SNE 2D projection of the ManiPsych corpus for comparison with UMAP.

t-SNE (t-Distributed Stochastic Neighbor Embedding) preserves local structure
differently than UMAP — better at separating clusters visually but slower and
non-deterministic without fixed random_state.

Uses the same TF-IDF as UMAP, then t-SNE with perplexity=30 (good for 5738 points).
"""
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
OUT_B64 = Path("/home/z/my-project/docs/reports/adintel/tsne_coords.b64")
OUT_META = REPO / "reports" / "adintel" / "tsne_projection_meta.json"

sys.path.insert(0, str(REPO))
from adintel.clean_body import clean_body

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize
from sklearn.decomposition import TruncatedSVD
from sklearn.manifold import TSNE
import base64

def main():
    print("[1/4] Loading corpus...")
    recs = []
    with open(DATA, "r", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line.strip())
            text = (r.get("title","") + " " + clean_body(r.get("body_redacted",""))).strip() or r.get("title","")
            recs.append(text)
    print(f"      {len(recs):,} ads")

    print("[2/4] Building TF-IDF + TruncatedSVD (50 dims for t-SNE speed)...")
    vec = TfidfVectorizer(sublinear_tf=True, min_df=2, max_df=0.85, ngram_range=(1,2),
                          strip_accents=None, lowercase=True, token_pattern=r"(?u)\b\w\w+\b")
    X = vec.fit_transform(recs)
    X_norm = normalize(X, norm="l2", copy=False)
    print(f"      TF-IDF: {X.shape}")
    
    # Pre-reduce to 50 dims with SVD (standard practice before t-SNE)
    svd = TruncatedSVD(n_components=50, random_state=42)
    X_svd = svd.fit_transform(X_norm)
    print(f"      SVD: {X_svd.shape}, explained variance: {svd.explained_variance_ratio_.sum():.3f}")

    print("[3/4] Running t-SNE (perplexity=30, random_state=42)...")
    t0 = time.time()
    tsne = TSNE(n_components=2, perplexity=30, max_iter=1000, random_state=42, init="pca", learning_rate="auto")
    coords = tsne.fit_transform(X_svd)
    elapsed = time.time() - t0
    print(f"      t-SNE: {coords.shape} in {elapsed:.1f}s")

    # Normalize to [0, 1]
    x_min, x_max = coords[:, 0].min(), coords[:, 0].max()
    y_min, y_max = coords[:, 1].min(), coords[:, 1].max()
    coords_norm = np.empty_like(coords, dtype=np.float32)
    coords_norm[:, 0] = (coords[:, 0] - x_min) / (x_max - x_min + 1e-9)
    coords_norm[:, 1] = (coords[:, 1] - y_min) / (y_max - y_min + 1e-9)

    print("[4/4] Saving packed Float32 base64...")
    packed = coords_norm.astype(np.float32).tobytes()
    b64 = base64.b64encode(packed).decode("ascii")
    OUT_B64.write_text(b64)
    print(f"      Packed: {OUT_B64} ({OUT_B64.stat().st_size / 1024:.1f} KB)")

    meta = {
        "method": "tsne",
        "n_records": len(recs),
        "params": {"n_components": 2, "perplexity": 30, "max_iter": 1000, "random_state": 42, "init": "pca"},
        "svd_pre_reduction": {"n_components": 50, "explained_variance": round(float(svd.explained_variance_ratio_.sum()), 4)},
        "coord_range_normalized": {"x": [0.0, 1.0], "y": [0.0, 1.0]},
        "elapsed_seconds": round(elapsed, 1),
        "ran_at": int(time.time()),
        "determinism": {"random_state": 42, "init": "pca"},
    }
    OUT_META.write_text(json.dumps(meta, indent=2))
    print(f"      Meta: {OUT_META}")
    print(f"\nDone. t-SNE coords saved (same record order as UMAP — use umap_record_order.json for lookup).")

if __name__ == "__main__":
    main()
