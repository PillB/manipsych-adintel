#!/usr/bin/env python3
"""Ingest public candidate URLs into the Phase 4 source log.

Input can be plain text, copied search results, or saved HTML. The tool extracts
URLs and records only public candidate source leads. It does not fetch pages.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG = ROOT / "reports" / "phase4_search_log.json"

TARGET_HOST_HINTS = (
    "locanto.com.pe",
    "doplim.com.pe",
    "clasf.pe",
    "evisos.com.pe",
    "anuto.com.pe",
    "facebook.com",
)

TARGET_TERM_HINTS = (
    "ayuda",
    "apoyo",
    "econom",
)


def extract_urls(text: str) -> list[str]:
    urls = re.findall(r"https?://[^\s\"'<>]+", text)
    cleaned = []
    for url in urls:
        cleaned.append(url.rstrip(").,;]"))
    return sorted(set(cleaned))


def is_candidate(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    haystack = url.lower()
    return any(host_hint in host for host_hint in TARGET_HOST_HINTS) and any(term in haystack for term in TARGET_TERM_HINTS)


def load_log(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"phase": 4, "attempts": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save_log(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_candidates(log_path: Path, candidates: list[str], label: str) -> int:
    data = load_log(log_path)
    attempts = list(data.get("attempts", []))
    existing = {attempt.get("query") for attempt in attempts if isinstance(attempt, dict)}
    added = 0
    for url in candidates:
        query = f"candidate_url {url}"
        if query in existing:
            continue
        attempts.append(
            {
                "query": query,
                "result_count": 1,
                "notes": f"Candidate URL extracted from {label}; not fetched or validated yet."
            }
        )
        added += 1
    data["attempts"] = attempts
    save_log(log_path, data)
    return added


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path, help="Text/HTML file. Reads stdin when omitted.")
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--all", action="store_true", help="Keep all URLs instead of only likely target candidate URLs.")
    args = parser.parse_args()

    text = args.input.read_text(encoding="utf-8") if args.input else sys.stdin.read()
    urls = extract_urls(text)
    candidates = urls if args.all else [url for url in urls if is_candidate(url)]
    added = append_candidates(args.log, candidates, str(args.input or "stdin"))
    print(json.dumps({"urls_found": len(urls), "candidates": candidates, "added": added}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
