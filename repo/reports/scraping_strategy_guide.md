# Scraping Strategy Step-by-Step Guide for Agents
## Ayuda Economica / Apoyo Economico / Brindo Ayuda — Male-Offering ("Hombre Busca Mujer" / Contactos) Public Ads

**Goal**: Collect ONLY real, full, non-duplicate public ads with valid `raw_archive_ref`, substantial body, target terms + male-offering signals. Append **only** to `data/processed/ad_manifest.jsonl`. Target >=1000 per platform if public supply allows; otherwise document honest exhaustion after documented high-effort attempts (50+ searches/attempts, city sweeps, 30-50+ fresh directs, multiple parallel techniques).

**Current Verified Baseline (2026-07-08)**: 1,589 strict-valid unique records rebuilt from local raw archives (all with unique raw refs; raws present verified; PII gate pass).
- Locanto Peru: 1,364
- Doplim Peru: 199
- Facebook Public: 26
- 2,372 raw `.html` archives scanned in `data/raw/ads/`
- Rebuild summary: `reports/raw_rebuild_summary.json`
- Gate `phase_gate.py --phase 4`: **PASSED** (PII=0 via _contains_contact_like_pii on full record json, no dups, no inters, raw coherence, required fields + family match)
- Current modeling should use the rebuilt manifest, not ad-hoc appended manifests. Future collection should still follow search-first + full gates + strict filters per this guide.
- Fresh web_search + list_extract on clean listings + short direct batches were historically low incremental yield (dups + inter + filter skips dominant); the raw rebuild recovered additional valid records from archived HTML.

**Mac Selenium recovery note (2026-07-06)**: on this machine, Chrome is installed at `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`, but `chromedriver` was not found in PATH during diagnosis. That specific combination is a common cause of `Chrome closed unexpectedly` in Selenium. The recovery path is now encoded in `tools/selenium_search_first_harvester.py` and `tools/scrape_ads.py`: explicit Chrome/driver discovery, headed-by-default debugging for the Selenium harvester, and a hard fallback to Playwright when the driver is missing.

This is after 100+ fetch attempts, 50+ searches, storms, subagents, parallel bg, strict rebuilds from good raws only, dedup rebuilds, full PII enforcement on complete records. Public indexed supply is limited + high block rate on Locanto. Guide is the single source of truth distilled from all runs. **Future agents MUST read and follow this exactly before any action.**

---

## Core Principles (Non-Negotiable)

1. Public indexed pages only. No login, no private groups, no CAPTCHA bypass.
2. **Search-first** for direct links (`/ID_...`, `id-XXXX`, group posts). Never start broad listing/tag pages.
3. Only full ads: TARGET terms + explicit male-offering perspective. Substantial clean body.
4. Always `archive_raw` → `raw_archive_ref`. Aggressive `redact_text`. Full PII gate **on the complete constructed record** (json.dumps of full record before append; never partial). Dedup by `sha256(url)` record_id (pre-load existing set in every loop). Rebuild manifest from good raws only after any issue.
5. Persevere with **full public gates**: es-PE Playwright + 12 real UAs + google.pe Referer + 30s selector waits + scrolls + len>2500 + anti-cargando/un momento/verificando/interstitial gate + 5-10x retries + 8-25s backoff + fresh ctx.
6. Proof everything to real SCRATCH (`/var/folders/.../implementer` for bg + `SCRATCH/implementer/`). Targeted pytest + `phase_gate --phase 4` after **every** manifest/code change.
7. Never fake, inject, weaken gates, or merge legacy without raws. Re-extract from raw on issues.

---

## Step-by-Step Agent Workflow (4 Phases — Follow in Order)

### Phase 1: Discovery — Search-First (Highest Yield Path)
Use `web_search` (primary) + operators for directs:

- Locanto: `site:locanto.com.pe ("/ID_" OR "Hombre-busca-mujer") ("brindo ayuda" OR "doy ayuda" OR "apoyo economico" OR "ayuda economica" OR "brindo apoyo") (lima OR arequipa OR trujillo OR piura OR chiclayo OR cusco OR callao OR huancayo) ("señoritas" OR "universitarias" OR "18" OR "madres solteras" OR "estudiantes")`
- Exact title phrases from known goods: `"Brindo-apoyo-economico-para-senoritas"`, `"DOY AYUDA ECONOMICA A SENORITAS"`, city + "ID_" variants.
- Doplim: `site:doplim.com.pe OR site:doplim.pe ("brindo ayuda economica" OR "doy ayuda" OR "brindo apoyo economico") (id- OR /id-)`
- FB: public indexed groups only via `site:facebook.com/groups ... -inurl:login`

Save seeds: `SCRATCH/implementer/seeds_*.json` + append `reports/phase4_search_log.json` (query, count, notes, ts). Compile 30-50+ directs from new + known-good.

**Worked**: Produced nearly all real adds (Doplim direct batches + Locanto when clean passed gates). External web_search + ID_ + phrase + city variants succeeded where internal/DDG alone often returned 0 or lists.

**Discarded**: Broad non-ID queries; starting from `/tag/` or listing index pages (90%+ immediate inter/"un momento").

**Rule**: Listings/0 directs → immediately new query with "ID_" + exact phrases from good titles + more cities. Log. Do not hammer lists.

### Phase 2: Robust Fetching (The Core That Produced Full Ads)
**Use exactly `tools/scrape_ads.py:fetch_playwright`** (or faithful port in collectors).

**Exact proven recipe** (copy verbatim patterns):

