#!/usr/bin/env python3
"""Analyze model performance by metadata slices and latent text clusters."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import joblib
import numpy as np
from sklearn.cluster import MiniBatchKMeans
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import accuracy_score, f1_score, hamming_loss, roc_auc_score
from sklearn.preprocessing import MultiLabelBinarizer

DEFAULT_DOCS = ROOT / "data/annotation/documents.jsonl"
DEFAULT_ANNOTATIONS = ROOT / "data/annotation/council_resolved_annotations.jsonl"
DEFAULT_MODEL = ROOT / "models/manipulation_council_tfidf_ovr.joblib"
DEFAULT_OUT = ROOT / "reports/segment_model_analysis.json"

CITY_PATTERNS = {
    "lima": r"\blima\b",
    "arequipa": r"\barequipa\b",
    "trujillo": r"\btrujillo\b",
    "chiclayo": r"\bchiclayo\b",
    "piura": r"\bpiura\b",
    "cusco": r"\b(?:cusco|cuzco)\b",
    "huancayo": r"\bhuancayo\b",
    "tacna": r"\btacna\b",
    "iquitos": r"\biquitos\b",
    "chimbote": r"\bchimbote\b",
    "ica": r"\bica\b",
    "puno": r"\bpuno\b",
    "callao": r"\bcallao\b",
}


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


POSTING_DATE_KEYS = (
    "posted_at",
    "posting_date",
    "published_at",
    "ad_posted_at",
    "listing_posted_at",
    "listing_date",
)


def posting_date_range(context: dict) -> str:
    """Return a coarse posting date bucket only when explicit posting metadata exists.

    Collection/acquisition timestamps are intentionally ignored because they
    describe crawler behavior rather than ad-poster behavior.
    """
    for key in POSTING_DATE_KEYS:
        value = context.get(key)
        if not value:
            continue
        value_str = str(value)
        month = re.search(r"\b(20\d{2})[-/](0?[1-9]|1[0-2])\b", value_str)
        if month:
            return f"posted_{month.group(1)}_{int(month.group(2)):02d}"
        year = re.search(r"\b(20\d{2})\b", value_str)
        if year:
            return f"posted_{year.group(1)}"
    return "posting_date_unavailable"


def cue_count(text: str, patterns: list[str]) -> int:
    folded = text.casefold()
    return sum(len(re.findall(pattern, folded)) for pattern in patterns)


def density_bin(count: int, length: int, name: str) -> str:
    if count == 0:
        return f"{name}_none"
    per_100 = count / max(length, 1) * 100
    if per_100 < 0.8:
        return f"{name}_low"
    if per_100 < 1.8:
        return f"{name}_medium"
    return f"{name}_high"


def repeated_phrase_bin(text: str) -> str:
    tokens = re.findall(r"[a-záéíóúñü0-9]+", text.casefold())
    if len(tokens) < 6:
        return "repetition_none"
    trigrams = Counter(zip(tokens, tokens[1:], tokens[2:]))
    repeated = sum(1 for count in trigrams.values() if count > 1)
    if repeated == 0:
        return "repetition_none"
    if repeated <= 2:
        return "repetition_low"
    return "repetition_high"


def orthography_noise_bin(text: str) -> str:
    folded = text.casefold()
    typo_patterns = [
        r"\beconomomico\w*\b",
        r"\beconomic[ao]\b",
        r"\bapoyo\s+econ[oó]mic[ao]\b",
        r"\bayud[ao]\s+econ[oó]mic[ao]\b",
        r"\bwhatsap+\b",
        r"\bwsp\b",
        r"\bwasap\b",
    ]
    count = cue_count(folded, typo_patterns)
    accentless = len(re.findall(r"\b(?:economico|economica|senoritas|discrecion|telefono|numero)\b", folded))
    total = count + accentless
    if total == 0:
        return "orthography_noise_none"
    if total <= 2:
        return "orthography_noise_low"
    return "orthography_noise_high"


def city_for(text: str) -> str:
    folded = text.casefold()
    for city, pattern in CITY_PATTERNS.items():
        if re.search(pattern, folded):
            return city
    return "unknown"


def length_bin(length: int) -> str:
    if length < 180:
        return "short_<180"
    if length < 360:
        return "medium_180_359"
    if length < 700:
        return "long_360_699"
    return "very_long_700_plus"


def count_bin(count: int, name: str) -> str:
    if count == 0:
        return f"{name}_0"
    if count <= 3:
        return f"{name}_1_3"
    if count <= 7:
        return f"{name}_4_7"
    return f"{name}_8_plus"


def quality_bin(value) -> str:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "quality_unknown"
    if v < 0.4:
        return "quality_low"
    if v < 0.65:
        return "quality_mid"
    return "quality_high"


def email_provider_family(text: str, context: dict) -> str:
    # The pipeline intentionally redacts direct emails. We report provider only
    # when safely visible in already-redacted text; otherwise privacy-safe status.
    if "[REDACTED_EMAIL]" in text:
        return "email_redacted"
    providers = re.findall(r"@([a-z0-9.-]+\.[a-z]{2,})", text.casefold())
    if not providers:
        return "not_available"
    provider = providers[0]
    if provider in {"gmail.com", "hotmail.com", "outlook.com", "yahoo.com", "icloud.com"}:
        return provider
    return "other_provider_domain"


def labels_for(row: dict) -> list[str]:
    return sorted({span["label"] for span in row.get("spans", [])})


def metric_block(y_true, y_pred, y_score=None) -> dict:
    if len(y_true) == 0:
        return {}
    out = {
        "records": int(y_true.shape[0]),
        "micro_f1": round(float(f1_score(y_true, y_pred, average="micro", zero_division=0)), 4),
        "macro_f1": round(float(f1_score(y_true, y_pred, average="macro", zero_division=0)), 4),
        "subset_accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "label_accuracy": round(float(1 - hamming_loss(y_true, y_pred)), 4),
    }
    if y_score is not None:
        try:
            out["roc_auc_micro"] = round(float(roc_auc_score(y_true, y_score, average="micro")), 4)
        except ValueError:
            out["roc_auc_micro"] = None
    return out


def tune_thresholds(y_true, y_score) -> list[float]:
    thresholds = []
    grid = np.linspace(0.15, 0.85, 29)
    for index in range(y_true.shape[1]):
        best_threshold, best_score = 0.5, -1.0
        column = y_true[:, index]
        if column.sum() == 0:
            thresholds.append(0.5)
            continue
        for threshold in grid:
            pred = (y_score[:, index] >= threshold).astype(int)
            score = f1_score(column, pred, zero_division=0)
            if score > best_score:
                best_threshold, best_score = float(threshold), float(score)
        thresholds.append(round(best_threshold, 3))
    return thresholds


def top_cluster_terms(vectorizer: TfidfVectorizer, model: MiniBatchKMeans, top_n: int = 8) -> dict[str, list[str]]:
    terms = np.array(vectorizer.get_feature_names_out())
    result = {}
    for cluster_id, center in enumerate(model.cluster_centers_):
        top = center.argsort()[::-1][:top_n]
        result[str(cluster_id)] = terms[top].tolist()
    return result


def analyze(docs_path: Path, annotations_path: Path, model_path: Path, output: Path, min_slice_records: int = 20) -> dict:
    docs = {row["record_id"]: row for row in load_jsonl(docs_path)}
    anns = {row["record_id"]: row for row in load_jsonl(annotations_path)}
    artifact = joblib.load(model_path)
    clf = artifact["model"]
    labels = artifact["labels"]
    mlb = MultiLabelBinarizer(classes=labels)
    mlb.fit([labels])
    records = []
    for record_id, doc in docs.items():
        text = doc["text"]
        context = doc.get("context", {})
        ann = anns.get(record_id, {"spans": []})
        title, _, body = text.partition("\n")
        span_count = len(ann.get("spans", []))
        record_city = city_for(text)
        record_length = length_bin(len(text))
        vulnerability_cues = cue_count(
            text,
            [
                r"\bestudiant\w*\b",
                r"\bmadre[s]?\s+solter\w*\b",
                r"\bnecesidad\b",
                r"\bapoyo\s+econ[oó]mic\w*\b",
                r"\bayuda\s+econ[oó]mic\w*\b",
                r"\bproblemas?\s+econ[oó]mic\w*\b",
                r"\bfamilia\b",
            ],
        )
        conditional_cues = cue_count(
            text,
            [
                r"\ba\s+cambio\b",
                r"\bsi\s+eres\b",
                r"\bsi\s+te\b",
                r"\bcon\s+beneficios\b",
                r"\bpor\s+compa[ñn][ií]a\b",
                r"\bcondici[oó]n\b",
                r"\bdiscret[oa]\b",
            ],
        )
        contact_cues = cue_count(
            text,
            [
                r"\bwhats?app\b",
                r"\bwsp\b",
                r"\bwasap\b",
                r"\btelegram\b",
                r"\binbox\b",
                r"\bprivado\b",
                r"\bmensaje\b",
                r"\b\[redacted_(?:phone|email|url|contact)\]\b",
            ],
        )
        records.append(
            {
                "record_id": record_id,
                "text": text,
                "title": title,
                "body": body,
                "split": doc["split"],
                "labels": labels_for(ann),
                "features": {
                    "platform": doc["platform"],
                    "source_platform": context.get("source_platform", doc["platform"]),
                    "city": record_city,
                    "length_bin": record_length,
                    "title_length_bin": length_bin(len(title)),
                    "body_length_bin": length_bin(len(body)),
                    "span_count_bin": count_bin(span_count, "spans"),
                    "label_count_bin": count_bin(len(labels_for(ann)), "labels"),
                    "posting_date_range": posting_date_range(context),
                    "raw_size_bucket": context.get("raw_size_bucket", "unknown"),
                    "quality_bin": quality_bin(context.get("quality_score")),
                    "paid_or_featured": "paid_or_featured" if context.get("is_paid_or_premium_marker") or context.get("is_featured_marker") else "not_paid_or_featured",
                    "image_available": "image_available" if context.get("image_available") else "no_image",
                    "email_provider_family": email_provider_family(text, context),
                    "has_redacted_contact": "has_redacted_contact" if "[REDACTED_" in text else "no_redacted_contact",
                    "vulnerability_cue_density": density_bin(vulnerability_cues, len(text), "vulnerability"),
                    "conditionality_cue_density": density_bin(conditional_cues, len(text), "conditionality"),
                    "contact_migration_density": density_bin(contact_cues, len(text), "contact_migration"),
                    "orthography_noise": orthography_noise_bin(text),
                    "repeated_phrase_bin": repeated_phrase_bin(text),
                    "city_length_interaction": f"{record_city}__{record_length}",
                },
            }
        )
    texts = [row["text"] for row in records]
    cluster_vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=3, max_features=6000, sublinear_tf=True)
    x_cluster = cluster_vectorizer.fit_transform(texts)
    cluster_count = 10
    cluster_model = MiniBatchKMeans(n_clusters=cluster_count, random_state=17, batch_size=512, n_init=10)
    clusters = cluster_model.fit_predict(x_cluster)
    cluster_terms = top_cluster_terms(cluster_vectorizer, cluster_model)
    for row, cluster_id in zip(records, clusters):
        row["features"]["tfidf_cluster"] = f"cluster_{int(cluster_id)}"
    validation = [row for row in records if row["split"] == "validation"]
    test = [row for row in records if row["split"] == "test"]
    y_val = mlb.transform([row["labels"] for row in validation])
    val_score = clf.predict_proba([row["text"] for row in validation])
    tuned_thresholds = tune_thresholds(y_val, val_score)
    y_test = mlb.transform([row["labels"] for row in test])
    test_score = clf.predict_proba([row["text"] for row in test])
    default_pred = (test_score >= 0.5).astype(int)
    tuned_pred = (test_score >= np.array(tuned_thresholds)).astype(int)
    overall_default = metric_block(y_test, default_pred, test_score)
    overall_tuned = metric_block(y_test, tuned_pred, test_score)
    dimensions = [
        "platform",
        "source_platform",
        "city",
        "length_bin",
        "body_length_bin",
        "span_count_bin",
        "label_count_bin",
        "raw_size_bucket",
        "quality_bin",
        "paid_or_featured",
        "image_available",
        "email_provider_family",
        "has_redacted_contact",
        "vulnerability_cue_density",
        "conditionality_cue_density",
        "contact_migration_density",
        "orthography_noise",
        "repeated_phrase_bin",
        "city_length_interaction",
        "tfidf_cluster",
    ]
    if any(row["features"]["posting_date_range"] != "posting_date_unavailable" for row in records):
        dimensions.append("posting_date_range")
    slices = []
    for dimension in dimensions:
        values = defaultdict(list)
        for index, row in enumerate(test):
            values[row["features"].get(dimension, "unknown")].append(index)
        for value, indexes in values.items():
            if len(indexes) < min_slice_records:
                continue
            idx = np.array(indexes)
            default_metrics = metric_block(y_test[idx], default_pred[idx], test_score[idx])
            tuned_metrics = metric_block(y_test[idx], tuned_pred[idx], test_score[idx])
            slices.append(
                {
                    "dimension": dimension,
                    "value": value,
                    "records": len(indexes),
                    "default": default_metrics,
                    "threshold_tuned": tuned_metrics,
                    "delta_micro_f1": round(tuned_metrics.get("micro_f1", 0) - default_metrics.get("micro_f1", 0), 4),
                    "top_terms": cluster_terms.get(value.replace("cluster_", ""), []) if dimension == "tfidf_cluster" else [],
                }
            )
    baseline = overall_default.get("micro_f1", 0)
    underperforming = sorted(
        [
            row
            for row in slices
            if row["records"] >= min_slice_records
            and row["default"].get("micro_f1", 1) <= baseline - 0.04
        ],
        key=lambda row: (row["default"].get("micro_f1", 1), -row["records"]),
    )[:20]
    outperforming = sorted(
        [
            row
            for row in slices
            if row["records"] >= min_slice_records
            and row["default"].get("micro_f1", 0) >= baseline + 0.03
        ],
        key=lambda row: (-row["default"].get("micro_f1", 0), -row["records"]),
    )[:20]
    cluster_summary = [
        {
            "cluster": f"cluster_{cluster_id}",
            "records": sum(1 for row in records if row["features"]["tfidf_cluster"] == f"cluster_{cluster_id}"),
            "top_terms": cluster_terms[str(cluster_id)],
        }
        for cluster_id in range(cluster_count)
    ]
    report = {
        "status": "segment_and_cluster_error_analysis",
        "gold": False,
        "records": len(records),
        "test_records": len(test),
        "method_notes": [
            "Predefined slices use privacy-safe metadata and derived text features.",
            "Collection time-of-day is intentionally excluded because it reflects crawler acquisition timing, not ad-poster behavior.",
            "Posting date range is used only when explicit posting metadata exists; the current processed corpus does not expose it.",
            "Engineered persuasion/manipulation features include vulnerability-cue density, conditionality density, contact-migration pressure, orthography/typo noise, repeated phrases, and city-length interactions.",
            "Email provider is reported only as redacted/unavailable/provider-family; no raw email addresses are exported.",
            "Latent clusters use CPU-safe TF-IDF plus MiniBatchKMeans, a fallback to transformer/UMAP/HDBSCAN topic clustering.",
            "Threshold-tuned results use validation-selected per-label thresholds and are a post-hoc improvement layer, not human-gold validation.",
        ],
        "unavailable_features": {
            "posting_date_range": "No explicit posting-date field is present in processed document context; collected_at was deliberately not used."
        },
        "overall_default": overall_default,
        "overall_threshold_tuned": overall_tuned,
        "thresholds": {label: tuned_thresholds[index] for index, label in enumerate(labels)},
        "slices": sorted(slices, key=lambda row: (row["dimension"], row["value"])),
        "underperforming_slices": underperforming,
        "outperforming_slices": outperforming,
        "clusters": cluster_summary,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--documents", type=Path, default=DEFAULT_DOCS)
    parser.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--min-slice-records", type=int, default=20)
    args = parser.parse_args()
    report = analyze(args.documents, args.annotations, args.model, args.out, args.min_slice_records)
    print(json.dumps({"out": str(args.out), "underperforming": report["underperforming_slices"][:5], "overall": report["overall_default"], "tuned": report["overall_threshold_tuned"]}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
