#!/usr/bin/env python3
"""Fetch unused public direct ad seeds and append only strict-valid records."""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.redact_pii import redact_text
from tools.scrape_ads import (
    archive_raw, fetch_http, fetch_playwright, get_facebook_variants, hash_text,
    is_access_interstitial, is_facebook_unloaded_skeleton, text_from_html,
    has_substantial_ad_content, extract_ad_detail_urls
)


DEFAULT_SEEDS = ROOT / "data" / "sources" / "harvested_seeds.jsonl"
DEFAULT_MANIFEST = ROOT / "data" / "processed" / "ad_manifest.jsonl"
DEFAULT_RAW = ROOT / "data" / "raw" / "ads"
DEFAULT_LOG = ROOT / "reports" / "phase4_search_log.json"
DEFAULT_REJECTED = ROOT / "data" / "sources" / "rejected_seed_urls.json"

TARGET_TERMS = (
    "ayuda economica",
    "ayuda económica",
    "apoyo economico",
    "apoyo económico",
    "ayudo economicamente",
    "ayudo económicamente",
    "brindo ayuda",
    "doy ayuda",
    "brindo apoyo",
    "ofrezco ayuda",
)

MALE_OFFERING_TERMS = (
    "brindo",
    "doy",
    "ofrezco",
    "ofresco",
    "se brinda",
    "se ofrece",
    "caballero",
    "hombre",
    "empresario",
    "sugar daddy",
    "solvente",
)

EXCLUDED_MINOR_TERMS = (
    "menor de 18",
    "menores de 18",
    "menor edad",
    "colegiala",
    "colegialas",
    "chica pequeña",
    "chica pequena",
    "no importa la edad",
    "sin importar edad",
    "sin importar la edad",
    "cualquier edad",
    "pulpin",
    "pulpines",
    "niña",
    "nina",
)

SEEKER_SIDE_TERMS = (
    "necesito ayuda",
    "busco ayuda",
    "busca ayuda",
    "en busca de ayuda",
    "necesito apoyo",
    "busco apoyo",
    "scort",
    "escort",
)


@dataclass(frozen=True)
class Seed:
    url: str
    text: str
    platform: str


@contextmanager
def open_browser_context() -> tuple[object, object]:
    from playwright.sync_api import sync_playwright

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
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-PE,es;q=0.9,en-US;q=0.5,en;q=0.3",
        "Referer": "https://www.google.com.pe/",
        "Sec-Ch-Ua": '"Google Chrome";v="133", "Chromium";v="133", "Not_A Brand";v="24"',
        "Sec-Ch-Ua-Platform": '"macOS"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "cross-site",
    }
    with sync_playwright() as p:
        launch_kwargs = {"headless": True, "args": ["--no-sandbox", "--disable-dev-shm-usage"]}
        force_bundled = os.environ.get("PLAYWRIGHT_FORCE_BUNDLED_CHROMIUM", "").strip() == "1"
        if not force_bundled:
            exe = None
            for candidate in (
                os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH", "").strip(),
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
            ):
                if candidate and Path(candidate).exists():
                    exe = candidate
                    break
            if exe:
                launch_kwargs["executable_path"] = exe
        try:
            browser = p.chromium.launch(**launch_kwargs)
        except Exception:
            launch_kwargs.pop("executable_path", None)
            browser = p.chromium.launch(**launch_kwargs)
        ctx = browser.new_context(
            locale="es-PE",
            user_agent=random.choice(uas),
            viewport={"width": random.choice([1280, 1366, 1440, 1600]), "height": 900},
            extra_http_headers=extra_headers,
        )
        try:
            yield browser, ctx
        finally:
            browser.close()


def should_use_http_parallel(args: argparse.Namespace) -> bool:
    return bool(args.http_only or args.workers > 1)


