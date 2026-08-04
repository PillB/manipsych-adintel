#!/usr/bin/env python3
"""Build search-engine query variants from the current public ad corpus."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


DEFAULT_MANIFEST = ROOT / "data" / "processed" / "ad_manifest.jsonl"
DEFAULT_OUTPUT = ROOT / "data" / "sources" / "query_bank.json"

CITY_TERMS = ["lima", "arequipa", "trujillo", "cusco", "piura", "chiclayo", "huancayo", "callao", "ica", "tacna"]
PLATFORM_SITE = {
    "locanto": "site:locanto.com.pe",
    "doplim": "site:doplim.com.pe OR site:doplim.pe",
    "facebook": "site:facebook.com/groups OR site:facebook.com",
}

STOPWORDS = {
    "de", "la", "el", "y", "o", "a", "en", "para", "con", "por", "del", "al", "las", "los",
    "un", "una", "que", "mi", "tu", "su", "se", "so", "soy", "hola", "busco", "brindo", "doy",
    "ofrezco", "ofresco", "ayuda", "economica", "económica", "apoyo", "económico", "economico",
}


def load_titles(path: Path) -> list[str]:
    titles: list[str] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            rec = json.loads(line)
            title = str(rec.get("title", "")).strip()
            if title:
                titles.append(title)
    return titles


def normalize_phrase(title: str) -> str:
    title = re.sub(r"\[[^\]]+\]", " ", title)
    title = re.sub(r"\b\d{2,}\b", " ", title)
    title = re.sub(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9 ]+", " ", title)
    parts = [p.lower() for p in title.split()]
    kept = [p for p in parts if p not in STOPWORDS and len(p) > 2]
    return " ".join(kept[:6]).strip()


def top_phrases(titles: list[str], limit: int) -> list[str]:
    counter: Counter[str] = Counter()
    for title in titles:
        phrase = normalize_phrase(title)
        if phrase:
            counter[phrase] += 1
    common = [phrase for phrase, _ in counter.most_common(limit)]
    return common


def build_queries(platform: str, titles: list[str], per_platform_limit: int) -> list[str]:
    site_clause = PLATFORM_SITE[platform]
    phrases = top_phrases(titles, per_platform_limit)
    queries: list[str] = []
    for city in CITY_TERMS:
        queries.append(f'{site_clause} ("ayuda economica" OR "apoyo economico" OR "brindo ayuda" OR "doy ayuda") {city} "ID_"')
    for phrase in phrases:
        queries.append(f'{site_clause} "{phrase}" "ID_"')
        for city in CITY_TERMS[:5]:
            queries.append(f'{site_clause} "{phrase}" {city}')
    # Keep order stable and deduped
    seen: set[str] = set()
    deduped: list[str] = []
    for query in queries:
        if query not in seen:
            seen.add(query)
            deduped.append(query)
    return deduped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args()

    titles = load_titles(args.manifest)
    bank = {
        platform: build_queries(platform, titles, args.limit)
        for platform in ("locanto", "doplim", "facebook")
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(bank, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({platform: len(queries) for platform, queries in bank.items()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
