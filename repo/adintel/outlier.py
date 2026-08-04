"""Outlier and novelty analysis (adintel.outlier).

The spec requires ten outlier types, each with:
  comparison population, feature space, score, method, supporting features,
  alternative explanation, uncertainty, review status.

Implemented types:
  creative_novelty, unusual_technique_combination, style_outlier,
  visual_outlier, performance_overperformer, performance_underperformer,
  temporal_outlier, duplicate, extraction_error, metadata_error, model_error.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from typing import Iterable

import numpy as np

from adintel.types import OutlierReport

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_dense(X) -> np.ndarray:
    if hasattr(X, "toarray"):
        return X.toarray()
    return np.asarray(X)


def _zscore(scores: np.ndarray) -> np.ndarray:
    if scores.size == 0:
        return scores
    mu = float(np.mean(scores))
    sigma = float(np.std(scores))
    if sigma < 1e-9:
        return np.zeros_like(scores)
    return (scores - mu) / sigma


def _sigmoid(z: float) -> float:
    return float(1.0 / (1.0 + np.exp(-z)))


# ---------------------------------------------------------------------------
# 1. Creative novelty
# ---------------------------------------------------------------------------


def detect_creative_novelty(
    texts: list[str],
    records: list[dict],
    novelty_quantile: float = 0.95,
) -> list[OutlierReport]:
    """Creative novelty = ads whose semantic content is far from the corpus
    centroid. Uses TF-IDF cosine distance to centroid."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    if not texts:
        return []
    vec = TfidfVectorizer(ngram_range=(1, 2), min_df=1, max_features=1500, sublinear_tf=True, lowercase=True, strip_accents="unicode")
    X = vec.fit_transform(texts)
    centroid = X.mean(axis=0)
    centroid = np.asarray(centroid)
    sims = cosine_similarity(X, centroid).ravel()
    dists = 1.0 - sims
    threshold = float(np.quantile(dists, novelty_quantile))
    out: list[OutlierReport] = []
    for i, d in enumerate(dists):
        if d >= threshold:
            rid = records[i].get("record_id", str(i)) if isinstance(records[i], dict) else str(i)
            out.append(OutlierReport(
                record_id=rid,
                kind="creative_novelty",
                score=float(d),
                method="tfidf_cosine_distance_to_centroid",
                comparison_population="full corpus",
                feature_space="semantic_tfidf",
                supporting_features={"distance_to_centroid": float(d), "threshold": threshold},
                alternative_explanation="Ad may be novel because it covers a topic the corpus rarely covers; review before classifying as creative innovation.",
                uncertainty=0.4,
            ))
    return out


# ---------------------------------------------------------------------------
# 2. Unusual technique combination
# ---------------------------------------------------------------------------


def detect_unusual_technique_combination(
    label_sets: list[set[str]],
    records: list[dict],
    support_threshold: int = 5,
) -> list[OutlierReport]:
    """Flag ads whose label-set is rare (co-occurrence count below support_threshold)."""
    pair_counts: Counter[tuple[str, ...]] = Counter()
    for s in label_sets:
        for combo in _all_pairs(sorted(s)):
            pair_counts[combo] += 1
    out: list[OutlierReport] = []
    for i, s in enumerate(label_sets):
        if len(s) < 2:
            continue
        rare_combos = []
        for combo in _all_pairs(sorted(s)):
            if pair_counts[combo] < support_threshold:
                rare_combos.append(combo)
        if rare_combos:
            rid = records[i].get("record_id", str(i)) if isinstance(records[i], dict) else str(i)
            out.append(OutlierReport(
                record_id=rid,
                kind="unusual_technique_combination",
                score=min(1.0, len(rare_combos) / 5.0),
                method="rare_label_pair_support",
                comparison_population="full corpus label co-occurrences",
                feature_space="technique_label_sets",
                supporting_features={"rare_combos": ["+".join(c) for c in rare_combos[:5]], "n_rare": len(rare_combos)},
                alternative_explanation="A rare combination may be a genuinely novel technique mix OR an annotation artefact; review labels.",
                uncertainty=0.5,
            ))
    return out


def _all_pairs(items: list[str]) -> list[tuple[str, ...]]:
    return [tuple(sorted((a, b))) for i, a in enumerate(items) for b in items[i + 1:]]


# ---------------------------------------------------------------------------
# 3. Style outlier
# ---------------------------------------------------------------------------


