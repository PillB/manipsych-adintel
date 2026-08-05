#!/usr/bin/env python3
"""Item 5: Deduplicate annotation spans and improve annotation quality.

Found 73.2% of records have duplicate spans (same label + same exact_text).
This script deduplicates them and produces an improved annotation file.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data" / "annotation" / "council_resolved_annotations.jsonl"
OUTPUT = ROOT / "data" / "annotation" / "council_resolved_dedup.jsonl"
REPORT = ROOT / "docs" / "annotation_improvements" / "dedup_report.json"


def deduplicate_spans(spans: list[dict]) -> tuple[list[dict], int]:
    """Remove duplicate spans by (label, exact_text). Keep first occurrence."""
    seen = set()
    deduped = []
    removed = 0
    for s in spans:
        key = (s.get("label"), s.get("exact_text"))
        if key in seen:
            removed += 1
            continue
        seen.add(key)
        deduped.append(s)
    return deduped, removed


def main() -> int:
    print("Deduplicating annotation spans...")

    total_records = 0
    total_spans_before = 0
    total_spans_after = 0
    total_removed = 0
    records_with_dups = 0

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    with open(INPUT) as fin, open(OUTPUT, "w") as fout:
        for line in fin:
            if not line.strip():
                continue
            record = json.loads(line)
            total_records += 1
            spans_before = len(record.get("spans", []))
            total_spans_before += spans_before

            deduped, removed = deduplicate_spans(record.get("spans", []))
            if removed > 0:
                records_with_dups += 1
            record["spans"] = deduped
            record["document"]["span_count"] = len(deduped)
            record["dedup_applied"] = removed > 0
            record["dedup_removed_count"] = removed

            total_spans_after += len(deduped)
            total_removed += removed
            fout.write(json.dumps(record, ensure_ascii=False) + "\n")

    report = {
        "total_records": total_records,
        "records_with_duplicates": records_with_dups,
        "pct_records_with_dups": round(records_with_dups / total_records * 100, 2),
        "total_spans_before": total_spans_before,
        "total_spans_after": total_spans_after,
        "total_removed": total_removed,
        "pct_spans_removed": round(total_removed / total_spans_before * 100, 2) if total_spans_before else 0,
        "output": str(OUTPUT),
    }

    REPORT.write_text(json.dumps(report, indent=2))
    print(f"Records: {total_records}")
    print(f"Records with duplicates: {records_with_dups} ({report['pct_records_with_dups']}%)")
    print(f"Spans before: {total_spans_before}")
    print(f"Spans after: {total_spans_after}")
    print(f"Removed: {total_removed} ({report['pct_spans_removed']}%)")
    print(f"Output: {OUTPUT}")
    print(f"Report: {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