```python
uas = [  # 12 recent Chrome
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) ... Chrome/133...",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ... Chrome/132...",
    # ... (full list from scrape_ads.py:  Mac/Win/Linux + 1 iOS)
]
extra_headers = {
    "Accept-Language": "es-PE,es;q=0.9,en-US;q=0.5,en;q=0.3",
    "Referer": "https://www.google.com.pe/",
    # Sec-* headers as in source
}
# In loop:
page.goto(url, wait_until="domcontentloaded", timeout=70-80s)
page.wait_for_selector("h1, .description, article, .ad_text, .user_content, a[href*='/ID_']", timeout=30000)
page.wait_for_timeout(random.randint(5000,12000))
# scrolls
if "/Hombre-busca" in url or ... : extra 4-8s
content = page.content()
low = content.lower(); first3k = low[:3000]
inter = is_access_interstitial(content)
if (len(content) < 2500 or
    "cargando" in first3k or "un momento" in first3k or
    "verificando" in first3k or inter):
    browser.close(); time.sleep(random.uniform(8,25)); continue  # fresh ctx next retry
# success return content
```

- max_retries=6-10. Always fresh browser/context per retry. UA rotation.
- Return only substantial non-inter content.

**Selenium fallback** similar (es-PE, explicit waits on h1/.description, random sleeps).

**Worked**: len>2500 + keyword gate + 30s waits + UA/Referer + backoff + fresh ctx turned many directs into usable full HTML. Doplim yielded well; Locanto adds when passed.

**Discarded (Dead Ends)**:
- requests.get / no waits / short waits → loading HTML saved → later gate fail.
- No UA rotation / no fresh ctx → blocks after 1.
- No len/keyword gate → recorded "cargando"/"un momento" screens.
- Hammering without 8-25s backoff.

**Recent observation (persevere batches + list_fresh)**: Even fresh directs frequently hit inter gate or "dup skip" (95%+ on repeated seeds). Need continuous fresh discovery (20-50+ new per wave via web_search). List extract secondary on *clean* (len>2500 !inter) listing renders yielded 48 /ID_ candidates (high potential). "nueva app" banner is usually OK if real body present — do **not** over-reject on it. "filter" skips common on seeker or non-male-offering pages.

### Phase 3: Extract, Filter, Redact, Archive, Write (Strict Contract)
1. BS4: title = first h1/title. Body = prefer `.description`, `article`, `.ad_text`, `main`, `section` (fallback full text, cap ~9.5k).
2. **Strict filter (in order)**:
   ```python
   TARGETS = ("ayuda economica", "apoyo economico", "doy ayuda", "brindo ayuda", "brindo apoyo")
   MALE = ("brindo", "doy", "ofresco", "soy ", "hombre", "señoritas", "universitarias")
   hay = (title + " " + body).lower()
   if not any(t in hay for t in TARGETS) or not any(m in hay for m in MALE): skip
   ```
3. `rt = redact_text(title)[:480]`, `rb = redact_text(body)[:9500]`
4. `if _contains_contact_like_pii(json.dumps({"t":rt,"b":rb})): skip`  (strict: phone/email patterns + redact diff)
5. `rid = hashlib.sha256(u.encode()).hexdigest()`
   - Pre-load `existing = set()` from manifest before loop. Skip if present. (Use `existing_record_ids(manifest)` helper when available.)
6. `rp = archive_raw(RAWDIR, collector_tag, url, html)`  (source-tagged filename, always write raw)
7. Build record **exactly**:
   ```json
   {
     "record_id": rid,
     "source_platform": "Locanto Peru (hombre busca mujer real)" | "Doplim Peru (hombre busca mujer or Contactos)" | "Facebook Public (indexed)",
     "source_url_hash": rid,
     "collected_at": "...Z",
     "title": rt,
     "body_redacted": rb,
     "raw_archive_ref": "data/raw/ads/xxx.html",
     "metadata": {
       "original_url": u,
       "collector": "persevere_..._guide | list_fresh | ...",
       "male_offering_perspective": true,
       "section": "Hombre-busca-mujer or Contactos",
       "full_public_ad": true
     }
   }
   ```
8. Append **only** to main `ad_manifest.jsonl`. Log "ADDED N raw=..."

**Exact filter snippet from successful collectors** (copy):
```python
TARGETS = ('ayuda economica', 'apoyo economico', 'doy ayuda', 'brindo ayuda', 'brindo apoyo')
MALE = ('brindo', 'doy', 'ofresco', 'soy ', 'hombre', 'señoritas', 'universitarias')
hay = (title + ' ' + body).lower()
if not any(t in hay for t in TARGETS) or not any(m in hay for m in MALE): skip
# BS4 extract: h1/title for title; .description / article / main for body (fallback text)
```

**List extract (secondary only)**: After clean listing fetch (len>2500 && !inter), extract /ID_ then detail-fetch each with full gates.

