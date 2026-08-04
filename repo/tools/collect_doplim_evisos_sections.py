#!/usr/bin/env python3
"""Two-phase massive collector for Doplim + Evisos Peru HBM / relaciones ocasionales.

Phase A (list gather): Selenium (Playwright fallback) navigates section listing pages,
dismisses adult modals, paginates (Ver más / clasificados/N), extracts main-card ad URLs
(expect 10+ per page).

Phase B (detail fetch): parallel/batched detail navigation with quality gates
(not empty/blocked/loading skeleton) + use-case relevance checks, archives raw HTML
under data/raw/ads until targets are met.

Public pages only. No login/CAPTCHA bypass.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import random
import re
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.scrape_ads import (  # noqa: E402
    archive_raw,
    fetch_playwright,
    fetch_selenium,
    has_substantial_ad_content,
    is_access_interstitial,
    text_from_html,
)

RAW_DIR = ROOT / "data" / "raw" / "ads"
SCRATCH = ROOT / "SCRATCH" / "implementer"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

DOPLIM_CITIES = [
    "lima",
    "arequipa",
    "trujillo",
    "cusco",
    "piura",
    "chiclayo",
    "callao",
    "huancayo",
    "ica",
    "tacna",
    "puno",
    "cajamarca",
    "chimbote",
    "ayacucho",
    "huancavelica",
    "iquitos",
    "tarapoto",
    "pucallpa",
    "juliaca",
    "sullana",
    "huaraz",
    "chincha",
    "tumbes",
    "moquegua",
    "abancay",
    "huánuco",
    "huanuco",
    "pasco",
    "bagua",
    "jaen",
]

DOPLIM_SECTIONS = [
    "hombre-busca-mujer",
    "relaciones-ocasionales",
    "contactos",
    "mujer-busca-hombre",
]

# Evisos list bases: keyword + section equivalents of HBM / RO / encuentros
EVISOS_LIST_BASES = [
    "https://www.evisos.com.pe/por-ayuda-economica.htm",
    "https://www.evisos.com.pe/apoyo-economico.htm",
    "https://www.evisos.com.pe/por-apoyo-economico.htm",
    "https://lima.evisos.com.pe/por-ayuda-economica.htm",
    "https://lima.evisos.com.pe/apoyo-economico.htm",
    "https://www.evisos.com.pe/brindo-ayuda.htm",
    "https://www.evisos.com.pe/doy-ayuda.htm",
    "https://www.evisos.com.pe/brindo-apoyo.htm",
    "https://www.evisos.com.pe/encuentros.htm",
    "https://lima.evisos.com.pe/encuentros.htm",
    "https://www.evisos.com.pe/por-encuentros.htm",
    "https://www.evisos.com.pe/hombre-busca-mujer.htm",
    "https://www.evisos.com.pe/por-hombre-busca-mujer.htm",
    "https://www.evisos.com.pe/contactos-ocasionales-peru.htm",
    "https://www.evisos.com.pe/relaciones-ocasionales.htm",
    "https://www.evisos.com.pe/por-relaciones-ocasionales.htm",
    "https://lima.evisos.com.pe/contactos.htm",
    "https://arequipa.evisos.com.pe/encuentros.htm",
    "https://trujillo.evisos.com.pe/encuentros.htm",
    "https://cusco.evisos.com.pe/encuentros.htm",
    "https://piura.evisos.com.pe/encuentros.htm",
    "https://chiclayo.evisos.com.pe/encuentros.htm",
]

# Card / detail relevance for ManiPsych use case (personal contact + economic-offer signals)
RELEVANCE_POS = re.compile(
    r"ayuda\s*econ[oó]mic|apoyo\s*econ[oó]mic|brindo\s*(ayuda|apoyo)|doy\s*(ayuda|apoyo)|"
    r"hombre\s*busca\s*mujer|mujer\s*busca\s*hombre|relaciones?\s*ocasional|"
    r"encuentro|caballero|discreta|universitaria|se[nñ]orita|madre\s*soltera|"
    r"ofrezco\s*(sexo|apoyo|ayuda)|brindo\s*sexo|busco\s*(mujer|chica|se[nñ]ora|alguien)|"
    r"soy\s*(hombre|var[oó]n|caballero|joven|pasivo|activo)|maduro.*(mujer|chica)|sugar|solvente|"
    r"\bsexo\b|\bchica\b|\bmujeres?\b|\bmaduras?\b|\bdiscreto\b|\bwhats?app\b|"
    r"masaje|relax|casual|amiguita|pareja|soltera|soltero|var[oó]n",
    re.I,
)
RELEVANCE_NEG = re.compile(
    r"peugeot|toyota|hyundai|alquila\s*local|maleta|puertas?\s*levadiz|"
    r"reaming|escariador|calamina|aluzinc|operario\s*de\s*producci|"
    r"vendedores?\s*para|baterista|guitarrista|volantes|fachaleta|"
    r"lavadora|electrodom[eé]stic|casa\s*en\s*venta|departamento\s*en\s*venta",
    re.I,
)

_LOG_LOCK = threading.Lock()
_SAVE_LOCK = threading.Lock()


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(path: Path, msg: str) -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    with _LOG_LOCK:
        print(line, flush=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def hash_url(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def ad_id_from_url(url: str) -> str | None:
    m = re.search(r"-id-(\d+)", url, re.I) or re.search(r"/id-(\d+)", url, re.I)
    return m.group(1) if m else None


def platform_of(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "doplim" in host:
        return "doplim"
    if "evisos" in host:
        return "evisos"
    return "other"


def existing_raw_keys(raw_dir: Path) -> set[str]:
    """Map of url-hash16 and platform-id keys already archived."""
    keys: set[str] = set()
    if not raw_dir.exists():
        return keys
    for p in raw_dir.glob("*.html"):
        name = p.name
        # filename: {source_id}_{hash16}.html
        if "_" in name and name.endswith(".html"):
            h = name.rsplit("_", 1)[-1].replace(".html", "")
            if len(h) == 16:
                keys.add(h)
            keys.add(name.lower())
        # also index by embedded canonical url if cheap
    return keys


def count_raw_by_platform(raw_dir: Path) -> dict[str, int]:
    counts = {"doplim": 0, "evisos": 0, "other": 0}
    if not raw_dir.exists():
        return counts
    for p in raw_dir.glob("*.html"):
        n = p.name.lower()
        try:
            head = p.read_text(encoding="utf-8", errors="ignore")[:2500].lower()
        except Exception:
            head = ""
        if "doplim" in n or "doplim" in head or "cnt-list_ads" in head:
            counts["doplim"] += 1
        elif "evisos" in n or "evisos" in head or "listing-link" in head:
            counts["evisos"] += 1
        else:
            # secondary filename heuristics used by prior collectors
            if n.startswith(("dop", "doplim", "seed_dop", "dopcat")):
                counts["doplim"] += 1
            elif n.startswith("evisos"):
                counts["evisos"] += 1
            else:
                counts["other"] += 1
    return counts


def is_relevant_card_or_detail(text: str, url: str = "", strict: bool = False) -> bool:
    hay = f"{text} {url}".lower()
    if RELEVANCE_NEG.search(hay) and not RELEVANCE_POS.search(hay):
        return False
    if strict:
        return bool(
            re.search(
                r"ayuda\s*econ|apoyo\s*econ|brindo\s*(ayuda|apoyo)|doy\s*(ayuda|apoyo)",
                hay,
                re.I,
            )
        )
    return bool(RELEVANCE_POS.search(hay))


def extract_doplim_main_cards(html: str, base_url: str) -> list[dict[str, str]]:
    """Extract ALL main ad cards from li.cnt-list_ads (HBM/RO section pages).

    On true section URLs we keep every main card (10–30+ expected). Pure product
    leakage is rare once city/section paths + adult modal are correct; residual
    junk is filtered again on detail.
    """
    soup = BeautifulSoup(html, "lxml")
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    cards = soup.select("li.cnt-list_ads, li[class*='cnt-list_ads']")
    section_page = any(
        k in base_url for k in ("hombre-busca", "relaciones-ocasionales", "/s/contactos/", "mujer-busca")
    )
    for card in cards:
        ctext = card.get_text(" ", strip=True)
        href = None
        for a in card.find_all("a", href=True):
            h = urljoin(base_url, a["href"])
            if re.search(r"-id-\d+\.html", h, re.I) or re.search(r"/id-\d+", h, re.I):
                href = h
                break
        if not href:
            continue
        aid = ad_id_from_url(href)
        if not aid or aid in seen:
            continue
        if not section_page:
            # Non-section: require personal/use-case signals; drop pure products
            if RELEVANCE_NEG.search(ctext) and not RELEVANCE_POS.search(ctext):
                continue
            if not RELEVANCE_POS.search(ctext):
                continue
        else:
            # Section pages: drop only obvious product/rental junk without personal signals
            if RELEVANCE_NEG.search(ctext) and not RELEVANCE_POS.search(ctext) and not re.search(
                r"sexo|mujer|hombre|chica|encuentro|busco|ofrezco|discreta|masaje|activo|pasivo",
                ctext,
                re.I,
            ):
                continue
        seen.add(aid)
        out.append({"url": href, "text": ctext[:240], "id": aid, "platform": "doplim"})
    return out


def extract_evisos_main_cards(html: str, base_url: str, loose: bool = False) -> list[dict[str, str]]:
    """Extract main listing cards (h2.title inside .info).

    loose=True keeps almost all main title cards for volume; detail phase filters.
    """
    soup = BeautifulSoup(html, "lxml")
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    # Primary main cards
    for a in soup.select("h2.title a, h2 a.title, .title a"):
        href = urljoin(base_url, a.get("href") or "")
        aid = ad_id_from_url(href)
        if not aid or aid in seen:
            continue
        block = a.find_parent("div") or a
        cat_el = block.select_one(".category-zone") if hasattr(block, "select_one") else None
        cat = cat_el.get_text(" ", strip=True) if cat_el else ""
        title = a.get_text(strip=True)
        desc_el = block.select_one(".desc") if hasattr(block, "select_one") else None
        desc = desc_el.get_text(" ", strip=True) if desc_el else ""
        hay = f"{cat} {title} {desc}"
        if not loose:
            if not is_relevant_card_or_detail(hay, href, strict=False):
                continue
            if RELEVANCE_NEG.search(hay) and not RELEVANCE_POS.search(hay):
                continue
        else:
            # loose: drop only hard product categories without personal terms
            if RELEVANCE_NEG.search(hay) and not RELEVANCE_POS.search(hay):
                if re.search(
                    r"ofertas de trabajo|inmuebles|autos|motos|electro|puertas|calamina|productos industriales",
                    hay,
                    re.I,
                ):
                    continue
        seen.add(aid)
        out.append(
            {
                "url": href.split("?")[0],
                "text": hay[:240],
                "id": aid,
                "platform": "evisos",
                "title": title,
                "category": cat,
            }
        )
    return out


def dismiss_adult_overlays(page) -> None:
    """Dismiss Doplim/Evisos adult warning modals so pagination clicks work."""
    try:
        page.evaluate(
            """() => {
            const clickTexts = ['soy mayor de 18', 'mayor de 18', 'acepto', 'entrar', 'continuar', 'aceptar'];
            for (const el of document.querySelectorAll('a,button,input,label')) {
              const t = ((el.innerText || el.value || el.getAttribute('aria-label') || '') + '').toLowerCase();
              if (clickTexts.some(x => t.includes(x))) {
                try { el.click(); } catch (e) {}
              }
            }
            const m = document.querySelector('#modalWarning, .modal.show, [role=dialog].modal');
            if (m) {
              m.classList.remove('show');
              m.style.display = 'none';
              m.setAttribute('aria-hidden', 'true');
            }
            document.querySelectorAll('.modal-backdrop').forEach(e => e.remove());
            document.body.classList.remove('modal-open');
            document.body.style.removeProperty('overflow');
            document.cookie = 'adult_content=1; path=/; max-age=31536000';
            document.cookie = 'adult=1; path=/; max-age=31536000';
            try { localStorage.setItem('adult', '1'); localStorage.setItem('adult_content', '1'); } catch (e) {}
        }"""
        )
    except Exception:
        pass
    time.sleep(0.8)


def make_browser(engine: str = "playwright", headless: bool = True):
    """Return (engine_name, browser_or_driver, context_or_none)."""
    if engine == "selenium":
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            from webdriver_manager.chrome import ChromeDriverManager

            options = Options()
            if headless:
                options.add_argument("--headless=new")
            options.add_argument("--lang=es-PE")
            options.add_argument("--window-size=1400,900")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument(
                "--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
            )
            if Path(CHROME).exists():
                options.binary_location = CHROME
            driver = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()), options=options
            )
            driver.set_page_load_timeout(75)
            return "selenium", driver, None
        except Exception as exc:
            print(f"[browser] selenium failed ({exc}); falling back to playwright", flush=True)

    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    launch_kwargs = {"headless": headless, "args": ["--no-sandbox", "--disable-dev-shm-usage"]}
    if Path(CHROME).exists():
        launch_kwargs["executable_path"] = CHROME
    browser = pw.chromium.launch(**launch_kwargs)
    ctx = browser.new_context(
        locale="es-PE",
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1400, "height": 900},
        extra_http_headers={
            "Accept-Language": "es-PE,es;q=0.9,en-US;q=0.5,en;q=0.3",
            "Referer": "https://www.google.com.pe/",
        },
    )
    # stash pw on browser for cleanup
    browser._pw = pw  # type: ignore[attr-defined]
    return "playwright", browser, ctx


def close_browser(engine: str, browser, ctx=None) -> None:
    try:
        if engine == "selenium":
            browser.quit()
        else:
            if ctx:
                ctx.close()
            browser.close()
            pw = getattr(browser, "_pw", None)
            if pw:
                pw.stop()
    except Exception:
        pass


def page_goto(engine: str, browser, ctx, url: str) -> str:
    if engine == "selenium":
        browser.get(url)
        time.sleep(random.uniform(2.5, 4.5))
        dismiss_adult_selenium(browser)
        time.sleep(1.0)
        return browser.page_source
    page = ctx.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=80000)
        page.wait_for_timeout(int(random.uniform(2500, 4500)))
        dismiss_adult_overlays(page)
        page.wait_for_timeout(1500)
        try:
            page.wait_for_selector(
                "li.cnt-list_ads, h2.title a, a.show_more, .results-found, h1",
                timeout=15000,
            )
        except Exception:
            pass
        for _ in range(3):
            page.evaluate("window.scrollBy(0, 700)")
            page.wait_for_timeout(600)
        return page.content()
    finally:
        page.close()


def dismiss_adult_selenium(driver) -> None:
    try:
        driver.execute_script(
            """
            const clickTexts = ['soy mayor de 18', 'mayor de 18', 'acepto', 'entrar', 'continuar'];
            for (const el of document.querySelectorAll('a,button,input,label')) {
              const t = ((el.innerText || el.value || '') + '').toLowerCase();
              if (clickTexts.some(x => t.includes(x))) { try { el.click(); } catch (e) {} }
            }
            const m = document.querySelector('#modalWarning');
            if (m) { m.classList.remove('show'); m.style.display='none'; }
            document.querySelectorAll('.modal-backdrop').forEach(e => e.remove());
            document.body.classList.remove('modal-open');
            document.cookie = 'adult_content=1; path=/';
            """
        )
    except Exception:
        pass


def doplim_show_more_loop(engine: str, browser, ctx, url: str, log_path: Path, max_clicks: int = 40) -> list[dict]:
    """Load a Doplim city/section page and click Ver más until exhausted; return cards."""
    collected: dict[str, dict] = {}
    if engine == "selenium":
        browser.get(url)
        time.sleep(3)
        dismiss_adult_selenium(browser)
        time.sleep(1.5)
        html = browser.page_source
        for card in extract_doplim_main_cards(html, url):
            collected[card["id"]] = card
        log(log_path, f"DOPLIM start {url} cards={len(collected)}")
        for i in range(max_clicks):
            before = len(collected)
            try:
                browser.execute_script(
                    """
                    const m = document.querySelector('#modalWarning');
                    if (m) { m.classList.remove('show'); m.style.display='none'; }
                    document.querySelectorAll('.modal-backdrop').forEach(e => e.remove());
                    document.body.classList.remove('modal-open');
                    const a = document.querySelector('a.show_more');
                    if (a) { a.click(); return true; }
                    return false;
                    """
                )
                time.sleep(random.uniform(2.5, 4.0))
            except Exception as e:
                log(log_path, f"  show_more click fail: {e}")
                break
            html = browser.page_source
            for card in extract_doplim_main_cards(html, url):
                collected[card["id"]] = card
            log(log_path, f"  show_more #{i+1}: {before}->{len(collected)}")
            if len(collected) <= before:
                # one more try after extra wait
                time.sleep(2)
                html = browser.page_source
                for card in extract_doplim_main_cards(html, url):
                    collected[card["id"]] = card
                if len(collected) <= before:
                    break
        return list(collected.values())

    # Playwright: keep a live page for repeated show_more
    page = ctx.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=80000)
        page.wait_for_timeout(3000)
        dismiss_adult_overlays(page)
        page.wait_for_timeout(2000)
        html = page.content()
        for card in extract_doplim_main_cards(html, url):
            collected[card["id"]] = card
        log(log_path, f"DOPLIM start {url} cards={len(collected)}")
        for i in range(max_clicks):
            before = len(collected)
            dismiss_adult_overlays(page)
            clicked = page.evaluate(
                """() => {
                const m = document.querySelector('#modalWarning');
                if (m) { m.classList.remove('show'); m.style.display='none'; }
                document.querySelectorAll('.modal-backdrop').forEach(e => e.remove());
                document.body.classList.remove('modal-open');
                const a = document.querySelector('a.show_more');
                if (a) { a.click(); return true; }
                return false;
            }"""
            )
            if not clicked:
                log(log_path, "  no show_more control")
                break
            page.wait_for_timeout(int(random.uniform(2500, 4000)))
            html = page.content()
            for card in extract_doplim_main_cards(html, url):
                collected[card["id"]] = card
            log(log_path, f"  show_more #{i+1}: {before}->{len(collected)}")
            if len(collected) <= before:
                page.wait_for_timeout(2000)
                html = page.content()
                for card in extract_doplim_main_cards(html, url):
                    collected[card["id"]] = card
                if len(collected) <= before:
                    break
        return list(collected.values())
    finally:
        page.close()


def evisos_list_url(base: str, page_n: int) -> str:
    if page_n <= 1:
        return base
    if base.endswith(".htm"):
        stem = base[:-4]
        return f"{stem}/clasificados/{page_n}"
    return f"{base.rstrip('/')}/clasificados/{page_n}"


def gather_doplim(engine: str, browser, ctx, log_path: Path, max_cities: int, max_clicks: int) -> list[dict]:
    all_cards: dict[str, dict] = {}
    cities = DOPLIM_CITIES[:max_cities] if max_cities else DOPLIM_CITIES
    for section in DOPLIM_SECTIONS:
        for city in cities:
            url = f"https://www.doplim.com.pe/s/{section}/{city}/"
            try:
                cards = doplim_show_more_loop(engine, browser, ctx, url, log_path, max_clicks=max_clicks)
                log(log_path, f"DOPLIM {section}/{city}: {len(cards)} main cards")
                if len(cards) < 10 and cards:
                    log(log_path, f"  WARN <10 cards on page for {url}")
                for c in cards:
                    c["section"] = section
                    c["city"] = city
                    all_cards[c["id"]] = c
                time.sleep(random.uniform(1.5, 3.0))
            except Exception as e:
                log(log_path, f"DOPLIM ERR {url}: {type(e).__name__}: {e}")
    return list(all_cards.values())


def gather_evisos(engine: str, browser, ctx, log_path: Path, max_pages: int) -> list[dict]:
    all_cards: dict[str, dict] = {}
    for base in EVISOS_LIST_BASES:
        low_streak = 0
        for page_n in range(1, max_pages + 1):
            url = evisos_list_url(base, page_n)
            try:
                html = page_goto(engine, browser, ctx, url)
                if is_access_interstitial(html) or len(html) < 2000:
                    log(log_path, f"EVISOS skip inter/short {url} len={len(html)}")
                    low_streak += 1
                    if low_streak >= 2:
                        break
                    continue
                # loose extract for volume on known personal/keyword bases; detail filters
                cards = extract_evisos_main_cards(html, url, loose=True)
                strict_cards = extract_evisos_main_cards(html, url, loose=False)
                log(
                    log_path,
                    f"EVISOS p{page_n} {url}: main_loose={len(cards)} main_strict={len(strict_cards)}",
                )
                if len(cards) >= 10:
                    log(log_path, "  OK 10+ main cards")
                # Prefer strict cards first (prepend), then loose
                for c in strict_cards + cards:
                    all_cards.setdefault(c["id"], c)
                if len(cards) == 0 and len(strict_cards) == 0:
                    low_streak += 1
                else:
                    low_streak = 0
                if low_streak >= 3:
                    break
                # stop early if pagination loops same ids
                if page_n >= 2 and len(cards) > 0:
                    # if no new ids vs previous accumulation growth is zero for this base
                    pass
                time.sleep(random.uniform(1.2, 2.5))
            except Exception as e:
                log(log_path, f"EVISOS ERR {url}: {type(e).__name__}: {e}")
                low_streak += 1
                if low_streak >= 2:
                    break
    return list(all_cards.values())


def quality_ok(html: str, url: str) -> tuple[bool, str]:
    if not html or len(html) < 1800:
        return False, "short_html"
    if is_access_interstitial(html):
        return False, "interstitial"
    low = html.lower()[:3500]
    if any(k in low for k in ("cargando", "un momento", "verificando tu navegador", "serás redirigido", "seras redirigido")):
        return False, "loading_gate"
    if not has_substantial_ad_content(html, url):
        return False, "no_substantial"
    text = text_from_html(html)
    if len(text) < 180:
        return False, "thin_text"
    return True, "ok"


def detail_relevant(html: str, url: str, strict: bool) -> tuple[bool, str]:
    soup = BeautifulSoup(html, "lxml")
    title = ""
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(" ", strip=True)
    if not title and soup.title:
        title = soup.title.get_text(" ", strip=True)
    body = text_from_html(html)[:6000]
    hay = f"{title} {body} {url}"
    # Hard reject product/job junk even if a weak personal token appears once
    if RELEVANCE_NEG.search(hay) and not re.search(
        r"ayuda\s*econ|apoyo\s*econ|brindo\s*(ayuda|apoyo)|doy\s*(ayuda|apoyo)|hombre\s*busca|encuentro|relaciones?\s*ocasional|\bsexo\b|discreta|universitaria",
        hay,
        re.I,
    ):
        return False, "junk_category"
    if "evisos" in url.lower():
        # Evisos is noisy: require stronger personal/economic-contact signals
        if not re.search(
            r"ayuda\s*econ|apoyo\s*econ|brindo\s*(ayuda|apoyo)|doy\s*(ayuda|apoyo)|"
            r"hombre\s*busca|mujer\s*busca|encuentro|relaciones?\s*ocasional|"
            r"\bsexo\b|discreta|universitaria|se[nñ]orita|madre\s*soltera|"
            r"caballero|busco\s*(mujer|hombre|chica|pareja)|ofrezco\s*(sexo|apoyo|ayuda)",
            hay,
            re.I,
        ):
            return False, "not_relevant"
    else:
        if not is_relevant_card_or_detail(hay, url, strict=strict):
            return False, "not_relevant"
    return True, title[:120]


def fetch_detail_html(url: str, mode: str, retries: int = 3) -> str:
    last = ""
    for attempt in range(retries):
        try:
            if mode == "selenium":
                html = fetch_selenium(url, timeout=55, headless=True)
            else:
                html = fetch_playwright(url, timeout_ms=70000, max_retries=3)
            last = html or last
            ok, reason = quality_ok(html, url)
            if ok:
                return html
            time.sleep(random.uniform(3, 8))
        except Exception:
            time.sleep(random.uniform(3, 8))
    return last


def save_ad(html: str, url: str, platform: str, collector: str, meta: dict | None = None) -> Path | None:
    tag = f"{platform}_{collector}"
    with _SAVE_LOCK:
        path = archive_raw(RAW_DIR, tag, url, html)
        # sidecar meta for later rebuild
        meta_path = path.with_suffix(".meta.json")
        payload = {
            "url": url,
            "platform": platform,
            "collector": collector,
            "saved_at": utc_now(),
            "raw_archive_ref": f"data/raw/ads/{path.name}",
            **(meta or {}),
        }
        try:
            meta_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        return path


def already_have(url: str, raw_keys: set[str]) -> bool:
    h16 = hash_url(url)[:16]
    if h16 in raw_keys:
        return True
    aid = ad_id_from_url(url)
    if aid:
        # scan raw_keys for id in filename is weak; also check file existence pattern
        for p in RAW_DIR.glob(f"*{aid}*.html"):
            return True
        # content-based: check any html containing the exact id path fragment is expensive; skip
    return False


def phase_b_fetch_batch(
    cards: list[dict],
    log_path: Path,
    mode: str,
    workers: int,
    target_doplim: int,
    target_evisos: int,
    strict_relevance: bool,
    stats: dict,
) -> None:
    raw_keys = existing_raw_keys(RAW_DIR)
    counts = count_raw_by_platform(RAW_DIR)
    stats["start_counts"] = dict(counts)
    log(log_path, f"PHASE B start counts={counts} candidates={len(cards)} workers={workers} mode={mode}")

    lock = threading.Lock()

    def handle(card: dict) -> None:
        nonlocal counts, raw_keys
        url = card["url"]
        platform = card.get("platform") or platform_of(url)
        with lock:
            if counts.get("doplim", 0) >= target_doplim and counts.get("evisos", 0) >= target_evisos:
                return
            if platform == "doplim" and counts.get("doplim", 0) >= target_doplim:
                return
            if platform == "evisos" and counts.get("evisos", 0) >= target_evisos:
                return
            if already_have(url, raw_keys):
                stats["skip_dup"] = stats.get("skip_dup", 0) + 1
                return

        html = fetch_detail_html(url, mode=mode, retries=3)
        ok, reason = quality_ok(html, url)
        if not ok:
            with lock:
                stats[f"skip_{reason}"] = stats.get(f"skip_{reason}", 0) + 1
            log(log_path, f"SKIP {platform} {reason} {url[:90]}")
            return
        rel_ok, title = detail_relevant(html, url, strict=strict_relevance)
        if not rel_ok:
            with lock:
                stats["skip_not_relevant"] = stats.get("skip_not_relevant", 0) + 1
            log(log_path, f"SKIP not_relevant {url[:90]}")
            return
        path = save_ad(
            html,
            url,
            platform,
            collector="section_mass",
            meta={"title": title, "list_text": card.get("text", "")[:200], "section": card.get("section", "")},
        )
        with lock:
            raw_keys.add(hash_url(url)[:16])
            counts[platform] = counts.get(platform, 0) + 1
            stats["saved"] = stats.get("saved", 0) + 1
            stats[f"saved_{platform}"] = stats.get(f"saved_{platform}", 0) + 1
        log(log_path, f"SAVED {platform} {path.name if path else '?'} title={title[:60]!r} totals={counts}")

    # Process in batches to allow mid-run stops
    batch_size = max(workers * 2, 8)
    for i in range(0, len(cards), batch_size):
        with lock:
            if counts.get("doplim", 0) >= target_doplim and counts.get("evisos", 0) >= target_evisos:
                log(log_path, "TARGETS reached; stopping phase B")
                break
        batch = cards[i : i + batch_size]
        # Prefer filling the lagging platform first
        batch = sorted(
            batch,
            key=lambda c: (
                0
                if (c.get("platform") == "evisos" and counts.get("evisos", 0) < target_evisos)
                else 0
                if (c.get("platform") == "doplim" and counts.get("doplim", 0) < target_doplim)
                else 1,
            ),
        )
        if workers <= 1:
            for card in batch:
                handle(card)
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
                futs = [ex.submit(handle, c) for c in batch]
                for f in concurrent.futures.as_completed(futs):
                    try:
                        f.result()
                    except Exception as e:
                        log(log_path, f"worker err {e}")
        time.sleep(random.uniform(1.0, 2.5))

    stats["end_counts"] = count_raw_by_platform(RAW_DIR)
    log(log_path, f"PHASE B done stats={stats}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Mass Doplim/Evisos HBM+RO section collector")
    parser.add_argument("--engine", choices=("playwright", "selenium"), default="playwright")
    parser.add_argument("--detail-mode", choices=("playwright", "selenium"), default="playwright")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--phase", choices=("all", "gather", "fetch", "both"), default="both")
    parser.add_argument("--target-doplim", type=int, default=1500)
    parser.add_argument("--target-evisos", type=int, default=1500)
    parser.add_argument("--max-cities", type=int, default=0, help="0=all cities")
    parser.add_argument("--max-show-more", type=int, default=35)
    parser.add_argument("--max-evisos-pages", type=int, default=40)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--strict-relevance", action="store_true", help="Require ayuda/apoyo econ terms")
    parser.add_argument("--seeds-out", type=Path, default=SCRATCH / "doplim_evisos_seeds.jsonl")
    parser.add_argument("--seeds-in", type=Path, default=None)
    parser.add_argument("--platform", choices=("all", "doplim", "evisos"), default="all")
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    SCRATCH.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    log_path = SCRATCH / f"collect_doplim_evisos_{ts}.log"
    log(log_path, f"START engine={args.engine} detail={args.detail_mode} phase={args.phase} targets D={args.target_doplim} E={args.target_evisos}")
    log(log_path, f"existing raw counts={count_raw_by_platform(RAW_DIR)}")

    seeds: list[dict] = []
    if args.seeds_in and args.seeds_in.exists():
        for line in args.seeds_in.read_text(encoding="utf-8").splitlines():
            if line.strip():
                seeds.append(json.loads(line))
        log(log_path, f"loaded seeds_in={len(seeds)} from {args.seeds_in}")

    if args.phase in ("all", "gather", "both") and not (args.phase == "fetch" and seeds):
        engine, browser, ctx = make_browser(args.engine, headless=not args.headed)
        try:
            if args.platform in ("all", "doplim"):
                d_cards = gather_doplim(
                    engine, browser, ctx, log_path, max_cities=args.max_cities, max_clicks=args.max_show_more
                )
                seeds.extend(d_cards)
                log(log_path, f"gathered doplim unique={len(d_cards)}")
            if args.platform in ("all", "evisos"):
                e_cards = gather_evisos(
                    engine, browser, ctx, log_path, max_pages=args.max_evisos_pages
                )
                seeds.extend(e_cards)
                log(log_path, f"gathered evisos unique={len(e_cards)}")
        finally:
            close_browser(engine, browser, ctx)

        # dedupe seeds by id/url
        uniq: dict[str, dict] = {}
        for s in seeds:
            key = s.get("id") or s.get("url")
            uniq[key] = s
        seeds = list(uniq.values())
        args.seeds_out.parent.mkdir(parents=True, exist_ok=True)
        with args.seeds_out.open("w", encoding="utf-8") as fh:
            for s in seeds:
                fh.write(json.dumps(s, ensure_ascii=False) + "\n")
        log(log_path, f"wrote seeds {len(seeds)} -> {args.seeds_out}")

    if args.phase in ("all", "fetch", "both"):
        # shuffle but keep platform balance
        random.shuffle(seeds)
        stats: dict = {}
        phase_b_fetch_batch(
            seeds,
            log_path=log_path,
            mode=args.detail_mode,
            workers=args.workers,
            target_doplim=args.target_doplim,
            target_evisos=args.target_evisos,
            strict_relevance=args.strict_relevance,
            stats=stats,
        )
        summary_path = SCRATCH / f"collect_doplim_evisos_summary_{ts}.json"
        summary = {
            "log": str(log_path),
            "seeds": len(seeds),
            "stats": stats,
            "raw_counts": count_raw_by_platform(RAW_DIR),
            "finished_at": utc_now(),
        }
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        log(log_path, f"SUMMARY {summary}")

    final = count_raw_by_platform(RAW_DIR)
    log(log_path, f"FINAL raw counts={final}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
