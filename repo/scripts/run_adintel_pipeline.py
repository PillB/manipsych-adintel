#!/usr/bin/env python3
"""End-to-end adintel pipeline runner.

Exercises the new adintel package on the real ManiPsych corpus:
  1. Loads the manifest (data/processed/ad_manifest.jsonl)
  2. Loads council annotations (data/annotation/council_resolved_annotations.jsonl)
  3. Runs the persuasive profile on a sample of ads
  4. Runs 7-space clustering on a sample
  5. Runs authorship verification on known same-source pairs from similarity_links.jsonl
  6. Runs outlier detection on the full corpus
  7. Writes reports/adintel/pipeline_results.json

This is the integration test that proves the package actually runs end-to-end
on real data, not just unit tests on synthetic fixtures.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path("/home/z/my-project/repo")
# scripts/ is at /home/z/my-project/scripts/, repo is at /home/z/my-project/repo/
sys.path.insert(0, str(ROOT))

from adintel import authorship as au
from adintel import checkpoints as cp
from adintel import clustering as cl
from adintel import outlier as ot
from adintel import profile as pf
from adintel import taxonomy as tx
from adintel.clean_body import clean_ad_text
from adintel.api import AdIntelAPI


MANIFEST = ROOT / "data" / "processed" / "ad_manifest.jsonl"
COUNCIL = ROOT / "data" / "annotation" / "council_resolved_annotations.jsonl"
SIM_LINKS = ROOT / "data" / "annotation" / "similarity_links.jsonl"
OUT_DIR = ROOT / "reports" / "adintel"
OUT_DIR.mkdir(parents=True, exist_ok=True)

PROFILE_SAMPLE = 200  # cap for speed
CLUSTER_SAMPLE = 300
AUTHORSHIP_PAIRS = 50
OUTLIER_SAMPLE = 1000


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return out


def main() -> int:
    t0 = time.perf_counter()
    print(f"[adintel-pipeline] ROOT={ROOT}")
    print(f"[adintel-pipeline] manifest: {MANIFEST} exists={MANIFEST.exists()}")
    print(f"[adintel-pipeline] council: {COUNCIL} exists={COUNCIL.exists()}")
    print(f"[adintel-pipeline] sim_links: {SIM_LINKS} exists={SIM_LINKS.exists()}")

    records = load_jsonl(MANIFEST)
    council = load_jsonl(COUNCIL)
    sim_links = load_jsonl(SIM_LINKS)
    print(f"[adintel-pipeline] loaded records={len(records)} council={len(council)} sim_links={len(sim_links)}")

    # Build text + record_id index
    rec_by_id = {r.get("record_id"): r for r in records if isinstance(r, dict) and r.get("record_id")}
    texts_full = [(r.get("record_id", ""), clean_ad_text(r.get('title', ''), r.get('body_redacted', ''))) for r in records if isinstance(r, dict)]

    # Council labels per record
    labels_by_id: dict[str, set[str]] = {}
    for c in council:
        rid = c.get("record_id")
        if not rid:
            continue
        labels = {s.get("label") for s in c.get("spans", []) if s.get("label")}
        labels_by_id.setdefault(rid, set()).update(labels)

    # ---- 1. Taxonomy report ------------------------------------------
    print("[adintel-pipeline] writing taxonomy v2 ...")
    tx.to_json(OUT_DIR / "taxonomy_v2.json")

    # ---- 2. Persuasive profile on sample -----------------------------
    print(f"[adintel-pipeline] scoring profile on sample of {PROFILE_SAMPLE} ...")
    sample_text = texts_full[:PROFILE_SAMPLE]
    profiles: list[dict] = []
    t_p = time.perf_counter()
    for rid, text in sample_text:
        p = pf.score_profile(text, record_id=rid)
        profiles.append(p.to_dict())
    profile_ms = (time.perf_counter() - t_p) * 1000.0
    print(f"[adintel-pipeline]   done in {profile_ms:.0f}ms ({profile_ms/len(sample_text):.2f}ms per ad)")
    # Compute mean per-dimension
    from adintel.types import PROFILE_DIMENSIONS
    dim_means = {d: float(sum(p["dimensions"].get(d, {}).get("score", 0.0) for p in profiles) / max(1, len(profiles))) for d in PROFILE_DIMENSIONS}
    dim_abstain = {d: int(sum(1 for p in profiles if p["dimensions"].get(d, {}).get("abstained", False))) for d in PROFILE_DIMENSIONS}
    (OUT_DIR / "profile_sample.json").write_text(json.dumps({
        "n_sampled": len(profiles),
        "dimension_means": dim_means,
        "dimension_abstain_counts": dim_abstain,
        "sample_record_ids": [p["record_id"] for p in profiles[:10]],
        "first_profile": profiles[0] if profiles else None,
    }, ensure_ascii=False, indent=2))

    # ---- 3. Clustering on sample -------------------------------------
    print(f"[adintel-pipeline] clustering on stratified sample of {CLUSTER_SAMPLE} ...")
    # R1-D01 fix: use stratified sampling by platform to avoid the
    # ingestion-order-induced brand leakage we saw in Round 1.
    cluster_records = cl.stratified_sample(records, by_field="source_platform", n_per_stratum=CLUSTER_SAMPLE // 5)
    cluster_texts = [clean_ad_text(r.get('title', ''), r.get('body_redacted', '')) for r in cluster_records]
    cluster_profiles = []
    for r in cluster_records:
        text = clean_ad_text(r.get('title', ''), r.get('body_redacted', ''))
        cluster_profiles.append(pf.score_profile(text, record_id=r.get("record_id", "")).to_dict())
    t_c = time.perf_counter()
    cluster_results = cl.cluster_all_spaces(cluster_records, cluster_texts, profiles=cluster_profiles, k=5, compute_stability=True)
    cluster_ms = (time.perf_counter() - t_c) * 1000.0
    print(f"[adintel-pipeline]   done in {cluster_ms:.0f}ms")
    cluster_summary: dict = {}
    for space, (assignments, report) in cluster_results.items():
        cluster_summary[space] = {
            "n_clusters": report.n_clusters,
            "n_noise": report.n_noise,
            "stability_ari": round(report.stability_ari, 4),
            "resampling_consistency": round(report.resampling_consistency, 4),
            "parameter_sensitivity": round(report.parameter_sensitivity, 4),
            "brand_leakage": report.brand_leakage,
            "topic_leakage": report.topic_leakage,
        }
    (OUT_DIR / "clustering_summary.json").write_text(json.dumps({
        "n_sampled": CLUSTER_SAMPLE,
        "elapsed_ms": round(cluster_ms, 1),
        "spaces": cluster_summary,
    }, ensure_ascii=False, indent=2))

    # ---- 4. Authorship on known same-source pairs --------------------
    print(f"[adintel-pipeline] authorship on {AUTHORSHIP_PAIRS} known same-source pairs ...")
    accepted_links = [l for l in sim_links if l.get("decision") == "accepted"][:AUTHORSHIP_PAIRS]
    auth_results: list[dict] = []
    n_correct = 0
    n_abstain = 0
    t_a = time.perf_counter()
    for link in accepted_links:
        left_id = link.get("left_record_id")
        right_id = link.get("right_record_id")
        left_text = next((t for rid, t in texts_full if rid == left_id), None)
        right_text = next((t for rid, t in texts_full if rid == right_id), None)
        if not left_text or not right_text:
            continue
        r = au.pairwise_verify(left_text, right_text, labels_by_id.get(left_id, set()), labels_by_id.get(right_id, set()))
        auth_results.append({
            "left_id": left_id,
            "right_id": right_id,
            "verdict": r.verdict,
            "confidence": round(r.confidence, 3),
            "stylometry": round(r.stylometry_score or 0, 3),
            "survived": r.survived,
            "n_left_tokens": r.left_token_count,
            "n_right_tokens": r.right_token_count,
        })
        if r.verdict == "same_source":
            n_correct += 1
        elif r.verdict == "insufficient_evidence":
            n_abstain += 1
    auth_ms = (time.perf_counter() - t_a) * 1000.0
    print(f"[adintel-pipeline]   done in {auth_ms:.0f}ms; same_source={n_correct}/{len(auth_results)} abstain={n_abstain}")
    (OUT_DIR / "authorship_known_pairs.json").write_text(json.dumps({
        "n_pairs": len(auth_results),
        "n_same_source_predicted": n_correct,
        "n_abstained": n_abstain,
        "accuracy_against_accepted_links": round(n_correct / max(1, len(auth_results)), 4),
        "elapsed_ms": round(auth_ms, 1),
        "results_sample": auth_results[:10],
    }, ensure_ascii=False, indent=2))

    # ---- 5. Outlier detection on a larger sample ---------------------
    print(f"[adintel-pipeline] outlier detection on sample of {OUTLIER_SAMPLE} ...")
    out_records = records[:OUTLIER_SAMPLE]
    out_texts = [clean_ad_text(r.get('title', ''), r.get('body_redacted', '')) for r in out_records]
    out_labels = [labels_by_id.get(r.get("record_id", ""), set()) for r in out_records]
    t_o = time.perf_counter()
    outlier_reports = ot.detect_all_outliers(out_texts, out_records, label_sets=out_labels)
    outlier_ms = (time.perf_counter() - t_o) * 1000.0
    by_kind: dict[str, int] = {}
    for r in outlier_reports:
        by_kind[r.kind] = by_kind.get(r.kind, 0) + 1
    print(f"[adintel-pipeline]   done in {outlier_ms:.0f}ms; total reports={len(outlier_reports)} by_kind={by_kind}")
    (OUT_DIR / "outlier_summary.json").write_text(json.dumps({
        "n_sampled": OUTLIER_SAMPLE,
        "n_reports": len(outlier_reports),
        "by_kind": by_kind,
        "elapsed_ms": round(outlier_ms, 1),
        "sample_reports": [r.to_dict() for r in outlier_reports[:5]],
    }, ensure_ascii=False, indent=2))

    # ---- 6. Checkpoint registry dump ---------------------------------
    cp.registry_to_json(OUT_DIR / "checkpoint_registry.json")

    # ---- 7. Final summary --------------------------------------------
    elapsed = time.perf_counter() - t0
    summary = {
        "ran_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_s": round(elapsed, 2),
        "taxonomy_version": tx.TAXONOMY_VERSION,
        "n_records_total": len(records),
        "n_council_annotations": len(council),
        "n_similarity_links": len(sim_links),
        "n_profile_sampled": len(profiles),
        "n_cluster_sampled": CLUSTER_SAMPLE,
        "n_authorship_pairs": len(auth_results),
        "n_outlier_sampled": OUTLIER_SAMPLE,
        "profile_dimension_means": dim_means,
        "cluster_summary": cluster_summary,
        "authorship_accuracy_against_accepted_links": round(n_correct / max(1, len(auth_results)), 4),
        "outlier_by_kind": by_kind,
        "checkpoint_count": len(cp.REGISTRY),
        "outputs": {
            "taxonomy_v2": str(OUT_DIR / "taxonomy_v2.json"),
            "profile_sample": str(OUT_DIR / "profile_sample.json"),
            "clustering_summary": str(OUT_DIR / "clustering_summary.json"),
            "authorship_known_pairs": str(OUT_DIR / "authorship_known_pairs.json"),
            "outlier_summary": str(OUT_DIR / "outlier_summary.json"),
            "checkpoint_registry": str(OUT_DIR / "checkpoint_registry.json"),
        },
    }
    (OUT_DIR / "pipeline_results.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"[adintel-pipeline] DONE in {elapsed:.1f}s. Results in {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
