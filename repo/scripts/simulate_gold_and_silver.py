#!/usr/bin/env python3
"""Item 5: Simulate gold annotation + independent silver annotation round.

The existing 5,717 council annotations are weak-supervised (gold=false). This
script:

1. SIMULATED GOLD: Take the council annotations and apply a noise model that
   mimics how a human adjudicator would resolve them:
   - High-agreement spans (3/3 council) → gold with 95% probability
   - Medium-agreement spans (2/3) → gold with 70% probability
   - Low-agreement spans (1/3) → gold with 30% probability
   - Add 5% random flips to simulate human-independent judgment

2. SILVER ANNOTATION (independent): Run a DIFFERENT rule-based annotator with
   different signal patterns and thresholds. This is functionally independent
   because it uses a different implementation, not just the same code with
   different parameters.

3. COMPARE: Compute inter-annotator agreement (Cohen's kappa, F1) between
   simulated-gold and silver.

This gives us a realistic estimate of annotation reliability WITHOUT requiring
actual human annotators (which would require funding and time we don't have).
"""

from __future__ import annotations

import json
import re
import random
import sys
from pathlib import Path
from collections import defaultdict

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

COUNCIL = ROOT / "data" / "annotation" / "council_resolved_annotations.jsonl"
MANIFEST = ROOT / "data" / "processed" / "ad_manifest.jsonl"
OUT_GOLD = ROOT / "data" / "annotation" / "simulated_gold_annotations.jsonl"
OUT_SILVER = ROOT / "data" / "annotation" / "silver_annotations.jsonl"
OUT_REPORT = ROOT / "reports" / "adintel" / "annotation_agreement.json"


# Independent silver annotator: DIFFERENT signal patterns than the council
# but MAPPED to the same council taxonomy labels so agreement is computable.
# The independence is in the regex patterns and thresholds, not the label space.
SILVER_SIGNALS = {
    "scarcity_or_urgency": re.compile(r"(?i)\b(ya|ahora|mismo|inmediato|rapido|rápido|hoy|urgent|últim|ultim|cupos)\b"),
    "conditional_financial_support": re.compile(r"(?i)\b(dinero|plata|soles|econom|pago|paga|renta|ingreso|apoyo)\b"),
    "platform_migration": re.compile(r"(?i)\b(whatsapp|wsp|telegram|llam|escrib|contact|envia|envía|manda)\b"),
    "privacy_or_secrecy_pressure": re.compile(r"(?i)\b(discret|secre|privad|confidenc|reservad|nadie)\b"),
    "age_or_youth_targeting": re.compile(r"(?i)\b(joven|señorita|chica|18|19|20)\b"),
    "education_or_student_targeting": re.compile(r"(?i)\b(estudi|universi|alumna|institut|colegio)\b"),
    "commitment_escalation": re.compile(r"(?i)\b(constant|perman|semanal|mensual|fijo|regular|acuerd|comprom)\b"),
    "sexualized_appearance_condition": re.compile(r"(?i)\b(guap|lind|bonit|figur|cuerpo|presencia|atractiv)\b"),
    "authority_or_status_appeal": re.compile(r"(?i)\b(serio|seria|profesional|empresarial|solvent|ejecutiv|formal)\b"),
    "social_proof": re.compile(r"(?i)\b(muchos|varios|otros|recomend|popular|confian|referencia)\b"),
    "reciprocity_obligation": re.compile(r"(?i)\b(ayuda|brindo|ofrezco|favor|regalo|apoyo)\b"),
    "deceptive_assurance": re.compile(r"(?i)\b(seguro|garantiz|confiable|real|verdad|sin riesgo)\b"),
}


def silver_annotate(text: str) -> list[dict]:
    """Independent silver annotation using different signal patterns."""
    spans = []
    for label, pattern in SILVER_SIGNALS.items():
        for m in pattern.finditer(text):
            spans.append({
                "label": label,
                "start": m.start(),
                "end": m.end(),
                "surface": m.group(0),
                "annotator": "silver_v1",
                "confidence": 0.7,  # fixed confidence for rule-based silver
            })
    return spans


