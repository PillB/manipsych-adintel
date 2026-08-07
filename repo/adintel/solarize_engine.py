"""Solarize engine: extends clustering + outlier modules with per-ad
membership, 4-way outlier classification, feature-engineering benchmarks,
and term-prevalence comparison across three control populations.

This module wraps `adintel.clustering` and `adintel.outlier` rather than
modifying them, so existing tests keep passing.

Public API
----------
* `compute_per_ad_membership(...)` — per-ad cluster_id, distance_to_centroid,
  silhouette, alternative_cluster_id, membership_strength.
* `classify_outliers_4way(...)` — assigns every ad to ≥0 of the four
  outlier kinds: detector, density_noise, cluster_enriched, boundary.
* `benchmark_feature_engineering(...)` — runs raw TF-IDF vs LSA vs UMAP
  baselines and reports silhouette + stability ARI for each. Used to
  justify or reject deep clustering.
* `compute_term_comparison(...)` — runs `solarize_stats.compare_term_set`
  against (a) all non-outlier ads, (b) same-cluster non-outlier ads,
  (c) matched controls on platform_family + city.
* `build_solarize_summary(...)` — top-level orchestrator that returns a
  single dict for `solarize_summary.json`.
"""

from __future__ import annotations

import time
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Sequence

import numpy as np
from sklearn.cluster import MiniBatchKMeans, DBSCAN
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import silhouette_samples, silhouette_score
from sklearn.preprocessing import normalize, StandardScaler

from adintel import solarize_stats
from adintel.solarize_stats import (
    OUTLIER_KINDS,
    canonical_outlier_kind,
    compare_term_set,
    aggregate_verdict,
)

def _clean_preview(text: str, max_chars: int = 200) -> str:
    """Clean body text by stripping ' - Category - ID' suffix, then truncate."""
    from adintel.clean_body import clean_body_preview
    return clean_body_preview(text or "", max_chars)


# ---------------------------------------------------------------------------
# Per-ad cluster membership
# ---------------------------------------------------------------------------


@dataclass
class AdMembership:
    """Per-ad cluster membership record."""

    record_id: str
    cluster_id: int
    distance_to_centroid: float
    silhouette: float
    alternative_cluster_id: int
    alternative_cluster_distance: float
    membership_strength: float  # softmax over inverse distance
    is_noise: bool  # True if DBSCAN assigned -1

    def to_dict(self) -> dict:
        return {
            "record_id": self.record_id,
            "cluster_id": int(self.cluster_id),
            "distance_to_centroid": round(float(self.distance_to_centroid), 4),
            "silhouette": round(float(self.silhouette), 4),
            "alternative_cluster_id": int(self.alternative_cluster_id),
            "alternative_cluster_distance": round(float(self.alternative_cluster_distance), 4),
            "membership_strength": round(float(self.membership_strength), 4),
            "is_noise": bool(self.is_noise),
        }


def _softmax_inverse_distance(dists: np.ndarray) -> np.ndarray:
    """Convert distances to softmax weights via 1/(d+eps)."""
    if dists.size == 0:
        return dists
    eps = 1e-6
    inv = 1.0 / (dists + eps)
    # Numerical stability
    inv = inv - inv.max()
    e = np.exp(inv)
    return e / e.sum()


