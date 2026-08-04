# Collection Agents — Optimal Configurations & Step-by-Step

**Last updated:** 2026-07-08  
**Goal:** Archive valid public ad detail HTML under `data/raw/ads/` for defensive research (ayuda económica / HBM / RO sections). Target ≥1500 raw detail ads per major platform when public supply allows.

Referenced from `AGENT_STATE.md` and `AGENTS.md`. Per-site agent skills live under  
`.grok/skills/collect-{doplim,locanto,evisos,facebook,ciudadanuncios}/`.  
Modeling after collection: `docs/MODELING.md`.

---

## Shared principles (all platforms)

1. **Public pages only** — no login, CAPTCHA solve, or access-control bypass.
2. **Two phases** — (A) gather main-card detail URLs from listings; (B) fetch details in parallel batches.
3. **Main cards only** — never sidebars / “otros anuncios” / footer.
4. **Quality gate before save** — reject short HTML, interstitials, `cargando` / `un momento` / `verificando` loading shells.
5. **Relevance gate** — personal-contact / male-offer / ayuda-económica signals; drop pure products/jobs when possible.
6. **Always** `archive_raw` → `data/raw/ads/{source}_*.html` with optional `.meta.json`.
7. **Throughput** — prefer platform APIs or HTTP when they work; use Playwright/Selenium only when required (Locanto lists, Evisos details, FB).

---

## Platform scoreboard (as of last successful runs)

| Platform | Best tool | List path | Detail path | Sustained rate (observed) | Target status |
|----------|-----------|-----------|-------------|---------------------------|---------------|
| **Doplim** | `tools/collect_doplim_evisos_fast.py` + ayuda topup | `POST /api/getAdsSearch` | HTTP | **~240–350 ads/min** | ≥1500 processed; CAP ROI |
| **Locanto** | `tools/collect_locanto_fast.py` | Mine list HTML + PW `/20701/` | Playwright (HTTP 403) | ~2–5/min/shard | ≥1500 processed; CAP |
| **Ciudad Anuncios** | `tools/collect_ciudadanuncios.py` | Related-ad BFS (search broken) | **HTTP** | **~100–150/min** | Major new source (≥1000 processed) |
| **Facebook** | `tools/collect_facebook_public.py` | `web_search` post permalinks | **HTTP-first** (og/message JSON) | Low (public supply) | Search-first only |
| **Evisos/Evisex** | `tools/collect_evisos_focused.py` | Evisex `apoyo-economico` lists | PW (HTTP 403) | Low; lists rate-limit | Focused only; avoid broad junk |

---

## 1. Doplim Peru (reference high-throughput agent)

### Structure (learned)

- Section URL: `https://www.doplim.com.pe/s/{section}/{city}/`
- Sections: `hombre-busca-mujer` (5/51), `relaciones-ocasionales` (5/54), `mujer-busca-hombre` (5/50), `contactos` (5/0)
- Main cards: `li.cnt-list_ads` → `*-id-{N}.html` (~30/page)
- Adult modal: `#modalWarning` — set cookie `adult_content=1` or click “Soy mayor de 18”
- **Pagination is API, not only UI:** UI `a.show_more[data-page]` posts:

```http
POST https://www.doplim.com.pe/api/getAdsSearch
page, cityid=0, areaid=0, catid, subcatid, query={city}, gal=0, price_min=0, price_max=0, sort_by=
```

Max **page 10** then control removed.

### Optimal command

```bash
python3 tools/collect_doplim_evisos_fast.py \
  --platform doplim \
  --target-doplim 1500 \
  --workers 12-16 \
  --max-pages 10 \
  --early-stop-unique 3500
```

### Step-by-step

