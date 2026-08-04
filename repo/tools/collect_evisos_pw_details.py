#!/usr/bin/env python3
"""Evisos detail-only collector (Playwright). Builds seeds from known + prior + light HTTP list."""
from __future__ import annotations

import json
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.collect_evisos_mass import (  # noqa: E402
    BASES,
    KNOWN,
    extract_cards,
    session,
)
from tools.scrape_ads import (  # noqa: E402
    archive_raw,
    fetch_playwright,
    has_substantial_ad_content,
    is_access_interstitial,
    text_from_html,
)

RAW = ROOT / "data" / "raw" / "ads"
SCR = ROOT / "SCRATCH" / "implementer"
POS = re.compile(
    r"ayuda\s*econ|apoyo\s*econ|brindo|doy ayuda|encuentro|hombre busca|mujer busca|"
    r"ocasional|\bsexo\b|discreta|universitaria|se[nñ]orita|madre soltera|caballero|"
    r"busco (mujer|hombre|chica)|ofrezco|intimidad|pareja|cari[nñ]",
    re.I,
)


def log(path: Path, msg: str) -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def already(url: str) -> bool:
    m = re.search(r"-id-(\d+)", url, re.I)
    if m and list(RAW.glob(f"*{m.group(1)}*.html")):
        return True
    import hashlib

    h = hashlib.sha256(url.encode()).hexdigest()[:16]
    return bool(list(RAW.glob(f"*_{h}.html")))


def build_seeds() -> list[dict]:
    allc: dict[str, dict] = {}
    for u in KNOWN:
        m = re.search(r"-id-(\d+)", u, re.I)
        if m:
            allc[m.group(1)] = {"url": u, "id": m.group(1), "platform": "evisos", "text": "known"}
    for p in SCR.glob("seeds_evisos*.jsonl"):
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
                aid = d.get("id") or ""
                if not aid and d.get("url"):
                    mm = re.search(r"-id-(\d+)", d["url"], re.I)
                    aid = mm.group(1) if mm else ""
                if aid and d.get("url"):
                    allc[str(aid)] = d
            except Exception:
                pass
    s = session()
    for base in BASES[:10]:
        try:
            r = s.get(base, timeout=20)
            if r.status_code == 200 and len(r.text) > 2000:
                for c in extract_cards(r.text, base, loose=True):
                    allc[c["id"]] = c
        except Exception:
            pass
    # modest ID expansion around known goods
    for base_id in (
        606945, 637331, 780526, 631653, 651497, 601022, 604929, 620420,
        603643, 766977, 612124, 774937, 641548, 831331, 736180, 712903, 665459,
    ):
        for d in range(-20, 21):
            iid = base_id + d
            if iid <= 0 or str(iid) in allc:
                continue
            allc[str(iid)] = {
                "url": f"https://lima-city.evisos.com.pe/anuncio-id-{iid}",
                "id": str(iid),
                "platform": "evisos",
                "text": "expand",
            }
    return list(allc.values())


def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    SCR.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    log_path = SCR / f"evisos_pw_details_{ts}.log"
    seeds = build_seeds()
    seeds_path = SCR / f"seeds_evisos_pw_{ts}.jsonl"
    with seeds_path.open("w", encoding="utf-8") as fh:
        for c in seeds:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")
    random.shuffle(seeds)
    start = len(list(RAW.glob("evisos*.html")))
    log(log_path, f"START seeds={len(seeds)} start_files={start}")
    saved = skip = err = 0
    target = 1500
    for i, c in enumerate(seeds):
        if start + saved >= target:
            break
        url = c["url"]
        if already(url):
            skip += 1
            continue
        try:
            html = fetch_playwright(url, timeout_ms=55000, max_retries=2) or ""
        except Exception as e:
            err += 1
            if err % 15 == 0:
                log(log_path, f"err {e}")
            continue
        if not html or len(html) < 2000 or is_access_interstitial(html):
            skip += 1
            continue
        low = html.lower()[:3000]
        if any(k in low for k in ("cargando", "un momento", "verificando", "no encontrado", "no existe")):
            skip += 1
            continue
        if not has_substantial_ad_content(html, url):
            skip += 1
            continue
        if "evisos" not in low[:2500]:
            skip += 1
            continue
        soup = BeautifulSoup(html, "lxml")
        title = (
            soup.find("h1").get_text(" ", strip=True)
            if soup.find("h1")
            else (soup.title.get_text(strip=True) if soup.title else "")
        )
        hay = f"{title} {text_from_html(html)[:4500]}"
        if not POS.search(hay):
            if c.get("text") == "expand":
                skip += 1
                continue
        path = archive_raw(RAW, "evisos_pw", url, html)
        path.with_suffix(".meta.json").write_text(
            json.dumps(
                {
                    "url": url,
                    "platform": "evisos",
                    "title": title[:120],
                    "saved_at": datetime.now(timezone.utc).isoformat() + "Z",
                    "collector": "evisos_pw_details",
                    "raw_archive_ref": f"data/raw/ads/{path.name}",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        saved += 1
        if saved % 3 == 0 or saved <= 5:
            log(log_path, f"SAVED {saved} total~{start+saved} {title[:55]!r} {path.name}")
        time.sleep(random.uniform(0.3, 0.7))
        if (i + 1) % 20 == 0:
            log(log_path, f"PROGRESS i={i+1}/{len(seeds)} saved={saved} skip={skip} err={err}")
    log(log_path, f"DONE saved={saved} skip={skip} err={err} files={len(list(RAW.glob('evisos*.html')))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
