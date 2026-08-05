#!/usr/bin/env python3
"""Run the Solarize engine on the full ManiPsych corpus.

Produces:
  - reports/adintel/solarize_summary.json  (aggregate, embedded in dashboard)
  - reports/adintel/solarize_per_ad.jsonl   (per-ad, fetched on demand)

The Solarize engine extends the existing adintel package with:
  - per-ad cluster membership (silhouette, alternative cluster, strength)
  - 4-way outlier classification (detector / density_noise / cluster_enriched / boundary)
  - feature-engineering benchmark (raw TF-IDF vs LSA vs SVD-scaled)
  - term-prevalence comparison with Wilson CI + Cohen's h + BH FDR
    across three control populations
  - explicit "NOT meaningfully different" verdict when warranted
"""

from __future__ import annotations

import json
import sys
import time
import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from adintel import outlier as ot
from adintel import solarize_engine as se

MANIFEST = ROOT / "data" / "processed" / "ad_manifest.jsonl"
COUNCIL = ROOT / "data" / "annotation" / "council_resolved_annotations.jsonl"
OUT_DIR = ROOT / "reports" / "adintel"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def load_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    out = []
    with open(path) as f:
        for line in f:
            if line.strip():
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
    return out


def get_commit_sha() -> str:
    """Get current git commit SHA. Returns 'unknown' if not in a repo."""
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, stderr=subprocess.DEVNULL
        ).decode().strip()
        return sha
    except Exception:
        return "unknown"


def get_commit_short() -> str:
    sha = get_commit_sha()
    return sha[:8] if sha != "unknown" else "unknown"


def main():
    t0 = time.perf_counter()
    print("=== SOLARIZE ENGINE ===")

    records = load_jsonl(MANIFEST)
    council = load_jsonl(COUNCIL)
    print(f"Loaded {len(records)} manifest records, {len(council)} council annotations")
    if not records:
        print("ERROR: no records loaded")
        sys.exit(1)

    texts = [f"{r.get('title','')} {r.get('body_redacted','')}" for r in records]
    label_sets = []
    labels_by_id = {}
    for c in council:
        rid = c.get("record_id")
        if rid:
            labels_by_id.setdefault(rid, set()).update(
                s.get("label") for s in c.get("spans", []) if s.get("label")
            )
    label_sets = [labels_by_id.get(r.get("record_id", ""), set()) for r in records]

    # ---- 1. Run existing outlier detection (sample n=1000) for historical kinds ----
    print("\n[1/3] Running existing outlier detection (sample n=1000)...")
    SAMPLE_N = 1000
    sample_records = records[:SAMPLE_N]
    sample_texts = texts[:SAMPLE_N]
    sample_label_sets = label_sets[:SAMPLE_N]
    historical_outlier_reports = ot.detect_all_outliers(
        sample_texts, sample_records, label_sets=sample_label_sets
    )
    print(f"  {len(historical_outlier_reports)} historical outlier reports (sample={SAMPLE_N})")

    # ---- 2. Run Solarize engine on full corpus ----
    print(f"\n[2/3] Running Solarize engine on {len(records)} records...")
    summary = se.build_solarize_summary(
        records=records,
        texts=texts,
        historical_outlier_reports=historical_outlier_reports,
        k=5,
        top_k_terms=50,
        top_n_ad_selector=300,
    )

    # ---- 3. Attach build fingerprint ----
    sha = get_commit_sha()
    sha_short = get_commit_short()
    manifest_hash = hashlib.sha256(open(MANIFEST, "rb").read()).hexdigest()[:16]
    fingerprint = f"solarize-{sha_short}-{manifest_hash}-{int(time.time())}"
    summary["build"].update({
        "commit_sha": sha,
        "commit_short": sha_short,
        "build_fingerprint": fingerprint,
        "manifest_sha256": manifest_hash,
    })

    # ---- 4. Save solarize_summary.json ----
    summary_path = OUT_DIR / "solarize_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\n  Saved: {summary_path} ({summary_path.stat().st_size / 1024:.1f} KB)")

    # ---- 5. Save solarize_per_ad.jsonl (full per-ad records for selector lookup) ----
    per_ad_path = OUT_DIR / "solarize_per_ad.jsonl"
    # We already have top 300 in summary.per_ad_selector, but write a more
    # complete per-ad file by recomputing from memberships.
    # Actually, we don't have memberships separately. So write the top 300
    # plus all outlier-flagged records.
    outlier_kind_by_id = summary["outlier_kind_by_record_id"]
    per_ad_records = list(summary["per_ad_selector"])
    seen_ids = {r["record_id"] for r in per_ad_records}
    # Add all outlier-flagged records not already in selector
    for rid, kinds in outlier_kind_by_id.items():
        if rid in seen_ids:
            continue
        rec = next((r for r in records if r.get("record_id") == rid), None)
        if not rec:
            continue
        # Find this ad's text and basic info — cluster_id may be missing
        idx = next((i for i, r in enumerate(records) if r.get("record_id") == rid), None)
        if idx is None:
            continue
        per_ad_records.append({
            "record_id": rid,
            "title": (rec.get("title", "") or "")[:80],
            "platform": rec.get("metadata", {}).get("platform_family", "unknown"),
            "cluster_id": -1,  # unknown — would need full re-walk
            "cluster_membership_strength": 0.0,
            "distance_to_centroid": 0.0,
            "silhouette": 0.0,
            "alternative_cluster_id": -1,
            "alternative_cluster_membership_strength": 0.0,
            "outlier_kinds": kinds,
            "outlier_score": 0.0,
            "body_preview": (texts[idx] or "")[:200],
        })
        seen_ids.add(rid)

    with open(per_ad_path, "w") as f:
        for rec in per_ad_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"  Saved: {per_ad_path} ({per_ad_path.stat().st_size / 1024:.1f} KB, {len(per_ad_records)} records)")

    # ---- 6. Print summary ----
    elapsed = time.perf_counter() - t0
    print(f"\n=== SOLARIZE COMPLETE ({elapsed:.1f}s) ===")
    print(f"  Commit SHA: {sha}")
    print(f"  Fingerprint: {fingerprint}")
    print(f"  N records: {summary['build']['n_records']}")
    print(f"  N clusters: {summary['clustering']['n_clusters']}")
    print(f"  Silhouette: {summary['clustering']['silhouette_mean']}")
    print(f"  Deep clustering justified: {summary['clustering']['deep_clustering_justified']}")
    print(f"  Outlier kinds: {summary['outliers']['by_kind']}")
    print(f"  Per-ad selector: {len(summary['per_ad_selector'])} top ads")
    print(f"  Per-ad JSONL: {len(per_ad_records)} records")
    for pop_key, pop_data in summary["term_comparison"].items():
        v = pop_data["aggregate_verdict"]
        print(f"  {pop_key}: {v['overall_verdict']} ({v['n_meaningfully_different']}/{v['n_terms_total']} meaningful)")


if __name__ == "__main__":
    main()