def compute_per_ad_membership(
    *,
    X,
    records: list[dict],
    k: int = 5,
    random_state: int = 42,
    compute_silhouette: bool = True,
) -> tuple[list[AdMembership], dict]:
    """Run MiniBatchKMeans + per-ad silhouette + alternative-cluster lookup.

    Returns (memberships, summary_stats).
    """
    if hasattr(X, "toarray"):
        X_arr = X.toarray()
    else:
        X_arr = np.asarray(X)
    n = X_arr.shape[0]

    if n < k:
        # Too few records — assign all to cluster 0
        memberships = [
            AdMembership(
                record_id=records[i].get("record_id", str(i)),
                cluster_id=0,
                distance_to_centroid=0.0,
                silhouette=0.0,
                alternative_cluster_id=-1,
                alternative_cluster_distance=0.0,
                membership_strength=1.0,
                is_noise=False,
            )
            for i in range(n)
        ]
        return memberships, {"n_clusters": 1, "silhouette_mean": 0.0, "k": k}

    km = MiniBatchKMeans(n_clusters=k, random_state=random_state, n_init=3, batch_size=128)
    labels = km.fit_predict(X_arr)
    centroids = km.cluster_centers_

    # Per-ad silhouette (sample-level). Falls back to 0 if undefined.
    if compute_silhouette and len(set(labels.tolist())) >= 2:
        try:
            if n > 3000:
                # Sample for silhouette computation, then back-fill via 1-NN.
                rng = np.random.RandomState(random_state)
                idx = rng.choice(n, min(3000, n), replace=False)
                sil_subset = silhouette_samples(X_arr[idx], labels[idx])
                # Assign each ad the silhouette of its nearest neighbour in the subset.
                # Cheap heuristic: use the median silhouette of the same cluster.
                cluster_sil_medians: dict[int, float] = {}
                for c in range(k):
                    c_mask = labels[idx] == c
                    if c_mask.any():
                        cluster_sil_medians[c] = float(np.median(sil_subset[c_mask]))
                    else:
                        cluster_sil_medians[c] = 0.0
                sil = np.array([cluster_sil_medians.get(int(labels[i]), 0.0) for i in range(n)])
                silhouette_mean = float(np.mean(sil_subset))
            else:
                sil = silhouette_samples(X_arr, labels)
                silhouette_mean = float(np.mean(sil))
        except Exception:
            sil = np.zeros(n)
            silhouette_mean = 0.0
    else:
        sil = np.zeros(n)
        silhouette_mean = 0.0

    # Per-ad: distance to own centroid, distance to nearest other centroid (alternative).
    memberships: list[AdMembership] = []
    for i in range(n):
        xi = X_arr[i]
        own_c = int(labels[i])
        d_own = float(np.linalg.norm(xi - centroids[own_c]))
        # Distances to all centroids
        all_d = np.linalg.norm(centroids - xi, axis=1)
        # Alternative = 2nd nearest (after own)
        order = np.argsort(all_d)
        alt_c = int(order[1]) if len(order) > 1 else -1
        alt_d = float(all_d[order[1]]) if len(order) > 1 else 0.0
        # Membership strength: softmax over inverse distance, restricted to top-2.
        top2 = order[:2]
        weights = _softmax_inverse_distance(all_d[top2])
        strength = float(weights[0])  # weight on own cluster

        memberships.append(
            AdMembership(
                record_id=records[i].get("record_id", str(i)),
                cluster_id=own_c,
                distance_to_centroid=d_own,
                silhouette=float(sil[i]),
                alternative_cluster_id=alt_c,
                alternative_cluster_distance=alt_d,
                membership_strength=strength,
                is_noise=False,
            )
        )

    summary = {
        "n_clusters": int(k),
        "silhouette_mean": round(silhouette_mean, 4),
        "k": k,
        "method": "TF-IDF (1-2 grams) → L2-normalise → MiniBatchKMeans",
    }
    return memberships, summary


# ---------------------------------------------------------------------------
# Density-based noise detection (DBSCAN label=-1)
# ---------------------------------------------------------------------------


def detect_density_noise(
    X,
    *,
    eps: float = 0.65,
    min_samples: int = 10,
) -> np.ndarray:
    """Return a boolean mask: True = DBSCAN noise (label=-1).

    Uses cosine distance after L2 normalisation. eps=0.65 means two ads must
    have cosine similarity ≥ 0.35 to be in the same neighbourhood. This is
    tuned for short Spanish classified ads where exact-match signal is weak
    but topical similarity is strong. min_samples=10 is the conservative
    DBSCAN default for "core point" status.
    """
    if hasattr(X, "toarray"):
        X_arr = X.toarray()
    else:
        X_arr = np.asarray(X)
    Xn = normalize(X_arr, norm="l2", axis=1)
    db = DBSCAN(eps=eps, min_samples=min_samples, metric="cosine", n_jobs=-1)
    labels = db.fit_predict(Xn)
    return labels == -1


# ---------------------------------------------------------------------------
# Within-cluster Mahalanobis / MAD outliers (cluster-enriched)
# ---------------------------------------------------------------------------