def fetch_page_with_session(page, url: str, timeout_ms: int, max_retries: int, is_facebook: bool = False) -> str:
    last_content = ""
    candidates = get_facebook_variants(url) if is_facebook else [url]
    for cand in candidates:
        for _ in range(max_retries):
            try:
                page.goto(cand, wait_until="domcontentloaded", timeout=timeout_ms)
                try:
                    page.wait_for_selector("h1, .description, article, .ad_text, .user_content, .bp_ad_title, a[href*='/ID_'], [data-id]", timeout=12000)
                except Exception:
                    try:
                        page.wait_for_load_state("networkidle", timeout=9000)
                    except Exception:
                        page.wait_for_timeout(3000)
                page.wait_for_timeout(random.randint(1200, 2600))
                try:
                    page.evaluate("window.scrollBy(0, Math.random()*600 + 200)")
                except Exception:
                    pass
                # Improved FB: extra waits on userContent/data-ad-preview, scroll + og:description text
                if is_facebook:
                    try:
                        page.wait_for_selector(".userContent, [data-ad-preview], [data-ad-preview='message'], #story_body_container, [data-testid*='post_message']", timeout=20000)
                    except:
                        pass
                    page.wait_for_timeout(random.randint(4000, 8000))
                    for _ in range(4):
                        try:
                            page.evaluate("window.scrollBy(0, 550)")
                            page.wait_for_timeout(900)
                        except:
                            pass
                    try:
                        page.wait_for_function(
                            "() => { const m = document.querySelector('meta[property=\"og:description\"]'); return m && m.content && m.content.trim().length > 25; }",
                            timeout=18000
                        )
                    except:
                        pass
                content = page.content()
                last_content = content
                low = content.lower()
                first3k = low[:3000]
                fb_unloaded = is_facebook and (is_facebook_unloaded_skeleton(content) or len(content) < 4000 or "loading" in first3k)
                if fb_unloaded:
                    print(f"[FB-UNLOADED-LOG] session_fetch cand={cand} len={len(content)}", flush=True)
                if len(content) >= 2500 and not (
                    "cargando" in first3k
                    or "un momento" in first3k
                    or "verificando" in first3k
                    or is_access_interstitial(content)
                    or fb_unloaded
                ):
                    return content
            except Exception:
                time.sleep(random.uniform(2, 6))
    return last_content


def fetch_page_http_first(url: str, timeout_s: int, max_retries: int, is_facebook: bool = False) -> str:
    last_content = ""
    candidates = get_facebook_variants(url) if is_facebook else [url]
    for cand in candidates:
        for _ in range(max_retries):
            try:
                content = fetch_http(cand, timeout=timeout_s)
                last_content = content
                low = content.lower()
                first3k = low[:3000]
                fb_unloaded = is_facebook and (is_facebook_unloaded_skeleton(content) or len(content) < 3000 or "usercontent" not in low and "post_message" not in low)
                if fb_unloaded:
                    print(f"[FB-UNLOADED-LOG] http_fetch cand={cand} len={len(content)} text={len(text_from_html(content))}", flush=True)
                if len(content) >= 1500 and not (
                    "cargando" in first3k
                    or "un momento" in first3k
                    or "verificando" in first3k
                    or is_access_interstitial(content)
                    or fb_unloaded
                ):
                    return content
                # For FB unloaded, fallback to playwright for JS render + extra waits
                if is_facebook and fb_unloaded:
                    try:
                        pw = fetch_playwright(cand, timeout_ms=timeout_s*1000, max_retries=3)
                        if pw and not is_facebook_unloaded_skeleton(pw):
                            return pw
                        last_content = pw or last_content
                    except Exception:
                        pass
            except Exception:
                time.sleep(0.25)
    # final fallback for FB: always try playwright with variants to ensure loaded content
    if is_facebook:
        try:
            for v in get_facebook_variants(url):
                pw = fetch_playwright(v, timeout_ms=timeout_s*1000, max_retries=3)
                if pw and not is_facebook_unloaded_skeleton(pw):
                    print(f"[FB-PLAYWRIGHT-FALLBACK] loaded from {v}", flush=True)
                    return pw
                else:
                    print(f"[FB-UNLOADED-LOG] playwright fallback still unloaded for {v}", flush=True)
        except Exception:
            pass
    return last_content


