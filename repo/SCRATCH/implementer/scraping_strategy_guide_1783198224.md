# Scraping Strategy Step-by-Step Guide for Agents
## Ayuda Economica / Apoyo Economico / Brindo Ayuda — Male-Offering ("Hombre Busca Mujer" / Contactos) Public Ads

**Goal**: Collect ONLY real, full, non-duplicate public ads with valid `raw_archive_ref`, substantial body, target terms + male-offering signals. Append to `data/processed/ad_manifest.jsonl`. Target >=1000 per platform if public supply allows; otherwise document honest exhaustion after documented high-effort attempts (50+ searches/attempts, city sweeps, fresh directs, multiple techniques).

**Current Verified Baseline (2026-07-04, after 100+ fetch attempts, 50+ searches, multiple storm batches, subagents, parallel bg collectors, merges + strict dedup/PII cleans)**: ~199 clean real full records with raw refs (96 Locanto Peru "hombre busca mujer real", 69 Doplim Peru contactos/hombre, ~34 Facebook Public indexed + other). ~377 raw .html archived. Gate --phase 4 passed (PII active, deduped). No search_evidence pollution. <<1000 per site = public exhaustion (listings 90%+ inter, directs rare + high block/interstitial rate even after UA/waits/gates; diminishing returns after large seed lists).

This guide is the distilled "what actually worked" from dozens of real runs, collect_*.py, storm agents, subagents, PII cleans/rebuilds, dedup fixes, and full Verification Plan executions. Future agents **MUST** read this first. Follow phases in order. Never retry discarded dead-ends.

---

## Core Principles (Non-Negotiable)

1. Public indexed pages only. No login, no private groups, no CAPTCHA solving, no bypasses.
2. **Search-first for direct links** (`/ID_...`, `-id-XXXX.html`, group post URLs). Never start with broad listing/tag pages.
3. Only full ads: target terms ("ayuda economica", "apoyo economico", "doy ayuda", "brindo ayuda", "brindo apoyo"...) + male-offering ("brindo", "doy", "ofrezco", "soy ", "señoritas", "universitarias", "hombre busca"...). Substantial body after clean.
4. Always: `archive_raw` → valid `raw_archive_ref` in manifest record. Redact PII. Dedup by sha256(url) record_id (pre-check + post-batch hygiene).
5. Persevere with public-content validation gates: localized browser settings, 5-25s+ random delays, explicit waits (h1/.description + networkidle), 5-10x retries + fresh contexts, **len>2500 + anti-"cargando"/"loading"/"un momento"/"nueva app disponible" gate**.
6. Proof + verification: Every action logged to SCRATCH/implementer/ (and real /var/.../implementer for bg). Update search_log + exhaustion docs honestly. Run full Verification Plan (plan.md) + `phase_gate.py --phase 4` (PII checks **active**) before any claim.
7. Never fake, inject, or weaken gates. Re-extract from raw on issues. Always dedup before append in parallel runs.

---

## Step-by-Step Agent Workflow (Follow Sequentially)

### Phase 1: Discovery — Search-First (Highest Yield)
1. Run `web_search` (preferred) + DDG with tight operators for **directs**:
   - Locanto: `site:locanto.com.pe ("/ID_" OR "Hombre-busca-mujer") ("brindo ayuda" OR "doy ayuda" OR "apoyo economico" OR "ayuda economica" OR "brindo apoyo") (lima OR arequipa OR trujillo OR piura OR chiclayo OR cusco OR callao OR huancayo) ("señoritas" OR "universitarias" OR "18" OR "madres solteras")`
   - Variants: add "constante", city-specific, exact title phrases from known goods ("Brindo-apoyo-economico-para-senoritas"), "sugar daddy" sparingly.
   - Doplim: `site:doplim.com.pe OR site:doplim.pe ("brindo ayuda economica" OR "doy ayuda" OR "brindo apoyo economico") (id- OR /id-)`
   - FB: `site:facebook.com/groups ("doy ayuda economica" OR "brindo ayuda" OR "brindo apoyo") ("señoritas" OR "universitarias" OR "chicas") -inurl:login`