def detect_cluster_enriched(
    X,
    labels: np.ndarray,
    *,
    threshold_mad: float = 3.5,
) -> np.ndarray:
    """Per-cluster MAD outlier: distance from centroid > threshold_mad * MAD.

    Returns a boolean mask. Used for the "cluster_enriched" outlier kind.
    """
    if hasattr(X, "toarray"):
        X_arr = X.toarray()
    else:
        X_arr = np.asarray(X)
    n = X_arr.shape[0]
    mask = np.zeros(n, dtype=bool)
    for c in sorted(set(labels.tolist())):
        if c == -1:
            continue
        members = np.where(labels == c)[0]
        if len(members) < 10:
            continue
        centroid = X_arr[members].mean(axis=0)
        dists = np.linalg.norm(X_arr[members] - centroid, axis=1)
        med = float(np.median(dists))
        mad = float(np.median(np.abs(dists - med))) or 1e-6
        # Robust z-score using MAD scaled by 0.6745
        z = (dists - med) / (mad * 1.4826)
        cutoff = threshold_mad
        outliers = np.abs(z) > cutoff
        mask[members[outliers]] = True
    return mask


# ---------------------------------------------------------------------------
# Boundary members (silhouette < 0)
# ---------------------------------------------------------------------------


def detect_boundary_members(
    X,
    labels: np.ndarray,
) -> np.ndarray:
    """Boundary members: per-ad silhouette < 0 (closer to another cluster)."""
    if hasattr(X, "toarray"):
        X_arr = X.toarray()
    else:
        X_arr = np.asarray(X)
    if len(set(labels.tolist())) < 2:
        return np.zeros(X_arr.shape[0], dtype=bool)
    try:
        sil = silhouette_samples(X_arr, labels)
    except Exception:
        return np.zeros(X_arr.shape[0], dtype=bool)
    return sil < 0.0


# ---------------------------------------------------------------------------
# 4-way outlier classification
# ---------------------------------------------------------------------------


def classify_outliers_4way(
    *,
    X,
    records: list[dict],
    historical_outlier_reports: list,  # adintel.outlier.OutlierReport objects
    memberships: list[AdMembership],
    use_density: bool = True,
) -> dict:
    """Classify each ad into 0..4 outlier kinds.

    Returns a dict:
      {
        "by_kind": {kind: n_ads},
        "by_record_id": {record_id: [kinds...]},
        "examples_per_kind": {kind: [record_id, score, reason]...},
      }
    """
    if hasattr(X, "toarray"):
        X_arr = X.toarray()
    else:
        X_arr = np.asarray(X)
    n = X_arr.shape[0]

    # Detector outliers: union of all historical OutlierReport record_ids
    detector_ids: set[str] = set()
    for r in historical_outlier_reports:
        detector_ids.add(r.record_id)

    labels = np.array([m.cluster_id for m in memberships])

    # Density noise
    if use_density:
        try:
            density_mask = detect_density_noise(X_arr)
        except Exception:
            density_mask = np.zeros(n, dtype=bool)
    else:
        density_mask = np.zeros(n, dtype=bool)

    # Cluster-enriched (MAD)
    try:
        enriched_mask = detect_cluster_enriched(X_arr, labels)
    except Exception:
        enriched_mask = np.zeros(n, dtype=bool)

    # Boundary (silhouette < 0)
    try:
        boundary_mask = detect_boundary_members(X_arr, labels)
    except Exception:
        boundary_mask = np.zeros(n, dtype=bool)

    # Build per-record kind sets
    by_record_id: dict[str, list[str]] = {}
    for i, r in enumerate(records):
        rid = r.get("record_id", str(i))
        kinds: list[str] = []
        if rid in detector_ids:
            kinds.append("detector")
        if bool(density_mask[i]):
            kinds.append("density_noise")
        if bool(enriched_mask[i]):
            kinds.append("cluster_enriched")
        if bool(boundary_mask[i]):
            kinds.append("boundary")
        if kinds:
            by_record_id[rid] = kinds

    by_kind_count = {k: 0 for k in OUTLIER_KINDS}
    for kinds in by_record_id.values():
        for k in kinds:
            by_kind_count[k] += 1

    # Examples per kind (top 5 by an internal score)
    examples_per_kind: dict[str, list] = {k: [] for k in OUTLIER_KINDS}
    for i, r in enumerate(records):
        rid = r.get("record_id", str(i))
        kinds = by_record_id.get(rid, [])
        if not kinds:
            continue
        # Score by silhouette negativity (boundary), then distance-to-centroid (enriched)
        m = memberships[i]
        score = 0.0
        if "boundary" in kinds:
            score += abs(min(0.0, m.silhouette))
        if "cluster_enriched" in kinds:
            score += m.distance_to_centroid
        if "density_noise" in kinds:
            score += 0.5
        if "detector" in kinds:
            score += 0.3
        for k in kinds:
            if len(examples_per_kind[k]) < 5:
                examples_per_kind[k].append({
                    "record_id": rid,
                    "title": (r.get("title", "") or "")[:80],
                    "platform": r.get("metadata", {}).get("platform_family", "unknown"),
                    "score": round(score, 3),
                    "cluster_id": m.cluster_id,
                    "silhouette": round(m.silhouette, 4),
                    "distance_to_centroid": round(m.distance_to_centroid, 4),
                    "reason": _outlier_reason(kinds, m),
                })

    return {
        "by_kind": by_kind_count,
        "by_record_id": by_record_id,
        "examples_per_kind": examples_per_kind,
    }