**Live HTML Analysis Findings (2026-07 + filtering fixes after review)**:
- **Locanto**: Main ads ONLY in `article.posting_listing` (~50-52 cards/page, all /ID_ inside main, no side distractors). Pagination via /N/ construction (UI caps display at ~20). Subagent + probes: 1000+ pages with 10+ main cards (no drop-off to p1000); high-page nav (p120/p150) confirmed correct male-offer ads from main cards. Use filtered ?query=ayuda+economica.
- **Doplim**: Main `li.cnt-list_ads` ; `-id-N.html`. Broad /s/hombre-busca-mujer/ pulls unrelated (cars, tools, classes) -- use /s/hombre-busca-mujer/ayuda+economica instead. "Ver más anuncios" .show_more .
- **Filtering**: extract_ad_detail_urls now restricts to main containers + skips bad card keywords. Test some links by fetch to verify "ayuda economica" / "brindo" male-offering. Expect 10+ main target-ish ads per filtered page.
- **Total pages & pagination (updated 2026-07-07 from dedicated quick iterative subagent + probes)**: 
  - p1 paginator UI (`.bst_pagination`): shows links only up to ~19-20 (text "12345...20", links to /20/).
  - Actual: **50-52 `article.posting_listing` main cards per page**. Strict main-card extract yields 19-50+ /ID_ (early/good runs ~49; later 25-33). 
  - Dedicated subagent (stepped+zoom+high to p1000, query+plain): **no drop-off below 10 (min ~19) up to p1000 tested**. UI "20" under-reports heavily; real pages with 10+ main ads **1000+ (very large / effectively unbounded)**. 
  - Fresh high validation (p120/p150): 52 cards / 25 IDs; navigated main-card ad → "Brindo apoyo económico a mujeres que pasen urgencias" (CORRECT male-offer type).
  - Practical: filtered ?query=ayuda+economica + /N/ walk. Stop after 3 consecutive <5-10 qualifying main IDs. Always extract **only** from article.posting_listing.
  - Best practice: always use filtered bases like `/20701/?query=ayuda+economica` + `/N/?query=...` (higher relevance, still ~50/page early on). Two-step mandatory. `next_locanto_listing_url` now preserves query. Main container scoping prevents sides/distractors/other categories. 10+ per page on good filtered pages.
  - Validation: multiple sample navigations from main-card extracts (p1-3,5,30,45+,55,60 range) returned correct male-offer "ayuda economica" ads (titles like "Brindo apoyo Economico...", "Doy ayuda económica a mujeres..."). Pre-fix broad extracts had cars/unrelated; now avoided.
- **FB & iterative**: Search-first or filtered. Run small quick trial-error agents to tune selectors/filters/URLs on 1-2 pages before long full crawls. Navigate/test links for type.
- **Locanto**: Ads via `a.posting_listing__title.js-result_title.js-ad_link` inside `<article class="posting_listing js-bst_list_item ...">`, href containing `/ID_\d+/`. Pagination containers: `div.bst_pagination.js-bst_pagination` containing numbered `a.bst_pagination__item.hitbox` (e.g. `/20701/1/`, `/2/`, `/3/`). Subagent confirmed successful poll + BS4 extract on these (49-50 IDs per page).
- **Doplim**: Ads `...-id-NNNNN.html` (links often `btn_hover_ads`) inside `<li class="col-6 col-md-3 cnt-list_ads">`. Key load-more: `a.btn_line_blue.show_more` text "Ver más anuncios" (javascript:void(0)). Subagent extracted 24 from /s/hombre-busca-mujer/.
- **FB**: As before (skeletons rejected; og:description is the reliable carrier on good renders).
- **Practical**: In list crawlers, wait for `.bst_pagination` or `.posting_listing` (Locanto) / `li.cnt-list_ads` or `.show_more` (Doplim) + ad count. For "Ver más", click + re-extract in browser context. Use /20701/N/ construction + BS4 re for `/ID_` / `id-`. Gate on h1/ID_ presence + len after polls. Subagent 019f3a8a... proved the full two-step + central archive.

**Previous Live HTML Analysis Findings (2026-07)**:
- **Locanto Hombre-busca-mujer**:
  - Ad detail: reliable `/ID_\d+/` (full: `/city/ID_123456/SLUG.html`)
  - Pagination: `/Hombre-busca-mujer/20701/N/` numeric construction (lists often 403 on plain fetch → use Selenium headed + explicit next page construction).
  - "Siguiente anuncio" is per-ad floating nav, not list pagination.
- **Doplim (hombre busca / Contactos)**:
  - Ad detail: `-id-\d+\.html` or `/id-\d+` (e.g. `...-id-1517088.html`)
  - Key interactable "Ver más anuncios" button: `<a class="btn_line_blue show_more" href="javascript:void(0)">Ver más anuncios</a>`
    - Often JS-driven → in Playwright/Selenium: after load, `page.click('a.show_more, text="Ver más anuncios"')` or evaluate, wait, re-extract more IDs from same page.
  - Traditional ?page= less common; "ver más" for volume.
- **General**: Use BS4 on `a[href]` for ID patterns. Prefer containers `article`, `li`, `div[class*=result|ad|item]`. Always gate on real content first.
- **Facebook**: Lists/groups heavily JS + auth walled. Primary = web_search `site:facebook.com/groups ("brindo ayuda" OR "doy apoyo") (senoritas|universitarias)` for direct post URLs. In browser (if feasible): group page → search input → submit → click post links (permalinks/posts/). Detail URLs: `/groups/ID/posts/ID/` or permalinks. Use heavy waits + og:description for content.

**Two-Step List Crawling (MANDATORY pattern for volume from sections with pagination)**:
1. **Gather phase (paginate + identify URLs)**: 
   - Load list page with robust waits (Selenium headed poll verificando or Playwright domcontentloaded + networkidle + scrolls + selector waits for h1 or multiple ad cards /ID_ anchors).
   - Confirm real content (no inter, len sufficient, ad summaries present e.g. count of extractable IDs >=3-5).
   - Extract ad detail URLs from summaries on page using BS4 (central `extract_ad_detail_urls`): Locanto `/ID_\d+/`, Doplim `id-\d+`, FB public permalinks/posts.
   - Paginate: discover next pages (bottom selectors: .pagination, a with "next"/"siguiente"/page numbers, `/N/` paths for Locanto 20701/, `?page=N`). Use `discover_pagination_urls` or platform next_ logic. Walk several pages (3-8), collect **unique** ad URLs into set. Random delays between pages.
   - Log extracted count per page.
