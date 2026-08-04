#!/usr/bin/env python3
"""High-throughput Doplim + Evisos collector (iterative v2).

Learnings encoded:
- Doplim pagination is NOT only UI "Ver más"; it posts to public
  `/api/getAdsSearch` with page 1..10, catid/subcatid, query=city.
  ~30 main cards/page, max ~10 pages/city/section. HTTP-only.
- Doplim adult gate: cookie + list warm-up; detail pages usually plain HTTP 200.
- Doplim main cards: `li.cnt-list_ads` + `-id-N.html` (same in API HTML fragments).
- Evisos lists: `h2.title a` + `/clasificados/N` pagination; HTTP often works.
- Prior bottleneck: serial browser gather of all cities before any detail fetch.
  Fix: HTTP API gather + parallel HTTP detail + stream saves immediately.

Targets: archive valid detail HTML under data/raw/ads until N per platform.
Public only; no login/CAPTCHA bypass.
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
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.scrape_ads import (  # noqa: E402
    archive_raw,
    has_substantial_ad_content,
    is_access_interstitial,
    text_from_html,
)

RAW_DIR = ROOT / "data" / "raw" / "ads"
SCRATCH = ROOT / "SCRATCH" / "implementer"

# From live JS on /s/hombre-busca-mujer/lima/ and related section pages
DOPLIM_SECTIONS = {
    # name: (catid, subcatid) — learned from live getAdsSearch JS 2026-07-08
    "hombre-busca-mujer": ("5", "51"),
    "relaciones-ocasionales": ("5", "54"),
    "mujer-busca-hombre": ("5", "50"),
    "contactos": ("5", "0"),
}

DOPLIM_CITIES = [
    "lima", "arequipa", "trujillo", "cusco", "piura", "chiclayo", "callao",
    "huancayo", "ica", "tacna", "puno", "cajamarca", "chimbote", "ayacucho",
    "huancavelica", "iquitos", "tarapoto", "pucallpa", "juliaca", "sullana",
    "huaraz", "chincha", "tumbes", "moquegua", "abancay", "huanuco", "jaen",
]

EVISOS_BASES = [
    "https://www.evisos.com.pe/por-ayuda-economica.htm",
    "https://www.evisos.com.pe/apoyo-economico.htm",
    "https://www.evisos.com.pe/por-apoyo-economico.htm",
    "https://lima.evisos.com.pe/por-ayuda-economica.htm",
    "https://www.evisos.com.pe/brindo-ayuda.htm",
    "https://www.evisos.com.pe/doy-ayuda.htm",
    "https://www.evisos.com.pe/encuentros.htm",
    "https://lima.evisos.com.pe/encuentros.htm",
    "https://www.evisos.com.pe/por-encuentros.htm",
    "https://www.evisos.com.pe/hombre-busca-mujer.htm",
    "https://www.evisos.com.pe/por-hombre-busca-mujer.htm",
    "https://www.evisos.com.pe/contactos-ocasionales-peru.htm",
    "https://www.evisos.com.pe/relaciones-ocasionales.htm",
    "https://arequipa.evisos.com.pe/encuentros.htm",
    "https://trujillo.evisos.com.pe/encuentros.htm",
    "https://cusco.evisos.com.pe/encuentros.htm",
    "https://piura.evisos.com.pe/encuentros.htm",
    "https://chiclayo.evisos.com.pe/encuentros.htm",
]

POS = re.compile(
    r"ayuda\s*econ|apoyo\s*econ|brindo\s*(ayuda|apoyo)|doy\s*(ayuda|apoyo)|"
    r"hombre\s*busca|mujer\s*busca|relaciones?\s*ocasional|encuentro|"
    r"\bsexo\b|discreta|universitaria|se[nñ]orita|madre\s*soltera|caballero|"
    r"busco\s*(mujer|hombre|chica|pareja|alguien)|ofrezco\s*(sexo|apoyo|ayuda)|"
    r"soy\s*(hombre|var[oó]n|joven|pasivo|activo)|maduras?|chica|masaje|casual|soltera",
    re.I,
)
NEG = re.compile(
    r"peugeot|toyota|alquila\s*local|maleta|puertas?\s*levadiz|reaming|escariador|"
    r"calamina|aluzinc|operario\s*de\s*producci|baterista|guitarrista|fachaleta|"
    r"matematic|clases de |curso de ",
    re.I,
)

_LOG_LOCK = threading.Lock()
_SAVE_LOCK = threading.Lock()
_COUNTERS = {"doplim": 0, "evisos": 0, "skip": 0, "saved": 0, "err": 0}
_SEEN_URLS: set[str] = set()
_SEEN_IDS: set[str] = set()


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(path: Path, msg: str) -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    with _LOG_LOCK:
        print(line, flush=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def hash16(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def ad_id(url: str) -> str | None:
    m = re.search(r"-id-(\d+)", url, re.I)
    return m.group(1) if m else None


def make_session(platform: str) -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-PE,es;q=0.9,en-US;q=0.5,en;q=0.3",
            "Referer": "https://www.google.com.pe/",
            "Cache-Control": "no-cache",
        }
    )
    if platform == "doplim":
        s.headers["X-Requested-With"] = "XMLHttpRequest"
        s.headers["Origin"] = "https://www.doplim.com.pe"
        s.cookies.set("adult_content", "1", domain=".doplim.com.pe")
        s.cookies.set("adult", "1", domain=".doplim.com.pe")
        try:
            s.get("https://www.doplim.com.pe/s/hombre-busca-mujer/lima/", timeout=25)
        except Exception:
            pass
    return s


def learn_doplim_section_ids(session: requests.Session, log_path: Path) -> dict[str, tuple[str, str]]:
    """Parse live section pages for catid/subcatid in getAdsSearch JS."""
    learned = dict(DOPLIM_SECTIONS)
    for name in list(learned.keys()):
        url = f"https://www.doplim.com.pe/s/{name}/lima/"
        try:
            r = session.get(url, timeout=30, headers={"Referer": "https://www.doplim.com.pe/"})
            m = re.search(
                r"getAdsSearch[\s\S]{0,600}?['\"]catid['\"]?\s*:\s*['\"]?(\d+)['\"]?"
                r"[\s\S]{0,120}?['\"]subcatid['\"]?\s*:\s*['\"]?(\d+)",
                r.text,
            )
            if not m:
                m = re.search(r"catid:\s*'(\d+)'[,\s]*subcatid:\s*'(\d+)'", r.text)
            if m:
                learned[name] = (m.group(1), m.group(2))
                log(log_path, f"LEARN doplim section={name} catid={m.group(1)} subcatid={m.group(2)}")
            else:
                log(log_path, f"LEARN miss section={name} keep default {learned[name]}")
        except Exception as e:
            log(log_path, f"LEARN err {name}: {e}")
    return learned


def extract_doplim_urls(html: str, base: str = "https://www.doplim.com.pe") -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    out: list[dict] = []
    seen: set[str] = set()
    cards = soup.select("li.cnt-list_ads") or [soup]
    for card in cards:
        text = card.get_text(" ", strip=True) if card is not soup else ""
        for a in card.find_all("a", href=True):
            h = a["href"]
            if not re.search(r"-id-\d+\.html", h, re.I):
                continue
            if h.startswith("//"):
                h = "https:" + h
            elif h.startswith("/"):
                h = urljoin(base, h)
            aid = ad_id(h)
            if not aid or aid in seen:
                continue
            seen.add(aid)
            if not text:
                text = a.get_text(" ", strip=True)
            out.append({"url": h.split("?")[0], "id": aid, "text": text[:220], "platform": "doplim"})
    # fallback pure regex if no cards
    if not out:
        for m in re.finditer(r"https?://[a-z0-9.-]*doplim\.com\.pe/[^\"'\s]+-id-(\d+)\.html", html, re.I):
            aid = m.group(1)
            if aid in seen:
                continue
            seen.add(aid)
            out.append({"url": m.group(0), "id": aid, "text": "", "platform": "doplim"})
    return out


def extract_evisos_urls(html: str, base: str, loose: bool = True) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    out: list[dict] = []
    seen: set[str] = set()
    for a in soup.select("h2.title a, h2 a, .title a"):
        h = urljoin(base, a.get("href") or "")
        aid = ad_id(h)
        if not aid or aid in seen:
            continue
        block = a.find_parent("div") or a
        cat_el = block.select_one(".category-zone") if hasattr(block, "select_one") else None
        cat = cat_el.get_text(" ", strip=True) if cat_el else ""
        title = a.get_text(strip=True)
        desc_el = block.select_one(".desc") if hasattr(block, "select_one") else None
        desc = desc_el.get_text(" ", strip=True) if desc_el else ""
        hay = f"{cat} {title} {desc}"
        if NEG.search(hay) and not POS.search(hay):
            continue
        if not loose and not POS.search(hay):
            continue
        seen.add(aid)
        out.append(
            {
                "url": h.split("?")[0],
                "id": aid,
                "text": hay[:220],
                "title": title,
                "category": cat,
                "platform": "evisos",
            }
        )
    return out


def gather_doplim_api(
    session: requests.Session,
    sections: dict[str, tuple[str, str]],
    cities: list[str],
    log_path: Path,
    max_pages: int = 10,
    early_stop_unique: int = 0,
) -> list[dict]:
    """HTTP API gather. early_stop_unique>0 stops when enough unique IDs collected."""
    all_cards: dict[str, dict] = {}
    for section, (catid, subcatid) in sections.items():
        for city in cities:
            if early_stop_unique and len(all_cards) >= early_stop_unique:
                log(log_path, f"EARLY STOP gather at {len(all_cards)} unique (>= {early_stop_unique})")
                return list(all_cards.values())
            got_pages = 0
            empty_streak = 0
            for page in range(1, max_pages + 1):
                data = {
                    "page": page,
                    "cityid": "0",
                    "areaid": "0",
                    "catid": catid,
                    "subcatid": subcatid,
                    "query": city,
                    "gal": 0,
                    "price_min": "0",
                    "price_max": 0,
                    "sort_by": "",
                }
                try:
                    session.headers["Referer"] = f"https://www.doplim.com.pe/s/{section}/{city}/"
                    r = session.post(
                        "https://www.doplim.com.pe/api/getAdsSearch",
                        data=data,
                        timeout=25,
                    )
                    if r.status_code != 200 or len(r.text) < 200:
                        empty_streak += 1
                        log(log_path, f"API empty {section}/{city} p{page} status={r.status_code} len={len(r.text)}")
                        if empty_streak >= 2:
                            break
                        continue
                    cards = extract_doplim_urls(r.text)
                    new = 0
                    for c in cards:
                        c["section"] = section
                        c["city"] = city
                        if c["id"] not in all_cards:
                            all_cards[c["id"]] = c
                            new += 1
                    got_pages += 1
                    empty_streak = 0 if new else empty_streak + 1
                    log(
                        log_path,
                        f"API {section}/{city} p{page}: cards={len(cards)} new={new} total={len(all_cards)}",
                    )
                    if len(cards) < 5 or new == 0:
                        empty_streak += 1
                    if empty_streak >= 2:
                        break
                    if early_stop_unique and len(all_cards) >= early_stop_unique:
                        log(log_path, f"EARLY STOP gather at {len(all_cards)} unique")
                        return list(all_cards.values())
                    time.sleep(random.uniform(0.05, 0.2))
                except Exception as e:
                    log(log_path, f"API ERR {section}/{city} p{page}: {e}")
                    empty_streak += 1
                    if empty_streak >= 2:
                        break
            if got_pages and got_pages * 25 >= 10:
                log(log_path, f"OK 10+ path {section}/{city} pages={got_pages}")
    return list(all_cards.values())


def evisos_page_url(base: str, page: int) -> str:
    if page <= 1:
        return base
    if base.endswith(".htm"):
        return f"{base[:-4]}/clasificados/{page}"
    return f"{base.rstrip('/')}/clasificados/{page}"


def gather_evisos_http(
    session: requests.Session,
    log_path: Path,
    max_pages: int = 30,
) -> list[dict]:
    all_cards: dict[str, dict] = {}
    for base in EVISOS_BASES:
        low = 0
        prev_ids: set[str] = set()
        for page in range(1, max_pages + 1):
            url = evisos_page_url(base, page)
            try:
                r = session.get(url, timeout=30)
                if r.status_code != 200 or len(r.text) < 1500:
                    low += 1
                    log(log_path, f"EV skip {url} status={r.status_code} len={len(r.text)}")
                    if low >= 2:
                        break
                    continue
                cards = extract_evisos_urls(r.text, url, loose=True)
                page_ids = {c["id"] for c in cards}
                # detect pagination loop (same set as previous)
                if page > 1 and page_ids and page_ids == prev_ids:
                    log(log_path, f"EV loop detect {url}; stop base")
                    break
                prev_ids = page_ids
                new = 0
                for c in cards:
                    if c["id"] not in all_cards:
                        all_cards[c["id"]] = c
                        new += 1
                log(log_path, f"EV p{page} {url}: cards={len(cards)} new={new} total={len(all_cards)}")
                if len(cards) >= 10:
                    log(log_path, "  OK 10+ main cards")
                if new == 0:
                    low += 1
                else:
                    low = 0
                if low >= 3:
                    break
                time.sleep(random.uniform(0.1, 0.35))
            except Exception as e:
                log(log_path, f"EV ERR {url}: {e}")
                low += 1
                if low >= 2:
                    break
    return list(all_cards.values())


def quality_ok(html: str, url: str) -> tuple[bool, str]:
    if not html or len(html) < 1800:
        return False, "short"
    if is_access_interstitial(html):
        return False, "inter"
    low = html.lower()[:3000]
    if any(k in low for k in ("cargando", "un momento", "verificando tu navegador")):
        return False, "loading"
    if not has_substantial_ad_content(html, url):
        return False, "thin"
    return True, "ok"


def relevant(html: str, url: str, platform: str) -> tuple[bool, str]:
    soup = BeautifulSoup(html, "lxml")
    title = ""
    if soup.find("h1"):
        title = soup.find("h1").get_text(" ", strip=True)
    elif soup.title:
        title = soup.title.get_text(" ", strip=True)
    body = text_from_html(html)[:5000]
    hay = f"{title} {body} {url}"
    if NEG.search(hay) and not POS.search(hay):
        return False, "junk"
    if platform == "evisos":
        if not re.search(
            r"ayuda\s*econ|apoyo\s*econ|brindo|doy ayuda|encuentro|hombre busca|mujer busca|"
            r"ocasional|\bsexo\b|discreta|universitaria|se[nñ]orita|madre soltera|caballero|"
            r"busco (mujer|hombre|chica)",
            hay,
            re.I,
        ):
            return False, "not_relevant"
    else:
        # Doplim HBM/RO section ads: accept personal contact language
        if not POS.search(hay):
            return False, "not_relevant"
    return True, title[:120]


def already_archived(url: str) -> bool:
    h = hash16(url)
    if h in _SEEN_URLS:
        return True
    aid = ad_id(url)
    if aid and aid in _SEEN_IDS:
        return True
    # filesystem
    if list(RAW_DIR.glob(f"*_{h}.html")):
        return True
    if aid and list(RAW_DIR.glob(f"*{aid}*.html")):
        return True
    return False


def index_existing_raws() -> None:
    if not RAW_DIR.exists():
        return
    for p in RAW_DIR.glob("*.html"):
        name = p.name
        if "_" in name:
            h = name.rsplit("_", 1)[-1].replace(".html", "")
            if len(h) == 16:
                _SEEN_URLS.add(h)
        for m in re.finditer(r"(\d{5,})", name):
            _SEEN_IDS.add(m.group(1))


def count_platform_raws() -> dict[str, int]:
    counts = {"doplim": 0, "evisos": 0, "other": 0}
    if not RAW_DIR.exists():
        return counts
    for p in RAW_DIR.glob("*.html"):
        n = p.name.lower()
        try:
            head = p.read_text(encoding="utf-8", errors="ignore")[:2000].lower()
        except Exception:
            head = ""
        if "doplim" in n or "doplim" in head or n.startswith(("dop", "seed_dop")):
            counts["doplim"] += 1
        elif "evisos" in n or "evisos" in head:
            counts["evisos"] += 1
        else:
            counts["other"] += 1
    return counts


def fetch_html(session: requests.Session, url: str, platform: str) -> str:
    """HTTP first; Playwright fallback for Evisos 403 / thin interstitials."""
    html = ""
    try:
        r = session.get(url, timeout=28, allow_redirects=True)
        html = r.text or ""
        if r.status_code == 200 and len(html) > 2500 and "un momento" not in html.lower()[:1500]:
            ok, _ = quality_ok(html, url)
            if ok:
                return html
    except Exception:
        pass
    # Browser fallback (esp. evisos detail 403)
    if platform == "evisos" or len(html) < 2500 or (html and "403" in html[:500]):
        try:
            from tools.scrape_ads import fetch_playwright

            html2 = fetch_playwright(url, timeout_ms=65000, max_retries=3)
            if html2 and len(html2) > len(html):
                return html2
        except Exception:
            pass
    return html


def fetch_and_save(
    session: requests.Session,
    card: dict,
    log_path: Path,
    targets: dict[str, int],
) -> None:
    platform = card.get("platform", "other")
    url = card["url"]
    with _SAVE_LOCK:
        if _COUNTERS.get(platform, 0) >= targets.get(platform, 10**9):
            return
        if already_archived(url):
            _COUNTERS["skip"] += 1
            return

    try:
        html = fetch_html(session, url, platform)
    except Exception as e:
        with _SAVE_LOCK:
            _COUNTERS["err"] += 1
        log(log_path, f"ERR fetch {url[:80]} {e}")
        return

    ok, reason = quality_ok(html, url)
    if not ok:
        with _SAVE_LOCK:
            _COUNTERS["skip"] += 1
        return
    rel, title = relevant(html, url, platform)
    if not rel:
        with _SAVE_LOCK:
            _COUNTERS["skip"] += 1
        return

    with _SAVE_LOCK:
        if _COUNTERS.get(platform, 0) >= targets.get(platform, 10**9):
            return
        if already_archived(url):
            _COUNTERS["skip"] += 1
            return
        path = archive_raw(RAW_DIR, f"{platform}_fast", url, html)
        meta = {
            "url": url,
            "platform": platform,
            "title": title,
            "saved_at": utc_now(),
            "collector": "fast_http_v2",
            "list_text": card.get("text", "")[:200],
            "section": card.get("section", ""),
            "city": card.get("city", ""),
            "raw_archive_ref": f"data/raw/ads/{path.name}",
        }
        try:
            path.with_suffix(".meta.json").write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass
        _SEEN_URLS.add(hash16(url))
        aid = ad_id(url)
        if aid:
            _SEEN_IDS.add(aid)
        _COUNTERS[platform] = _COUNTERS.get(platform, 0) + 1
        _COUNTERS["saved"] += 1
        n = _COUNTERS[platform]
    if n % 25 == 0 or n < 5:
        log(log_path, f"SAVED {platform} n={n} title={title[:50]!r} file={path.name}")


def run_fetch_pool(
    cards: list[dict],
    log_path: Path,
    workers: int,
    targets: dict[str, int],
) -> None:
    # split sessions per thread-ish via thread local
    local = threading.local()

    def session_for(platform: str) -> requests.Session:
        key = f"s_{platform}"
        s = getattr(local, key, None)
        if s is None:
            s = make_session(platform)
            setattr(local, key, s)
        return s

    def work(card: dict) -> None:
        plat = card.get("platform", "doplim")
        with _SAVE_LOCK:
            if _COUNTERS.get("doplim", 0) >= targets.get("doplim", 10**9) and _COUNTERS.get(
                "evisos", 0
            ) >= targets.get("evisos", 10**9):
                return
            if _COUNTERS.get(plat, 0) >= targets.get(plat, 10**9):
                return
        fetch_and_save(session_for(plat), card, log_path, targets)

    random.shuffle(cards)
    # prioritize under-target platform
    cards.sort(
        key=lambda c: 0
        if _COUNTERS.get(c.get("platform", ""), 0) < targets.get(c.get("platform", ""), 0)
        else 1
    )
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(work, c) for c in cards]
        done = 0
        for f in as_completed(futs):
            done += 1
            try:
                f.result()
            except Exception as e:
                log(log_path, f"worker err {e}")
            if done % 50 == 0:
                elapsed = max(time.time() - t0, 0.1)
                rate = _COUNTERS["saved"] / elapsed * 60
                log(
                    log_path,
                    f"PROGRESS done={done}/{len(cards)} saved={_COUNTERS['saved']} "
                    f"doplim={_COUNTERS['doplim']} evisos={_COUNTERS['evisos']} "
                    f"skip={_COUNTERS['skip']} rate={rate:.1f}/min",
                )
            with _SAVE_LOCK:
                if _COUNTERS.get("doplim", 0) >= targets.get("doplim", 10**9) and _COUNTERS.get(
                    "evisos", 0
                ) >= targets.get("evisos", 10**9):
                    break


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--platform", choices=("all", "doplim", "evisos"), default="all")
    ap.add_argument("--target-doplim", type=int, default=1500)
    ap.add_argument("--target-evisos", type=int, default=1500)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--max-cities", type=int, default=0)
    ap.add_argument("--max-pages", type=int, default=10)
    ap.add_argument("--max-evisos-pages", type=int, default=40)
    ap.add_argument(
        "--early-stop-unique",
        type=int,
        default=0,
        help="Stop Doplim API gather once this many unique IDs collected (0=all)",
    )
    ap.add_argument("--learn-only", action="store_true")
    args = ap.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    SCRATCH.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    log_path = SCRATCH / f"collect_fast_{ts}.log"
    index_existing_raws()
    start_counts = count_platform_raws()
    # seed counters from existing so we stop at absolute totals
    _COUNTERS["doplim"] = start_counts.get("doplim", 0)
    _COUNTERS["evisos"] = start_counts.get("evisos", 0)
    targets = {"doplim": args.target_doplim, "evisos": args.target_evisos}
    log(log_path, f"START fast_v2 targets={targets} start_counts={start_counts} workers={args.workers}")

    cities = DOPLIM_CITIES[: args.max_cities] if args.max_cities else DOPLIM_CITIES
    cards: list[dict] = []

    if args.platform in ("all", "doplim"):
        s = make_session("doplim")
        sections = learn_doplim_section_ids(s, log_path)
        if args.learn_only:
            print(json.dumps(sections, indent=2))
            return 0
        t0 = time.time()
        early = args.early_stop_unique
        if not early and args.target_doplim:
            # default: enough unique seeds for target + buffer, avoid endless national crawl
            early = max(args.target_doplim * 2, args.target_doplim + 500)
        d_cards = gather_doplim_api(
            s,
            sections,
            cities,
            log_path,
            max_pages=args.max_pages,
            early_stop_unique=early,
        )
        log(log_path, f"GATHER doplim unique={len(d_cards)} in {time.time()-t0:.1f}s")
        cards.extend(d_cards)
        seeds = SCRATCH / f"seeds_doplim_fast_{ts}.jsonl"
        with seeds.open("w", encoding="utf-8") as fh:
            for c in d_cards:
                fh.write(json.dumps(c, ensure_ascii=False) + "\n")
        log(log_path, f"wrote {seeds}")

    if args.platform in ("all", "evisos"):
        s = make_session("evisos")
        t0 = time.time()
        e_cards = gather_evisos_http(s, log_path, max_pages=args.max_evisos_pages)
        log(log_path, f"GATHER evisos unique={len(e_cards)} in {time.time()-t0:.1f}s")
        cards.extend(e_cards)
        seeds = SCRATCH / f"seeds_evisos_fast_{ts}.jsonl"
        with seeds.open("w", encoding="utf-8") as fh:
            for c in e_cards:
                fh.write(json.dumps(c, ensure_ascii=False) + "\n")
        log(log_path, f"wrote {seeds}")

    log(log_path, f"FETCH start candidates={len(cards)}")
    t0 = time.time()
    run_fetch_pool(cards, log_path, workers=args.workers, targets=targets)
    elapsed = time.time() - t0
    end_counts = count_platform_raws()
    summary = {
        "log": str(log_path),
        "candidates": len(cards),
        "counters": dict(_COUNTERS),
        "start_counts": start_counts,
        "end_counts": end_counts,
        "elapsed_s": round(elapsed, 1),
        "ads_per_min": round(_COUNTERS["saved"] / max(elapsed, 0.1) * 60, 2),
        "finished_at": utc_now(),
    }
    sp = SCRATCH / f"collect_fast_summary_{ts}.json"
    sp.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    log(log_path, f"FINAL {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
