#!/usr/bin/env python3
"""Generate candidate inferences and a self-contained HTML review report."""

from __future__ import annotations

import argparse
import html
import json
import math
import re
import shutil
import sys
import unicodedata
import warnings
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import joblib
import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sklearn.cluster import MiniBatchKMeans
from sklearn.decomposition import TruncatedSVD
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.ensemble import IsolationForest
from sklearn.exceptions import ConvergenceWarning
from sklearn.metrics import (
    adjusted_rand_score,
    calinski_harabasz_score,
    davies_bouldin_score,
    normalized_mutual_info_score,
    silhouette_score,
)
from sklearn.neural_network import MLPRegressor

DEFAULT_DOCS = ROOT / "data/annotation/documents.jsonl"
DEFAULT_ANNOTATIONS = ROOT / "data/annotation/council_resolved_annotations.jsonl"
DEFAULT_MODEL = ROOT / "models/manipulation_council_tfidf_ovr.joblib"
DEFAULT_JSON = ROOT / "reports/council_candidate_inferences.json"
DEFAULT_HTML = ROOT / "reports/ad_manipulation_report.html"
DEFAULT_MODEL_REPORT = ROOT / "reports/council_candidate_model_report.json"
DEFAULT_SEGMENT_REPORT = ROOT / "reports/segment_model_analysis.json"

MANIP_LABELS = {
    "conditional_financial_support",
    "economic_vulnerability_targeting",
    "privacy_or_secrecy_pressure",
    "guilt_or_shame_pressure",
    "deceptive_assurance",
    "fear_or_threat",
}
CONTEXT_CAP = 0.25
REPORT_ASSET_DIR = ROOT / "reports/assets"

SPANISH_STOPWORDS = {
    "a",
    "al",
    "algo",
    "ante",
    "aqui",
    "aquí",
    "asi",
    "así",
    "cada",
    "como",
    "con",
    "contra",
    "cual",
    "cuando",
    "de",
    "del",
    "desde",
    "donde",
    "dos",
    "el",
    "ella",
    "ellas",
    "ellos",
    "en",
    "entre",
    "eres",
    "es",
    "esa",
    "ese",
    "eso",
    "esta",
    "está",
    "este",
    "esto",
    "la",
    "las",
    "le",
    "lo",
    "los",
    "mas",
    "más",
    "me",
    "mi",
    "mis",
    "no",
    "o",
    "para",
    "pero",
    "por",
    "que",
    "qué",
    "se",
    "si",
    "sí",
    "sin",
    "su",
    "sus",
    "te",
    "tu",
    "un",
    "una",
    "uno",
    "y",
    "ya",
}

LABEL_FAMILIES = {
    "conditional_financial_support": ("Manipulation", "conditional exchange"),
    "economic_vulnerability_targeting": ("Manipulation", "vulnerability targeting"),
    "privacy_or_secrecy_pressure": ("Manipulation", "secrecy/concealment"),
    "guilt_or_shame_pressure": ("Manipulation", "social pressure"),
    "deceptive_assurance": ("Manipulation", "assurance/minimization"),
    "fear_or_threat": ("Manipulation", "fear/loss"),
    "reciprocity_obligation": ("Persuasion", "reciprocity"),
    "platform_migration": ("Persuasion", "private-channel migration"),
    "sexualized_appearance_condition": ("Manipulation", "appearance/sexual condition"),
    "age_or_youth_targeting": ("Manipulation", "age targeting"),
    "education_or_student_targeting": ("Manipulation", "student targeting"),
    "family_obligation_targeting": ("Manipulation", "family obligation"),
    "transactional_ambiguity": ("Manipulation", "ambiguous exchange"),
    "commitment_escalation": ("Persuasion", "dependency/escalation"),
    "foot_in_the_door": ("Persuasion", "low-friction first step"),
    "social_proof": ("Persuasion", "social proof"),
    "authority_or_status_appeal": ("Persuasion", "status/authority"),
    "exclusivity_or_special_treatment": ("Persuasion", "special treatment"),
    "scarcity_or_urgency": ("Persuasion", "urgency/scarcity"),
    "repetition_or_campaign_escalation": ("Persuasion", "campaign repetition"),
}


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def context_score(context: dict) -> float:
    score = 0.0
    if context.get("is_paid_or_premium_marker") or context.get("is_featured_marker"):
        score += 0.08
    if int(context.get("followers_count") or 0) > 0:
        score += 0.06
    if int(context.get("facebook_reactions_approx") or 0) > 0 or int(context.get("facebook_comments_approx") or 0) > 0:
        score += 0.06
    if context.get("image_available"):
        score += 0.05
    return min(CONTEXT_CAP, score)


def score_record(text: str, spans: list[dict], context: dict) -> dict:
    text_len = max(1, len(text))
    capped = spans[:]
    burden = min(1.0, sum((span.get("intensity") or 0) * sum(end - start for start, end in span["segments"]) for span in capped) / (text_len * 4))
    manip_burden = min(
        1.0,
        sum(
            (span.get("harm_risk") or 0) * sum(end - start for start, end in span["segments"])
            for span in capped
            if span["label"] in MANIP_LABELS
        )
        / (text_len * 3),
    )
    max_intensity = max((span.get("intensity") or 0 for span in capped), default=0) / 4
    max_severity = max((span.get("harm_risk") or 0 for span in capped), default=0) / 3
    diversity = min(1.0, len({span["label"] for span in capped}) / 8)
    repetition = 1.0 if any(span["label"] in {"commitment_escalation", "repetition_or_campaign_escalation"} for span in capped) else 0.0
    vulnerability = 1.0 if any(span["label"] in {"economic_vulnerability_targeting", "age_or_youth_targeting", "education_or_student_targeting", "family_obligation_targeting"} for span in capped) else 0.0
    concealment = 1.0 if any(span["label"] in {"privacy_or_secrecy_pressure", "platform_migration"} for span in capped) else 0.0
    persuasion = 100 * (0.40 * burden + 0.25 * max_intensity + 0.20 * diversity + 0.15 * repetition)
    manipulation = 100 * (0.40 * manip_burden + 0.25 * max_severity + 0.20 * vulnerability + 0.15 * concealment)
    exposure = context_score(context) / CONTEXT_CAP
    review_priority = 0.70 * manipulation + 0.20 * persuasion + 10 * exposure
    return {
        "persuasion": round(persuasion, 2),
        "manipulation": round(manipulation, 2),
        "review_priority": round(review_priority, 2),
        "arithmetic": {
            "persuasion": {
                "span_burden": round(burden, 4),
                "max_intensity": round(max_intensity, 4),
                "technique_diversity": round(diversity, 4),
                "repetition_escalation": round(repetition, 4),
            },
            "manipulation": {
                "severity_span_burden": round(manip_burden, 4),
                "max_severity": round(max_severity, 4),
                "vulnerability_conditionality": round(vulnerability, 4),
                "concealment_coercion": round(concealment, 4),
            },
            "context_exposure": round(exposure, 4),
        },
    }


def span_excerpt(text: str, span: dict) -> str:
    return " … ".join(text[start:end] for start, end in span["segments"])


def fold_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def safe_tokens(text: str) -> list[str]:
    folded = fold_text(text.replace("[REDACTED_CONTACT]", " redacted_contact "))
    tokens = re.findall(r"[a-z0-9_áéíóúñü]+", folded)
    return [token for token in tokens if len(token) >= 3 and token not in SPANISH_STOPWORDS and not token.startswith("http")]


def phrase_terms(tokens: list[str], max_terms: int = 70) -> list[str]:
    terms: list[str] = []
    for n in (2, 1):
        for index in range(max(0, len(tokens) - n + 1)):
            term = " ".join(tokens[index : index + n])
            if term not in terms:
                terms.append(term)
            if len(terms) >= max_terms:
                return terms
    return terms


def rounded_float(value: float, digits: int = 4) -> float:
    if not math.isfinite(float(value)):
        return 0.0
    return round(float(value), digits)


def build_global_explainability(artifact: dict, model_report: dict) -> dict:
    pipeline = artifact["model"]
    labels = artifact["labels"]
    vectorizer = pipeline.named_steps["tfidf"]
    classifier = pipeline.named_steps["clf"]
    terms = np.array(vectorizer.get_feature_names_out())
    metrics = model_report.get("metrics", {}).get("test", {}).get("per_label", {})
    label_rows = []
    for index, label in enumerate(labels):
        estimator = classifier.estimators_[index]
        coef = estimator.coef_[0]
        top_positive = coef.argsort()[::-1][:12]
        top_negative = coef.argsort()[:8]
        metric = metrics.get(label, {})
        support = int(metric.get("support") or 0)
        label_rows.append(
            {
                "label": label,
                "family": LABEL_FAMILIES.get(label, ("Persuasion", "project label"))[0],
                "type": LABEL_FAMILIES.get(label, ("Persuasion", "project label"))[1],
                "support": support,
                "f1": metric.get("f1"),
                "precision": metric.get("precision"),
                "recall": metric.get("recall"),
                "roc_auc": metric.get("roc_auc"),
                "low_support": support < 20,
                "top_positive_terms": [
                    {"term": str(terms[i]), "weight": rounded_float(coef[i])}
                    for i in top_positive
                    if coef[i] > 0
                ],
                "contrast_terms": [
                    {"term": str(terms[i]), "weight": rounded_float(coef[i])}
                    for i in top_negative
                    if coef[i] < 0
                ],
            }
        )
    return {
        "method": "TF-IDF logistic one-vs-rest coefficient inspection; positive weights increase the candidate-model score for the selected label.",
        "caveats": [
            "Coefficient explanations are model internals, not proof of manipulation.",
            "Correlated terms can share or mask importance.",
            "Metrics measure agreement with candidate council labels, not human gold.",
        ],
        "labels": label_rows,
    }


def build_term_network(rows: list[dict], max_terms: int = 80, max_edges: int = 220) -> dict:
    term_counts: Counter[str] = Counter()
    term_platforms: dict[str, Counter[str]] = defaultdict(Counter)
    term_labels: dict[str, Counter[str]] = defaultdict(Counter)
    term_examples: dict[str, list[str]] = defaultdict(list)
    cooc: Counter[tuple[str, str]] = Counter()
    label_term_edges: Counter[tuple[str, str]] = Counter()
    platform_term_edges: Counter[tuple[str, str]] = Counter()
    doc_terms_by_id: dict[str, set[str]] = {}

    for row in rows:
        tokens = safe_tokens(row["text"])
        terms = phrase_terms(tokens, 55)
        unique_terms = set(terms)
        doc_terms_by_id[row["record_id"]] = unique_terms
        for term in unique_terms:
            term_counts[term] += 1
            term_platforms[term][row["platform"]] += 1
            if len(term_examples[term]) < 3:
                term_examples[term].append(row["record_id"])
            for label in row["labels"]:
                term_labels[term][label] += 1
                label_term_edges[(label, term)] += 1
            platform_term_edges[(row["platform"], term)] += 1
        top_doc_terms = sorted(unique_terms, key=lambda term: (-term_counts[term], term))[:14]
        for left_index, left in enumerate(top_doc_terms):
            for right in top_doc_terms[left_index + 1 :]:
                a, b = sorted((left, right))
                cooc[(a, b)] += 1

    selected_terms = {term for term, _ in term_counts.most_common(max_terms)}
    nodes = []
    for label in sorted({label for row in rows for label in row["labels"]}):
        family, label_type = LABEL_FAMILIES.get(label, ("Persuasion", "project label"))
        nodes.append({"id": f"label:{label}", "name": label, "kind": "label", "family": family, "type": label_type, "weight": 1})
    for platform in sorted({row["platform"] for row in rows}):
        nodes.append({"id": f"platform:{platform}", "name": platform, "kind": "platform", "weight": 1})
    for term in sorted(selected_terms, key=lambda item: (-term_counts[item], item)):
        nodes.append(
            {
                "id": f"term:{term}",
                "name": term,
                "kind": "term",
                "weight": int(term_counts[term]),
                "platform_counts": dict(term_platforms[term].most_common(5)),
                "label_counts": dict(term_labels[term].most_common(8)),
                "examples": term_examples[term],
            }
        )

    edges = []
    for (left, right), weight in cooc.most_common(max_edges):
        if left in selected_terms and right in selected_terms and weight >= 4:
            edges.append({"source": f"term:{left}", "target": f"term:{right}", "kind": "term_term", "weight": int(weight)})
    for (label, term), weight in label_term_edges.most_common(max_edges):
        if term in selected_terms and weight >= 8:
            edges.append({"source": f"label:{label}", "target": f"term:{term}", "kind": "label_term", "weight": int(weight)})
    for (platform, term), weight in platform_term_edges.most_common(80):
        if term in selected_terms and weight >= 12:
            edges.append({"source": f"platform:{platform}", "target": f"term:{term}", "kind": "platform_term", "weight": int(weight)})

    return {
        "method": "Accent-folded Spanish term and phrase co-occurrence over redacted ad text; edges are capped for responsiveness.",
        "nodes": nodes,
        "edges": sorted(edges, key=lambda row: row["weight"], reverse=True)[: max_edges + 80],
        "top_terms": [{"term": term, "count": int(count), "examples": term_examples[term]} for term, count in term_counts.most_common(30)],
    }


