#!/usr/bin/env python3
"""Item 4: Quasi-causal analysis of technique → performance associations.

The corpus has no real A/B holdout, so we CANNOT make causal claims. But we
CAN:
  1. Compute descriptive associations (technique presence ↔ performance)
  2. Stratify by platform, seasonality, and quality_score to control confounders
  3. Estimate quasi-causal effects using matching and regression
  4. Report everything with the correct evidence ladder:
     descriptive < associative < predictive < quasi-causal < causal
  5. Explicitly mark what WOULD be needed for a real causal claim

This module does NOT claim causation. It reports the evidence honestly.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from collections import defaultdict

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PERF = ROOT / "data" / "processed" / "synthetic_performance.jsonl"
COUNCIL = ROOT / "data" / "annotation" / "council_resolved_annotations.jsonl"
MANIFEST = ROOT / "data" / "processed" / "ad_manifest.jsonl"
OUT = ROOT / "reports" / "adintel" / "causal_analysis.json"


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    with open(path) as f:
        for line in f:
            if line.strip():
                out.append(json.loads(line))
    return out


def main() -> int:
    perf = load_jsonl(PERF)
    council = load_jsonl(COUNCIL)
    manifest = load_jsonl(MANIFEST)

    if not perf:
        print("ERROR: synthetic_performance.jsonl not found. Run generate_synthetic_performance.py first.")
        return 1

    # Index by record_id
    perf_by_id = {p["record_id"]: p for p in perf}
    manifest_by_id = {m["record_id"]: m for m in manifest}
    labels_by_id = {}
    for c in council:
        rid = c.get("record_id")
        if rid:
            labels_by_id.setdefault(rid, set()).update(
                s.get("label") for s in c.get("spans", []) if s.get("label")
            )

    # For each technique label, compute:
    # 1. Descriptive: mean CTR for ads with vs without the label
    # 2. Associative: correlation between label presence and CTR
    # 3. Stratified: CTR difference controlling for platform
    # 4. Quasi-causal: matched-pair estimate (match on platform + quality_score)

    all_labels = set()
    for labels in labels_by_id.values():
        all_labels.update(labels)

    results = []
    for label in sorted(all_labels):
        with_label = []
        without_label = []
        for rid, labels in labels_by_id.items():
            p = perf_by_id.get(rid)
            if not p:
                continue
            if label in labels:
                with_label.append(p)
            else:
                without_label.append(p)

        if len(with_label) < 10:
            continue

        ctr_with = np.mean([p["ctr"] for p in with_label])
        ctr_without = np.mean([p["ctr"] for p in without_label])
        diff = ctr_with - ctr_without

        # Stratified by platform (top 3 platforms)
        platform_strata = {}
        for platform in ["doplim", "locanto", "ciudadanuncios"]:
            with_p = [p for p in with_label if p["platform"] == platform]
            without_p = [p for p in without_label if p["platform"] == platform]
            if len(with_p) >= 5 and len(without_p) >= 5:
                platform_strata[platform] = {
                    "n_with": len(with_p),
                    "n_without": len(without_p),
                    "ctr_with": float(np.mean([p["ctr"] for p in with_p])),
                    "ctr_without": float(np.mean([p["ctr"] for p in without_p])),
                    "diff": float(np.mean([p["ctr"] for p in with_p]) - np.mean([p["ctr"] for p in without_p])),
                }

        # Quasi-causal: matched-pair estimate
        # Match each ad with the label to an ad without the label on platform + quality_score bucket
        matched_diffs = []
        for p_with in with_label:
            # Find best match: same platform, closest quality_score
            candidates = [p for p in without_label
                         if p["platform"] == p_with["platform"]
                         and abs(p["quality_score"] - p_with["quality_score"]) < 0.15]
            if candidates:
                best = min(candidates, key=lambda p: abs(p["quality_score"] - p_with["quality_score"]))
                matched_diffs.append(p_with["ctr"] - best["ctr"])

        matched_estimate = float(np.mean(matched_diffs)) if matched_diffs else None
        matched_se = float(np.std(matched_diffs) / math.sqrt(len(matched_diffs))) if len(matched_diffs) > 1 else None

        # Evidence ladder
        if matched_estimate is not None and abs(matched_estimate) < 0.001:
            evidence_level = "descriptive"
        elif matched_estimate is not None and matched_se and abs(matched_estimate) > 2 * matched_se:
            evidence_level = "quasi_causal"
        else:
            evidence_level = "associative"

        results.append({
            "label": label,
            "n_with_label": len(with_label),
            "n_without_label": len(without_label),
            "ctr_with_label": round(ctr_with, 6),
            "ctr_without_label": round(ctr_without, 6),
            "descriptive_diff": round(diff, 6),
            "platform_stratified": platform_strata,
            "matched_estimate": round(matched_estimate, 6) if matched_estimate is not None else None,
            "matched_se": round(matched_se, 6) if matched_se is not None else None,
            "matched_n_pairs": len(matched_diffs),
            "evidence_level": evidence_level,
            "causal_claim": "NOT SUPPORTED — synthetic data; requires live A/B holdout for causal claim",
            "recommendation": f"To establish causality for '{label}', run a randomized A/B holdout where the technique is deliberately varied while holding all else constant.",
        })

    # Overall summary
    summary = {
        "analysis_type": "quasi_causal_association",
        "data_source": "synthetic_performance.jsonl (SYNTHETIC — based on researched benchmarks, NOT real observed performance)",
        "method": "matched-pair estimation on platform + quality_score",
        "evidence_ladder": ["descriptive", "associative", "predictive", "quasi_causal", "causal"],
        "highest_evidence_achieved": max(r["evidence_level"] for r in results) if results else "none",
        "n_techniques_analyzed": len(results),
        "n_techniques_quasi_causal": sum(1 for r in results if r["evidence_level"] == "quasi_causal"),
        "causal_claims_made": 0,
        "causal_claims_supported": 0,
        "results": results,
        "limitations": [
            "Synthetic performance data — not real observed outcomes",
            "No randomized A/B holdout — cannot establish causality",
            "Matching on platform + quality_score only — residual confounding likely",
            "Small sample sizes for rare labels reduce statistical power",
            "Seasonality and audience effects not fully controlled",
        ],
        "what_would_be_needed_for_causal": [
            "Randomized A/B holdout where the technique is deliberately varied",
            "Real performance metrics (CTR, conversion, spend) from ad platform APIs",
            "Pre-registration of hypothesis and analysis plan",
            "Adequate sample size (power analysis)",
            "Attribution window consistency across arms",
            "Blinded outcome assessment",
        ],
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Causal analysis complete: {len(results)} techniques analyzed")
    print(f"  Quasi-causal: {summary['n_techniques_quasi_causal']}")
    print(f"  Associative: {sum(1 for r in results if r['evidence_level'] == 'associative')}")
    print(f"  Descriptive: {sum(1 for r in results if r['evidence_level'] == 'descriptive')}")
    print(f"  Causal claims made: {summary['causal_claims_made']}")
    print(f"  Causal claims supported: {summary['causal_claims_supported']}")
    print(f"  Output: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
