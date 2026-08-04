#!/usr/bin/env python3
"""Train a candidate multilabel model from resolved council annotations."""

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
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    f1_score,
    hamming_loss,
    precision_recall_curve,
    precision_recall_fscore_support,
    roc_curve,
    roc_auc_score,
)
from sklearn.multiclass import OneVsRestClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import MultiLabelBinarizer

DEFAULT_DOCS = ROOT / "data/annotation/documents.jsonl"
DEFAULT_ANNOTATIONS = ROOT / "data/annotation/council_resolved_annotations.jsonl"
DEFAULT_MODEL = ROOT / "models/manipulation_council_tfidf_ovr.joblib"
DEFAULT_REPORT = ROOT / "reports/council_candidate_model_report.json"


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def exact_match(y_true, y_pred) -> float:
    return float((y_true == y_pred).all(axis=1).mean())


def evaluate(model, texts: list[str], y, labels: list[str]) -> dict:
    if not texts:
        return {"records": 0}
    y_pred = model.predict(texts)
    hamming = hamming_loss(y, y_pred)
    y_score = None
    try:
        y_score = model.predict_proba(texts)
        avg_precision = average_precision_score(y, y_score, average="micro")
    except Exception:
        avg_precision = 0.0
    auc_micro = None
    auc_macro = None
    auc_supported_label_count = 0
    roc_curve_micro = []
    precision_recall_curve_micro = []
    per_label_auc: dict[str, float | None] = {}
    if y_score is not None:
        try:
            auc_micro = float(roc_auc_score(y, y_score, average="micro"))
            fpr, tpr, _ = roc_curve(y.ravel(), y_score.ravel())
            step = max(1, len(fpr) // 80)
            roc_curve_micro = [
                [round(float(x), 4), round(float(y_value), 4)]
                for x, y_value in list(zip(fpr, tpr))[::step]
            ]
            last_roc = [round(float(fpr[-1]), 4), round(float(tpr[-1]), 4)]
            if roc_curve_micro and roc_curve_micro[-1] != last_roc:
                roc_curve_micro.append(last_roc)
        except ValueError:
            auc_micro = None
        try:
            pr_precision, pr_recall, _ = precision_recall_curve(y.ravel(), y_score.ravel())
            step = max(1, len(pr_precision) // 80)
            precision_recall_curve_micro = [
                [round(float(recall), 4), round(float(precision_value), 4)]
                for precision_value, recall in list(zip(pr_precision, pr_recall))[::step]
            ]
            last_pr = [round(float(pr_recall[-1]), 4), round(float(pr_precision[-1]), 4)]
            if precision_recall_curve_micro and precision_recall_curve_micro[-1] != last_pr:
                precision_recall_curve_micro.append(last_pr)
        except ValueError:
            precision_recall_curve_micro = []
        auc_values = []
        for index, label in enumerate(labels):
            column = y[:, index]
            if len(set(column.tolist())) < 2:
                per_label_auc[label] = None
                continue
            value = float(roc_auc_score(column, y_score[:, index]))
            per_label_auc[label] = round(value, 4)
            auc_values.append(value)
        if auc_values:
            auc_supported_label_count = len(auc_values)
            auc_macro = sum(auc_values) / len(auc_values)
    precision, recall, macro_f1, _ = precision_recall_fscore_support(
        y, y_pred, average="macro", zero_division=0
    )
    per_label_precision, per_label_recall, per_label_f1, support = precision_recall_fscore_support(
        y, y_pred, average=None, zero_division=0
    )
    return {
        "records": len(texts),
        "micro_f1": round(float(f1_score(y, y_pred, average="micro", zero_division=0)), 4),
        "macro_f1": round(float(macro_f1), 4),
        "macro_precision": round(float(precision), 4),
        "macro_recall": round(float(recall), 4),
        "average_precision_micro": round(float(avg_precision), 4),
        "accuracy": round(float(accuracy_score(y, y_pred)), 4),
        "subset_accuracy": round(float(accuracy_score(y, y_pred)), 4),
        "label_accuracy": round(float(1.0 - hamming), 4),
        "label_accuracy_micro": round(float(1.0 - hamming), 4),
        "roc_auc_micro": round(auc_micro, 4) if auc_micro is not None else None,
        "roc_auc_macro": round(auc_macro, 4) if auc_macro is not None else None,
        "roc_auc_macro_supported": round(auc_macro, 4) if auc_macro is not None else None,
        "roc_auc_supported_label_count": auc_supported_label_count,
        "roc_curve_micro": roc_curve_micro,
        "precision_recall_curve_micro": precision_recall_curve_micro,
        "hamming_loss": round(float(hamming), 4),
        "exact_match": round(exact_match(y, y_pred), 4),
        "per_label": {
            label: {
                "precision": round(float(per_label_precision[index]), 4),
                "recall": round(float(per_label_recall[index]), 4),
                "f1": round(float(per_label_f1[index]), 4),
                "accuracy": round(float(accuracy_score(y[:, index], y_pred[:, index])), 4),
                "roc_auc": per_label_auc.get(label),
                "support": int(support[index]),
            }
            for index, label in enumerate(labels)
        },
    }


def train(docs_path: Path, annotations_path: Path, model_path: Path, report_path: Path) -> dict:
    docs = {row["record_id"]: row for row in load_jsonl(docs_path)}
    annotations = {row["record_id"]: row for row in load_jsonl(annotations_path)}
    records = []
    for record_id, doc in docs.items():
        ann = annotations.get(record_id, {"spans": []})
        records.append(
            {
                "record_id": record_id,
                "text": doc["text"],
                "split": doc["split"],
                "labels": sorted({span["label"] for span in ann.get("spans", [])}),
                "platform": doc["platform"],
            }
        )
    labels = sorted({label for row in records for label in row["labels"]})
    mlb = MultiLabelBinarizer(classes=labels)
    mlb.fit([labels])
    train_rows = [row for row in records if row["split"] == "train"]
    validation_rows = [row for row in records if row["split"] == "validation"]
    test_rows = [row for row in records if row["split"] == "test"]
    challenge_rows = [row for row in records if row["split"] == "challenge"]
    x_train = [row["text"] for row in train_rows]
    y_train = mlb.transform([row["labels"] for row in train_rows])
    model = Pipeline(
        [
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_features=20000, sublinear_tf=True)),
            ("clf", OneVsRestClassifier(LogisticRegression(max_iter=1000, class_weight="balanced"))),
        ]
    )
    model.fit(x_train, y_train)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": model,
            "labels": labels,
            "source": str(annotations_path),
            "label_status": "candidate_subagent_council_consensus_not_human_gold",
        },
        model_path,
    )
    label_counts = Counter(label for row in records for label in row["labels"])
    report = {
        "status": "candidate_model_trained_from_council_consensus",
        "gold": False,
        "records": len(records),
        "model_path": str(model_path),
        "annotation_source": str(annotations_path),
        "labels": labels,
        "label_counts": dict(sorted(label_counts.items())),
        "split_counts": dict(Counter(row["split"] for row in records)),
        "platform_counts": dict(Counter(row["platform"] for row in records)),
        "metrics": {
            "validation": evaluate(
                model,
                [row["text"] for row in validation_rows],
                mlb.transform([row["labels"] for row in validation_rows]),
                labels,
            ),
            "test": evaluate(
                model,
                [row["text"] for row in test_rows],
                mlb.transform([row["labels"] for row in test_rows]),
                labels,
            ),
            "challenge": evaluate(
                model,
                [row["text"] for row in challenge_rows],
                mlb.transform([row["labels"] for row in challenge_rows]),
                labels,
            ),
        },
        "limitations": [
            "Training labels are resolved council suggestions, not two-human adjudicated gold.",
            "Metrics evaluate agreement with the council labeling function and should not be presented as independently validated human performance.",
            "Image pixels were unavailable; image-only persuasion remains unmodeled.",
        ],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--documents", type=Path, default=DEFAULT_DOCS)
    parser.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    print(json.dumps(train(args.documents, args.annotations, args.model, args.report), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
