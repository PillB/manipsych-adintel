#!/usr/bin/env python3
"""High-throughput Locanto Peru HBM collector (Doplim-style two-phase).

Phase A options:
  - mine: extract /ID_ URLs from existing listing HTML under data/raw/ads
  - crawl: Playwright list pages /{city}/Hombre-busca-mujer/20701/N/?query=...
    (main cards only: article.posting_listing; HTTP lists usually 403)

Phase B: parallel detail fetch (HTTP first, Playwright on inter/short) + quality
+ relevance gates; archive under data/raw/ads as locanto_fast_*.html

Optimal defaults learned 2026-07:
  - List: filtered ?query=ayuda+economica, /N/ pagination, main article.posting_listing
  - Expect 19–50+ IDs/page; stop after 3 consecutive low-yield pages
  - Detail: es-PE, google.pe Referer, len gates, no cargando/un momento
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse, parse_qsl, urlencode

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.scrape_ads import (  # noqa: E402
    archive_raw,
    extract_ad_detail_urls,
    fetch_playwright,
    has_substantial_ad_content,
    is_access_interstitial,
    text_from_html,
)

RAW = ROOT / "data" / "raw" / "ads"
SCR = ROOT / "SCRATCH" / "implementer"

CITIES = [
    "lima", "arequipa", "trujillo", "cusco", "piura", "chiclayo", "callao",
    "huancayo", "ica", "tacna", "puno", "cajamarca", "chimbote", "ayacucho",
]

POS = re.compile(
    r"ayuda\s*econ|apoyo\s*econ|brindo|doy ayuda|doy apoyo|ofrezco|"
    r"caballero|discreta|universitaria|se[nñ]orita|madre soltera|"
    r"hombre busca|encuentro|\bsexo\b|busco (mujer|chica)|solvente",
    re.I,
)
NEG = re.compile(
    r"peugeot|toyota|alquiler de|vendo (auto|casa)|herramienta|curso de matem",
    re.I,
)

_lock = threading.Lock()
_counts = {"saved": 0, "skip": 0, "err": 0}
_seen: set[str] = set()


def log(path: Path, msg: str) -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def ad_id(url: str) -> str | None:
    m = re.search(r"/ID_(\d+)/", url, re.I)
    return m.group(1) if m else None


def h16(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def count_locanto_detail() -> int:
    """Count Locanto *detail* ad HTML only (not list pages).

    Prefer explicit collector prefixes. Content heuristic: Locanto host + single-ad
    markers and few listing cards across the full file (not just first 3k).
    """
    n = 0
    detail_prefixes = (
        "locanto_fast_",
        "locanto_detail",
        "locanto_hombre",
        "hombre_busca_mujer",
        "hombre_busca_mujer_real",
    )
    list_prefixes = ("lima_p", "cusco_p", "arequipa_p", "trujillo_p", "sect_p", "list_", "piura_p", "chiclayo_p")
    for p in RAW.glob("*.html"):
        name = p.name.lower()
        if any(name.startswith(pref) for pref in detail_prefixes):
            n += 1
            continue
        if any(name.startswith(pref) for pref in list_prefixes):
            continue
        if name.startswith(("doplim", "evisos", "facebook", "fb_", "dop")):
            continue
        try:
            t = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        low = t.lower()
        if "locanto.com.pe" not in low and "locanto" not in name:
            continue
        cards = low.count("posting_listing")
        if cards >= 6:
            continue  # listing page
        # detail: one ID_ in URL path patterns + substantial size + h1
        if len(t) < 2500:
            continue
        if re.search(r"/id_\d+/[^\"'\s]+\.html", low) and re.search(r"<h1[\s>]", low):
            n += 1
    return n


def already(url: str) -> bool:
    """O(1) membership via prebuilt _seen (no per-URL filesystem globs)."""
    iid = ad_id(url)
    if iid and iid in _seen:
        return True
    return h16(url) in _seen


def index_seen() -> None:
    """Build set of known URL hashes and Locanto IDs once."""
    for p in RAW.glob("*.html"):
        if "_" in p.name:
            h = p.name.rsplit("_", 1)[-1].replace(".html", "")
            if len(h) == 16 and all(c in "0123456789abcdef" for c in h):
                _seen.add(h)
        meta = p.with_suffix(".meta.json")
        if meta.exists():
            try:
                data = json.loads(meta.read_text(encoding="utf-8"))
                u = data.get("url") or ""
                if u:
                    _seen.add(h16(u))
                    iid = ad_id(u)
                    if iid:
                        _seen.add(iid)
            except Exception:
                pass
        # Tagged detail names sometimes embed nothing; scan only small tagged files for ID_
        name = p.name.lower()
        if name.startswith(("locanto_fast_", "locanto_detail", "locanto_hombre", "hombre_busca")):
            try:
                head = p.read_text(encoding="utf-8", errors="ignore")[:8000]
                for m in re.finditer(r"/ID_(\d+)/", head, re.I):
                    _seen.add(m.group(1))
            except Exception:
                pass


def mine_from_raw() -> list[dict]:
    urls: dict[str, str] = {}
    for f in RAW.glob("*.html"):
        t = f.read_text(encoding="utf-8", errors="ignore")
        if not re.search(r"/ID_\d+/", t, re.I):
            continue
        for m in re.finditer(
            r"https?://(?:www\.)?locanto\.com\.pe/[^\"'\s<>]+/ID_(\d+)/[^\"'\s<>]*",
            t,
            re.I,
        ):
            u = m.group(0).split("&")[0].rstrip("'\"")
            urls[m.group(1)] = u
        for m in re.finditer(r'href=["\']([^"\']*/ID_(\d+)/[^"\']*)["\']', t, re.I):
            path = m.group(1)
            if path.startswith("/"):
                path = "https://www.locanto.com.pe" + path
            if "locanto" not in path:
                continue
            urls[m.group(2)] = path.split("?")[0]
    return [{"url": u, "id": i, "platform": "locanto"} for i, u in urls.items()]


def listing_url(city: str, page: int, query: str) -> str:
    q = urlencode({"query": query})
    if page <= 0:
        return f"https://www.locanto.com.pe/{city}/Hombre-busca-mujer/20701/?{q}"
    return f"https://www.locanto.com.pe/{city}/Hombre-busca-mujer/20701/{page}/?{q}"


def crawl_lists(log_path: Path, cities: list[str], max_pages: int, queries: list[str]) -> list[dict]:
    from playwright.sync_api import sync_playwright

    chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    allc: dict[str, dict] = {}
    with sync_playwright() as p:
        kwargs = {"headless": True, "args": ["--no-sandbox", "--disable-dev-shm-usage"]}
        if Path(chrome).exists():
            kwargs["executable_path"] = chrome
        browser = p.chromium.launch(**kwargs)
        ctx = browser.new_context(
            locale="es-PE",
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
            ),
            extra_http_headers={
                "Accept-Language": "es-PE,es;q=0.9",
                "Referer": "https://www.google.com.pe/",
            },
        )
        page = ctx.new_page()
        for city in cities:
            for query in queries:
                low_streak = 0
                for pi in range(0, max_pages):
                    url = listing_url(city, pi, query)
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=70000)
                        page.wait_for_timeout(random.randint(4000, 8000))
                        try:
                            page.wait_for_selector(
                                "article.posting_listing, a[href*='/ID_']", timeout=20000
                            )
                        except Exception:
                            pass
                        page.wait_for_timeout(2000)
                        html = page.content()
                        if is_access_interstitial(html) or len(html) < 2500:
                            log(log_path, f"LIST inter/short {url} len={len(html)}")
                            low_streak += 1
                            if low_streak >= 3:
                                break
                            time.sleep(random.uniform(5, 12))
                            continue
                        ids = extract_ad_detail_urls(html, url, platform_hint="locanto")
                        # fallback unscoped if extract empty but cards present
                        if len(ids) < 5:
                            for a in BeautifulSoup(html, "lxml").select(
                                "article.posting_listing a[href*='/ID_']"
                            ):
                                h = urljoin(url, a["href"])
                                if re.search(r"/ID_\d+/", h) and h not in ids:
                                    ids.append(h)
                        new = 0
                        for u in ids:
                            iid = ad_id(u)
                            if iid and iid not in allc:
                                allc[iid] = {
                                    "url": u.split("?")[0],
                                    "id": iid,
                                    "platform": "locanto",
                                    "city": city,
                                    "query": query,
                                }
                                new += 1
                        log(
                            log_path,
                            f"LIST {city} p{pi} q={query!r}: ids={len(ids)} new={new} total={len(allc)}"
                            + (" OK10+" if len(ids) >= 10 else ""),
                        )
                        if len(ids) < 5 or new < 3:
                            low_streak += 1
                        else:
                            low_streak = 0
                        if low_streak >= 3:
                            break
                        time.sleep(random.uniform(1.5, 3.5))
                    except Exception as e:
                        log(log_path, f"LIST ERR {url}: {e}")
                        low_streak += 1
                        if low_streak >= 3:
                            break
        browser.close()
    return list(allc.values())


def quality(html: str, url: str) -> tuple[bool, str]:
    if not html or len(html) < 2000:
        return False, "short"
    if is_access_interstitial(html):
        return False, "inter"
    low = html.lower()[:3500]
    if any(k in low for k in ("cargando", "un momento", "verificando tu navegador")):
        return False, "loading"
    if not has_substantial_ad_content(html, url):
        return False, "thin"
    return True, "ok"


def relevant(html: str, url: str) -> tuple[bool, str]:
    soup = BeautifulSoup(html, "lxml")
    title = ""
    if soup.find("h1"):
        title = soup.find("h1").get_text(" ", strip=True)
    elif soup.title:
        title = soup.title.get_text(strip=True)
    body = text_from_html(html)[:5500]
    hay = f"{title} {body} {url}"
    if NEG.search(hay) and not POS.search(hay):
        return False, "junk"
    if not POS.search(hay):
        return False, "not_relevant"
    return True, title[:120]


def fetch_detail(url: str) -> str:
    # HTTP rarely works on Locanto; still try once
    try:
        s = requests.Session()
        s.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "es-PE,es;q=0.9",
                "Referer": "https://www.google.com.pe/",
            }
        )
        r = s.get(url, timeout=25)
        if r.status_code == 200 and len(r.text) > 3000 and not is_access_interstitial(r.text):
            ok, _ = quality(r.text, url)
            if ok:
                return r.text
    except Exception:
        pass
    try:
        # Fewer retries for throughput; serial PW is the bottleneck
        return fetch_playwright(url, timeout_ms=50000, max_retries=2) or ""
    except Exception:
        return ""


def process_one(card: dict, log_path: Path, target: int, start_n: int, tag: str = "locanto_fast") -> None:
    url = card["url"]
    with _lock:
        if start_n + _counts["saved"] >= target:
            return
        if already(url):
            _counts["skip"] += 1
            return
    html = fetch_detail(url)
    ok, reason = quality(html, url)
    if not ok:
        with _lock:
            _counts["skip"] += 1
        return
    rel, title = relevant(html, url)
    if not rel:
        with _lock:
            _counts["skip"] += 1
        return
    with _lock:
        if start_n + _counts["saved"] >= target:
            return
        if already(url):
            _counts["skip"] += 1
            return
        path = archive_raw(RAW, tag, url, html)
        meta = {
            "url": url,
            "platform": "locanto",
            "title": title,
            "saved_at": datetime.now(timezone.utc).isoformat() + "Z",
            "collector": "collect_locanto_fast",
            "raw_archive_ref": f"data/raw/ads/{path.name}",
        }
        try:
            path.with_suffix(".meta.json").write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass
        iid = ad_id(url)
        if iid:
            _seen.add(iid)
        _seen.add(h16(url))
        _counts["saved"] += 1
        n = _counts["saved"]
    if n % 10 == 0 or n <= 5:
        log(log_path, f"SAVED {n} total~{start_n+n} title={title[:55]!r} {path.name}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=1500)
    ap.add_argument("--mode", choices=("mine", "crawl", "both", "seeds"), default="both")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--max-pages", type=int, default=30)
    ap.add_argument("--cities", default=",".join(CITIES[:8]))
    ap.add_argument(
        "--queries",
        default="ayuda economica,apoyo economico,brindo ayuda,doy ayuda",
    )
    ap.add_argument("--seeds-in", type=Path, default=None, help="JSONL seeds (skip mine/crawl)")
    ap.add_argument("--shard", type=int, default=0, help="Shard index (0-based)")
    ap.add_argument("--shards", type=int, default=1, help="Total shards for parallel processes")
    ap.add_argument("--tag", default="locanto_fast", help="archive_raw source tag")
    args = ap.parse_args()

    RAW.mkdir(parents=True, exist_ok=True)
    SCR.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    log_path = SCR / f"locanto_fast_{ts}.log"
    index_seen()
    # Count only tagged detail archives for target (locanto_fast_ is authoritative for this tool)
    start_tagged = len(list(RAW.glob("locanto_fast_*.html"))) + len(
        list(RAW.glob("locanto_detail*.html"))
    ) + len(list(RAW.glob("locanto_hombre*.html"))) + len(
        list(RAW.glob("hombre_busca_mujer*.html"))
    )
    start_n = start_tagged
    log(
        log_path,
        f"START locanto_fast target={args.target} start_tagged_detail={start_n} "
        f"content_heuristic≈{count_locanto_detail()} mode={args.mode}",
    )
    if start_n >= args.target:
        log(log_path, f"EXIT early: tagged Locanto detail count already meets target ({start_n}>={args.target})")
        return 0

    cards: list[dict] = []
    if args.seeds_in and args.seeds_in.exists():
        for line in args.seeds_in.read_text(encoding="utf-8").splitlines():
            if line.strip():
                cards.append(json.loads(line))
        log(log_path, f"LOADED seeds_in={len(cards)} from {args.seeds_in}")
    else:
        if args.mode in ("mine", "both"):
            mined = mine_from_raw()
            log(log_path, f"MINED {len(mined)} IDs from raw listing archives")
            cards.extend(mined)
        if args.mode in ("crawl", "both") and start_n + len(cards) < args.target * 2:
            cities = [c.strip() for c in args.cities.split(",") if c.strip()]
            queries = [q.strip() for q in args.queries.split(",") if q.strip()]
            crawled = crawl_lists(log_path, cities, args.max_pages, queries)
            log(log_path, f"CRAWLED {len(crawled)} IDs")
            byid = {c["id"]: c for c in cards}
            for c in crawled:
                byid[c["id"]] = c
            cards = list(byid.values())

        seeds = SCR / f"seeds_locanto_fast_{ts}.jsonl"
        with seeds.open("w", encoding="utf-8") as fh:
            for c in cards:
                fh.write(json.dumps(c, ensure_ascii=False) + "\n")
        log(log_path, f"seeds {len(cards)} -> {seeds}")

    # Drop already-archived IDs before scheduling work
    pending = [c for c in cards if not already(c["url"])]
    # Shard for multi-process parallel (each process serial Playwright)
    if args.shards > 1:
        pending = [c for i, c in enumerate(pending) if i % args.shards == args.shard]
        log(log_path, f"shard {args.shard}/{args.shards} size={len(pending)}")
    log(log_path, f"pending after dedup/shard={len(pending)} (from {len(cards)})")
    random.shuffle(pending)
    t0 = time.time()
    log(log_path, f"FETCH start pending={len(pending)} mode=serial_playwright tag={args.tag}")
    for done, c in enumerate(pending, 1):
        try:
            process_one(c, log_path, args.target, start_n, tag=args.tag)
        except Exception as e:
            _counts["err"] += 1
            log(log_path, f"err {e}")
        if done % 5 == 0 or _counts["saved"] <= 3:
            elapsed = max(time.time() - t0, 0.1)
            rate = _counts["saved"] / elapsed * 60
            log(
                log_path,
                f"PROGRESS done={done}/{len(pending)} saved={_counts['saved']} "
                f"skip={_counts['skip']} rate={rate:.1f}/min "
                f"tagged={start_n + _counts['saved']}",
            )
        if start_n + _counts["saved"] >= args.target:
            break
        time.sleep(random.uniform(0.2, 0.6))

    end_tagged = start_n + _counts["saved"]
    end_n = count_locanto_detail()
    summary = {
        "start_tagged": start_n,
        "end_tagged": end_tagged,
        "end_detail_heuristic": end_n,
        "saved": _counts["saved"],
        "skip": _counts["skip"],
        "err": _counts["err"],
        "candidates": len(cards),
        "pending": len(pending),
        "elapsed_s": round(time.time() - t0, 1),
        "log": str(log_path),
    }
    (SCR / f"locanto_fast_summary_{ts}.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    log(log_path, f"FINAL {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