def _outlier_reason(kinds: list[str], m: AdMembership) -> str:
    """Human-readable reason string for an outlier ad."""
    bits = []
    if "detector" in kinds:
        bits.append("flagged by rule-based / model-based detector")
    if "density_noise" in kinds:
        bits.append("DBSCAN assigned to noise (low-density region)")
    if "cluster_enriched" in kinds:
        bits.append(f"within-cluster distance {m.distance_to_centroid:.2f} (MAD outlier)")
    if "boundary" in kinds:
        bits.append(f"silhouette {m.silhouette:.2f} < 0 (closer to another cluster)")
    return "; ".join(bits) + "."


# ---------------------------------------------------------------------------
# Feature-engineering benchmark (R5, R6)
# ---------------------------------------------------------------------------


def benchmark_feature_engineering(
    *,
    texts: Sequence[str],
    k: int = 5,
    random_state: int = 42,
) -> list[dict]:
    """Benchmark three feature-engineering baselines for clustering.

    Baselines (in order of complexity):
      1. raw_tfidf_kmeans       — TF-IDF (1-2 grams, 5k features) + KMeans
      2. tfidf_lsa100_kmeans    — TF-IDF → LSA(100d) + KMeans
      3. tfidf_svd_umap_kmeans  — TF-IDF → SVD(50d) → (no UMAP if unavailable) → KMeans

    Returns a list of dicts sorted by silhouette descending. The dashboard
    will use this to justify (or reject) the deep-clustering step.
    """
    results: list[dict] = []

    # Baseline 1: raw TF-IDF + KMeans
    t0 = time.perf_counter()
    try:
        vec = TfidfVectorizer(max_features=5000, ngram_range=(1, 2), min_df=2, max_df=0.95)
        X1 = vec.fit_transform(texts)
        X1 = normalize(X1, norm="l2", axis=1)
        km = MiniBatchKMeans(n_clusters=k, random_state=random_state, n_init=3, batch_size=128)
        labels1 = km.fit_predict(X1)
        sil1 = _safe_silhouette(X1, labels1)
        ari1 = _safe_stability(X1, k, random_state)
        results.append({
            "name": "raw_tfidf_kmeans",
            "feature": "TF-IDF (1-2 grams, 5k features, L2-normalised)",
            "silhouette": round(sil1, 4),
            "stability_ari": round(ari1, 4),
            "k": k,
            "elapsed_s": round(time.perf_counter() - t0, 2),
            "deep": False,
        })
    except Exception as e:
        results.append({"name": "raw_tfidf_kmeans", "error": str(e)})

    # Baseline 2: TF-IDF → LSA(100d) + KMeans  (the existing "deep" approach)
    t0 = time.perf_counter()
    try:
        svd = TruncatedSVD(n_components=min(100, X1.shape[1] - 1), random_state=random_state)
        X2 = svd.fit_transform(X1)
        X2 = normalize(X2, norm="l2", axis=1)
        km = MiniBatchKMeans(n_clusters=k, random_state=random_state, n_init=3, batch_size=128)
        labels2 = km.fit_predict(X2)
        sil2 = _safe_silhouette(X2, labels2)
        ari2 = _safe_stability(X2, k, random_state)
        results.append({
            "name": "tfidf_lsa100_kmeans",
            "feature": "TF-IDF → LSA(100d) → L2 → KMeans (the previous 'deep' approach)",
            "silhouette": round(sil2, 4),
            "stability_ari": round(ari2, 4),
            "k": k,
            "explained_variance": round(float(svd.explained_variance_ratio_.sum()), 4),
            "elapsed_s": round(time.perf_counter() - t0, 2),
            "deep": True,
        })
    except Exception as e:
        results.append({"name": "tfidf_lsa100_kmeans", "error": str(e)})

    # Baseline 3: TF-IDF → SVD(50d) → StandardScaler → KMeans
    t0 = time.perf_counter()
    try:
        svd3 = TruncatedSVD(n_components=min(50, X1.shape[1] - 1), random_state=random_state)
        X3 = svd3.fit_transform(X1)
        X3 = StandardScaler(with_mean=False).fit_transform(X3)
        X3 = normalize(X3, norm="l2", axis=1)
        km = MiniBatchKMeans(n_clusters=k, random_state=random_state, n_init=3, batch_size=128)
        labels3 = km.fit_predict(X3)
        sil3 = _safe_silhouette(X3, labels3)
        ari3 = _safe_stability(X3, k, random_state)
        results.append({
            "name": "tfidf_svd50_scaled_kmeans",
            "feature": "TF-IDF → SVD(50d) → StandardScaler → L2 → KMeans",
            "silhouette": round(sil3, 4),
            "stability_ari": round(ari3, 4),
            "k": k,
            "explained_variance": round(float(svd3.explained_variance_ratio_.sum()), 4),
            "elapsed_s": round(time.perf_counter() - t0, 2),
            "deep": True,
        })
    except Exception as e:
        results.append({"name": "tfidf_svd50_scaled_kmeans", "error": str(e)})

    # Sort by silhouette descending
    results.sort(key=lambda r: -r.get("silhouette", -1.0))
    return results