1. Warm session: GET a city section URL; set adult cookies.
2. Learn cat/subcat from live JS (or use table above).
3. **Gather:** for each section × city, POST pages 1–10 to `/api/getAdsSearch`; parse `li.cnt-list_ads` links; require 10+ cards when content exists.
4. **Early-stop** when unique IDs ≥ ~2× remaining target.
5. **Fetch:** ThreadPool 12–16 workers; HTTP GET detail; gate quality + relevance; `archive_raw(..., "doplim_fast", ...)`.
6. Stop at ≥1500 Doplim-classified files under `data/raw/ads/`.

### Evidence

- Lima HBM API: 300 IDs / ~3.4s  
- Detail HTTP ~277 ads/min (10 workers)  
- Full run: ~1058 new saves in ~4.4 min at ~240/min → **1500+ Doplim raws**

---

## 2. Locanto Peru (Hombre busca mujer)

### Structure (learned)

- List: `https://www.locanto.com.pe/{city}/Hombre-busca-mujer/20701/?query=ayuda+economica`
- Page N: `.../20701/{N}/?query=...` (preserve query)
- Main cards **only:** `article.posting_listing` → `/ID_{n}/...html`
- ~50 cards/page UI; **19–50+** filtered IDs/page; UI paginator ~20 is display-only
- Plain **HTTP list/detail often 403 / “Un momento”** → Playwright (or Selenium headed) required for live crawl
- **Acceleration:** mine `/ID_` from existing listing HTML already in `data/raw/ads/` (thousands of seeds without re-listing)

### Optimal command

```bash
# Fast seed path: mine /ID_ from listing HTML already in data/raw/ads
# Serial Playwright detail (sync Playwright is NOT thread-safe — workers=1)
python3 tools/collect_locanto_fast.py --mode mine --target 1500 --workers 1

# Mine + live list crawl
python3 tools/collect_locanto_fast.py --mode both --target 1500 --workers 1 \
  --max-pages 40 --cities lima,arequipa,trujillo,cusco,piura,chiclayo,callao,huancayo \
  --queries "ayuda economica,apoyo economico,brindo ayuda,doy ayuda"
```

Legacy: `python3 tools/collect_hombre_locanto.py --max-ads 400`

**Count only tagged detail files** toward 1500: `locanto_fast_*`, `locanto_detail*`, `locanto_hombre*`, `hombre_busca_mujer*` — **not** listing pages (`lima_p*`, `sect_*`).

### Step-by-step

1. Prefer **mine** phase from local listing HTML (`lima_p*`, `sect_*`, etc.) — often 2000+ IDs.
2. Dedup with O(1) seen-set (hashes + meta URLs); skip already-archived IDs.
3. If more seeds needed: Playwright filtered list; `article.posting_listing` only; `/N/` until low yield.
4. Detail: serial `fetch_playwright`; reject inter/loading; relevance gate; `locanto_fast_*.html`.
5. Observed serial rate ~4–10 ads/min (Playwright-bound). For more throughput, run **separate process shards** of seed jsonl — not threads.

### Pitfalls

- Do not treat listing HTML as an “ad”.
- Do not extract IDs outside `article.posting_listing`.
- Do not ThreadPool Playwright sync API (hangs).
- Expect high interstitial rate on live lists; backoff; fresh context.

---

## 3. Evisos Peru

### Structure (learned)

- HBM/RO equivalents: `encuentros.htm`, `hombre-busca-mujer.htm`, `contactos-ocasionales-peru.htm`, `por-ayuda-economica.htm`, `apoyo-economico.htm`
- Main cards: `h2.title a` (+ `.category-zone`, `.desc`)
- Pagination: `{stem}/clasificados/{N}` (page 1 = base `.htm`)
- ~25–30 titles/page when healthy; keyword search is **noisy** (jobs/products)
- **List HTTP often 200; detail HTTP often 403** → Playwright for details

### Optimal command

```bash
python3 tools/collect_evisos_mass.py --target 1500 --max-pages 50
```

### Step-by-step

1. HTTP GET list bases; extract all main `h2.title` cards (loose); keep 10+ when present.
2. Paginate until loop (same ID set) or 3–4 zero-new pages.
3. Merge known-good web-indexed detail URLs.
4. Detail via Playwright only; quality + stronger relevance (personal/econ).
5. Archive `evisos_mass_*.html` / `evisos_pw_*.html`.

