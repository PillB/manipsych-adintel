#!/usr/bin/env python3
"""Facebook public post collector — search-first only (no login).

Primary path: HTTP fetch of public post URLs (og:title / og:description / message JSON).
Fallback: Playwright only if HTTP lacks TARGET text.

Never logs in, never joins private groups, never bypasses CAPTCHA.
"""

from __future__ import annotations

import argparse
import hashlib
import html as html_lib
import json
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.scrape_ads import archive_raw  # noqa: E402

RAW = ROOT / "data" / "raw" / "ads"
SCR = ROOT / "SCRATCH" / "implementer"

SEED_URLS = [
    "https://www.facebook.com/groups/2382711485285084/posts/4105697169653165/",
    "https://www.facebook.com/groups/2709450222624428/posts/4381946475374786/",
    "https://www.facebook.com/groups/2058190747802106/posts/4331004727187352/",
    "https://www.facebook.com/groups/955328711711298/posts/1968258663751626/",
    "https://www.facebook.com/groups/citas.sanmiguel.lima.lima.peru/posts/1516274410064624/",
]

TARGET_RE = re.compile(
    r"ayuda\s*econ|apoyo\s*econ|brindo\s+(?:ayuda|apoyo)|doy\s+(?:ayuda|apoyo)|"
    r"ofrezco\s+(?:ayuda|apoyo)|ayudo\s*econ|brindo\s+apoyo\s*/\s*econ",
    re.I,
)
OFFER_RE = re.compile(
    r"\b(brindo|doy|ofrezco|caballero|profesional|empresario|hombre)\b",
    re.I,
)
JUNK_RE = re.compile(
    r"refuerzo escolar|apoyo escolar|apoyo acad|apoyo legal|apoyo en spss|"
    r"apoyo en revit|autocad|log[ií]stic|cuidado de ancianos|educadora|"
    r"pacientes|dental|fractura|perrito|hogar temporal|veterinari|"
    r"ALIMENTO|adopte|adopci[oó]n",
    re.I,
)


def log(path: Path, msg: str) -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def normalize_fb(url: str) -> str:
    u = url.strip().replace("m.facebook.com", "www.facebook.com")
    if u.startswith("//"):
        u = "https:" + u
    if "?" in u:
        u = u.split("?", 1)[0]
    if not u.endswith("/"):
        u += "/"
    return u


def already(url: str) -> bool:
    h = hashlib.sha256(url.encode()).hexdigest()[:16]
    if list(RAW.glob(f"*_{h}.html")):
        return True
    m = re.search(r"/posts/(\d+)", url)
    if m and list(RAW.glob(f"*{m.group(1)}*")):
        return True
    return False


def detail_ok(title: str, body: str) -> tuple[bool, str]:
    hay = f"{title}\n{body}"
    if JUNK_RE.search(hay):
        return False, "junk"
    if not TARGET_RE.search(hay):
        return False, "no_target"
    if re.search(r"\bbusco\s+ayuda\b", hay, re.I) and not OFFER_RE.search(hay):
        return False, "seeker_only"
    return True, "ok"


def _unescape_fb(s: str) -> str:
    s = html_lib.unescape(s)
    try:
        s = bytes(s, "utf-8").decode("unicode_escape")
    except Exception:
        pass
    return re.sub(r"\s+", " ", s).strip()


def extract_from_html(page: str) -> tuple[str, str]:
    title = ""
    body = ""
    m = re.search(r'property="og:title"\s+content="([^"]*)"', page)
    if m:
        title = _unescape_fb(m.group(1))
    if not title:
        m = re.search(r"<title[^>]*>([^<]+)</title>", page, re.I)
        if m:
            title = _unescape_fb(m.group(1))
    m = re.search(r'property="og:description"\s+content="([^"]*)"', page)
    if m:
        body = _unescape_fb(m.group(1))
    # GraphQL-ish message text
    msgs = re.findall(r'"message"\s*:\s*\{\s*"text"\s*:\s*"((?:\\.|[^"\\])*)"', page)
    for raw in msgs:
        t = _unescape_fb(raw)
        if len(t) > len(body):
            body = t
    # strip Facebook suffix noise from title
    title = re.sub(r"\s*\|\s*Facebook\s*$", "", title)
    return title[:300], body[:4000]


