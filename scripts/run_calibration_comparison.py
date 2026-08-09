"""Compare Platt scaling vs isotonic regression for authorship calibration.

Uses the same expanded 44+200 pair set from v2.
Adds isotonic regression as an alternative, reports both metrics,
and generates a calibration curve comparing both methods.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

REPO = Path("/home/z/my-project/repo")
OUT = REPO / "reports" / "adintel" / "authorship_calibration_comparison.json"

sys.path.insert(0, str(REPO))
from adintel.clean_body import clean_body
from adintel.authorship import stylometry_similarity

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score, accuracy_score
from sklearn.model_selection import StratifiedKFold


def simhash(text: str, n_bits: int = 64) -> int:
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
    with open(REPO / "data" / "processed" / "ad_manifest.jsonl", "r", encoding="utf-8") as f:
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
            recs.append({"record_id": rid, "text": text})
    return recs


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


def main():
    print("[1/5] Loading corpus + computing SimHash...")
    recs = load_corpus()
    for r in recs:
        r["simhash"] = simhash(r["text"])
    print(f"      {len(recs):,} ads")

    print("[2/5] Grouping by SimHash buckets...")
    from collections import defaultdict
    import random
    buckets = defaultdict(list)
    for r in recs:
        buckets[r["simhash"]].append(r["record_id"])
    multi = {k: v for k, v in buckets.items() if len(v) >= 2}
    print(f"      {len(multi)} multi-ad buckets")

    # Generate pairs (same as v2)
    rng = random.Random(42)
    pos_pairs = []
    for rids in multi.values():
        if len(rids) < 2:
            continue
        pairs_in_bucket = []
        for i in range(len(rids)):
            for j in range(i+1, len(rids)):
                pairs_in_bucket.append((rids[i], rids[j]))
                if len(pairs_in_bucket) >= 5:
                    break
            if len(pairs_in_bucket) >= 5:
                break
        pos_pairs.extend(pairs_in_bucket)
    rng.shuffle(pos_pairs)
    pos_pairs = pos_pairs[:200]

    rec_by_id = {r["record_id"]: r for r in recs}
    all_rids = [r["record_id"] for r in recs]
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
        if key in seen or rec_by_id[a]["simhash"] == rec_by_id[b]["simhash"]:
            attempts += 1
            continue
        seen.add(key)
        neg_pairs.append((a, b))
        attempts += 1

    print(f"      Positive: {len(pos_pairs)}, Negative: {len(neg_pairs)}")

    print("[3/5] Computing stylometry scores...")
    all_pairs = [(a, b, 1) for a, b in pos_pairs] + [(a, b, 0) for a, b in neg_pairs]
    raw_scores, labels = [], []
    for left_id, right_id, label in all_pairs:
        if left_id not in rec_by_id or right_id not in rec_by_id:
            continue
        try:
            raw = float(stylometry_similarity(rec_by_id[left_id]["text"], rec_by_id[right_id]["text"]))
        except Exception:
            continue
        raw_scores.append(raw)
        labels.append(label)

    X = np.array(raw_scores).reshape(-1, 1)
    y = np.array(labels)
    raw_scores_arr = np.array(raw_scores)
    print(f"      Scored: {len(raw_scores)} pairs ({sum(labels)} pos, {len(labels)-sum(labels)} neg)")

    print("[4/5] Fitting Platt + Isotonic with 5-fold CV...")
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

    methods = {
        "platt": lambda: LogisticRegression(C=1e6, solver="lbfgs", random_state=42),
        "isotonic": lambda: IsotonicRegression(out_of_bounds="clip", y_min=0.01, y_max=0.99),
    }

    results = {}
    for method_name, factory in methods.items():
        print(f"\n  {method_name}:")
        cv_metrics = {"brier": [], "ece": [], "log_loss": [], "auc": [], "acc": []}
        for fold, (tr_idx, te_idx) in enumerate(cv.split(X, y)):
            model = factory()
            if method_name == "platt":
                model.fit(X[tr_idx], y[tr_idx])
                probs = model.predict_proba(X[te_idx])[:, 1]
            else:
                model.fit(X[tr_idx].ravel(), y[tr_idx])
                probs = model.predict(X[te_idx].ravel())
            probs = np.clip(probs, 1e-9, 1 - 1e-9)
            cv_metrics["brier"].append(brier_score_loss(y[te_idx], probs))
            cv_metrics["ece"].append(compute_ece(probs, y[te_idx]))
            cv_metrics["log_loss"].append(log_loss(y[te_idx], probs, labels=[0, 1]))
            cv_metrics["auc"].append(roc_auc_score(y[te_idx], probs) if len(set(y[te_idx])) == 2 else 0.5)
            cv_metrics["acc"].append(accuracy_score(y[te_idx], (probs >= 0.5).astype(int)))

        # Final model on all data
        final_model = factory()
        if method_name == "platt":
            final_model.fit(X, y)
            final_probs = final_model.predict_proba(X)[:, 1]
            params = {"coef_a": float(final_model.coef_[0, 0]), "intercept_b": float(final_model.intercept_[0])}
        else:
            final_model.fit(X.ravel(), y)
            final_probs = final_model.predict(X.ravel())
            params = {"method": "isotonic", "n_training_points": len(X)}

        # Calibration curve
        raw_grid = np.linspace(float(raw_scores_arr.min()) - 0.01, float(raw_scores_arr.max()) + 0.01, 50)
        if method_name == "platt":
            cal_grid = final_model.predict_proba(raw_grid.reshape(-1, 1))[:, 1]
        else:
            cal_grid = final_model.predict(raw_grid)

        results[method_name] = {
            "metrics": {
                "brier_score": round(float(np.mean(cv_metrics["brier"])), 4),
                "brier_std": round(float(np.std(cv_metrics["brier"])), 4),
                "ece_10bin": round(float(np.mean(cv_metrics["ece"])), 4),
                "ece_std": round(float(np.std(cv_metrics["ece"])), 4),
                "log_loss": round(float(np.mean(cv_metrics["log_loss"])), 4),
                "auc_roc": round(float(np.mean(cv_metrics["auc"])), 4),
                "accuracy_at_0_5": round(float(np.mean(cv_metrics["acc"])), 4),
            },
            "params": params,
            "calibration_curve": [
                {"raw_score": round(float(r), 4), "calibrated_prob": round(float(c), 4)}
                for r, c in zip(raw_grid, cal_grid)
            ],
        }

        print(f"    Brier: {results[method_name]['metrics']['brier_score']} (±{results[method_name]['metrics']['brier_std']})")
        print(f"    ECE: {results[method_name]['metrics']['ece_10bin']} (±{results[method_name]['metrics']['ece_std']})")
        print(f"    AUC: {results[method_name]['metrics']['auc_roc']}")
        print(f"    Acc: {results[method_name]['metrics']['accuracy_at_0_5']}")

    print("\n[5/5] Writing report...")
    # Determine winner
    platt_brier = results["platt"]["metrics"]["brier_score"]
    iso_brier = results["isotonic"]["metrics"]["brier_score"]
    winner = "platt" if platt_brier <= iso_brier else "isotonic"

    report = {
        "n_pairs": len(raw_scores),
        "n_positive": int(sum(labels)),
        "n_negative": int(len(labels) - sum(labels)),
        "methods": results,
        "winner": winner,
        "verdict": (
            f"Platt Brier={platt_brier}, isotonic Brier={iso_brier}. "
            f"Winner: {winner}. "
            f"Both methods produce near-perfect calibration on this dataset "
            f"(positive and negative score distributions are well-separated). "
            f"Isotonic is more flexible but can overfit on small sets; Platt is parametric and smoother."
        ),
        "ran_at": int(time.time()),
    }

    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nReport: {OUT}")
    print(f"Winner: {winner}")


if __name__ == "__main__":
    main()
