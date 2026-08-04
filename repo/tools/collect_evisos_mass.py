#!/usr/bin/env python3
"""Mass Evisos Peru HBM / RO / encuentros collector.

Phase A: HTTP list pagination (main h2.title cards, 10+ expected).
Phase B: Playwright detail fetch in sequential batches (HTTP detail is 403).
Saves raw HTML only under data/raw/ads when quality + relevance pass.
Target default: 1500 evisos raws.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

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

BASES = [
    "https://www.evisos.com.pe/encuentros.htm",
    "https://lima.evisos.com.pe/encuentros.htm",
    "https://www.evisos.com.pe/hombre-busca-mujer.htm",
    "https://www.evisos.com.pe/por-hombre-busca-mujer.htm",
    "https://www.evisos.com.pe/contactos-ocasionales-peru.htm",
    "https://www.evisos.com.pe/relaciones-ocasionales.htm",
    "https://www.evisos.com.pe/por-relaciones-ocasionales.htm",
    "https://www.evisos.com.pe/por-encuentros.htm",
    "https://www.evisos.com.pe/por-ayuda-economica.htm",
    "https://www.evisos.com.pe/apoyo-economico.htm",
    "https://www.evisos.com.pe/por-apoyo-economico.htm",
    "https://lima.evisos.com.pe/por-ayuda-economica.htm",
    "https://lima.evisos.com.pe/apoyo-economico.htm",
    "https://www.evisos.com.pe/brindo-ayuda.htm",
    "https://www.evisos.com.pe/doy-ayuda.htm",
    "https://www.evisos.com.pe/brindo-apoyo.htm",
    "https://arequipa.evisos.com.pe/encuentros.htm",
    "https://trujillo.evisos.com.pe/encuentros.htm",
    "https://cusco.evisos.com.pe/encuentros.htm",
    "https://piura.evisos.com.pe/encuentros.htm",
    "https://chiclayo.evisos.com.pe/encuentros.htm",
    "https://lima.evisos.com.pe/contactos.htm",
    "https://www.evisos.com.pe/servicios-eroticos.htm",
    "https://lima.evisos.com.pe/servicios-eroticos.htm",
]

KNOWN = [
    "https://lima-city.evisos.com.pe/busco-apoyo-economico-de-senoras-id-606945",
    "https://lima-city.evisos.com.pe/ayuda-economica-sa-lo-a-mujeres-id-637331",
    "https://lima-city.evisos.com.pe/ayuda-economica-a-cambio-de-intimidad-id-774937",
    "https://lima-city.evisos.com.pe/apoyo-economico-id-780526",
    "https://piura-city.evisos.com.pe/ofrezco-ayuda-economica-a-universitaria-id-631653",
    "https://lima-city.evisos.com.pe/curiosa-busco-experimentar-a-cambio-de-ayuda-econa-mi-id-651497",
    "https://lima-city.evisos.com.pe/ayuda-econ-por-sexo-con-senora-madura-id-601022",
    "https://lima-city.evisos.com.pe/solo-ayuda-economica-soy-una-chica-id-604929",
    "https://lima-city.evisos.com.pe/busco-hombre-maduro-a-cambio-de-ayuda-economica-id-620420",
    "https://lima-city.evisos.com.pe/para-senora-madura-apoyo-economico-mutuo-acuerdo-id-603643",
    "https://lima-city.evisos.com.pe/madre-soltera-busca-ayuda-id-831331",
    "https://arequipa-city.evisos.com.pe/ayuda-economica-para-mujeres-en-arequipa-id-766977",
    "https://imperial.evisos.com.pe/apoyo-economico-urgente-me-llamo-lucia-id-612124",
    "https://lima.evisos.com.pe/doy-ayuda-economica-a-seora-o-seorita-discreta-id-6859",
    "https://lima-city.evisos.com.pe/busco-pareja-para-relacion-seria-id-641548",
    "https://palpa.evisos.com.pe/ayuda-economica-a-cambio-de-mi-caria-osa-compaa-ia-id-651605",
]

POS = re.compile(
    r"ayuda\s*econ|apoyo\s*econ|brindo|doy ayuda|encuentro|hombre busca|mujer busca|"
    r"ocasional|\bsexo\b|discreta|universitaria|se[nñ]orita|madre soltera|caballero|"
    r"busco (mujer|hombre|chica|pareja)|ofrezco|intimidad|cari[nñ]o|pareja",
    re.I,
)
NEG = re.compile(
    r"peugeot|toyota|puertas?\s*levadiz|calamina|aluzinc|operario|baterista|"
    r"matematic|clases de |raqueta|inventario|catalogo natura|uniforme escolar",
    re.I,
)


def log(path: Path, msg: str) -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def ad_id(url: str) -> str | None:
    m = re.search(r"-id-(\d+)", url, re.I)
    return m.group(1) if m else None


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
            "Referer": "https://www.google.com.pe/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
    )
    return s


def extract_cards(html: str, base: str, loose: bool = True) -> list[dict]:
    """Main listing cards from h2.title. loose=True keeps almost all for volume;
    detail phase applies relevance/quality gates."""
    soup = BeautifulSoup(html, "lxml")
    out: list[dict] = []
    seen: set[str] = set()
    for a in soup.select("h2.title a, h2 a, .title a"):
        href = urljoin(base, a.get("href") or "")
        aid = ad_id(href)
        if not aid or aid in seen:
            continue
        block = a.find_parent("div") or a
        cat_el = block.select_one(".category-zone") if hasattr(block, "select_one") else None
        cat = cat_el.get_text(" ", strip=True) if cat_el else ""
        title = a.get_text(strip=True)
        desc_el = block.select_one(".desc") if hasattr(block, "select_one") else None
        desc = desc_el.get_text(" ", strip=True) if desc_el else ""
        hay = f"{cat} {title} {desc}"
        # Only hard-drop obvious product junk without any personal signal
        if NEG.search(hay) and not POS.search(hay):
            if re.search(
                r"ofertas de trabajo|inmuebles|autos|motos|productos industriales|electro",
                hay,
                re.I,
            ):
                continue
            if not loose:
                continue
        if not loose and not POS.search(hay):
            continue
        seen.add(aid)
        out.append(
            {
                "url": href.split("?")[0],
                "id": aid,
                "title": title,
                "category": cat,
                "text": hay[:220],
                "platform": "evisos",
            }
        )
    return out


def count_evisos() -> int:
    n = 0
    for p in RAW.glob("*.html"):
        name = p.name.lower()
        if "evisos" in name:
            n += 1
            continue
        try:
            head = p.read_text(encoding="utf-8", errors="ignore")[:1800].lower()
        except Exception:
            head = ""
        if "evisos" in head:
            n += 1
    return n


def already(url: str) -> bool:
    aid = ad_id(url)
    if aid and list(RAW.glob(f"*{aid}*.html")):
        return True
    import hashlib

    h = hashlib.sha256(url.encode()).hexdigest()[:16]
    return bool(list(RAW.glob(f"*_{h}.html")))


def quality(html: str, url: str) -> tuple[bool, str]:
    if not html or len(html) < 2000:
        return False, "short"
    if is_access_interstitial(html):
        return False, "inter"
    low = html.lower()[:3500]
    if any(k in low for k in ("cargando", "un momento", "verificando tu navegador", "access denied")):
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
    body = text_from_html(html)[:5000]
    hay = f"{title} {body} {url}"
    if NEG.search(hay) and not POS.search(hay):
        return False, "junk"
    if not POS.search(hay):
        return False, "not_relevant"
    return True, title[:120]


def gather_lists(log_path: Path, max_pages: int) -> list[dict]:
    s = session()
    allc: dict[str, dict] = {}
    for base in BASES:
        prev: set[str] = set()
        low = 0
        for page in range(1, max_pages + 1):
            url = page_url(base, page)
            try:
                r = s.get(url, timeout=25)
                html = r.text if r.status_code == 200 else ""
                # Skip Playwright list fallback (too slow); empty page => stop base
                if len(html) < 1500:
                    low += 1
                    log(log_path, f"LIST skip {url} status={getattr(r,'status_code',None)} len={len(html)}")
                    if low >= 2:
                        break
                    continue
                cards = extract_cards(html, url, loose=True)
                ids = {c["id"] for c in cards}
                # stop only if full page id-set identical to previous (true loop)
                if page > 1 and ids and ids == prev and len(ids) >= 5:
                    log(log_path, f"LIST loop {url}; stop base")
                    break
                prev = ids
                new = 0
                for c in cards:
                    if c["id"] not in allc:
                        allc[c["id"]] = c
                        new += 1
                log(
                    log_path,
                    f"LIST p{page} {url}: cards={len(cards)} new={new} total={len(allc)}"
                    + (" OK10+" if len(cards) >= 10 else ""),
                )
                # allow a few zero-new pages (site reordering) before stop
                if new == 0:
                    low += 1
                else:
                    low = 0
                if low >= 4:
                    break
                time.sleep(random.uniform(0.15, 0.4))
            except Exception as e:
                log(log_path, f"LIST ERR {url}: {e}")
                low += 1
                if low >= 2:
                    break
    for u in KNOWN:
        aid = ad_id(u)
        if aid and aid not in allc:
            allc[aid] = {"url": u, "id": aid, "title": "", "text": "known", "platform": "evisos"}
    # merge prior seeds
    for p in SCR.glob("seeds_evisos*.jsonl"):
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                d = json.loads(line)
                aid = d.get("id") or ad_id(d.get("url", ""))
                if aid and aid not in allc and d.get("url"):
                    d["platform"] = "evisos"
                    allc[aid] = d
        except Exception:
            pass
    return list(allc.values())


def fetch_detail(url: str) -> str:
    # Prefer playwright (HTTP 403 on evisos details)
    try:
        html = fetch_playwright(url, timeout_ms=75000, max_retries=4)
        if html and len(html) > 2500:
            return html
    except Exception:
        pass
    try:
        r = session().get(url, timeout=30)
        return r.text or ""
    except Exception:
        return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=1500)
    ap.add_argument("--max-pages", type=int, default=50)
    ap.add_argument("--seeds-only", action="store_true")
    args = ap.parse_args()

    RAW.mkdir(parents=True, exist_ok=True)
    SCR.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    log_path = SCR / f"evisos_mass_{ts}.log"
    start_n = count_evisos()
    log(log_path, f"START evisos_mass target={args.target} start_count={start_n}")

    cards = gather_lists(log_path, max_pages=args.max_pages)
    seeds = SCR / f"seeds_evisos_mass_{ts}.jsonl"
    with seeds.open("w", encoding="utf-8") as fh:
        for c in cards:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")
    log(log_path, f"GATHER unique={len(cards)} -> {seeds}")
    if args.seeds_only:
        return 0

    saved = skip = err = 0
    t0 = time.time()
    random.shuffle(cards)
    for i, c in enumerate(cards):
        if start_n + saved >= args.target:
            log(log_path, f"TARGET reached {start_n + saved}")
            break
        url = c["url"]
        if already(url):
            skip += 1
            continue
        html = fetch_detail(url)
        ok, reason = quality(html, url)
        if not ok:
            skip += 1
            if (i + 1) % 20 == 0:
                log(log_path, f"skip quality={reason} {url[:70]}")
            continue
        rel, title = relevant(html, url)
        if not rel:
            skip += 1
            continue
        path = archive_raw(RAW, "evisos_mass", url, html)
        meta = {
            "url": url,
            "platform": "evisos",
            "title": title,
            "saved_at": datetime.now(timezone.utc).isoformat() + "Z",
            "collector": "evisos_mass_pw",
            "raw_archive_ref": f"data/raw/ads/{path.name}",
            "list_text": c.get("text", "")[:200],
        }
        try:
            path.with_suffix(".meta.json").write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass
        saved += 1
        if saved % 5 == 0 or saved <= 5:
            rate = saved / max(time.time() - t0, 0.1) * 60
            log(
                log_path,
                f"SAVED {saved} total_evisos~{start_n+saved} rate={rate:.1f}/min title={title[:50]!r} {path.name}",
            )
        time.sleep(random.uniform(0.35, 0.9))
        if (i + 1) % 15 == 0:
            log(
                log_path,
                f"PROGRESS i={i+1}/{len(cards)} saved={saved} skip={skip} err={err} "
                f"count={count_evisos()}",
            )

    end_n = count_evisos()
    summary = {
        "start": start_n,
        "end": end_n,
        "saved": saved,
        "skip": skip,
        "err": err,
        "candidates": len(cards),
        "elapsed_s": round(time.time() - t0, 1),
        "log": str(log_path),
    }
    (SCR / f"evisos_mass_summary_{ts}.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    log(log_path, f"FINAL {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
