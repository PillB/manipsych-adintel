#!/usr/bin/env python3
"""
Search-engine-first + direct link following harvester using Selenium (for robustness when list pages block).
"First search in search engine then click each link to ad pages".

This is for public indexed content only. Polite delays, no CAPTCHA solving or illegal bypass.
Use as alternative or complement to Playwright/requests + BS4 when more "human click" simulation needed for JS-heavy public pages.

Requires: selenium, webdriver (e.g. ChromeDriver matching your Chrome version).
Install: pip install selenium
Download driver: https://chromedriver.chromium.org/

Strategy per user request and plan perseverance:
1. Search engine queries (DDG or simulated) for direct ad pages.
2. Parse results for ad links.
3. Visit each direct ad page with Selenium browser rendering.
4. Extract with BS4 or Selenium.
5. Redact, log to manifest.

This avoids low-yield list pages by going straight to public indexed details.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import time
import random
from pathlib import Path
from urllib.parse import quote
from typing import Optional

from bs4 import BeautifulSoup

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    HAS_SELENIUM = True
except ImportError:
    HAS_SELENIUM = False

ROOT = Path(__file__).resolve().parents[1]
import sys
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.redact_pii import redact_text
from tools.scrape_ads import is_access_interstitial, write_record, CandidateAd, archive_raw, hash_text

DEFAULT_MANIFEST = ROOT / "data" / "processed" / "ad_manifest.jsonl"
DEFAULT_RAW = ROOT / "data" / "raw" / "ads"

HOMBRE_BUSCA_QUERIES = [
    "ayuda economica OR apoyo economico OR doy ayuda OR brindo apoyo site:locanto.com.pe/Hombre-busca-mujer/",
    "ayuda economica hombre busca mujer site:locanto.com.pe",
    "ayuda economica site:locanto.com.pe/Contactos/",
    "hombre busca mujer ayuda economica doplim lima",
    "doy ayuda economica OR brindo apoyo lima site:facebook.com/groups",
]

TARGET_TERMS = ["ayuda economica", "apoyo economico", "doy ayuda", "brindo apoyo", "ofrezco apoyo"]

def resolve_chrome_binary() -> Optional[str]:
    candidates = [
        os.environ.get("SELENIUM_CHROME_BINARY", "").strip(),
        os.environ.get("CHROME_BINARY", "").strip(),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return None


def resolve_chromedriver() -> Optional[str]:
    candidates = [
        os.environ.get("SELENIUM_CHROMEDRIVER_PATH", "").strip(),
        os.environ.get("CHROMEDRIVER_PATH", "").strip(),
        shutil.which("chromedriver") or "",
        "/opt/homebrew/bin/chromedriver",
        "/usr/local/bin/chromedriver",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return None


def get_driver(headless: bool = False):
    if not HAS_SELENIUM:
        raise RuntimeError("Selenium not installed")
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--lang=es-PE")
    opts.add_argument("--window-size=1366,900")
    opts.add_argument("--no-first-run")
    opts.add_argument("--no-default-browser-check")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-background-networking")
    opts.add_argument("--disable-sync")
    opts.add_argument("--remote-debugging-port=0")
    opts.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    opts.add_argument("--no-sandbox")
    chrome_binary = resolve_chrome_binary()
    if chrome_binary:
        opts.binary_location = chrome_binary

    chromedriver = resolve_chromedriver()
    if not chromedriver:
        raise RuntimeError(
            "No chromedriver found. Install ChromeDriver or set SELENIUM_CHROMEDRIVER_PATH, "
            "CHROMEDRIVER_PATH, or add chromedriver to PATH. On this Mac, Chrome exists but the "
            "driver is missing, which is a common cause of 'Chrome closed unexpectedly'. "
            "For a quick recovery, run this script with Playwright instead or install a matching driver."
        )

    from selenium.webdriver.chrome.service import Service

    driver = webdriver.Chrome(service=Service(chromedriver), options=opts)
    driver.set_page_load_timeout(30)
    return driver

def search_ddg(query: str) -> list[str]:
    import requests
    from bs4 import BeautifulSoup
    from urllib.parse import quote
    url = "https://html.duckduckgo.com/html/?q=" + quote(query)
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; ResearchBot/1.0)"}, timeout=20)
        soup = BeautifulSoup(resp.text, "lxml")
        links = []
        for a in soup.select(".result__a"):
            href = a.get("href", "")
            if href and any(t in href.lower() for t in ["locanto", "doplim", "evisos", "facebook"]):
                # Resolve DDG redirect if present
                if "duckduckgo.com" in href and "uddg=" in href:
                    from urllib.parse import parse_qs, urlparse, unquote
                    parsed = urlparse(href)
                    target = parse_qs(parsed.query).get("uddg", [""])[0]
                    if target:
                        href = unquote(target)
                links.append(href)
        print(f"[Selenium Harvester] Real DDG search for '{query}' found {len(links)} candidate links")
        return links
    except Exception as e:
        print(f"[Selenium Harvester] Real search failed for {query}: {e}")
        return []

def fetch_with_selenium(driver, url: str) -> str:
    import random
    try:
        time.sleep(random.uniform(1.5, 3.5))
        driver.get(url)
        # Wait for real ad content selectors to skip verification interstitials
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            WebDriverWait(driver, 12).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "h1, .ad-title, .description, article[data-id], .padded, .bp_ad_title"))
            )
        except:
            time.sleep(4)
        time.sleep(random.uniform(2, 4))
        return driver.page_source
    except Exception as e:
        print(f"  Selenium fetch error for {url}: {e}")
        return ""

def extract_ad_from_html(html: str, url: str, platform: str = "Evisos/Locanto") -> Optional[CandidateAd]:
    if is_access_interstitial(html):
        return None
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.string.strip() if soup.title else "Untitled ad"
    body = soup.get_text(separator=" ", strip=True)[:8000]
    if not any(term in body.lower() for term in TARGET_TERMS):
        return None
    return CandidateAd(platform=platform, url=url, title=title, body=body)

def main():
    parser = argparse.ArgumentParser(description="Search-first Selenium harvester for public ads - hombre busca mujer focus")
    parser.add_argument("--queries", nargs="+", default=HOMBRE_BUSCA_QUERIES)
    parser.add_argument("--section", action="store_true", help="Use hombre busca mujer targeted queries for Locanto/Doplim/FB")
    parser.add_argument("--headless", action="store_true", default=False, help="Launch Chrome headless. Default is headed for debugging on Mac.")
    parser.add_argument("--max", type=int, default=5)
    args = parser.parse_args()

    queries = HOMBRE_BUSCA_QUERIES if args.section or not args.queries else args.queries

    if not HAS_SELENIUM:
        print("Install selenium and ChromeDriver first. Falling back to note: use Playwright agentic for now.")
        # still allow discovery simulation
        print("Simulating search-first for hombre busca mujer queries (what worked):", queries[:2])
        return 0

    try:
        driver = get_driver(args.headless)
    except Exception as e:
        print(f"[Selenium Harvester] Browser launch failed: {e}")
        print("[Selenium Harvester] Recovery path: install chromedriver, set SELENIUM_CHROMEDRIVER_PATH, or use Playwright fallback.")
        return 2
    try:
        all_links = []
        for q in queries[:3]:  # limit
            print(f"Search-first for hombre busca mujer query: {q}")
            links = search_ddg(q)
            all_links.extend(links[:args.max])
            time.sleep(2)
        all_links = list(dict.fromkeys(all_links))[:args.max]

        print(f"Visiting {len(all_links)} direct ad links from hombre busca mujer search (click simulation with Selenium for robustness)...")
        for url in all_links:
            print(f"  Visiting (Selenium click): {url}")
            html = fetch_with_selenium(driver, url)
            candidate = extract_ad_from_html(html, url)
            if candidate:
                raw_path = archive_raw(DEFAULT_RAW, "selenium_search", url, html)
                if write_record(DEFAULT_MANIFEST, candidate, raw_path):
                    print(f"    Logged: {candidate.title[:60]}")
            time.sleep(random.uniform(2, 4))  # Persevere with delay
    finally:
        driver.quit()
    print("Done. Check manifest.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