def detect_style_outliers(texts: list[str], records: list[dict], z_threshold: float = 2.5) -> list[OutlierReport]:
    """Style outlier = ads whose rhetorical-style feature vector is far from
    the corpus mean (z-score in rhetorical-style space)."""
    from adintel.clustering import build_rhetorical_features
    from sklearn.metrics.pairwise import euclidean_distances

    if len(texts) < 5:
        return []
    X = build_rhetorical_features(texts)
    if X.shape[0] < 5:
        return []
    centroid = X.mean(axis=0)
    dists = euclidean_distances(X, centroid.reshape(1, -1)).ravel()
    z = _zscore(dists)
    out: list[OutlierReport] = []
    for i, zi in enumerate(z):
        if abs(zi) >= z_threshold:
            rid = records[i].get("record_id", str(i)) if isinstance(records[i], dict) else str(i)
            out.append(OutlierReport(
                record_id=rid,
                kind="style_outlier",
                score=_sigmoid(abs(zi) - z_threshold),
                method="rhetorical_feature_z_score",
                comparison_population="full corpus",
                feature_space="rhetorical_style",
                supporting_features={"z_score": float(zi), "distance": float(dists[i])},
                alternative_explanation="Style outlier may indicate a different author, format, or platform norm rather than a problematic ad.",
                uncertainty=0.4,
            ))
    return out


# ---------------------------------------------------------------------------
# 4. Visual outlier
# ---------------------------------------------------------------------------


def detect_visual_outliers(records: list[dict], z_threshold: float = 2.5) -> list[OutlierReport]:
    """Visual outlier = ads whose image_count or raw_size_bucket is far from
    the corpus mean. Note: limited because we don't have image pixels."""
    from adintel.clustering import build_visual_features
    if len(records) < 5:
        return []
    X = build_visual_features(records)
    centroid = X.mean(axis=0)
    dists = np.linalg.norm(X - centroid, axis=1)
    z = _zscore(dists)
    out: list[OutlierReport] = []
    for i, zi in enumerate(z):
        if abs(zi) >= z_threshold:
            rid = records[i].get("record_id", str(i)) if isinstance(records[i], dict) else str(i)
            out.append(OutlierReport(
                record_id=rid,
                kind="visual_outlier",
                score=_sigmoid(abs(zi) - z_threshold),
                method="visual_metadata_z_score",
                comparison_population="full corpus",
                feature_space="visual_metadata_proxy",
                supporting_features={"z_score": float(zi), "image_count": float(X[i, 0]), "raw_size_bucket": float(X[i, 1])},
                alternative_explanation="v1 corpus has no image pixels; this is a metadata-only proxy. Real visual outlier detection requires archived pixels.",
                uncertainty=0.6,
            ))
    return out


# ---------------------------------------------------------------------------
# 5 & 6. Performance over/under-performers
# ---------------------------------------------------------------------------

# The v1 corpus has no real performance metrics (no spend, impressions, CTR).
# We use quality_score as a proxy but EXPLICITLY mark the report as proxy-only.


def detect_performance_outliers(
    records: list[dict],
    z_threshold: float = 2.0,
) -> tuple[list[OutlierReport], list[OutlierReport]]:
    """Return (overperformers, underperformers) based on quality_score z-score.

    WARNING: This is a PROXY. The corpus has no spend/impressions/CTR. The
    dashboard must surface this limitation in every performance outlier card.
    """
    if len(records) < 5:
        return [], []
    scores = np.array([
        float(records[i].get("metadata", {}).get("quality_score", 0.0)) if isinstance(records[i], dict) else 0.0
        for i in range(len(records))
    ])
    z = _zscore(scores)
    over: list[OutlierReport] = []
    under: list[OutlierReport] = []
    for i, zi in enumerate(z):
        rid = records[i].get("record_id", str(i)) if isinstance(records[i], dict) else str(i)
        if zi >= z_threshold:
            over.append(OutlierReport(
                record_id=rid,
                kind="performance_overperformer",
                score=_sigmoid(zi - z_threshold),
                method="quality_score_z_score",
                comparison_population="full corpus",
                feature_space="performance_proxy_quality_score",
                supporting_features={"z_score": float(zi), "quality_score": float(scores[i])},
                alternative_explanation="quality_score is a rebuild-pipeline proxy, NOT a real performance metric. Treat as descriptive only.",
                uncertainty=0.8,
            ))
        elif zi <= -z_threshold:
            under.append(OutlierReport(
                record_id=rid,
                kind="performance_underperformer",
                score=_sigmoid(-zi - z_threshold),
                method="quality_score_z_score",
                comparison_population="full corpus",
                feature_space="performance_proxy_quality_score",
                supporting_features={"z_score": float(zi), "quality_score": float(scores[i])},
                alternative_explanation="Low quality_score is a rebuild-pipeline proxy, NOT a real performance metric. May indicate an extraction problem rather than a genuinely underperforming ad. Treat as descriptive only.",
                uncertainty=0.8,
            ))
    return over, under


# ---------------------------------------------------------------------------
# 7. Temporal outlier
# ---------------------------------------------------------------------------