2. Parse results → collect clean direct URLs (filter out list pages).
3. Save seeds: `SCRATCH/implementer/seeds_$(date +%s).json` + append to `reports/phase4_search_log.json` (query, result_count, notes, ts). Aim 50-100+ logged attempts before exhaustion.
4. Compile master list of known-good directs from prior successful runs + new.
5. Cross-check against manifest to avoid dups.

**Worked (Evidence)**: Surfaced 7-20+ fresh Locanto ID_ + multiple Doplim in rounds. External web_search + ID_ phrases + city variants beat internal search (often 0) and avoided low-yield list pages. Doplim directs gave clean ADDEDs in batches.

**Discarded**: Broad non-ID_ queries; starting with /tag/ or Hombre-busca-mujer/ listing URLs (immediate inter). Sole reliance on DDG html without web_search supplement.

**Rule**: If search returns only listings or 0 directs → immediately pivot to "ID_" + "Brindo-ayuda..." + exact phrases + more cities from history. Log and move on. Do not hammer lists.

### Phase 2: Robust Fetching (The Core That Produced Real Full Ads)
Use **enhanced `tools/scrape_ads.py:fetch_playwright`** (or robust variant in collect_*.py). Selenium as fallback.

**Proven Parameters (copy these patterns exactly)**:
- 8-12 real recent Chrome UAs (Mac/Win/Linux + 1 mobile). Rotate per attempt.
- Headers: Accept-Language=es-PE, Referer=https://www.google.com.pe/, realistic Sec-*.
- `page.goto(url, wait_until="domcontentloaded", timeout=50-80s)`
- **Explicit waits (critical)**: `wait_for_selector("h1, .description, article, .ad_text, .user_content, a[href*='/ID_'], [data-id]", timeout=30000)`
  - Fallback: networkidle 18s or hard 12s timeout.
- Human sim: random 5-12s wait, 2x scrolls (400-800px), extra 4-8s for /Hombre-busca or query= pages.
- **Mandatory anti-interstitial / anti-loading gate** (after content load, before accept):
  ```python
  content = page.content()
  low = content.lower()
  if (len(content) < 2500 or
      "cargando" in low[:3000] or "loading" in low[:2000] or "verifying" in low[:2000] or
      "un momento" in low[:2000] or "verificando" in low[:2000] or
      "cloudflare" in low[:3000] or "nueva app" in low[:1000] or
      is_access_interstitial(content)):
      # close browser, sleep 10-25s, continue retry
  ```
- Retry loop: 5-10 attempts. On fail/inter: `time.sleep(random.uniform(8,25))` + new UA + fresh browser/context. Increase backoff.
- Return only if passed all gates + substantial content.

**Selenium fallback** (lang=es-PE, explicit WebDriverWait on h1/.description, sleeps, quit).

**Worked**: The len + keyword cargando/un momento/verifying/nueva app + selector wait + UA + random delays + 5-10x + fresh ctx produced the verifiable full bodies (Doplim successes in direct batches, Locanto adds from known+fresh directs + list-extract on rare clean renders). Storm logs show len=100k+ good fetches passing gate.

**Discarded (Dead Ends)**:
- No waits / short waits / only requests.get → partial or loading HTML recorded as ads → later gate fails + junk.
- Single UA / no fresh ctx → fast blocks.
- No len/keyword gate → recorded "cargando" screens.
- Hammering same URL without backoff.

**Dead-End Avoidance**: After any fetch, **always** apply the gate before parsing title/body. If 5+ retries on a direct fail → mark exhausted for that seed, log, move to next. Never write inter content. Recent runs: even directs on Locanto frequently inter → need 30+ seeds + variants.

### Phase 3: Extract, Filter, Redact, Archive, Write (Strict Contract)
1. Parse: Title = first h1/h2 or <title>. Body = prefer .description / article / .ad_text / main / section (fallback full text, cap 9-11k chars).
2. Strict filter (in this order):
   - Contains ≥1 TARGET term.
   - Contains male-offering signal (brindo/doy/ofrezco + context or "hombre busca"/"señoritas"/"universitarias").
   - Body after clean > ~300-500 meaningful chars.
