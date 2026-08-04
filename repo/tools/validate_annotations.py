#!/usr/bin/env python3
"""Validate immutable text hashes and standoff span substrings in an annotation DB."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def validate(path: Path) -> list[str]:
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    errors: list[str] = []
    for row in db.execute("SELECT * FROM documents"):
        actual = hashlib.sha256(row["text"].encode("utf-8")).hexdigest()
        if actual != row["text_hash"]:
            errors.append(f"{row['record_id']}: document text hash mismatch")
    query = """
      SELECT s.id, s.segments_json, s.exact_text, a.record_id,
             a.text_hash AS annotation_text_hash, d.text, d.text_hash AS document_text_hash
      FROM spans s JOIN annotation_sets a ON a.id=s.annotation_set_id
      JOIN documents d ON d.record_id=a.record_id
    """
    for row in db.execute(query):
        if row["annotation_text_hash"] != row["document_text_hash"]:
            errors.append(f"span {row['id']}: annotation text hash mismatch")
            continue
        try:
            segments = json.loads(row["segments_json"])
            pieces = []
            previous_end = -1
            for start, end in segments:
                if not (isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(row["text"])):
                    raise ValueError("invalid bounds")
                if start < previous_end:
                    raise ValueError("segments overlap or are unordered")
                pieces.append(row["text"][start:end])
                previous_end = end
            if " … ".join(pieces) != row["exact_text"]:
                raise ValueError("exact_text mismatch")
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"span {row['id']}: {exc}")
    db.close()
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", nargs="?", type=Path, default=ROOT / "data/annotation/annotations.sqlite3")
    args = parser.parse_args()
    errors = validate(args.database)
    if errors:
        print("\n".join(errors))
        return 1
    print("annotation validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
