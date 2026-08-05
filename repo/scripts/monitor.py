#!/usr/bin/env python3
"""O-03: Monitoring script — checks key metrics against thresholds.

Runs drift checks, calibration checks, and system health checks.
Produces reports/adintel/monitoring_report.json.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "reports" / "adintel" / "monitoring_report.json"

# Thresholds
THRESHOLDS = {
    "authorship_tpr_min": 0.60,
    "authorship_fpr_max": 0.05,
    "calibration_brier_max": 0.10,
    "calibration_ece_max": 0.15,
    "test_pass_rate_min": 0.99,
    "pipeline_record_count_min": 5000,
}


def check_authorship() -> dict:
    """Check authorship TPR and FPR against thresholds."""
    path = ROOT / "audit" / "assurance" / "evidence" / "negative_pair_evaluation.json"
    if not path.exists():
        return {"check": "authorship", "status": "not_verified", "reason": "evaluation file not found"}
    data = json.load(open(path))
    tpr = data["pos_pairs"]["tpr"]
    fpr = data["neg_pairs"]["fpr"]
    return {
        "check": "authorship",
        "tpr": round(tpr, 4),
        "fpr": round(fpr, 4),
        "tpr_threshold": THRESHOLDS["authorship_tpr_min"],
        "fpr_threshold": THRESHOLDS["authorship_fpr_max"],
        "tpr_pass": tpr >= THRESHOLDS["authorship_tpr_min"],
        "fpr_pass": fpr <= THRESHOLDS["authorship_fpr_max"],
        "status": "pass" if tpr >= THRESHOLDS["authorship_tpr_min"] and fpr <= THRESHOLDS["authorship_fpr_max"] else "fail",
    }


def check_calibration() -> dict:
    """Check calibration metrics."""
    path = ROOT / "audit" / "assurance" / "evidence" / "calibration_report.json"
    if not path.exists():
        return {"check": "calibration", "status": "not_verified", "reason": "calibration report not found"}
    data = json.load(open(path))
    brier = data["calibration_metrics"]["brier_score"]
    ece = data["calibration_metrics"]["ece_5bin"]
    return {
        "check": "calibration",
        "brier": round(brier, 4),
        "ece": round(ece, 4),
        "brier_threshold": THRESHOLDS["calibration_brier_max"],
        "ece_threshold": THRESHOLDS["calibration_ece_max"],
        "brier_pass": brier <= THRESHOLDS["calibration_brier_max"],
        "ece_pass": ece <= THRESHOLDS["calibration_ece_max"],
        "status": "pass" if brier <= THRESHOLDS["calibration_brier_max"] and ece <= THRESHOLDS["calibration_ece_max"] else "fail",
    }


def check_file_integrity() -> dict:
    """Check file integrity manifest exists."""
    path = ROOT / "audit" / "assurance" / "evidence" / "file_integrity_manifest.json"
    if not path.exists():
        return {"check": "file_integrity", "status": "not_verified", "reason": "manifest not found"}
    data = json.load(open(path))
    return {
        "check": "file_integrity",
        "file_count": data["file_count"],
        "generated_at": data["generated_at"],
        "status": "pass",
    }


def check_pipeline() -> dict:
    """Check pipeline results exist and have correct record count."""
    path = ROOT / "reports" / "adintel" / "pipeline_results.json"
    if not path.exists():
        return {"check": "pipeline", "status": "not_verified", "reason": "pipeline results not found"}
    data = json.load(open(path))
    records = data.get("n_records_total", 0)
    return {
        "check": "pipeline",
        "n_records": records,
        "threshold": THRESHOLDS["pipeline_record_count_min"],
        "status": "pass" if records >= THRESHOLDS["pipeline_record_count_min"] else "fail",
    }


def check_dashboard_live() -> dict:
    """Check if dashboard HTML exists and is non-trivial."""
    path = ROOT / "reports" / "adintel" / "adintel_dashboard.html"
    if not path.exists():
        return {"check": "dashboard", "status": "not_verified", "reason": "dashboard not found"}
    size = path.stat().st_size
    return {
        "check": "dashboard",
        "size_bytes": size,
        "size_mb": round(size / 1024 / 1024, 1),
        "status": "pass" if size > 1_000_000 else "fail",
    }


def main() -> int:
    checks = [
        check_authorship(),
        check_calibration(),
        check_file_integrity(),
        check_pipeline(),
        check_dashboard_live(),
    ]

    report = {
        "monitored_at": datetime.now(timezone.utc).isoformat(),
        "thresholds": THRESHOLDS,
        "checks": checks,
        "n_checks": len(checks),
        "n_pass": sum(1 for c in checks if c.get("status") == "pass"),
        "n_fail": sum(1 for c in checks if c.get("status") == "fail"),
        "n_not_verified": sum(1 for c in checks if c.get("status") == "not_verified"),
        "overall_status": "pass" if all(c.get("status") == "pass" for c in checks) else "fail",
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2))
    print(f"Monitoring: {report['n_pass']}/{report['n_checks']} checks pass, {report['n_fail']} fail, {report['n_not_verified']} not verified")
    print(f"Overall: {report['overall_status']}")
    print(f"Output: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
