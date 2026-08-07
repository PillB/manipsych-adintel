#!/usr/bin/env python3
"""Run adintel pipeline on FULL data (not sample).

The existing pipeline uses samples (200 for profile, 300 for clustering,
1000 for outliers). This script runs on ALL 5,189 records and produces
complete technique-level results with real examples.
"""

from __future__ import annotations

import json, sys, time, hashlib
from pathlib import Path
from collections import Counter, defaultdict

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from adintel import profile as pf
from adintel import outlier as ot
from adintel import taxonomy as tx
from adintel.clean_body import clean_ad_text

MANIFEST = ROOT / "data" / "processed" / "ad_manifest.jsonl"
COUNCIL = ROOT / "data" / "annotation" / "council_resolved_annotations.jsonl"
OUT_DIR = ROOT / "reports" / "adintel"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def load_jsonl(path):
    if not path.exists(): return []
    out = []
    with open(path) as f:
        for line in f:
            if line.strip():
                try: out.append(json.loads(line))
                except: pass
    return out


def main():
    t0 = time.perf_counter()
    print("=== FULL-DATA ADINTEL PIPELINE ===")

    records = load_jsonl(MANIFEST)
    council = load_jsonl(COUNCIL)
    print(f"Loaded {len(records)} manifest records, {len(council)} council annotations")

    # Build text and label index
    texts = [clean_ad_text(r.get('title',''), r.get('body_redacted','')) for r in records]
    labels_by_id = {}
    for c in council:
        rid = c.get("record_id")
        if rid:
            labels_by_id.setdefault(rid, set()).update(
                s.get("label") for s in c.get("spans", []) if s.get("label")
            )

    # ---- 1. FULL PROFILE SCORING (all 5,189 records) ----
    print(f"\nScoring 17-dim profile on ALL {len(records)} records...")
    t_p = time.perf_counter()
    all_profiles = []
    for i, (r, text) in enumerate(zip(records, texts)):
        p = pf.score_profile(text, record_id=r.get("record_id", str(i)))
        all_profiles.append(p.to_dict())
    profile_ms = (time.perf_counter() - t_p) * 1000
    print(f"  Done in {profile_ms:.0f}ms ({profile_ms/len(records):.2f}ms/ad)")

    # Aggregate dimension stats
    from adintel.types import PROFILE_DIMENSIONS
    dim_stats = {}
    for d in PROFILE_DIMENSIONS:
        scores = [p["dimensions"][d]["score"] for p in all_profiles]
        abstains = sum(1 for p in all_profiles if p["dimensions"][d].get("abstained"))
        dim_stats[d] = {
            "mean": round(sum(scores)/len(scores), 4),
            "median": round(sorted(scores)[len(scores)//2], 4),
            "max": round(max(scores), 4),
            "n_above_0.3": sum(1 for s in scores if s > 0.3),
            "n_above_0.5": sum(1 for s in scores if s > 0.5),
            "n_abstained": abstains,
            "abstention_rate": round(abstains/len(scores), 4),
            "prevalence": round(sum(1 for s in scores if s > 0.1)/len(scores), 4),
        }

    # ---- 2. TECHNIQUE-LEVEL RESULTS (from council labels) ----
    print(f"\nComputing technique-level results...")
    all_labels = set()
    for labels in labels_by_id.values():
        all_labels.update(labels)

    technique_results = []
    for label in sorted(all_labels):
        ads_with = [rid for rid, labels in labels_by_id.items() if label in labels]
        ads_without = [rid for rid, labels in labels_by_id.items() if label not in labels]
        # Get example ads
        examples = []
        for rid in ads_with[:3]:
            rec = next((r for r in records if r.get("record_id") == rid), None)
            if rec:
                examples.append({
                    "record_id": rid,
                    "title": rec.get("title", "")[:80],
                    "platform": rec.get("metadata", {}).get("platform_family", "unknown"),
                })
        technique_results.append({
            "label": label,
            "count": len(ads_with),
            "prevalence": round(len(ads_with)/len(council), 4),
            "denominator": len(council),
            "example_ids": ads_with[:5],
            "examples": examples,
            "model_version": "council-v5",
            "taxonomy_version": tx.TAXONOMY_VERSION,
            "v2_leaves": tx.v1_to_v2(label),
        })

    # ---- 3. FULL OUTLIER DETECTION (all 5,189 records) ----
    print(f"\nRunning outlier detection on ALL {len(records)} records...")
    t_o = time.perf_counter()
    label_sets = [labels_by_id.get(r.get("record_id",""), set()) for r in records]
    outlier_reports = ot.detect_all_outliers(texts, records, label_sets=label_sets)
    outlier_ms = (time.perf_counter() - t_o) * 1000
    print(f"  Done in {outlier_ms:.0f}ms, {len(outlier_reports)} reports")

    outlier_by_kind = Counter(r.kind for r in outlier_reports)
    outlier_examples = {}
    for kind in outlier_by_kind:
        kind_reports = [r for r in outlier_reports if r.kind == kind]
        outlier_examples[kind] = [
            {"record_id": r.record_id, "score": r.score, "method": r.method,
             "alternative_explanation": r.alternative_explanation,
             "uncertainty": r.uncertainty}
            for r in kind_reports[:3]
        ]

    # ---- 4. DATA HASHES ----
    manifest_hash = hashlib.sha256(open(MANIFEST, "rb").read()).hexdigest()[:16]
    council_hash = hashlib.sha256(open(COUNCIL, "rb").read()).hexdigest()[:16]

    # ---- 5. SAVE FULL RESULTS ----
    full_results = {
        "run_id": f"full-data-{int(time.time())}",
        "ran_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_records": len(records),
        "n_council_annotations": len(council),
        "manifest_sha256": manifest_hash,
        "council_sha256": council_hash,
        "taxonomy_version": tx.TAXONOMY_VERSION,
        "elapsed_s": round(time.perf_counter() - t0, 2),

        "profile": {
            "n_records": len(records),
            "uses_full_data": True,
            "dimensions": dim_stats,
            "sample_record_ids": [p["record_id"] for p in all_profiles[:5]],
            "first_profile": all_profiles[0] if all_profiles else None,
        },

        "techniques": {
            "n_techniques": len(technique_results),
            "results": technique_results,
        },

        "outliers": {
            "n_records": len(records),
            "uses_full_data": True,
            "n_reports": len(outlier_reports),
            "by_kind": dict(outlier_by_kind),
            "examples": outlier_examples,
        },

        "cluster_alignment": json.load(open(OUT_DIR / "cluster_alignment_report.json"))["comparison"],
    }

    out_path = OUT_DIR / "full_data_results.json"
    out_path.write_text(json.dumps(full_results, indent=2, ensure_ascii=False))
    print(f"\n=== FULL DATA RESULTS SAVED ===")
    print(f"  Output: {out_path}")
    print(f"  Size: {out_path.stat().st_size / 1024:.1f} KB")
    print(f"  Records: {len(records)}")
    print(f"  Techniques: {len(technique_results)}")
    print(f"  Outliers: {len(outlier_reports)}")
    print(f"  Elapsed: {full_results['elapsed_s']}s")
    print(f"\n  Profile dimension means (top 5):")
    for d, s in sorted(dim_stats.items(), key=lambda x: -x[1]["mean"])[:5]:
        print(f"    {d}: mean={s['mean']}, prevalence={s['prevalence']}, abstention={s['abstention_rate']}")
    print(f"\n  Technique results (top 5):")
    for t in sorted(technique_results, key=lambda x: -x["count"])[:5]:
        print(f"    {t['label']}: count={t['count']}, prevalence={t['prevalence']}")
    print(f"\n  Outlier breakdown:")
    for kind, count in outlier_by_kind.most_common():
        print(f"    {kind}: {count}")
    print(f"\n  Cluster alignment: {full_results['cluster_alignment']['verdict']} (ARI={full_results['cluster_alignment']['metrics']['ARI']})")


if __name__ == "__main__":
    main()