3. Redact aggressively: `redact_text(...)` for phones, emails, wsp, "escribeme", numbers patterns. Re-check with `_contains_contact_like_pii`.
4. Dedup: `rid = hashlib.sha256(url.encode()).hexdigest()`. Skip if in existing set (load before loop).
5. Archive: `raw_ref = archive_raw(raw_dir, source_id, url, html)` (e.g. "locanto_directs_guide", "doplim_new_directs", "list_id_extract").
6. Build record (example from successful storms/direct batches):
   ```json
   {
     "record_id": rid,
     "source_platform": "Locanto Peru (hombre busca mujer real)" | "Doplim Peru (hombre busca mujer or Contactos)" | "Facebook Public (indexed)",
     "source_url_hash": rid,
     "collected_at": "...",
     "title": redacted_title,
     "body_redacted": redacted_body,
     "raw_archive_ref": "data/raw/ads/xxx.html",
     "male_offering": true,
     "metadata": {"original_url": url, "section": "Hombre-busca-mujer", "collector": "storm_xxx | directs_push | list_extract", "male_offering_perspective": true, "full_public_ad": true}
   }
   ```
7. Append **only** to main `ad_manifest.jsonl`. Never other files for final. In parallel: load existing set each batch.

**Bulk listing path** (secondary): After fetch listing + !inter + len>2500, use extract ID URLs then detail fetch each (with gates).

**FB special**: After fetch, check login wall indicators ("iniciar sesión" x2 + short content). Skip if present.

**Worked**: Strict + re-redact + raw always + dedup + male filter gave clean manifest that passes gate --phase4/--all + blackbox. Doplim direct pushes added successfully. Rebuilds from good raws + post dedup fixed early pollution.

**Discarded**: Writing search snippets or "harvested" without full fetch/raw; weak filters (any keyword = seekers mixed in); skipping PII re-check; no dedup (caused recent gate fails).

**Rule**: If record would fail gate later, drop it now. Re-extract title/body from the raw .html if needed. Always pre-load existing rids in collector scripts.

### Phase 4: Orchestration, Scaling, Perseverance & Agents
- **Preferred scripts** (proven):
  - `python tools/collect_hombre_locanto.py --max-ads 400 --cities "lima,arequipa,..."` (search_ddg_directs + robust playwright + extract_ids + write only good).
  - `python tools/collect_full_hombre_ads.py --max 350`
- Custom storm batches: compile fresh directs list from latest searches → loop with fetch_playwright + gates + append (see locanto_directs_*.py patterns).
- **Subagents** (`spawn_subagent`): **Use locked single-mind prompt** (verbatim):
  > "You are a single-mind collector for ONLY real full public 'ayuda economica' / 'brindo ayuda' ads from [Locanto Hombre-busca-mujer | Doplim Contactos | public FB groups]. Use web_search for fresh direct /ID_ or post URLs first. Then robust fetch_playwright (es-PE, waits on h1/.description, scrolls, 5-10 retries, len>2500 + !cargando/!un momento/!inter/!nueva app gate). Extract title+body only if target terms + male-offering signals. Archive raw, redact, dedup by rid, append ONLY valid full records with raw_archive_ref to main manifest. Log every fetch/skip/add with reasons to SCRATCH/implementer (and real var path for bg). Never fake data or write without full non-inter HTML. Persevere with new variants/cities until clear exhaustion."
- Parallelism: city splits (lima north/south), site-specific storms (Locanto/Doplim/FB), listing-extract + directs. Multiple bg + subagents.
- Perseverance protocol: listings inter → pivot to directs immediately. Consecutive fails on seeds → fresh web_search for variants/phrases. Random long sleeps between. High max (300-500). Recent: Locanto needs 15-30+ directs per batch due to inter rate; Doplim more forgiving.
- FB: only public indexed group posts discovered via search.
- Hygiene: after batch, dedup manifest if needed (sha on record_id), re-run gate.

