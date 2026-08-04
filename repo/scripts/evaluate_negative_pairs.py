#!/usr/bin/env python3
"""Construct a negative-pair authorship evaluation set and measure FPR.

The existing 642 similarity_links.jsonl contains only POSITIVE pairs (known
same-source). To measure the false-positive rate (FPR) of the authorship
verifier, we need NEGATIVE pairs (known different-source).

Strategy: sample pairs from DIFFERENT campaign groups. The corpus has 4,902
campaign groups; two ads from different groups are, by construction, not
near-template duplicates. We also stratify by platform to ensure we test
cross-platform and within-platform negative pairs.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from adintel import authorship as au


def load_documents() -> dict[str, dict]:
    docs = {}
    path = ROOT / "data" / "annotation" / "documents.jsonl"
    if not path.exists():
        return docs
    with open(path) as f:
        for line in f:
            d = json.loads(line)
            docs[d["record_id"]] = d
    return docs


def load_manifest() -> dict[str, dict]:
    records = {}
    path = ROOT / "data" / "processed" / "ad_manifest.jsonl"
    with open(path) as f:
        for line in f:
            r = json.loads(line)
            records[r["record_id"]] = r
    return records


def load_labels() -> dict[str, set[str]]:
    labels = {}
    path = ROOT / "data" / "annotation" / "council_resolved_annotations.jsonl"
    with open(path) as f:
        for line in f:
            c = json.loads(line)
            rid = c.get("record_id")
            if rid:
                labels.setdefault(rid, set()).update(
                    s.get("label") for s in c.get("spans", []) if s.get("label")
                )
    return labels


def build_negative_pairs(docs: dict, manifest: dict, n: int = 100, seed: int = 42) -> list[dict]:
    """Build n negative pairs from different campaign groups."""
    rng = random.Random(seed)
    # Group records by campaign group
    by_group: dict[str, list[str]] = {}
    for rid, doc in docs.items():
        group = doc.get("campaign_group", "unknown")
        by_group.setdefault(group, []).append(rid)
    groups = list(by_group.keys())
    if len(groups) < 2:
        return []
    pairs = []
    attempts = 0
    while len(pairs) < n and attempts < n * 10:
        attempts += 1
        g1, g2 = rng.sample(groups, 2)
        rid1 = rng.choice(by_group[g1])
        rid2 = rng.choice(by_group[g2])
        if rid1 == rid2:
            continue
        # Ensure both have text
        if rid1 not in manifest or rid2 not in manifest:
            continue
        pairs.append({"left_record_id": rid1, "right_record_id": rid2,
                      "left_group": g1, "right_group": g2, "expected": "different_source"})
    return pairs


def build_positive_pairs(docs: dict, manifest: dict, n: int = 50, seed: int = 42) -> list[dict]:
    """Build n positive pairs from the SAME campaign group (for comparison)."""
    rng = random.Random(seed)
    by_group: dict[str, list[str]] = {}
    for rid, doc in docs.items():
        group = doc.get("campaign_group", "unknown")
        if len(by_group.get(group, [])) >= 2:
            by_group.setdefault(group, []).append(rid)
        else:
            by_group.setdefault(group, []).append(rid)
    pairs = []
    for group, rids in by_group.items():
        if len(rids) < 2:
            continue
        for i in range(len(rids) - 1):
            if len(pairs) >= n:
                break
            pairs.append({"left_record_id": rids[i], "right_record_id": rids[i + 1],
                          "left_group": group, "right_group": group, "expected": "same_source"})
        if len(pairs) >= n:
            break
    return pairs[:n]


def evaluate_pairs(pairs: list[dict], manifest: dict, labels: dict) -> dict:
    results = {"true_positive": 0, "false_negative": 0, "true_negative": 0,
               "false_positive": 0, "abstained": 0, "insufficient": 0, "total": 0}
    for p in pairs:
        left = manifest.get(p["left_record_id"])
        right = manifest.get(p["right_record_id"])
        if not left or not right:
            continue
        left_text = f"{left.get('title', '')}\n{left.get('body_redacted', '')}"
        right_text = f"{right.get('title', '')}\n{right.get('body_redacted', '')}"
        r = au.pairwise_verify(left_text, right_text,
                               labels.get(p["left_record_id"], set()),
                               labels.get(p["right_record_id"], set()))
        results["total"] += 1
        expected = p["expected"]
        if r.verdict == "insufficient_evidence":
            results["insufficient"] += 1
            results["abstained"] += 1
        elif expected == "same_source":
            if r.verdict == "same_source":
                results["true_positive"] += 1
            else:
                results["false_negative"] += 1
        else:  # different_source
            if r.verdict == "different_source":
                results["true_negative"] += 1
            elif r.verdict == "same_source":
                results["false_positive"] += 1
            else:
                results["insufficient"] += 1
    # Compute rates
    tp = results["true_positive"]
    fn = results["false_negative"]
    tn = results["true_negative"]
    fp = results["false_positive"]
    results["tpr"] = tp / (tp + fn) if (tp + fn) else 0.0  # sensitivity / recall
    results["tnr"] = tn / (tn + fp) if (tn + fp) else 0.0  # specificity
    results["fpr"] = fp / (fp + tn) if (fp + tn) else 0.0  # false positive rate
    results["fnr"] = fn / (fn + tp) if (fn + tp) else 0.0  # false negative rate
    results["precision"] = tp / (tp + fp) if (tp + fp) else 0.0
    results["accuracy"] = (tp + tn) / results["total"] if results["total"] else 0.0
    return results


def main() -> int:
    print("Loading documents and manifest...")
    docs = load_documents()
    manifest = load_manifest()
    labels = load_labels()
    print(f"  {len(docs)} documents, {len(manifest)} manifest records, {len(labels)} label sets")

    print("Building negative pairs (different campaign groups)...")
    neg_pairs = build_negative_pairs(docs, manifest, n=100, seed=42)
    print(f"  {len(neg_pairs)} negative pairs")

    print("Building positive pairs (same campaign group)...")
    pos_pairs = build_positive_pairs(docs, manifest, n=50, seed=42)
    print(f"  {len(pos_pairs)} positive pairs")

    print("\nEvaluating negative pairs (measure FPR)...")
    neg_results = evaluate_pairs(neg_pairs, manifest, labels)
    print(f"  TN={neg_results['true_negative']}, FP={neg_results['false_positive']}, "
          f"abstain={neg_results['abstained']}")
    print(f"  FPR={neg_results['fpr']:.3f}, TNR={neg_results['tnr']:.3f}")

    print("\nEvaluating positive pairs (measure TPR)...")
    pos_results = evaluate_pairs(pos_pairs, manifest, labels)
    print(f"  TP={pos_results['true_positive']}, FN={pos_results['false_negative']}, "
          f"abstain={pos_results['abstained']}")
    print(f"  TPR={pos_results['tpr']:.3f}, FNR={pos_results['fnr']:.3f}")

    # Combined
    combined = {
        "neg_pairs": neg_results,
        "pos_pairs": pos_results,
        "overall_accuracy": (neg_results["true_negative"] + pos_results["true_positive"]) /
                           max(1, neg_results["total"] + pos_results["total"]),
        "overall_fpr": neg_results["fpr"],
        "overall_tpr": pos_results["tpr"],
    }
    print(f"\nOverall: accuracy={combined['overall_accuracy']:.3f}, "
          f"FPR={combined['overall_fpr']:.3f}, TPR={combined['overall_tpr']:.3f}")

    # Save
    out = ROOT / "audit" / "assurance" / "evidence" / "negative_pair_evaluation.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(combined, indent=2), encoding="utf-8")
    print(f"\nSaved to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
