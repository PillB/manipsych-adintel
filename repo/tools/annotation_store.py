#!/usr/bin/env python3
"""Transactional operations for the local annotation SQLite store."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

LAYERS = {"human", "subagent", "adjudicated"}
STATES = {"draft", "submitted", "adjudicated"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _validate_segments(text: str, span: dict) -> tuple[str, str]:
    segments = span.get("segments")
    if not isinstance(segments, list) or not segments:
        raise ValueError("each span requires one or more segments")
    pieces = []
    previous_end = -1
    normalized = []
    for segment in segments:
        if not isinstance(segment, list) or len(segment) != 2:
            raise ValueError("segments must be [start, end] pairs")
        start, end = segment
        if not (isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(text)):
            raise ValueError("span bounds are invalid")
        if start < previous_end:
            raise ValueError("segments must be ordered and non-overlapping")
        normalized.append([start, end])
        pieces.append(text[start:end])
        previous_end = end
    exact = " … ".join(pieces)
    if span.get("exact_text") != exact:
        raise ValueError("exact_text does not match immutable text offsets")
    return json.dumps(normalized, separators=(",", ":")), exact


def save_annotation(
    database: Path,
    record_id: str,
    actor_id: str,
    layer: str,
    state: str,
    spans: list[dict],
    document: dict | None = None,
    round: int = 1,
) -> int:
    if layer not in LAYERS or state not in STATES:
        raise ValueError("invalid layer or state")
    if not isinstance(round, int) or round < 1:
        raise ValueError("round must be a positive integer")
    if layer == "adjudicated" and state != "adjudicated":
        raise ValueError("adjudicated layer requires adjudicated state")
    if layer != "adjudicated" and state == "adjudicated":
        raise ValueError("only the adjudicated layer may use adjudicated state")
    db = sqlite3.connect(database)
    db.row_factory = sqlite3.Row
    try:
        doc = db.execute("SELECT * FROM documents WHERE record_id=?", (record_id,)).fetchone()
        if not doc:
            raise ValueError("unknown record_id")
        role = "adjudicator" if layer == "adjudicated" else layer
        assignment = db.execute(
            "SELECT 1 FROM assignments WHERE record_id=? AND reviewer_id=? AND role=? AND round=?",
            (record_id, actor_id, role, round),
        ).fetchone()
        if not assignment and layer != "adjudicated":
            raise ValueError("actor is not assigned to this record and layer")
        current = db.execute(
            "SELECT id,state FROM annotation_sets WHERE record_id=? AND actor_id=? AND layer=? AND round=?",
            (record_id, actor_id, layer, round),
        ).fetchone()
        if current and current["state"] in {"submitted", "adjudicated"}:
            raise ValueError("submitted and adjudicated annotation sets are immutable")
        validated = []
        for span in spans:
            segments_json, exact = _validate_segments(doc["text"], span)
            if not str(span.get("label") or "").strip():
                raise ValueError("span label is required")
            validated.append((span, segments_json, exact))
        now = utc_now()
        payload = json.dumps(document or {}, ensure_ascii=False, sort_keys=True)
        with db:
            if current:
                set_id = int(current["id"])
                db.execute(
                    "UPDATE annotation_sets SET state=?,document_json=?,updated_at=? WHERE id=?",
                    (state, payload, now, set_id),
                )
                db.execute("DELETE FROM spans WHERE annotation_set_id=?", (set_id,))
            else:
                cursor = db.execute(
                    """INSERT INTO annotation_sets
                       (record_id,actor_id,layer,state,round,text_hash,document_json,created_at,updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (record_id, actor_id, layer, state, round, doc["text_hash"], payload, now, now),
                )
                set_id = int(cursor.lastrowid)
            for span, segments_json, exact in validated:
                db.execute(
                    """INSERT INTO spans
                       (annotation_set_id,label,segments_json,exact_text,rationale,intensity,
                        manipulativeness,harm_risk,explicitness,vulnerability_target,provenance)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        set_id, span["label"], segments_json, exact, span.get("rationale", ""),
                        span.get("intensity"), span.get("manipulativeness"), span.get("harm_risk"),
                        span.get("explicitness"), span.get("vulnerability_target"), actor_id,
                    ),
                )
            if state in {"submitted", "adjudicated"}:
                db.execute(
                    "UPDATE assignments SET status='submitted' WHERE record_id=? AND reviewer_id=? AND role=? AND round=?",
                    (record_id, actor_id, role, round),
                )
        return set_id
    finally:
        db.close()


def visible_annotations(database: Path, record_id: str, actor_id: str, round: int = 1) -> list[dict]:
    """Hide all other layers until this human reviewer has submitted."""
    db = sqlite3.connect(database)
    db.row_factory = sqlite3.Row
    own = db.execute(
        "SELECT state FROM annotation_sets WHERE record_id=? AND actor_id=? AND layer='human' AND round=?",
        (record_id, actor_id, round),
    ).fetchone()
    if not own or own["state"] != "submitted":
        predicate, params = "a.record_id=? AND a.actor_id=? AND a.round=?", (record_id, actor_id, round)
    else:
        predicate, params = "a.record_id=? AND a.round=?", (record_id, round)
    rows = db.execute(
        f"""SELECT a.id,a.actor_id,a.layer,a.state,a.round,a.document_json,s.label,s.segments_json,
                   s.exact_text,s.rationale,s.intensity,s.manipulativeness,s.harm_risk,
                   s.explicitness,s.vulnerability_target
            FROM annotation_sets a LEFT JOIN spans s ON s.annotation_set_id=a.id
            WHERE {predicate} ORDER BY a.layer,a.actor_id,s.id""",
        params,
    ).fetchall()
    db.close()
    return [dict(row) for row in rows]


def progress(database: Path) -> list[dict]:
    db = sqlite3.connect(database)
    db.row_factory = sqlite3.Row
    rows = db.execute(
        """SELECT role,status,COUNT(*) AS count FROM assignments
           GROUP BY role,status ORDER BY role,status"""
    ).fetchall()
    db.close()
    return [dict(row) for row in rows]
