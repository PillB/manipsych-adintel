#!/usr/bin/env python3
"""Rank processed ads by manipulation/persuasion risk with explanations."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import joblib

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.detect_manipulation import analyze_text
from tools.redact_pii import redact_text
from tools.render_html_report import render_html_report


DEFAULT_MANIFEST = ROOT / "data" / "processed" / "ad_manifest.jsonl"
DEFAULT_MODEL = ROOT / "models" / "manipulation_tfidf_ovr.joblib"
DEFAULT_JSON = ROOT / "reports" / "ad_manipulation_ranking.json"
DEFAULT_HTML = ROOT / "reports" / "ad_manipulation_report.html"
DEFAULT_MODEL_REPORT = ROOT / "reports" / "phase5_model_report.json"
DEFAULT_REBUILD_SUMMARY = ROOT / "reports" / "raw_rebuild_summary.json"

CONTEXT_LABELS = {
    "paid_or_promoted_visibility_signal",
    "repeat_or_high_volume_poster_signal",
    "social_engagement_signal",
}

UBIQUITOUS_WEAK_LABELS = {
    "financial_emergency_multiplier",
    "reciprocity_obligation",
}


def load_records(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def compact_excerpt(text: str, limit: int = 360) -> str:
    text = re.sub(r"\s+", " ", redact_text(text)).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def top_probabilities(labels: list[str], probabilities: list[float], exclude: set[str], limit: int = 6) -> list[dict[str, object]]:
    pairs = [
        {"label": label, "probability": round(float(probability), 4)}
        for label, probability in zip(labels, probabilities)
        if label not in exclude
    ]
    return sorted(pairs, key=lambda item: item["probability"], reverse=True)[:limit]


def score_record(record: dict[str, object], model, labels: list[str]) -> dict[str, object]:
    text = f"{record.get('title', '')}\n{record.get('body_redacted', '')}"
    rule_result = analyze_text(text)
    probabilities = list(model.predict_proba([text])[0])
    prob_map = dict(zip(labels, probabilities))
    technique_probs = [
        probability
        for label, probability in prob_map.items()
        if label not in CONTEXT_LABELS and label not in UBIQUITOUS_WEAK_LABELS
    ]
    top_technique_avg = sum(sorted(technique_probs, reverse=True)[:4]) / max(1, min(4, len(technique_probs)))
    context_probs = [prob_map.get(label, 0.0) for label in CONTEXT_LABELS]
    context_probability = max(context_probs) if context_probs else 0.0
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    quality_score = float(metadata.get("quality_score") or 0.5)

    # Discriminative score: rule evidence + non-ubiquitous model labels + visibility/context.
    overall = min(
        1.0,
        0.45 * float(rule_result["score"])
        + 0.35 * float(top_technique_avg)
        + 0.12 * float(context_probability)
        + 0.08 * quality_score,
    )
    evidence_tags = [finding["tag"] for finding in rule_result["findings"]]
    explanation = []
    if evidence_tags:
        explanation.append("Rule evidence: " + ", ".join(evidence_tags))
    model_top = top_probabilities(labels, probabilities, CONTEXT_LABELS | UBIQUITOUS_WEAK_LABELS, limit=4)
    if model_top:
        explanation.append("Top discriminative model labels: " + ", ".join(item["label"] for item in model_top[:3]))
    context_top = top_probabilities(labels, probabilities, set(labels) - CONTEXT_LABELS, limit=3)
    if context_top:
        explanation.append("Context signals: " + ", ".join(item["label"] for item in context_top if item["probability"] >= 0.5))

    return {
        "record_id": record.get("record_id"),
        "source_platform": record.get("source_platform"),
        "raw_archive_ref": record.get("raw_archive_ref"),
        "title": redact_text(str(record.get("title", ""))),
        "excerpt": compact_excerpt(str(record.get("body_redacted", ""))),
        "overall_score": round(overall, 4),
        "rule_score": rule_result["score"],
        "quality_score": quality_score,
        "rule_findings": rule_result["findings"],
        "top_model_labels": model_top,
        "context_model_labels": context_top,
        "metadata_signals": {
            key: metadata.get(key)
            for key in (
                "platform_family",
                "is_paid_or_premium_marker",
                "is_featured_marker",
                "followers_count",
                "image_count",
                "facebook_reactions_approx",
                "facebook_comments_approx",
                "facebook_group_present",
                "quality_score",
            )
            if metadata.get(key) not in (None, False, "", 0)
        },
        "explanation": explanation,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--json-out", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--html-out", type=Path, default=DEFAULT_HTML)
    parser.add_argument("--model-report", type=Path, default=DEFAULT_MODEL_REPORT)
    parser.add_argument("--rebuild-summary", type=Path, default=DEFAULT_REBUILD_SUMMARY)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    records = load_records(args.manifest)
    artifact = joblib.load(args.model)
    model = artifact["model"]
    labels = list(artifact["labels"])
    ranked = sorted(
        (score_record(record, model, labels) for record in records),
        key=lambda row: row["overall_score"],
        reverse=True,
    )
    output = {
        "total_records_scored": len(records),
        "ranking_method": {
            "overall_score": "0.45*rule_score + 0.35*top_discriminative_model_probability_average + 0.12*context_probability + 0.08*quality_score",
            "excluded_from_discriminative_average": sorted(CONTEXT_LABELS | UBIQUITOUS_WEAK_LABELS),
            "note": "Exploratory weak-supervised ranking; not production scoring.",
        },
        "top_records": ranked[: args.limit],
    }
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    render_html_report(
        output,
        json.loads(args.model_report.read_text(encoding="utf-8")),
        json.loads(args.rebuild_summary.read_text(encoding="utf-8")),
        args.html_out,
    )
    print(json.dumps({"records_scored": len(records), "json_out": str(args.json_out), "html_out": str(args.html_out)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