2. **Fetch phase (separate, after full gathering)**: For each collected detail URL:
   - fetch_playwright or fetch_selenium (with FB-specific: wait_for_selector userContent / data-ad-preview / post_message, 5+ scrolls, 5-12s waits, m.facebook variants, retries).
   - After fetch: strict gate `has_substantial_ad_content` (or equiv: !is_facebook_unloaded_skeleton, text_len >180-250, no inter/verificando, FB markers or general body).
   - Only then `archive_raw` (central data/raw/ads) + process title/body + filters + PII + dedup + append manifest.
- Why: Prevents saving/processing unloaded JS skeletons ("only html and no contents"), avoids mixing list HTML with ad HTMLs, allows exhaustive collection from N-page forum/list sections without hammering.
- FB special: Public FB "lists" rare (use search-first for direct post URLs mostly); when encountered apply same waits + gate before any archive. m.facebook fallbacks + extra 20s+ waits + scroll-to-render critical. Skip early if skeleton detected (logs FB-UNLOADED-LOG).
- Evidence of use: listcrawl scripts extract 50 IDs/page then details; collect_hombre_locanto does listings->IDs->details.

**Worked**: Strict order + re-redact + full PII check (on complete rec) + pre-dedup + raw always produced gate-passing clean manifest (287 records, PII=0).

**Discarded**: Writing snippets without full raw fetch; no male filter (seekers mixed); skip PII recheck; no pre-load dedup (dups + gate fails); legacy no-raw merges.

**Rule**: If it would fail phase 4 gate, drop now. Re-extract title/body from the archived raw .html when needed.

### Phase 4: Orchestration, Scaling, Perseverance & Agents
**Proven tools**:
- `python tools/collect_hombre_locanto.py --max-ads 400 --cities "..."` (search-first + robust fetch).
- `python tools/collect_full_hombre_ads.py`
- Custom direct/storm batches (exact pattern above, search-first compiled lists).
- `spawn_subagent` with **locked single-mind prompt** (verbatim):

> "You are a single-mind collector for ONLY real full public 'ayuda economica' / 'brindo ayuda' ads from [Locanto Hombre-busca-mujer | Doplim Contactos | public FB groups]. Use web_search for fresh direct /ID_ or post URLs first. Then robust fetch_playwright (es-PE, waits on h1/.description, scrolls, 5-10 retries, len>2500 + !cargando/!un momento/!inter/!nueva app gate). Extract title+body only if target terms + male-offering signals. Archive raw, redact, dedup by rid, append ONLY valid full records with raw_archive_ref to main manifest. Log every fetch/skip/add with reasons to SCRATCH/implementer (and real var path for bg). Never fake data or write without full non-inter HTML. Persevere with new variants/cities until clear exhaustion."

**Scaling tactics that worked**:
- Parallel bg + city splits (lima variants, multiple platforms).
- Compile 20-50+ directs per Locanto push.
- After batch: load manifest, dedup by record_id if needed, `phase_gate --phase 4`, targeted pytest, snapshot to SCRATCH.

**Perseverance**:
- Listings inter → pivot to directs immediately.
- Consecutive inter on directs → fresh web_search (new phrases/cities), longer sleeps.
- High inter on Locanto is normal (even directs). Document attempts.
- EPIPE mitigation: shorter batches (cap adds ~6-8 per run or split lists) — long playwright sessions crash.

**Hygiene**: Always real SCRATCH logs for bg. Post-batch: counts, 5+ raw samples + paths, gate output, pytest tee to `SCRATCH/implementer/pytest_*.txt` and gate_*.txt.

---

## What Worked (Ranked — These Produced the Clean Gate-Passing Records)

1. **Search-first web_search + direct /ID_ + exact title phrases + cities + male signals** — avoided list blocks; surfaced usable directs. Fresh queries every wave required.
2. **Full fetch_playwright gates** (12 UAs, es-PE, google.pe Referer, 30s h1 waits, scrolls, len>2500 + cargando/un momento/verificando/inter gate **in first 3k**, 5-10 retries + 8-25s backoff + fresh ctx/UA) — enabled real full bodies; turned inters into retries.
3. **Strict TARGETS + MALE filter** + aggressive `redact_text` + **_contains_contact_like_pii on full constructed record json** + pre-dedup (rid set loaded every batch).
4. **Always archive_raw + raw_archive_ref** in every record. Re-extract title/body from raw on any repair.
5. **List-ID-extract secondary ONLY** on clean (len>2500 !inter) listing renders — high ID yield (48+ per clean page), then full gated details.
6. **Locked subagent prompts + parallel city/site storms + bg collectors + short batches**.
7. **Rebuild manifest cleanly from good raws + post-batch dedup** after any pollution (keep unique rids, bak saved).
8. **Every step logged to real SCRATCH + search_log (exhaustive + attempts list) + exhaustion updates**. Targeted pytest + gate --phase 4 after every manifest/code change.

---

## What Didn't Work & Were Discarded (Dead Ends — Never Retry)

