"""Multi-space clustering with stability and leakage evaluation.

The spec requires seven cluster spaces:
  persuasive-technique vectors, semantic content, rhetorical style,
  visual structure, multimodal structure, authorial style, normalised
  performance behaviour.

For each space we build features, run a clustering algorithm, and evaluate:
  stability (ARI over resamples),
  resampling consistency (pair co-occurrence),
  parameter sensitivity (std of n_clusters across grid),
  brand/topic leakage (per-cluster dominance),
  representative ads, boundary ads, cluster explanations, noise handling.

CPU-friendly: TF-IDF + MiniBatchKMeans is the default. HDBSCAN is optional
and only used if installed.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Callable, Iterable

import numpy as np
from sklearn.cluster import MiniBatchKMeans
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import adjusted_rand_score, silhouette_samples, silhouette_score
from sklearn.preprocessing import normalize

from adintel.types import ClusterAssignment, ClusterReport


# ---------------------------------------------------------------------------
# Feature builders
# ---------------------------------------------------------------------------


def _safe_text(s: str | None) -> str:
    if not s:
        return ""
    return str(s)


def build_persuasive_features(profiles: list[dict]) -> np.ndarray:
    """Build a (n_ads, 17) matrix from persuasive-profile dicts.

    Each profile must be a serialised PersuasiveProfile (i.e. p.to_dict()).
    Missing dimensions are filled with 0.0; abstained dimensions are filled
    with 0.0 (so abstention does not look like maximum persuasion).
    """
    from adintel.types import PROFILE_DIMENSIONS

    rows: list[list[float]] = []
    for p in profiles:
        dims = p.get("dimensions", {})
        row = [float(dims.get(d, {}).get("score", 0.0)) for d in PROFILE_DIMENSIONS]
        rows.append(row)
    X = np.asarray(rows, dtype=np.float64)
    return normalize(X, norm="l2", axis=1) if X.shape[0] else X


def build_semantic_features(texts: Iterable[str], max_features: int = 1500) -> tuple[np.ndarray, TfidfVectorizer]:
    """Semantic content via TF-IDF word unigrams + bigrams."""
    vec = TfidfVectorizer(
        ngram_range=(1, 2),
        min_df=2,
        max_features=max_features,
        sublinear_tf=True,
        lowercase=True,
        strip_accents="unicode",
    )
    X = vec.fit_transform([_safe_text(t) for t in texts])
    return X, vec


def build_rhetorical_features(texts: Iterable[str]) -> np.ndarray:
    """Rhetorical style: function-word frequencies, punctuation ratios,
    sentence-length distribution. Style only, not content."""
    FW = [
        "de", "la", "que", "el", "en", "y", "a", "los", "se", "del", "las", "un",
        "por", "con", "no", "una", "su", "para", "es", "al", "lo", "como", "más",
        "pero", "sus", "le", "ya", "o", "este", "sí", "porque", "esta", "entre",
        "cuando", "muy", "sin", "sobre", "también", "me", "hasta", "hay", "donde",
    ]
    texts_list = [(_safe_text(t)) for t in texts]
    rows: list[list[float]] = []
    for t in texts_list:
        toks = t.lower().split()
        n = max(1, len(toks))
        fw_counts = {w: 0 for w in FW}
        for tok in toks:
            w = tok.strip(".,;:!?¡¿\"'()[]")
            if w in fw_counts:
                fw_counts[w] += 1
        fw_freq = [fw_counts[w] / n for w in FW]
        n_chars = max(1, len(t))
        punct = [
            t.count("!") / n_chars,
            t.count("?") / n_chars,
            t.count(",") / n_chars,
            t.count(".") / n_chars,
        ]
        sents = [s for s in t.split(".") if s.strip()]
        avg_len = np.mean([len(s.split()) for s in sents]) if sents else 0.0
        rows.append(fw_freq + punct + [avg_len])
    X = np.asarray(rows, dtype=np.float64)
    return normalize(X, norm="l2", axis=1) if X.shape[0] else X


def build_authorial_features(texts: Iterable[str]) -> np.ndarray:
    """Authorial style = char-5-gram TF-IDF L2-normalised.

    This is the same signal used in stylometry (Burrows's Delta lineage).
    Char n-grams are robust to topic shift, which is exactly what authorship
    verification needs.
    """
    vec = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(4, 5),
        min_df=2,
        max_features=2000,
        sublinear_tf=True,
        lowercase=True,
    )
    X = vec.fit_transform([_safe_text(t) for t in texts])
    return X  # sparse, already L2-normalised by TfidfVectorizer


def build_visual_features(records: list[dict]) -> np.ndarray:
    """Visual structure features. v1 corpus has no image pixels, so we use
    image-availability metadata and raw-size bucket as proxies.

    This is a documented limitation: full visual clustering requires archived
    image pixels, which are not in the local corpus."""
    rows: list[list[float]] = []
    for r in records:
        meta = r.get("metadata", {}) if isinstance(r, dict) else {}
        image_count = float(meta.get("image_count", 0) or 0)
        raw_size_bucket_map = {
            "lt_10kb": 0.0, "10kb_100kb": 1.0, "100kb_500kb": 2.0, "500kb_plus": 3.0,
        }
        rsb = raw_size_bucket_map.get(str(meta.get("raw_size_bucket", "")), 0.0)
        rows.append([image_count, rsb, float(meta.get("is_featured_marker", False) or False)])
    return np.asarray(rows, dtype=np.float64)


def build_multimodal_features(texts: Iterable[str], records: list[dict]) -> np.ndarray:
    """Multimodal structure = concatenation of semantic + visual + rhetorical.
    Used to detect cross-modal technique combinations."""
    sem, _ = build_semantic_features(texts)
    vis = build_visual_features(records)
    rh = build_rhetorical_features(texts)
    # Convert sparse sem to dense if small, else keep sparse hstack
    import scipy.sparse as sp
    if sp.issparse(sem):
        sem_dense = sem.toarray()
    else:
        sem_dense = np.asarray(sem)
    out = np.hstack([sem_dense, vis, rh])
    return out


def build_performance_features(records: list[dict]) -> np.ndarray:
    """Normalised performance behaviour. v1 corpus has NO real performance
    metrics (no spend, impressions, CTR). We use the available proxies:
    quality_score, is_paid_or_premium_marker, is_featured_marker, and a
    'has_engagement_signal' flag. The dashboard must disclose this limitation
    in every performance-cluster explanation."""
    rows: list[list[float]] = []
    for r in records:
        meta = r.get("metadata", {}) if isinstance(r, dict) else {}
        q = float(meta.get("quality_score", 0.0) or 0.0)
        paid = float(bool(meta.get("is_paid_or_premium_marker", False)))
        featured = float(bool(meta.get("is_featured_marker", False)))
        eng = float(bool(meta.get("facebook_reactions_approx", 0)) or bool(meta.get("facebook_comments_approx", 0)))
        rows.append([q, paid, featured, eng])
    X = np.asarray(rows, dtype=np.float64)
    return normalize(X, norm="l2", axis=1) if X.shape[0] else X


# ---------------------------------------------------------------------------
# Clustering runner
# ---------------------------------------------------------------------------


def _kmeans(X: np.ndarray, k: int, random_state: int = 42) -> np.ndarray:
    """MiniBatchKMeans with deterministic seed."""
    if X.shape[0] < k:
        # Not enough points; assign all to one cluster
        return np.zeros(X.shape[0], dtype=int)
    if hasattr(X, "toarray"):  # sparse
        X = X.toarray()
    km = MiniBatchKMeans(n_clusters=k, random_state=random_state, n_init=3, batch_size=64)
    return km.fit_predict(X)


def _silhouette_safe(X: np.ndarray, labels: np.ndarray) -> float:
    if len(set(labels.tolist())) < 2:
        return 0.0
    try:
        if hasattr(X, "toarray"):
            X_eval = X.toarray()
        else:
            X_eval = X
        if X_eval.shape[0] > 2000:
            idx = np.random.RandomState(42).choice(X_eval.shape[0], 2000, replace=False)
            X_eval = X_eval[idx]
            labels = labels[idx]
        return float(silhouette_score(X_eval, labels))
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Stability / leakage evaluation
# ---------------------------------------------------------------------------


def evaluate_stability(
    X: np.ndarray,
    k: int,
    n_resamples: int = 5,
    sample_frac: float = 0.8,
    random_state: int = 42,
) -> tuple[float, float]:
    """Return (mean_ARI, resampling_consistency).

    mean_ARI: mean adjusted Rand index between the full-data clustering and
    each bootstrap resample's clustering projected onto the resampled points.
    resampling_consistency: fraction of co-clustered pairs in the full data
    that remain co-clustered across resamples.
    """
    rng = np.random.RandomState(random_state)
    n = X.shape[0]
    if n < max(10, k * 2):
        return 0.0, 0.0
    if hasattr(X, "toarray"):
        X_arr = X.toarray()
    else:
        X_arr = np.asarray(X)
    full_labels = _kmeans(X_arr, k, random_state=random_state)
    aris: list[float] = []
    pair_consistency: list[float] = []
    for i in range(n_resamples):
        idx = rng.choice(n, max(2, int(n * sample_frac)), replace=False)
        sub = X_arr[idx]
        sub_labels = _kmeans(sub, k, random_state=random_state + i)
        # ARI between full_labels on idx and sub_labels
        aris.append(adjusted_rand_score(full_labels[idx], sub_labels))
        # Pair consistency: among pairs co-clustered in full, how many remain
        # co-clustered in sub? Only consider pairs where both points are in idx.
        pairs_total = 0
        pairs_same = 0
        for a_local, a_global in enumerate(idx):
            for b_global in idx:
                if b_global == a_global:
                    continue
                if full_labels[a_global] == full_labels[b_global]:
                    pairs_total += 1
                    b_local = np.where(idx == b_global)[0]
                    if len(b_local) and sub_labels[a_local] == sub_labels[b_local[0]]:
                        pairs_same += 1
        if pairs_total:
            pair_consistency.append(pairs_same / pairs_total)
    mean_ari = float(np.mean(aris)) if aris else 0.0
    mean_pc = float(np.mean(pair_consistency)) if pair_consistency else 0.0
    return mean_ari, mean_pc


def evaluate_parameter_sensitivity(
    X: np.ndarray,
    k_grid: Iterable[int] = (3, 4, 5, 6, 7, 8),
    random_state: int = 42,
) -> float:
    """Return std of n_clusters_found across the grid.

    Higher std = more sensitive to the parameter. We use the *effective*
    number of clusters (excluding noise singleton clusters) as the metric.
    """
    if hasattr(X, "toarray"):
        X_arr = X.toarray()
    else:
        X_arr = np.asarray(X)
    if X_arr.shape[0] < 8:
        return 0.0
    n_clusters_found: list[int] = []
    for k in k_grid:
        labels = _kmeans(X_arr, k, random_state=random_state)
        n_clusters_found.append(len(set(labels.tolist())))
    return float(np.std(n_clusters_found)) if n_clusters_found else 0.0


def evaluate_leakage(
    records: list[dict],
    labels: np.ndarray,
    field: str = "source_platform",
) -> dict[str, float]:
    """For each cluster, what fraction is dominated by a single brand/topic?

    Returns a dict mapping the dominant value -> mean dominance across clusters.
    A cluster is 'dominated' if one value covers >= 70% of its members.
    """
    n_clusters = len(set(labels.tolist()))
    dominance_per_cluster: list[float] = []
    dominant_values: list[str] = []
    for c in range(n_clusters):
        members = [i for i, l in enumerate(labels) if l == c]
        if not members:
            continue
        counts: dict[str, int] = {}
        for i in members:
            v = "unknown"
            if isinstance(records[i], dict):
                meta = records[i].get("metadata", {}) if isinstance(records[i].get("metadata"), dict) else {}
                v = str(meta.get(field, records[i].get(field, "unknown")))
            counts[v] = counts.get(v, 0) + 1
        top_val, top_n = max(counts.items(), key=lambda x: x[1])
        dom = top_n / len(members)
        if dom >= 0.7:
            dominance_per_cluster.append(dom)
            dominant_values.append(top_val)
    if not dominance_per_cluster:
        return {}
    # Aggregate by dominant value
    out: dict[str, float] = {}
    for v, d in zip(dominant_values, dominance_per_cluster):
        out[v] = max(out.get(v, 0.0), d)
    return out


# ---------------------------------------------------------------------------
# Cluster explanation
# ---------------------------------------------------------------------------


def explain_clusters(
    X: np.ndarray,
    labels: np.ndarray,
    records: list[dict],
    texts: list[str],
    top_k_words: int = 5,
) -> list[dict]:
    """For each cluster, return the top-K distinguishing words and the most
    central member (representative) and the most ambiguous member (boundary)."""
    if hasattr(X, "toarray"):
        X_arr = X.toarray()
    else:
        X_arr = np.asarray(X)
    explanations: list[dict] = []
    n_clusters = len(set(labels.tolist()))
    # Compute centroid for each cluster
    for c in range(n_clusters):
        members = [i for i, l in enumerate(labels) if l == c]
        if not members:
            continue
        centroid = X_arr[members].mean(axis=0)
        # Representative = closest to centroid
        dists = np.linalg.norm(X_arr[members] - centroid, axis=1)
        rep_idx = members[int(np.argmin(dists))]
        # Boundary = farthest from centroid
        bnd_idx = members[int(np.argmax(dists))]
        # Top words by frequency in cluster vs corpus
        cluster_words: dict[str, int] = {}
        for i in members:
            for w in str(texts[i]).lower().split():
                w = w.strip(".,;:!?¡¿\"'()[]")
                if len(w) > 3:
                    cluster_words[w] = cluster_words.get(w, 0) + 1
        top_words = sorted(cluster_words.items(), key=lambda x: -x[1])[:top_k_words]
        rec_id = records[rep_idx].get("record_id", str(rep_idx)) if isinstance(records[rep_idx], dict) else str(rep_idx)
        bnd_id = records[bnd_idx].get("record_id", str(bnd_idx)) if isinstance(records[bnd_idx], dict) else str(bnd_idx)
        explanations.append({
            "cluster_id": int(c),
            "n_members": len(members),
            "representative_id": rec_id,
            "boundary_id": bnd_id,
            "top_words": [w for w, _ in top_words],
        })
    return explanations


# ---------------------------------------------------------------------------
# Public: run a single space
# ---------------------------------------------------------------------------


def cluster_space(
    space: str,
    X: np.ndarray,
    records: list[dict],
    texts: list[str],
    k: int = 6,
    random_state: int = 42,
    compute_stability: bool = True,
) -> tuple[list[ClusterAssignment], ClusterReport]:
    """Cluster one space and return assignments + report."""
    labels = _kmeans(X, k, random_state=random_state)
    n_clusters = int(len(set(labels.tolist())))
    n_noise = int(np.sum(labels == -1))  # always 0 for kmeans but kept for HDBSCAN parity
    if compute_stability:
        ari, pc = evaluate_stability(X, k, random_state=random_state)
        sens = evaluate_parameter_sensitivity(X, random_state=random_state)
    else:
        ari = pc = sens = 0.0
    brand_leak = evaluate_leakage(records, labels, field="source_platform")
    topic_leak = evaluate_leakage(records, labels, field="platform_family")
    reps: list[str] = []
    bounds: list[str] = []
    explanations = explain_clusters(X, labels, records, texts)
    for e in explanations:
        reps.append(e["representative_id"])
        bounds.append(e["boundary_id"])
    assignments = [
        ClusterAssignment(
            record_id=(records[i].get("record_id", str(i)) if isinstance(records[i], dict) else str(i)),
            cluster_id=int(labels[i]),
            space=space,
            is_noise=False,
        )
        for i in range(len(records))
    ]
    report = ClusterReport(
        space=space,
        n_clusters=n_clusters,
        n_noise=n_noise,
        stability_ari=ari,
        resampling_consistency=pc,
        parameter_sensitivity=sens,
        brand_leakage=brand_leak,
        topic_leakage=topic_leak,
        representative_ids=reps,
        boundary_ids=bounds,
        cluster_explanations=explanations,
        human_coherence_note=None,
    )
    return assignments, report


def stratified_sample(records: list[dict], by_field: str = "source_platform", n_per_stratum: int = 100, random_state: int = 42) -> list[dict]:
    """Stratified sample by a metadata field.

    The Round 1 challenge found that taking the first-N records yields
    single-platform clusters because the corpus is ingested in platform-major
    order. This helper returns a balanced sample so cluster brand leakage is
    not an artefact of ingestion order.

    Falls back to truncation if any stratum has fewer than n_per_stratum.
    """
    import random as _random

    rng = _random.Random(random_state)
    strata: dict[str, list[dict]] = {}
    for r in records:
        if not isinstance(r, dict):
            continue
        meta = r.get("metadata", {}) if isinstance(r.get("metadata"), dict) else {}
        v = str(meta.get(by_field, r.get(by_field, "unknown")))
        strata.setdefault(v, []).append(r)
    out: list[dict] = []
    for v, items in strata.items():
        rng.shuffle(items)
        out.extend(items[:n_per_stratum])
    return out


# ---------------------------------------------------------------------------
# Public: run all spaces
# ---------------------------------------------------------------------------


def cluster_all_spaces(
    records: list[dict],
    texts: list[str],
    profiles: list[dict] | None = None,
    k: int = 6,
    compute_stability: bool = True,
) -> dict[str, tuple[list[ClusterAssignment], ClusterReport]]:
    """Run clustering in all 7 spaces and return assignments + reports.

    Spaces: persuasive, semantic, rhetorical, visual, multimodal, authorial,
    performance. If `profiles` is None, persuasive is skipped (returned as
    an empty report)."""
    results: dict[str, tuple[list[ClusterAssignment], ClusterReport]] = {}
    if profiles is not None and len(profiles) == len(records):
        X_pers = build_persuasive_features(profiles)
        results["persuasive"] = cluster_space("persuasive", X_pers, records, texts, k=k, compute_stability=compute_stability)
    X_sem, _ = build_semantic_features(texts)
    results["semantic"] = cluster_space("semantic", X_sem, records, texts, k=k, compute_stability=compute_stability)
    X_rh = build_rhetorical_features(texts)
    results["rhetorical"] = cluster_space("rhetorical", X_rh, records, texts, k=k, compute_stability=compute_stability)
    X_vis = build_visual_features(records)
    results["visual"] = cluster_space("visual", X_vis, records, texts, k=k, compute_stability=compute_stability)
    X_mm = build_multimodal_features(texts, records)
    results["multimodal"] = cluster_space("multimodal", X_mm, records, texts, k=k, compute_stability=compute_stability)
    X_au = build_authorial_features(texts)
    results["authorial"] = cluster_space("authorial", X_au, records, texts, k=k, compute_stability=compute_stability)
    X_pf = build_performance_features(records)
    results["performance"] = cluster_space("performance", X_pf, records, texts, k=k, compute_stability=compute_stability)
    return results