**Worked**: Locked prompts + parallel storms + collect scripts + search-first + post-clean merge + dedup. Produced the 96+ Locanto hombre and Doplim volume. Directs push + list ID extract on clean pages added real records. Gate passes after fixes.

**Discarded**: Single-threaded low-max runs; trusting listing pages; no splits; writing before full validation + dedup; no real SCRATCH logging.

---

## What Worked (Ranked by Yield & Reliability)

1. **Search-first web_search + direct /ID_ targeting** (with city + exact phrases) — avoided low-yield list pages; produced most real adds (Doplim batches + Locanto directs).
2. **Enhanced fetch_playwright with full anti-load gates** (len>2500 + cargando/un momento/verifying/nueva app + selector waits + hombre extra waits + UA + 8-25s backoff + fresh ctx) — turned inter-heavy into usable full HTML on directs (storm logs confirm good len + filters pass).
3. **Dedicated collect_hombre_locanto.py / custom storm batches / list ID extract** on compiled known+fresh directs (per guide).
4. **Strict term + male filter + PII re-redact + raw ref requirement + pre/post dedup**.
5. **Locked subagent prompts + bg parallel city/site storms**.
6. **Re-extract/rebuild manifest from good raws + dedup script** after PII or dup issues.
7. **Logging every attempt + SCRATCH snapshots + full Verification before claims**. Real /var/.../implementer for bg runs.
8. Bulk ID extraction only from clean non-inter listing renders.

These directly account for the ~199 real records and passing gates.

---

## What Didn't Work & Were Discarded (Dead Ends — Never Retry)

| Strategy | Why It Failed (Evidence) | Replacement / Rule |
|----------|---------------------------|--------------------|
| Start with listing/tag pages (Hombre-busca-mujer/20701/ etc.) | 90%+ "Un momento...", CF, cargando, phone-verif, short len. Junk recorded → gate explosions. | Search-first directs only. Use listings at most for ID extraction after gate pass. |
| Short/no waits, no scrolls, no selector waits | Captured loading screens. Low body quality. | Mandatory 30s selector + 5-12s + scrolls + networkidle. |
| No len/keyword anti-load gate in fetch | "cargando" / verifying / "nueva app" HTML saved as ads. | Always gate before return/parse. |
| Single UA / fixed short delays / no fresh ctx | Rapid blocks, 0 yield after first. | 8-12 UAs, random 8-25s, fresh browser/ctx per retry. |
| Internal DDG/search alone | Frequently 0 results or blocked. | Always supplement with external web_search. |
| Writing search snippets / "harvested" without full raw fetch | Manifest pollution ("search_evidence"). Gate fails. | Only full fetched + raw + body. Guards now in collectors. |
| Weak validation (keyword only, no male signal) | Seeker ads + female-offering mixed in. | Require both targets + explicit male_offering. |
| Disabling PII checks or skipping re-redact | Later --all/blackbox failures. | PII always active in phase_gate. Re-run redact + check. |
| Low max-ads / single city / no parallel | Tiny output. | 300-500+, city splits, storm 3+ batches. |
| No raw archive or raw_ref in record | Violates manifest contract + verif. | Always archive + include ref. |
| Claiming volume from counts without proof of full non-inter HTML + raw | "175 harvested" vs 1-2 real. | Require successful gate-passing fetch + add logs + verif. |
| No pre/post dedup in parallel appends | Duplicate record_id gate errors (recent runs). | Load existing set in every collector; run dedup rebuild after batches. |
| Over-broad redact (e.g. bare "id" patterns) | Flagged good URLs. | Use lookbehind + specific patterns in redact_pii. |
| Selenium-first without Playwright | Slower, more setup, similar blocks if no waits/UA. | Playwright primary (enhanced); Selenium complement. |
| No logging of attempts/skips | Lost learnings; can't prove exhaustion. | Every fetch = SCRATCH log line + search_log entry. Use real SCRATCH for bg. |

