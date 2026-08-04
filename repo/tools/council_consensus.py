#!/usr/bin/env python3
"""Evaluate 3-subagent council agreement and queue second-pass rounds."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data/annotation/annotations.sqlite3"
COUNCIL_SIZE = 3
THRESHOLD = 0.90


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def digest(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def actor_for_round(round_number: int, slot: int) -> str:
    suffix = chr(ord("a") + slot)
    if round_number == 1:
        return f"subagent_{suffix}"
    return f"subagent_r{round_number}_{suffix}"


SIGNATURE_DOCUMENT_FIELDS = {
    "persuasive_intensity",
    "manipulativeness",
    "harm_risk",
    "explicitness",
    "labels",
    "span_count",
    "negative_example",
}

SIGNATURE_SPAN_FIELDS = {
    "label",
    "segments",
    "exact_text",
    "intensity",
    "manipulativeness",
    "harm_risk",
    "explicitness",
    "vulnerability_target",
}


def normalize_document(document_json: str) -> dict:
    document = json.loads(document_json or "{}")
    return {key: document[key] for key in sorted(SIGNATURE_DOCUMENT_FIELDS) if key in document}


def normalize_span(span: dict) -> dict:
    return {key: span[key] for key in sorted(SIGNATURE_SPAN_FIELDS) if key in span}


def _span_rows(db: sqlite3.Connection, annotation_set_id: int) -> list[dict]:
    rows = db.execute(
        """SELECT label,segments_json,exact_text,rationale,intensity,manipulativeness,
                  harm_risk,explicitness,vulnerability_target
           FROM spans WHERE annotation_set_id=? ORDER BY label,segments_json,exact_text""",
        (annotation_set_id,),
    ).fetchall()
    spans = []
    for row in rows:
        item = dict(row)
        item["segments"] = json.loads(item.pop("segments_json"))
        spans.append(normalize_span(item))
    return spans


def annotation_signature(db: sqlite3.Connection, annotation_set_id: int, document_json: str) -> str:
    """Hash the exact normalized annotation payload for agreement checks."""
    payload = {
        "document": normalize_document(document_json),
        "spans": _span_rows(db, annotation_set_id),
    }
    return digest(payload)


def load_submitted_signatures(db: sqlite3.Connection, round_number: int) -> dict[str, dict[str, str]]:
    """Load all submitted subagent signatures for a round without N+1 queries."""
    set_rows = db.execute(
        """SELECT id,record_id,actor_id,document_json FROM annotation_sets
           WHERE layer='subagent' AND state='submitted' AND round=?
           ORDER BY record_id,actor_id""",
        (round_number,),
    ).fetchall()
    if not set_rows:
        return {}
    set_by_id = {int(row["id"]): row for row in set_rows}
    spans_by_set: dict[int, list[dict]] = defaultdict(list)
    for row in db.execute(
        """SELECT s.annotation_set_id,s.label,s.segments_json,s.exact_text,s.rationale,s.intensity,
                  s.manipulativeness,s.harm_risk,s.explicitness,s.vulnerability_target
           FROM spans s
           JOIN annotation_sets a ON a.id=s.annotation_set_id
          WHERE a.layer='subagent' AND a.state='submitted' AND a.round=?
          ORDER BY s.annotation_set_id,s.label,s.segments_json,s.exact_text""",
        (round_number,),
    ):
        item = dict(row)
        set_id = int(item.pop("annotation_set_id"))
        item["segments"] = json.loads(item.pop("segments_json"))
        spans_by_set[set_id].append(normalize_span(item))
    result: dict[str, dict[str, str]] = defaultdict(dict)
    for set_id, row in set_by_id.items():
        payload = {
            "document": normalize_document(row["document_json"]),
            "spans": spans_by_set.get(set_id, []),
        }
        result[row["record_id"]][row["actor_id"]] = digest(payload)
    return result


def ensure_next_round_assignments(db: sqlite3.Connection, record_id: str, next_round: int) -> None:
    for slot in range(COUNCIL_SIZE):
        db.execute(
            """INSERT OR IGNORE INTO assignments(record_id,reviewer_id,role,round,status)
               VALUES (?,?,?,?, 'pending')""",
            (record_id, actor_for_round(next_round, slot), "subagent", next_round),
        )


def evaluate(database: Path, round_number: int = 1, create_next_round: bool = False) -> dict:
    db = sqlite3.connect(database, timeout=60)
    db.row_factory = sqlite3.Row
    decisions = Counter()
    records = [
        row["record_id"]
        for row in db.execute(
            """SELECT DISTINCT record_id FROM assignments
               WHERE role='subagent' AND round=? ORDER BY record_id""",
            (round_number,),
        )
    ]
    if not records:
        records = [row["record_id"] for row in db.execute("SELECT record_id FROM documents ORDER BY record_id")]
    submitted_signatures = load_submitted_signatures(db, round_number)
    now = utc_now()
    with db:
        db.execute(
            """DELETE FROM council_consensus
               WHERE round=?
                 AND NOT EXISTS (
                   SELECT 1 FROM assignments a
                   WHERE a.record_id=council_consensus.record_id
                     AND a.role='subagent'
                     AND a.round=council_consensus.round
                 )""",
            (round_number,),
        )
        for record_id in records:
            signatures_by_actor = submitted_signatures.get(record_id, {})
            submitted_count = len(signatures_by_actor)
            signature_counts = Counter(signatures_by_actor.values())
            consensus_signature, votes = (None, 0)
            if signature_counts:
                consensus_signature, votes = signature_counts.most_common(1)[0]
            agreement = votes / COUNCIL_SIZE
            if submitted_count < COUNCIL_SIZE:
                decision = "pending"
            elif agreement >= THRESHOLD:
                decision = "accepted"
                if create_next_round:
                    db.execute(
                        """DELETE FROM assignments
                           WHERE record_id=? AND role='subagent' AND round=?
                             AND status='pending'
                             AND NOT EXISTS (
                               SELECT 1 FROM annotation_sets s
                               WHERE s.record_id=assignments.record_id
                                 AND s.actor_id=assignments.reviewer_id
                                 AND s.layer='subagent'
                                 AND s.round=assignments.round
                             )""",
                        (record_id, round_number + 1),
                    )
            else:
                decision = "second_pass"
                if create_next_round:
                    ensure_next_round_assignments(db, record_id, round_number + 1)
            accepted_actor_id = None
            if consensus_signature:
                accepted_actor_id = next(
                    actor for actor, signature in sorted(signatures_by_actor.items()) if signature == consensus_signature
                )
            db.execute(
                """INSERT INTO council_consensus
                   (record_id,round,council_size,submitted_count,agreement,decision,
                    consensus_signature,accepted_actor_id,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(record_id,round) DO UPDATE SET
                     council_size=excluded.council_size,
                     submitted_count=excluded.submitted_count,
                     agreement=excluded.agreement,
                     decision=excluded.decision,
                     consensus_signature=excluded.consensus_signature,
                     accepted_actor_id=excluded.accepted_actor_id,
                     updated_at=excluded.updated_at""",
                (
                    record_id,
                    round_number,
                    COUNCIL_SIZE,
                    submitted_count,
                    agreement,
                    decision,
                    consensus_signature,
                    accepted_actor_id,
                    now,
                ),
            )
            decisions[decision] += 1
    db.close()
    return {
        "round": round_number,
        "council_size": COUNCIL_SIZE,
        "agreement_threshold": THRESHOLD,
        "records": len(records),
        "decisions": dict(sorted(decisions.items())),
        "next_round_created": bool(create_next_round),
    }


def export_queue(database: Path, output: Path, round_number: int = 1) -> int:
    db = sqlite3.connect(database, timeout=60)
    db.row_factory = sqlite3.Row
    rows = db.execute(
        """SELECT d.record_id,d.platform,d.split_name,d.batch_id,d.context_json,
                  c.round,c.submitted_count,c.agreement,c.decision
           FROM council_consensus c JOIN documents d ON d.record_id=c.record_id
           WHERE c.round=? AND c.decision IN ('pending','second_pass')
           ORDER BY c.decision,d.platform,d.record_id""",
        (round_number,),
    ).fetchall()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for row in rows:
            item = dict(row)
            item["context"] = json.loads(item.pop("context_json"))
            handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
    db.close()
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DB)
    parser.add_argument("--round", type=int, default=1)
    parser.add_argument("--create-next-round", action="store_true")
    parser.add_argument("--queue-output", type=Path, default=ROOT / "data/annotation/council_second_pass_queue.jsonl")
    args = parser.parse_args()
    result = evaluate(args.database, args.round, args.create_next_round)
    queued = export_queue(args.database, args.queue_output, args.round)
    result["queue_records"] = queued
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
