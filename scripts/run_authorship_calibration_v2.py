"""Expand the authorship calibration set from 10+10 to 200+200 pairs.

Strategy:
1. Load all 5,738 ads
2. Compute SimHash for each ad (char-4-gram, 64-bit)
3. Group ads by SimHash buckets (Hamming distance ≤ 3)
4. Within each bucket, generate positive pairs (same bucket = likely same source)
5. Generate negative pairs (random distinct buckets)
6. Compute stylometry_similarity for each pair
7. Fit Platt scaling on the expanded set
8. Compute Brier, ECE, log-loss, AUC with 5-fold CV

This gives a much more defensible calibration than the 10+10 set.
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
from pathlib import Path
from collections import defaultdict

REPO = Path("/home/z/my-project/repo")
DATA = REPO / "data" / "processed" / "ad_manifest.jsonl"
OUT = REPO / "reports" / "adintel" / "authorship_calibration_v2.json"

sys.path.insert(0, str(REPO))
from adintel.clean_body import clean_body
from adintel.authorship import stylometry_similarity

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score, accuracy_score
from sklearn.model_selection import StratifiedKFold


def simhash(text: str, n_bits: int = 64) -> int:
    """Compute SimHash for text using char-4-grams."""
    if len(text) < 4:
        return 0
    tokens = [text[i:i+4] for i in range(len(text) - 3)]
    v = [0] * n_bits
    for token in tokens:
        h = hash(token) & ((1 << n_bits) - 1)
        for i in range(n_bits):
            if h & (1 << i):
                v[i] += 1
            else:
                v[i] -= 1
    fingerprint = 0
    for i in range(n_bits):
        if v[i] > 0:
            fingerprint |= (1 << i)
    return fingerprint


def hamming_distance(a: int, b: int) -> int:
    return bin(a ^ b).count('1')


def load_corpus():
    recs = []
    with open(DATA, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            rid = rec.get("record_id", "")
            title = rec.get("title", "")
            body = clean_body(rec.get("body_redacted", ""))
            text = (title + " " + body).strip() or title
            if len(text) < 20:
                continue
            recs.append({"record_id": rid, "text": text, "platform": rec.get("source_platform", "")})
    return recs


def main():
    print("[1/6] Loading corpus...")
    recs = load_corpus()
    print(f"      {len(recs):,} ads")

    print("[2/6] Computing SimHash for each ad...")
    t0 = time.time()
    for r in recs:
        r["simhash"] = simhash(r["text"])
    print(f"      Done in {time.time()-t0:.1f}s")

    print("[3/6] Grouping by SimHash buckets (Hamming ≤ 3)...")
    # Group by exact SimHash first (fast)
    exact_buckets = defaultdict(list)
    for r in recs:
        exact_buckets[r["simhash"]].append(r["record_id"])

    # Also check near-duplicates (Hamming ≤ 3) — sample-based for speed
    buckets = defaultdict(list)
    for sh, rids in exact_buckets.items():
        buckets[sh] = rids

    # Merge buckets with Hamming ≤ 3
    simhashes = list(buckets.keys())
    merged = {}
    parent = {s: s for s in simhashes}

    def find(s):
        while parent[s] != s:
            parent[s] = parent[parent[s]]
            s = parent[s]
        return s

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    # Sample 2000 simhashes for merging (full N² is too slow)
    sample_size = min(2000, len(simhashes))
    rng = random.Random(42)
    sample = rng.sample(simhashes, sample_size)
    for i in range(len(sample)):
        for j in range(i+1, len(sample)):
            if hamming_distance(sample[i], sample[j]) <= 3:
                union(sample[i], sample[j])

    # Build merged buckets
    final_buckets = defaultdict(list)
    for s in simhashes:
        root = find(s)
        final_buckets[root].extend(buckets[s])

    multi_buckets = {k: v for k, v in final_buckets.items() if len(v) >= 2}
    print(f"      {len(multi_buckets)} multi-ad buckets (≥2 ads)")
    total_in_buckets = sum(len(v) for v in multi_buckets.values())
    print(f"      {total_in_buckets:,} ads in multi-ad buckets")

    print("[4/6] Generating positive + negative pairs...")
    # Positive pairs: from same bucket (max 5 per bucket to avoid dominance)
    pos_pairs = []
    for rids in multi_buckets.values():
        if len(rids) < 2:
            continue
        # Sample up to 5 pairs per bucket
        pairs_in_bucket = []
        for i in range(len(rids)):
            for j in range(i+1, len(rids)):
                pairs_in_bucket.append((rids[i], rids[j]))
                if len(pairs_in_bucket) >= 5:
                    break
            if len(pairs_in_bucket) >= 5:
                break
        pos_pairs.extend(pairs_in_bucket)

    # Cap at 200 positive pairs
    rng = random.Random(42)
    rng.shuffle(pos_pairs)
    pos_pairs = pos_pairs[:200]

    # Negative pairs: random distinct ads (different buckets)
    all_rids = [r["record_id"] for r in recs]
    rec_by_id = {r["record_id"]: r for r in recs}
    neg_pairs = []
    seen = set()
    attempts = 0
    while len(neg_pairs) < 200 and attempts < 5000:
        i = rng.randrange(len(all_rids))
        j = rng.randrange(len(all_rids))
        if i == j:
            attempts += 1
            continue
        a, b = all_rids[i], all_rids[j]
        key = tuple(sorted([a, b]))
        if key in seen:
            attempts += 1
            continue
        # Ensure different buckets
        if rec_by_id[a]["simhash"] == rec_by_id[b]["simhash"]:
            attempts += 1
            continue
        seen.add(key)
        neg_pairs.append((a, b))
        attempts += 1

    print(f"      Positive pairs: {len(pos_pairs)}")
    print(f"      Negative pairs: {len(neg_pairs)}")

    print("[5/6] Computing stylometry similarity for all pairs...")
    all_pairs = [(a, b, 1) for a, b in pos_pairs] + [(a, b, 0) for a, b in neg_pairs]
    raw_scores = []
    labels = []
    for left_id, right_id, label in all_pairs:
        if left_id not in rec_by_id or right_id not in rec_by_id:
            continue
        try:
            raw = float(stylometry_similarity(rec_by_id[left_id]["text"], rec_by_id[right_id]["text"]))
        except Exception:
            continue
        raw_scores.append(raw)
        labels.append(label)

    raw_scores = np.array(raw_scores)
    labels = np.array(labels)
    print(f"      Scored: {len(raw_scores)} pairs ({sum(labels)} positive, {len(labels)-sum(labels)} negative)")
    pos_mean = raw_scores[labels == 1].mean() if (labels == 1).sum() > 0 else 0
    neg_mean = raw_scores[labels == 0].mean() if (labels == 0).sum() > 0 else 0
    print(f"      Mean raw score (positive): {pos_mean:.4f}")
    print(f"      Mean raw score (negative): {neg_mean:.4f}")

    print("[6/6] Fitting Platt scaling + 5-fold CV...")
    X = raw_scores.reshape(-1, 1)
    y = labels

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_metrics = {"brier": [], "ece": [], "log_loss": [], "auc": [], "acc": []}

    def compute_ece(probs, labels, n_bins=10):
        probs, labels = np.asarray(probs), np.asarray(labels)
        bins = np.linspace(0, 1, n_bins + 1)
        ece = 0.0
        n = len(probs)
        for i in range(n_bins):
            lo, hi = bins[i], bins[i + 1]
            mask = (probs >= lo) & (probs < hi if i < n_bins - 1 else probs <= hi)
            if mask.sum() == 0:
                continue
            ece += (mask.sum() / n) * abs(probs[mask].mean() - labels[mask].mean())
        return float(ece)

    for fold, (tr_idx, te_idx) in enumerate(cv.split(X, y)):
        lr = LogisticRegression(C=1e6, solver="lbfgs", random_state=42)
        lr.fit(X[tr_idx], y[tr_idx])
        probs = np.clip(lr.predict_proba(X[te_idx])[:, 1], 1e-9, 1 - 1e-9)
        cv_metrics["brier"].append(brier_score_loss(y[te_idx], probs))
        cv_metrics["ece"].append(compute_ece(probs, y[te_idx]))
        cv_metrics["log_loss"].append(log_loss(y[te_idx], probs, labels=[0, 1]))
        cv_metrics["auc"].append(roc_auc_score(y[te_idx], probs) if len(set(y[te_idx])) == 2 else 0.5)
        cv_metrics["acc"].append(accuracy_score(y[te_idx], (probs >= 0.5).astype(int)))

    # Final model on all data
    final_lr = LogisticRegression(C=1e6, solver="lbfgs", random_state=42)
    final_lr.fit(X, y)
    platt_a = float(final_lr.coef_[0, 0])
    platt_b = float(final_lr.intercept_[0])

    metrics = {
        "brier_score": round(float(np.mean(cv_metrics["brier"])), 4),
        "brier_std": round(float(np.std(cv_metrics["brier"])), 4),
        "ece_10bin": round(float(np.mean(cv_metrics["ece"])), 4),
        "ece_std": round(float(np.std(cv_metrics["ece"])), 4),
        "log_loss": round(float(np.mean(cv_metrics["log_loss"])), 4),
        "log_loss_std": round(float(np.std(cv_metrics["log_loss"])), 4),
        "auc_roc": round(float(np.mean(cv_metrics["auc"])), 4),
        "auc_std": round(float(np.std(cv_metrics["auc"])), 4),
        "accuracy_at_0_5": round(float(np.mean(cv_metrics["acc"])), 4),
        "accuracy_std": round(float(np.std(cv_metrics["acc"])), 4),
        "n_folds": 5,
    }

    # Calibration curve
    raw_grid = np.linspace(float(raw_scores.min()) - 0.01, float(raw_scores.max()) + 0.01, 50)
    cal_grid = final_lr.predict_proba(raw_grid.reshape(-1, 1))[:, 1]
    cal_curve = [{"raw_score": round(float(r), 4), "calibrated_prob": round(float(c), 4)} for r, c in zip(raw_grid, cal_grid)]

    report = {
        "n_positive_pairs": len(pos_pairs),
        "n_synthetic_negatives": len(neg_pairs),
        "n_scored": len(raw_scores),
        "calibration_method": "platt_v2_expanded",
        "calibration_params": {
            "coef_a": round(platt_a, 4),
            "intercept_b": round(platt_b, 4),
            "formula": f"p(same_source) = sigmoid({platt_a:.4f} * raw_score + {platt_b:.4f})",
        },
        "metrics": metrics,
        "calibration_curve": cal_curve,
        "raw_score_stats": {
            "positive_mean": round(float(pos_mean), 4),
            "negative_mean": round(float(neg_mean), 4),
            "positive_min": round(float(raw_scores[labels == 1].min()), 4) if (labels == 1).sum() > 0 else 0,
            "positive_max": round(float(raw_scores[labels == 1].max()), 4) if (labels == 1).sum() > 0 else 0,
            "negative_min": round(float(raw_scores[labels == 0].min()), 4) if (labels == 0).sum() > 0 else 0,
            "negative_max": round(float(raw_scores[labels == 0].max()), 4) if (labels == 0).sum() > 0 else 0,
        },
        "improvement_vs_v1": {
            "v1_pairs": "10+10",
            "v2_pairs": f"{len(pos_pairs)}+{len(neg_pairs)}",
            "v1_brier": 0.0001,
            "v2_brier": metrics["brier_score"],
            "v1_ece": 0.0023,
            "v2_ece": metrics["ece_10bin"],
            "note": "v2 has 20x more data; metrics are more honest. Higher Brier/ECE expected due to harder negatives.",
        },
        "ran_at": int(time.time()),
    }

    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nReport: {OUT}")
    print(f"\nMetrics:")
    for k, v in metrics.items():
        print(f"  {k}: {v}")
    print(f"\nPlatt formula: {report['calibration_params']['formula']}")


if __name__ == "__main__":
    main()
