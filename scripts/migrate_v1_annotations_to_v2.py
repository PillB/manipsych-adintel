#!/usr/bin/env python3
"""Migrate v1 annotations to v2 using adintel.taxonomy.v1_to_v2.

Reads data/annotation/council_resolved_annotations.jsonl (v1 labels) and
writes data/annotation/council_resolved_annotations_v2.jsonl (v2 labels).

The migration is non-destructive: every v1 span is preserved with its original
label, and a new `v2_labels` field is added with the projected v2 leaves.
One v1 label may project to multiple v2 leaves (e.g. `reciprocity_obligation`
-> `cc_reciprocity_frame` + `bs_reciprocity_obligation`).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path("/home/z/my-project/repo")
sys.path.insert(0, str(REPO))

from adintel import taxonomy as tx


INPUT = REPO / "data" / "annotation" / "council_resolved_annotations.jsonl"
OUTPUT = REPO / "data" / "annotation" / "council_resolved_annotations_v2.jsonl"
REPORT = REPO / "reports" / "adintel" / "v1_to_v2_migration_report.json"


def main() -> int:
    if not INPUT.exists():
        print(f"ERROR: {INPUT} not found")
        return 1

    n_in = 0
    n_out = 0
    unmapped_set: set[str] = set()
    projection_counts: dict[str, int] = {}
    n_multi_projection = 0

    with open(INPUT, "r", encoding="utf-8") as fin, open(OUTPUT, "w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            n_in += 1
            spans = rec.get("spans", [])
            for s in spans:
                v1 = s.get("label")
                if not v1:
                    continue
                v2_leaves = tx.v1_to_v2(v1)
                if not v2_leaves:
                    unmapped_set.add(v1)
                    continue
                if len(v2_leaves) > 1:
                    n_multi_projection += 1
                s["v1_label"] = v1
                s["v2_labels"] = v2_leaves
                projection_counts[v1] = projection_counts.get(v1, 0) + 1
            rec["taxonomy_version"] = "adintel-taxonomy-v2"
            rec["migration_notes"] = "v1 labels preserved as v1_label; v2 leaves projected to v2_labels; multi-label projections are expected (one v1 label may map to multiple v2 leaves)."
            fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n_out += 1

    report = {
        "input_records": n_in,
        "output_records": n_out,
        "unmapped_v1_labels": sorted(unmapped_set),
        "n_multi_label_projections": n_multi_projection,
        "projection_counts_by_v1_label": projection_counts,
        "v2_taxonomy_version": tx.TAXONOMY_VERSION,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(f"Migration complete: {n_in} -> {n_out} records")
    print(f"  unmapped v1 labels: {len(unmapped_set)}")
    print(f"  multi-label projections: {n_multi_projection}")
    print(f"  report: {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
