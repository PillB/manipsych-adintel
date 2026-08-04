#!/usr/bin/env python3
"""Harvest candidate ad URLs (esp. Locanto /ID_ detail pages) using BeautifulSoup4 + requests/Playwright.
Single-focus for agentic use: feed this seeds for collection sub-agents.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import hashlib
import random
from pathlib import Path
from urllib.parse import urljoin, urlparse, quote

import requests
from bs4 import BeautifulSoup

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.ingest_candidate_urls import is_candidate

DEFAULT_OUTPUT = ROOT / "data" / "sources" / "harvested_seeds.jsonl"
TARGET_TERMS = ("ayuda economica", "ayuda económica", "apoyo economico", "apoyo económico", "ayudo economicamente", "hombre busca mujer", "contactos")

# Prioritized queries for hombre busca mujer sections (what worked: search engine targeted for section + direct IDs)
HOMBRE_BUSCA_QUERIES = [
    '"ayuda economica" OR "apoyo economico" OR "doy ayuda" OR "brindo apoyo" site:locanto.com.pe/Hombre-busca-mujer/',
    '"ayuda economica" OR "apoyo economico" hombre busca mujer site:locanto.com.pe',
    '"ayuda economica" site:locanto.com.pe/Contactos/P/',
    'site:locanto.com.pe "ID_" "hombre busca mujer" (ayuda OR apoyo OR economico)',
    'doplim "hombre busca mujer" (ayuda economica OR apoyo) lima',
    '"ayuda economica" OR "brindo apoyo" (lima OR peru) (site:facebook.com/groups OR site:facebook.com) -inurl:(marketplace login)',
]


def load_query_bank(path: Path | None) -> dict[str, list[str]]:
    if not path or not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {}
    out: dict[str, list[str]] = {}
    for platform, queries in data.items():
        if isinstance(queries, list):
            out[str(platform)] = [str(q) for q in queries if str(q).strip()]
    return out

def fetch_http(url: str, timeout: int = 25) -> str:
    import random
    uas = [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    ]
    resp = requests.get(
        url,
        timeout=timeout,
        headers={
            "User-Agent": random.choice(uas),
            "Accept-Language": "es-PE,es;q=0.9,en;q=0.5",
        },
    )
    resp.raise_for_status()
    return resp.text

def fetch_playwright(url: str, timeout_ms: int = 45000) -> str:
    import random
    if not HAS_PLAYWRIGHT:
        raise RuntimeError("Playwright not installed")
    # Expanded UAs + headers + waits (perseverance from prior blocks)
    uas = [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    ]
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(locale="es-PE", user_agent=random.choice(uas), viewport={"width": 1280, "height": 800})
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        try:
            page.wait_for_selector("h1, .description, article, a[href*='/ID_'], .bp_ad_title", timeout=14000)
        except Exception:
            page.wait_for_timeout(4000)
        page.wait_for_timeout(random.randint(1500, 3000))
        content = page.content()
        browser.close()
    return content

def normalize_facebook_url(url: str) -> str:
    """Normalize FB URLs to stable public post forms for seed persistence."""
    if "facebook.com" not in url.lower():
        return url
    u = url.replace("m.facebook.com", "www.facebook.com")
    if "//facebook.com" in u and "//www.facebook.com" not in u:
        u = u.replace("//facebook.com", "//www.facebook.com", 1)
    try:
        from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
        p = urlparse(u)
        qs = [(k, v) for k, v in parse_qsl(p.query) if not k.lower().startswith("fb") and k.lower() not in ("ref", "refsrc", "h", "paipv")]
        newq = urlencode(qs)
        u = urlunparse((p.scheme or "https", p.netloc, p.path, p.params, newq, ""))
    except Exception:
        pass
    return u.strip()

def extract_id_links(html: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        full = urljoin(base_url, href)
        text = (a.get_text() or "").strip().lower()
        # Generalized for any Peruvian city (not just lima) + handle hyphenated slugs
        url_norm = full.lower().replace("-", " ").replace("_", " ")
        is_fb_public = "facebook.com" in full.lower() and any(p in full for p in ("/groups/", "/posts/", "/permalink/"))
        if re.search(r"/[a-z0-9-]+/ID_\d+/", full) or any(t in url_norm or t in text for t in TARGET_TERMS) or is_fb_public:
            if is_candidate(full):
                norm_full = normalize_facebook_url(full)
                links.append({"url": norm_full, "text": a.get_text(strip=True)[:200]})
    # dedup
    seen = set()
    out = []
    for l in links:
        if l["url"] not in seen:
            seen.add(l["url"])
            out.append(l)
    return out

def harvest(query_url: str, mode: str = "http", max_pages: int = 3) -> list[dict]:
    results = []
    for i in range(max_pages):
        url = query_url if i == 0 else f"{query_url}&page={i+1}" if "?" in query_url else f"{query_url}?page={i+1}"
        try:
            html = fetch_playwright(url) if mode == "playwright" and HAS_PLAYWRIGHT else fetch_http(url)
            links = extract_id_links(html, url)
            results.extend(links)
            time.sleep(1.2)
            if not links:
                break
        except Exception as e:
            results.append({"error": str(e), "url": url})
            break
    return results

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", help="Base search or tag URL to harvest from (optional if using --section)")
    parser.add_argument("--section", choices=["hombre_busca_mujer", "doplim", "facebook"], help="Use built-in targeted queries for hombre busca mujer sections on Locanto/Doplim/FB (what worked most: search-first for specific category)")
    parser.add_argument("--mode", default="http", choices=["http", "playwright"])
    parser.add_argument("--max-pages", type=int, default=2)
    parser.add_argument("--query-bank", type=Path)
    parser.add_argument("--query-platform", choices=["locanto", "doplim", "facebook", "all"], default="all")
    parser.add_argument("--query-shard-index", type=int, default=0)
    parser.add_argument("--query-shard-count", type=int, default=1)
    parser.add_argument("--query-limit", type=int, default=40)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    if args.section:
        queries = HOMBRE_BUSCA_QUERIES if args.section == "hombre_busca_mujer" else HOMBRE_BUSCA_QUERIES  # extend as needed
        all_seeds = []
        for q in queries[:3]:  # limit for run
            # For section, use as DDG style or pass to web search equiv; here simulate with example or use as url if tag
            url = f"https://html.duckduckgo.com/html/?q={quote(q)}"
            print(f"Harvesting via search-first for section query: {q}")
            seeds = harvest(url, args.mode, args.max_pages)
            all_seeds.extend(seeds)
            time.sleep(2)
        seeds = all_seeds
    else:
        if not args.url:
            bank = load_query_bank(args.query_bank)
            platform_queries = bank.get(args.query_platform, []) if bank else []
            if not platform_queries:
                parser.error("--url required unless --section or --query-bank")
            shard_queries = platform_queries[args.query_shard_index::max(1, args.query_shard_count)]
            shard_queries = shard_queries[: args.query_limit]
            seeds = []
            for query in shard_queries:
                search_url = f"https://html.duckduckgo.com/html/?q={quote(query)}"
                print(f"Harvesting query: {query}")
                seeds.extend(harvest(search_url, args.mode, args.max_pages))
                time.sleep(random.uniform(0.8, 1.8))
        else:
            seeds = harvest(args.url, args.mode, args.max_pages)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    # Safety: never inject seeds/snippets directly into ad_manifest (prevents search_evidence pollution for volume)
    if "ad_manifest" in str(args.out):
        raise RuntimeError("harvest_seeds must not write to ad_manifest; use separate seeds file only")
    with args.out.open("a", encoding="utf-8") as f:
        for s in seeds:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    print(json.dumps({"harvested": len([s for s in seeds if "url" in s]), "total": len(seeds)}, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
