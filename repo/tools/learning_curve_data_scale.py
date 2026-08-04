#!/usr/bin/env python3
"""Learning-curve study: model metrics vs number of processed records.

Uses a fixed holdout test set; trains on increasing train sizes (absolute and
per-platform). Reports marginal gains and recommends whether to stay at 1500
or continue +10% batches.

Outputs: reports/learning_curve_data_scale.json
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, precision_recall_fscore_support
from sklearn.model_selection import train_test_split
from sklearn.multiclass import OneVsRestClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import MultiLabelBinarizer

from tools.train_manipulation_model import build_dataset, load_records

DEFAULT_MANIFEST = ROOT / "data" / "processed" / "ad_manifest.jsonl"
DEFAULT_OUT = ROOT / "reports" / "learning_curve_data_scale.json"


def platform_bucket(record: dict) -> str:
    p = str(record.get("source_platform") or record.get("metadata", {}).get("platform_family") or "").lower()
    if "locanto" in p:
        return "locanto"
    if "doplim" in p:
        return "doplim"
    if "ciudad" in p or "ciudadanuncios" in p:
        return "ciudadanuncios"
    if "evisos" in p or "evisex" in p:
        return "evisos"
    if "facebook" in p or "fb" in p:
        return "facebook"
    meta = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    fam = str(meta.get("platform_family") or "").lower()
    if fam in ("locanto", "doplim", "evisos", "facebook", "ciudadanuncios"):
        return fam
    ref = str(record.get("raw_archive_ref") or "").lower()
    if "locanto" in ref or "hombre_busca" in ref:
        return "locanto"
    if "doplim" in ref or "dop" in ref:
        return "doplim"
    if "ciudadanuncios" in ref:
        return "ciudadanuncios"
    if "evisos" in ref or "evisex" in ref:
        return "evisos"
    if "facebook" in ref or "/fb_" in ref:
        return "facebook"
    return "other"


def train_eval(texts_train, labels_train, texts_test, labels_test, all_label_sets) -> dict:
    mlb = MultiLabelBinarizer()
    # Fit on full label universe so dims match
    mlb.fit(all_label_sets)
    y_train = mlb.transform(labels_train)
    y_test = mlb.transform(labels_test)
    if len(texts_train) < 8:
        return {"error": "too_few_train", "n_train": len(texts_train)}
    model = Pipeline(
        [
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=1, max_features=3000)),
            ("clf", OneVsRestClassifier(LogisticRegression(max_iter=1000, class_weight="balanced"))),
        ]
    )
    model.fit(texts_train, y_train)
    y_pred = model.predict(y_test) if False else model.predict(texts_test)
    precision, recall, macro_f1, _ = precision_recall_fscore_support(
        y_test, y_pred, average="macro", zero_division=0
    )
    micro_f1 = f1_score(y_test, y_pred, average="micro", zero_division=0)
    acc = accuracy_score(y_test, y_pred)
    return {
        "n_train": len(texts_train),
        "n_test": len(texts_test),
        "macro_f1": round(float(macro_f1), 4),
        "micro_f1": round(float(micro_f1), 4),
        "macro_precision": round(float(precision), 4),
        "macro_recall": round(float(recall), 4),
        "accuracy": round(float(acc), 4),
    }


def size_grid(n_max: int, base: int = 1500) -> list[int]:
    """Absolute sizes up to n_max, plus +10% steps from base if larger."""
    seeds = [50, 100, 200, 400, 600, 800, 1000, 1200, 1500]
    sizes = [s for s in seeds if s <= n_max]
    if n_max >= base:
        s = base
        while s <= n_max:
            if s not in sizes:
                sizes.append(s)
            nxt = int(round(s * 1.10))
            if nxt <= s:
                nxt = s + max(1, int(0.1 * s))
            s = nxt
    if n_max not in sizes and n_max >= 50:
        sizes.append(n_max)
    return sorted(set(sizes))


def marginal_analysis(curve: list[dict], metric: str = "macro_f1") -> list[dict]:
    out = []
    for i in range(1, len(curve)):
        a, b = curve[i - 1], curve[i]
        if a.get("error") or b.get("error"):
            continue
        dn = b["n_train"] - a["n_train"]
        dm = b[metric] - a[metric]
        out.append(
            {
                "from_n": a["n_train"],
                "to_n": b["n_train"],
                "delta_n": dn,
                f"delta_{metric}": round(dm, 4),
                f"gain_per_100_records": round(100.0 * dm / dn, 4) if dn else None,
            }
        )
    return out


def recommend(curve: list[dict], marginal: list[dict], base: int = 1500) -> dict:
    """Recommend stay at base if diminishing returns, else continue +10%."""
    clean = [c for c in curve if not c.get("error")]
    if not clean:
        return {"action": "insufficient_data", "reason": "no successful train points"}
    max_n = max(c["n_train"] for c in clean)
    # Find point at or just below base
    at_base = [c for c in clean if c["n_train"] >= min(base, max_n)]
    if not at_base:
        return {
            "action": "collect_to_base",
            "reason": f"max train n={max_n} < base={base}",
            "suggested_target": base,
        }
    # Diminishing returns: last steps after 0.7*base have gain_per_100 < threshold
    threshold = 0.005  # <0.5 F1 points per 100 records
    late = [m for m in marginal if m["from_n"] >= int(0.7 * min(base, max_n))]
    if not late:
        late = marginal[-3:] if len(marginal) >= 3 else marginal
    late_gains = [m["gain_per_100_records"] for m in late if m["gain_per_100_records"] is not None]
    avg_late = sum(late_gains) / len(late_gains) if late_gains else 0.0
    best = max(clean, key=lambda c: (c["macro_f1"], c["micro_f1"]))
    if max_n < base:
        return {
            "action": "collect_to_base",
            "reason": f"need more data to reach {base}",
            "suggested_target": base,
            "best_n": best["n_train"],
            "best_macro_f1": best["macro_f1"],
            "avg_late_gain_per_100": round(avg_late, 4),
        }
    if avg_late < threshold:
        return {
            "action": "stay",
            "reason": (
                f"diminishing returns: avg gain/100 records after ~0.7×base = {avg_late:.4f} "
                f"< threshold {threshold}"
            ),
            "suggested_target": base,
            "best_n": best["n_train"],
            "best_macro_f1": best["macro_f1"],
            "avg_late_gain_per_100": round(avg_late, 4),
        }
    # continue +10%
    nxt = int(round(max_n * 1.10))
    return {
        "action": "continue_plus_10pct",
        "reason": f"still meaningful gains (avg late gain/100={avg_late:.4f})",
        "suggested_target": nxt,
        "best_n": best["n_train"],
        "best_macro_f1": best["macro_f1"],
        "avg_late_gain_per_100": round(avg_late, 4),
    }


def run_curve(
    indices: list[int],
    texts: list[str],
    labels: list[list[str]],
    test_idx: list[int],
    sizes: list[int],
    rng: random.Random,
) -> tuple[list[dict], list[dict]]:
    test_texts = [texts[i] for i in test_idx]
    test_labels = [labels[i] for i in test_idx]
    train_pool = [i for i in indices if i not in set(test_idx)]
    rng.shuffle(train_pool)
    all_label_sets = labels
    curve = []
    for n in sizes:
        if n > len(train_pool):
            continue
        pick = train_pool[:n]
        tr_t = [texts[i] for i in pick]
        tr_l = [labels[i] for i in pick]
        metrics = train_eval(tr_t, tr_l, test_texts, test_labels, all_label_sets)
        curve.append(metrics)
    return curve, marginal_analysis(curve)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--base-target", type=int, default=1500)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--test-size", type=float, default=0.25)
    args = ap.parse_args()

    records = load_records(args.manifest)
    texts, labels = build_dataset(records)
    platforms = [platform_bucket(r) for r in records]
    rng = random.Random(args.seed)

    # Global fixed holdout
    idx = list(range(len(records)))
    train_idx, test_idx = train_test_split(
        idx, test_size=args.test_size, random_state=args.seed
    )
    # re-seed train order
    train_idx = list(train_idx)
    rng.shuffle(train_idx)

    global_sizes = size_grid(len(train_idx), args.base_target)
    # Use only train pool for size grid max
    g_curve, g_marg = run_curve(train_idx, texts, labels, test_idx, global_sizes, rng)
    g_rec = recommend(g_curve, g_marg, args.base_target)

    by_platform: dict = {}
    plat_groups: dict[str, list[int]] = defaultdict(list)
    for i, p in enumerate(platforms):
        plat_groups[p].append(i)

    for plat, pidx in sorted(plat_groups.items()):
        if len(pidx) < 20:
            by_platform[plat] = {
                "n_records": len(pidx),
                "note": "too_few_for_curve",
                "recommendation": {
                    "action": "collect_to_base",
                    "suggested_target": args.base_target,
                    "reason": f"only {len(pidx)} processed records",
                },
            }
            continue
        # platform-local split
        p_train, p_test = train_test_split(pidx, test_size=min(0.3, max(0.2, 8 / len(pidx))), random_state=args.seed)
        p_train = list(p_train)
        rng.shuffle(p_train)
        sizes = size_grid(len(p_train), min(args.base_target, len(p_train)))
        # For platform curves, test set is platform-local
        curve = []
        test_texts = [texts[i] for i in p_test]
        test_labels = [labels[i] for i in p_test]
        for n in sizes:
            if n < 8:
                continue
            pick = p_train[:n]
            metrics = train_eval(
                [texts[i] for i in pick],
                [labels[i] for i in pick],
                test_texts,
                test_labels,
                labels,
            )
            curve.append(metrics)
        marg = marginal_analysis(curve)
        rec = recommend(curve, marg, min(args.base_target, len(pidx)))
        # if platform has fewer than base, force collect_to_base
        if len(pidx) < args.base_target:
            rec = {
                "action": "collect_to_base",
                "reason": f"processed count {len(pidx)} < {args.base_target}",
                "suggested_target": args.base_target,
                "current_processed": len(pidx),
                "best_n": rec.get("best_n"),
                "best_macro_f1": rec.get("best_macro_f1"),
                "avg_late_gain_per_100": rec.get("avg_late_gain_per_100"),
            }
        by_platform[plat] = {
            "n_records": len(pidx),
            "n_train_pool": len(p_train),
            "n_test": len(p_test),
            "curve": curve,
            "marginal": marg,
            "recommendation": rec,
        }

    report = {
        "manifest": str(args.manifest),
        "total_records": len(records),
        "platform_counts": dict(Counter(platforms)),
        "base_target": args.base_target,
        "holdout_test_size": len(test_idx),
        "global": {
            "n_train_pool": len(train_idx),
            "curve": g_curve,
            "marginal": g_marg,
            "recommendation": g_rec,
        },
        "by_platform": by_platform,
        "summary": {
            "doplim": by_platform.get("doplim", {}).get("recommendation"),
            "locanto": by_platform.get("locanto", {}).get("recommendation"),
            "ciudadanuncios": by_platform.get("ciudadanuncios", {}).get("recommendation"),
            "evisos": by_platform.get("evisos", {}).get("recommendation"),
            "facebook": by_platform.get("facebook", {}).get("recommendation"),
            "global": g_rec,
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    print(f"wrote {args.out}")
    print("platform_counts", report["platform_counts"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
