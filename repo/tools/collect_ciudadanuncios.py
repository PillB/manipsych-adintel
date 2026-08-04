#!/usr/bin/env python3
"""Ciudad Anuncios Peru collector (PeruTops-named surface).

Discovery:
  - Seed known good /item/N URLs (web-indexed + prior)
  - BFS via related-ad links on detail pages (site search is broken/unfiltered)
  - Card/title prefilter: ayuda/apoyo econ + optional male-offer language

Fetch: plain HTTP works for details (no Playwright required).
Save: data/raw/ads/ciudadanuncios_*.html with strict TARGET/OFFER gates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.scrape_ads import archive_raw, has_substantial_ad_content, is_access_interstitial, text_from_html

RAW = ROOT / "data" / "raw" / "ads"
SCR = ROOT / "SCRATCH" / "implementer"

# Indexed seeds (web search + related-graph bootstraps)
SEED_URLS = [
    "https://santotomnas.ciudadanuncios.pe/item/514478/",
    "https://lima.ciudadanuncios.pe/item/655574/",
    "https://abancay.ciudadanuncios.pe/item/321666/",
    "https://cusco.ciudadanuncios.pe/item/396229/",
    "https://puertomaldonado.ciudadanuncios.pe/item/680028/",
    "https://lima.ciudadanuncios.pe/item/287707/",
    "https://juliaca.ciudadanuncios.pe/item/635383/",
    "https://lima.ciudadanuncios.pe/item/694706/",
    "https://trujillo.ciudadanuncios.pe/item/293544/",
    "https://lima.ciudadanuncios.pe/item/634002/",
    "https://cusco.ciudadanuncios.pe/item/301168/",
    "https://juliaca.ciudadanuncios.pe/item/768598/",
    "https://sanvicentedecanete.ciudadanuncios.pe/item/780891/",
    "https://lima.ciudadanuncios.pe/item/670303/",
    "https://piura.ciudadanuncios.pe/item/118751/",
]

TARGET_RE = re.compile(
    r"ayuda\s*econ[oó]mica|apoyo\s*econ[oó]mico|ayudo\s*econ[oó]micamente|"
    r"brindo\s+(?:ayuda|apoyo)|doy\s+(?:ayuda|apoyo)|ofrezco\s+(?:ayuda|apoyo)|"
    r"se\s+da\s+(?:ayuda|apoyo)|se\s+brinda\s+(?:ayuda|apoyo)",
    re.I,
)
OFFER_RE = re.compile(
    r"\b(brindo|doy|ofrezco|se brinda|se da|brinda apoyo|caballero|profesional|"
    r"hombre|chico|ejecutivo)\b",
    re.I,
)
SEEKER_RE = re.compile(
    r"\bbusco\s+(ayuda|apoyo|chica|activo|pasivo|amigo)",
    re.I,
)
JUNK_RE = re.compile(
    r"\b(refuerzo escolar|apoyo escolar|apoyo acad[eé]mico|apoyo legal|"
    r"clases de|matem[aá]tic|spss|autocad|revit|log[ií]stic|"
    r"cuidado de ancianos|educadora infantil|mascota|perrito|"
    r"banda|vocalista|baterista|alquiler|departamento)\b",
    re.I,
)
ITEM_RE = re.compile(r"https?://[a-z0-9.-]*ciudadanuncios\.pe/item/(\d+)/?", re.I)


def log(path: Path, msg: str) -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "es-PE,es;q=0.9,en;q=0.5",
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        }
    )
    return s


def norm_item(url: str) -> str | None:
    m = ITEM_RE.search(url)
    if not m:
        return None
    host = urlparse(url).netloc.lower() or "www.ciudadanuncios.pe"
    return f"https://{host}/item/{m.group(1)}/"


def already(url: str) -> bool:
    m = ITEM_RE.search(url)
    if m and list(RAW.glob(f"*_{m.group(1)}.html")):
        return True
    h = hashlib.sha256(url.encode()).hexdigest()[:16]
    return bool(list(RAW.glob(f"*_{h}.html")))


def title_ok(title: str) -> bool:
    if not title or len(title) < 8:
        return False
    if JUNK_RE.search(title):
        return False
    if not TARGET_RE.search(title):
        return False
    return True


def detail_ok(title: str, body: str) -> tuple[bool, str]:
    joined = f"{title}\n{body}"
    if JUNK_RE.search(joined):
        return False, "junk"
    if not TARGET_RE.search(joined):
        return False, "no_target"
    if SEEKER_RE.search(joined) and not OFFER_RE.search(joined):
        return False, "seeker_only"
    if not OFFER_RE.search(joined) and re.search(r"\bbusco\b", joined, re.I):
        return False, "seeker_no_offer"
    return True, "ok"


def extract_related(html: str, base: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "lxml")
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for a in soup.select('a[href*="/item/"]'):
        href = a.get("href") or ""
        full = norm_item(urljoin(base, href))
        if not full or full in seen:
            continue
        title = a.get_text(" ", strip=True)[:200]
        seen.add(full)
        out.append((full, title))
    return out


def extract_title_body(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "lxml")
    title = ""
    if soup.find("h1"):
        title = soup.find("h1").get_text(" ", strip=True)
    elif soup.title:
        title = soup.title.get_text(" ", strip=True)
    body = text_from_html(html)
    # Prefer text after "Detalles del Anuncio" if present
    m = re.search(r"Detalles del Anuncio(.*?)(Anuncios relacionados|Reportar|$)", body, re.I | re.S)
    if m and len(m.group(1).strip()) > 40:
        body = m.group(1).strip()
    return title[:300], body[:8000]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=200)
    ap.add_argument("--max-visit", type=int, default=800)
    ap.add_argument("--seeds-extra", type=Path, default=None, help="jsonl with {url} lines")
    args = ap.parse_args()

    RAW.mkdir(parents=True, exist_ok=True)
    SCR.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    log_path = SCR / f"ciudadanuncios_{ts}.log"
    seeds_out = SCR / f"seeds_ciudadanuncios_{ts}.jsonl"

    sess = session()
    queue: deque[str] = deque()
    seen_urls: set[str] = set()

    seeds = list(SEED_URLS)
    if args.seeds_extra and args.seeds_extra.exists():
        for line in args.seeds_extra.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
                u = norm_item(str(d.get("url") or ""))
                if u:
                    seeds.append(u)
            except Exception:
                u = norm_item(line.strip())
                if u:
                    seeds.append(u)

    for u in seeds:
        nu = norm_item(u)
        if nu and nu not in seen_urls:
            seen_urls.add(nu)
            queue.append(nu)

    log(log_path, f"START seeds={len(queue)} target={args.target} max_visit={args.max_visit}")

    saved = skip = err = visited = 0
    saved_urls: list[dict] = []

    def load_html(url: str) -> str | None:
        """Prefer local raw archive (expand graph without re-download), else HTTP."""
        h = hashlib.sha256(url.encode()).hexdigest()[:16]
        m = ITEM_RE.search(url)
        for p in list(RAW.glob(f"*_{h}.html")) + (
            list(RAW.glob(f"*_{m.group(1)}*.html")) if m else []
        ):
            try:
                t = p.read_text(encoding="utf-8", errors="ignore")
                if len(t) > 1500:
                    return t
            except Exception:
                pass
        try:
            r = sess.get(url, timeout=20)
        except Exception:
            return None
        if r.status_code != 200 or len(r.text) < 1500:
            return None
        if is_access_interstitial(r.text):
            return None
        return r.text

    while queue and saved < args.target and visited < args.max_visit:
        url = queue.popleft()
        visited += 1
        was_archived = already(url)
        html = load_html(url)
        if not html:
            skip += 1
            err += 0
            continue

        title, body = extract_title_body(html)
        # Always expand related links so BFS continues past already-saved seeds
        for href, rtitle in extract_related(html, url):
            if href in seen_urls:
                continue
            if title_ok(rtitle) or TARGET_RE.search(rtitle) or TARGET_RE.search(href):
                seen_urls.add(href)
                queue.append(href)

        if was_archived:
            skip += 1
            if visited % 50 == 0:
                log(log_path, f"expand-only visited={visited} q={len(queue)} saved={saved}")
            continue

        if not title_ok(title):
            skip += 1
            continue
        ok, why = detail_ok(title, body)
        if not ok:
            skip += 1
            if skip % 20 == 0:
                log(log_path, f"skip_{why} {title[:55]!r}")
            continue
        if not has_substantial_ad_content(html, url) and len(body) < 40:
            skip += 1
            continue

        path = archive_raw(RAW, "ciudadanuncios", url, html)
        path.with_suffix(".meta.json").write_text(
            json.dumps(
                {
                    "url": url,
                    "platform": "ciudadanuncios",
                    "title": title[:160],
                    "saved_at": datetime.now(timezone.utc).isoformat() + "Z",
                    "collector": "collect_ciudadanuncios",
                    "raw_archive_ref": f"data/raw/ads/{path.name}",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        saved += 1
        saved_urls.append({"url": url, "title": title, "path": path.name})
        if saved % 5 == 0 or saved <= 8:
            log(log_path, f"SAVED {saved} {title[:60]!r} {path.name} q={len(queue)}")
        time.sleep(random.uniform(0.12, 0.35))
        if visited % 25 == 0:
            log(
                log_path,
                f"PROGRESS visited={visited} saved={saved} skip={skip} err={err} queue={len(queue)}",
            )

    with seeds_out.open("w", encoding="utf-8") as fh:
        for d in saved_urls:
            fh.write(json.dumps(d, ensure_ascii=False) + "\n")

    log(log_path, f"DONE saved={saved} skip={skip} err={err} visited={visited} queue_left={len(queue)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