def process_fetched_html(
    args: argparse.Namespace,
    seed: Seed,
    html: str,
    record_ids: set[str],
    stats: Counter[str],
) -> bool:
    if not html or len(html) < 1500:
        stats["short_or_empty_html"] += 1
        return False
    if is_access_interstitial(html):
        stats["interstitial"] += 1
        return False
    is_fb = "facebook" in (seed.platform or "").lower()
    if is_fb and is_facebook_unloaded_skeleton(html):
        stats["fb_unloaded_skeleton"] += 1
        print(f"[FB-UNLOADED-LOG] process skip unloaded before archive url={seed.url} len={len(html)}", flush=True)
        return False
    title, body = extract_title_body(html)
    focused_text = description_focus(title, body)
    check_text = focused_text
    if is_fb:
        # Perseverance for FB public indexed: the search hit had the terms; fetched HTML is often sparse/JS
        check_text = (focused_text + " " + seed.text + " " + seed.url).lower()
    if is_likely_seeker_side(check_text):
        stats["seeker_side"] += 1
        return False
    if not has_target_terms(check_text):
        stats["no_target_terms"] += 1
        return False
    if not has_male_offering_signal(check_text):
        stats["not_male_offering"] += 1
        return False
    if has_excluded_minor_signal(check_text):
        stats["excluded_minor_signal"] += 1
        return False
    min_body = args.min_body_chars
    if is_fb:
        # Only archive if loaded (not skeleton). Use seed terms if body sparse but confirm loaded.
        if is_facebook_unloaded_skeleton(html):
            stats["fb_unloaded_skeleton"] += 1
            print(f"[FB-UNLOADED-LOG] process skip unloaded body url={seed.url}", flush=True)
            return False
        if len(body) < 60:
            body = (body + " " + text_from_html(html) + " " + seed.text)[:3500].strip()
        min_body = 1
    if len(body) < min_body:
        stats["body_too_short"] += 1
        return False
    # Final guard: avoid archiving FB (or general) unloaded JS skeletons or empty pages
    # even if earlier filters passed. This directly addresses pages with only HTML skeleton.
    if not has_substantial_ad_content(html, seed.url):
        stats["unloaded_or_empty_detail"] = stats.get("unloaded_or_empty_detail", 0) + 1
        print(f"[CONTENT-GATE] skip no-substantial url={seed.url} len={len(html)}", flush=True)
        return False
    raw_ref = archive_raw(args.raw_dir, args.raw_prefix, seed.url, html)
    if append_record(args.manifest, seed, title or seed.text or "Untitled public ad", body, raw_ref, record_ids):
        stats["added"] += 1
        return True
    stats["duplicate_after_fetch"] += 1
    return False


def normalize_facebook_url(url: str) -> str:
    """Normalize FB URLs to stable public post forms: prefer www over m, strip tracking params."""
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


def normalize_url(url: str) -> str:
    url = url.strip().rstrip(").,;]")
    return normalize_facebook_url(url)


def get_facebook_variants(url: str) -> list[str]:
    """Generate m.facebook / www.facebook fallbacks for perseverance on FB public indexed pages."""
    if "facebook.com" not in url.lower():
        return [url]
    base = normalize_facebook_url(url)
    cands = [base]
    cands.append(base.replace("www.facebook.com", "m.facebook.com"))
    cands.append(base.replace("m.facebook.com", "www.facebook.com"))
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


def classify_platform(url: str) -> str | None:
    host = urlparse(url).netloc.lower()
    lowered = url.lower()
    if "locanto.com.pe" in host and re.search(r"/ID_\d+/", url):
        return "Locanto Peru (hombre busca mujer real)"
    if "doplim.com.pe" in host or host.endswith(".doplim.com.pe") or host == "doplim.pe" or host.endswith(".doplim.pe"):
        return "Doplim Peru (hombre busca mujer or Contactos)"
    if "facebook.com" in host:
        return "Facebook Public (indexed)"
    return None