| Strategy | Why Failed (Evidence from 100+ runs) | Replacement / Rule |
|----------|-------------------------------------|--------------------|
| Start with listing/tag pages (Hombre-busca-mujer/20701 etc.) | 90%+ "Un momento", CF, cargando, short len. Junk → gate explosions. | Search-first directs only. Use listings solely for ID extract after clean gate pass. |
| Short/no waits, requests.get, no selector waits | Captured loading screens. | Mandatory 30s selector + scrolls + extra hombre waits + networkidle fallback. |
| No len/keyword anti-load gate | "cargando"/"un momento"/verifying saved as ads. | Gate before any parse/return. |
| Single UA / no fresh ctx / short delays | Rapid blocks, 0 yield. | 12 UAs, random 7-15s between, 8-25s backoff, fresh ctx per retry. |
| Sole DDG / internal search | Often 0 or blocked. | Always supplement external web_search. |
| Write without full raw fetch + body | Pollution (search snippets). Gate fails. | Full fetch + archive + substantial body only. |
| Weak/no male filter | Seeker + female ads mixed. | Require both TARGET + MALE signals. |
| Skip PII re-redact / disable gate | Later phase4/blackbox failures. | PII checks always active. Re-check after redact. |
| Low max / no parallel / single city | Tiny output. | 300-500 target, city splits, 3+ bg/subagents, 30+ directs for Locanto. |
| No raw_archive_ref or missing fields | Violates contract + verif. | Always archive + full schema. |
| No pre/post dedup in parallel | Duplicate rids, JSON issues, gate fails. | Load existing set every batch; dedup rebuild after. |
| Legacy dedicated (0-raw) merge | Polluted manifest; excluded in clean rebuilds. | Only append main from good raws. |
| Over-long playwright batches | EPIPE crashes (observed in persevere_big). | Cap per-run (6-8 adds or split lists); shorter launches. |
| No logging of skips/reasons | Lost learnings; can't prove exhaustion. | Every FETCH/skip/ADD = SCRATCH line. |
| Claim volume without proof (full non-inter HTML + raw + gate) | "Harvested N" vs real adds. | Require gate-pass + logs + verif before claims. |
| Partial PII check (title/body dict only) in collectors | PII leaked into metadata/seed_text; caught only by full-record gate. | ALWAYS _contains_contact_like_pii on json.dumps(entire record) + re-extract from raw on fixes. |
| Repeated directs without fresh web_search each wave | 95%+ dup skips. Old seeds exhausted quickly. | Mine exact title phrases from valid ads; new web_search (ID_ + phrases + cities + MALE) before every batch. Compile 30-60+ fresh. |
| List extract / bulk from inter or short listings | Garbage IDs or 0; pollutes. | Extract IDs **only** from listings that passed len>2500 + !inter gate first. |

These were retried across agents/storms and consistently gave 0 good or broke gates. Skip immediately.

---

## Agent Decision Tree (Quick Reference)

- Search only lists/0? → New query: "ID_" + exact `"Brindo-..."` phrases + cities + "señoritas". Log.
- Direct fetch: inter/short/cargando? → 5-10x retry (UA+delay+fresh). Still fail? Exhaust seed. Move on. (Locanto high inter rate normal.)
- Listing clean (len>2500 !inter)? → Extract /ID_ only → detail each with full gates.
- Terms present but no clear male-offering? → Discard.
- After redact still PII? → Drop.
- Dup on rid? → Skip (pre-check); rebuild dedup if needed.
- 15-20+ directs give mostly inter/dup + diminishing returns after 50+ attempts/20+ searches? → Honest exhaustion doc. Stop or pivot.
- Ready to claim? → `phase_gate --phase 4`, targeted pytest (test_scrape_ads.py test_redact_pii.py test_phase_gates_blackbox.py test_scrape_interstitial.py), full verif steps 1-8 (plan.md), save 5+ raws + logs + counts.json + gate/pytest output to real SCRATCH. Update plan/exhaustion/search_log/this guide (new learnings only).

---

## Recommended Commands & Exact Patterns

- Discovery: multiple `web_search` → seeds_*.json + search_log.
- High-volume: `python tools/collect_hombre_locanto.py --max-ads 500 ...`
- Ad-hoc (per guide): compile directs list → python one-off with fetch_playwright + gate + TARGETS+MALE + redact + _contains + archive + dedup pre-load + append (see persevere_big / locanto_known_focused patterns in SCRATCH).
- Subagent: spawn with locked prompt above (site-specific).
- Repair/clean: `python tools/phase_gate.py --phase 4`; dedup rebuild; `python tools/scrub_manifest.py` if needed.
- Verify: pytest -q ... ; gate ; snapshots to SCRATCH.

---

## Logging, Proof & Honest Exhaustion Protocol

- **Every** search/fetch/skip/add → dedicated timestamped line in SCRATCH/implementer/ log + (for bg) real /var/.../implementer/ log.
- Post-batch: manifest counts/platform split, 5 raw sample paths + snippets, gate output, pytest tee → SCRATCH/implementer/.
- Update: `reports/phase4_search_log.json`, `reports/phase4_exhaustion.md` (terse), `goal/plan.md` (deviations terse), AGENT_STATE.
- **Exhaustion criteria** (honest): 50+ attempts, 20+ distinct searches, 10+ city sweeps, 30-50+ fresh directs compiled, high inter rate (listings 90%+, directs frequently gate-skip), many dups, no-new streak → document "public indexed full male-offering ads limited under constraints". Record exact counts + all proof. Never claim 1000 without raws/bodies/gate.
- Copy this guide + latest artifacts to SCRATCH on updates.
- Re-run gate + pytest + verif steps 1-8 after **any** change.

---

## Additional Recent Learnings (2026-07-05, from list_fresh / persevere_*/fresh_* bg batches + dedup_rebuilds + full PII gate enforcement per guide)

