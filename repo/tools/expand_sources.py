#!/usr/bin/env python3
"""Generate public classified-source URL candidates for Phase 4."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "sources" / "expanded_ad_sources.json"


LOCANTO_CITIES = [
    "lima",
    "arequipa",
    "trujillo",
    "chiclayo",
    "piura",
    "cusco",
    "callao",
    "huancayo",
    "ica",
    "tacna",
]

LOCANTO_TAGS = [
    ("ayuda-economica", "ayuda economica"),
    ("apoyo-economico", "apoyo economico"),
    ("ayudo-economicamente", "ayudo economicamente"),
]

EXTERNAL_CANDIDATES = [
    ("doplim", "https://www.doplim.com.pe/search/s/?q={query}"),
    ("evisos", "https://www.evisos.com.pe/search.php?keyword={query}"),
    ("clasf", "https://www.clasf.pe/q/{slug}/"),
]


def locanto_sources() -> list[dict[str, object]]:
    sources: list[dict[str, object]] = []
    for city in LOCANTO_CITIES:
        for tag, query in LOCANTO_TAGS:
            for page in ("", "1/", "2/", "19/"):
                page_suffix = "first" if not page else f"page_{page.strip('/')}"
                sources.append(
                    {
                        "id": f"locanto_{city}_{tag}_{page_suffix}",
                        "platform": "Locanto Peru",
                        "mode": "playwright",
                        "url": f"https://www.locanto.com.pe/{city}/tag/{tag}/{page}",
                        "query": query,
                        "public_only": True,
                        "notes": "Generated Locanto city/tag/pagination candidate."
                    }
                )
    return sources


def external_sources() -> list[dict[str, object]]:
    sources: list[dict[str, object]] = []
    for platform, template in EXTERNAL_CANDIDATES:
        for slug, query in (("ayuda-economica", "ayuda economica"), ("apoyo-economico", "apoyo economico")):
            encoded = query.replace(" ", "%20")
            url = template.format(query=encoded, slug=slug)
            sources.append(
                {
                    "id": f"{platform}_peru_{slug}",
                    "platform": f"{platform.title()} Peru",
                    "mode": "http",
                    "url": url,
                    "query": query,
                    "public_only": True,
                    "notes": "Generated external classified search candidate."
                }
            )
    return sources


def build_sources() -> dict[str, object]:
    return {
        "sources": locanto_sources() + external_sources()
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    data = build_sources()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "sources": len(data["sources"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