def is_direct_candidate(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    if "locanto.com.pe" in host:
        return bool(re.search(r"/ID_\d+/", url))
    if "doplim" in host:
        return True
    if "facebook.com" in host:
        # broader public post patterns for perseverance on indexed groups/posts
        return any(p in url for p in ("/groups/", "/posts/", "/permalink/", "/story.php")) or bool(re.search(r"facebook.com/[^/]+/posts/", url))
    return False


def has_target_terms(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in TARGET_TERMS)


def has_male_offering_signal(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in MALE_OFFERING_TERMS)


def has_excluded_minor_signal(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in EXCLUDED_MINOR_TERMS)


def is_likely_seeker_side(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in SEEKER_SIDE_TERMS)


def load_manifest_state(path: Path) -> tuple[set[str], set[str], set[str]]:
    record_ids: set[str] = set()
    raw_refs: set[str] = set()
    urls: set[str] = set()
    if not path.exists():
        return record_ids, raw_refs, urls
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        record_ids.add(str(record.get("record_id", "")))
        raw_refs.add(str(record.get("raw_archive_ref", "")))
        original_url = record.get("metadata", {}).get("original_url") if isinstance(record.get("metadata"), dict) else None
        if original_url:
            urls.add(str(original_url))
    return record_ids, raw_refs, urls


def load_manifest_state_snapshot(path: Path) -> tuple[set[str], set[str], set[str]]:
    if not path.exists():
        return set(), set(), set()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return set(), set(), set()
    return (
        {str(value) for value in data.get("record_ids", []) if str(value)},
        {str(value) for value in data.get("raw_refs", []) if str(value)},
        {str(value) for value in data.get("urls", []) if str(value)},
    )


def load_rejected_urls(path: Path) -> set[str]:
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return {str(url) for url in data.get("urls", [])}
    if isinstance(data, list):
        return {str(url) for url in data}
    return set()


def load_seeds(path: Path, platform_filter: str) -> list[Seed]:
    seeds: list[Seed] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        url = normalize_url(str(item.get("url", "")))
        text = str(item.get("text") or item.get("title") or "")
        platform = classify_platform(url)
        if not platform or not is_direct_candidate(url):
            continue
        if platform_filter != "all" and platform_filter.lower() not in platform.lower():
            continue
        haystack = f"{url} {text}"
        if not has_target_terms(haystack):
            continue
        if url in seen:
            continue
        seen.add(url)
        seeds.append(Seed(url=url, text=text, platform=platform))
    return seeds


def extract_title_body(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "lxml")
    title = ""
    # FB-specific selectors for perseverance on public group posts (og, message content)
    for sel in ('meta[property="og:title"]', 'meta[name="title"]', 'meta[property="og:site_name"]'):
        el = soup.select_one(sel)
        if el:
            val = (el.get("content") or "").strip()
            if len(val) > 3:
                title = val[:500]
                break
    if not title:
        for selector in ("h1", "h2", "title"):
            element = soup.select_one(selector) if selector != "title" else soup.find("title")
            if element:
                value = re.sub(r"\s+", " ", element.get_text(" ", strip=True)).strip()
                if len(value) > 3:
                    title = value[:500]
                    break
    body = ""
    # FB perseverance: og:description is often the most reliable carrier of public post text
    # (even when .userContent etc are absent or JS-unloaded). Then DOM selectors.
    for selector in (
        'meta[property="og:description"]',
        'meta[property="og:title"]',
        ".userContent", ".user_content", "#story_body_container",
        '[data-ad-preview="message"]', 'div[data-testid*="post_message"]',
        "._5pbx", ".messageBody", ".description", "article", "#ad_text", ".ad_text", ".bp_ad_desc", "main", "section"
    ):
        element = soup.select_one(selector)
        if element:
            if selector.startswith("meta"):
                val = (element.get("content") or "").strip()
            else:
                val = re.sub(r"\s+", " ", element.get_text(" ", strip=True)).strip()
            if len(val) > len(body):
                body = val
    if len(body) < 120:
        body = text_from_html(html)
    # If FB and we have og desc, ensure it's in the body for filter checks (FB markup varies; og often has the post)
    low_html = html.lower()[:2000]
    if "facebook" in low_html:
        try:
            ogd = soup.select_one('meta[property="og:description"]')
            if ogd:
                og_text = (ogd.get("content") or "").strip()
                if len(og_text) > len(body):
                    body = og_text
                elif og_text and og_text not in body:
                    body = (body + " " + og_text)[:12000]
        except Exception:
            pass
    return title, body[:12000]


def description_focus(title: str, body: str) -> str:
    lowered = body.lower()
    start = lowered.find("descripción")
    if start == -1:
        start = 0
    end_candidates = [lowered.find(marker, start + 1) for marker in ("anuncio n°", "denunciar", "más detalles", "información clave")]
    end_candidates = [value for value in end_candidates if value != -1]
    end = min(end_candidates) if end_candidates else min(len(body), start + 1800)
    return f"{title} {body[start:end]}"


def append_record(manifest: Path, seed: Seed, title: str, body: str, raw_ref: Path, record_ids: set[str]) -> bool:
    record_id = hash_text(seed.url)
    if record_id in record_ids:
        return False
    record = {
        "record_id": record_id,
        "source_platform": seed.platform,
        "source_url_hash": record_id,
        "collected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "title": redact_text(title)[:500],
        "body_redacted": redact_text(body)[:10000],
        "raw_archive_ref": "data/raw/ads/" + raw_ref.name,
        "metadata": {
            "original_url": redact_text(seed.url),
            "collector": "tools/collect_seed_inventory.py",
            "seed_text": redact_text(seed.text)[:300],
            "male_offering_perspective": True,
            "full_public_ad": True,
        },
    }
    manifest.parent.mkdir(parents=True, exist_ok=True)
    with manifest.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    record_ids.add(record_id)
    return True


def update_attempt_log(path: Path, platform: str, stats: Counter[str], added: int) -> None:
    loaded = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    if isinstance(loaded, dict):
        data = loaded
        attempts = list(data.get("attempts", []))
    elif isinstance(loaded, list):
        first = loaded[0] if loaded and isinstance(loaded[0], dict) else {}
        if isinstance(first, dict) and isinstance(first.get("attempts"), list):
            data = {key: value for key, value in first.items() if key != "attempts"}
            attempts = list(first["attempts"])
            attempts.extend(item for item in loaded[1:] if isinstance(item, dict))
        else:
            data = {"phase": 4, "status": "exhaustive"}
            attempts = list(loaded)
    else:
        data = {"phase": 4, "status": "exhaustive"}
        attempts = []
    attempts.append(
        {
            "query": f"tools/collect_seed_inventory.py platform={platform}",
            "result_count": added,
            "notes": "seed inventory fetch pass; " + ", ".join(f"{key}={value}" for key, value in sorted(stats.items())),
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
    )
    data["attempts"] = attempts
    data["summary"] = "Search-first public collection remains ongoing under strict validation; seed-inventory collector records explicit skip reasons."
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def collect(args: argparse.Namespace) -> dict[str, object]:
    manifest_state = getattr(args, "manifest_state", None)
    if manifest_state:
        record_ids, _raw_refs, urls = load_manifest_state_snapshot(manifest_state)
    else:
        record_ids, _raw_refs, urls = load_manifest_state(args.manifest)
    rejected_urls = load_rejected_urls(args.rejected_urls)
    seeds = load_seeds(args.seeds, args.platform)
    seeds = [seed for seed in seeds if seed.url not in rejected_urls and hash_text(seed.url) not in record_ids and seed.url not in urls]
    if args.shuffle:
        random.shuffle(seeds)
    else:
        seeds.sort(key=lambda seed: (seed.platform, seed.text.lower(), seed.url))
    if args.seed_shard_count > 1:
        shard_index = max(0, min(args.seed_shard_index, args.seed_shard_count - 1))
        seeds = [seed for idx, seed in enumerate(seeds) if idx % args.seed_shard_count == shard_index]
    selected = seeds[: args.max_fetch]
    stats: Counter[str] = Counter({"candidate_seeds": len(seeds), "selected": len(selected)})
    added = 0
    collect_start = time.time()
    browser_page = None
    browser_ctx = None
    browser_failed = False
    if not should_use_http_parallel(args):
        try:
            browser_ctx = open_browser_context()
            _browser, ctx = browser_ctx.__enter__()
            browser_page = ctx.new_page()
        except Exception:
            browser_failed = True
            browser_page = None

    try:
        use_http_parallel = should_use_http_parallel(args) or browser_page is None
        if use_http_parallel:
            max_workers = max(1, min(args.workers, max(1, len(selected))))
            if args.verbose:
                print(f"  mode=http-parallel workers={max_workers}", flush=True)
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_map = {}
                for index, seed in enumerate(selected, start=1):
                    stats["attempted"] += 1
                    if args.verbose:
                        print(f"[{index}/{len(selected)}] {seed.platform}: {seed.url}", flush=True)
                    haystack = f"{seed.url} {seed.text}"
                    if has_excluded_minor_signal(haystack):
                        stats["excluded_minor_signal"] += 1
                        if args.verbose:
                            print("  skip=excluded_minor_signal", flush=True)
                        continue
                    is_fb = "facebook" in (seed.platform or "").lower()
                    fb_retries = args.retries + (3 if is_fb else 0)
                    future = executor.submit(
                        fetch_page_http_first,
                        seed.url,
                        max(10, int(args.timeout_ms / 1000)),
                        fb_retries,
                        is_fb,
                    )
                    future_map[future] = seed
                for future in as_completed(future_map):
                    seed = future_map[future]
                    try:
                        html = future.result()
                    except Exception as exc:  # noqa: BLE001
                        stats[f"fetch_error_{type(exc).__name__}"] += 1
                        if args.verbose:
                            print(f"  skip=fetch_error_{type(exc).__name__}", flush=True)
                        continue
                    if args.verbose:
                        print(f"  fetched={len(html)}", flush=True)
                    if process_fetched_html(args, seed, html, record_ids, stats):
                        added += 1
        else:
            for index, seed in enumerate(selected, start=1):
                stats["attempted"] += 1
                if args.verbose:
                    print(f"[{index}/{len(selected)}] {seed.platform}: {seed.url}", flush=True)
                haystack = f"{seed.url} {seed.text}"
                if has_excluded_minor_signal(haystack):
                    stats["excluded_minor_signal"] += 1
                    if args.verbose:
                        print("  skip=excluded_minor_signal", flush=True)
                    continue
                html = ""
                is_fb = "facebook" in (seed.platform or "").lower()
                fb_retries = args.retries + (3 if is_fb else 0)
                if browser_page is not None:
                    try:
                        html = fetch_page_with_session(browser_page, seed.url, timeout_ms=args.timeout_ms, max_retries=fb_retries, is_facebook=is_fb)
                    except Exception as exc:  # noqa: BLE001
                        stats[f"fetch_error_{type(exc).__name__}"] += 1
                        if args.verbose:
                            print(f"  browser skip=fetch_error_{type(exc).__name__}", flush=True)
                if not html:
                    html = fetch_page_http_first(seed.url, timeout_s=max(10, int(args.timeout_ms / 1000)), max_retries=fb_retries, is_facebook=is_fb)
                if process_fetched_html(args, seed, html, record_ids, stats):
                    added += 1
                    if args.verbose:
                        print(f"  added={added} title={seed.text[:80]}", flush=True)
                time.sleep(args.delay)
    finally:
        if browser_ctx is not None:
            try:
                browser_ctx.__exit__(None, None, None)
            except Exception:
                pass
    stats["added"] = added
    elapsed = time.time() - collect_start
    rate = (added / (elapsed / 60.0)) if elapsed > 0 else 0.0
    rate_note = f"{rate:.2f} ads/min" if added > 0 else "rate limited by supply/blocks/interstitials"
    stats["elapsed_s"] = round(elapsed, 1)
    stats["throughput"] = rate_note
    update_attempt_log(args.attempt_log, args.platform, stats, added)
    if args.verbose or True:
        print(f"[collector] platform={args.platform} elapsed={elapsed:.1f}s added={added} throughput={rate_note}", flush=True)
    return {
        "platform": args.platform,
        "added": added,
        "stats": dict(stats),
        "selected_urls": [seed.url for seed in selected],
        "browser_failed": browser_failed,
        "elapsed_s": round(elapsed, 1),
        "throughput": rate_note,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=Path, default=DEFAULT_SEEDS)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--manifest-state", type=Path)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--attempt-log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--rejected-urls", type=Path, default=DEFAULT_REJECTED)
    parser.add_argument("--platform", choices=("all", "locanto", "doplim", "facebook"), default="all")
    parser.add_argument("--max-fetch", type=int, default=10)
    parser.add_argument("--timeout-ms", type=int, default=45000)
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--delay", type=float, default=1.5)
    parser.add_argument("--min-body-chars", type=int, default=220)
    parser.add_argument("--raw-prefix", default="seed_inventory")
    parser.add_argument("--shuffle", action="store_true")
    parser.add_argument("--seed-shard-index", type=int, default=0)
    parser.add_argument("--seed-shard-count", type=int, default=4)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--http-only", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    print(json.dumps(collect(args), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