- Short guide batches (search-first directs + full UA/es-PE/Referer/waits/scrolls + len>2500 + anti-cargando/un momento/verificando/inter gate in first3k + TARGETS+MALE + pre-dedup + full redact + _contains on COMPLETE record): 90%+ "dup skip", "inter gate skip", "filter/no male", "short". Net adds near 0 on repeated seeds. Doplim incremental on brand-new "id-" seeds from web_search; Locanto very low after first waves.
- **List extract secondary ONLY on clean listings**: Arequipa (and Trujillo) clean Hombre-busca-mujer listing (len>2500 !inter) yielded 48-50 /ID_ candidates. Full gated detail fetches added incremental clean records. NEVER list-extract from inter or short pages. Always gate the listing first.
- Repeated directs from prior seeds without fresh web_search = guaranteed dead-end (dups). **Every volume push requires new web_search** using exact phrases mined from good titles + city + "ID_" / "id-" + male terms. Compile 30-60+ new candidates per wave.
- Short batches (cap ~5-8 adds or split) required: long playwright runs trigger EPIPE. Always sleep 7-15s between, 8-25s backoff on retry.
- **Full record PII gate is mandatory**: Inline collectors using only partial check on title/body dict leaked PII into metadata/seed_text. phase4 gate (_contains on json.dumps(full record)) + rebuild from raw caught + dropped. Rule: re-extract title/body ONLY from raw on fixes; _contains on final constructed dict; sanitize metadata to safe keys. Prefer tools or replicate exact.
- Dedup: Multiple append paths (list + direct + bg) produced dups. Fix: pre-load existing rids every batch; post-run rebuild keeping unique (saved .bak); gate re-run. Always append-only to main after rid check.
- "nueva app" banner: OK (not inter) if substantial body + gates pass. Do not over-filter.
- Legacy dedicated (84 0-raw) + any no-raw: permanently excluded from main AC counts.
- Exhaustion reality: despite 100+ attempts / 50+ searches / 30+ directs per wave / storms / subagents / list-on-clean, adds slow or 0 net. Public indexed full male-offering ads scarce + high block rate on Locanto. Persevere ONLY with fresh discovery + clean-list-extract per this guide or document honest exhaustion with proof (search_log exhaustive + attempts list + gate + raws + logs). Never retry dead-ends.

---

## Agent Execution Checklist (No Shortcuts — Follow Sequentially)

1. Prep: Read full guide + plan.md + phase4_exhaustion.md. Load current rids. Create dedicated SCRATCH log (real path for bg). web_search seeds.
2. Discovery (Phase 1): web_search site: + ID_ + TARGET + city + MALE. Compile 20-50+ directs. Save seeds + search_log.
3. Fetch (Phase 2): For each:
   - sleep 7-15s
   - html = fetch_playwright(..., 70s, 6-10 retries)  # full UA/es-PE/referer/30s-wait/scroll/gate
   - if not html or len<2200 or inter or cargando/un momento/verificando in low[:2500]: log skip; continue
   - (exact gate in scrape_ads.py)
4. Extract+Filter+Redact+Archive+Dedup (Phase 3): BS4 selectors. Require TARGETS and MALE. redact. _contains? drop. sha256 pre-check. archive_raw(collector, url, html). Build exact record.
5. Write: Append ONLY main manifest. Log "ADDED".
6. Post: dedup if needed, `phase_gate --phase 4`, targeted pytest (tee output), snapshot counts/samples/logs to SCRATCH/implementer/.
7. Scale/Persevere (Phase 4): Low yield → new searches (exact phrases from good titles), city variants. List extract only on clean. Launch bg + subagents (locked prompt). Min 30 directs for Locanto. Document.
8. Verify & stop/claim: Full verif 1-8. gate. pytest. Honest exhaustion if <<1000 after effort. Terse updates to plan/exhaustion/search_log. Update **this guide only** for new proven learnings. Never weaken gates.

**Locked subagent prompt (copy verbatim)**: "You are a single-mind collector for ONLY real full public 'ayuda economica' / 'brindo ayuda' ads from [Locanto Hombre-busca-mujer | Doplim Contactos | public FB groups]. Use web_search for fresh direct /ID_ or post URLs first. Then robust fetch_playwright (es-PE, waits on h1/.description, scrolls, 5-10 retries, len>2500 + !cargando/!un momento/!inter/!nueva app gate). Extract title+body only if target terms + male-offering signals. Archive raw, redact, dedup by rid, append ONLY valid full records with raw_archive_ref to main manifest. Log every fetch/skip/add with reasons to SCRATCH/implementer (and real var path for bg). Never fake data or write without full non-inter HTML. Persevere with new variants/cities until clear exhaustion."

---

## Post-Guide Batch Evidence Snapshot (2026-07-05)

- Guided bg batches + list_fresh (search-first + full fetch_playwright UA/es-PE/headers/30s-wait/scrolls/len+anti-inter gate + TARGETS+MALE + pre-dedup + full-record _contains + archive + append main): 
  - Logs: heavy "dup skip", "inter gate skip", "filter", "short", "no target+male". Net adds low (0 in some persevere runs; +1-3 per fresh wave on Doplim; list extract on clean added incremental after gated details).
  - List extract: clean Arequipa Hombre listing (post gate) → 48+/ID_ ; similar for other cities. Only on verified clean renders.
- Current: 287 total (Locanto 145; Doplim 108; FB ~30; other 4), 521 raws, PII=0 (_contains on full record json), all referenced raws present + files verified, gate --phase 4 PASSED (post dedup rebuild from good raws only). Targeted pytest passed.
- Proofs saved to REAL_SCRATCH/implementer/ (persevere_*.log, list_fresh*.log, *_doplim_*.log, gate_phase4_*.txt, pytest_final_*.txt, state_*.json, final_rebuild_*.json, bak manifests) + SCRATCH/implementer/.
- Exhaustion holds: despite 100+ attempts / 50+ searches / multiple bg storms + subagents + 30+ directs per wave + list extracts, volume far below 1000/site. Public indexed male-offering full ads are scarce + heavily blocked. Continue only with fresh discovery per guide; document honestly when no-new streak after high effort.

Copy of this guide + artifacts saved to SCRATCH/implementer/ on update.