These dead-ends were retried multiple times across agents and consistently delivered 0 or bad records + failed gates. Future runs: skip immediately. If tempted, re-read this section.

---

## Agent Decision Tree (Quick Reference)

- Search returns only lists or 0? → New query with "ID_" + exact "Brindo-ayuda..." phrases + city + "señoritas". Log.
- Fetch on direct returns inter/short/cargando/"nueva app"? → Retry 5-10x (UA+delay+fresh). Still fail? Mark exhausted for seed. Move on. (Locanto high inter rate observed.)
- Listing fetched clean + len>2500? → Extract IDs only, detail-fetch those (with gates).
- Record has terms but no clear male offering? → Discard (seeker).
- After redact still has PII? → Drop or re-redact from raw.
- Dup detected on append/gate? → Rebuild dedup by record_id from current manifest.
- 5+ consecutive inter on known directs + fresh seeds exhausted (30+ targeted)? → Document exhaustion. Stop or switch platform/variant.
- Ready to claim progress? → Run: phase_gate --phase 4, pytest test_scrape* test_phase_gates*, verif steps 1-8 (plan.md), save samples + logs + counts json to SCRATCH/implementer/. Update this guide + exhaustion.

---

## Recommended Commands & Tools (Proven)

- Discovery: web_search (multiple variants + cities) → seeds.json.
- High-volume Locanto: `python tools/collect_hombre_locanto.py --max-ads 500 --cities "lima,arequipa,trujillo,piura,chiclayo,huancayo,callao,ica,cusco,tacna"`
- Full sweeps: `python tools/collect_full_hombre_ads.py --max 400`
- Ad-hoc storm/directs: Python scripts on list of fresh directs using fetch_playwright + the gates shown (see locanto_*_push, storm_* in SCRATCH history).
- Subagent launch: spawn_subagent with the locked prompt above (site-specific).
- Clean/repair: `python tools/phase_gate.py --phase 4`; re-runs of redact; dedup rebuild script; `python tools/scrub_manifest.py` if needed.
- Verify: pytest -q tests/test_scrape*.py tests/test_phase_gates*.py; full plan Verification.
- Enhance: Edit fetch_playwright in scrape_ads.py only when adding new anti-patterns observed in logs (e.g. "nueva app").

---

## Logging, Proof & Exhaustion Protocol

- **Every** search/fetch/skip/add → timestamped line in dedicated SCRATCH log + search_log.json entry. Bg collectors must write to real /var/folders/.../implementer too.
- Post-batch: snapshot `manifest head -20`, platform counts, 5+ raw sample paths + samples, gate output, pytest output → SCRATCH/implementer/.
- Update `reports/phase4_search_log.json`, `reports/phase4_exhaustion.md`, plan.md (terse deviations only), AGENT_STATE.
- **Exhaustion criteria** (honest): After 50+ attempts, 20+ distinct searches, sweeps of 10+ cities, 30+ fresh directs from search, high inter rate (listings 90%+, directs often gate-fail), diminishing adds (many dups) → document "public supply exhausted for practical collection under constraints". Record exact counts + proof. Never claim 1000 without the raws and bodies.
- Copy this guide + latest logs/audit json to SCRATCH/implementer/ on major updates.
- Always re-run gate + targeted pytest + verif steps 1-8 after changes.

---

## Additional Recent Learnings (2026-07-04)

- Locanto: direct /ID_ success rate low (many inter gate skips even with full recipe) but when clean + terms+male pass → good full bodies + raw added. Need very large compiled seed lists + title phrase variants.
- Doplim: higher success on direct fetches from search seeds (multiple ADDED in one batch run).
- Parallel bg/subagents increase volume but introduce dups → enforce existing set load + post dedup.
- All final records have valid raw_archive_ref and pass strict PII gate. Legacy dedicated without raws excluded.
- Persevere: storms + subagents + new web_search seeds continue until clear no-new streak.

Copy of this guide and proof artifacts saved to SCRATCH/implementer/ with each update.