def detect_temporal_outliers(records: list[dict], z_threshold: float = 3.0) -> list[OutlierReport]:
    """Temporal outlier = ads collected at timestamps far from the median
    collection window. Useful for detecting batch effects or scraping glitches."""
    from datetime import datetime

    timestamps: list[float] = []
    valid_indices: list[int] = []
    for i, r in enumerate(records):
        if not isinstance(r, dict):
            continue
        ts = r.get("collected_at")
        if not ts:
            continue
        try:
            # ISO-8601
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            timestamps.append(dt.timestamp())
            valid_indices.append(i)
        except Exception:
            continue
    if len(timestamps) < 5:
        return []
    arr = np.array(timestamps)
    median = float(np.median(arr))
    # Convert to days from median
    days_off = (arr - median) / 86400.0
    z = _zscore(days_off)
    out: list[OutlierReport] = []
    for j, zi in enumerate(z):
        if abs(zi) >= z_threshold:
            i = valid_indices[j]
            rid = records[i].get("record_id", str(i)) if isinstance(records[i], dict) else str(i)
            out.append(OutlierReport(
                record_id=rid,
                kind="temporal_outlier",
                score=_sigmoid(abs(zi) - z_threshold),
                method="collection_timestamp_z_score",
                comparison_population="full corpus collection timestamps",
                feature_space="collection_time",
                supporting_features={"z_score": float(zi), "days_from_median": float(days_off[j])},
                alternative_explanation="Temporal outlier usually indicates a batch collection event or scraping glitch, not ad content.",
                uncertainty=0.3,
            ))
    return out


# ---------------------------------------------------------------------------
# 8. Duplicates
# ---------------------------------------------------------------------------


def detect_duplicates(texts: list[str], records: list[dict]) -> list[OutlierReport]:
    """Exact-text duplicates by SHA-256. Same-text ads are duplicates by
    definition (not by model similarity)."""
    seen: dict[str, int] = {}
    out: list[OutlierReport] = []
    for i, t in enumerate(texts):
        h = hashlib.sha256(t.encode("utf-8")).hexdigest()
        if h in seen:
            j = seen[h]
            rid_i = records[i].get("record_id", str(i)) if isinstance(records[i], dict) else str(i)
            out.append(OutlierReport(
                record_id=rid_i,
                kind="duplicate",
                score=1.0,
                method="exact_text_sha256",
                comparison_population="full corpus",
                feature_space="exact_text_hash",
                supporting_features={"sha256": h, "original_record_index": j},
                alternative_explanation="Exact-text duplicate by hash. This is the only outlier type with certainty 1.0.",
                uncertainty=0.0,
            ))
        else:
            seen[h] = i
    return out


# ---------------------------------------------------------------------------
# 9. Extraction errors
# ---------------------------------------------------------------------------

_EXTRACTION_ERROR_PATTERNS = [
    re.compile(r"^error\b", re.I),
    re.compile(r"\\u00", re.I),  # unrendered unicode escapes
    re.compile(r"\bobject Object\b", re.I),
    re.compile(r"\bundefined\b", re.I),
    re.compile(r"\bnull\b", re.I),
    re.compile(r"^[\W_]+$"),  # punctuation/symbols only
]


def detect_extraction_errors(texts: list[str], records: list[dict], min_words: int = 3) -> list[OutlierReport]:
    """Flag ads with obvious extraction-error markers."""
    out: list[OutlierReport] = []
    for i, t in enumerate(texts):
        if not t or len(re.findall(r"\b\w+\b", t)) < min_words:
            rid = records[i].get("record_id", str(i)) if isinstance(records[i], dict) else str(i)
            out.append(OutlierReport(
                record_id=rid,
                kind="extraction_error",
                score=0.9,
                method="extraction_error_pattern_match",
                comparison_population="full corpus",
                feature_space="text_surface_patterns",
                supporting_features={"word_count": len(re.findall(r"\b\w+\b", t))},
                alternative_explanation="Apparent extraction failure. Investigate the raw archive before treating as a real ad.",
                uncertainty=0.2,
            ))
            continue
        for pat in _EXTRACTION_ERROR_PATTERNS:
            if pat.search(t):
                rid = records[i].get("record_id", str(i)) if isinstance(records[i], dict) else str(i)
                out.append(OutlierReport(
                    record_id=rid,
                    kind="extraction_error",
                    score=0.8,
                    method="extraction_error_pattern_match",
                    comparison_population="full corpus",
                    feature_space="text_surface_patterns",
                    supporting_features={"pattern": pat.pattern},
                    alternative_explanation="Surface pattern suggests extraction error. Inspect raw HTML.",
                    uncertainty=0.3,
                ))
                break
    return out


# ---------------------------------------------------------------------------
# 10. Metadata errors
# ---------------------------------------------------------------------------


