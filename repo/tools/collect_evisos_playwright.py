
#!/usr/bin/env python3
"""Evisos list (HTTP) + detail (Playwright) collector."""
import json, re, sys, time, random
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.scrape_ads import archive_raw, fetch_playwright, has_substantial_ad_content, is_access_interstitial, text_from_html
from tools.collect_doplim_evisos_fast import extract_evisos_urls, evisos_page_url, EVISOS_BASES, count_platform_raws

RAW = ROOT / "data/raw/ads"
SCR = ROOT / "SCRATCH/implementer"
LOG = SCR / f"evisos_pw_collect_{int(time.time())}.log"
POS = re.compile(
    r"ayuda\s*econ|apoyo\s*econ|brindo|doy ayuda|encuentro|hombre busca|mujer busca|"
    r"ocasional|\bsexo\b|discreta|universitaria|se[nñ]orita|madre soltera|caballero|"
    r"busco (mujer|hombre|chica)|ofrezco",
    re.I,
)

def log(m):
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {m}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")

def gather():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        "Accept-Language": "es-PE,es;q=0.9",
        "Referer": "https://www.google.com.pe/",
    })
    allc = {}
    bases = list(EVISOS_BASES) + [
        "https://www.evisos.com.pe/por-ayuda-economica.htm",
        "https://www.evisos.com.pe/apoyo-economico.htm",
        "https://lima.evisos.com.pe/por-ayuda-economica.htm",
        "https://www.evisos.com.pe/encuentros.htm",
        "https://lima.evisos.com.pe/encuentros.htm",
        "https://www.evisos.com.pe/contactos-ocasionales-peru.htm",
        "https://www.evisos.com.pe/hombre-busca-mujer.htm",
        "https://www.evisos.com.pe/relaciones-ocasionales.htm",
        "https://www.evisos.com.pe/por-encuentros.htm",
        "https://www.evisos.com.pe/brindo-ayuda.htm",
        "https://www.evisos.com.pe/doy-ayuda.htm",
    ]
    for base in dict.fromkeys(bases):
        prev = set()
        for page in range(1, 40):
            url = evisos_page_url(base, page)
            try:
                r = s.get(url, timeout=30)
                if r.status_code != 200 or len(r.text) < 1500:
                    # try playwright for list
                    try:
                        html = fetch_playwright(url, timeout_ms=50000, max_retries=2)
                    except Exception:
                        html = ""
                else:
                    html = r.text
                if not html or len(html) < 1500:
                    break
                cards = extract_evisos_urls(html, url, loose=True)
                ids = {c["id"] for c in cards}
                if page > 1 and ids and ids == prev:
                    break
                prev = ids
                new = 0
                for c in cards:
                    if c["id"] not in allc:
                        allc[c["id"]] = c
                        new += 1
                log(f"LIST {url} cards={len(cards)} new={new} total={len(allc)}")
                if new == 0 and page > 1:
                    break
                time.sleep(0.2)
            except Exception as e:
                log(f"LIST ERR {url} {e}")
                break
    # known goods
    known = [
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
    ]
    for u in known:
        m = re.search(r"-id-(\d+)", u)
        if m and m.group(1) not in allc:
            allc[m.group(1)] = {"url": u, "id": m.group(1), "platform": "evisos", "text": "known"}
    return list(allc.values())

def good(html, url):
    if not html or len(html) < 2000: return False, "short"
    if is_access_interstitial(html): return False, "inter"
    if any(k in html.lower()[:3000] for k in ("cargando", "un momento", "verificando tu navegador")):
        return False, "load"
    if not has_substantial_ad_content(html, url): return False, "thin"
    return True, "ok"

def main():
    SCR.mkdir(parents=True, exist_ok=True)
    start = count_platform_raws()
    log(f"START evisos_pw counts={start}")
    cards = gather()
    seeds_path = SCR / f"seeds_evisos_pw_{int(time.time())}.jsonl"
    with seeds_path.open("w") as f:
        for c in cards:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    log(f"gathered {len(cards)} -> {seeds_path}")
    saved = skip = err = 0
    target = 1500
    for i, c in enumerate(cards):
        if start.get("evisos", 0) + saved >= target:
            break
        url = c["url"]
        try:
            html = fetch_playwright(url, timeout_ms=70000, max_retries=3)
        except Exception as e:
            err += 1
            log(f"ERR {e} {url[:70]}")
            continue
        ok, reason = good(html, url)
        if not ok:
            skip += 1
            continue
        soup = BeautifulSoup(html, "lxml")
        title = soup.find("h1").get_text(" ", strip=True) if soup.find("h1") else (soup.title.get_text(strip=True) if soup.title else "")
        hay = f"{title} {text_from_html(html)[:4500]}"
        if not POS.search(hay):
            skip += 1
            continue
        path = archive_raw(RAW, "evisos_pw", url, html)
        meta = {
            "url": url, "platform": "evisos", "title": title[:120],
            "saved_at": datetime.now(timezone.utc).isoformat() + "Z",
            "collector": "evisos_pw", "raw_archive_ref": f"data/raw/ads/{path.name}",
        }
        path.with_suffix(".meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
        saved += 1
        if saved % 5 == 0 or saved < 5:
            log(f"SAVED {saved} {title[:50]!r} {path.name}")
        time.sleep(random.uniform(0.4, 1.0))
        if (i + 1) % 10 == 0:
            log(f"PROGRESS i={i+1}/{len(cards)} saved={saved} skip={skip} err={err} total_evisos={count_platform_raws().get('evisos')}")
    end = count_platform_raws()
    log(f"DONE saved={saved} skip={skip} err={err} end_counts={end}")

if __name__ == "__main__":
    main()