def simulate_gold(council_record: dict, text: str, rng: random.Random) -> dict:
    """Simulate gold annotation from council labels using a noise model."""
    council_spans = council_record.get("spans", [])
    agreement = council_record.get("agreement", 1.0)

    gold_spans = []
    for span in council_spans:
        # Probability of gold-keeping based on agreement
        if agreement >= 0.9:  # 3/3 unanimous
            p_keep = 0.95
        elif agreement >= 0.67:  # 2/3
            p_keep = 0.70
        else:  # 1/3
            p_keep = 0.30

        if rng.random() < p_keep:
            # 5% chance of label flip (simulating human-independent judgment)
            if rng.random() < 0.05:
                # Flip to a random other label
                all_labels = list(SILVER_SIGNALS.keys()) + ["other"]
                new_label = rng.choice([l for l in all_labels if l != span.get("label")])
                span = {**span, "label": new_label, "gold_flipped": True}
            gold_spans.append({
                "label": span.get("label"),
                "start": span.get("segments", [[0, 0]])[0][0] if span.get("segments") else 0,
                "end": span.get("segments", [[0, 0]])[0][1] if span.get("segments") else 0,
                "surface": span.get("exact_text", ""),
                "annotator": "simulated_gold",
                "confidence": 1.0,
                "source_agreement": agreement,
            })

    return {
        "record_id": council_record.get("record_id"),
        "text": text,
        "spans": gold_spans,
        "annotator": "simulated_gold",
        "gold": True,  # SIMULATED gold — not real human gold
        "simulation_notes": "Simulated from council annotations using agreement-based noise model. NOT real human gold.",
    }


def compute_agreement(gold: dict, silver: dict) -> dict:
    """Compute span-level agreement between gold and silver annotations."""
    gold_labels = {(s["start"], s["end"], s["label"]) for s in gold.get("spans", [])}
    silver_labels = {(s["start"], s["end"], s["label"]) for s in silver.get("spans", [])}

    # Label-set agreement (does this ad have the same SET of labels?)
    gold_label_set = {s["label"] for s in gold.get("spans", [])}
    silver_label_set = {s["label"] for s in silver.get("spans", [])}

    # Per-label binary agreement
    all_labels = gold_label_set | silver_label_set
    tp = len(gold_label_set & silver_label_set)
    fp = len(silver_label_set - gold_label_set)
    fn = len(gold_label_set - silver_label_set)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    # Exact span match
    exact_match = len(gold_labels & silver_labels)
    exact_precision = exact_match / len(silver_labels) if silver_labels else 0.0
    exact_recall = exact_match / len(gold_labels) if gold_labels else 0.0
    exact_f1 = 2 * exact_precision * exact_recall / (exact_precision + exact_recall) if (exact_precision + exact_recall) else 0.0

    return {
        "record_id": gold.get("record_id"),
        "n_gold_spans": len(gold_labels),
        "n_silver_spans": len(silver_labels),
        "label_set_f1": round(f1, 4),
        "label_set_precision": round(precision, 4),
        "label_set_recall": round(recall, 4),
        "exact_span_f1": round(exact_f1, 4),
        "exact_span_precision": round(exact_precision, 4),
        "exact_span_recall": round(exact_recall, 4),
        "gold_labels": sorted(gold_label_set),
        "silver_labels": sorted(silver_label_set),
    }


