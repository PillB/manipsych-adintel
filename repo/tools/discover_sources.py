#!/usr/bin/env python3
"""Run public search discovery queries and append Phase 4 attempt evidence."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote, unquote, urlparse, parse_qs

import requests


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.ingest_candidate_urls import append_candidates, extract_urls, is_candidate


DEFAULT_LOG = ROOT / "reports" / "phase4_search_log.json"


DEFAULT_QUERIES = [
    '"ayuda economica" "locanto.com.pe/lima/ID_"',
    '"ayuda económica" "locanto.com.pe/lima/ID_"',
    '"apoyo economico" "locanto.com.pe/lima/ID_"',
    '"apoyo económico" "locanto.com.pe/lima/ID_"',
    '"ayuda economica" "doplim.com.pe" "Lima"',
    '"apoyo economico" "doplim.com.pe" "Lima"',
    '"ayuda economica" "clasf.pe" "Lima"',
    '"apoyo economico" "clasf.pe" "Lima"',
    '"ayuda economica" "evisos.com.pe" "Lima"',
    '"apoyo economico" "evisos.com.pe" "Lima"',
]


def duckduckgo_html(query: str) -> str:
    url = "https://duckduckgo.com/html/?q=" + quote(query)
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=25)
    response.raise_for_status()
    return response.text


def extract_ddg_result_urls(page_html: str) -> list[str]:
    urls = extract_urls(page_html)
    output: list[str] = []
    for url in urls:
        if "w3.org/TR" in url:
            continue
        parsed = urlparse(url)
        if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
            target = parse_qs(parsed.query).get("uddg", [""])[0]
            if target:
                output.append(unquote(target))
        elif "duckduckgo.com" not in parsed.netloc:
            output.append(url)
    return sorted(set(output))


def is_soft_challenge(page_html: str) -> bool:
    lowered = page_html.lower()
    return "anomaly" in lowered or "captcha" in lowered or "vqd=" in lowered and "result__a" not in lowered


def load_log(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"phase": 4, "attempts": []}


def save_log(path: Path, data: dict[str, object]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_attempt(log_path: Path, query: str, status: int, urls: list[str], notes: str) -> None:
    data = load_log(log_path)
    attempts = list(data.get("attempts", []))
    attempts.append(
        {
            "query": f"duckduckgo_html {query}",
            "result_count": len(urls),
            "notes": f"HTTP {status}. {notes}"
        }
    )
    data["attempts"] = attempts
    save_log(log_path, data)


def run_query(query: str, log_path: Path) -> dict[str, object]:
    url = "https://duckduckgo.com/html/?q=" + quote(query)
    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=25)
        urls = extract_ddg_result_urls(response.text)
        candidates = [url for url in urls if is_candidate(url)]
        notes = "soft challenge or no result anchors" if is_soft_challenge(response.text) else "parsed search response"
        append_attempt(log_path, query, response.status_code, candidates, notes)
        append_candidates(log_path, candidates, f"duckduckgo query: {query}")
        return {"query": query, "status": response.status_code, "urls": urls, "candidates": candidates, "notes": notes}
    except Exception as exc:  # noqa: BLE001
        append_attempt(log_path, query, 0, [], f"{type(exc).__name__}: {exc}")
        return {"query": query, "status": 0, "urls": [], "candidates": [], "notes": f"{type(exc).__name__}: {exc}"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", action="append", help="Query to run. May be provided multiple times.")
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    args = parser.parse_args()

    queries = args.query or DEFAULT_QUERIES
    results = [run_query(query, args.log) for query in queries]
    print(json.dumps({"results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