## Iteration Retrospection (Phase 4 Perseverance + Selenium Headed + Checklists + Subagents)
**What worked:**
- archive_raw centralization confirmed in practice: all runs (even with temp --raw-dir in verif) produce "data/raw/ads/..." refs in manifests, files land in canonical folder. Matches mandatory requirement.
- fetch_selenium updated to headed default (ChromeDriverManager, no --headless, es-PE UA, explicit polling loop for "verificando tu navegador" / verificando messages until ad selectors/content or timeout; falls back gracefully). Matches spec/reference code.
- Per-phase + overall checklists designed with testable conditions (searches, directs, rates, gates, central raws, retros, subagents) added to this guide + AGENT_STATE; used to track.
- Single-mind subagents launched (3 focused: Locanto Hombre, Doplim, FB public) with locked prompts + platform specific; they are using tools, reading code, persevering.
- Launches executed with --keep-temp to SCRATCH, exact [runner] elapsed/added/throughput line captured in runner_stdout.log files, fan-out, accounting correct, central refs verified in merged.
- pytest 31 passed (incl scrape_interstitial), phase_gate --phase 4 PASS, CI updated for phase 4 gate.
- Subagents + search first + variants + rate logging support >=10/min when supply allows (observed in prior, documented limit here).

**What failed / pending / issues:**
- Live net/sandbox limits yield (low adds in runs despite code; subagents running but may hit same blocks/inter/dups). Honest: public supply scarce on Locanto/FB; Doplim better on fresh.
- FB still mostly no_target or short even with variants/extract (JS render + verification common); perseverance helps terms via seed but body limited.
- Subagents still running at capture; need poll for counts later.
- No 1000 yet (353 baseline + small adds); continue with more waves.
- Headed Selenium may be slow/visible for large; use for debug, playwright for volume.

**Improvements for next iteration/phase:**
- Poll subagents, compile new seeds from their logs, run more fresh web_search + city sweeps + directs for Locanto/Doplim (target 200+ directs/wave).
- Add more BS4 direct parsing if needed for speed.
- Use headed Selenium in one verif launch for the polling test.
- Document more attempts in search_log/exhaustion if no new after 50+.
- Run full verif steps: pytest + launches (incl selenium) + gate + evidence to SCRATCH; mark checklist items; write retros.
- If exhaustion, stop with proof (attempts, logs, gate).
- For full project phases: since 0-3 done, continue phase 4 to 1000/exhaust per site, then phase 5 model if volume, phase 6.
- Persevere: new exact phrases from any added ads, m. fallbacks, list on clean only, parallel shards.

Next phase/iteration plan: 1. Poll subagents for results/seeds. 2. Fresh discovery waves (web_search + compile 30+ directs per platform). 3. Focused collector runs (playwright + selenium headed option) with small batches to avoid EPIPE. 4. Gate + tests after adds. 5. Update state/guide with counts, retros, checklist progress. 6. If <1000 after high effort, document exhaustion honestly. Carry out with tools, subagents, logs to SCRATCH. Test checklist conditions.

## Throughput & FB Perseverance Update (2026-07-06)
- Expanded FB queries in query_bank: more group-focused, exact phrases ("brindo ayuda economica", "doy apoyo a señoritas", city sweeps), permalink/post patterns, no reliance on "ID_".
- Seed/harvest loaders now normalize FB URLs (www <-> m, strip fbclid/ref tracking) and accept broader public post patterns (/permalink/, /story.php) for more candidates.
- FB fetch perseverance: m.facebook.com + www fallbacks; FB-specific extract (og:title, .userContent etc). For JS-heavy FB posts (common unloaded HTML skeletons with no body content), fetch_playwright/selenium now use extra waits on .userContent/[data-ad-preview]/story_body, scrolls, networkidle, and detect/retry on "unloaded" (short len or loading indicators) to avoid gathering empty pages. Prefer playwright for FB. Longer backoff.
- Retries/backoff elevated for FB platform seeds (+3).
- Parallelization: run_phase4_parallel / run_query_harvest_parallel / collect_seed_inventory now default workers=12-16, shards=4-6, http-only parallel mode, reduced delays (0.1s), higher max-fetch/retries=2, state snapshots always passed.
- Rate logging: every collector/runner end now emits elapsed_s + added + "X.YY ads/min" (or "rate limited by supply/blocks/interstitials").
- http-parallel is default when workers>1; delay moved out of submit loops.
- These increase fan-out and resilience on public FB groups + websites without relaxing any gates (interstitial, male-offering, PII on full record, raw_archive_ref, dedup, TARGET+MALE).
- Note: 10 ads/min target may still be limited by public supply/blocks (documented); code now supports the throughput when supply exists.

**Future agents**: Follow this document exactly. All dead-ends already catalogued and discarded: listings-first (90%+ inter), repeated directs w/o fresh search, partial PII checks (only on t/b), no pre-dedup, legacy 0-raw merges, long batches (EPIPE), weak waits/no gate, no raw archive. The ONLY strategies that produced clean gate-passing records (287): search-first web_search (site: + /ID_ + exact phrases + cities + male signals) + robust fetch_playwright (12 UAs, es-PE, google.pe Referer, 30s selector, scrolls, len>2500 + cargando/un momento/verificando/inter gate first3k + retries/backoff/fresh) + strict TARGETS+MALE + BS4 extract + aggressive redact + full _contains on complete record + always archive_raw + sha pre-load dedup + append main only + list-ID-extract **only** after clean listing gate pass. Persevere with fresh discovery or document exhaustion with full proof (search_log exhaustive + attempts[] + gate + raws + logs). Never retry discarded approaches.

## Per-Phase Task Checklists & Success Conditions (for Phase 4 focus + overall project)

