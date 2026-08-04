#!/usr/bin/env python3
"""Export pending council-review packets with text, context, and label schema."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data/annotation/annotations.sqlite3"
DEFAULT_SCHEMA = ROOT / "data/annotation/label_schema.json"
DEFAULT_OUTPUT = ROOT / "data/annotation/council_packets.jsonl"


def export_packets(
    database: Path,
    schema_path: Path,
    output: Path,
    reviewer_id: str | None = None,
    round_number: int = 1,
    limit: int | None = None,
) -> int:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    db = sqlite3.connect(database)
    db.row_factory = sqlite3.Row
    params: list[object] = [round_number]
    reviewer_clause = ""
    if reviewer_id:
        reviewer_clause = "AND a.reviewer_id=?"
        params.append(reviewer_id)
    limit_clause = ""
    if limit:
        limit_clause = "LIMIT ?"
        params.append(limit)
    rows = db.execute(
        f"""SELECT a.record_id,a.reviewer_id,a.round,d.corpus_version,d.platform,d.split_name,
                   d.batch_id,d.text,d.text_hash,d.context_json
            FROM assignments a JOIN documents d ON d.record_id=a.record_id
            LEFT JOIN annotation_sets s
              ON s.record_id=a.record_id
             AND s.actor_id=a.reviewer_id
             AND s.layer='subagent'
             AND s.round=a.round
            WHERE a.role='subagent'
              AND a.status='pending'
              AND a.round=?
              AND s.id IS NULL
              {reviewer_clause}
            ORDER BY d.batch_id,d.platform,a.record_id,a.reviewer_id
            {limit_clause}""",
        params,
    ).fetchall()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for row in rows:
            text = row["text"]
            title, _, body = text.partition("\n")
            packet = {
                "record_id": row["record_id"],
                "reviewer_id": row["reviewer_id"],
                "round": row["round"],
                "corpus_version": row["corpus_version"],
                "platform": row["platform"],
                "split_name": row["split_name"],
                "batch_id": row["batch_id"],
                "text_hash": row["text_hash"],
                "title": title,
                "body": body,
                "text": text,
                "context": json.loads(row["context_json"]),
                "label_schema": schema,
                "instructions": {
                    "task": "Review Spanish ad title, body, available image metadata, and context signals.",
                    "output_layer": "subagent",
                    "offsets": "Use zero-based, end-exclusive Unicode-code-point offsets into packet.text.",
                    "negative_examples": "Submit an empty spans list when no persuasive/manipulative span is present.",
                    "provenance": "Save with tools.annotation_store.save_annotation using this reviewer_id and round.",
                    "consensus_rule": "Council passes only when 3/3 reviewers produce the same normalized annotation payload.",
                },
            }
            handle.write(json.dumps(packet, ensure_ascii=False, sort_keys=True) + "\n")
    db.close()
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DB)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--reviewer-id")
    parser.add_argument("--round", type=int, default=1)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    count = export_packets(args.database, args.schema, args.output, args.reviewer_id, args.round, args.limit)
    print(json.dumps({"packets": count, "output": str(args.output)}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