def _safe_silhouette(X, labels) -> float:
    if len(set(labels.tolist())) < 2:
        return 0.0
    try:
        if hasattr(X, "toarray"):
            X_eval = X.toarray()
        else:
            X_eval = np.asarray(X)
        if X_eval.shape[0] > 3000:
            rng = np.random.RandomState(42)
            idx = rng.choice(X_eval.shape[0], 3000, replace=False)
            X_eval = X_eval[idx]
            labels = labels[idx]
        return float(silhouette_score(X_eval, labels, metric="euclidean"))
    except Exception:
        return 0.0


def _safe_stability(X, k: int, random_state: int = 42, n_resamples: int = 3) -> float:
    from sklearn.metrics import adjusted_rand_score

    if hasattr(X, "toarray"):
        X_arr = X.toarray()
    else:
        X_arr = np.asarray(X)
    n = X_arr.shape[0]
    if n < 10:
        return 0.0
    try:
        km0 = MiniBatchKMeans(n_clusters=k, random_state=random_state, n_init=3, batch_size=128)
        l0 = km0.fit_predict(X_arr)
        aris = []
        rng = np.random.RandomState(random_state)
        for i in range(n_resamples):
            idx = rng.choice(n, max(2, int(n * 0.8)), replace=False)
            sub = X_arr[idx]
            km = MiniBatchKMeans(n_clusters=k, random_state=random_state + i + 1, n_init=3, batch_size=128)
            ls = km.fit_predict(sub)
            aris.append(adjusted_rand_score(l0[idx], ls))
        return float(np.mean(aris)) if aris else 0.0
    except Exception:
        return 0.0


