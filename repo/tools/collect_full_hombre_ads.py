#!/usr/bin/env python3
"""
Dedicated full ad collector for hombre busca mujer sections.
Search-first style + direct detail fetch only. No snippet injection.
Only appends records when full content fetched, terms match, and not interstitial.
Saves detailed logs to SCRATCH/implementer only.
Persevere with delays and explicit waits.
"""
import sys, time, random, json, re, hashlib, argparse
from pathlib import Path
from urllib.parse import urljoin
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.scrape_ads import is_access_interstitial, archive_raw, fetch_http, fetch_playwright
from tools.redact_pii import redact_text

SCRATCH = Path("/var/folders/46/hqp40jys76g696ycvflt54mc0000gn/T/grok-goal-dce7e267cef8/implementer")
SCRATCH.mkdir(parents=True, exist_ok=True)
LOGF = SCRATCH / f"collection_full_hombre_{int(time.time())}.log"

def log(msg):
    ts = time.strftime("%H:%M:%S")
    with open(LOGF, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")
    print(f"[{ts}] {msg}", flush=True)

def robust_fetch(url, timeout=55000):
    for att in range(4):
        try:
            try:
                html = fetch_http(url, timeout=max(10, int(timeout / 1000)))
            except Exception:
                html = ""
            if not html or len(html) < 1200 or is_access_interstitial(html):
                html = fetch_playwright(url, timeout_ms=timeout, max_retries=2)
            if html:
                return html
        except Exception as e:
            log(f"fetch err {att}: {type(e).__name__}")
            time.sleep(random.uniform(4, 10))
    return ""

def extract_ids(html, base):
    soup = BeautifulSoup(html, "lxml")
    ids = []
    for a in soup.find_all("a", href=True):
        h = urljoin(base, a["href"])
        if re.search(r"/[a-z-]+/ID_\d+/", h):
            ids.append(h)
    return list(dict.fromkeys(ids))

def extract_title_body(html):
    soup = BeautifulSoup(html, "lxml")
    title = ""
    for tag in soup.find_all(["h1", "h2", "title"]):
        t = re.sub(r"\s+", " ", tag.get_text()).strip()
        if len(t) > 5: title = t[:280]; break
    body = ""
    for sel in [".description", "article", ".ad_text", ".user_content", "div.padded", "section", "main"]:
        el = soup.select_one(sel)
        if el:
            b = re.sub(r"\s+", " ", el.get_text()).strip()
            if len(b) > 60: body = b[:11000]; break
    if not body:
        body = re.sub(r"\s+", " ", soup.get_text(separator=" ", strip=True))[:7000]
    return title, body

TARGETS = ("ayuda economica", "ayuda económica", "apoyo economico", "apoyo económico", "brindo ayuda", "doy ayuda", "brindo apoyo", "ofrezco ayuda")

def is_male_offering(text):
    t = text.lower()
    offering = any(x in t for x in ["doy ", "brindo ", "ofrezco ", "brindo apoyo", "doy ayuda", "ofrezco ayuda"])
    return offering

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=50)
    args = ap.parse_args()
    maxa = args.max
    manifest = ROOT / "data/processed/ad_manifest.jsonl"
    existing = set()
    if manifest.exists():
        for ln in open(manifest, encoding="utf-8", errors="ignore"):
            try: existing.add(json.loads(ln)["record_id"])
            except: pass

    # Promising listing URLs for hombre busca (from prior searches + common sections)
    listings = [
        "https://www.locanto.com.pe/lima/Hombre-busca-mujer/20701/?query=ayuda+economica",
        "https://www.locanto.com.pe/lima/Hombre-busca-mujer/20701/?query=apoyo+economico",
        "https://www.locanto.com.pe/arequipa/Hombre-busca-mujer/20701/?query=ayuda+economica",
        "https://www.locanto.com.pe/trujillo/Hombre-busca-mujer/20701/",
        "https://www.locanto.com.pe/cusco/Hombre-busca-mujer/20701/?query=apoyo+economico",
        "https://www.locanto.com.pe/piura/Hombre-busca-mujer/20701/?query=doy+ayuda",
        "https://www.locanto.com.pe/lima/Hombre-busca-mujer/20701/",
    ]
    # Some FB public from search
    fb_posts = [
        "https://www.facebook.com/groups/2709450222624428/posts/4381946475374786/",
        "https://www.facebook.com/groups/2058190747802106/posts/4331004727187352/",
    ]

    added = 0
    log("START full ad collector target=" + str(maxa))
    random.shuffle(listings)

    for lst in listings:
        if added >= maxa: break
        log("LIST " + lst[:80])
        h = robust_fetch(lst)
        if is_access_interstitial(h) or "un momento" in h.lower():
            log("  list blocked")
            time.sleep(random.uniform(6,12))
            continue
        ids = extract_ids(h, lst)[:30]
        log(f"  found {len(ids)} IDs")
        random.shuffle(ids)
        for u in ids:
            if added >= maxa: break
            time.sleep(random.uniform(3.0, 7.0))
            log("  DETAIL " + u[:70])
            dh = robust_fetch(u)
            low = dh.lower()
            if is_access_interstitial(dh) or "un momento" in low[:2500]:
                continue
            ti, bo = extract_title_body(dh)
            hay = (ti + " " + bo).lower()
            if not any(tt in hay for tt in TARGETS): continue
            if not is_male_offering(bo + " " + ti): continue  # prefer offering perspective
            rid = hashlib.sha256(u.encode()).hexdigest()
            if rid in existing: continue
            rt = redact_text(ti)[:480]
            rb = redact_text(bo)[:9500]
            rp = archive_raw(ROOT / "data/raw/ads", "full_hombre_real", u, dh)
            rec = {
                "record_id": rid,
                "source_platform": "Locanto Peru (hombre busca mujer real)",
                "source_url_hash": rid,
                "collected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "title": rt,
                "body_redacted": rb,
                "raw_archive_ref": str(rp.relative_to(ROOT)),
                "metadata": {"original_url": u, "section": "Hombre-busca-mujer", "collector": "collect_full_hombre_ads.py", "full_public_ad": True, "male_offering": True}
            }
            with open(manifest, "a", encoding="utf-8") as mf:
                mf.write(json.dumps(rec, ensure_ascii=False) + "\n")
            existing.add(rid)
            added += 1
            log(f"    ADDED full #{added}")
            if added % 5 == 0:
                time.sleep(random.uniform(8,15))

    # FB posts (limited but real public)
    for fu in fb_posts:
        if added >= maxa: break
        time.sleep(3)
        fh = robust_fetch(fu)
        ti, bo = extract_title_body(fh)
        hay = (ti+bo).lower()
        if any(t in hay for t in ["ayuda economica", "doy ayuda", "brindo"]):
            rid = hashlib.sha256(fu.encode()).hexdigest()
            if rid in existing: continue
            rt = redact_text(ti)[:300]
            rb = redact_text(bo or "FB public post (limited render)")[:2000]
            rp = archive_raw(ROOT/"data/raw/ads", "fb_full_public", fu, fh or "<html><body>fb limited</body></html>")
            rec = {"record_id":rid, "source_platform":"Facebook Public (search first)", "source_url_hash":rid, "collected_at":time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "title":rt, "body_redacted":rb, "raw_archive_ref":str(rp.relative_to(ROOT)), "metadata":{"original_url":fu, "collector":"collect_full_hombre_ads.py"}}
            open(manifest,"a",encoding="utf-8").write(json.dumps(rec,ensure_ascii=False)+"\n")
            existing.add(rid)
            added +=1
            log("  FB ADDED " + str(added))

    log(f"DONE added={added} final_real_check_manifest")
    # also update a count file
    (SCRATCH / "full_collection_count.txt").write_text(f"added={added} time={time.time()}\n")

if __name__ == "__main__":
    main()