**Overall Project Success Checklist (testable conditions for completion):**
- [ ] All 6 phases executed in sequence with retrospections written after each.
- [ ] Phase 4: >=1000 strict-valid ads (or documented exhaustion with 50+ attempts, 20+ searches, centralized raws in data/raw/ads) per major platform (Locanto Hombre-busca-mujer, Doplim, FB public).
- [ ] Manifest passes phase_gate --phase 4 (PII=0, dedup, raw coherence, required fields).
- [ ] Throughput >=10 ads/min logged in at least one parallel run (or explicitly "limited by supply/blocks").
- [ ] Selenium headed (no --headless, ChromeDriverManager or equivalent, polling for verificando messages until real content) + Playwright + BS4 used and tested.
- [ ] Single-mind subagents used for focused platform harvesting; all raw HTMLs centralized in data/raw/ads with relative refs in manifest.
- [ ] Full relevant pytest + blackbox + integration tests + CI pass; per-phase checklists completed with evidence in SCRATCH.
- [ ] Updated strategy guide + AGENT_STATE with new tactics, checklists, retros.

**Phase 4 Specific Checklist (Ad Collection - current focus, follow in order, mark when conditions met):**
- [ ] Read current AGENT_STATE, strategy guide, prior SCRATCH, code for Locanto/Doplim/FB.
- [ ] Design/expand this checklist + overall success conditions; add to guide and state (testable: searches, directs, rates, gates, retros).
- [ ] Centralize archive_raw unconditionally to data/raw/ads (relative refs always); confirm in all collectors.
- [ ] Implement/update fetch_playwright + fetch_selenium (headed default, ChromeDriverManager, no --headless, es-PE headers, explicit polling/wait until verificando/verifying messages resolve and ad selectors/content appear).
- [ ] Enhance FB: m. variants, expanded queries/selectors, +retries; integrate in seed loaders and runners.
- [ ] Raise parallel defaults (workers 12-16, shards 4-6+), rate logging (elapsed + added + ads/min or limit note), state snapshots.
- [ ] Wire single-mind subagent prompts (locked) for Locanto Hombre, Doplim, FB public groups; use spawn_subagent for focused runs.
- [ ] Add/update tests: unit for extract/fetch/verif logic, integration for runners, blackbox for gates; update CI if needed.
- [ ] Execute >=2 real parallel/seed launches (mixed + platform-specific, playwright/selenium options, --keep-temp to SCRATCH subdirs); capture rate logs, manifests, raws (confirm under data/raw/ads).
- [ ] Run full pytest (targeted + full relevant) + phase_gate --phase 4; write retrospection; update guide/state with status, new ads or exhaustion docs.
- [ ] Success conditions met: clean fan-out observed, correct accounting, >=10/min or documented limit, FB/Locanto seeds exercised, central raws + good refs, gate pass, evidence in SCRATCH, checklist marked.

After every sub-phase/iteration: introspect, write retrospection in AGENT_STATE.md and guide (what worked, failed, pending, improvements), run tests/gate, update checklist. Persevere with fresh queries, variants, subagents until 1000/site or honest exhaustion (50+ attempts documented).

**2026-07-07 Filtering & Pagination Update (from analysis + iterative subagent trials)**:
- Locanto Lima /20701/: Main cards = `article.posting_listing` (~49-51 per page; all /ID_ inside main, zero side leakage). 10+ yes. Pagination: p1 shows ~1-19, but p20/p50 still full ~50 cards → **50+ pages total** (dynamic; not exhaustive in prior limited runs).
- Doplim: Broad /s/hombre-busca-mujer/ mixes unrelated (cars, tools, classes, rentals - navigated samples confirmed). Use filtered ?q=ayuda+economica + strict main li + card keyword filter (positive "ayuda/brindo", skip "alquila/herramienta"). Yield low → prefer search-first.
- Extraction: Now ONLY main containers (refined extract_ad_detail_urls); tested on live HTML.
- Validation: Fetched/navigated 5+ main-card links; good ones match male-offering + ayuda terms (e.g. "Brindo ayuda economica a mujeres 18-27", "VARON BUSCA... APOYO ECONOMICO"). Bad filtered early.
- Total pages: Locanto Lima 50+; Doplim uses load-more + limited numeric. Walk with caps or until yield drops.
- Approach: Iterative small agents (trial selectors, filtered URLs, count main cards 10+, navigate/test links) before long crawls. Matches user request.

**2026-07-07 Main Card + Full Pagination + Validation (user feedback)**:
- Locanto Lima Hombre section: ~50+ pages (p50 has ~50 main article.posting_listing cards with /ID_; p1 UI only links ~19 but higher exist). Walk /N/ until <5 main IDs.
- Main ad card section: article.posting_listing for Locanto (~50/page); for Doplim main li.col-6 under results. Extract ONLY from there + card text filter (require "ayuda|brindo|apoyo", exclude "alquila|herramienta|curso|peugeot|auto|maleta").
- Filtered lists: use ?query=ayuda+economica inside /20701/ for Locanto; ?q=ayuda+economica for Doplim (broad /s/hombre-busca-mujer/ is polluted with unrelated).
- Validation: after extract from main, navigate (fetch) sample URLs and check title/body for male-offering + ayuda terms (not cars, not "busco hombre", not minors).
- Total pages: Locanto Lima at least 50 (tested); not all in previous limited runs.
- Iterative quick agents: use small trials on 1-2 pages (selectors, main container count, filtered yield, spot-check 3-5 links by fetch) before long crawls. Subagents did this (e.g. refined containers + filters, validated good links like "brindo ayuda a mujeres 18-27").
- Doplim note: lists often mixed; strict filter or search-first.
- This prevents unrelated; main card has the 10+ relevant.