def deep_clustering_justified(benchmark: list[dict], *, min_silhouette: float = 0.10) -> tuple[bool, str]:
    """Decide whether deep clustering is justified (R6).

    Deep clustering is justified ONLY if:
      - the best simple baseline (raw TF-IDF) has silhouette < min_silhouette, AND
      - the best deep baseline improves silhouette by ≥ 0.05 over the simple baseline.
    Otherwise deep clustering is NOT justified — simpler baselines already work.
    """
    simple = [r for r in benchmark if not r.get("deep", False) and "silhouette" in r]
    deep = [r for r in benchmark if r.get("deep", False) and "silhouette" in r]
    if not simple or not deep:
        return False, "Insufficient benchmark data to justify deep clustering."
    best_simple = max(r["silhouette"] for r in simple)
    best_deep = max(r["silhouette"] for r in deep)
    if best_simple < min_silhouette and (best_deep - best_simple) >= 0.05:
        return True, (
            f"Simple baselines failed (best silhouette {best_simple:.3f} < {min_silhouette}); "
            f"deep clustering improves silhouette by {best_deep - best_simple:.3f} (→ {best_deep:.3f})."
        )
    return False, (
        f"Simple baselines already achieve silhouette {best_simple:.3f} (≥ {min_silhouette}); "
        f"deep clustering only achieves {best_deep:.3f} (Δ {best_deep - best_simple:+.3f}). "
        f"Deep clustering NOT justified — simpler baselines suffice."
    )


# ---------------------------------------------------------------------------
# Term-prevalence comparison across three control populations (R1–R4)
# ---------------------------------------------------------------------------


def _extract_candidate_terms(texts: Sequence[str], *, top_k: int = 80) -> list[str]:
    """Extract candidate terms for prevalence comparison.

    Uses 1- and 2-gram TF-IDF vocabulary restricted to the top-K by document
    frequency. Returns the top-K terms.
    """
    try:
        vec = TfidfVectorizer(ngram_range=(1, 2), min_df=3, max_df=0.85, max_features=top_k)
        vec.fit_transform(texts)
        return list(vec.get_feature_names_out())
    except Exception:
        # Fallback: top frequency words
        c: Counter = Counter()
        for t in texts:
            for w in str(t).lower().split():
                w = w.strip(".,;:!?¡¿\"'()[]")
                if len(w) > 3:
                    c[w] += 1
        return [w for w, _ in c.most_common(top_k)]