### Pitfalls

- Selenium Chrome may hit `ERR_INTERNET_DISCONNECTED` in this environment; prefer Playwright or requests for lists.
- Public indexed personal-ad supply is thinner than Doplim; document exhaustion if &lt;1500 after full pagination + known directs.

---

## 4. Facebook public (indexed)

### Structure

- No reliable public list crawl without login.
- Detail: `/groups/{id}/posts/{id}/`, permalinks; content often in `og:description`.
- Unloaded JS skeletons common → `is_facebook_unloaded_skeleton` + m.facebook fallbacks.

### Optimal approach

1. `web_search`: `site:facebook.com/groups ("brindo ayuda" OR "doy apoyo") (señoritas OR universitarias) (lima OR ...)`
2. Fetch with `fetch_playwright` (extra waits on userContent / og:description).
3. Gate skeleton; archive only substantial posts as `facebook_public_*.html` / `fb_*`.

Throughput will stay **supply/login limited**; do not expect Doplim-class rates.

---

## 5. Selenium vs Playwright vs HTTP

| Need | Prefer |
|------|--------|
| Doplim list+detail | **HTTP + `/api/getAdsSearch`** |
| Locanto list live | **Playwright** (HTTP 403) |
| Locanto seeds | **Mine raw listing HTML** |
| Evisos list | **HTTP** |
| Evisos detail | **Playwright** |
| Debug adult modals / headed | **Selenium headed** (`fetch_selenium`) |
| FB public posts | **Playwright** |

Selenium patterns (when used): es-PE UA, dismiss `#modalWarning`, poll until not “verificando”, click `a.show_more` via JS if needed, then BS4 extract.

---

## 6. Verification checklist

```bash
# Platform raw counts (approximate classifiers)
python3 -c "from tools.collect_doplim_evisos_fast import count_platform_raws; print(count_platform_raws())"
python3 -c "from tools.collect_locanto_fast import count_locanto_detail; print('locanto_detail', count_locanto_detail())"

# Sample new archives
ls -lt data/raw/ads/doplim_fast_*.html | head
ls -lt data/raw/ads/locanto_fast_*.html | head
ls -lt data/raw/ads/evisos*.html | head

# Logs
ls -lt SCRATCH/implementer/*fast*.log SCRATCH/implementer/evisos_mass*.log | head
```

After large raw growth, rebuild processed manifest:

```bash
python3 tools/rebuild_manifest_from_raw.py
python3 tools/phase_gate.py --phase 4
```

---

## 7. Tools map

| Tool | Role |
|------|------|
| `tools/collect_doplim_evisos_fast.py` | Doplim API mass + Evisos HTTP list helper |
| `tools/collect_locanto_fast.py` | Locanto mine + crawl + parallel detail |
| `tools/collect_evisos_mass.py` | Evisos list HTTP + Playwright detail |
| `tools/collect_evisos_playwright.py` | Alternate Evisos PW path |
| `tools/collect_hombre_locanto.py` | Legacy Locanto search-first + list |
| `tools/collect_doplim_evisos_sections.py` | Browser two-phase (debug) |
| `tools/scrape_ads.py` | Shared fetch/extract/archive/gates |
| `tools/selenium_search_first_harvester.py` | Search-first Selenium demo |

---

## 8. Skills (agent auto-invoke)

| Skill | Path |
|-------|------|
| collect-doplim | `.grok/skills/collect-doplim/SKILL.md` |
| collect-locanto | `.grok/skills/collect-locanto/SKILL.md` |
| collect-evisos | `.grok/skills/collect-evisos/SKILL.md` |
| collect-facebook | `.grok/skills/collect-facebook/SKILL.md` |

Invoke: `/collect-doplim`, `/collect-locanto`, etc., or natural language matching skill descriptions.
