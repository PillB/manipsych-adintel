#!/usr/bin/env python3
"""Doplim high-yield top-up via getAdsSearch + parallel HTTP details (tag: doplim_ayuda)."""
from __future__ import annotations

import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.collect_doplim_evisos_fast import (  # noqa: E402
    extract_doplim_urls,
    make_session,
    quality_ok,
)
from tools.scrape_ads import archive_raw  # noqa: E402

RAW = ROOT / "data" / "raw" / "ads"
SCRATCH = ROOT / "SCRATCH" / "implementer"
SCRATCH.mkdir(parents=True, exist_ok=True)

SECTIONS = {
    "hombre-busca-mujer": ("5", "51"),
    "relaciones-ocasionales": ("5", "54"),
    "mujer-busca-hombre": ("5", "50"),
    "contactos": ("5", "0"),
}
QUERIES = [
    "ayuda economica",
    "apoyo economico",
    "brindo ayuda",
    "doy ayuda",
    "brindo apoyo",
    "ayuda a señoritas",
    "doy apoyo",
    "ofrezco ayuda",
    "ayuda universitaria",
    "apoyo a estudiantes",
    "brindo apoyo economico",
    "doy apoyo economico",
    "ayuda a chicas",
    "apoyo a mujeres",
    "ayuda discreta",
    "caballero ayuda",
    "profesional ayuda",
    "sugar daddy",
    "apoyo discreto",
    "ayudo economicamente",
]
CITIES = [
    "lima", "arequipa", "trujillo", "cusco", "piura", "chiclayo", "callao",
    "huancayo", "ica", "tacna", "puno", "cajamarca", "chimbote", "ayacucho",
    "iquitos", "tarapoto", "pucallpa", "juliaca", "sullana", "huaraz",
]


def log(path: Path, msg: str) -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def hash_from_name(name: str) -> str | None:
    m = re.search(r"_([0-9a-f]{16})\.html$", name)
    return m.group(1) if m else None


def main() -> None:
    log_path = SCRATCH / f"doplim_ayuda_topup_{int(time.time())}.log"
    sess = make_session("doplim")
    seen: dict[str, dict] = {}

    def api_pull(catid: str, subcatid: str, query: str, section: str, max_pages: int = 10) -> None:
        empty = 0
        for page in range(1, max_pages + 1):
            data = {
                "page": page,
                "cityid": "0",
                "areaid": "0",
                "catid": catid,
                "subcatid": subcatid,
                "query": query,
                "gal": 0,
                "price_min": "0",
                "price_max": 0,
                "sort_by": "",
            }
            try:
                sess.headers["Referer"] = f"https://www.doplim.com.pe/s/{section}/lima/"
                r = sess.post(
                    "https://www.doplim.com.pe/api/getAdsSearch",
                    data=data,
                    timeout=25,
                )
                if r.status_code != 200 or len(r.text) < 200:
                    empty += 1
                    if empty >= 2:
                        break
                    continue
                cards = extract_doplim_urls(r.text)
                new = 0
                for c in cards:
                    if c["id"] not in seen:
                        seen[c["id"]] = c
                        new += 1
                if not cards or new == 0:
                    empty += 1
                else:
                    empty = 0
                if empty >= 2:
                    break
                time.sleep(random.uniform(0.05, 0.18))
            except Exception as e:
                log(log_path, f"API ERR {section} q={query!r} p{page}: {e}")
                empty += 1
                if empty >= 2:
                    break

    for section, (catid, subcatid) in SECTIONS.items():
        for q in QUERIES:
            api_pull(catid, subcatid, q, section, max_pages=10)
            log(log_path, f"after {section} q={q!r} unique={len(seen)}")

    # city residual on HBM
    catid, subcatid = SECTIONS["hombre-busca-mujer"]
    for city in CITIES:
        api_pull(catid, subcatid, city, "hombre-busca-mujer", max_pages=6)
        log(log_path, f"after city={city} unique={len(seen)}")

    log(log_path, f"GATHER unique={len(seen)}")

    # index existing url hashes from filenames (archive_raw uses hash of url)
    from hashlib import sha256

    def h16(url: str) -> str:
        return sha256(url.encode()).hexdigest()[:16]

    existing_h = set()
    for p in RAW.glob("*.html"):
        hh = hash_from_name(p.name)
        if hh:
            existing_h.add(hh)

    pending = []
    for c in seen.values():
        if h16(c["url"]) in existing_h:
            continue
        pending.append(c)
    log(log_path, f"pending={len(pending)}")

    workers = 12
    sessions = [make_session("doplim") for _ in range(workers)]
    saved = skip = err = 0
    t0 = time.time()

    def fetch_i(item):
        i, c = item
        s = sessions[i % workers]
        url = c["url"]
        try:
            r = s.get(url, timeout=25)
            html = r.text or ""
            ok, why = quality_ok(html, url)
            if not ok:
                return i, "skip", why
            path = archive_raw(RAW, "doplim_ayuda", url, html)
            return i, "saved", path.name
        except Exception as e:
            return i, "err", str(e)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(fetch_i, (i, c)) for i, c in enumerate(pending)]
        done = 0
        for fut in as_completed(futs):
            i, status, info = fut.result()
            done += 1
            if status == "saved":
                saved += 1
            elif status == "skip":
                skip += 1
            else:
                err += 1
            if done % 25 == 0 or done == len(pending) or done <= 5:
                rate = saved / max((time.time() - t0) / 60.0, 1e-6)
                log(
                    log_path,
                    f"PROGRESS i={done}/{len(pending)} saved={saved} skip={skip} err={err} "
                    f"rate={rate:.1f}/min {info or ''}",
                )

    log(log_path, f"DONE saved={saved} skip={skip} err={err}")


if __name__ == "__main__":
    main()