def compute_term_comparison(
    *,
    outlier_record_ids: set[str],
    records: list[dict],
    texts: list[str],
    memberships: list[AdMembership],
    outlier_kind_by_id: dict[str, list[str]],
    top_k_terms: int = 50,
    min_support: int = 5,
) -> dict:
    """Compute three-way term-prevalence comparison.

    Populations:
      (a) all non-outlier ads
      (b) non-outlier ads in the same cluster (matched on cluster_id)
      (c) matched controls on platform_family (when metadata exists)
    """
    # Map record_id -> text and record_id -> membership
    text_by_id = {r.get("record_id", ""): t for r, t in zip(records, texts)}
    mem_by_id = {m.record_id: m for m in memberships}

    # Outlier texts (any ad with ≥1 outlier kind)
    outlier_ids = sorted(outlier_record_ids)
    non_outlier_ids = [rid for rid in text_by_id if rid not in outlier_record_ids]

    # (a) all non-outlier ads
    outlier_texts = [text_by_id[rid] for rid in outlier_ids if rid in text_by_id]
    control_a_texts = [text_by_id[rid] for rid in non_outlier_ids if rid in text_by_id]

    # (b) same-cluster non-outlier ads
    # For each outlier ad, find non-outlier ads in the same cluster.
    by_cluster: dict[int, list[str]] = defaultdict(list)
    for rid in non_outlier_ids:
        m = mem_by_id.get(rid)
        if m:
            by_cluster[m.cluster_id].append(rid)
    control_b_texts: list[str] = []
    for rid in outlier_ids:
        m = mem_by_id.get(rid)
        if not m:
            continue
        same_cluster = by_cluster.get(m.cluster_id, [])
        # Take up to 5 same-cluster controls per outlier (cap total to control_b size)
        for ctrl_id in same_cluster[:5]:
            if ctrl_id in text_by_id:
                control_b_texts.append(text_by_id[ctrl_id])

    # (c) matched controls on platform_family
    by_platform: dict[str, list[str]] = defaultdict(list)
    for rid in non_outlier_ids:
        rec = next((r for r in records if r.get("record_id") == rid), None)
        if rec:
            plat = rec.get("metadata", {}).get("platform_family", "unknown")
            by_platform[plat].append(rid)
    control_c_texts: list[str] = []
    for rid in outlier_ids:
        rec = next((r for r in records if r.get("record_id") == rid), None)
        if not rec:
            continue
        plat = rec.get("metadata", {}).get("platform_family", "unknown")
        same_plat = by_platform.get(plat, [])
        for ctrl_id in same_plat[:3]:
            if ctrl_id in text_by_id:
                control_c_texts.append(text_by_id[ctrl_id])

    # Candidate terms from the outlier corpus
    terms = _extract_candidate_terms(outlier_texts + control_a_texts, top_k=top_k_terms)

    # Run comparisons
    pop_a = compare_term_set(
        terms=terms,
        outlier_texts=outlier_texts,
        control_texts=control_a_texts,
        comparison_population="all non-outlier ads",
        min_support=min_support,
    )
    verdict_a = aggregate_verdict(pop_a)

    pop_b = compare_term_set(
        terms=terms,
        outlier_texts=outlier_texts,
        control_texts=control_b_texts,
        comparison_population="non-outlier ads in the same cluster",
        min_support=min_support,
    )
    verdict_b = aggregate_verdict(pop_b)

    pop_c = compare_term_set(
        terms=terms,
        outlier_texts=outlier_texts,
        control_texts=control_c_texts,
        comparison_population="matched controls on platform_family",
        min_support=min_support,
    )
    verdict_c = aggregate_verdict(pop_c)

    return {
        "outlier_vs_all_non_outlier": {
            "comparison_population": "all non-outlier ads",
            "n_outlier": len(outlier_texts),
            "n_control": len(control_a_texts),
            "rows": pop_a,
            "aggregate_verdict": verdict_a,
        },
        "outlier_vs_same_cluster_non_outlier": {
            "comparison_population": "non-outlier ads in the same cluster",
            "n_outlier": len(outlier_texts),
            "n_control": len(control_b_texts),
            "rows": pop_b,
            "aggregate_verdict": verdict_b,
        },
        "outlier_vs_matched_control": {
            "comparison_population": "matched controls on platform_family",
            "n_outlier": len(outlier_texts),
            "n_control": len(control_c_texts),
            "rows": pop_c,
            "aggregate_verdict": verdict_c,
        },
    }


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------


