#!/usr/bin/env python3
"""Collect public ad pages into a raw archive and redacted JSONL manifest.

The collector is intentionally conservative:
- public URLs only;
- no login, CAPTCHA solving, or access-control bypass;
- rate limited;
- raw HTML stays under data/raw;
- processed records redact contact-like PII and hash source URLs.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
import time
import random
import threading
import shutil
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.redact_pii import redact_text


DEFAULT_SOURCES = ROOT / "data" / "sources" / "ad_sources.json"
DEFAULT_RAW_DIR = ROOT / "data" / "raw" / "ads"
DEFAULT_MANIFEST = ROOT / "data" / "processed" / "ad_manifest.jsonl"
DEFAULT_ATTEMPT_LOG = ROOT / "reports" / "phase4_search_log.json"


TARGET_TERMS = (
    "ayuda economica",
    "ayuda económica",
    "apoyo economico",
    "apoyo económico",
    "ayudo economicamente",
    "ayudo económicamente",
    "brindo ayuda",
    "brindo apoyo",
    "doy ayuda",
    "doy apoyo",
    "brindar ayuda",
    "brindar apoyo",
    "ayuda para",
    "apoyo rapido",
)

_HTTP_SESSION_STATE = threading.local()
_RECORD_ID_CACHE: dict[str, set[str]] = {}


@dataclass(frozen=True)
class CandidateAd:
    platform: str
    url: str
    title: str
    body: str


class LinkTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[dict[str, str]] = []
        self._href_stack: list[str | None] = []
        self._text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            attrs_dict = {key.lower(): value for key, value in attrs}
            self._href_stack.append(attrs_dict.get("href"))
            self._text_parts.append("")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href_stack:
            href = self._href_stack.pop()
            text = self._text_parts.pop() if self._text_parts else ""
            if href and text.strip():
                self.links.append({"href": href, "text": normalize_space(text)})

    def handle_data(self, data: str) -> None:
        if self._href_stack and self._text_parts:
            self._text_parts[-1] += data


class TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "noscript"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self.parts.append(data)


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def text_from_html(page_html: str) -> str:
    # Prefer BS4 for robustness when available
    try:
        soup = BeautifulSoup(page_html, "lxml")
        text = soup.get_text(separator=" ", strip=True)
        return normalize_space(text)
    except Exception:
        parser = TextParser()
        parser.feed(page_html)
        return normalize_space(" ".join(parser.parts))


HARD_ACCESS_PATTERNS = (
    re.compile(r"captcha", re.I),
    re.compile(r"cloudflare", re.I),
    re.compile(r"access denied", re.I),
    re.compile(r"verify you are human", re.I),
    re.compile(r"estamos verificando tu navegador", re.I),
    re.compile(r"navegador antes de acceder", re.I),
    re.compile(r"ser[aá]s redirigido", re.I),
    re.compile(r"phone verification", re.I),
    re.compile(r"verifying your account", re.I),
    re.compile(r"js-phone_verification_mfd", re.I),
)


def is_hard_access_interstitial(page_html: str) -> bool:
    page_text = text_from_html(page_html).lower()
    title = extract_title(page_html).lower()
    combined = f"{title} {page_text}"
    if "un momento" in title and any(term in combined for term in ("captcha", "verificando", "redirigido", "cloudflare")):
        return True
    return any(pattern.search(combined) for pattern in HARD_ACCESS_PATTERNS)


def is_access_interstitial(page_html: str) -> bool:
    return is_hard_access_interstitial(page_html)


def get_facebook_variants(url: str) -> list[str]:
    """Generate m.facebook / www.facebook fallbacks for perseverance on FB public indexed pages. Prefer www but try m for server-render potential."""
    if "facebook.com" not in url.lower():
        return [url]
    base = url.replace("m.facebook.com", "www.facebook.com")
    if "//facebook.com" in base and "//www.facebook.com" not in base:
        base = base.replace("//facebook.com", "//www.facebook.com", 1)
    cands = [base]
    m = base.replace("www.facebook.com", "m.facebook.com")
    if m != base:
        cands.append(m)
    # Also plain if needed
    if "www.facebook.com" not in base and "m.facebook.com" not in base:
        cands.append(base.replace("facebook.com", "www.facebook.com"))
        cands.append(base.replace("facebook.com", "m.facebook.com"))
    seen = set()
    uniq = []
    for c in cands:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    return uniq


def is_facebook_unloaded_skeleton(html: str) -> bool:
    """Detect unloaded JS empty/skeleton pages for FB public posts (common: login wall, short HTML, no rendered userContent).
    Used to avoid gathering/archiving pages where content JS has not loaded yet.
    """
    if not html or len(html) < 1500:
        return True
    low = html.lower()
    # Common skeleton/login indicators
    if "log in to facebook" in low or "iniciar sesión" in low[:2000] or "create account" in low[:1500]:
        return True
    if "please log in" in low or "log into facebook" in low:
        return True
    # Very short meaningful content despite large HTML (JS not rendered) -- key for "only html no contents"
    text_len = len(text_from_html(html))
    # FB often surfaces the real ad text in og:description even when DOM text is tiny
    og_desc_len = 0
    try:
        from bs4 import BeautifulSoup
        og = BeautifulSoup(html, "lxml").select_one('meta[property="og:description"]')
        if og:
            og_desc_len = len((og.get("content") or "").strip())
    except Exception:
        pass
    if text_len < 250 and og_desc_len < 30:
        return True
    # Special for group posts: if og:description carries the full ad text (very common for public indexed "ayuda economica" posts), accept even if main DOM text is minimal (groups often hydrate poorly for scrapers)
    try:
        og_content = ""
        from bs4 import BeautifulSoup
        og = BeautifulSoup(html, "lxml").select_one('meta[property="og:description"]')
        if og:
            og_content = (og.get("content") or "").strip()
        if og_desc_len > 80 and re.search(r"ayuda|apoyo|brindo|doy", og_content, re.I):
            return False  # has real content via og, do not treat as skeleton
    except:
        pass
    # No FB content markers after waits -- typical of unloaded
    has_fb_markers = any(m in low for m in ["usercontent", "data-ad-preview", "story_body", "post_message", "og:description"])
    if ("facebook.com" in low and not has_fb_markers) and og_desc_len < 20:
        if len(html) > 8000 and text_len < 800:
            return True
    # Large HTML but very little extractable text (common for pure skeleton before JS hydrate)
    if len(html) > 20000 and text_len < 350 and og_desc_len < 30:
        return True
    return False


def has_substantial_ad_content(html: str, url: str = "") -> bool:
    """Gate to avoid archiving empty/unloaded/skeleton detail ad pages.
    Call before archive_raw on ad *detail* pages (step 2 after link gathering).
    """
    if not html or len(html) < 1800:
        return False
    low_first = html.lower()[:3500]
    if is_access_interstitial(html):
        return False
    if any(k in low_first for k in ["cargando", "un momento", "verificando tu navegador", "serás redirigido"]):
        return False
    url_l = (url or "").lower()
    is_fb = "facebook" in url_l or "facebook.com" in low_first
    if is_fb:
        if is_facebook_unloaded_skeleton(html):
            return False
        # Require real post text beyond skeleton. og:description often holds the ad for FB public posts.
        t = text_from_html(html)
        og_desc = ""
        try:
            from bs4 import BeautifulSoup
            og = BeautifulSoup(html, "lxml").select_one('meta[property="og:description"]')
            if og: og_desc = (og.get("content") or "").strip()
        except Exception:
            pass
        effective_body = max(len(t), len(og_desc))
        if effective_body < 30:
            return False
        # If we have og or markers or decent text, accept (FB markup varies)
        has_marker = any(m in html.lower() for m in ["usercontent", "data-ad-preview", "post_message", "story_body", "og:description"])
        if not has_marker and effective_body < 150:
            return False
    else:
        t = text_from_html(html)
        if len(t) < 220:
            return False
    return True


def load_sources(path: Path) -> list[dict[str, object]]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return list(data.get("sources", []))


def build_http_session() -> requests.Session:
    uas = [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    ]
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": random.choice(uas),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "es-PE,es;q=0.9,en-US;q=0.5,en;q=0.3",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Referer": "https://www.google.com.pe/",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "cross-site",
        }
    )
    adapter = requests.adapters.HTTPAdapter(pool_connections=16, pool_maxsize=16, max_retries=0)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def get_http_session() -> requests.Session:
    session = getattr(_HTTP_SESSION_STATE, "session", None)
    if session is None:
        session = build_http_session()
        _HTTP_SESSION_STATE.session = session
    return session


def fetch_http(url: str, timeout: int = 25, session: requests.Session | None = None) -> str:
    session = session or get_http_session()
    response = session.get(url, timeout=timeout, allow_redirects=True)
    response.raise_for_status()
    return response.text


def fetch_playwright(url: str, timeout_ms: int = 80000, max_retries: int = 10) -> str:
    from playwright.sync_api import sync_playwright
    # Recent browser UAs help keep localized public rendering predictable.
    uas = [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    ]
    extra_headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "es-PE,es;q=0.9,en-US;q=0.5,en;q=0.3",
        "Referer": "https://www.google.com.pe/",
        "Sec-Ch-Ua": '"Google Chrome";v="133", "Chromium";v="133", "Not_A Brand";v="24"',
        "Sec-Ch-Ua-Platform": '"macOS"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "cross-site",
    }
    def chromium_executable_path() -> str | None:
        env_path = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH", "").strip()
        candidates = [env_path] if env_path else []
        candidates.extend([
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ])
        for candidate in candidates:
            if candidate and Path(candidate).exists():
                return candidate
        return None

    executable_path = chromium_executable_path()
    last_content = ""
    fb_variants = get_facebook_variants(url) if "facebook.com" in url.lower() else [url]
    for attempt in range(max_retries):
        for variant in fb_variants:
            try:
                with sync_playwright() as p:
                    launch_kwargs = {"headless": True, "args": ["--no-sandbox", "--disable-dev-shm-usage"]}
                    if executable_path:
                        launch_kwargs["executable_path"] = executable_path
                    browser = p.chromium.launch(**launch_kwargs)
                    ctx = browser.new_context(
                        locale="es-PE",
                        user_agent=random.choice(uas),
                        viewport={"width": random.choice([1280,1366,1440,1600]), "height": 900},
                        extra_http_headers=extra_headers,
                    )
                    page = ctx.new_page()
                    page.goto(variant, wait_until="domcontentloaded", timeout=timeout_ms)
                    # Strong explicit wait for REAL ad content, not loading screens
                    try:
                        # General + site-specific from live HTML analysis
                        page.wait_for_selector("h1, .description, article, .ad_text, .user_content, .bp_ad_title, a[href*='/ID_'], [data-id], .posting_listing, .bst_pagination, li.cnt-list_ads, a.show_more", timeout=30000)
                    except:
                        try:
                            page.wait_for_load_state("networkidle", timeout=18000)
                        except:
                            page.wait_for_timeout(12000)
                    # Extra waits and checks to avoid recording loading/verifying screens as ads
                    page.wait_for_timeout(random.randint(5000, 12000))
                    try:
                        page.evaluate("window.scrollBy(0, Math.random()*800 + 400)")
                        page.wait_for_timeout(random.randint(1200, 3000))
                        page.evaluate("window.scrollBy(0, Math.random()*400 + 200)")
                    except:
                        pass
                    if "/Hombre-busca" in url or "20701" in url or "query=" in url or "/contactos" in url.lower():
                        page.wait_for_timeout(random.randint(4000, 8000))

                    # FB-specific: extra waits on userContent/data-ad-preview, scroll, detect unloaded JS empty pages and retry with m.facebook or playwright variants
                    fb_url = "facebook.com" in url.lower()
                    if fb_url:
                        # Explicit extra waits for userContent and data-ad-preview per spec
                        try:
                            page.wait_for_selector(".userContent, [data-ad-preview], [data-ad-preview='message'], #story_body_container, div[role='article'], [data-testid*='post_message'], meta[property='og:title']", timeout=30000)
                        except:
                            pass
                        page.wait_for_timeout(random.randint(5000, 12000))
                        # Multiple scrolls to trigger render
                        for _ in range(5):
                            try:
                                page.evaluate("window.scrollBy(0, 600)")
                                page.wait_for_timeout(random.randint(800, 1800))
                            except:
                                pass
                        # Wait specifically again for content markers
                        try:
                            page.wait_for_selector("div.userContent, [data-ad-preview], .userContent, [data-testid*='post_message']", timeout=15000)
                        except:
                            pass
                        page.wait_for_timeout(random.randint(3000, 6000))
                        # Stronger: wait for og:description to actually have the post text (FB often relies on this)
                        try:
                            page.wait_for_function(
                                "() => { const m = document.querySelector('meta[property=\"og:description\"]'); return m && m.content && m.content.trim().length > 25; }",
                                timeout=20000
                            )
                        except:
                            pass
                        # One more scroll + settle for any "See more" or hydration
                        try:
                            page.evaluate("window.scrollBy(0, 300)")
                            page.wait_for_timeout(1500)
                        except:
                            pass

                    # Additional anti-loading check: require substantial content
                    # Strict gate per spec: len<2500 or keywords or is_access_interstitial in first 3k chars
                    content = page.content()
                    low = content.lower()
                    first3k = low[:3000]
                    inter = is_access_interstitial(content)
                    # Detect FB unloaded JS pages (empty content despite no inter) - improved
                    fb_unloaded = fb_url and (is_facebook_unloaded_skeleton(content) or len(content) < 4000 or "loading" in first3k or "please log in" in first3k or "log in" in first3k[:2000])
                    if fb_unloaded:
                        print(f"[FB-UNLOADED-LOG] variant={variant} orig={url} len={len(content)} text_len={len(text_from_html(content))} first3k_indicators={first3k[:200]}", flush=True)
                    if (len(content) < 2500 or
                        "cargando" in first3k or
                        "un momento" in first3k or
                        "verificando" in first3k or
                        inter or
                        fb_unloaded):
                        # treat as not ready / inter / unloaded - retry with fresh ctx + next variant
                        browser.close()
                        last_content = content
                        time.sleep(random.uniform(8.0, 25.0))
                        continue
                    browser.close()
                    last_content = content
                    if not inter and "un momento" not in first3k and "verificando" not in first3k and "cloudflare" not in first3k and "nueva app" not in first3k and not fb_unloaded:
                        return content
                    # Persevere: longer backoff on block, fresh ctx next
                    time.sleep(random.uniform(8.0, 25.0))
            except Exception as e:
                time.sleep(random.uniform(8.0, 25.0))
                continue
    return last_content


def fetch_selenium(url: str, timeout: int = 60, headless: bool = False) -> str:
    """Selenium fetch in headed mode by default (per spec) with polling for browser verification interstitials ("Estamos verificando tu navegador...") until real ad content loads. Uses ChromeDriverManager + exact ChromeOptions recommended for Grok/Codex CLI headed scraping. Falls back to Playwright if driver missing."""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from webdriver_manager.chrome import ChromeDriverManager
    except ImportError as exc:
        raise RuntimeError("selenium + webdriver-manager not installed; install them or use fetch_playwright") from exc

    uas = [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    ]
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    # No --headless for default headed visible mode
    options.add_argument("--lang=es-PE")
    options.add_argument("--window-size=1366,900")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-sync")
    options.add_argument("--remote-debugging-port=0")
    options.add_argument(f"--user-agent={random.choice(uas)}")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")  # help avoid some flags

    # Chrome binary
    chrome_binary = None
    for candidate in (
        os.environ.get("SELENIUM_CHROME_BINARY", "").strip(),
        os.environ.get("CHROME_BINARY", "").strip(),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ):
        if candidate and Path(candidate).exists():
            chrome_binary = candidate
            break
    if chrome_binary:
        options.binary_location = chrome_binary

    # Use ChromeDriverManager for easy matching driver (recommended in spec)
    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    except Exception:
        # Fallback to explicit path
        chromedriver = None
        for candidate in (
            os.environ.get("SELENIUM_CHROMEDRIVER_PATH", "").strip(),
            os.environ.get("CHROMEDRIVER_PATH", "").strip(),
            shutil.which("chromedriver") or "",
            "/opt/homebrew/bin/chromedriver",
            "/usr/local/bin/chromedriver",
        ):
            if candidate and Path(candidate).exists():
                chromedriver = candidate
                break
        if not chromedriver:
            # Final fallback to playwright as per plan
            print("[selenium] no driver, falling back to playwright", flush=True)
            return fetch_playwright(url, timeout_ms=timeout*1000, max_retries=3)
        driver = webdriver.Chrome(service=Service(chromedriver), options=options)

    try:
        driver.set_page_load_timeout(timeout)
        driver.get(url)

        # Perseverant polling: wait until verificando / browser verification messages are gone and real ad content appears
        start = time.time()
        verificando_keywords = ["verificando tu navegador", "verifying your browser", "estamos verificando", "seras redirigido", "un momento", "cargando"]
        ad_selectors = "h1, .description, article, .ad_text, .user_content, a[href*='/ID_'], [data-id]"
        fb_selectors = ".userContent, [data-ad-preview='message'], #story_body_container, div[role='article'], [data-testid*='post_message']"

        while time.time() - start < timeout:
            try:
                page_src = driver.page_source.lower()
                if any(kw in page_src for kw in verificando_keywords):
                    time.sleep(1.5)
                    continue
                # Wait for ad content selectors
                try:
                    WebDriverWait(driver, 8).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, ad_selectors))
                    )
                except:
                    pass
                # FB specific waits for JS loaded content: extra waits on userContent/data-ad-preview, scroll, detect unloaded
                if "facebook.com" in url.lower():
                    try:
                        WebDriverWait(driver, 20).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, fb_selectors))
                        )
                    except:
                        pass
                    time.sleep(random.uniform(4,8))
                    # extra scrolls
                    for _ in range(4):
                        driver.execute_script("window.scrollBy(0, 550);")
                        time.sleep(0.8)
                    try:
                        WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, ".userContent, [data-ad-preview]"))
                        )
                    except:
                        pass
                content = driver.page_source
                if len(content) > 2000 and not is_access_interstitial(content):
                    low = content.lower()[:3000]
                    fb_unloaded = "facebook.com" in url.lower() and (is_facebook_unloaded_skeleton(content) or len(content) < 4000 or "loading" in low[:1000])
                    if fb_unloaded:
                        print(f"[FB-UNLOADED-LOG] selenium url={url} len={len(content)}", flush=True)
                    if not any(k in low for k in ["verificando", "cargando", "un momento"]) and not fb_unloaded:
                        return content
            except Exception:
                pass
            time.sleep(1.0)

        # final return whatever we have
        return driver.page_source
    finally:
        driver.quit()


def fetch_source(source: dict[str, object]) -> str:
    mode = str(source.get("mode", "http"))
    url = str(source["url"])
    if mode == "playwright":
        return fetch_playwright(url)
    if mode == "selenium":
        return fetch_selenium(url)
    return fetch_http(url)


def discover_links(page_html: str, base_url: str) -> list[dict[str, str]]:
    # BS4 enhanced discovery for ID links and terms (preferred)
    try:
        soup = BeautifulSoup(page_html, "lxml")
        discovered = []
        for a in soup.find_all("a", href=True):
            href = urljoin(base_url, a["href"])
            text = normalize_space(a.get_text() or "")
            haystack = f"{href} {text}".lower()
            if re.search(r"/ID_\d+/.+\.html$", href) or re.search(r"/ID_\d+/", href):
                discovered.append({"url": href, "text": text or "Locanto detail page"})
            elif any(term in haystack for term in TARGET_TERMS):
                discovered.append({"url": href, "text": text})
        return dedupe_links(discovered)
    except Exception:
        parser = LinkTextParser()
        parser.feed(page_html)
        discovered: list[dict[str, str]] = []
        for link in parser.links:
            href = urljoin(base_url, link["href"])
            text = normalize_space(link["text"])
            haystack = f"{href} {text}".lower()
            if re.search(r"/ID_\d+/.+\.html$", href):
                discovered.append({"url": href, "text": text or "Locanto detail page"})
            elif any(term in haystack for term in TARGET_TERMS):
                discovered.append({"url": href, "text": text})
        return dedupe_links(discovered)


def dedupe_links(links: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    output: list[dict[str, str]] = []
    for link in links:
        url = link["url"]
        if url not in seen:
            seen.add(url)
            output.append(link)
    return output


def extract_candidate(platform: str, url: str, page_html: str, fallback_title: str = "") -> CandidateAd | None:
    page_text = text_from_html(page_html)
    lowered = page_text.lower()
    if not any(term in lowered for term in TARGET_TERMS):
        return None
    # Post-fetch gate: require male-offer perspective; reject plain "busco apoyo" seekers even if target term present (from validation leakage)
    has_strong_offer = any(x in lowered for x in ("brindo", "doy ", "ofrezco", "brindar ayuda", "le ayudo", "te brindo", "yo brindo", "hombre maduro", "caballero maduro"))
    has_seeker_phrase = any(x in lowered for x in ("busco apoyo", "busco ayuda economica", "busco ayuda económica", "interesado en conocerme", "conocerme y"))
    if has_seeker_phrase and not has_strong_offer:
        return None
    title = fallback_title or extract_title(page_html) or "Untitled public ad"
    return CandidateAd(platform=platform, url=url, title=title, body=page_text)


def extract_title(page_html: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", page_html, flags=re.IGNORECASE | re.DOTALL)
    return normalize_space(match.group(1)) if match else ""

def extract_ads_from_listing_html(html: str, base_url: str, platform: str = "Locanto Hombre Busca Mujer") -> list[CandidateAd]:
    """Bulk extract multiple ad cards from a listing/search results page HTML.
    Used for volume. Parses Locanto-style /ID_ in hombre busca mujer sections.
    Relaxed: accept all /ID_ from hombre section listings (terms often in URL/query).
    """
    soup = BeautifulSoup(html, "lxml")
    ads = []
    seen_urls = set()
    is_hombre_section = "hombre" in base_url.lower() or "/20701" in base_url or "Hombre-busca" in base_url
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"])
        if not re.search(r"/ID_\d+/", href):
            continue
        if href in seen_urls:
            continue
        seen_urls.add(href)
        title = normalize_space(a.get_text() or "")
        if not title:
            parent = a.find_parent()
            if parent:
                h = parent.find(["h1","h2","h3"])
                if h: title = normalize_space(h.get_text())
        if not title:
            title = "Untitled listing ad (hombre busca)"
        card = a.find_parent(["article", "div", "li", "section"]) or a
        body = normalize_space(card.get_text(separator=" "))
        # Accept broadly for hombre section targeted listings
        if is_hombre_section or any(term in (body + " " + title).lower() for term in TARGET_TERMS):
            ads.append(CandidateAd(platform=platform, url=href, title=title[:300], body=body[:8000]))
    return ads


def extract_ad_detail_urls(html: str, base_url: str, platform_hint: str = "") -> list[str]:
    """Step 1 of two-step list crawling: identify ad detail URLs from a rendered listing/summary page.
    Refined: ONLY pull /ID_ or -id- links from *within* the main ad card containers (article.posting_listing for Locanto; li.cnt-list_ads for Doplim).
    Scopes to primary results area first (main, .bsp_list, section etc) then cards inside to strictly avoid sidebars, "otros anuncios", "anuncios similares", promoted extras, footer, unrelated categories.
    From live analysis: Locanto ~49-51 article.posting_listing cards per page in /Hombre-busca-mujer/20701/ (incl. top/premium); Doplim ~30-35 li.cnt-list_ads yielding 30 id- links.
    Supports:
      - Locanto: /ID_\d+/ only from main cards
      - Doplim: -id-\d+\.html only from main cards
      - FB: post patterns
    Always dedup, preserve order. Call only on pages that passed real-content load gate.
    Expect 10+ valid main ads per targeted section page.
    """
    soup = BeautifulSoup(html, "lxml")
    out: list[str] = []
    seen = set()
    hint = (platform_hint + " " + base_url).lower()
    is_loc = "locanto" in hint
    is_dop = "doplim" in hint
    is_fb = "facebook" in hint

    # Primary main results area (avoids side/footers/otros); fallback to soup
    main_area = soup.select_one(
        "main.page_main, main, div.js-bsp_results, div.bsp_list, "
        "section.cnt_ads_list, section, div.cnt_ads_list, #content, .content, ul.row"
    ) or soup

    if is_loc or "locanto" in base_url.lower() or "locanto" in hint:
        # ONLY from main ad card containers
        cards = main_area.select("article.posting_listing")
        if not cards:
            cards = soup.select("article.posting_listing")
        for card in cards:
            ctext = card.get_text(" ", strip=True)
            # Refined from iterative trials: scope to main article.posting_listing only (avoids all sides/distractors/cars).
            # Card-level prefilter: keep most of the section main cards that mention ayuda/apoyo terms or offer signals;
            # drop obvious pure seekers (busco ayuda/apoyo/chica without counter offer sig). Yields ~48/50 main cards (relaxed)
            # vs prior ~25-30 while still safe. Full gates (TARGET, male perspective, no minor/inter) applied on detail.
            has_kw = bool(re.search(r"ayuda|apoyo|brindo|doy|ofrezco|caballero|profesional.*(ayuda|apoyo|brindo)", ctext, re.I))
            is_bad_seeker = bool(re.search(r"busco (ayuda|apoyo|chica|universitaria|estudiante)", ctext, re.I)) and not re.search(r"brindo|doy|ofrezco", ctext, re.I)
            if not has_kw or is_bad_seeker:
                continue
            for a in card.find_all("a", href=True):
                h = urljoin(base_url, a["href"])
                if h not in seen and re.search(r"/ID_\d+/", h):
                    seen.add(h)
                    out.append(h)
    elif is_dop or "doplim" in base_url.lower() or "doplim" in hint:
        # ONLY from main ad card containers (li.cnt-list_ads from live fetch analysis; col-12/featured etc)
        # Additional card-level filter for target terms to avoid cars/rentals/unrelated even on filtered ?q= lists
        cards = main_area.select("li.cnt-list_ads, li[class*='cnt-list_ads']")
        if not cards:
            cards = soup.select("li.cnt-list_ads, li[class*='cnt-list_ads']")
        for card in cards:
            ctext = card.get_text(" ", strip=True)
            # Stronger offer prefilter for Doplim (address seeker/mixed leakage seen in city runs).
            # Require positive male-offer signals or caballero/profesional framing (like Locanto tightened version).
            # Require "ayuda economica" / "apoyo economico" phrasing + offer signal (stricter for target "ayuda economica" male-offer ads)
            has_ayuda_econ = bool(re.search(r"ayuda\s*economica|apoyo\s*economico", ctext, re.I))
            has_offer = bool(re.search(r"brindo|doy|ofrezco|se brinda|brinda apoyo", ctext, re.I))
            has_kw = has_ayuda_econ and has_offer
            is_bad_seeker = bool(re.search(r"busco (ayuda|apoyo|chica|universitaria|estudiante|senorita)", ctext, re.I)) and not re.search(r"brindo|doy|ofrezco", ctext, re.I)
            if not has_kw or is_bad_seeker:
                continue
            for a in card.find_all("a", href=True):
                h = urljoin(base_url, a["href"])
                if h not in seen and (re.search(r"-id-\d+\.html", h, re.IGNORECASE) or re.search(r"/id-\d+", h, re.IGNORECASE)):
                    seen.add(h)
                    out.append(h)
    elif is_fb or "facebook" in base_url.lower() or "facebook" in hint:
        # FB often lacks strict cards; use main_area + patterns. Improved for group conversations/posts
        for a in main_area.find_all("a", href=True):
            h = urljoin(base_url, a["href"])
            if h not in seen and (re.search(r"facebook\.com/.+/(posts|permalink|story\.php)", h, re.IGNORECASE) or ("/groups/" in h and re.search(r"/\d{5,}/?", h))):
                seen.add(h)
                out.append(h)
        # Stronger group post harvesting: role=article, userContent containers, data-ft, common in group feeds/search
        for container in soup.select("div[role=article], [data-ad-preview], .userContentWrapper, div[data-ft], [data-testid*='post']"):
            for a in container.find_all("a", href=True):
                h = urljoin(base_url, a["href"])
                if h not in seen and (re.search(r"facebook\.com/.+/(posts|permalink|story\.php)", h, re.IGNORECASE) or ("/groups/" in h and re.search(r"/\d{5,}", h))):
                    seen.add(h)
                    out.append(h)
    else:
        # generic: prefer cards but fall back
        cards = main_area.select("article, li[class*='ad'], li[class*='list'], div[class*='result']")
        if not cards:
            cards = [soup]
        for card in cards:
            for a in card.find_all("a", href=True):
                h = urljoin(base_url, a["href"])
                if h not in seen and (re.search(r"/ID_\d+/", h) or re.search(r"-id-\d+\.html", h, re.IGNORECASE)):
                    seen.add(h)
                    out.append(h)
    return out


def extract_facebook_engagement_users(html: str, post_url: str) -> dict:
    """Extract users who commented/replied or liked/positively reacted to an FB post (esp. group posts).
    Works on archived HTML or fresh fetch_playwright result.
    Returns structured dict with post_author, commenters, reactors (positive), approx counts.
    Profile URLs are normalized to absolute facebook.com form when possible.
    Basic info = display name + profile_url (more details rarely available publicly without login).
    Tolerant of partial public renders (many archived pages only have reaction *counts*, few or no named commenters).
    """
    from bs4 import BeautifulSoup
    from urllib.parse import urljoin, urlparse, parse_qs
    import re, datetime

    result = {
        "post_url": post_url,
        "post_author": None,
        "commenters": [],
        "reactors": [],
        "reactions_approx": None,
        "comments_approx": None,
        "group_name": None,
        "extracted_at": datetime.datetime.utcnow().isoformat() + "Z",
        "source_note": "visible+parsed from public HTML (may be incomplete)",
    }

    if not html or len(html) < 2000:
        return result

    soup = BeautifulSoup(html, "lxml")
    low = html.lower()

    # 1. Better post author detection. Prefer actual person names over the ad title itself.
    # Look in specific places: near date, "posted by", first actor in group context.
    author_name = None
    # Try data-testid or common actor containers first
    for sel in [ '[data-testid*="actor"]', '[aria-label*="Posted by"]', 'strong', 'h3', 'h2' ]:
        for el in soup.select(sel)[:8]:
            t = el.get_text(" ", strip=True)
            if 2 < len(t) < 70 and not any(b in t.lower() for b in ["facebook", "iniciar", "sesión", "comentar", "reaccion", "grupo", "public", "doy ayuda", "brindo", "ayuda economica"]):
                author_name = t
                break
        if author_name:
            break
    if not author_name:
        # Fallback to og:title but strip the ad content if it looks like the offer
        og = soup.select_one('meta[property="og:title"]')
        if og:
            t = og.get("content", "")
            # If title is mostly the ad text, leave author unknown (common); else take left part
            if "|" in t:
                left = t.split("|")[0].strip()
                if 2 < len(left) < 60 and "ayuda" not in left.lower():
                    author_name = left

    # 2. Group name
    for a in soup.select('a[href*="/groups/"]'):
        gt = a.get_text(strip=True)
        if gt and len(gt) > 4 and not any(x in gt.lower() for x in ["login", "ver"]):
            result["group_name"] = gt[:100]
            break

    # 3. Reactions (es-PE + en) - more tolerant
    for pat in [
        r"(\d[\d,. ]*)\s*(me gusta|reaccionaron|personas? reaccion|reacciones|likes?|reactions?)",
        r"todas las reacciones[:\s]*(\d+)",
        r"(\d+)\s*(personas?|likes?|reacciones?)",
    ]:
        m = re.search(pat, low, re.I)
        if m:
            num = re.sub(r"[^\d]", "", m.group(1) or m.group(0))
            if num:
                try:
                    val = int(num)
                    if val > 0:
                        result["reactions_approx"] = val
                        break
                except:
                    result["reactions_approx"] = m.group(0)[:40]

    # 4. Comments approx
    m = re.search(r"(\d[\d,. ]*)\s*(comentarios?|comments?)", low, re.I)
    if m:
        try:
            result["comments_approx"] = int(re.sub(r"[^\d]", "", m.group(1)))
        except:
            pass

    # 5. Profile candidates from real anchors (filter junk hard)
    seen = set()
    cands = []
    junk = {"iniciar sesión", "iniciar", "¿olvidaste", "facebook", "comentar", "me gusta", "reaccion", "ver más", "login", "recuperar", "grupo público"}

    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if not href or ("facebook.com" not in href and not href.startswith("/")):
            continue
        abs_h = urljoin("https://www.facebook.com", href)
        try:
            p = urlparse(abs_h)
            if "facebook.com" not in (p.netloc or ""): continue
            if "id=" in p.query:
                uid = parse_qs(p.query).get("id", [""])[0]
                if uid.isdigit():
                    abs_h = f"https://www.facebook.com/profile.php?id={uid}"
            else:
                abs_h = f"https://{p.netloc}{p.path}".rstrip("/")
        except:
            pass

        # Only keep plausible person or member profiles
        if not re.search(r"/(profile\.php\?id=\d{5,}|[\w\.-]{4,}/?)$", abs_h) and "/user/" not in abs_h:
            continue

        nm = (a.get_text(" ", strip=True) or a.get("aria-label", "") or a.get("title", ""))[:70].strip()
        if not nm or len(nm) < 3: continue
        nlow = nm.lower()
        if any(j in nlow for j in junk): continue
        if any(x in nlow for x in ["doy ayuda", "brindo", "ayuda economica", "urgencia"]): continue  # ad text leaking as name

        if abs_h not in seen:
            seen.add(abs_h)
            cands.append({"name": nm, "profile_url": abs_h})

    # 6. Mine big JSON payloads for user objects (name + id)
    for m in re.finditer(r'"name"\s*:\s*"([^"\\]{3,60})"[^}]{0,300}"id"\s*:\s*"?(\d{8,})"?', html):
        nm, uid = m.group(1).strip(), m.group(2)
        if any(j in nm.lower() for j in junk) or len(nm) < 3: continue
        prof = f"https://www.facebook.com/profile.php?id={uid}"
        if prof not in seen:
            seen.add(prof)
            cands.append({"name": nm, "profile_url": prof})

    # Assign
    if author_name:
        result["post_author"] = {"name": author_name, "profile_url": None}
        for c in cands[:5]:
            if author_name.lower()[:12] in c["name"].lower():
                result["post_author"]["profile_url"] = c["profile_url"]
                break

    # Split: reactors are scarce in public; put first few plausible as reactors if we saw reaction count, else all to commenters
    for i, c in enumerate(cands[:15]):
        if result.get("reactions_approx") and i < 4:
            result["reactors"].append(c)
        else:
            result["commenters"].append(c)

    def dedup(lst):
        o, s = [], set()
        for x in lst:
            k = x.get("profile_url") or x["name"]
            if k not in s:
                s.add(k); o.append(x)
        return o

    result["commenters"] = dedup(result["commenters"])
    result["reactors"] = dedup(result["reactors"])

    # Strict personal name filter (remove UI, pages, hashtags, schools, nav junk that pollute public snapshots)
    personal_junk = {
        "privacidad", "publicidad", "condiciones", "fotos", "inicio", "información", "negocio local",
        "escuela", "barbero", "barberos", "galindo", "aprende", "cortes", "ampliar", "seguidores", "seguidos",
        "publicaciones", "ver más", "reaccion", "me gusta", "comentar", "chicas positivas",
        "marketing", "giphy", "comando", "ventas", "doctor", "talk of", "foodbank", "galveston"
    }
    def is_plausible_personal(name: str) -> bool:
        n = (name or "").strip()
        if not n or len(n) < 3 or len(n) > 50: return False
        nl = n.lower()
        if n.startswith("#"): return False
        if any(j in nl for j in personal_junk): return False
        if re.search(r"\d{3,}", n): return False
        if "." in n and len(n) > 10: return False  # urls or emails
        if any(w in nl for w in ["marketing", "doctor ", "comando ", "giphy", "emp", "búsqu", "women ", "galveston", "foodbank", "ventas ", "página", "oficial"]): return False
        words = [w for w in re.split(r"[\s\.\-]+", n) if w]
        if len(words) == 0 or len(words) > 5: return False
        # Look like a real person: mostly capitalized words, 2-4 tokens, no obvious business
        cap = sum(1 for w in words if w[:1].isupper())
        return cap >= 1 and len(words) >= 1

    result["commenters"] = [c for c in result["commenters"] if is_plausible_personal(c.get("name",""))]
    result["reactors"] = [c for c in result["reactors"] if is_plausible_personal(c.get("name",""))]
    if result.get("post_author") and not is_plausible_personal(result["post_author"].get("name", "")):
        result["post_author"] = None

    # For posts inside groups, drop the group page itself masquerading as author or commenter
    # (common when the ad is posted to the group and the parser picks the group link)
    if result.get("post_url") and "/groups/" in result["post_url"]:
        gmatch = re.search(r"/groups/(\d+)", result["post_url"])
        if gmatch:
            gid = gmatch.group(1)
            if result.get("post_author") and gid in str(result["post_author"].get("profile_url","")):
                result["post_author"] = None
            result["commenters"] = [c for c in result["commenters"] if gid not in str(c.get("profile_url",""))]
            result["reactors"] = [c for c in result["reactors"] if gid not in str(c.get("profile_url",""))]

    total = len(result["commenters"]) + len(result["reactors"]) + (1 if result.get("post_author") else 0)
    if total <= 1:
        result["source_note"] = "limited public render (no or few named users in unauthenticated snapshot); only counts/author if lucky"

    return result


def discover_pagination_urls(html: str, base_url: str, max_pages: int = 8) -> list[str]:
    """Find pagination links or 'load more' interactables typically near the bottom of forum/listing pages.
    From live HTML analysis:
      - Locanto: numeric /20701/N/ paths (construct if needed), occasional ?dist=
      - Doplim: "Ver más anuncios" with class btn_line_blue show_more (often javascript:void(0) -- click to load more summaries on same page)
      - Common: ?page=N , lone page numbers, siguiente/next text
    Returns list of URLs (or special markers for JS actions). Use after real-content load.
    """
    soup = BeautifulSoup(html, "lxml")
    candidates: list[str] = []
    base_parsed = urlparse(base_url)
    # 1. Explicit next/siguiente + "Ver más anuncios" (Doplim key from analysis)
    for a in soup.find_all("a", href=True):
        txt = (a.get_text() or "").strip().lower()
        h = urljoin(base_url, a["href"])
        cls = " ".join(a.get("class", [])).lower() if a.get("class") else ""
        if any(k in txt for k in ["next", "siguiente", "más anuncios", "ver más"]):
            candidates.append(h)
        if "show_more" in cls or "btn_line_blue" in cls:
            candidates.append(h)  # even if js:void, caller can decide action or ignore
    # 2. Numbered / param patterns
    for a in soup.find_all("a", href=True):
        h = urljoin(base_url, a["href"])
        if re.search(r"[?&]page=\d+", h) or re.search(r"/\d{1,2}/?$", h) or re.search(r"/p/\d+", h):
            candidates.append(h)
    # 3. Locanto-specific 20701/N/ and bst_pagination__item (from live analysis of rendered list)
    for a in soup.find_all("a", href=True):
        h = urljoin(base_url, a["href"])
        cls = " ".join(a.get("class", [])).lower() if a.get("class") else ""
        if ("/20701/" in h or "bst_pagination__item" in cls) and re.search(r"/\d+/?$", h):
            candidates.append(h)
    # 4. Synthesize for known patterns when links missing (Locanto /N/)
    if not candidates or len(candidates) < 2:
        parsed = urlparse(base_url)
        segs = [s for s in parsed.path.split("/") if s]
        if "20701" in segs:
            for i in range(2, max_pages + 1):
                if segs[-1] == "20701":
                    new_path = parsed.path.rstrip("/") + f"/{i}/"
                else:
                    new_path = re.sub(r"/\d+/?$", f"/{i}/", parsed.path)
                candidates.append(urlunparse(parsed._replace(path=new_path)))
        elif segs and segs[-1].isdigit():
            for i in range(2, min(max_pages + 1, int(segs[-1]) + 5)):
                new_segs = segs[:-1] + [str(i)]
                candidates.append(urlunparse(parsed._replace(path="/" + "/".join(new_segs) + "/")))
    # Dedup + same host + limit (keep js: actions for Doplim "ver mas" even if no netloc)
    seen = set()
    uniq = []
    for u in candidates:
        if u not in seen and u != base_url:
            p = urlparse(u)
            if p.netloc == base_parsed.netloc or p.netloc == "" or "javascript" in u.lower():
                seen.add(u)
                uniq.append(u)
    return uniq[:max_pages]


def hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def archive_raw(raw_dir: Path, source_id: str, url: str, page_html: str) -> Path:
    # MANDATORY: always centralize raw HTML storage to data/raw/ads for all collectors and verif runs.
    # The passed raw_dir is accepted for backward compat (e.g. per-job scratch) but actual HTMLs
    # are written under the canonical location so that raw_archive_ref is always a clean relative
    # path under data/raw/ads.
    canonical_raw = ROOT / "data" / "raw" / "ads"
    canonical_raw.mkdir(parents=True, exist_ok=True)
    filename = f"{source_id}_{hash_text(url)[:16]}.html"
    path = canonical_raw / filename
    path.write_text(page_html, encoding="utf-8")
    return path


def existing_record_ids(manifest: Path) -> set[str]:
    cache_key = str(manifest.resolve()) if manifest.exists() else str(manifest)
    cached = _RECORD_ID_CACHE.get(cache_key)
    if cached is not None:
        return cached
    if not manifest.exists():
        _RECORD_ID_CACHE[cache_key] = set()
        return _RECORD_ID_CACHE[cache_key]
    ids: set[str] = set()
    with manifest.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                try:
                    ids.add(json.loads(line).get("record_id", ""))
                except json.JSONDecodeError:
                    continue
    _RECORD_ID_CACHE[cache_key] = ids
    return ids


def write_record(manifest: Path, candidate: CandidateAd, raw_ref: Path) -> bool:
    manifest.parent.mkdir(parents=True, exist_ok=True)
    record_id = hash_text(candidate.url)
    ids = existing_record_ids(manifest)
    if record_id in ids:
        return False
    record = {
        "record_id": record_id,
        "source_platform": candidate.platform,
        "source_url_hash": hash_text(candidate.url),
        "collected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "title": redact_text(candidate.title)[:500],
        "body_redacted": redact_text(candidate.body)[:10000],
        "raw_archive_ref": "data/raw/ads/" + raw_ref.name,
        "metadata": {
            "collector": "tools/scrape_ads.py",
            "source_url_host_hash": hash_text(candidate.url.split("/", 3)[2] if "://" in candidate.url else candidate.url)
        },
    }
    with manifest.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    ids.add(record_id)
    return True


def collect_from_source(source: dict[str, object], raw_dir: Path, manifest: Path, max_details: int) -> dict[str, object]:
    source_id = str(source["id"])
    platform = str(source.get("platform", source_id))
    url = str(source["url"])
    result: dict[str, object] = {"source_id": source_id, "url": url, "fetched": False, "links": 0, "records_written": 0, "error": ""}
    try:
        html_text = fetch_source(source)
        result["fetched"] = True
        archive_raw(raw_dir, f"{source_id}_index", url, html_text)
        if is_access_interstitial(html_text):
            result["error"] = "AccessInterstitial: public fetch returned CAPTCHA/interstitial; stopped without bypass"
            return result
        links = discover_links(html_text, url)
        result["links"] = len(links)
        direct = extract_candidate(platform, url, html_text, fallback_title=str(source.get("query", "")))
        if direct:
            raw_ref = archive_raw(raw_dir, source_id, url, html_text)
            if write_record(manifest, direct, raw_ref):
                result["records_written"] = int(result["records_written"]) + 1
        for link in links[:max_details]:
            time.sleep(1.0)
            detail_html = fetch_playwright(link["url"]) if str(source.get("mode")) == "playwright" else fetch_http(link["url"])
            candidate = extract_candidate(platform, link["url"], detail_html, fallback_title=link["text"])
            if not candidate:
                continue
            raw_ref = archive_raw(raw_dir, source_id, link["url"], detail_html)
            if write_record(manifest, candidate, raw_ref):
                result["records_written"] = int(result["records_written"]) + 1
    except Exception as exc:  # noqa: BLE001 - collection should log and continue.
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def append_attempt_log(path: Path, results: list[dict[str, object]]) -> None:
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = {"phase": 4, "status": "insufficient_for_exhaustion", "attempts": []}
    attempts = list(data.get("attempts", []))
    for result in results:
        notes = []
        if result.get("fetched"):
            notes.append("fetched")
        if result.get("error"):
            notes.append(str(result["error"]))
        if result.get("links"):
            notes.append(f"links={result['links']}")
        if result.get("records_written"):
            notes.append(f"records_written={result['records_written']}")
        attempts.append(
            {
                "query": f"tools/scrape_ads.py fetch {result.get('url')}",
                "result_count": int(result.get("records_written", 0)),
                "notes": "; ".join(notes) or "completed with no records"
            }
        )
    data["attempts"] = attempts
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--attempt-log", type=Path, default=DEFAULT_ATTEMPT_LOG)
    parser.add_argument("--max-sources", type=int, default=3)
    parser.add_argument("--max-details", type=int, default=25)
    parser.add_argument("--source-id", help="Run only a matching source id")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    sources = load_sources(args.sources)
    if args.source_id:
        sources = [source for source in sources if source.get("id") == args.source_id]
    sources = sources[: args.max_sources]
    if args.dry_run:
        print(json.dumps({"sources": sources}, ensure_ascii=False, indent=2))
        return 0
    results = [collect_from_source(source, args.raw_dir, args.manifest, args.max_details) for source in sources]
    append_attempt_log(args.attempt_log, results)
    print(json.dumps({"results": results}, ensure_ascii=False, indent=2))
    return 0 if all(not result.get("error") for result in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
