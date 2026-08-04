#!/usr/bin/env python3
"""Drop processed ad manifest rows that fail strict raw/content coherence checks."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.phase_gate import _contains_contact_like_pii, _looks_like_ui_boilerplate, _platform_family, _raw_family
from tools.redact_pii import redact_text
from tools.scrape_ads import is_access_interstitial


AGE_RISK_TERMS = (
    "menor de 18",
    "menores de 18",
    "menor edad",
    "colegiala",
    "colegialas",
    "chica pequeña",
    "chica pequena",
    "no importa la edad",
    "sin importar edad",
    "sin importar la edad",
    "cualquier edad",
    "pulpin",
    "pulpines",
    "niña",
    "nina",
)


def _contains_age_risk_signal(record: dict[str, object]) -> bool:
    metadata = record.get("metadata", {})
    original_url = metadata.get("original_url", "") if isinstance(metadata, dict) else ""
    text = f"{record.get('title', '')} {original_url}".lower()
    return any(term in text for term in AGE_RISK_TERMS)


def reasons_for_record(record: dict[str, object], seen_raw_refs: set[str], seen_record_ids: set[str]) -> list[str]:
    reasons: list[str] = []
    record_id = str(record.get("record_id", ""))
    title = str(record.get("title", ""))
    body = str(record.get("body_redacted", ""))
    raw_ref = str(record.get("raw_archive_ref", ""))
    if not title or not body or not raw_ref:
        reasons.append("missing_required_text_or_raw_ref")
    if record_id in seen_record_ids:
        reasons.append("duplicate_record_id")
    if is_access_interstitial(f"{title} {body}"):
        reasons.append("processed_interstitial")
    if _contains_contact_like_pii(json.dumps(record, ensure_ascii=False)):
        reasons.append("processed_contact_like_pii")
    if _looks_like_ui_boilerplate(body):
        reasons.append("processed_ui_boilerplate")
    if _contains_age_risk_signal(record):
        reasons.append("processed_age_risk_signal")
    if raw_ref in seen_raw_refs:
        reasons.append("duplicate_raw_ref")
    if raw_ref:
        raw_path = ROOT / raw_ref
        if not raw_path.exists():
            reasons.append("missing_raw_ref")
        else:
            raw_html = raw_path.read_text(encoding="utf-8", errors="ignore")
            if is_access_interstitial(raw_html):
                reasons.append("raw_interstitial")
            raw_family = _raw_family(raw_ref)
            platform_family = _platform_family(str(record.get("source_platform", "")))
            if raw_family != "other" and platform_family != "other" and raw_family != platform_family:
                reasons.append("raw_platform_family_mismatch")
    return reasons


def scrub_invalid_ads(path: Path) -> dict[str, object]:
    records: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))

    kept: list[dict[str, object]] = []
    seen_raw_refs: set[str] = set()
    seen_record_ids: set[str] = set()
    removed: Counter[str] = Counter()
    for record in records:
        for field in ("title", "body_redacted"):
            record[field] = redact_text(str(record.get(field, "")))
        reasons = reasons_for_record(record, seen_raw_refs, seen_record_ids)
        raw_ref = str(record.get("raw_archive_ref", ""))
        record_id = str(record.get("record_id", ""))
        if reasons:
            removed.update(reasons)
            continue
        seen_raw_refs.add(raw_ref)
        seen_record_ids.add(record_id)
        kept.append(record)

    backup = path.with_suffix(path.suffix + f".strict_backup_{int(time.time())}")
    shutil.copy2(path, backup)
    path.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n" for record in kept), encoding="utf-8")
    return {
        "manifest": str(path),
        "backup": str(backup),
        "input_records": len(records),
        "kept_records": len(kept),
        "removed_records": len(records) - len(kept),
        "removal_reasons": dict(removed),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", nargs="?", type=Path, default=ROOT / "data" / "processed" / "ad_manifest.jsonl")
    args = parser.parse_args()
    print(json.dumps(scrub_invalid_ads(args.manifest), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
