#!/usr/bin/env python3
"""Focused Evisos/Evisex collector for male-offer ayuda economica ads.

Research (2026-07-08):
- evisos.com.pe tag/slug lists (por-ayuda-economica, encuentros, brindo-ayuda)
  are heavily polluted (bandas, empleo, mascotas, clases). ID-neighborhood
  expansion made this worse (saved vocalista/baterista junk).
- evisex.pe /encuentros/* paths are higher yield (646+ apoyo-economico ads).
- PeruTops meta threads name public surfaces for these ads as:
  Doplim, Blidoo (thin), ciudad-anuncios, Twitter, Facebook groups —
  NOT random Evisos IDs. Forums are discussion, not ad hosts.

Strategy:
  1) HTTP list only from high-signal bases (Evisex + tight Evisos slugs)
  2) Card-level prefilter: require ayuda/apoyo econ terms in card text/title
  3) Reject band/job/pet/class junk and pure seekers when no male-offer language
  4) Playwright detail fetch; save only if rebuild-aligned TARGET+OFFER pass
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import sys
import time
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
    fetch_playwright,
    has_substantial_ad_content,
    is_access_interstitial,
    text_from_html,
)

RAW = ROOT / "data" / "raw" / "ads"
SCR = ROOT / "SCRATCH" / "implementer"

# High-signal list bases only (validated HTTP 200 + relevant card titles)
BASES = [
    # Evisex — best public volume for this niche
    "https://www.evisex.pe/encuentros/apoyo-economico.htm",
    "https://www.evisex.pe/encuentros/ayuda-economica-a-mujeres-de-lima.htm",
    "https://www.evisex.pe/encuentros/sexo-a-cambio-de-ayuda-economica.htm",
    "https://www.evisex.pe/encuentros/ayuda-economica-a-cambio-de-intimidad.htm",
    "https://www.evisex.pe/encuentros/mujer-busca-hombre/mujer-busca-ayuda-economica.htm",
    "https://www.evisex.pe/encuentros/busca-hombre-para-ayuda-economica.htm",
    "https://www.evisex.pe/encuentros/hombre-busca-mujer.htm",
    "https://lima.evisex.pe/encuentros/apoyo-economico.htm",
    # Evisos — only tight slugs; still noisy, rely on card prefilter
    "https://www.evisos.com.pe/por-ayuda-economica.htm",
    "https://www.evisos.com.pe/apoyo-economico.htm",
    "https://lima.evisos.com.pe/por-ayuda-economica.htm",
    "https://lima.evisos.com.pe/apoyo-economico.htm",
    "https://www.evisos.com.pe/brindo-ayuda.htm",
    "https://www.evisos.com.pe/doy-ayuda.htm",
    "https://arequipa.evisos.com.pe/por-ayuda-economica.htm",
    "https://trujillo.evisos.com.pe/por-ayuda-economica.htm",
    "https://cusco.evisos.com.pe/por-ayuda-economica.htm",
]

# Seed known good detail URLs (from prior research / indexed samples)
KNOWN = [
    "https://lima-city.evisos.com.pe/apoyo-economico-id-780526",
    "https://cusco-city.evisos.com.pe/ayuda-economica-para-chicas-en-apuros-cusco-id-657602",
    "https://trujillo.evisos.com.pe/ayuda-a-chibolas-no-importa-el-fisico-id-755017",
    "https://piura-city.evisos.com.pe/ofrezco-ayuda-economica-a-universitaria-id-631653",
    "https://lima-city.evisos.com.pe/ayuda-economica-a-cambio-de-intimidad-id-774937",
    "https://arequipa-city.evisos.com.pe/ayuda-economica-para-mujeres-en-arequipa-id-766977",
    "https://lima-city.evisos.com.pe/ayuda-economica-sa-lo-a-mujeres-id-637331",
]

# Align with rebuild_manifest_from_raw TARGET / OFFER / BAD_SEEKER
TARGET_RE = re.compile(
    r"ayuda\s*econ[oó]mica|apoyo\s*econ[oó]mico|ayudo\s*econ[oó]micamente|"
    r"brindo\s+(?:ayuda|apoyo)|doy\s+(?:ayuda|apoyo)|ofrezco\s+(?:ayuda|apoyo)|"
    r"se\s+brinda\s+(?:ayuda|apoyo)|brinda\s+(?:ayuda|apoyo)",
    re.I,
)
OFFER_RE = re.compile(
    r"\b(brindo|doy|ofrezco|se brinda|brinda apoyo|le ayudo|te brindo|"
    r"hombre maduro|caballero|profesional|ejecutivo)\b",
    re.I,
)
BAD_SEEKER_RE = re.compile(
    r"busco\s+(ayuda|apoyo|chica|universitaria|estudiante|señorita|senorita)",
    re.I,
)
JUNK_RE = re.compile(
    r"\b(banda|baterista|bajista|vocalista|guitarrista|cantante|m[uú]sico|"
    r"paramore|coverss?|punk\s*rock|ensayo|"
    r"alquilo|habitaci[oó]n|local comercial|drywall|aluzinc|calamina|"
    r"shih\s*tzu|cachorro|mascota|adopci[oó]n|"
    r"matem[aá]tic|clases?\s+de|curso\s+de|biomagnetismo|"
    r"operador de|retroescavadora|vendedores|ofertas?\s+de\s+trabajo|"
    r"asistente administrativo|nutricionista|nana por horas|"
    r"pad\s*mouse|walkie\s*talkie|gps protege|"
    r"masajes?\s+terap[eé]utic|scorts?|vibrador|"
    r"ong en lima|repartir volantes)\b",
    re.I,
)


def log(path: Path, msg: str) -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def page_url(base: str, n: int) -> str:
    if n <= 1:
        return base
    if base.endswith(".htm"):
        return f"{base[:-4]}/clasificados/{n}"
    return f"{base.rstrip('/')}/clasificados/{n}"


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


def card_ok(title: str, snippet: str = "") -> bool:
    hay = f"{title} {snippet}"
    if JUNK_RE.search(hay):
        return False
    if not TARGET_RE.search(hay):
        return False
    # Prefer male-offer language; allow seekers that still mention ayuda for later filter
    return True


def extract_cards(html: str, base: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    out: dict[str, dict] = {}
    # Main list titles
    for a in soup.select("h2.title a[href], .ad-title a[href], a[href*='-id-']"):
        href = a.get("href") or ""
        if "-id-" not in href.lower() and "id-" not in href.lower():
            continue
        if href.startswith("//"):
            href = "https:" + href
        elif href.startswith("/"):
            href = urljoin(base, href)
        m = re.search(r"-id-(\d+)", href, re.I)
        if not m:
            continue
        aid = m.group(1)
        title = a.get_text(" ", strip=True)[:220]
        # nearby card text
        parent = a.find_parent(["li", "article", "div"])
        snip = parent.get_text(" ", strip=True)[:400] if parent else title
        if not card_ok(title, snip):
            continue
        host = urlparse(href).netloc.lower()
        plat = "evisex" if "evisex" in host else "evisos"
        out[aid] = {
            "id": aid,
            "url": href.split("?")[0],
            "title": title,
            "platform": plat,
            "text": snip[:220],
        }
    return list(out.values())


def already(url: str) -> bool:
    m = re.search(r"-id-(\d+)", url, re.I)
    if m and list(RAW.glob(f"*{m.group(1)}*.html")):
        return True
    h = hashlib.sha256(url.encode()).hexdigest()[:16]
    return bool(list(RAW.glob(f"*_{h}.html")))


def detail_ok(title: str, body: str) -> tuple[bool, str]:
    joined = f"{title}\n{body}"
    if JUNK_RE.search(joined):
        return False, "junk"
    if not TARGET_RE.search(joined):
        return False, "no_target"
    if BAD_SEEKER_RE.search(joined) and not OFFER_RE.search(joined):
        return False, "seeker_only"
    # Prefer offers for processed yield; still allow dual language
    if not OFFER_RE.search(joined) and not re.search(
        r"\b(brindo|doy|ofrezco|se brinda|caballero|profesional)\b", joined, re.I
    ):
        # pure seeker without offer words — skip for high-yield collection
        if re.search(r"\bbusco\b", joined, re.I):
            return False, "seeker_no_offer"
    return True, "ok"


def gather(log_path: Path, max_pages: int = 25) -> list[dict]:
    s = session()
    allc: dict[str, dict] = {}
    for u in KNOWN:
        m = re.search(r"-id-(\d+)", u, re.I)
        if m:
            allc[m.group(1)] = {
                "id": m.group(1),
                "url": u,
                "title": "known",
                "platform": "evisos",
                "text": "known",
            }
    for base in BASES:
        empty = 0
        for page in range(1, max_pages + 1):
            url = page_url(base, page)
            try:
                r = s.get(url, timeout=25)
                if r.status_code != 200 or len(r.text) < 2000:
                    empty += 1
                    log(log_path, f"LIST skip {url} status={r.status_code} len={len(r.text)}")
                    if empty >= 2:
                        break
                    continue
                cards = extract_cards(r.text, url)
                new = 0
                for c in cards:
                    if c["id"] not in allc:
                        allc[c["id"]] = c
                        new += 1
                log(
                    log_path,
                    f"LIST {url}: cards_ok={len(cards)} new={new} total={len(allc)}",
                )
                if new == 0:
                    empty += 1
                else:
                    empty = 0
                if empty >= 3:
                    break
                time.sleep(random.uniform(0.15, 0.4))
            except Exception as e:
                log(log_path, f"LIST ERR {url}: {e}")
                empty += 1
                if empty >= 2:
                    break
    return list(allc.values())


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=200)
    ap.add_argument("--max-pages", type=int, default=20)
    args = ap.parse_args()

    RAW.mkdir(parents=True, exist_ok=True)
    SCR.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    log_path = SCR / f"evisos_focused_{ts}.log"
    seeds = gather(log_path, max_pages=args.max_pages)
    seeds_path = SCR / f"seeds_evisos_focused_{ts}.jsonl"
    with seeds_path.open("w", encoding="utf-8") as fh:
        for c in seeds:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")
    random.shuffle(seeds)
    start = len(list(RAW.glob("evisos*.html")) + list(RAW.glob("evisex*.html")))
    log(log_path, f"START seeds={len(seeds)} start_files={start} target={args.target}")

    saved = skip = err = 0
    for i, c in enumerate(seeds):
        if saved >= args.target:
            break
        url = c["url"]
        if already(url):
            skip += 1
            continue
        # Skip known-junk expand leftovers: require target in seed title when present
        title0 = c.get("title") or ""
        if title0 and title0 != "known" and not TARGET_RE.search(title0) and not card_ok(title0, c.get("text") or ""):
            skip += 1
            continue
        try:
            html = fetch_playwright(url, timeout_ms=55000, max_retries=2) or ""
        except Exception as e:
            err += 1
            if err % 10 == 0:
                log(log_path, f"err {e}")
            continue
        if not html or len(html) < 1800 or is_access_interstitial(html):
            skip += 1
            continue
        low = html.lower()[:3500]
        if any(k in low for k in ("cargando", "un momento", "verificando", "no encontrado", "no existe")):
            skip += 1
            continue
        if not has_substantial_ad_content(html, url):
            skip += 1
            continue
        if "evisos" not in low[:3000] and "evisex" not in low[:3000]:
            skip += 1
            continue
        soup = BeautifulSoup(html, "lxml")
        title = (
            soup.find("h1").get_text(" ", strip=True)
            if soup.find("h1")
            else (soup.title.get_text(strip=True) if soup.title else "")
        )
        body = text_from_html(html)[:6000]
        ok, why = detail_ok(title, body)
        if not ok:
            skip += 1
            if skip % 15 == 0:
                log(log_path, f"skip_{why} {title[:60]!r}")
            continue
        tag = "evisex_pw" if "evisex" in url else "evisos_pw"
        path = archive_raw(RAW, tag, url, html)
        path.with_suffix(".meta.json").write_text(
            json.dumps(
                {
                    "url": url,
                    "platform": "evisex" if "evisex" in url else "evisos",
                    "title": title[:120],
                    "saved_at": datetime.now(timezone.utc).isoformat() + "Z",
                    "collector": "collect_evisos_focused",
                    "raw_archive_ref": f"data/raw/ads/{path.name}",
                    "filter": "strict_target_offer",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        saved += 1
        if saved % 2 == 0 or saved <= 8:
            log(log_path, f"SAVED {saved} {title[:65]!r} {path.name}")
        time.sleep(random.uniform(0.25, 0.6))
        if (i + 1) % 15 == 0:
            log(log_path, f"PROGRESS i={i+1}/{len(seeds)} saved={saved} skip={skip} err={err}")

    log(log_path, f"DONE saved={saved} skip={skip} err={err}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
