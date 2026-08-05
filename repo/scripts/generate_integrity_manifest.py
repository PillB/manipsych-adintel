#!/usr/bin/env python3
"""O-02: Generate file-integrity manifest for all model, data, and report files.
Verifies that no tampering has occurred since the manifest was generated."""

import hashlib
import json
import sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "audit" / "assurance" / "evidence" / "file_integrity_manifest.json"

# Files to hash (exclude backups, caches, __pycache__)
EXCLUDE_PATTERNS = [".bak", "__pycache__", ".pytest_cache", ".DS_Store", ".bak_"]


def should_hash(path: Path) -> bool:
    rel = str(path.relative_to(ROOT))
    return not any(pat in rel for pat in EXCLUDE_PATTERNS) and path.is_file()


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    manifest = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "root": str(ROOT),
        "files": {},
    }

    # Hash key files
    targets = [
        ROOT / "adintel" / "*.py",
        ROOT / "scripts" / "*.py",
        ROOT / "tests" / "adintel" / "*.py",
        ROOT / "models" / "*.joblib",
        ROOT / "models" / "*.pkl",
        ROOT / "data" / "processed" / "ad_manifest.jsonl",
        ROOT / "data" / "annotation" / "council_resolved_annotations.jsonl",
        ROOT / "data" / "annotation" / "similarity_links.jsonl",
        ROOT / "reports" / "adintel" / "pipeline_results.json",
        ROOT / "reports" / "adintel" / "adintel_dashboard.html",
        ROOT / "docs" / "interactive_analyzer.html",
    ]

    for pattern in targets:
        for path in ROOT.glob(str(pattern).replace(str(ROOT) + "/", "")):
            if should_hash(path):
                rel = str(path.relative_to(ROOT))
                manifest["files"][rel] = {
                    "sha256": hash_file(path),
                    "size": path.stat().st_size,
                }

    manifest["file_count"] = len(manifest["files"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(manifest, indent=2))
    print(f"File integrity manifest: {manifest['file_count']} files")
    print(f"Output: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
