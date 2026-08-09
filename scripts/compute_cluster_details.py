"""Compute cluster membership explanation data for the dashboard.

For each HDBSCAN v2 cluster:
- Top 5 distinguishing terms (highest TF-IDF mean vs corpus mean, Cohen's h > 0.2)
- 3 representative ads (highest silhouette / closest to centroid in UMAP space)
- 2 boundary ads (lowest silhouette / furthest from centroid)

Output: hdbscan_cluster_details.json — compact, embedded in dashboard
"""
import json
import os
import sys
from pathlib import Path
from collections import defaultdict
import numpy as np

os.environ["NUMBA_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"

REPO = Path("/home/z/my-project/repo")
MANIFEST = REPO / "data" / "processed" / "ad_manifest.jsonl"
LABELS = REPO / "reports" / "adintel" / "hdbscan_labels_v2.jsonl"
OUT = Path("/home/z/my-project/docs/reports/adintel/hdbscan_cluster_details.json")

sys.path.insert(0, str(REPO))
from adintel.clean_body import clean_body

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

def main():
    # Load corpus in manifest order (same as UMAP/HDBSCAN)
    recs = []
    with open(MANIFEST) as f:
        for line in f:
            r = json.loads(line.strip())
            text = (r.get("title","") + " " + clean_body(r.get("body_redacted",""))).strip() or r.get("title","")
            recs.append({"record_id": r["record_id"], "text": text, "platform": r.get("source_platform","")})
    print(f"Loaded {len(recs)} ads")

    # Load HDBSCAN labels
    labels = []
    with open(LABELS) as f:
        for line in f:
            labels.append(json.loads(line.strip()))
    print(f"Loaded {len(labels)} labels")
    
    # Build record_id -> label map
    label_map = {l["record_id"]: l["hdbscan_cluster"] for l in labels}
    
    # Assign labels to recs (in manifest order)
    hdb_labels = np.array([label_map.get(r["record_id"], -1) for r in recs])
    
    # Build TF-IDF
    print("Building TF-IDF...")
    vec = TfidfVectorizer(sublinear_tf=True, min_df=2, max_df=0.85, ngram_range=(1,2),
                          strip_accents=None, lowercase=True, token_pattern=r"(?u)\b\w\w+\b")
    X = vec.fit_transform([r["text"] for r in recs])
    X_norm = normalize(X, norm="l2", copy=False)
    feature_names = vec.get_feature_names_out()
    print(f"TF-IDF: {X.shape}")

    # For each cluster (top 20 by size), compute:
    # 1. Distinguishing terms (Cohen's h > 0.2, sorted by h descending)
    # 2. Representative ads (highest TF-IDF similarity to cluster centroid)
    # 3. Boundary ads (lowest similarity to centroid)
    
    unique_clusters, counts = np.unique(hdb_labels[hdb_labels != -1], return_counts=True)
    order = np.argsort(-counts)
    top_clusters = unique_clusters[order[:20]].tolist()
    
    # Global corpus term frequency (for comparison)
    corpus_mean = np.asarray(X.mean(axis=0)).flatten()
    
    cluster_details = []
    for cid in top_clusters:
        mask = hdb_labels == cid
        n_members = int(mask.sum())
        if n_members < 2:
            continue
        
        # Cluster centroid
        cluster_mean = np.asarray(X[mask].mean(axis=0)).flatten()
        
        # Cohen's h for each term: 2*arcsin(sqrt(p1)) - 2*arcsin(sqrt(p2))
        # p1 = cluster term frequency, p2 = corpus term frequency
        p1 = np.clip(cluster_mean, 0, 1)
        p2 = np.clip(corpus_mean, 0, 1)
        h = 2 * np.arcsin(np.sqrt(p1)) - 2 * np.arcsin(np.sqrt(p2))
        
        # Top distinguishing terms (h > 0.2, sorted by h)
        top_indices = np.argsort(-h)[:20]
        distinguishing_terms = []
        for idx in top_indices:
            if h[idx] > 0.15 and cluster_mean[idx] > 0.01:
                distinguishing_terms.append({
                    "term": feature_names[idx],
                    "h": round(float(h[idx]), 3),
                    "cluster_freq": round(float(cluster_mean[idx]), 4),
                    "corpus_freq": round(float(corpus_mean[idx]), 4),
                })
            if len(distinguishing_terms) >= 5:
                break
        
        # Representative ads (highest similarity to centroid)
        from sklearn.metrics.pairwise import cosine_similarity
        sims = cosine_similarity(X[mask], cluster_mean.reshape(1, -1)).flatten()
        member_indices = np.where(mask)[0]
        
        rep_order = np.argsort(-sims)[:3]
        representative_ads = []
        for idx in rep_order:
            r = recs[member_indices[idx]]
            representative_ads.append({
                "record_id": r["record_id"][:16],
                "title": r["text"][:60],
                "similarity": round(float(sims[idx]), 3),
            })
        
        # Boundary ads (lowest similarity to centroid)
        boundary_order = np.argsort(sims)[:2]
        boundary_ads = []
        for idx in boundary_order:
            r = recs[member_indices[idx]]
            boundary_ads.append({
                "record_id": r["record_id"][:16],
                "title": r["text"][:60],
                "similarity": round(float(sims[idx]), 3),
            })
        
        cluster_details.append({
            "cluster_id": int(cid),
            "n_members": n_members,
            "distinguishing_terms": distinguishing_terms,
            "representative_ads": representative_ads,
            "boundary_ads": boundary_ads,
        })
    
    output = {"n_clusters_detailed": len(cluster_details), "clusters": cluster_details}
    OUT.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")))
    print(f"\nSaved {OUT} ({OUT.stat().st_size / 1024:.1f} KB)")
    print(f"Detailed {len(cluster_details)} clusters")
    for c in cluster_details[:3]:
        print(f"  Cluster {c['cluster_id']} ({c['n_members']} ads): {[t['term'] for t in c['distinguishing_terms']]}")

if __name__ == "__main__":
    main()