def build_solarize_summary(
    *,
    records: list[dict],
    texts: list[str],
    historical_outlier_reports: list,
    k: int = 5,
    top_k_terms: int = 50,
    top_n_ad_selector: int = 200,
    random_state: int = 42,
) -> dict:
    """Top-level entry point: produce the full solarize_summary dict.

    This is called by scripts/run_solarize_pipeline.py.
    """
    t0 = time.perf_counter()

    # ---- 1. Feature engineering + clustering ----
    vec = TfidfVectorizer(max_features=5000, ngram_range=(1, 2), min_df=2, max_df=0.95)
    X = vec.fit_transform(texts)
    X = normalize(X, norm="l2", axis=1)
    feature_names = vec.get_feature_names_out().tolist()

    # ---- 2. Per-ad membership ----
    memberships, mem_summary = compute_per_ad_membership(
        X=X, records=records, k=k, random_state=random_state
    )

    # ---- 3. Feature engineering benchmark (R5, R6) ----
    benchmark = benchmark_feature_engineering(texts=texts, k=k, random_state=random_state)
    deep_justified, deep_reason = deep_clustering_justified(benchmark)

    # ---- 4. 4-way outlier classification (R9) ----
    outlier_class = classify_outliers_4way(
        X=X,
        records=records,
        historical_outlier_reports=historical_outlier_reports,
        memberships=memberships,
    )

    # ---- 5. Term-prevalence comparison (R1–R4) ----
    outlier_ids = set(outlier_class["by_record_id"].keys())
    term_comparison = compute_term_comparison(
        outlier_record_ids=outlier_ids,
        records=records,
        texts=texts,
        memberships=memberships,
        outlier_kind_by_id=outlier_class["by_record_id"],
        top_k_terms=top_k_terms,
    )

    # ---- 6. Cluster explanations (distinguishing terms + examples) ----
    from adintel.clustering import explain_clusters

    labels = np.array([m.cluster_id for m in memberships])
    cluster_explanations = explain_clusters(
        X=X, labels=labels, records=records, texts=texts, feature_names=feature_names
    )
    # Enrich with sample ads
    for ce in cluster_explanations:
        cid = ce["cluster_id"]
        member_idx = [i for i, l in enumerate(labels) if l == cid]
        sample_ads = []
        for i in member_idx[:5]:
            r = records[i]
            sample_ads.append({
                "record_id": r.get("record_id", str(i)),
                "title": (r.get("title", "") or "")[:80],
                "platform": r.get("metadata", {}).get("platform_family", "unknown"),
                "body_preview": _clean_preview(texts[i]),
                "cluster_membership_strength": round(memberships[i].membership_strength, 3),
                "silhouette": round(memberships[i].silhouette, 4),
            })
        ce["sample_ads"] = sample_ads
        # Outlier rate in this cluster
        n_outlier_in_cluster = sum(
            1 for i in member_idx if records[i].get("record_id", "") in outlier_ids
        )
        ce["outlier_rate"] = round(n_outlier_in_cluster / max(1, len(member_idx)), 4)
        ce["silhouette_mean"] = round(
            float(np.mean([memberships[i].silhouette for i in member_idx])), 4
        ) if member_idx else 0.0

    # ---- 7. Per-ad selector (top-N by combined activity score) ----
    # Top ads = those with most outlier kinds + lowest silhouette + highest distance
    selector_records: list[dict] = []
    for i, m in enumerate(memberships):
        r = records[i]
        rid = r.get("record_id", str(i))
        kinds = outlier_class["by_record_id"].get(rid, [])
        score = len(kinds) + abs(min(0.0, m.silhouette)) + m.distance_to_centroid
        selector_records.append({
            "record_id": rid,
            "title": (r.get("title", "") or "")[:80],
            "platform": r.get("metadata", {}).get("platform_family", "unknown"),
            "cluster_id": m.cluster_id,
            "cluster_membership_strength": round(m.membership_strength, 4),
            "distance_to_centroid": round(m.distance_to_centroid, 4),
            "silhouette": round(m.silhouette, 4),
            "alternative_cluster_id": m.alternative_cluster_id,
            "alternative_cluster_membership_strength": round(1.0 - m.membership_strength, 4),
            "outlier_kinds": kinds,
            "outlier_score": round(score, 4),
            "body_preview": (texts[i] or "")[:200],
        })
    selector_records.sort(key=lambda r: -r["outlier_score"])
    top_selector = selector_records[:top_n_ad_selector]

    return {
        "build": {
            "solarize_version": "1.0",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "n_records": len(records),
            "k": k,
            "elapsed_s": round(time.perf_counter() - t0, 2),
        },
        "clustering": {
            **mem_summary,
            "feature_engineering_benchmark": benchmark,
            "deep_clustering_justified": deep_justified,
            "deep_clustering_reason": deep_reason,
            "n_clusters": k,
            "k": k,
        },
        "clusters": cluster_explanations,
        "outliers": {
            "by_kind": outlier_class["by_kind"],
            "kind_definitions": {
                "detector": "Rule-based / model-based outlier detector (historical 11 kinds: creative_novelty, style_outlier, duplicate, etc.)",
                "density_noise": "DBSCAN label=-1 (low-density point, not assigned to any cluster by density-based clustering)",
                "cluster_enriched": "Within-cluster Mahalanobis/MAD distance > 3.5σ (top outliers within their own cluster)",
                "boundary": "Per-ad silhouette score < 0 (closer to another cluster's centroid than to its own)",
            },
            "examples_per_kind": outlier_class["examples_per_kind"],
        },
        "term_comparison": term_comparison,
        "per_ad_selector": top_selector,
        "outlier_kind_by_record_id": outlier_class["by_record_id"],
    }
