#!/usr/bin/env python3
"""Deploy the adintel dashboard to GitHub Pages.

GitHub Pages is configured to serve from /docs/ on the main branch.
This script copies the generated dashboard + supporting JSON data into
/docs/reports/adintel/ so that the next push triggers a Pages deployment
to https://pillb.github.io/manipsych-adintel/.

Usage:
    python3 scripts/deploy_to_pages.py

After running, commit and push the changes:
    git add docs/
    git commit -m "deploy: solarize dashboard to GitHub Pages"
    git push origin main
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]  # /home/z/my-project/
SRC = REPO / "repo" / "reports" / "adintel"
DST = REPO / "docs" / "reports" / "adintel"

REQUIRED_FILES = [
    "adintel_dashboard.html",
    "solarize_summary.json",
    "solarize_per_ad.jsonl",
    "full_data_results.json",
    "clustering_summary.json",
    "outlier_summary.json",
    "cluster_alignment_report.json",
    "deep_clustering_analysis.json",
    "profile_sample.json",
    "pipeline_results.json",
    "taxonomy_v2.json",
    "checkpoint_registry.json",
    "authorship_known_pairs.json",
    "v1_to_v2_migration_report.json",
    "performance_benchmarks.json",
    "annotation_agreement.json",
    "monitoring_report.json",
    "causal_analysis.json",
    "causal_analysis_smart.json",
    "visual_persuasion_report.json",
    "vlm_screenshot_report.json",
    "vlm_visual_report.json",
]


def main() -> int:
    DST.mkdir(parents=True, exist_ok=True)
    copied = 0
    missing = 0
    for fname in REQUIRED_FILES:
        src = SRC / fname
        dst = DST / fname
        if src.exists():
            shutil.copy2(src, dst)
            size_kb = dst.stat().st_size / 1024
            print(f"  copied {fname}: {size_kb:.1f} KB")
            copied += 1
        else:
            print(f"  MISSING {fname}")
            missing += 1
    print(f"\nDone: {copied} files copied, {missing} missing.")
    if missing > 0:
        print("Some source files are missing — the deploy may be incomplete.")
    return 0 if missing == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