def detect_metadata_errors(records: list[dict]) -> list[OutlierReport]:
    """Flag records with missing required fields, malformed metadata, or
    inconsistent platform_family vs source_platform."""
    out: list[OutlierReport] = []
    required = ("record_id", "source_platform", "collected_at", "title", "body_redacted")
    for i, r in enumerate(records):
        if not isinstance(r, dict):
            out.append(OutlierReport(
                record_id=str(i),
                kind="metadata_error",
                score=1.0,
                method="metadata_schema_check",
                comparison_population="full corpus",
                feature_space="metadata_schema",
                supporting_features={"missing": "all"},
                alternative_explanation="Record is not a dict.",
                uncertainty=0.0,
            ))
            continue
        missing = [f for f in required if not r.get(f)]
        if missing:
            out.append(OutlierReport(
                record_id=r.get("record_id", str(i)),
                kind="metadata_error",
                score=0.7,
                method="metadata_schema_check",
                comparison_population="full corpus",
                feature_space="metadata_schema",
                supporting_features={"missing_fields": missing},
                alternative_explanation="Missing required fields. May be a partial scrape.",
                uncertainty=0.3,
            ))
            continue
        # Platform family consistency
        meta = r.get("metadata", {}) if isinstance(r.get("metadata"), dict) else {}
        sp = str(r.get("source_platform", "")).lower()
        pf = str(meta.get("platform_family", "")).lower()
        if pf and pf not in sp and sp not in pf:
            out.append(OutlierReport(
                record_id=r.get("record_id", str(i)),
                kind="metadata_error",
                score=0.6,
                method="metadata_cross_field_check",
                comparison_population="full corpus",
                feature_space="metadata_schema",
                supporting_features={"source_platform": sp, "platform_family": pf},
                alternative_explanation="source_platform and platform_family disagree. Possible metadata corruption.",
                uncertainty=0.4,
            ))
    return out


# ---------------------------------------------------------------------------
# 11. Model errors
# ---------------------------------------------------------------------------


def detect_model_errors(
    predictions: list[dict],
    records: list[dict],
    confidence_floor: float = 0.2,
    disagreement_threshold: int = 2,
) -> list[OutlierReport]:
    """Flag predictions where the model itself signals low confidence or
    checkpoint disagreement."""
    out: list[OutlierReport] = []
    for i, pred in enumerate(predictions):
        rid = records[i].get("record_id", str(i)) if i < len(records) and isinstance(records[i], dict) else str(i)
        # Low confidence
        conf = float(pred.get("confidence", 1.0))
        if conf < confidence_floor:
            out.append(OutlierReport(
                record_id=rid,
                kind="model_error",
                score=1.0 - conf,
                method="low_model_confidence",
                comparison_population="full corpus predictions",
                feature_space="model_confidence",
                supporting_features={"confidence": conf},
                alternative_explanation="Low model confidence. May indicate out-of-distribution input or genuinely ambiguous ad.",
                uncertainty=0.5,
            ))
            continue
        # Checkpoint disagreement
        disagreement = pred.get("disagreement", [])
        if isinstance(disagreement, list) and len(disagreement) >= disagreement_threshold:
            out.append(OutlierReport(
                record_id=rid,
                kind="model_error",
                score=min(1.0, len(disagreement) / 5.0),
                method="checkpoint_disagreement",
                comparison_population="full corpus predictions",
                feature_space="model_checkpoint_disagreement",
                supporting_features={"n_disagreeing": len(disagreement), "disagreeing": disagreement[:5]},
                alternative_explanation="Checkpoint disagreement. Route to human review per the spec's human-routing rule.",
                uncertainty=0.4,
            ))
    return out


# ---------------------------------------------------------------------------
# Public: run all outlier detectors
# ---------------------------------------------------------------------------


def detect_all_outliers(
    texts: list[str],
    records: list[dict],
    label_sets: list[set[str]] | None = None,
    predictions: list[dict] | None = None,
) -> list[OutlierReport]:
    """Run all 10+ outlier detectors and return a flat list of OutlierReports.

    Each report carries its own kind, score, method, comparison population,
    feature space, supporting features, alternative explanation, uncertainty,
    and review status — per spec."""
    out: list[OutlierReport] = []
    out.extend(detect_creative_novelty(texts, records))
    if label_sets is not None:
        out.extend(detect_unusual_technique_combination(label_sets, records))
    out.extend(detect_style_outliers(texts, records))
    out.extend(detect_visual_outliers(records))
    over, under = detect_performance_outliers(records)
    out.extend(over)
    out.extend(under)
    out.extend(detect_temporal_outliers(records))
    out.extend(detect_duplicates(texts, records))
    out.extend(detect_extraction_errors(texts, records))
    out.extend(detect_metadata_errors(records))
    if predictions is not None:
        out.extend(detect_model_errors(predictions, records))
    return out