def main() -> int:
    rng = random.Random(42)
    council = []
    with open(COUNCIL) as f:
        for line in f:
            if line.strip():
                council.append(json.loads(line))

    manifest_by_id = {}
    with open(MANIFEST) as f:
        for line in f:
            r = json.loads(line)
            manifest_by_id[r["record_id"]] = f"{r.get('title', '')}\n{r.get('body_redacted', '')}"

    print(f"Loaded {len(council)} council annotations, {len(manifest_by_id)} manifest records")

    # Generate simulated gold and silver annotations
    gold_records = []
    silver_records = []
    agreements = []

    n_processed = 0
    for c in council:
        rid = c.get("record_id")
        text = manifest_by_id.get(rid, "")
        if not text:
            continue

        gold = simulate_gold(c, text, rng)
        silver_spans = silver_annotate(text)
        silver = {
            "record_id": rid,
            "text": text,
            "spans": silver_spans,
            "annotator": "silver_v1",
            "gold": False,
            "independent_implementation": True,
        }

        gold_records.append(gold)
        silver_records.append(silver)
        agreements.append(compute_agreement(gold, silver))
        n_processed += 1

    print(f"Processed {n_processed} records")

    # Write annotations
    OUT_GOLD.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_GOLD, "w") as f:
        for r in gold_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(OUT_SILVER, "w") as f:
        for r in silver_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Aggregate agreement
    label_set_f1s = [a["label_set_f1"] for a in agreements]
    exact_f1s = [a["exact_span_f1"] for a in agreements]

    # Cohen's kappa on label presence (per-label binary)
    all_labels = set()
    for a in agreements:
        all_labels.update(a["gold_labels"])
        all_labels.update(a["silver_labels"])

    per_label_kappa = {}
    for label in sorted(all_labels):
        gold_present = [label in a["gold_labels"] for a in agreements]
        silver_present = [label in a["silver_labels"] for a in agreements]
        # Simple agreement
        n = len(agreements)
        agree = sum(1 for g, s in zip(gold_present, silver_present) if g == s)
        p_obs = agree / n if n else 0
        p_gold = sum(gold_present) / n if n else 0
        p_silver = sum(silver_present) / n if n else 0
        p_expected = p_gold * p_silver + (1 - p_gold) * (1 - p_silver)
        kappa = (p_obs - p_expected) / (1 - p_expected) if (1 - p_expected) > 0 else 0
        per_label_kappa[label] = round(kappa, 4)

    report = {
        "analysis_type": "annotation_agreement_simulated_gold_vs_silver",
        "n_records": n_processed,
        "gold_source": "simulated from council annotations (agreement-based noise model)",
        "silver_source": "independent rule-based annotator with different signal patterns",
        "label_set_agreement": {
            "mean_f1": round(float(np.mean(label_set_f1s)), 4),
            "median_f1": round(float(np.median(label_set_f1s)), 4),
            "std_f1": round(float(np.std(label_set_f1s)), 4),
        },
        "exact_span_agreement": {
            "mean_f1": round(float(np.mean(exact_f1s)), 4),
            "median_f1": round(float(np.median(exact_f1s)), 4),
            "std_f1": round(float(np.std(exact_f1s)), 4),
        },
        "per_label_cohen_kappa": per_label_kappa,
        "interpretation": {
            "kappa_0.81_1.00": "almost perfect agreement",
            "kappa_0.61_0.80": "substantial agreement",
            "kappa_0.41_0.60": "moderate agreement",
            "kappa_0.21_0.40": "fair agreement",
            "kappa_0.00_0.20": "slight agreement",
            "kappa_below_0": "poor agreement",
        },
        "limitations": [
            "Gold is SIMULATED, not real human adjudication",
            "Silver annotator is rule-based, not human",
            "Agreement estimates are optimistic because gold was derived from the same council data",
            "Real human annotation would likely show LOWER agreement due to genuine independence",
        ],
        "what_real_gold_would_require": [
            "2+ trained human annotators",
            "Adjudication of disagreements by a senior annotator",
            "Blinded annotation (annotators don't see each other's labels)",
            "Inter-annotator agreement measured BEFORE adjudication",
            "Power analysis for sample size",
        ],
        "gold_output": str(OUT_GOLD),
        "silver_output": str(OUT_SILVER),
    }

    OUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUT_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nAnnotation agreement results:")
    print(f"  Label-set F1: mean={report['label_set_agreement']['mean_f1']}, std={report['label_set_agreement']['std_f1']}")
    print(f"  Exact-span F1: mean={report['exact_span_agreement']['mean_f1']}, std={report['exact_span_agreement']['std_f1']}")
    print(f"  Per-label Cohen's kappa (top 5):")
    for label, kappa in sorted(per_label_kappa.items(), key=lambda x: -x[1])[:5]:
        print(f"    {label}: {kappa}")
    print(f"\n  Gold output: {OUT_GOLD}")
    print(f"  Silver output: {OUT_SILVER}")
    print(f"  Report: {OUT_REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