def representative_rows(rows: list[dict], limit: int = 900) -> list[dict]:
    selected: dict[str, dict] = {}
    for key in ("review_priority", "manipulation", "persuasion"):
        for row in sorted(rows, key=lambda item: item["scores"][key], reverse=True)[:250]:
            selected[row["record_id"]] = row
    for platform in sorted({row["platform"] for row in rows}):
        platform_rows = [row for row in rows if row["platform"] == platform]
        step = max(1, len(platform_rows) // 80)
        for row in platform_rows[::step][:80]:
            selected[row["record_id"]] = row
    return list(selected.values())[:limit]


def characterize_cluster(
    top_terms: list[dict],
    label_counts: Counter,
    platform_counts: Counter,
    avg_review: float,
    size: int,
) -> dict:
    terms = [str(term["term"]) for term in top_terms[:8]]
    term_blob = " ".join(terms)
    labels = set(label_counts)
    leading_platform = platform_counts.most_common(1)[0][0] if platform_counts else "mixed platforms"
    leading_labels = [label for label, _ in label_counts.most_common(4)]

    if {"conditional_financial_support", "transactional_ambiguity"} & labels and {"economic_vulnerability_targeting", "education_or_student_targeting", "family_obligation_targeting"} & labels:
        title = "Help-with-conditions vulnerability pattern"
        likely_pattern = "Economic support is framed around people who may need money, studying support, or family help, while the exact exchange can be conditional or ambiguous."
        risk = "Higher review priority: check whether the offer creates pressure through need, dependency, secrecy, or implied companionship."
    elif "platform_migration" in labels and "privacy_or_secrecy_pressure" in labels:
        title = "Private-channel and discretion pattern"
        likely_pattern = "Ads in this cluster appear to move readers toward private contact while normalizing discretion or hidden interaction."
        risk = "Watch for reduced accountability: secrecy plus private-channel migration can make coercive or deceptive terms harder to inspect."
    elif "commitment_escalation" in labels:
        title = "Recurring support / dependency pattern"
        likely_pattern = "The shared wording suggests ongoing help, monthly/weekly support, or repeated contact that may create dependency over time."
        risk = "Review whether repeated support is paired with conditions, vulnerability cues, or pressure to continue."
    elif "authority_or_status_appeal" in labels:
        title = "Status-backed support pattern"
        likely_pattern = "These ads emphasize professional, serious, respectful, or solvent advertiser identity to make the offer feel credible."
        risk = "Status claims can increase trust without proof; verify whether credibility language hides an unclear exchange."
    elif "family_obligation_targeting" in labels or any("madre" in term or "familia" in term for term in terms):
        title = "Family-need support pattern"
        likely_pattern = "The cluster appears to address family or caregiving pressure, especially single-mother or household-need language."
        risk = "Family-obligation framing can amplify vulnerability and make an exploitative offer seem like practical help."
    elif "education_or_student_targeting" in labels or any("estudiante" in term or "universitaria" in term for term in terms):
        title = "Student-support targeting pattern"
        likely_pattern = "The shared language points to students, studies, or education-related financial need."
        risk = "Student targeting can combine economic vulnerability with age/youth targeting; check age and conditionality carefully."
    elif any("ayuda" in term or "apoyo" in term for term in terms):
        title = "Economic-help offer pattern"
        likely_pattern = "Most examples share help/support vocabulary. The cluster likely groups templates that advertise money or support as the hook."
        risk = "Economic-help framing is not automatically manipulative, but it becomes higher risk when paired with conditions, secrecy, youth, or hardship."
    else:
        title = "Shared-template persuasion pattern"
        likely_pattern = "The neural bottleneck grouped these ads because they share wording/template structure more than an obvious single human label."
        risk = "Use exemplars and exact annotations to decide whether this is a meaningful persuasion pattern or only template similarity."

    if avg_review >= 58:
        confidence = "High review-priority cluster; prioritize manual inspection before treating the wording as benign."
    elif avg_review >= 50:
        confidence = "Medium review-priority cluster; useful for reviewer triage, but verify with ad-level spans."
    else:
        confidence = "Lower review-priority cluster; still inspect examples because rare severe spans may be diluted by averages."

    term_summary = ", ".join(terms[:5]) if terms else "no stable top terms"
    label_summary = ", ".join(label.replace("_", " ") for label in leading_labels) if leading_labels else "no dominant labels"
    return {
        "eli5_title": title,
        "eli5_description": f"ELI5: this group looks like ads that use similar wording around {term_summary}. In plain terms, the model sees a repeated ad style rather than one isolated post.",
        "risk_characterization": risk,
        "likely_pattern": likely_pattern,
        "review_guidance": f"Open the exemplar ads and verify the exact highlighted spans for {label_summary}. Do not infer risk from the cluster alone.",
        "confidence_note": f"{confidence} It contains {size} representative map ads and is strongest on {leading_platform}.",
    }


def normalized_projection(values: np.ndarray) -> np.ndarray:
    if values.size == 0:
        return np.zeros((0, 2))
    if values.ndim == 1:
        values = values.reshape(-1, 1)
    if values.shape[1] < 2:
        values = np.column_stack([values[:, 0], np.zeros(values.shape[0])])
    coords = values[:, :2].astype(float)
    coords = coords - coords.mean(axis=0, keepdims=True)
    max_abs = np.max(np.abs(coords), axis=0)
    max_abs[max_abs == 0] = 1.0
    return np.clip(coords / max_abs, -1.0, 1.0)


def projection_silhouette(coords: np.ndarray, labels: np.ndarray) -> float | None:
    try:
        return rounded_float(float(silhouette_score(coords, labels))) if len(set(labels)) > 1 and len(coords) > len(set(labels)) else None
    except ValueError:
        return None


def clustering_metric_suite(features: np.ndarray, labels: np.ndarray) -> dict:
    unique = sorted(set(int(label) for label in labels))
    if len(unique) < 2 or len(features) <= len(unique):
        return {
            "silhouette": None,
            "davies_bouldin": None,
            "calinski_harabasz": None,
            "cluster_count": len(unique),
        }
    metrics: dict[str, float | int | None] = {"cluster_count": len(unique)}
    try:
        metrics["silhouette"] = rounded_float(float(silhouette_score(features, labels)))
    except ValueError:
        metrics["silhouette"] = None
    try:
        metrics["davies_bouldin"] = rounded_float(float(davies_bouldin_score(features, labels)))
    except ValueError:
        metrics["davies_bouldin"] = None
    try:
        metrics["calinski_harabasz"] = rounded_float(float(calinski_harabasz_score(features, labels)))
    except ValueError:
        metrics["calinski_harabasz"] = None
    return metrics


def build_deep_isolation_slices(
    dense: np.ndarray,
    bottleneck: np.ndarray,
    projection_arrays: dict[str, np.ndarray],
    sample_rows: list[dict],
    cluster_labels: np.ndarray,
) -> dict:
    """Deep Isolation Forest-inspired partition layer.

    DIF's core idea is to isolate over neural/random representation ensembles
    rather than only original linear axes. This local implementation uses random
    ReLU representation ensembles plus the learned bottleneck, then groups ads
    by isolation-tree leaf co-association.
    """
    sample_size = dense.shape[0]
    if sample_size < 20:
        return {"method": "Skipped: not enough rows for Deep Isolation Forest slices.", "slices": [], "point_slice_ids": [], "point_scores": [], "metrics": {}}

    rng = np.random.default_rng(41)
    representations = []
    rep_width = max(8, min(24, dense.shape[1] // 2))
    for _ in range(3):
        weights = rng.normal(0, 1 / math.sqrt(max(1, dense.shape[1])), size=(dense.shape[1], rep_width))
        bias = rng.normal(0, 0.05, size=(rep_width,))
        random_rep = np.maximum(0.0, dense @ weights + bias)
        representations.append(np.column_stack([bottleneck, random_rep]))

    leaf_blocks = []
    score_columns = []
    for index, representation in enumerate(representations):
        forest = IsolationForest(
            n_estimators=64,
            max_samples=min(256, sample_size),
            contamination="auto",
            random_state=137 + index,
            n_jobs=1,
        )
        forest.fit(representation)
        leaf_blocks.append(
            np.column_stack(
                [
                    tree.apply(representation[:, feature_indices])
                    for tree, feature_indices in zip(forest.estimators_, forest.estimators_features_)
                ]
            )
        )
        score_columns.append(-forest.score_samples(representation))

    leaves = np.hstack(leaf_blocks)
    anomaly_scores = np.mean(np.column_stack(score_columns), axis=1)
    total_trees = leaves.shape[1]
    coassoc = np.zeros((sample_size, sample_size), dtype=np.float32)
    for tree_index in range(total_trees):
        groups: dict[int, list[int]] = defaultdict(list)
        for row_index, leaf in enumerate(leaves[:, tree_index]):
            groups[int(leaf)].append(row_index)
        for members in groups.values():
            if len(members) == 1:
                coassoc[members[0], members[0]] += 1
            else:
                idx = np.array(members)
                coassoc[np.ix_(idx, idx)] += 1
    coassoc /= max(1, total_trees)
    distance = np.clip(1.0 - coassoc, 0.0, 1.0)
    np.fill_diagonal(distance, 0.0)
    target_slices = max(6, min(12, int(round(math.sqrt(sample_size / 8)))))
    try:
        slicer = AgglomerativeClustering(n_clusters=target_slices, metric="precomputed", linkage="average")
    except TypeError:
        slicer = AgglomerativeClustering(n_clusters=target_slices, affinity="precomputed", linkage="average")
    slice_labels = slicer.fit_predict(distance)

    deep_sep = projection_arrays["deep_separation"]
    bottleneck_metrics = clustering_metric_suite(bottleneck, slice_labels)
    projection_metrics = clustering_metric_suite(deep_sep, slice_labels)
    kmeans_bottleneck_metrics = clustering_metric_suite(bottleneck, cluster_labels)
    kmeans_projection_metrics = clustering_metric_suite(deep_sep, cluster_labels)
    isolation_scores = [rounded_float(float(score)) for score in anomaly_scores]
    slices = []
    for slice_id in sorted(set(int(label) for label in slice_labels)):
        indices = [idx for idx, label in enumerate(slice_labels) if int(label) == slice_id]
        rows = [sample_rows[idx] for idx in indices]
        top_labels = Counter(label for row in rows for label in row["labels"])
        top_platforms = Counter(row["platform"] for row in rows)
        top_clusters = Counter(f"deep_cluster_{int(cluster_labels[idx])}" for idx in indices)
        avg_review = sum(row["scores"]["review_priority"] for row in rows) / len(rows)
        avg_anomaly = float(np.mean(anomaly_scores[indices]))
        exemplars = []
        for idx in sorted(indices, key=lambda i: -anomaly_scores[i])[:4]:
            row = sample_rows[idx]
            exemplars.append(
                {
                    "record_id": row["record_id"],
                    "title": row["title"][:110],
                    "platform": row["platform"],
                    "review_priority": row["scores"]["review_priority"],
                    "anomaly_score": rounded_float(float(anomaly_scores[idx])),
                    "labels": row["labels"][:5],
                }
            )
        slices.append(
            {
                "id": f"isolation_slice_{slice_id}",
                "name": f"Isolation cut-slice {slice_id + 1}",
                "count": len(rows),
                "avg_anomaly_score": rounded_float(avg_anomaly),
                "avg_review_priority": rounded_float(avg_review),
                "dominant_labels": [{"label": label, "count": int(count)} for label, count in top_labels.most_common(5)],
                "dominant_platforms": [{"platform": platform, "count": int(count)} for platform, count in top_platforms.most_common(4)],
                "dominant_deep_clusters": [{"cluster": cluster, "count": int(count)} for cluster, count in top_clusters.most_common(4)],
                "exemplars": exemplars,
                "eli5_description": "ELI5: this slice groups ads that repeatedly land in the same isolation-tree leaves after neural/random feature transforms. It reflects cut-based partition behavior rather than round centroid distance.",
                "review_guidance": "Use these slices to find non-round pockets, boundary cases, and unusual ads that k-means hulls may hide.",
            }
        )

    return {
        "method": "Deep Isolation Forest-inspired neural representation ensemble: random ReLU representations plus learned bottleneck → IsolationForest leaf cuts → leaf co-association distance → agglomerative cut-slices.",
        "research_basis": [
            "Deep Isolation Forest maps data through neural representation ensembles before isolation cuts.",
            "Isolation-tree leaf co-association exposes cut-defined partitions that can be non-circular/non-centroidal.",
            "Cluster quality is reported with complementary internal metrics because silhouette alone favors convex separated groups.",
        ],
        "metrics": {
            "tree_count": int(total_trees),
            "representation_count": len(representations),
            "slice_count": len(slices),
            "avg_anomaly_score": rounded_float(float(np.mean(anomaly_scores))),
            "ari_vs_deep_kmeans": rounded_float(float(adjusted_rand_score(cluster_labels, slice_labels))),
            "nmi_vs_deep_kmeans": rounded_float(float(normalized_mutual_info_score(cluster_labels, slice_labels))),
            "deep_isolation_bottleneck": bottleneck_metrics,
            "deep_isolation_projection": projection_metrics,
            "kmeans_bottleneck": kmeans_bottleneck_metrics,
            "kmeans_projection": kmeans_projection_metrics,
            "metric_guide": {
                "silhouette": "Higher is better; favors compact separated groups.",
                "davies_bouldin": "Lower is better; penalizes scatter relative to centroid separation.",
                "calinski_harabasz": "Higher is better; between-cluster dispersion over within-cluster dispersion.",
                "ari_vs_deep_kmeans": "Agreement between isolation cut-slices and neural k-means, adjusted for chance.",
                "nmi_vs_deep_kmeans": "Information overlap between isolation cut-slices and neural k-means.",
            },
        },
        "slices": slices,
        "point_slice_ids": [f"isolation_slice_{int(label)}" for label in slice_labels],
        "point_scores": isolation_scores,
    }


def build_deep_cluster_explanations(
    sample_rows: list[dict],
    matrix,
    coords: np.ndarray,
    x_scale: float,
    y_scale: float,
) -> tuple[list[str | None], dict]:
    """Train an explainable neural-bottleneck clustering layer for the corpus map.

    This intentionally stays CPU/local-only: TF-IDF is compressed with SVD, a
    shallow MLPRegressor learns an autoencoder-style bottleneck, and MiniBatch
    KMeans clusters the bottleneck. Cluster explanations use c-TF-IDF-style
    lexical contrast plus label/platform/score summaries and nearest exemplars.
    """
    if matrix.shape[0] < 20 or matrix.shape[1] < 3:
        return [None for _ in sample_rows], {
            "method": "Skipped: not enough corpus-map rows/features for stable explainable neural-bottleneck clustering.",
            "clusters": [],
            "metrics": {"sample_size": len(sample_rows), "cluster_count": 0},
        }

    n_components = max(2, min(64, matrix.shape[0] - 1, matrix.shape[1] - 1))
    dense_svd = TruncatedSVD(n_components=n_components, random_state=17).fit_transform(matrix)
    center = dense_svd.mean(axis=0, keepdims=True)
    scale = dense_svd.std(axis=0, keepdims=True) + 1e-6
    dense = (dense_svd - center) / scale
    bottleneck_width = max(4, min(12, n_components // 3))
    hidden_width = max(16, min(48, n_components))
    mlp = MLPRegressor(
        hidden_layer_sizes=(hidden_width, bottleneck_width, hidden_width),
        activation="relu",
        solver="adam",
        alpha=0.0005,
        batch_size=min(128, max(16, matrix.shape[0] // 4)),
        learning_rate_init=0.001,
        max_iter=220,
        early_stopping=True,
        validation_fraction=0.12,
        n_iter_no_change=18,
        random_state=17,
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ConvergenceWarning)
        mlp.fit(dense, dense)

    def relu(values: np.ndarray) -> np.ndarray:
        return np.maximum(0.0, values)

    hidden_1 = relu(dense @ mlp.coefs_[0] + mlp.intercepts_[0])
    bottleneck = relu(hidden_1 @ mlp.coefs_[1] + mlp.intercepts_[1])
    cluster_count = max(3, min(9, int(round(math.sqrt(matrix.shape[0] / 18)))))
    clusterer = MiniBatchKMeans(n_clusters=cluster_count, random_state=17, batch_size=256, n_init=10)
    labels = clusterer.fit_predict(bottleneck)
    reconstruction = mlp.predict(dense)
    reconstruction_mse = float(np.mean((reconstruction - dense) ** 2))
    try:
        silhouette = float(silhouette_score(bottleneck, labels)) if len(set(labels)) > 1 else None
    except ValueError:
        silhouette = None

    deep2d = MLPRegressor(
        hidden_layer_sizes=(hidden_width, 2, hidden_width),
        activation="relu",
        solver="adam",
        alpha=0.0007,
        batch_size=min(128, max(16, matrix.shape[0] // 4)),
        learning_rate_init=0.001,
        max_iter=220,
        early_stopping=True,
        validation_fraction=0.12,
        n_iter_no_change=18,
        random_state=29,
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ConvergenceWarning)
        deep2d.fit(dense, dense)
    deep2d_h1 = relu(dense @ deep2d.coefs_[0] + deep2d.intercepts_[0])
    deep2d_coords = relu(deep2d_h1 @ deep2d.coefs_[1] + deep2d.intercepts_[1])
    deep2d_reconstruction = deep2d.predict(dense)
    deep2d_mse = float(np.mean((deep2d_reconstruction - dense) ** 2))

    if len(set(labels)) > 2:
        try:
            separation_raw = LinearDiscriminantAnalysis(n_components=2, solver="svd").fit_transform(bottleneck, labels)
        except Exception:
            separation_raw = bottleneck[:, :2]
    else:
        separation_raw = bottleneck[:, :2]
    projection_arrays = {
        "deep_separation": normalized_projection(separation_raw),
        "deep_bottleneck": normalized_projection(deep2d_coords),
        "legacy_svd": normalized_projection(coords),
    }
    projection_metrics = {
        "deep_separation": {
            "name": "Deep cluster-separation map",
            "method": "Fisher/LDA-style 2D projection of the learned neural bottleneck; optimized to make learned clusters visually separable.",
            "silhouette": projection_silhouette(projection_arrays["deep_separation"], labels),
        },
        "deep_bottleneck": {
            "name": "Deep 2D autoencoder map",
            "method": "Separate shallow neural autoencoder with a two-neuron bottleneck; preserves reconstructive structure rather than explicitly separating clusters.",
            "silhouette": projection_silhouette(projection_arrays["deep_bottleneck"], labels),
            "reconstruction_mse": rounded_float(deep2d_mse),
            "mlp_iterations": int(getattr(deep2d, "n_iter_", 0)),
        },
        "legacy_svd": {
            "name": "Legacy TF-IDF/SVD diagnostic map",
            "method": "Linear TF-IDF/SVD diagnostic projection retained only for comparison; not the default cluster map.",
            "silhouette": projection_silhouette(projection_arrays["legacy_svd"], labels),
        },
    }
    default_projection = "deep_separation"
    deep_isolation = build_deep_isolation_slices(dense, bottleneck, projection_arrays, sample_rows, labels)

    cluster_term_counts: dict[int, Counter] = defaultdict(Counter)
    cluster_doc_terms: dict[int, set[str]] = defaultdict(set)
    for cluster_id, row in zip(labels, sample_rows):
        terms = phrase_terms(safe_tokens(row["text"]), max_terms=90)
        cluster_term_counts[int(cluster_id)].update(terms)
        cluster_doc_terms[int(cluster_id)].update(set(terms))
    term_cluster_df = Counter()
    for terms in cluster_doc_terms.values():
        term_cluster_df.update(terms)

    clusters = []
    for cluster_id in sorted(set(int(label) for label in labels)):
        indices = [index for index, label in enumerate(labels) if int(label) == cluster_id]
        rows = [sample_rows[index] for index in indices]
        term_total = sum(cluster_term_counts[cluster_id].values()) or 1
        scored_terms = []
        for term, count in cluster_term_counts[cluster_id].items():
            tf = count / term_total
            idf = math.log((1 + cluster_count) / (1 + term_cluster_df[term])) + 1.0
            scored_terms.append((term, count, tf * idf))
        top_terms = [
            {"term": term, "count": int(count), "score": rounded_float(score)}
            for term, count, score in sorted(scored_terms, key=lambda item: item[2], reverse=True)[:12]
        ]
        centroid = clusterer.cluster_centers_[cluster_id]
        exemplars = []
        for index in sorted(indices, key=lambda idx: float(np.linalg.norm(bottleneck[idx] - centroid)))[:4]:
            row = sample_rows[index]
            exemplars.append(
                {
                    "record_id": row["record_id"],
                    "title": row["title"][:110],
                    "platform": row["platform"],
                    "labels": row["labels"][:5],
                    "review_priority": row["scores"]["review_priority"],
                    "manipulation": row["scores"]["manipulation"],
                    "persuasion": row["scores"]["persuasion"],
                    "distance": rounded_float(float(np.linalg.norm(bottleneck[index] - centroid))),
                }
            )
        top_label_counts = Counter(label for row in rows for label in row["labels"])
        top_platform_counts = Counter(row["platform"] for row in rows)
        avg_review = sum(row["scores"]["review_priority"] for row in rows) / len(rows)
        avg_manip = sum(row["scores"]["manipulation"] for row in rows) / len(rows)
        avg_pers = sum(row["scores"]["persuasion"] for row in rows) / len(rows)
        cluster_name = " · ".join(term["term"] for term in top_terms[:3]) if top_terms else f"cluster {cluster_id + 1}"
        characterization = characterize_cluster(top_terms, top_label_counts, top_platform_counts, avg_review, len(rows))
        default_coords = projection_arrays[default_projection]
        clusters.append(
            {
                "id": f"deep_cluster_{cluster_id}",
                "name": cluster_name,
                **characterization,
                "count": len(rows),
                "centroid": {
                    "x": rounded_float(float(np.mean(default_coords[indices, 0]))),
                    "y": rounded_float(float(np.mean(default_coords[indices, 1]))),
                },
                "top_terms": top_terms,
                "dominant_labels": [{"label": label, "count": int(count)} for label, count in top_label_counts.most_common(6)],
                "dominant_platforms": [{"platform": platform, "count": int(count)} for platform, count in top_platform_counts.most_common(5)],
                "scores": {
                    "avg_review_priority": rounded_float(avg_review),
                    "avg_manipulation": rounded_float(avg_manip),
                    "avg_persuasion": rounded_float(avg_pers),
                },
                "exemplars": exemplars,
                "interpretation": "Treat this as a learned template/topic neighborhood: the neural bottleneck groups similar TF-IDF patterns; c-TF-IDF terms and exemplars explain what the group appears to share.",
            }
        )

    point_cluster_ids = [f"deep_cluster_{int(label)}" for label in labels]
    point_projections = []
    for index in range(len(sample_rows)):
        point_projections.append(
            {
                name: {"x": rounded_float(float(values[index, 0])), "y": rounded_float(float(values[index, 1]))}
                for name, values in projection_arrays.items()
            }
        )
    return point_cluster_ids, {
        "method": "TF-IDF is densified for local CPU feasibility, then a shallow neural autoencoder learns a bottleneck representation. The default visible map is a cluster-separation projection of that neural bottleneck, not the legacy SVD map. MiniBatchKMeans clusters the bottleneck; explanations use c-TF-IDF-style contrastive terms, dominant candidate labels/platforms, scores, and nearest exemplars.",
        "research_basis": [
            "BERTopic-style transformer/topic pipeline: embedding, clustering, then c-TF-IDF topic descriptions.",
            "Deep descriptive clustering: learn representations while keeping human-readable cluster descriptions.",
            "Explainable deep clustering guidance: expose fidelity/quality metrics, sparse lexical summaries, and human-check exemplars.",
            "Dimensionality-reduction guidance: use task-appropriate projections and report quality metrics because local/global structure trade off in 2D maps.",
        ],
        "default_projection": default_projection,
        "projection_modes": projection_metrics,
        "point_projections": point_projections,
        "deep_isolation": deep_isolation,
        "metrics": {
            "sample_size": len(sample_rows),
            "cluster_count": cluster_count,
            "svd_components": n_components,
            "bottleneck_width": bottleneck_width,
            "mlp_iterations": int(getattr(mlp, "n_iter_", 0)),
            "reconstruction_mse": rounded_float(reconstruction_mse),
            "silhouette": rounded_float(silhouette) if silhouette is not None else None,
        },
        "clusters": clusters,
    }


def build_corpus_map(rows: list[dict], artifact: dict) -> dict:
    pipeline = artifact["model"]
    vectorizer = pipeline.named_steps["tfidf"]
    sample_rows = representative_rows(rows)
    matrix = vectorizer.transform([row["text"] for row in sample_rows])
    if matrix.shape[0] < 3:
        coords = np.zeros((matrix.shape[0], 2))
        variance = [0.0, 0.0]
    else:
        svd = TruncatedSVD(n_components=2, random_state=17)
        coords = svd.fit_transform(matrix)
        variance = [rounded_float(v) for v in svd.explained_variance_ratio_]
    max_abs_x = max(float(abs(x)) for x in coords[:, 0]) if len(coords) else 1.0
    max_abs_y = max(float(abs(y)) for y in coords[:, 1]) if len(coords) else 1.0
    point_cluster_ids, deep_clusters = build_deep_cluster_explanations(sample_rows, matrix, coords, max_abs_x, max_abs_y)
    point_projections = deep_clusters.get("point_projections", [])
    point_slice_ids = deep_clusters.get("deep_isolation", {}).get("point_slice_ids", [])
    point_isolation_scores = deep_clusters.get("deep_isolation", {}).get("point_scores", [])
    default_projection = deep_clusters.get("default_projection", "deep_separation")
    points = []
    for index, (row, deep_cluster) in enumerate(zip(sample_rows, point_cluster_ids)):
        projections = point_projections[index] if index < len(point_projections) else {}
        default_coords = projections.get(default_projection) or projections.get("deep_bottleneck") or projections.get("legacy_svd") or {"x": 0.0, "y": 0.0}
        points.append(
            {
                "record_id": row["record_id"],
                "x": default_coords["x"],
                "y": default_coords["y"],
                "projections": projections,
                "platform": row["platform"],
                "split": row["split"],
                "title": row["title"][:110],
                "labels": row["labels"][:6],
                "review_priority": row["scores"]["review_priority"],
                "manipulation": row["scores"]["manipulation"],
                "persuasion": row["scores"]["persuasion"],
                "span_count": len(row["spans"]),
                "deep_cluster": deep_cluster,
                "isolation_slice": point_slice_ids[index] if index < len(point_slice_ids) else None,
                "isolation_anomaly_score": point_isolation_scores[index] if index < len(point_isolation_scores) else None,
            }
        )
    return {
        "method": "Default map uses a learned neural bottleneck plus cluster-separation projection. A legacy TF-IDF/SVD diagnostic projection is retained for comparison only; 2D distances remain exploratory, not causal.",
        "explained_variance_ratio": variance,
        "deep_clusters": deep_clusters,
        "points": points,
    }


def build_facet_overview(rows: list[dict], segment_report: dict) -> dict:
    def bucket_counts(values: list[str]) -> list[dict]:
        return [{"value": value, "count": int(count)} for value, count in Counter(values).most_common()]

    facets = [
        {"name": "platform", "values": bucket_counts([row["platform"] for row in rows])},
        {"name": "split", "values": bucket_counts([row["split"] for row in rows])},
        {"name": "label_count", "values": bucket_counts([str(len(row["labels"])) for row in rows])},
        {"name": "span_count_bin", "values": bucket_counts(["0" if not row["spans"] else "1-3" if len(row["spans"]) <= 3 else "4-7" if len(row["spans"]) <= 7 else "8+" for row in rows])},
        {"name": "paid_or_featured", "values": bucket_counts(["yes" if row["context"].get("is_paid_or_premium_marker") or row["context"].get("is_featured_marker") else "no" for row in rows])},
        {"name": "image_available", "values": bucket_counts(["yes" if row["context"].get("image_available") else "no" for row in rows])},
    ]
    return {
        "method": "Facets-inspired compact overview of safe categorical/document features.",
        "facets": facets,
        "weak_slices": segment_report.get("underperforming_slices", [])[:8] if segment_report else [],
        "notes": segment_report.get("method_notes", []) if segment_report else [],
    }


def build_annotation_taxonomy_matrix(label_counts: Counter) -> list[dict]:
    rows = []
    for label, count in sorted(label_counts.items()):
        family, label_type = LABEL_FAMILIES.get(label, ("Persuasion", "project label"))
        rows.append(
            {
                "label": label,
                "family": family,
                "type": label_type,
                "count": int(count),
                "common_false_positive_risk": "Generic ad wording may look persuasive without manipulative pressure; verify local span context.",
                "human_check": "Confirm exact span boundary, implied exchange, vulnerability target, and whether the evidence is explicit or contextual.",
            }
        )
    return rows


def generate(
    docs_path: Path,
    annotations_path: Path,
    model_path: Path,
    json_out: Path,
    html_out: Path,
    model_report: Path,
    segment_report: Path = DEFAULT_SEGMENT_REPORT,
) -> dict:
    docs = {row["record_id"]: row for row in load_jsonl(docs_path)}
    annotations = {row["record_id"]: row for row in load_jsonl(annotations_path)}
    artifact = joblib.load(model_path)
    model = artifact["model"]
    labels = artifact["labels"]
    rows = []
    for record_id, doc in docs.items():
        ann = annotations[record_id]
        text = doc["text"]
        context = doc.get("context", {})
        scores = score_record(text, ann.get("spans", []), context)
        probabilities = dict(zip(labels, model.predict_proba([text])[0]))
        top_model = [
            {"label": label, "probability": round(float(prob), 4)}
            for label, prob in sorted(probabilities.items(), key=lambda item: item[1], reverse=True)[:8]
        ]
        model_predictions = [
            {"label": label, "probability": round(float(prob), 4)}
            for label, prob in sorted(probabilities.items(), key=lambda item: item[1], reverse=True)
        ]
        spans = [
            {
                **span,
                "excerpt": span_excerpt(text, span),
                "contribution_hint": round(((span.get("intensity") or 0) + (span.get("harm_risk") or 0)) / 7, 3),
            }
            for span in ann.get("spans", [])
        ]
        title, _, body = text.partition("\n")
        rows.append(
            {
                "record_id": record_id,
                "platform": doc["platform"],
                "split": doc["split"],
                "campaign_group": doc["campaign_group"],
                "title": title,
                "excerpt": body[:420],
                "text": text,
                "context": context,
                "accepted_round": ann["accepted_round"],
                "agreement": ann["agreement"],
                "scores": scores,
                "labels": sorted({span["label"] for span in spans}),
                "spans": spans,
                "top_model": top_model,
                "model_predictions": model_predictions,
            }
        )
    ranked = sorted(rows, key=lambda row: row["scores"]["review_priority"], reverse=True)
    label_counts = Counter(label for row in rows for label in row["labels"])
    span_count = sum(len(row["spans"]) for row in rows)
    zero_span_records = sum(1 for row in rows if not row["spans"])
    model_report_data = json.loads(model_report.read_text(encoding="utf-8"))
    segment_data = json.loads(segment_report.read_text(encoding="utf-8")) if segment_report.exists() else {}
    global_explainability = build_global_explainability(artifact, model_report_data)
    term_network = build_term_network(rows)
    corpus_map = build_corpus_map(rows, artifact)
    facet_overview = build_facet_overview(rows, segment_data)
    output = {
        "status": "candidate_inferences_from_council_consensus",
        "gold": False,
        "records": len(rows),
        "source": str(annotations_path),
        "model": str(model_path),
        "source_counts": dict(Counter(row["platform"] for row in rows)),
        "consensus_round_counts": dict(Counter(str(row["accepted_round"]) for row in rows)),
        "label_counts": dict(sorted(label_counts.items())),
        "span_count": span_count,
        "zero_span_records": zero_span_records,
        "observability": {
            "missing_image_pixels": sum(1 for row in rows if row["context"].get("image_available")),
            "image_metadata_without_pixels": sum(1 for row in rows if row["context"].get("image_available")),
            "challenge_records": sum(1 for row in rows if row["split"] == "challenge"),
            "undersized_cohorts": {"facebook": 26, "evisos": 2},
            "gold": False,
            "known_errors": [
                "Candidate council labels are not human-adjudicated gold.",
                "Image pixels are not archived locally; image-only persuasion cannot be inspected.",
                "Model metrics measure agreement with council labels, not independent human validity.",
            ],
        },
        "iteration_timeline": [
            {
                "stage": "weak baseline",
                "date": "2026-07-08",
                "records": 1589,
                "spans": None,
                "micro_f1": 0.8785,
                "macro_f1": 0.73,
                "note": "Historical weak-label baseline on smaller rebuilt corpus.",
            },
            {
                "stage": "research-v2 council",
                "date": "2026-07-09",
                "records": 5717,
                "spans": 33720,
                "micro_f1": 0.9145,
                "macro_f1": 0.7104,
                "note": "Expanded research rubric before Spanish orthographic pass.",
            },
            {
                "stage": "localized council",
                "date": "2026-07-09",
                "records": len(rows),
                "spans": span_count,
                "micro_f1": None,
                "macro_f1": None,
                "note": "Accent/gender/typo/slang normalization with exact original offsets.",
            },
        ],
        "top_by_review_priority": ranked[:500],
        "top_by_manipulation": sorted(rows, key=lambda row: row["scores"]["manipulation"], reverse=True)[:500],
        "top_by_persuasion": sorted(rows, key=lambda row: row["scores"]["persuasion"], reverse=True)[:500],
        "global_explainability": global_explainability,
        "term_network": term_network,
        "corpus_map": corpus_map,
        "facet_overview": facet_overview,
        "annotation_taxonomy_matrix": build_annotation_taxonomy_matrix(label_counts),
    }
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    render_html(output, model_report_data, html_out, segment_data)
    return {"records": len(rows), "json": str(json_out), "html": str(html_out)}


def render_html(data: dict, model_report: dict, path: Path, segment_report: dict | None = None) -> None:
    ensure_report_assets(path.parent)
    embedded = json.dumps({"report": data, "modelReport": model_report, "segmentReport": segment_report or {}}, ensure_ascii=False)
    embedded = (
        embedded.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    template = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>ManiPsych research-v2 model observatory</title>
<style>
/* Tailwind-inspired utility report; no CDN required. Design references Tailwind CSS utility patterns: https://tailwindcss.com */
:root{--ink:#17201d;--muted:#60706a;--paper:#f7f5ef;--card:#fffffb;--line:#d9d3c5;--green:#2f6f4e;--amber:#c9802f;--red:#b4473d;--blue:#315d8c;--violet:#6d4fa3;--shadow:0 18px 50px #17201d16}
*{box-sizing:border-box} html{scroll-behavior:smooth} body{margin:0;overflow-x:hidden;background:radial-gradient(circle at top left,#fff8e7 0,#f7f5ef 38%,#edf2ee 100%);color:var(--ink);font-family:Inter,ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif}
a{color:inherit}.skip{position:absolute;left:-999px}.skip:focus{left:16px;top:16px;background:#fff;padding:10px;border-radius:10px;z-index:9}
.hero{position:sticky;top:0;z-index:5;background:linear-gradient(135deg,#14201d,#28473a 55%,#714f28);color:white;border-bottom:1px solid #ffffff24;box-shadow:0 10px 40px #0002}
.hero-inner{padding:18px min(5vw,72px);display:grid;grid-template-columns:1.2fr .8fr;gap:18px;align-items:center}.hero-inner>*{min-width:0}.eyebrow{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:#a8d7bd;font-weight:800}.eyebrow,.title,.sub{overflow-wrap:anywhere}.title{font-size:clamp(28px,4vw,56px);line-height:.95;margin:6px 0}.sub{color:#dce9e1;margin:0;line-height:1.5}.nav{display:flex;flex-wrap:wrap;gap:8px;justify-content:flex-end;min-width:0}.nav a,.pill,.btn{border:1px solid #ffffff36;background:#ffffff14;color:inherit;border-radius:999px;padding:8px 11px;text-decoration:none;font-size:12px;font-weight:700;backdrop-filter:blur(10px)}
.shell{padding:22px min(5vw,72px);max-width:100vw;overflow-x:hidden}.grid{display:grid;gap:16px}.kpis{grid-template-columns:repeat(6,minmax(130px,1fr))}.layout{display:grid;grid-template-columns:330px minmax(360px,1fr) 420px;gap:16px;align-items:start}.panel,.card{background:var(--card);background:color-mix(in srgb,var(--card) 94%,white);border:1px solid var(--line);border-radius:22px;padding:16px;box-shadow:var(--shadow)}.panel h2,.panel h3,.card h3{margin:0 0 8px}.small{font-size:12px;color:var(--muted);line-height:1.45}.metric{font-size:28px;font-weight:900}.metric-label{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);font-weight:800}
.controls{position:sticky;top:118px}.control{width:100%;padding:10px 12px;border:1px solid var(--line);border-radius:12px;background:white;margin:4px 0 10px}.list{max-height:72vh;overflow:auto;display:grid;gap:10px;padding-right:4px}.rank{cursor:pointer;text-align:left;width:100%;border:1px solid var(--line);background:white;border-radius:16px;padding:12px;transition:transform .18s ease,box-shadow .18s ease,border-color .18s ease}.rank:hover,.rank[aria-current=true],.rank[aria-selected=true]{transform:translateY(-2px);box-shadow:0 14px 30px #17201d18;border-color:#8aae9a}.rank-title{font-weight:850;margin-bottom:5px}.scoreline{display:flex;gap:7px;flex-wrap:wrap;margin-top:8px}.chip{display:inline-flex;align-items:center;gap:5px;border-radius:999px;padding:4px 8px;font-size:11px;font-weight:800;background:#eef3ef;color:#1e3a2d}.chip.red{background:#fae4df;color:#7b241d}.chip.amber{background:#f6ead7;color:#744512}.chip.blue{background:#e2edf9;color:#213d65}.chip.violet{background:#ece6fb;color:#432b70}
.detail-title{font-size:22px;font-weight:900;margin:0}.annotated{font-size:16px;line-height:2.1;background:#fff;border:1px solid var(--line);border-radius:18px;padding:18px;max-height:48vh;overflow:auto}.seg{border-radius:5px;padding:2px 1px;background:linear-gradient(transparent 56%,#f8d68c 56%,#f8d68c 72%,transparent 72%)}.seg.manip{background:linear-gradient(transparent 52%,#f2aaa3 52%,#f2aaa3 70%,transparent 70%),linear-gradient(transparent 74%,#93c5fd 74%,#93c5fd 88%,transparent 88%)}.seg:hover{outline:2px solid #17201d33}.legend{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0}
.ledger{max-height:34vh;overflow:auto}.ledger-row{border-bottom:1px solid #eee6d7;padding:10px 0}.dossier{display:grid;gap:10px;max-height:40vh;overflow:auto}.dossier-card{border:1px solid #eadbc7;border-radius:16px;padding:12px;background:linear-gradient(135deg,#fffdf8,#f8f4eb)}.dossier-card h3{margin:0 0 6px;font-size:15px}.type-badge{display:inline-flex;border-radius:999px;padding:3px 8px;font-size:10px;font-weight:900;letter-spacing:.05em;text-transform:uppercase;background:#e7edf5;color:#263f66}.eli5{border-left:4px solid #e0b15f;padding:7px 9px;background:#fff8e9;border-radius:10px;margin:8px 0}.bar{height:9px;border-radius:999px;background:#ece6dc;overflow:hidden}.bar>i{display:block;height:100%;border-radius:999px;background:linear-gradient(90deg,var(--green),var(--amber),var(--red))}.waterfall{display:grid;gap:9px}.rowline{display:grid;grid-template-columns:155px 1fr 48px;gap:8px;align-items:center;font-size:12px}
.pipeline{overflow-x:auto;overflow-y:hidden}.pipe-svg{min-width:1080px;width:100%;height:390px}.node{fill:#fffdf8;stroke:#c9c0af;stroke-width:1.4}.node-title{font-size:14px;font-weight:800;fill:#17201d}.node-sub{font-size:11px;fill:#60706a}.flow{stroke:#527762;stroke-width:3;fill:none;marker-end:url(#arrow)}.pulse{animation:pulse 2.6s infinite}.dash{stroke-dasharray:6 6}.table{width:100%;border-collapse:collapse;font-size:12px}.table th,.table td{padding:8px;border-bottom:1px solid #eee6d7;text-align:left}.table th{color:#60706a;text-transform:uppercase;font-size:10px;letter-spacing:.08em}.viz-grid{display:grid;grid-template-columns:1.1fr .9fr;gap:16px}.chart{width:100%;min-height:260px}.chart svg{width:100%;height:auto;display:block}.axis{stroke:#9b907e;stroke-width:1}.curve{fill:none;stroke:var(--blue);stroke-width:3}.curve.pr{stroke:var(--green)}.curve.base{stroke:#c8bca7;stroke-width:1.5;stroke-dasharray:6 6}.dot{fill:var(--red);stroke:white;stroke-width:2}.timeline{display:grid;gap:10px}.timeline-row{display:grid;grid-template-columns:120px 1fr 72px;gap:10px;align-items:center;border-left:4px solid #d5c9b8;padding:8px 0 8px 12px}.heat{display:grid;gap:7px}.heat-row{display:grid;grid-template-columns:180px repeat(4,1fr);gap:6px;align-items:center;font-size:12px}.heat-cell{border-radius:8px;padding:6px;text-align:center;color:#12201b;background:#edf1ec}.annotated-title{font-size:22px;font-weight:900;margin:0}.body-label{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);font-weight:900;margin:12px 0 6px}.slice-card{border:1px solid #eee1cf;border-radius:16px;padding:10px;background:#fff;margin:8px 0}.terms{display:flex;gap:5px;flex-wrap:wrap;margin-top:5px}
.big-viz{min-height:380px;border:1px solid #eee1cf;border-radius:18px;background:#fff;overflow:hidden}.viz-toolbar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:8px 0 12px}.viz-toolbar .control{width:auto;min-width:150px;margin:0}.network-node{cursor:pointer}.network-node:focus{outline:3px solid #315d8c}.network-edge{stroke:#b8ad9a;stroke-opacity:.35}.network-label{font-size:10px;pointer-events:none;fill:#17201d;font-weight:750}.network-label-bg{fill:#fffdf8;stroke:#dbcdb9;stroke-width:.8;opacity:.94}.network-leader{stroke:#948772;stroke-width:.75;stroke-dasharray:2 2;opacity:.7}.scatter-point{cursor:pointer;stroke:white;stroke-width:1.5}.scatter-point:focus{outline:3px solid #315d8c}.tooltip{position:fixed;z-index:10;max-width:320px;background:#17201d;color:white;border-radius:12px;padding:9px 10px;font-size:12px;box-shadow:var(--shadow);pointer-events:none;display:none}.facet-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}.facet-card{border:1px solid #eee1cf;border-radius:16px;padding:12px;background:#fff}.coef-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}.coef-card{border:1px solid #eee1cf;border-radius:16px;padding:12px;background:#fff}.term-pill{display:inline-flex;justify-content:space-between;gap:8px;border-radius:999px;padding:5px 8px;background:#eef3ef;margin:3px;font-size:11px}.warn{border-left:4px solid var(--red);padding:8px 10px;background:#fff1ef;border-radius:12px}.legend-row{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0}.legend-item{display:inline-flex;gap:6px;align-items:center;border:1px solid #eadfce;border-radius:999px;padding:4px 8px;background:#fff;font-size:11px}.swatch{width:10px;height:10px;border-radius:50%;display:inline-block}.map-info-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:10px;margin-top:10px}.map-card{border:1px solid #eee1cf;border-radius:16px;background:#fff;padding:10px}.map-card h3{font-size:14px;margin:0 0 6px}.neighbor-list{display:grid;gap:5px}.neighbor-list button{border:1px solid #eadfce;border-radius:10px;background:#fff;padding:6px;text-align:left;cursor:pointer}
.tutorial{border:1px solid #d9eadf;border-left:5px solid var(--green);border-radius:16px;background:linear-gradient(135deg,#f3fbf5,#fffdf8);padding:12px 14px;margin:10px 0 14px}.tutorial h3{margin:0 0 6px;font-size:14px}.tutorial ul{margin:6px 0 0 18px;padding:0}.tutorial li{margin:4px 0}.tutorial-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px}.tutorial-card{border:1px solid #e7decf;border-radius:14px;background:#fff;padding:10px}
.toast{position:fixed;right:16px;bottom:16px;background:#17201d;color:white;border-radius:14px;padding:12px 14px;box-shadow:var(--shadow);opacity:0;transform:translateY(8px);transition:.2s;pointer-events:none}.toast.show{opacity:1;transform:translateY(0)}
@keyframes pulse{0%,100%{filter:drop-shadow(0 0 0 #65a98400)}50%{filter:drop-shadow(0 0 12px #65a984aa)}}
@media(max-width:1200px){.layout{grid-template-columns:300px 1fr}.right-col{grid-column:1 / -1}.kpis{grid-template-columns:repeat(3,1fr)}.controls{position:static}.viz-grid{grid-template-columns:1fr}}
@media(max-width:760px){.hero-inner{grid-template-columns:1fr}.nav{justify-content:flex-start}.layout{display:block}.panel,.card{margin-bottom:14px}.kpis{grid-template-columns:repeat(2,1fr)}.annotated{max-height:none}.title{font-size:32px}.shell{padding:14px}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto!important}*,*::before,*::after{animation-duration:.01ms!important;animation-iteration-count:1!important;transition-duration:.01ms!important}.pulse{animation:none}}
@media print{.hero,.controls,.toast{display:none!important}body{background:white}.shell{padding:0}.layout{display:block}.panel,.card{box-shadow:none;break-inside:avoid}.annotated,.ledger{max-height:none;overflow:visible}}
</style></head><body>
<a class="skip" href="#explorer">Skip to explorer</a>
<header class="hero"><div class="hero-inner">
  <div><div class="eyebrow">Research-v2 · Council-candidate model observatory</div>
    <h1 class="title">ManiPsych ad manipulation explorer</h1>
    <p class="sub">Corpus __RECORDS__ records · __SPANS__ visible candidate spans · candidate consensus only, not human-adjudicated gold · model status: __MODEL_STATUS__</p></div>
  <nav class="nav" aria-label="Report navigation">
    <a href="#pipeline">Pipeline</a><a href="#metrics">Metrics</a><a href="#diagnostics">Diagnostics</a><a href="#explainability-atlas">Explainability</a><a href="#term-network">Term Network</a><a href="#corpus-map">Corpus Map</a><a href="#explorer">Top 25</a><a href="#observability">Observability</a><a href="#research">Research</a>
  </nav>
</div></header>
<main class="shell">
  <section id="metrics" class="grid kpis" aria-label="Key metrics">
    <div class="panel"><div class="metric">__RECORDS__</div><div class="metric-label">records</div></div>
    <div class="panel"><div class="metric">__SPANS__</div><div class="metric-label">candidate spans</div></div>
    <div class="panel"><div class="metric">__ZERO_SPAN__</div><div class="metric-label">zero-span ads</div></div>
    <div class="panel"><div class="metric">__TEST_MICRO__</div><div class="metric-label">test micro-F1*</div></div>
    <div class="panel"><div class="metric">__TEST_MACRO__</div><div class="metric-label">test macro-F1*</div></div>
    <div class="panel"><div class="metric">__TEST_AUC__</div><div class="metric-label">test ROC AUC micro*</div></div>
    <div class="panel"><div class="metric">__TEST_ACC__</div><div class="metric-label">test label accuracy*</div></div>
    <div class="panel"><div class="metric">__GOLD__</div><div class="metric-label">human gold?</div></div>
  </section>
  <section class="tutorial" aria-label="Metrics tutorial">
    <h3>How to read the KPI cards</h3>
    <ul class="small">
      <li><b>Records/spans</b> describe the current candidate-council corpus and visible annotation evidence.</li>
      <li><b>F1, AUC, and accuracy</b> measure agreement with council-candidate labels, not independent human gold.</li>
      <li><b>Human gold?</b> stays false until funded blinded human review and adjudication are completed.</li>
    </ul>
  </section>
  <section id="pipeline" class="panel pipeline" style="margin-top:16px">
    <h2>Collection → cleaning → annotation → model stack → report</h2>
    <p class="small">End-to-end provenance diagram. Dashed links mark candidate-only layers; solid links mark deterministic data movement. The model stack combines resolved council spans, TF-IDF one-vs-rest probabilities, score arithmetic, bounded exposure context, and privacy-safe enrichment variables. Posting date can be analyzed only when explicit posting metadata exists; collection time is excluded.</p>
    <div class="tutorial"><h3>How to use this pipeline diagram</h3><ul class="small"><li>Read left to right: public pages become raw archives, then immutable text records, candidate council spans, model outputs, and report views.</li><li>Dashed arrows mark layers that are suggestions or diagnostics rather than human-adjudicated truth.</li><li>Use this section to audit provenance: every downstream visualization should trace back to immutable text and redacted context metadata.</li></ul></div>
    <svg class="pipe-svg" role="img" aria-label="Pipeline diagram from websites to raw archives to processed manifest to council annotations to model stack to report">
      <defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#527762"/></marker></defs>
      <path class="flow pulse" d="M120 90 C190 90 190 90 260 90"/><path class="flow pulse" d="M420 90 C490 90 490 90 560 90"/><path class="flow pulse" d="M720 90 C790 90 790 90 860 90"/>
      <path class="flow dash" d="M640 150 C640 220 420 220 420 285"/><path class="flow" d="M720 285 C780 285 800 245 860 245"/><path class="flow dash" d="M720 285 C790 330 845 335 900 335"/>
      <rect class="node" x="20" y="45" width="140" height="90" rx="18"/><text class="node-title" x="42" y="78">Web sources</text><text class="node-sub" x="42" y="101">Doplim, Locanto,</text><text class="node-sub" x="42" y="118">Ciudad, FB, Evisos</text>
      <rect class="node" x="260" y="45" width="160" height="90" rx="18"/><text class="node-title" x="290" y="78">Raw archives</text><text class="node-sub" x="290" y="101">HTML snapshots</text><text class="node-sub" x="290" y="118">PII-safe references</text>
      <rect class="node" x="560" y="45" width="160" height="90" rx="18"/><text class="node-title" x="585" y="78">Processing</text><text class="node-sub" x="585" y="101">clean, dedupe, hash,</text><text class="node-sub" x="585" y="118">campaign groups</text>
      <rect class="node" x="860" y="45" width="160" height="90" rx="18"/><text class="node-title" x="884" y="78">Structured corpus</text><text class="node-sub" x="884" y="101">5,717 immutable</text><text class="node-sub" x="884" y="118">documents</text>
      <rect class="node" x="260" y="240" width="180" height="90" rx="18"/><text class="node-title" x="286" y="273">Council labels</text><text class="node-sub" x="286" y="296">3 subagents · 90%+</text><text class="node-sub" x="286" y="313">candidate spans</text>
      <rect class="node" x="560" y="240" width="160" height="90" rx="18"/><text class="node-title" x="586" y="273">Model stack</text><text class="node-sub" x="586" y="296">TF-IDF OVR + spans</text><text class="node-sub" x="586" y="313">+ score ensemble</text>
      <rect class="node" x="860" y="200" width="160" height="90" rx="18"/><text class="node-title" x="894" y="233">Explorer</text><text class="node-sub" x="894" y="256">rankings, overlays,</text><text class="node-sub" x="894" y="273">metrics, errors</text>
      <rect class="node" x="880" y="312" width="180" height="62" rx="18"/><text class="node-title" x="906" y="337">Slice analysis</text><text class="node-sub" x="906" y="358">engineered variables, clusters, weak cohorts</text>
    </svg>
  </section>
  <section id="diagnostics" class="viz-grid" style="margin-top:16px">
    <div class="panel" style="grid-column:1 / -1"><h2>Diagnostics tutorial</h2><div class="tutorial-grid small"><div class="tutorial-card"><b>Curves:</b> ROC and precision-recall summarize label-decision ranking quality. High AUC does not prove labels are human-valid.</div><div class="tutorial-card"><b>Heatmap:</b> darker cells are better metric values; low-support labels should be read cautiously.</div><div class="tutorial-card"><b>Slices/clusters:</b> weak cohorts identify where review or submodels may help, not where ads are necessarily more manipulative.</div><div class="tutorial-card"><b>Threshold overlay:</b> compares default .50 decisions with validation-tuned thresholds; tuning must never use final test labels.</div></div></div>
    <div class="panel chart"><h2>Model curves</h2><p class="small"><b>How to read:</b> ROC shows ranking quality across false-positive tradeoffs; precision-recall is more sensitive to rare labels. These curves measure agreement with candidate council labels, not human gold.</p><div id="curveChart"></div></div>
    <div class="panel"><h2>Training/test iteration timeline</h2><p class="small"><b>How to read:</b> scan top to bottom to see what changed between corpus/model iterations and whether metrics moved after those changes.</p><div id="iterationTimeline" class="timeline"></div></div>
    <div class="panel"><h2>Per-label metric heatmap</h2><p class="small"><b>How to read:</b> darker cells indicate stronger test-set agreement; first check support, then compare F1/AUC/accuracy. Empty AUC means no positive/negative support for that cohort.</p><div id="metricHeatmap" class="heat"></div></div>
    <div class="panel"><h2>Error and review lifecycle</h2><p class="small"><b>How to read:</b> each row is a known pipeline/review risk or fix. Use it as the context for why current metrics should be treated as candidate-model evidence.</p><div id="errorTimeline" class="timeline"></div></div>
    <div class="panel"><h2>Underperforming slices</h2><p class="small"><b>How to read:</b> each card is a supported cohort whose micro-F1 trails the overall test score. Use these as review targets or submodel candidates, not as manipulation prevalence claims.</p><div id="sliceWeakness"></div></div>
    <div class="panel"><h2>Latent ad clusters</h2><p class="small"><b>How to read:</b> top terms summarize TF-IDF clusters. Clusters reveal template/vocabulary neighborhoods and should be cross-checked with annotated examples.</p><div id="clusterSummary"></div></div>
    <div class="panel"><h2>Threshold overlay</h2><p class="small"><b>How to read:</b> compare default .50 decisions with validation-tuned thresholds. Improvements are a lightweight decision-layer change, not new human validation.</p><div id="thresholdOverlay"></div></div>
  </section>
  <section id="explainability-atlas" class="panel" style="margin-top:16px">
    <h2>Explainability atlas</h2>
    <p class="small">Global and local explanation views inspired by SHAP/LIME-style text explanations and interactive model cards. Coefficients show model internals, not proof of manipulation.</p>
    <div class="tutorial"><h3>How to read and interact with explainability</h3><ul class="small"><li>Choose a label to see the model terms that most increase that label's score and contrast terms that push away from it.</li><li>The local evidence card updates when you select an ad in the Top 25 explorer and shows whether top model terms actually appear in that ad.</li><li>Interpretation rule: coefficient terms explain the TF-IDF model, while annotation spans explain the candidate council decision. Disagreement is a review signal.</li></ul></div>
    <div class="viz-toolbar">
      <label class="small" for="explainLabel">Label</label><select id="explainLabel" class="control"></select>
    </div>
    <div id="explainabilityAtlas" class="coef-grid"></div>
  </section>
  <section id="term-network" class="panel" style="margin-top:16px">
    <h2>Term and technique network</h2>
    <p class="small">Co-occurrence network connecting normalized Spanish terms, annotation labels, and platforms. Click a node to inspect linked labels/examples; use the controls to reduce graph density.</p>
    <div class="tutorial"><h3>How to read and interact with the network</h3><ul class="small"><li><b>Green nodes</b> are normalized terms/phrases; <b>red nodes</b> are annotation labels; <b>blue nodes</b> are platforms.</li><li>Smart labels intentionally hide lower-priority labels when they would overlap. Hover, keyboard-focus, or click any node to recover the full label.</li><li>Thicker links mean stronger co-occurrence in the redacted corpus. This is association, not causation.</li><li>Use node-type, top-N, and label-mode controls to simplify clutter before interpreting clusters.</li></ul></div>
    <div class="viz-toolbar">
      <label class="small" for="networkKind">Node type</label><select id="networkKind" class="control"><option value="">All</option><option value="term">Terms</option><option value="label">Labels</option><option value="platform">Platforms</option></select>
      <label class="small" for="networkTopN">Top nodes</label><select id="networkTopN" class="control"><option>60</option><option selected>100</option><option>140</option></select>
      <label class="small" for="networkLabelMode">Labels</label><select id="networkLabelMode" class="control"><option value="smart" selected>Smart labels</option><option value="important">Important only</option><option value="hidden">Hide labels</option></select>
      <button id="networkReset" class="btn" type="button">Reset network</button>
    </div>
    <div id="networkStatus" class="small"></div><div id="termNetworkViz" class="big-viz" role="img" aria-label="Term and technique co-occurrence network"></div>
    <div id="networkInspector" class="small"></div>
  </section>
  <section id="corpus-map" class="panel" style="margin-top:16px">
    <h2>Corpus map</h2>
    <p class="small">Embedding-projector-style deep-learning map of representative ads. The default view uses a trained neural bottleneck and a cluster-separation projection, so learned groups should be easier to see than in the old SVD diagnostic view.</p>
    <div class="tutorial"><h3>How to read and interact with the corpus map</h3><ul class="small"><li>Each point is a representative ad. The default coordinates come from a shallow neural autoencoder bottleneck, then a separation projection over that learned space.</li><li>Use <b>Projection</b> to compare the default cluster-separation view, the raw 2D neural bottleneck view, and the legacy SVD diagnostic. If separation disappears in SVD, that means the old dimensions were not aligned with the learned clusters.</li><li><b>K-means hulls</b> are centroid-style groups: useful for compact learned neighborhoods, but they can look circular and hide weird boundary pockets.</li><li><b>Deep Isolation Forest cut-slices</b> are tree-cut partitions after neural/random feature transforms: useful for non-circular pockets, boundary cases, and unusual ads. Rectangles are approximate visible extents of those cut-slices, not exact legal boundaries.</li><li><b>Metrics hint:</b> Silhouette higher is better, Davies–Bouldin lower is better, Calinski–Harabasz higher is better, while ARI/NMI compare whether isolation slices agree with k-means. None of these proves semantic truth.</li><li>Always inspect the selected ad annotations before inferring a manipulation technique from a map neighborhood.</li></ul></div>
    <div class="viz-toolbar">
      <label class="small" for="mapProjection">Projection</label><select id="mapProjection" class="control"><option value="deep_separation" selected>Deep separated clusters</option><option value="deep_bottleneck">Deep 2D bottleneck</option><option value="legacy_svd">Legacy SVD diagnostic</option></select>
      <label class="small" for="mapColor">Color by</label><select id="mapColor" class="control"><option value="platform">Platform</option><option value="score">Review score</option><option value="split">Split</option><option value="deep_cluster">Deep cluster</option><option value="isolation_slice">Isolation cut-slice</option><option value="isolation_score">Isolation anomaly score</option></select>
      <label class="small" for="mapOverlay">Overlay</label><select id="mapOverlay" class="control"><option value="both" selected>K-means hulls + isolation cuts</option><option value="kmeans">K-means hulls only</option><option value="isolation">Isolation cut boxes only</option><option value="none">No overlays</option></select>
      <label class="small" for="mapQuery">Search map</label><input id="mapQuery" class="control" placeholder="term, label, title">
      <button id="mapResetLayers" class="btn" type="button">Reset cluster layers</button>
    </div>
    <div id="mapClusterLayers" class="legend-row" aria-label="Interactive cluster layers"></div>
    <div id="mapLegend" class="legend-row" aria-label="Corpus map legend"></div>
    <div id="corpusMapViz" class="big-viz" role="img" aria-label="Corpus embedding scatter plot"></div>
    <div id="mapInspector" class="small"></div>
    <div class="map-info-grid"><div id="mapSelectedDetail" class="map-card"></div><div id="mapNeighbors" class="map-card"></div></div>
    <div id="mapQuadrants" class="map-info-grid"></div>
    <h3 style="margin-top:16px">Explainable deep clusters</h3>
    <p class="small">How to read: these are learned corpus-map neighborhoods, not final labels. Use the cluster terms as hypotheses, the exemplars as sanity checks, and the silhouette/reconstruction metrics as quality signals.</p>
    <div id="deepClusterPanel" class="map-info-grid"></div>
    <h3 style="margin-top:16px">Deep Isolation Forest cut-slices and metric comparison</h3>
    <p class="small">How to read: isolation slices are cut-defined partitions from neural/random representations. They are useful when round hulls hide non-circular pockets or boundary cases.</p>
    <div id="isolationPanel" class="map-info-grid"></div>
  </section>
  <section id="facet-overview" class="panel" style="margin-top:16px">
    <h2>Facet overview and taxonomy matrix</h2>
    <p class="small">Facets-inspired distribution cards plus an annotation taxonomy matrix for reviewer/model sensemaking.</p>
    <div class="tutorial"><h3>How to use facets and taxonomy</h3><ul class="small"><li>Facet cards reveal corpus imbalance and metadata skew across safe categorical features.</li><li>The taxonomy matrix explains each label family/type and what a human reviewer should verify before trusting a span.</li><li>Use this section before interpreting model metrics: skewed facets and low-support labels often explain brittle model behavior.</li></ul></div>
    <div id="facetOverview" class="facet-grid"></div>
    <h3 style="margin-top:16px">Annotation taxonomy matrix</h3><div id="taxonomyMatrix"></div>
  </section>
  <section id="explorer" class="layout" style="margin-top:16px">
    <aside class="panel controls">
      <h2>Top 25 explorer</h2><div class="tutorial"><h3>How to review individual ads</h3><ul class="small"><li>Choose ranking mode, platform, label, or search query to select an ad.</li><li>Use shortcuts: <b>n</b>/<b>p</b> move through ads, <b>/</b> search, <b>1</b>/<b>2</b>/<b>3</b> change ranking.</li><li>Read the center text for exact highlighted spans, then compare the right-side ledger, ELI5 dossier, model probabilities, and council-vs-model mismatch.</li></ul></div>
      <label class="small" for="rankMode">Ranking</label><select id="rankMode" class="control"><option value="top_by_review_priority">Review priority</option><option value="top_by_manipulation">Manipulation</option><option value="top_by_persuasion">Persuasion</option></select>
      <label class="small" for="platformFilter">Platform</label><select id="platformFilter" class="control"><option value="">All platforms</option></select>
      <label class="small" for="labelFilter">Technique</label><select id="labelFilter" class="control"><option value="">All techniques</option></select>
      <label class="small" for="query">Search title/body/label</label><input id="query" class="control" placeholder="e.g. discreción, estudiante, a cambio">
      <button id="copyLink" class="btn" type="button">Copy deep link</button>
      <p class="small">Top 25 shown after filters. Full embedded data contains top 500 per ranking to keep the report responsive.</p>
      <div id="rankList" class="list" role="listbox" aria-label="Ranked ads"></div>
    </aside>
    <section class="panel">
      <div id="detailHead"></div>
      <div class="legend"><span class="chip amber">persuasive span</span><span class="chip red">manipulative/severity span</span><span class="chip blue">context/model metadata</span></div>
      <p class="small">Interpretation guide: highlights are candidate council spans on immutable text offsets. Red underlines signal labels currently treated as higher manipulative-severity categories; amber spans are persuasive or contextual techniques.</p>
      <div id="annotatedText" class="annotated" aria-label="Annotated ad text"></div>
      <h3 style="margin-top:16px">Score arithmetic</h3><div id="waterfall" class="waterfall"></div>
    </section>
    <aside class="panel right-col">
      <h2>Explanation ledger</h2><p class="small">How to read: each row gives the exact excerpt, label type, ELI5 meaning, offsets, and intensity/manipulation/harm scores. Use it to verify whether the highlight really supports the label.</p><div id="ledger" class="ledger"></div>
      <h2 style="margin-top:16px">Annotation dossier / ELI5</h2><div id="annotationDossier" class="dossier"></div>
      <h2 style="margin-top:16px">Model predictions</h2><div id="modelPredictions"></div>
      <h2 style="margin-top:16px">Council vs model</h2><div id="agreementBox" class="small"></div>
    </aside>
  </section>
  <section id="observability" class="grid" style="grid-template-columns:1fr 1fr;margin-top:16px">
    <div class="panel"><h2>Observability and error budget</h2><div class="tutorial"><h3>How to read observability</h3><ul class="small"><li>These rows list known limitations, cohort warnings, and model/corpus status signals.</li><li>Use this before making claims: if a limitation applies, treat the visualization as exploratory rather than validated.</li></ul></div><table class="table" id="obsTable"></table></div>
    <div class="panel"><h2>Label distribution</h2><p class="small">How to read: longer bars are more frequent candidate labels. Common labels can dominate model behavior; rare labels require extra caution.</p><div id="labelChart"></div></div>
  </section>
  <section id="expert-poc" class="panel" style="margin-top:16px">
    <h2>No-code AI expert review proof of concept</h2>
    <p class="small">This layer demonstrates expert annotation judgment and fundable human-review workflow. It is not human-adjudicated gold and is kept separate from candidate council/model outputs.</p>
    <div class="tutorial"><h3>How to interpret the expert POC</h3><ul class="small"><li>This section documents a proof-of-concept expert overlay, not full-corpus human adjudication.</li><li>Use it to show funders what future blinded human review and adjudication would look like.</li><li>Do not mix this layer into gold metrics until human reviewers and adjudicators complete the formal workflow.</li></ul></div>
    <div id="expertPoc"></div>
  </section>
  <section id="research" class="panel" style="margin-top:16px">
    <h2>Research-backed design choices</h2>
    <div class="tutorial"><h3>How to use the research notes</h3><ul class="small"><li>This section explains why the report separates overview, drill-down, local explanations, uncertainty, and limitations.</li><li>Use it as the methodological legend for readers who need to understand what the report can and cannot support.</li><li>For claims, cite the specific metric/visualization and the relevant limitation instead of quoting a single score alone.</li></ul></div>
    <ul class="small">
      <li>Model cards/datasheets practice: expose intended use, limitations, split metrics, and subgroup/cohort warnings.</li>
      <li>Human-centered XAI: provide local explanations, score arithmetic, uncertainty/limitations, and avoid equating explanations with truth.</li>
      <li>Dashboard UX: overview first, zoom/filter, details on demand, keyboard navigation, accessible tables, mobile and print modes.</li>
      <li>Dark-pattern and manipulation research: separate persuasion, manipulation, severity, vulnerability, concealment, and exposure context.</li>
    </ul>
    <p class="small">This report intentionally marks all labels as candidate council outputs. It should not be used as human-adjudicated gold.</p>
  </section>
</main>
<div id="toast" class="toast" role="status" aria-live="polite"></div>
<script id="report-data" type="application/json">__EMBEDDED__</script>
<script src="assets/d3-lite-force.js"></script>
<script>
const payload = JSON.parse(document.getElementById('report-data').textContent);
const data = payload.report, modelReport = payload.modelReport, segmentReport = payload.segmentReport || {};
let mode = 'top_by_review_priority', selected = 0, currentRows = [];
let activeMapClusters = new Set();
let activeMapQuadrant = '';
const manipLabels = new Set(['conditional_financial_support','economic_vulnerability_targeting','privacy_or_secrecy_pressure','guilt_or_shame_pressure','deceptive_assurance','fear_or_threat']);
const labelGuide = {
  conditional_financial_support:{type:'conditional exchange',meaning:'Money or help is framed as dependent on compliance, companionship, secrecy, appearance, or another implied concession.',eli5:'The ad says help is available, but there is a catch.',watch:'Look for “a cambio”, “si eres…”, companionship, discretion, or conditions near money/help.'},
  economic_vulnerability_targeting:{type:'vulnerability targeting',meaning:'The message focuses on financial stress, students, single mothers, family need, or scarcity of resources.',eli5:'It looks for people who may need money badly.',watch:'Student, mother, family, debt, need, economic help, support.'},
  reciprocity_obligation:{type:'reciprocity pressure',meaning:'A gift/help/support frame may make the reader feel they owe attention, contact, loyalty, or compliance.',eli5:'“I help you, so you may feel you should give something back.”',watch:'Brindo/doy apoyo, ayuda económica, support offered as personal favor.'},
  platform_migration:{type:'private-channel migration',meaning:'The ad pushes the reader away from the public platform into WhatsApp, phone, inbox, or another private channel.',eli5:'It asks to move the conversation somewhere harder to monitor.',watch:'WhatsApp, WSP, inbox, privado, phone/email/URL placeholders.'},
  privacy_or_secrecy_pressure:{type:'secrecy pressure',meaning:'Privacy, discretion, or confidentiality is used to reduce scrutiny or normalize hidden interaction.',eli5:'It says “keep this quiet” or makes secrecy part of the offer.',watch:'Discreción, reservado, privado, confidencial.'},
  sexualized_appearance_condition:{type:'appearance/sexual condition',meaning:'The offer is tied to body, age, femininity, attractiveness, or sexualized companionship.',eli5:'Help depends on looking or acting a certain way.',watch:'Bonita, joven, señorita, cuerpo, compañía, beneficios.'},
  age_or_youth_targeting:{type:'age targeting',meaning:'The ad selects or pressures people by age/youth.',eli5:'It is aimed at young people or a narrow age group.',watch:'Joven, 18-25, señorita joven, cualquier edad when paired with support.'},
  education_or_student_targeting:{type:'student targeting',meaning:'The ad calls out students or educational need as part of the persuasion frame.',eli5:'It tries to appeal to students who may need support.',watch:'Estudiante, universitaria, estudios, matrícula.'},
  family_obligation_targeting:{type:'family-obligation targeting',meaning:'Family role or responsibility is used to intensify need or obligation.',eli5:'It uses family pressure as the reason someone might accept.',watch:'Madre soltera, hijos, familia, hogar.'},
  transactional_ambiguity:{type:'ambiguous transaction',meaning:'The exact exchange is left unclear while implying money, benefits, companionship, or intimacy.',eli5:'It sounds like a deal but hides the real terms.',watch:'Beneficios, apoyo, conversar, amistad, compañía without clear boundaries.'},
  deceptive_assurance:{type:'assurance/minimization',meaning:'The ad reassures safety, seriousness, privacy, or harmlessness without evidence.',eli5:'It says “trust me” or “nothing bad” but does not prove it.',watch:'Serio, real, seguro, confiable, sin problemas.'},
  commitment_escalation:{type:'commitment escalation',meaning:'The ad encourages small initial steps that can lead to stronger obligations or risk.',eli5:'Start small now, harder to leave later.',watch:'Primero conversa, prueba, paso a paso, luego vemos.'},
  foot_in_the_door:{type:'foot-in-the-door',meaning:'A low-effort first action is requested before the full ask becomes clear.',eli5:'It asks for an easy first yes.',watch:'Escríbeme, consulta, solo conversa, manda mensaje.'},
  social_proof:{type:'social proof',meaning:'Popularity, normality, or other people’s participation is used as persuasion.',eli5:'It says others do this, so it must be okay.',watch:'Muchas chicas, otros casos, recomendado, todos.'},
  authority_or_status_appeal:{type:'authority/status appeal',meaning:'Status, profession, money, seriousness, or power is used to make the offer seem credible or attractive.',eli5:'It tries to impress you with status.',watch:'Empresario, profesional, solvente, ejecutivo, serio.'},
  exclusivity_or_special_treatment:{type:'special-treatment appeal',meaning:'The reader is made to feel selected, preferred, or eligible for an exclusive benefit.',eli5:'It says you could be specially chosen.',watch:'Especial, exclusiva, selecciono, preferencia.'},
  scarcity_or_urgency:{type:'scarcity/urgency',meaning:'Limited time, limited slots, or pressure to act quickly is used to reduce deliberation.',eli5:'It pushes “decide now”.',watch:'Urgente, hoy, rápido, cupos, inmediato.'},
  fear_or_threat:{type:'fear/threat pressure',meaning:'Fear, loss, danger, or negative consequences are used to motivate action.',eli5:'It tries to scare someone into responding.',watch:'Perder oportunidad, problemas, riesgo, amenaza.'},
  guilt_or_shame_pressure:{type:'guilt/shame pressure',meaning:'Moral judgment, embarrassment, or shame is used to influence response.',eli5:'It makes someone feel bad for not accepting.',watch:'No seas, solo serias, no interesadas, juzgar.'},
  repetition_or_campaign_escalation:{type:'repetition/escalation',meaning:'Repeated templates or escalating offers increase pressure or reach.',eli5:'The same tactic keeps appearing or gets stronger.',watch:'Repeated phrases, reposts, similar ads, escalating benefit/risk.'}
};
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function guideFor(label){return labelGuide[label] || {type:'project label',meaning:'Project-specific persuasion/manipulation annotation.',eli5:'This marks a phrase the council considered relevant.',watch:'Review the excerpt, rationale, and score fields.'}}
function toast(msg){const t=$('toast');t.textContent=msg;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),1800)}
function colorFor(value){
  const palette=['#315d8c','#2f6f4e','#c9802f','#b4473d','#6d4fa3','#72806e','#8f5b2d'];
  let hash=0; for(const ch of String(value||'')) hash=(hash*31+ch.charCodeAt(0))>>>0;
  return palette[hash%palette.length];
}
function allReportRows(){const byId={}; ['top_by_review_priority','top_by_manipulation','top_by_persuasion'].forEach(k=>(data[k]||[]).forEach(r=>byId[r.record_id]=r)); return byId}
function initFilters(){
  Object.keys(data.source_counts).sort().forEach(p=>$('platformFilter').insertAdjacentHTML('beforeend',`<option>${esc(p)}</option>`));
  Object.keys(data.label_counts).sort().forEach(l=>$('labelFilter').insertAdjacentHTML('beforeend',`<option>${esc(l)}</option>`));
  (data.global_explainability?.labels||[]).forEach(row=>$('explainLabel').insertAdjacentHTML('beforeend',`<option value="${esc(row.label)}">${esc(row.label)}</option>`));
}
function rows(){
  const q=$('query').value.toLowerCase(), p=$('platformFilter').value, l=$('labelFilter').value;
  return data[mode].filter(r=>(!p||r.platform===p)&&(!l||r.labels.includes(l))&&(!q||(r.title+' '+(r.text||r.excerpt||'')+' '+r.labels.join(' ')).toLowerCase().includes(q))).slice(0,25);
}
function renderList(){
  currentRows = rows(); if(selected>=currentRows.length) selected=0;
  $('rankList').innerHTML = currentRows.map((r,i)=>`<button class="rank" role="option" aria-current="${i===selected}" aria-selected="${i===selected}" onclick="selectRow(${i})">
    <div class="small">#${i+1} · ${esc(r.platform)} · ${esc(r.split)} · ${esc(r.record_id.slice(0,10))}</div>
    <div class="rank-title">${esc(r.title.slice(0,96))}</div>
    <div class="scoreline"><span class="chip red">priority ${r.scores.review_priority}</span><span class="chip amber">manip ${r.scores.manipulation}</span><span class="chip blue">pers ${r.scores.persuasion}</span></div>
  </button>`).join('');
  renderDetail(currentRows[selected] || data[mode][0]);
}
window.selectRow = i => {selected=i;renderList(); if(currentRows[i]) history.replaceState(null,'','#'+currentRows[i].record_id)};
function segmentText(text, spans){
  const safeSpans = (spans||[]).map(s=>({...s,segments:(s.segments||[]).map(([a,b])=>[Math.max(0,Math.min(text.length,a)),Math.max(0,Math.min(text.length,b))]).filter(([a,b])=>a<b)})).filter(s=>s.segments.length);
  const cuts = new Set([0,text.length]); safeSpans.forEach(s=>s.segments.forEach(([a,b])=>{cuts.add(a);cuts.add(b)}));
  const points=[...cuts].sort((a,b)=>a-b); let out='';
  for(let i=0;i<points.length-1;i++){const a=points[i], b=points[i+1], piece=text.slice(a,b); if(!piece) continue;
    const active=safeSpans.filter(s=>s.segments.some(([x,y])=>a>=x&&b<=y)); const cls=active.some(s=>manipLabels.has(s.label))?'seg manip':(active.length?'seg':'');
    const title=active.map(s=>s.label).join(', ');
    out += cls ? `<span class="${cls}" title="${esc(title)}">${esc(piece)}</span>` : esc(piece);
  } return out;
}
function shiftSpans(spans, delta, minStart=0, maxEnd=Infinity){
  return (spans||[]).map(s=>({...s,segments:(s.segments||[]).map(([a,b])=>[a-delta,b-delta]).filter(([a,b])=>a>=minStart&&b<=maxEnd&&a<b)})).filter(s=>s.segments.length);
}
function bar(label,value,color=''){return `<div class="rowline"><span>${esc(label)}</span><div class="bar"><i style="width:${Math.max(0,Math.min(100,value*100))}%;${color}"></i></div><b>${(value*100).toFixed(0)}%</b></div>`}
function renderDossier(r){
  const spans = r.spans || [];
  if(!spans.length){
    $('annotationDossier').innerHTML = '<p class="small">No candidate annotation spans. This ad is useful as a negative/low-signal example.</p>';
    return;
  }
  const grouped = {};
  spans.forEach(s=>{
    grouped[s.label] ||= {count:0,examples:[],maxIntensity:0,maxManip:0,maxHarm:0};
    grouped[s.label].count += 1;
    if(grouped[s.label].examples.length < 3) grouped[s.label].examples.push(s.excerpt);
    grouped[s.label].maxIntensity = Math.max(grouped[s.label].maxIntensity, Number(s.intensity||0));
    grouped[s.label].maxManip = Math.max(grouped[s.label].maxManip, Number(s.manipulativeness||0));
    grouped[s.label].maxHarm = Math.max(grouped[s.label].maxHarm, Number(s.harm_risk||0));
  });
  const maxHarm = Math.max(...Object.values(grouped).map(g=>g.maxHarm));
  const maxManip = Math.max(...Object.values(grouped).map(g=>g.maxManip));
  const summary = `<div class="dossier-card"><h3>Plain-language readout</h3><p class="small">This ad contains <b>${Object.keys(grouped).length}</b> technique type(s) across <b>${spans.length}</b> span(s). Highest manipulation severity is <b>${maxManip}/3</b>; highest harm risk is <b>${maxHarm}/3</b>. Treat this as candidate council explainability, not human-adjudicated truth.</p></div>`;
  const cards = Object.entries(grouped).sort((a,b)=>b[1].maxManip-a[1].maxManip || b[1].count-a[1].count).map(([label,g])=>{
    const guide=guideFor(label);
    return `<div class="dossier-card"><h3>${esc(label.replaceAll('_',' '))} <span class="type-badge">${esc(guide.type)}</span></h3><div class="eli5"><b>ELI5:</b> ${esc(guide.eli5)}</div><p class="small"><b>What this label means:</b> ${esc(guide.meaning)}</p><p class="small"><b>Why it appears here:</b> ${g.examples.map(x=>'“'+esc(x)+'”').join(' · ')}</p><p class="small"><b>Watch for:</b> ${esc(guide.watch)}<br><b>Count:</b> ${g.count} · <b>max intensity:</b> ${g.maxIntensity}/4 · <b>max manipulation:</b> ${g.maxManip}/3 · <b>max harm:</b> ${g.maxHarm}/3</p></div>`;
  }).join('');
  $('annotationDossier').innerHTML = summary + cards;
}
function renderDetail(r){
  if(!r) return; const fullText = r.text || (r.title + "\\n" + (r.excerpt || ''));
  const title = r.title || fullText.split('\\n')[0] || '';
  const bodyStart = fullText.startsWith(title + '\\n') ? title.length + 1 : 0;
  const body = bodyStart ? fullText.slice(bodyStart) : fullText;
  const titleSpans = shiftSpans(r.spans,0,0,title.length);
  const bodySpans = shiftSpans(r.spans,bodyStart,0,body.length);
  $('detailHead').innerHTML = `<p class="small">${esc(r.record_id)} · ${esc(r.platform)} · ${esc(r.split)} · round ${r.accepted_round}</p><div class="annotated-title">${segmentText(title,titleSpans)}</div><div class="scoreline"><span class="chip red">review ${r.scores.review_priority}</span><span class="chip amber">manipulation ${r.scores.manipulation}</span><span class="chip blue">persuasion ${r.scores.persuasion}</span><span class="chip violet">${r.spans.length} spans</span></div>`;
  $('annotatedText').innerHTML = `<div class="body-label">Ad body</div>${segmentText(body, bodySpans)}`;
  const a=r.scores.arithmetic;
  $('waterfall').innerHTML = `<h4>Persuasion</h4>${bar('weighted span burden',a.persuasion.span_burden)}${bar('max intensity',a.persuasion.max_intensity)}${bar('technique diversity',a.persuasion.technique_diversity)}${bar('repetition/escalation',a.persuasion.repetition_escalation)}<h4>Manipulation</h4>${bar('severity burden',a.manipulation.severity_span_burden)}${bar('max severity',a.manipulation.max_severity)}${bar('vulnerability/conditionality',a.manipulation.vulnerability_conditionality)}${bar('concealment/coercion',a.manipulation.concealment_coercion)}${bar('bounded exposure context',a.context_exposure)}`;
  $('ledger').innerHTML = r.spans.map((s,i)=>{const guide=guideFor(s.label); return `<div class="ledger-row"><span class="chip ${manipLabels.has(s.label)?'red':'amber'}">${i+1}. ${esc(s.label)}</span> <span class="type-badge">${esc(guide.type)}</span><p>${esc(s.excerpt)}</p><p class="small"><b>Meaning:</b> ${esc(guide.meaning)}<br><b>ELI5:</b> ${esc(guide.eli5)}<br>offsets ${esc(JSON.stringify(s.segments))} · intensity ${s.intensity} · manip ${s.manipulativeness} · harm ${s.harm_risk} · ${esc(s.rationale||'')}</p></div>`}).join('') || '<p class="small">No candidate spans.</p>';
  renderDossier(r);
  renderSelectedExplainability(r);
  const allModel = r.model_predictions || r.top_model || [];
  $('modelPredictions').innerHTML = allModel.slice(0,12).map(m=>`${bar(m.label,m.probability,'background:linear-gradient(90deg,var(--blue),var(--violet))')}`).join('') + `<p class="small">Showing top ${Math.min(12,allModel.length)} of ${allModel.length} model labels; agreement uses all embedded probabilities.</p>`;
  const council=new Set(r.labels), model=new Set(allModel.filter(m=>m.probability>=.5).map(m=>m.label));
  const overlap=[...council].filter(x=>model.has(x)); const modelOnly=[...model].filter(x=>!council.has(x)); const councilOnly=[...council].filter(x=>!model.has(x));
  $('agreementBox').innerHTML = `<b>Overlap:</b> ${esc(overlap.join(', ')||'none')}<br><b>Model-only ≥0.5:</b> ${esc(modelOnly.join(', ')||'none')}<br><b>Council-only:</b> ${esc(councilOnly.slice(0,12).join(', ')||'none')}`;
}
function lineChart(points, options={}){
  const width=620,height=300,pad=34;
  const pts=(points||[]).filter(p=>Number.isFinite(p[0])&&Number.isFinite(p[1]));
  const path=pts.map(([x,y],i)=>`${i?'L':'M'}${pad+x*(width-2*pad)} ${height-pad-y*(height-2*pad)}`).join(' ');
  return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(options.label||'metric curve')}"><path class="axis" d="M${pad} ${height-pad}H${width-pad}M${pad} ${height-pad}V${pad}"/><path class="curve base" d="M${pad} ${height-pad}L${width-pad} ${pad}"/><path class="curve ${options.cls||''}" d="${path}"/><text x="${pad}" y="${height-8}" font-size="11">0</text><text x="${width-pad-8}" y="${height-8}" font-size="11">1</text><text x="8" y="${pad+4}" font-size="11">1</text><text x="${width/2-40}" y="20" font-size="13" font-weight="800">${esc(options.title||'')}</text></svg>`;
}
function heatColor(value){
  if(value===null||value===undefined||Number.isNaN(Number(value))) return '#eee6d7';
  const v=Math.max(0,Math.min(1,Number(value))); const hue=20+v*115; return `hsl(${hue} 48% ${88-v*34}%)`;
}
function renderDiagnostics(){
  const test=modelReport.metrics?.test||{}, validation=modelReport.metrics?.validation||{};
  $('curveChart').innerHTML = `<div class="viz-grid" style="grid-template-columns:1fr 1fr"><div>${lineChart(test.roc_curve_micro||[],{title:'Test micro ROC',label:'test micro ROC curve'})}<p class="small">AUC ${test.roc_auc_micro ?? 'n/a'}</p></div><div>${lineChart(test.precision_recall_curve_micro||[],{title:'Test micro precision-recall',label:'test micro precision recall curve',cls:'pr'})}<p class="small">Average precision ${test.average_precision_micro ?? 'n/a'}</p></div></div>`;
  const timeline=(data.iteration_timeline||[]).map(item=>({...item,micro_f1:item.micro_f1 ?? (item.stage==='localized council'?test.micro_f1:null),macro_f1:item.macro_f1 ?? (item.stage==='localized council'?test.macro_f1:null)}));
  $('iterationTimeline').innerHTML = timeline.map((item,i)=>`<div class="timeline-row"><b>${esc(item.date)}</b><div><b>${esc(item.stage)}</b><br><span class="small">${esc(item.note)} · records ${item.records}${item.spans?` · spans ${item.spans}`:''}</span></div><div><span class="tag blue">μF1 ${item.micro_f1 ?? 'n/a'}</span><br><span class="tag amber">MF1 ${item.macro_f1 ?? 'n/a'}</span></div></div>`).join('');
  const labels=Object.entries(test.per_label||{}).sort((a,b)=>(b[1].support||0)-(a[1].support||0)).slice(0,20);
  $('metricHeatmap').innerHTML = `<div class="heat-row"><b>Label</b><b>F1</b><b>AUC</b><b>Acc</b><b>Support</b></div>` + labels.map(([label,m])=>`<div class="heat-row"><span title="${esc(label)}">${esc(label.replaceAll('_',' ').slice(0,26))}</span><span class="heat-cell" style="background:${heatColor(m.f1)}">${m.f1}</span><span class="heat-cell" style="background:${heatColor(m.roc_auc)}">${m.roc_auc ?? 'n/a'}</span><span class="heat-cell" style="background:${heatColor(m.accuracy)}">${m.accuracy}</span><b>${m.support}</b></div>`).join('');
  const known=[['Raw collection','10,293 HTML archives collected; strict extraction rejects interstitials/duplicates.'],['Offer filter','5,717 modeling records; 21 strict processed records excluded by offer-preferring filter.'],['Research-v2','Rubric expanded after survey/source review.'],['Spanish localization','Gender/accent/typo/slang omissions fixed in candidate council layer.'],['No-code expert POC','Direct expert overlay created for seed issue; full human review remains funding-dependent.'],['Current model','Agreement metrics use candidate council labels, not human gold.']];
  $('errorTimeline').innerHTML = known.map(([stage,note])=>`<div class="timeline-row"><b>${esc(stage)}</b><div class="small">${esc(note)}</div><span class="tag ${stage.includes('Current')?'red':'blue'}">${stage.includes('fixed')?'fixed':'tracked'}</span></div>`).join('');
  renderSegmentDiagnostics();
}
function sliceCard(row){
  const terms=(row.top_terms||[]).map(t=>`<span class="tag">${esc(t)}</span>`).join('');
  return `<div class="slice-card"><b>${esc(row.dimension)} = ${esc(row.value)}</b><div class="small">${row.records} test records · default μF1 ${row.default?.micro_f1 ?? 'n/a'} · tuned μF1 ${row.threshold_tuned?.micro_f1 ?? 'n/a'} · Δ ${row.delta_micro_f1 ?? 'n/a'}</div>${terms?`<div class="terms">${terms}</div>`:''}</div>`;
}
function renderSegmentDiagnostics(){
  if(!segmentReport.status){$('sliceWeakness').innerHTML='<p class="small">Segment report not generated.</p>';return}
  const weak=(segmentReport.underperforming_slices||[]).slice(0,8);
  $('sliceWeakness').innerHTML = weak.map(sliceCard).join('') || '<p class="small">No underperforming slices above minimum support threshold.</p>';
  $('clusterSummary').innerHTML = (segmentReport.clusters||[]).slice(0,10).map(c=>`<div class="slice-card"><b>${esc(c.cluster)}</b><div class="small">${c.records} corpus records</div><div class="terms">${(c.top_terms||[]).map(t=>`<span class="tag blue">${esc(t)}</span>`).join('')}</div></div>`).join('');
  const d=segmentReport.overall_default||{}, t=segmentReport.overall_threshold_tuned||{};
  const notes=(segmentReport.method_notes||[]).map(n=>`<li>${esc(n)}</li>`).join('');
  const unavailable=segmentReport.unavailable_features?.posting_date_range ? `<p class="small"><b>Temporal feature note:</b> ${esc(segmentReport.unavailable_features.posting_date_range)}</p>` : '';
  $('thresholdOverlay').innerHTML = `<table class="table"><tr><th>Metric</th><th>Default .50</th><th>Validation-tuned</th><th>Δ</th></tr>${['micro_f1','macro_f1','subset_accuracy','label_accuracy'].map(k=>`<tr><td>${esc(k)}</td><td>${d[k] ?? 'n/a'}</td><td>${t[k] ?? 'n/a'}</td><td>${(Number(t[k]||0)-Number(d[k]||0)).toFixed(4)}</td></tr>`).join('')}</table>${unavailable}<ul class="small">${notes}</ul><p class="small">Privacy-safe provider feature status: email domains are unavailable/redacted unless already safe in extracted text.</p>`;
}
function termPills(terms){
  return (terms||[]).slice(0,12).map(t=>`<span class="term-pill"><span>${esc(t.term)}</span><b>${Number(t.weight).toFixed(2)}</b></span>`).join('');
}
function renderExplainabilityAtlas(){
  const selectedLabel=$('explainLabel').value || data.global_explainability?.labels?.[0]?.label;
  const row=(data.global_explainability?.labels||[]).find(x=>x.label===selectedLabel);
  if(!row){$('explainabilityAtlas').innerHTML='<p class="small">No global explanations available.</p>';return}
  const warning=row.low_support ? `<p class="warn small"><b>Low support:</b> this label has ${row.support} test examples; treat metrics and coefficients cautiously.</p>` : '';
  $('explainabilityAtlas').innerHTML = `<div class="coef-card"><h3>${esc(row.label.replaceAll('_',' '))}</h3><p class="small"><b>Tutorial:</b> start with support and F1/AUC to judge reliability, then read positive terms as model evidence that raises this label. Contrast terms help explain why similar ads may not trigger it.</p><p class="small"><b>Family:</b> ${esc(row.family)} · <b>Type:</b> ${esc(row.type)} · <b>Support:</b> ${row.support}<br><b>F1:</b> ${row.f1 ?? 'n/a'} · <b>Precision:</b> ${row.precision ?? 'n/a'} · <b>Recall:</b> ${row.recall ?? 'n/a'} · <b>AUC:</b> ${row.roc_auc ?? 'n/a'}</p>${warning}<h4>Terms pushing this label up</h4>${termPills(row.top_positive_terms)}<h4>Contrast terms</h4>${termPills(row.contrast_terms)}<p class="small">${esc(data.global_explainability?.method || '')}</p></div><div class="coef-card"><h3>Selected-ad local evidence</h3><p class="small"><b>Tutorial:</b> after selecting an ad, compare model term hits with council spans. Agreement supports review confidence; mismatch means inspect manually.</p><div id="selectedEvidence" class="small">Select an ad to show local overlap between council spans, model predictions, and coefficient terms.</div></div><div class="coef-card"><h3>Caveats</h3><p class="small"><b>Tutorial:</b> read these caveats before using explanation terms in any claim or presentation.</p><ul class="small">${(data.global_explainability?.caveats||[]).map(c=>`<li>${esc(c)}</li>`).join('')}</ul></div>`;
}
function renderSelectedExplainability(r){
  if(!$('selectedEvidence')) return;
  const selectedLabel=$('explainLabel').value || r.labels?.[0];
  const row=(data.global_explainability?.labels||[]).find(x=>x.label===selectedLabel);
  const terms=(row?.top_positive_terms||[]).map(t=>t.term.toLowerCase());
  const text=(r.text||'').toLowerCase();
  const hits=terms.filter(t=>text.includes(t)).slice(0,10);
  const prob=(r.model_predictions||[]).find(m=>m.label===selectedLabel)?.probability;
  const council=r.labels.includes(selectedLabel);
  $('selectedEvidence').innerHTML = `<b>Selected label:</b> ${esc(selectedLabel)}<br><b>Council has label:</b> ${council?'yes':'no'} · <b>model probability:</b> ${prob ?? 'n/a'}<br><b>Coefficient terms present in ad:</b> ${esc(hits.join(', ')||'none among top terms')}<br><b>Span examples:</b> ${esc((r.spans||[]).filter(s=>s.label===selectedLabel).slice(0,3).map(s=>s.excerpt).join(' · ') || 'none')}`;
}
function tooltip(){
  let t=document.querySelector('.tooltip'); if(!t){t=document.createElement('div');t.className='tooltip';document.body.appendChild(t)} return t;
}
function shortNodeLabel(node){
  const name=String(node.name||'');
  const clean=node.kind==='label' ? name.replaceAll('_',' ') : name;
  return clean.length > 22 ? clean.slice(0,20)+'…' : clean;
}
function nodeLabelPriority(node){
  if(node.kind==='label') return 10000;
  if(node.kind==='platform') return 9000;
  return Number(node.weight||1);
}
function overlapBox(a,b,pad=2){
  return !(a.x+a.w+pad < b.x || b.x+b.w+pad < a.x || a.y+a.h+pad < b.y || b.y+b.h+pad < a.y);
}
function placeNetworkLabels(nodes, width, height, maxWeight, mode){
  if(mode==='hidden') return [];
  const sorted=[...nodes].sort((a,b)=>nodeLabelPriority(b)-nodeLabelPriority(a));
  const visibleLimit = mode==='important' ? 32 : 58;
  const occupied = nodes.map(n=>{
    const r=n.kind==='term'?5+14*Math.sqrt((n.weight||1)/maxWeight):n.kind==='label'?11:9;
    return {x:n.x-r-2,y:n.y-r-2,w:2*r+4,h:2*r+4,type:'node'};
  });
  const placements=[];
  for(const node of sorted){
    if(placements.length>=visibleLimit && node.kind==='term') continue;
    if(mode==='important' && node.kind==='term' && nodeLabelPriority(node)<sorted[Math.min(visibleLimit,sorted.length-1)].weight) continue;
    const text=shortNodeLabel(node), w=Math.max(34, text.length*6.2+10), h=15;
    const r=node.kind==='term'?5+14*Math.sqrt((node.weight||1)/maxWeight):node.kind==='label'?11:9;
    const candidates=[
      {x:node.x+r+9,y:node.y-h/2,anchor:'start'},
      {x:node.x-r-w-9,y:node.y-h/2,anchor:'start'},
      {x:node.x-w/2,y:node.y-r-h-8,anchor:'middle'},
      {x:node.x-w/2,y:node.y+r+8,anchor:'middle'},
      {x:node.x+r+8,y:node.y+r+4,anchor:'start'},
      {x:node.x-r-w-8,y:node.y+r+4,anchor:'start'},
      {x:node.x+r+8,y:node.y-r-h-4,anchor:'start'},
      {x:node.x-r-w-8,y:node.y-r-h-4,anchor:'start'},
    ];
    const fit=candidates.find(c=>{
      const box={x:Math.max(4,Math.min(width-w-4,c.x)),y:Math.max(4,Math.min(height-h-4,c.y)),w,h};
      return !occupied.some(o=>overlapBox(box,o,3));
    });
    if(!fit) continue;
    const box={x:Math.max(4,Math.min(width-w-4,fit.x)),y:Math.max(4,Math.min(height-h-4,fit.y)),w,h};
    occupied.push(box);
    placements.push({...box,node,text,anchor:fit.anchor,leader:Math.abs((box.x+w/2)-node.x)>r+12 || Math.abs((box.y+h/2)-node.y)>r+12});
  }
  return placements;
}
function renderTermNetwork(){
  const container=$('termNetworkViz'), status=$('networkStatus'); const network=data.term_network||{};
  const kind=$('networkKind').value, topN=Number($('networkTopN').value||100), labelMode=$('networkLabelMode').value;
  let nodes=(network.nodes||[]).filter(n=>!kind||n.kind===kind||n.kind!=='term').slice(0,topN);
  const nodeIds=new Set(nodes.map(n=>n.id));
  let edges=(network.edges||[]).filter(e=>nodeIds.has(e.source)&&nodeIds.has(e.target)).slice(0,260);
  status.textContent = `${nodes.length} nodes · ${edges.length} edges · runtime ${window.d3?.version || 'vanilla fallback'}`;
  $('networkInspector').innerHTML = '<b>How to interpret selections:</b> clicked terms show example record ids and linked labels. Treat links as co-occurrence clues for reviewer navigation, not as causal or validated manipulation evidence.';
  if(!nodes.length){container.innerHTML='<p class="small" style="padding:16px">No network data.</p>';return}
  const width=980,height=620; const laid=window.d3LiteForce?.layout ? window.d3LiteForce.layout(nodes,edges,{width,height,charge:-390,iterations:230}) : {nodes:nodes.map((n,i)=>({...n,x:width/2+Math.cos(i/nodes.length*Math.PI*2)*310,y:height/2+Math.sin(i/nodes.length*Math.PI*2)*230})),links:edges.map(e=>({source:nodes.find(n=>n.id===e.source),target:nodes.find(n=>n.id===e.target),weight:e.weight,kind:e.kind})).filter(e=>e.source&&e.target)};
  const maxWeight=Math.max(...laid.nodes.map(n=>n.weight||1),1);
  const labels=placeNetworkLabels(laid.nodes,width,height,maxWeight,labelMode);
  status.textContent += ` · ${labels.length} visible smart labels`;
  container.innerHTML = `<svg viewBox="0 0 ${width} ${height}" width="100%" height="100%" aria-label="term network">${laid.links.map(e=>`<line class="network-edge" x1="${e.source.x}" y1="${e.source.y}" x2="${e.target.x}" y2="${e.target.y}" stroke-width="${Math.min(5,0.8+Math.sqrt(e.weight||1)/2)}"></line>`).join('')}${laid.nodes.map(n=>`<g class="network-node" tabindex="0" data-node="${esc(n.id)}" aria-label="${esc(n.name)}"><circle cx="${n.x}" cy="${n.y}" r="${n.kind==='term'?5+14*Math.sqrt((n.weight||1)/maxWeight):n.kind==='label'?11:9}" fill="${n.kind==='label'?'#b4473d':n.kind==='platform'?'#315d8c':'#2f6f4e'}" opacity=".88"></circle></g>`).join('')}<g class="network-label-layer">${labels.map(p=>`${p.leader?`<line class="network-leader" x1="${p.node.x}" y1="${p.node.y}" x2="${p.x+p.w/2}" y2="${p.y+p.h/2}"></line>`:''}<g class="network-label-group" data-label-node="${esc(p.node.id)}"><rect class="network-label-bg" x="${p.x}" y="${p.y}" width="${p.w}" height="${p.h}" rx="6"></rect><text class="network-label" x="${p.x+p.w/2}" y="${p.y+11}" text-anchor="middle">${esc(p.text)}</text></g>`).join('')}</g></svg>`;
  container.querySelectorAll('.network-node').forEach(el=>{
    const node=laid.nodes.find(n=>n.id===el.dataset.node); const show=ev=>{const t=tooltip();t.innerHTML=`<b>${esc(node.name)}</b><br>${esc(node.kind)} · weight ${node.weight||1}<br>${esc(Object.entries(node.label_counts||{}).slice(0,4).map(([k,v])=>`${k}:${v}`).join(' · '))}`;t.style.display='block';t.style.left=(ev.clientX+12)+'px';t.style.top=(ev.clientY+12)+'px'}; const hide=()=>tooltip().style.display='none';
    el.addEventListener('mousemove',show); el.addEventListener('mouseleave',hide); el.addEventListener('focus',ev=>show({clientX:40,clientY:120})); el.addEventListener('blur',hide);
    el.addEventListener('click',()=>{$('networkInspector').innerHTML=`<b>${esc(node.name)}</b> · ${esc(node.kind)}<br>Examples: ${(node.examples||[]).map(id=>`<a href="#${esc(id)}">${esc(id.slice(0,10))}</a>`).join(' ')||'n/a'}<br>Labels: ${esc(Object.entries(node.label_counts||{}).map(([k,v])=>`${k} ${v}`).join(' · ')||'n/a')}`});
  });
}
function selectRecordFromMap(recordId){
  const rowMap=allReportRows(); if(!rowMap[recordId]){location.hash=recordId;toast('Record linked but not in top-500 embedded explorer');return}
  for(const candidateMode of ['top_by_review_priority','top_by_manipulation','top_by_persuasion']){
    const idx=(data[candidateMode]||[]).findIndex(r=>r.record_id===recordId);
    if(idx>=0){mode=candidateMode;$('rankMode').value=mode;$('platformFilter').value='';$('labelFilter').value='';$('query').value='';selected=Math.min(idx,24);renderList();location.hash=recordId;document.getElementById('explorer').scrollIntoView({block:'start'});return}
  }
}
function topCounts(items, limit=3){
  const counts={}; items.filter(Boolean).forEach(x=>counts[x]=(counts[x]||0)+1);
  return Object.entries(counts).sort((a,b)=>b[1]-a[1]).slice(0,limit).map(([k,v])=>`${k} ${v}`);
}
function deepClusters(){
  return data.corpus_map?.deep_clusters?.clusters || [];
}
function isolationData(){
  return data.corpus_map?.deep_clusters?.deep_isolation || {};
}
function isolationSlices(){
  return isolationData().slices || [];
}
function deepClusterById(id){
  return deepClusters().find(cluster=>cluster.id===id);
}
function isolationSliceById(id){
  return isolationSlices().find(slice=>slice.id===id);
}
function deepClusterName(id){
  const cluster=deepClusterById(id);
  return cluster ? cluster.name : (id || 'unclustered');
}
function deepClusterTitle(id){
  const cluster=deepClusterById(id);
  return cluster ? (cluster.eli5_title || cluster.name) : (id || 'unclustered');
}
function pointCoord(p, projection){
  const chosen=p.projections?.[projection] || p.projections?.[data.corpus_map?.deep_clusters?.default_projection] || p.projections?.deep_separation || {x:p.x,y:p.y};
  return {x:Number(chosen.x)||0,y:Number(chosen.y)||0};
}
function quadrantName(p, projection){
  const coord=pointCoord(p, projection);
  if(coord.x>=0 && coord.y>=0) return 'Upper right';
  if(coord.x<0 && coord.y>=0) return 'Upper left';
  if(coord.x<0 && coord.y<0) return 'Lower left';
  return 'Lower right';
}
function renderMapLegend(points, colorMode){
  if(colorMode==='score'){
    $('mapLegend').innerHTML = `<span class="legend-item"><span class="swatch" style="background:hsl(120 54% 48%)"></span>lower review score</span><span class="legend-item"><span class="swatch" style="background:hsl(45 54% 48%)"></span>medium</span><span class="legend-item"><span class="swatch" style="background:hsl(15 54% 48%)"></span>higher review score</span>`;
    return;
  }
  if(colorMode==='deep_cluster'){
    const values=[...new Set(points.map(p=>p.deep_cluster).filter(Boolean))].sort();
    $('mapLegend').innerHTML = values.map(v=>`<span class="legend-item"><span class="swatch" style="background:${colorFor(v)}"></span>${esc(deepClusterTitle(v).slice(0,42))}</span>`).join('');
    return;
  }
  if(colorMode==='isolation_slice'){
    const values=[...new Set(points.map(p=>p.isolation_slice).filter(Boolean))].sort();
    $('mapLegend').innerHTML = values.map(v=>`<span class="legend-item"><span class="swatch" style="background:${colorFor(v)}"></span>${esc((isolationSliceById(v)?.name||v).slice(0,38))}</span>`).join('');
    return;
  }
  if(colorMode==='isolation_score'){
    $('mapLegend').innerHTML = `<span class="legend-item"><span class="swatch" style="background:hsl(210 54% 48%)"></span>lower isolation score</span><span class="legend-item"><span class="swatch" style="background:hsl(45 54% 48%)"></span>medium</span><span class="legend-item"><span class="swatch" style="background:hsl(0 54% 48%)"></span>higher anomaly score</span>`;
    return;
  }
  const values=[...new Set(points.map(p=>colorMode==='split'?p.split:p.platform))].sort();
  $('mapLegend').innerHTML = values.map(v=>`<span class="legend-item"><span class="swatch" style="background:${colorFor(v)}"></span>${esc(v)}</span>`).join('');
}
function resetMapLayers(){activeMapClusters=new Set(deepClusters().map(c=>c.id));activeMapQuadrant='';$('mapColor').value='deep_cluster';renderCorpusMap()}
function isolateMapCluster(id){activeMapClusters=new Set([id]);activeMapQuadrant='';$('mapColor').value='deep_cluster';renderCorpusMap()}
function toggleMapCluster(id){
  if(!activeMapClusters.size) activeMapClusters=new Set(deepClusters().map(c=>c.id));
  if(activeMapClusters.has(id)) activeMapClusters.delete(id); else activeMapClusters.add(id);
  $('mapColor').value='deep_cluster';renderCorpusMap();
}
function focusMapQuadrant(name){activeMapQuadrant=name;renderCorpusMap()}
function renderClusterLayerControls(){
  const clusters=deepClusters();
  if(!clusters.length){$('mapClusterLayers').innerHTML='';return}
  if(!activeMapClusters.size) activeMapClusters=new Set(clusters.map(c=>c.id));
  $('mapClusterLayers').innerHTML = clusters.map(cluster=>{
    const on=activeMapClusters.has(cluster.id);
    return `<span class="legend-item"><button class="btn" type="button" aria-pressed="${on}" onclick="toggleMapCluster('${esc(cluster.id)}')" style="background:${on?colorFor(cluster.id):'#fff'};color:${on?'#fff':'var(--ink)'}">${on?'✓':'○'} ${esc((cluster.eli5_title||cluster.name).slice(0,36))}</button><button class="btn" type="button" onclick="isolateMapCluster('${esc(cluster.id)}')">solo</button></span>`;
  }).join('');
}
function clusterHull(points, cx, cy){
  const groups={};
  points.forEach(p=>{if(p.deep_cluster){(groups[p.deep_cluster] ||= []).push(p)}});
  return Object.entries(groups).filter(([id,rows])=>rows.length>=3).map(([id,rows])=>{
    const xs=rows.map(cx), ys=rows.map(cy), minX=Math.min(...xs), maxX=Math.max(...xs), minY=Math.min(...ys), maxY=Math.max(...ys);
    const rx=Math.max(24,(maxX-minX)/2+18), ry=Math.max(18,(maxY-minY)/2+14);
    return `<ellipse cx="${(minX+maxX)/2}" cy="${(minY+maxY)/2}" rx="${rx}" ry="${ry}" fill="${colorFor(id)}" fill-opacity=".08" stroke="${colorFor(id)}" stroke-opacity=".38" stroke-width="2" stroke-dasharray="7 5"></ellipse>`;
  }).join('');
}
function isolationSliceBoxes(points, cx, cy){
  const groups={};
  points.forEach(p=>{if(p.isolation_slice){(groups[p.isolation_slice] ||= []).push(p)}});
  return Object.entries(groups).filter(([id,rows])=>rows.length>=2).map(([id,rows])=>{
    const xs=rows.map(cx), ys=rows.map(cy), minX=Math.min(...xs), maxX=Math.max(...xs), minY=Math.min(...ys), maxY=Math.max(...ys);
    const padX=12, padY=10;
    return `<rect x="${minX-padX}" y="${minY-padY}" width="${Math.max(18,maxX-minX+padX*2)}" height="${Math.max(18,maxY-minY+padY*2)}" rx="7" fill="none" stroke="${colorFor(id)}" stroke-opacity=".55" stroke-width="1.8" stroke-dasharray="3 4"></rect>`;
  }).join('');
}
function renderMapQuadrants(visiblePoints, allPoints, projection){
  const groups={'Upper right':[],'Upper left':[],'Lower left':[],'Lower right':[]};
  const fullGroups={'Upper right':[],'Upper left':[],'Lower left':[],'Lower right':[]};
  visiblePoints.forEach(p=>groups[quadrantName(p, projection)].push(p));
  allPoints.forEach(p=>fullGroups[quadrantName(p, projection)].push(p));
  $('mapQuadrants').innerHTML = Object.entries(groups).map(([name,rows])=>{
    const baseline=fullGroups[name]||[];
    const basis=rows.length ? rows : baseline;
    const labels=topCounts(basis.flatMap(r=>r.labels||[]),4).join(' · ') || 'No dominant labels in baseline';
    const platforms=topCounts(basis.map(r=>r.platform),3).join(' · ') || 'No platform baseline';
    const clusters=topCounts(basis.map(r=>deepClusterById(r.deep_cluster)?.eli5_title || deepClusterName(r.deep_cluster)),3).join(' · ') || 'No cluster baseline';
    const slices=topCounts(basis.map(r=>isolationSliceById(r.isolation_slice)?.name || r.isolation_slice),3).join(' · ') || 'No isolation-slice baseline';
    const scores=basis.length ? (basis.reduce((s,r)=>s+r.review_priority,0)/basis.length).toFixed(1) : '0.0';
    const exemplars=basis.slice().sort((a,b)=>b.review_priority-a.review_priority).slice(0,2).map(r=>`<button type="button" onclick="selectRecordFromMap('${esc(r.record_id)}')"><b>${esc(r.title.slice(0,70))}</b><br><span class="small">${esc(r.platform)} · review ${r.review_priority}</span></button>`).join('');
    const emptyNote=rows.length ? '' : `<p class="small warn">No visible ads in this quadrant under current filters/layers. Showing full-map baseline context from ${baseline.length} ads.</p>`;
    return `<div class="map-card"><h3>${esc(name)} quadrant</h3><p class="small"><b>How to read:</b> this region groups ads with similar selected-projection direction, not a named human topic.</p>${emptyNote}<p class="small"><b>Visible/full ads:</b> ${rows.length} / ${baseline.length} · <b>avg review:</b> ${scores}<br><b>Top clusters:</b> ${esc(clusters)}<br><b>Top isolation slices:</b> ${esc(slices)}<br><b>Platforms:</b> ${esc(platforms)}<br><b>Dominant labels:</b> ${esc(labels)}</p><button class="btn" type="button" onclick="focusMapQuadrant('${esc(name)}')">Focus this quadrant</button><div class="neighbor-list" style="margin-top:6px">${exemplars}</div></div>`;
  }).join('');
}
function nearestMapNeighbors(point, points, projection, limit=6){
  const base=pointCoord(point, projection);
  return points.filter(p=>p.record_id!==point.record_id).map(p=>{const coord=pointCoord(p, projection);return {...p,distance:Math.hypot(coord.x-base.x,coord.y-base.y)}}).sort((a,b)=>a.distance-b.distance).slice(0,limit);
}
function renderSelectedMapPoint(point, points, projection){
  if(!point){
    $('mapSelectedDetail').innerHTML = '<h3>Selected point</h3><p class="small">Click a map point to see ad metadata, scores, labels, and nearest neighbors.</p>';
    $('mapNeighbors').innerHTML = '<h3>Nearest neighbors</h3><p class="small">Nearest neighbors appear after selecting a point.</p>';
    return;
  }
  const cluster=deepClusterById(point.deep_cluster);
  const slice=isolationSliceById(point.isolation_slice);
  const clusterTerms=(cluster?.top_terms||[]).slice(0,6).map(t=>t.term).join(', ') || 'n/a';
  $('mapSelectedDetail').innerHTML = `<h3>Selected point</h3><p class="small"><b>${esc(point.title)}</b><br>${esc(point.platform)} · ${esc(point.split)} · spans ${point.span_count}<br><b>Review:</b> ${point.review_priority} · <b>Manip:</b> ${point.manipulation} · <b>Pers:</b> ${point.persuasion}<br><b>Labels:</b> ${esc((point.labels||[]).join(', ')||'none')}<br><b>Deep cluster:</b> ${esc(cluster?.eli5_title || cluster?.name || 'n/a')}<br><b>Isolation slice:</b> ${esc(slice?.name || point.isolation_slice || 'n/a')} · anomaly ${point.isolation_anomaly_score ?? 'n/a'}<br><b>ELI5:</b> ${esc(cluster?.eli5_description || 'No cluster explanation available.')}<br><b>Cluster terms:</b> ${esc(clusterTerms)}</p><button class="btn" type="button" onclick="selectRecordFromMap('${esc(point.record_id)}')">Open in ad explorer</button>`;
  const neighbors=nearestMapNeighbors(point,points,projection);
  $('mapNeighbors').innerHTML = `<h3>Nearest neighbors</h3><p class="small">How to read: these ads are nearby in the selected 2D projection. Use them to inspect repeated templates or model blind spots.</p><div class="neighbor-list">${neighbors.map(n=>`<button type="button" onclick="selectRecordFromMap('${esc(n.record_id)}')"><b>${esc(n.title.slice(0,80))}</b><br><span class="small">${esc(n.platform)} · distance ${n.distance.toFixed(3)} · ${esc((n.labels||[]).slice(0,3).join(', '))}</span></button>`).join('')}</div>`;
}
function renderDeepClusterPanel(points){
  const map=data.corpus_map||{}, clusterMeta=map.deep_clusters||{}, clusters=deepClusters();
  if(!clusters.length){
    $('deepClusterPanel').innerHTML = '<div class="map-card"><h3>Deep clusters unavailable</h3><p class="small">The local report did not have enough rows/features to train stable neural-bottleneck clusters.</p></div>';
    return;
  }
  const visibleCounts={}; points.forEach(p=>{if(p.deep_cluster) visibleCounts[p.deep_cluster]=(visibleCounts[p.deep_cluster]||0)+1});
  const metrics=clusterMeta.metrics||{};
  const metricCard = `<div class="map-card"><h3>Model quality signals</h3><p class="small"><b>How to read:</b> higher silhouette suggests cleaner separation; lower reconstruction MSE suggests the bottleneck preserved more SVD information.</p><p class="small"><b>Sample:</b> ${metrics.sample_size ?? 'n/a'} · <b>clusters:</b> ${metrics.cluster_count ?? clusters.length}<br><b>bottleneck:</b> ${metrics.bottleneck_width ?? 'n/a'} · <b>MLP iters:</b> ${metrics.mlp_iterations ?? 'n/a'}<br><b>silhouette:</b> ${metrics.silhouette ?? 'n/a'} · <b>reconstruction MSE:</b> ${metrics.reconstruction_mse ?? 'n/a'}</p></div>`;
  const cards = clusters.map(cluster=>{
    const terms=(cluster.top_terms||[]).slice(0,8).map(t=>`<span class="term-pill">${esc(t.term)} <b>${t.count}</b></span>`).join('');
    const labels=(cluster.dominant_labels||[]).slice(0,4).map(x=>`${x.label} ${x.count}`).join(' · ') || 'n/a';
    const platforms=(cluster.dominant_platforms||[]).slice(0,4).map(x=>`${x.platform} ${x.count}`).join(' · ') || 'n/a';
    const exemplars=(cluster.exemplars||[]).slice(0,3).map(ex=>`<button type="button" onclick="selectRecordFromMap('${esc(ex.record_id)}')"><b>${esc(ex.title.slice(0,78))}</b><br><span class="small">${esc(ex.platform)} · review ${ex.review_priority} · distance ${ex.distance}</span></button>`).join('');
    return `<div class="map-card"><h3><span class="swatch" style="background:${colorFor(cluster.id)}"></span> ${esc(cluster.eli5_title || cluster.name)}</h3><p class="small"><b>Visible/map ads:</b> ${visibleCounts[cluster.id]||0} / ${cluster.count}<br><b>Avg review/manip/pers:</b> ${cluster.scores?.avg_review_priority ?? 'n/a'} / ${cluster.scores?.avg_manipulation ?? 'n/a'} / ${cluster.scores?.avg_persuasion ?? 'n/a'}<br><b>Platforms:</b> ${esc(platforms)}<br><b>Dominant labels:</b> ${esc(labels)}</p><p class="small"><b>What this means:</b> ${esc(cluster.eli5_description || cluster.interpretation || 'Learned text-neighborhood hypothesis.')}</p><p class="small"><b>Likely pattern:</b> ${esc(cluster.likely_pattern || 'Shared wording or template structure.')}<br><b>Main risk:</b> ${esc(cluster.risk_characterization || 'Review exact spans before drawing conclusions.')}<br><b>Reviewer should check:</b> ${esc(cluster.review_guidance || 'Inspect exemplar ads and annotations.')}</p><div>${terms}</div><div class="scoreline"><button class="btn" type="button" onclick="isolateMapCluster('${esc(cluster.id)}')">Highlight on map</button><button class="btn" type="button" onclick="toggleMapCluster('${esc(cluster.id)}')">Toggle layer</button></div><p class="small"><b>Confidence note:</b> ${esc(cluster.confidence_note || '')}</p><div class="neighbor-list">${exemplars}</div></div>`;
  }).join('');
  $('deepClusterPanel').innerHTML = metricCard + cards;
}
function renderIsolationPanel(points){
  const iso=isolationData(), metrics=iso.metrics||{}, slices=isolationSlices();
  if(!slices.length){$('isolationPanel').innerHTML='<div class="map-card"><h3>No isolation slices</h3><p class="small">Deep Isolation Forest slices were not generated.</p></div>';return}
  const visibleCounts={}; points.forEach(p=>{if(p.isolation_slice) visibleCounts[p.isolation_slice]=(visibleCounts[p.isolation_slice]||0)+1});
  const metricRows=[
    ['K-means · bottleneck', metrics.kmeans_bottleneck],
    ['K-means · visible projection', metrics.kmeans_projection],
    ['Isolation slices · bottleneck', metrics.deep_isolation_bottleneck],
    ['Isolation slices · visible projection', metrics.deep_isolation_projection],
  ];
  const metricCard=`<div class="map-card"><h3>SOTA-style clustering metric comparison</h3><p class="small"><b>How to read:</b> use multiple metrics because each has a bias. Silhouette higher is better; Davies–Bouldin lower is better; Calinski–Harabasz higher is better. ARI/NMI compare isolation slices to k-means and should not be forced to 1.0.</p><table class="table"><tr><th>Layer</th><th>Sil</th><th>DB↓</th><th>CH↑</th></tr>${metricRows.map(([name,m])=>`<tr><td>${esc(name)}</td><td>${m?.silhouette ?? 'n/a'}</td><td>${m?.davies_bouldin ?? 'n/a'}</td><td>${m?.calinski_harabasz ?? 'n/a'}</td></tr>`).join('')}</table><p class="small"><b>ARI vs k-means:</b> ${metrics.ari_vs_deep_kmeans ?? 'n/a'} · <b>NMI:</b> ${metrics.nmi_vs_deep_kmeans ?? 'n/a'} · <b>avg anomaly:</b> ${metrics.avg_anomaly_score ?? 'n/a'}<br><b>Method:</b> ${esc(iso.method||'n/a')}</p></div>`;
  const cards=slices.map(slice=>{
    const labels=(slice.dominant_labels||[]).slice(0,4).map(x=>`${x.label} ${x.count}`).join(' · ')||'n/a';
    const platforms=(slice.dominant_platforms||[]).slice(0,3).map(x=>`${x.platform} ${x.count}`).join(' · ')||'n/a';
    const clusters=(slice.dominant_deep_clusters||[]).slice(0,3).map(x=>`${deepClusterTitle(x.cluster)} ${x.count}`).join(' · ')||'n/a';
    const exemplars=(slice.exemplars||[]).slice(0,3).map(ex=>`<button type="button" onclick="selectRecordFromMap('${esc(ex.record_id)}')"><b>${esc(ex.title.slice(0,78))}</b><br><span class="small">${esc(ex.platform)} · anomaly ${ex.anomaly_score} · review ${ex.review_priority}</span></button>`).join('');
    return `<div class="map-card"><h3><span class="swatch" style="background:${colorFor(slice.id)}"></span> ${esc(slice.name)}</h3><p class="small"><b>Visible/map ads:</b> ${visibleCounts[slice.id]||0} / ${slice.count}<br><b>Avg anomaly/review:</b> ${slice.avg_anomaly_score} / ${slice.avg_review_priority}<br><b>Dominant labels:</b> ${esc(labels)}<br><b>Platforms:</b> ${esc(platforms)}<br><b>Overlaps clusters:</b> ${esc(clusters)}</p><p class="small">${esc(slice.eli5_description)}<br><b>Reviewer should check:</b> ${esc(slice.review_guidance)}</p><div class="neighbor-list">${exemplars}</div></div>`;
  }).join('');
  $('isolationPanel').innerHTML=metricCard+cards;
}
function renderCorpusMap(){
  const map=data.corpus_map||{}, container=$('corpusMapViz'), query=($('mapQuery').value||'').toLowerCase(), color=$('mapColor').value, projection=$('mapProjection').value || map.deep_clusters?.default_projection || 'deep_separation', overlay=$('mapOverlay').value||'both';
  const allPoints=(map.points||[]);
  if(!activeMapClusters.size) activeMapClusters=new Set(deepClusters().map(c=>c.id));
  const points=allPoints.filter(p=>{
    const cluster=deepClusterById(p.deep_cluster);
    const searchable=(p.title+' '+p.platform+' '+(p.labels||[]).join(' ')+' '+deepClusterName(p.deep_cluster)+' '+deepClusterTitle(p.deep_cluster)+' '+(cluster?.eli5_description||'')).toLowerCase();
    return (!query||searchable.includes(query)) && (!p.deep_cluster || activeMapClusters.has(p.deep_cluster)) && (!activeMapQuadrant || quadrantName(p,projection)===activeMapQuadrant);
  });
  const width=900,height=500,pad=34;
  function cx(p){const c=pointCoord(p,projection);return pad+(c.x+1)/2*(width-2*pad)} function cy(p){const c=pointCoord(p,projection);return height-pad-(c.y+1)/2*(height-2*pad)}
  function fill(p){if(color==='score') return `hsl(${120-Math.min(100,p.review_priority)*1.05} 54% 48%)`; if(color==='isolation_score') return `hsl(${220-Math.min(1,Math.max(0,(p.isolation_anomaly_score||0)-0.35))*220} 58% 48%)`; if(color==='split') return colorFor(p.split); if(color==='deep_cluster') return colorFor(p.deep_cluster||'unclustered'); if(color==='isolation_slice') return colorFor(p.isolation_slice||'unsliced'); return colorFor(p.platform)}
  renderClusterLayerControls();
  renderMapLegend(points,color);
  renderMapQuadrants(points,allPoints,projection);
  renderDeepClusterPanel(points);
  renderIsolationPanel(points);
  const projectionInfo=map.deep_clusters?.projection_modes?.[projection] || {};
  const axisLabel=projection==='legacy_svd'?'Legacy SVD diagnostic axis':'Deep neural projection axis';
  const overlaySvg = `${(overlay==='both'||overlay==='kmeans')?clusterHull(points,cx,cy):''}${(overlay==='both'||overlay==='isolation')?isolationSliceBoxes(points,cx,cy):''}`;
  container.innerHTML = `<svg viewBox="0 0 ${width} ${height}" width="100%" height="100%" aria-label="corpus map"><path class="axis" d="M${pad} ${height/2}H${width-pad}M${width/2} ${pad}V${height-pad}"></path>${overlaySvg}<text class="network-label" x="${width/2}" y="${height-8}" text-anchor="middle">${esc(axisLabel)} 1</text><text class="network-label" transform="translate(14 ${height/2}) rotate(-90)" text-anchor="middle">${esc(axisLabel)} 2</text><text class="network-label" x="${pad+4}" y="${height/2-8}">axis 1 −</text><text class="network-label" x="${width-pad-58}" y="${height/2-8}">axis 1 +</text><text class="network-label" x="${width/2+8}" y="${pad+10}">axis 2 +</text><text class="network-label" x="${width/2+8}" y="${height-pad-8}">axis 2 −</text>${points.map(p=>`<circle class="scatter-point" tabindex="0" data-record="${esc(p.record_id)}" cx="${cx(p)}" cy="${cy(p)}" r="${4+Math.min(8,(p.span_count||0)/2)}" fill="${fill(p)}" opacity=".82"></circle>`).join('')}</svg>`;
  $('mapInspector').innerHTML = `<b>How to interpret this view:</b> ${points.length} of ${allPoints.length} representative ads are visible${activeMapQuadrant?` in ${esc(activeMapQuadrant)}`:''}. Current projection: <b>${esc(projectionInfo.name||projection)}</b> · silhouette ${projectionInfo.silhouette ?? 'n/a'}. ${esc(projectionInfo.method||'Projection metadata unavailable.')} Ellipse hulls show neural k-means clusters; dashed rectangles show Deep Isolation Forest cut-slices. Compare both because centroid metrics favor round groups while isolation cuts expose non-circular pockets and anomalies.`;
  renderSelectedMapPoint(points[0],points,projection);
  container.querySelectorAll('.scatter-point').forEach(el=>{
    const p=points.find(x=>x.record_id===el.dataset.record); const show=ev=>{const t=tooltip();t.innerHTML=`<b>${esc(p.title)}</b><br>${esc(p.platform)} · ${esc(p.split)} · review ${p.review_priority}<br>cluster: ${esc(deepClusterTitle(p.deep_cluster))}<br>${esc((p.labels||[]).join(', '))}`;t.style.display='block';t.style.left=(ev.clientX+12)+'px';t.style.top=(ev.clientY+12)+'px'}; const hide=()=>tooltip().style.display='none';
    el.addEventListener('mousemove',show); el.addEventListener('mouseleave',hide); el.addEventListener('focus',ev=>show({clientX:40,clientY:160})); el.addEventListener('blur',hide); el.addEventListener('click',()=>renderSelectedMapPoint(p,points,projection));
  });
}
function renderFacetOverview(){
  const overview=data.facet_overview||{};
  $('facetOverview').innerHTML = (overview.facets||[]).map(f=>{const max=Math.max(...(f.values||[]).map(v=>v.count),1);return `<div class="facet-card"><h3>${esc(f.name)}</h3><p class="small"><b>How to read:</b> bars compare counts inside this feature. Large imbalances can explain model bias or brittle slice metrics.</p>${(f.values||[]).slice(0,8).map(v=>`<div class="rowline"><span>${esc(v.value)}</span><div class="bar"><i style="width:${v.count/max*100}%;background:linear-gradient(90deg,var(--green),var(--blue))"></i></div><b>${v.count}</b></div>`).join('')}</div>`}).join('');
  $('taxonomyMatrix').innerHTML = `<table class="table"><tr><th>Label</th><th>Family</th><th>Type</th><th>Count</th><th>Human check</th></tr>${(data.annotation_taxonomy_matrix||[]).map(r=>`<tr><td>${esc(r.label)}</td><td>${esc(r.family)}</td><td>${esc(r.type)}</td><td>${r.count}</td><td>${esc(r.human_check)}</td></tr>`).join('')}</table>`;
}
function renderAdvancedAnalytics(){
  renderExplainabilityAtlas(); renderTermNetwork(); renderCorpusMap(); renderFacetOverview();
}
function renderExpertPoc(){
  const seed='h_f4fc363a9b8f997059ec332d2ec0effd3960edf30c9f677131a8a9061e43fd81';
  const seedRows=['Direct no-code AI expert review completed for the seed record.', 'Correction: “Brindó apoyo económica” is a malformed but semantically valid economic-support frame.', 'Layer is proof-of-concept AI expert overlay, not human gold.', 'Full-corpus human-equivalent review requires funded reviewer assignments and adjudication.'];
  $('expertPoc').innerHTML = `<div class="scoreline"><span class="chip blue">POC records 1 / ${data.records}</span><span class="chip amber">candidate council records ${data.records}</span><span class="chip red">human gold false</span></div><table class="table"><tr><th>Item</th><th>Status</th></tr>${seedRows.map((row,i)=>`<tr><td>${i+1}</td><td>${esc(row)}</td></tr>`).join('')}<tr><td>Seed</td><td><a href="#${seed}">${seed}</a></td></tr></table>`;
}
function renderObs(){
  const obs=data.observability, metrics=modelReport.metrics?.test||{};
  $('obsTable').innerHTML = `<tr><th>Signal</th><th>Value</th></tr><tr><td>Candidate gold flag</td><td>${obs.gold}</td></tr><tr><td>Challenge records</td><td>${obs.challenge_records}</td></tr><tr><td>Image metadata but no pixels</td><td>${obs.image_metadata_without_pixels ?? obs.missing_image_pixels}</td></tr><tr><td>Test micro/macro F1*</td><td>${metrics.micro_f1 ?? 'n/a'} / ${metrics.macro_f1 ?? 'n/a'}</td></tr><tr><td>Accuracy*</td><td>subset ${metrics.subset_accuracy ?? metrics.accuracy ?? 'n/a'} · label ${metrics.label_accuracy_micro ?? metrics.label_accuracy ?? 'n/a'}</td></tr><tr><td>ROC AUC*</td><td>micro ${metrics.roc_auc_micro ?? 'n/a'} · macro-supported ${metrics.roc_auc_macro_supported ?? metrics.roc_auc_macro ?? 'n/a'} (${metrics.roc_auc_supported_label_count ?? 0} labels)</td></tr><tr><td>Known errors</td><td>${esc(obs.known_errors.join(' · '))}</td></tr>`;
  const labels=Object.entries(data.label_counts).sort((a,b)=>b[1]-a[1]);
  const max=Math.max(...labels.map(x=>x[1]));
  $('labelChart').innerHTML = labels.map(([l,c])=>`<div class="rowline"><span title="${esc(l)}">${esc(l.replaceAll('_',' ').slice(0,24))}</span><div class="bar"><i style="width:${(c/max)*100}%;background:linear-gradient(90deg,var(--green),var(--blue))"></i></div><b>${c}</b></div>`).join('');
}
['rankMode','platformFilter','labelFilter'].forEach(id=>$(id).addEventListener('change',e=>{if(id==='rankMode')mode=e.target.value;selected=0;renderList()}));
$('query').addEventListener('input',()=>{selected=0;renderList()});
$('explainLabel').addEventListener('change',()=>{renderExplainabilityAtlas(); renderDetail(currentRows[selected] || data[mode][0])});
$('networkKind').addEventListener('change',renderTermNetwork);
$('networkTopN').addEventListener('change',renderTermNetwork);
$('networkLabelMode').addEventListener('change',renderTermNetwork);
$('networkReset').addEventListener('click',()=>{$('networkKind').value='';$('networkTopN').value='100';$('networkLabelMode').value='smart';renderTermNetwork()});
$('mapProjection').addEventListener('change',()=>{activeMapQuadrant='';renderCorpusMap()});
$('mapColor').addEventListener('change',renderCorpusMap);
$('mapOverlay').addEventListener('change',renderCorpusMap);
$('mapQuery').addEventListener('input',renderCorpusMap);
$('mapResetLayers').addEventListener('click',resetMapLayers);
async function copyDeepLink(){try{if(navigator.clipboard?.writeText){await navigator.clipboard.writeText(location.href);toast('Deep link copied');return}}catch(e){} const area=document.createElement('textarea');area.value=location.href;area.setAttribute('readonly','');area.style.position='fixed';area.style.left='-9999px';document.body.appendChild(area);area.select();let ok=false;try{ok=document.execCommand('copy')}catch(e){}area.remove();toast(ok?'Deep link copied':'Deep link ready in address bar')}
$('copyLink').addEventListener('click',copyDeepLink);
function applyHash(){
  const id=decodeURIComponent((location.hash||'').slice(1)); if(!id) return false;
  for(const candidateMode of ['top_by_review_priority','top_by_manipulation','top_by_persuasion']){
    if((data[candidateMode]||[]).some(r=>r.record_id===id)){
      mode=candidateMode; $('rankMode').value=mode; $('platformFilter').value=''; $('labelFilter').value=''; $('query').value='';
      currentRows=rows(); const idx=currentRows.findIndex(r=>r.record_id===id);
      if(idx>=0){selected=idx;renderList();$('rankList').children[idx]?.scrollIntoView({block:'nearest'});return true}
    }
  }
  return false;
}
document.addEventListener('keydown',e=>{const typing=['INPUT','TEXTAREA','SELECT'].includes(e.target?.tagName); if(typing && e.key!=='Escape') return; if(e.key==='/' ){e.preventDefault();$('query').focus()} if(e.key==='n'){selected=Math.min(selected+1,currentRows.length-1);renderList()} if(e.key==='p'){selected=Math.max(selected-1,0);renderList()} if(['1','2','3'].includes(e.key)){mode=['top_by_review_priority','top_by_manipulation','top_by_persuasion'][Number(e.key)-1];$('rankMode').value=mode;selected=0;renderList()} if(e.key==='Escape') document.activeElement?.blur?.()});
window.addEventListener('hashchange',()=>{applyHash()});
initFilters(); renderObs(); renderDiagnostics(); renderAdvancedAnalytics(); renderExpertPoc(); if(!applyHash()) renderList();
</script>
</body></html>"""
    metrics = model_report.get("metrics", {}).get("test", {})
    replacements = {
        "__EMBEDDED__": embedded,
        "__RECORDS__": html.escape(str(data["records"])),
        "__SPANS__": html.escape(str(data.get("span_count", 0))),
        "__ZERO_SPAN__": html.escape(str(data.get("zero_span_records", 0))),
        "__MODEL_STATUS__": html.escape(str(model_report.get("status", "unknown"))),
        "__TEST_MICRO__": html.escape(str(metrics.get("micro_f1", "n/a"))),
        "__TEST_MACRO__": html.escape(str(metrics.get("macro_f1", "n/a"))),
        "__TEST_AUC__": html.escape(str(metrics.get("roc_auc_micro", "n/a"))),
        "__TEST_ACC__": html.escape(str(metrics.get("label_accuracy_micro", metrics.get("label_accuracy", "n/a")))),
        "__GOLD__": "false",
    }
    page = template
    for key, value in replacements.items():
        page = page.replace(key, value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding="utf-8")


def ensure_report_assets(output_dir: Path) -> None:
    source_dir = REPORT_ASSET_DIR
    target_dir = output_dir / "assets"
    target_dir.mkdir(parents=True, exist_ok=True)
    for source in source_dir.glob("*.js"):
        target = target_dir / source.name
        if source.resolve() != target.resolve():
            shutil.copyfile(source, target)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--documents", type=Path, default=DEFAULT_DOCS)
    parser.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--json-out", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--html-out", type=Path, default=DEFAULT_HTML)
    parser.add_argument("--model-report", type=Path, default=DEFAULT_MODEL_REPORT)
    args = parser.parse_args()
    print(json.dumps(generate(args.documents, args.annotations, args.model, args.json_out, args.html_out, args.model_report), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
