#!/usr/bin/env python3
"""Train a small supervised manipulation-tagging model from processed records."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, precision_recall_fscore_support
from sklearn.model_selection import train_test_split
from sklearn.multiclass import OneVsRestClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import MultiLabelBinarizer

from tools.detect_manipulation import analyze_text


DEFAULT_MANIFEST = ROOT / "data" / "processed" / "ad_manifest.jsonl"
DEFAULT_MODEL = ROOT / "models" / "manipulation_tfidf_ovr.joblib"
DEFAULT_REPORT = ROOT / "reports" / "phase5_model_report.json"


def load_records(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def weak_labels(text: str) -> list[str]:
    labels = set(analyze_text(text)["tags"])
    lowered = text.lower()
    if any(term in lowered for term in ("discret", "anonim", "privado", "reservad")):
        labels.add("safety_and_privacy_multiplier")
    if any(term in lowered for term in ("estudi", "universidad", "instituto")):
        labels.add("education_and_career_aspiration_multiplier")
    if any(term in lowered for term in ("constante", "semanal", "mensual", "apoyo económico seguro")):
        labels.add("commitment_consistency_foot_in_door")
    if any(term in lowered for term in ("buena presencia", "guapa", "figura", "madura", "joven")):
        labels.add("status_and_respectability_multiplier")
    if any(term in lowered for term in ("familia", "alquiler", "pensión", "gastos")):
        labels.add("family_care_obligation_multiplier")
    labels.add("financial_emergency_multiplier")
    labels.add("reciprocity_obligation")
    return sorted(labels)


def metadata_context_labels(record: dict[str, object], account_counts: Counter[str]) -> list[str]:
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    labels: set[str] = set()
    if metadata.get("is_paid_or_premium_marker") or metadata.get("is_featured_marker"):
        labels.add("paid_or_promoted_visibility_signal")
    if (
        int(metadata.get("followers_count") or 0) > 0
        or int(metadata.get("facebook_reactions_approx") or 0) > 0
        or int(metadata.get("facebook_comments_approx") or 0) > 0
    ):
        labels.add("social_engagement_signal")
    account_hash = str(metadata.get("account_hash") or "")
    if account_hash and account_counts[account_hash] > 1:
        labels.add("repeat_or_high_volume_poster_signal")
    return sorted(labels)


def build_dataset(records: list[dict[str, object]]) -> tuple[list[str], list[list[str]]]:
    account_counts = Counter(
        str(record.get("metadata", {}).get("account_hash"))
        for record in records
        if isinstance(record.get("metadata"), dict) and record.get("metadata", {}).get("account_hash")
    )
    texts = [f"{record.get('title', '')}\n{record.get('body_redacted', '')}" for record in records]
    labels = [
        sorted(set(weak_labels(text)) | set(metadata_context_labels(record, account_counts)))
        for text, record in zip(texts, records)
    ]
    return texts, labels


def train_model(texts: list[str], labels: list[list[str]], model_path: Path) -> dict[str, object]:
    mlb = MultiLabelBinarizer()
    y = mlb.fit_transform(labels)
    if len(texts) < 8:
        raise ValueError("Need at least 8 records for train/test split")

    stratify = None
    x_train, x_test, y_train, y_test = train_test_split(texts, y, test_size=0.30, random_state=42, stratify=stratify)
    model = Pipeline(
        [
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=1, max_features=3000)),
            ("clf", OneVsRestClassifier(LogisticRegression(max_iter=1000, class_weight="balanced"))),
        ]
    )
    model.fit(x_train, y_train)
    y_pred = model.predict(x_test)
    precision, recall, macro_f1, _ = precision_recall_fscore_support(y_test, y_pred, average="macro", zero_division=0)
    micro_f1 = f1_score(y_test, y_pred, average="micro", zero_division=0)
    subset_accuracy = accuracy_score(y_test, y_pred)

    model_path = model_path if model_path.is_absolute() else (ROOT / model_path)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "labels": list(mlb.classes_)}, model_path)
    label_counts = Counter(label for row in labels for label in row)
    try:
        model_path_str = str(model_path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        model_path_str = str(model_path)
    return {
        "model_path": model_path_str,
        "records": len(texts),
        "train_records": len(x_train),
        "test_records": len(x_test),
        "labels": list(mlb.classes_),
        "label_counts": dict(label_counts),
        "macro_precision": round(float(precision), 4),
        "macro_recall": round(float(recall), 4),
        "macro_f1": round(float(macro_f1), 4),
        "micro_f1": round(float(micro_f1), 4),
        "accuracy": round(float(subset_accuracy), 4),
        "calibration_error": "not_estimated_small_weak_label_dataset"
    }


def dataset_summary(records: list[dict[str, object]]) -> dict[str, object]:
    platform_counts = Counter()
    quality_signal_counts = Counter()
    for record in records:
        metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
        platform_counts[str(metadata.get("platform_family") or record.get("source_platform") or "unknown")] += 1
        for key in (
            "is_paid_or_premium_marker",
            "is_featured_marker",
            "followers_count",
            "image_count",
            "facebook_reactions_approx",
            "facebook_comments_approx",
            "facebook_group_present",
        ):
            if metadata.get(key):
                quality_signal_counts[key] += 1
    return {
        "platform_counts": dict(platform_counts),
        "quality_signal_counts": dict(quality_signal_counts),
    }


def write_report(metrics: dict[str, object], report_path: Path, summary: dict[str, object]) -> None:
    report = {
        "phase": 5,
        "title": "Manipulation Detection Model Report",
        "status": "trained_small_supervised_baseline",
        "training_data": {
            "available_records": metrics["records"],
            "source": "data/processed/ad_manifest.jsonl",
            "platform_counts": summary["platform_counts"],
            "quality_signal_counts": summary["quality_signal_counts"],
            "labeling": "weak supervision from Phase 1 taxonomy rules, Phase 2 multiplier cues, and aggregate non-PII context metadata",
            "limitation": "Dataset is rebuilt from local raw public archives and remains weak-labeled; metrics are exploratory and not production-grade."
        },
        "label_schema": {
            "labels": metrics["labels"],
            "output_fields": ["score", "tags", "findings.evidence", "findings.rationale"]
        },
        "model_approaches": [
            {
                "name": "rule_based_baseline",
                "artifact": "tools/detect_manipulation.py",
                "status": "implemented"
            },
            {
                "name": "tfidf_logistic_regression_one_vs_rest",
                "artifact": metrics["model_path"],
                "status": "trained"
            },
            {
                "name": "deep_learning_transformer",
                "status": "deferred",
                "blocked_by": "requires human-adjudicated labels before meaningful fine-tuning"
            }
        ],
        "evaluation_metrics": {
            "macro_f1": metrics["macro_f1"],
            "micro_f1": metrics["micro_f1"],
            "macro_precision": metrics["macro_precision"],
            "macro_recall": metrics["macro_recall"],
            "accuracy": metrics["accuracy"],
            "calibration_error": metrics["calibration_error"],
            "train_records": metrics["train_records"],
            "test_records": metrics["test_records"],
            "label_counts": metrics["label_counts"]
        },
        "robustness_tests": [
            {"name": "accent_and_case_variation", "status": "covered_by_rule_tests"},
            {"name": "low_signal_false_positive_check", "status": "covered_by_unit_tests"},
            {"name": "holdout_evaluation", "status": "implemented"},
            {"name": "obfuscated_contact_redaction", "status": "implemented"}
        ],
        "red_team_cases": [
            {"case": "Legitimate public aid announcement", "expected_behavior": "low score unless conditionality or private contact cues appear"},
            {"case": "Financial offer plus private channel and discretion", "expected_behavior": "high risk tags for financial, migration, and privacy multipliers"},
            {"case": "Benign economic news article", "expected_behavior": "no tags or low score"}
        ],
        "retrospective": {
            "best_approaches": [
                f"TF-IDF one-vs-rest logistic regression is the best trained model currently possible with {metrics['records']} weakly labeled records.",
                "Rule-based evidence spans remain more explainable than the trained classifier while labels are weakly supervised.",
                "Aggregate visibility and engagement metadata provide useful context labels without storing profile-level PII."
            ],
            "limitations": [
                "Labels are weakly supervised, not human annotated.",
                "No deep learning model was fine-tuned because human-adjudicated labels are not yet available.",
                "Metrics are exploratory and should not be treated as production performance."
            ],
            "failure_modes": [
                "May overfit repeated Locanto phrasing.",
                "May miss slang, image-only ads, and heavily obfuscated contact text.",
                "May confuse legitimate aid discussions with exploitative offers."
            ]
        }
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    records = load_records(args.manifest)
    texts, labels = build_dataset(records)
    metrics = train_model(texts, labels, args.model)
    write_report(metrics, args.report, dataset_summary(records))
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
