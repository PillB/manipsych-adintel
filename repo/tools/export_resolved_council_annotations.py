#!/usr/bin/env python3
"""Export one resolved accepted council suggestion set per document."""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data/annotation/annotations.sqlite3"
DEFAULT_OUTPUT = ROOT / "data/annotation/council_resolved_annotations.jsonl"


def export_resolved(database: Path, output: Path) -> dict:
    db = sqlite3.connect(database)
    db.row_factory = sqlite3.Row
    rows = db.execute(
        """WITH accepted AS (
             SELECT record_id, MAX(round) AS accepted_round
               FROM council_consensus
              WHERE decision='accepted'
              GROUP BY record_id
           )
           SELECT d.record_id,d.corpus_version,d.platform,d.split_name,d.text_hash,
                  c.round AS accepted_round,c.agreement,c.accepted_actor_id,
                  a.id AS annotation_set_id,a.document_json
             FROM accepted x
             JOIN council_consensus c
               ON c.record_id=x.record_id AND c.round=x.accepted_round
             JOIN documents d ON d.record_id=x.record_id
             JOIN annotation_sets a
               ON a.record_id=c.record_id
              AND a.actor_id=c.accepted_actor_id
              AND a.layer='subagent'
              AND a.state='submitted'
              AND a.round=c.round
            ORDER BY d.record_id"""
    ).fetchall()
    output.parent.mkdir(parents=True, exist_ok=True)
    spans_by_set: dict[int, list[dict]] = defaultdict(list)
    for span in db.execute(
        """WITH accepted AS (
             SELECT record_id, MAX(round) AS accepted_round
               FROM council_consensus
              WHERE decision='accepted'
              GROUP BY record_id
           )
           SELECT s.annotation_set_id,s.label,s.segments_json,s.exact_text,s.rationale,s.intensity,
                  s.manipulativeness,s.harm_risk,s.explicitness,s.vulnerability_target,s.provenance
             FROM accepted x
             JOIN council_consensus c
               ON c.record_id=x.record_id AND c.round=x.accepted_round
             JOIN annotation_sets a
               ON a.record_id=c.record_id
              AND a.actor_id=c.accepted_actor_id
              AND a.layer='subagent'
              AND a.state='submitted'
              AND a.round=c.round
             JOIN spans s ON s.annotation_set_id=a.id
            ORDER BY s.annotation_set_id,s.label,s.segments_json,s.exact_text"""
    ):
        item = dict(span)
        set_id = int(item.pop("annotation_set_id"))
        item["segments"] = json.loads(item.pop("segments_json"))
        spans_by_set[set_id].append(item)
    span_total = 0
    with output.open("w", encoding="utf-8") as handle:
        for row in rows:
            spans = spans_by_set.get(int(row["annotation_set_id"]), [])
            span_total += len(spans)
            payload = {
                "record_id": row["record_id"],
                "corpus_version": row["corpus_version"],
                "platform": row["platform"],
                "split_name": row["split_name"],
                "text_hash": row["text_hash"],
                "layer": "subagent",
                "gold": False,
                "accepted_round": row["accepted_round"],
                "agreement": row["agreement"],
                "accepted_actor_id": row["accepted_actor_id"],
                "document": json.loads(row["document_json"] or "{}"),
                "spans": spans,
            }
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    total_documents = db.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    db.close()
    return {
        "documents": int(total_documents),
        "resolved": len(rows),
        "spans": span_total,
        "output": str(output),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(json.dumps(export_resolved(args.database, args.output), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
