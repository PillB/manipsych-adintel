#!/usr/bin/env python3
"""Reapply current redaction rules to processed JSONL records."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.redact_pii import redact_text


def scrub_manifest(path: Path) -> int:
    records = []
    changed = 0
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            for field in ("title", "body_redacted"):
                original = record.get(field, "")
                redacted = redact_text(original)
                if redacted != original:
                    changed += 1
                    record[field] = redacted
            metadata = record.get("metadata")
            if isinstance(metadata, dict) and isinstance(metadata.get("seed_text"), str):
                original = metadata["seed_text"]
                redacted = redact_text(original)
                if redacted != original:
                    changed += 1
                    metadata["seed_text"] = redacted
            if isinstance(metadata, dict) and isinstance(metadata.get("original_url"), str):
                original = metadata["original_url"]
                redacted = redact_text(original)
                if redacted != original:
                    changed += 1
                    metadata["original_url"] = redacted
            records.append(record)
    path.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records), encoding="utf-8")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", nargs="?", type=Path, default=ROOT / "data" / "processed" / "ad_manifest.jsonl")
    args = parser.parse_args()
    changed = scrub_manifest(args.manifest)
    print(json.dumps({"manifest": str(args.manifest), "records_changed": changed}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