def build_archive_html(url: str, title: str, body: str, raw_page: str) -> str:
    """Minimal self-contained HTML for rebuild (title+body extractors)."""
    safe_title = html_lib.escape(title)
    safe_body = html_lib.escape(body)
    safe_url = html_lib.escape(url)
    # keep a truncated slice of original for provenance (not full 700k always)
    snippet = raw_page[:80000] if len(raw_page) > 80000 else raw_page
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8"/>
<title>{safe_title}</title>
<meta property="og:title" content="{safe_title}"/>
<meta property="og:description" content="{safe_body}"/>
<meta property="og:url" content="{safe_url}"/>
<link rel="canonical" href="{safe_url}"/>
</head>
<body>
<h1>{safe_title}</h1>
<div class="userContent" data-ad-preview="message">{safe_body}</div>
<!-- original_len={len(raw_page)} -->
<!-- begin_original_snippet -->
{snippet}
<!-- end_original_snippet -->
</body>
</html>
"""


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-PE,es;q=0.9,en;q=0.5",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Upgrade-Insecure-Requests": "1",
        }
    )
    return s


def fetch_http(sess: requests.Session, url: str) -> str:
    r = sess.get(url, timeout=30)
    if r.status_code != 200:
        return ""
    return r.text or ""


def load_seeds(extra: Path | None) -> list[str]:
    urls: list[str] = [normalize_fb(u) for u in SEED_URLS]
    if extra and extra.exists():
        for line in extra.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
                u = d.get("url") or d.get("link") or ""
            except Exception:
                u = line.strip()
            if "facebook.com" in u.lower():
                urls.append(normalize_fb(u))
    for p in (ROOT / "SCRATCH").rglob("*.jsonl"):
        if "facebook" not in p.name.lower() and "fb" not in p.name.lower():
            continue
        try:
            for line in p.read_text(encoding="utf-8", errors="ignore").splitlines()[:400]:
                for m in re.findall(
                    r"https?://(?:www\.|m\.)?facebook\.com/groups/[^/\s\"']+/posts/\d+",
                    line,
                ):
                    urls.append(normalize_fb(m))
        except Exception:
            pass
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u in seen or "facebook.com" not in u:
            continue
        # prefer post URLs
        seen.add(u)
        out.append(u)
    out.sort(key=lambda u: (0 if "/posts/" in u else 1, u))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=40)
    ap.add_argument("--seeds-jsonl", type=Path, default=None)
    ap.add_argument("--max-try", type=int, default=80)
    ap.add_argument("--playwright-fallback", action="store_true")
    args = ap.parse_args()

    RAW.mkdir(parents=True, exist_ok=True)
    SCR.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    log_path = SCR / f"facebook_public_{ts}.log"

    seeds = load_seeds(args.seeds_jsonl)
    log(log_path, f"START seeds={len(seeds)} target={args.target} http_first=1")

    sess = session()
    saved = skip = err = 0
    tried = 0
    for url in seeds:
        if saved >= args.target or tried >= args.max_try:
            break
        tried += 1
        if already(url):
            skip += 1
            continue
        if "/posts/" not in url and "permalink" not in url:
            # bare group pages rarely work without login
            skip += 1
            continue
        try:
            page = fetch_http(sess, url)
        except Exception as e:
            err += 1
            log(log_path, f"HTTP ERR {e}")
            page = ""

        title, body = extract_from_html(page) if page else ("", "")
        if not TARGET_RE.search(f"{title}\n{body}") and args.playwright_fallback:
            try:
                from tools.scrape_ads import fetch_playwright

                page = fetch_playwright(url, timeout_ms=45000, max_retries=1) or page
                title, body = extract_from_html(page)
            except Exception as e:
                log(log_path, f"PW ERR {e}")

        ok, why = detail_ok(title, body)
        if not ok:
            skip += 1
            log(log_path, f"skip_{why} tried={tried} {title[:50]!r}")
            continue
        if len(body) < 20 and len(title) < 20:
            skip += 1
            continue

        html = build_archive_html(url, title, body, page or "")
        path = archive_raw(RAW, "facebook_public", url, html)
        path.with_suffix(".meta.json").write_text(
            json.dumps(
                {
                    "url": url,
                    "platform": "facebook",
                    "title": title[:160],
                    "body_excerpt": body[:400],
                    "saved_at": datetime.now(timezone.utc).isoformat() + "Z",
                    "collector": "collect_facebook_public",
                    "raw_archive_ref": f"data/raw/ads/{path.name}",
                    "fetch": "http",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        saved += 1
        log(log_path, f"SAVED {saved} {title[:60]!r} {path.name}")
        time.sleep(random.uniform(0.8, 1.8))

    log(log_path, f"DONE saved={saved} skip={skip} err={err} tried={tried}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
