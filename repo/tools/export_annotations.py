#!/usr/bin/env python3
"""Deterministically export annotation layers without collapsing provenance."""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def export(database: Path, output: Path) -> int:
    db = sqlite3.connect(database)
    db.row_factory = sqlite3.Row
    sets = db.execute(
        """SELECT a.*,d.corpus_version,d.platform,d.split_name,d.campaign_group
           FROM annotation_sets a JOIN documents d ON d.record_id=a.record_id
           ORDER BY a.record_id,a.round,a.layer,a.actor_id"""
    ).fetchall()
    spans_by_set: dict[int, list[dict]] = defaultdict(list)
    for span in db.execute(
        """SELECT annotation_set_id,label,segments_json,exact_text,rationale,intensity,manipulativeness,
                  harm_risk,explicitness,vulnerability_target,provenance
             FROM spans
            ORDER BY annotation_set_id,id"""
    ):
        item = dict(span)
        set_id = int(item.pop("annotation_set_id"))
        item["segments"] = json.loads(item.pop("segments_json"))
        spans_by_set[set_id].append(item)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for item in sets:
            row = dict(item)
            row["document"] = json.loads(row.pop("document_json"))
            row["spans"] = spans_by_set.get(int(row.pop("id")), [])
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    db.close()
    return len(sets)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=ROOT / "data/annotation/annotations.sqlite3")
    parser.add_argument("--output", type=Path, default=ROOT / "data/annotation/annotations_export.jsonl")
    args = parser.parse_args()
    print(f"exported {export(args.database, args.output)} annotation sets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
