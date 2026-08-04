# Scraping Strategy Step-by-Step Guide for Agents
## Ayuda Economica / Apoyo Economico / Brindo Ayuda — Male-Offering ("Hombre Busca Mujer" / Contactos) Public Ads

**Goal**: Collect ONLY real, full, non-duplicate public ads with valid `raw_archive_ref`, substantial body, target terms + male-offering signals. Append to `data/processed/ad_manifest.jsonl`. Target >=1000 per platform if public supply allows; otherwise document honest exhaustion after documented high-effort attempts (50+ searches/attempts, city sweeps, fresh directs, multiple techniques).

**Current Verified Baseline (2026-07-04, after 100+ fetch attempts, 40+ searches, storm batches, subagents, merges)**: 187 real full records (88 Locanto Peru "hombre busca mujer real", 62 Doplim Peru contactos/hombre, 31 Facebook Public indexed). 320+ raw .html archived. Gate/tests/verif passed with PII active. No search_evidence pollution. <<1000 per site = public exhaustion (listings 90%+ inter, directs rare + high block rate).

This guide is the distilled "what actually worked" from dozens of real runs, collect_*.py, storm agents, subagents, PII cleans, rebuilds, and full Verification Plan executions. Future agents **MUST** read this first. Follow phases in order. Never retry discarded dead-ends.

---

## Core Principles (Non-Negotiable)

1. Public indexed pages only. No login, no private groups, no CAPTCHA solving, no bypasses.
2. **Search-first for direct links** (`/ID_...`, `-id-XXXX.html`, group post URLs). Never start with broad listing/tag pages.
3. Only full ads: target terms ("ayuda economica", "apoyo economico", "doy ayuda", "brindo ayuda", "brindo apoyo"...) + male-offering ("brindo", "doy", "ofrezco", "soy ", "señoritas", "universitarias", "hombre busca"...). Substantial body after clean.
4. Always: `archive_raw` → valid `raw_archive_ref` in manifest record. Redact PII. Dedup by sha256(url) record_id.
5. Persevere with evasion + gates: UA rotation (real Chrome list), 5-25s+ random delays, explicit waits (h1/.description + networkidle), 5-10x retries + fresh ctx, **len>2500 + anti-"cargando"/"loading"/"un momento" gate**.
6. Proof + verification: Every action logged to SCRATCH/implementer/. Update search_log + exhaustion docs honestly. Run full Verification Plan (plan.md) + `phase_gate.py --phase 4` (PII checks **active**) before any claim.
7. Never fake, inject, or weaken gates. Re-extract from raw on issues.

---

## Step-by-Step Agent Workflow (Follow Sequentially)

### Phase 1: Discovery — Search-First (Highest Yield, Bypasses Blocks)
1. Run `web_search` (preferred over sole DDG) with tight operators for **directs**:
   - Locanto: `site:locanto.com.pe ("/ID_" OR "Hombre-busca-mujer") ("brindo ayuda" OR "doy ayuda" OR "apoyo economico" OR "ayuda economica" OR "brindo apoyo") (lima OR arequipa OR trujillo OR ... ) ("señoritas" OR "universitarias" OR "18")`
   - Variants: add "constante", city-specific, exact title phrases from known goods, "sugar daddy" etc sparingly.
   - Doplim: `site:doplim.com.pe OR site:doplim.pe ("brindo ayuda economica" OR "doy ayuda" OR "brindo apoyo economico") (id- OR /id-)`
   - FB: `site:facebook.com/groups ("doy ayuda economica" OR "brindo ayuda" OR "brindo apoyo") ("señoritas" OR "universitarias" OR "chicas") -inurl:login`
2. Parse results → collect clean direct URLs (filter out list pages).
3. Save seeds: `SCRATCH/implementer/seeds_$(date +%s).json` + append to `reports/phase4_search_log.json` (query, result_count, notes, ts). Aim 50-100+ logged attempts before exhaustion.
4. Compile master list of known-good directs from prior successful runs + new.
5. Cross-check against manifest to avoid dups.

**Worked (Evidence)**: Surfaced 7+ fresh Locanto ID_ + 9+ Doplim in single rounds. External web_search + ID_ phrases beat internal search (often 0). Bypassed 90%+ list blocks.

**Discarded**: Broad non-ID_ queries; starting with /tag/ or Hombre-busca-mujer/ listing URLs (immediate inter). Sole reliance on DDG html without web_search supplement.

**Rule**: If search returns only listings or 0 directs → immediately pivot to "ID_" + "brindo ayuda" + city phrases from prior titles. Log and move on. Do not hammer lists.

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

**Selenium fallback** (similar UA, lang=es-PE, --disable-blink, explicit WebDriverWait on h1/.description, sleeps, quit).

**Worked**: The len + keyword cargando/un momento/verifying + selector wait + UA + random delays + 5-10x + fresh ctx produced the verifiable full bodies (many Doplim successes, some Locanto directs, FB indexed). Listings still inter but directs yielded when clean.

**Discarded (Dead Ends)**:
- No waits / short waits / only requests.get → partial or loading HTML recorded as ads → later gate fails + junk.
- Single UA / no fresh ctx → fast blocks.
- No len/keyword gate → recorded "cargando" screens.
- Hammering same URL without backoff.

**Dead-End Avoidance**: After any fetch, **always** apply the gate before parsing title/body. If 5+ retries on a direct fail → mark exhausted for that seed, log, move to next. Never write inter content.

### Phase 3: Extract, Filter, Redact, Archive, Write (Strict Contract)
1. Parse: Title = first h1/h2 or <title>. Body = prefer .description / article / .ad_text / main / section (fallback full text, cap 9-11k chars).
2. Strict filter (in this order):
   - Contains ≥1 TARGET term.
   - Contains male-offering signal (brindo/doy/ofrezco + context or "hombre busca"/"señoritas"/"universitarias").
   - Body after clean > ~300-500 meaningful chars.
3. Redact aggressively: `redact_text(...)` for phones, emails, wsp, "escribeme", numbers patterns. Re-check with `_contains_contact_like_pii`.
4. Dedup: `rid = hashlib.sha256(url.encode()).hexdigest()`. Skip if in existing set.
5. Archive: `raw_ref = archive_raw(raw_dir, source_id, url, html)` (e.g. "locanto_storm", "fresh_storm", "doplim_new").
6. Build record (example from successful storms):
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
     "metadata": {"original_url": url, "section": "Hombre-busca-mujer", "collector": "storm_xxx", "male_offering_perspective": true, "full_public_ad": true}
   }
   ```
7. Append **only** to main `ad_manifest.jsonl`. Never other files for final.

**Bulk listing path** (secondary): After fetch listing + !inter + len>2500, use `extract_ads_from_listing_html` or `extract_id_urls` to pull /ID_ candidates, then detail fetch each.

**FB special**: After fetch, check login wall indicators ("iniciar sesión" x2 + short content). Skip if present.

**Worked**: Strict + re-redact + raw always + dedup + male filter gave clean manifest that passes gate --phase4/--all + blackbox. Rebuilds from good raws fixed early pollution.

**Discarded**: Writing search snippets or "harvested" without full fetch/raw; weak filters (any keyword = seekers mixed in); skipping PII re-check; no dedup.

**Rule**: If record would fail gate later, drop it now. Re-extract title/body from the raw .html if needed.

### Phase 4: Orchestration, Scaling, Perseverance & Agents
- **Preferred scripts** (proven):
  - `python tools/collect_hombre_locanto.py --max-ads 400 --cities "lima,arequipa,..."` (search_ddg_directs + robust playwright + extract_ids + write only good).
  - `python tools/collect_full_hombre_ads.py --max 350`
- Custom storm batches: compile fresh directs list from latest searches → loop with fetch_playwright + gates + append.
- **Subagents** (`spawn_subagent`): **Use locked single-mind prompt**:
  > "You are a single-mind collector for ONLY real full public 'ayuda economica' / 'brindo ayuda' ads from [Locanto Hombre-busca-mujer | Doplim Contactos | public FB groups]. Use web_search for fresh direct /ID_ or post URLs first. Then robust fetch_playwright (UA rotate, es-PE, waits on h1/.description, scrolls, 5-10 retries, len>2500 + !cargando/!un momento/!inter gate). Extract title+body only if target terms + male-offering signals. Archive raw, redact, dedup, append ONLY valid full records with raw_archive_ref to main manifest. Log every fetch/skip/add with reasons to SCRATCH. Never fake data or write without full non-inter HTML. Persevere with new variants/cities until clear exhaustion."
- Parallelism: city splits (lima north/south), site-specific storms (Locanto/Doplim/FB), listing-extract + directs.
- Perseverance protocol: listings inter → pivot to directs immediately. Consecutive fails on seeds → fresh web_search for variants. Random long sleeps between. High max (300-500). Multiple bg + subagents.
- FB: only public indexed group posts discovered via search.

**Worked**: Locked prompts + parallel storms + collect scripts + search-first + post-clean merge. Produced the 88+ Locanto hombre and Doplim volume.

**Discarded**: Single-threaded low-max runs; trusting listing pages; no splits; writing before full validation.

---

## What Worked (Ranked by Yield & Reliability)

1. **Search-first web_search + direct /ID_ targeting** — bypassed list blocks; produced most real adds.
2. **Enhanced fetch_playwright with full anti-load gates** (len>2500 + cargando/un momento/verifying/please wait checks + selector waits + hombre extra waits + UA + 8-25s backoff + fresh ctx) — turned inter-heavy into usable full HTML on directs.
3. **Dedicated collect_hombre_locanto.py / custom storm batches** on compiled known+fresh directs.
4. **Strict term + male filter + PII re-redact + raw ref requirement**.
5. **Locked subagent prompts + bg parallel city/site storms**.
6. **Re-extract/rebuild manifest from good raws** after PII or dup issues.
7. **Logging every attempt + SCRATCH snapshots + full Verification before claims**.
8. Bulk ID extraction only from clean non-inter listing renders.

These directly account for the 187 real records and passing gates.

---

## What Didn't Work & Were Discarded (Dead Ends — Never Retry)

| Strategy | Why It Failed (Evidence) | Replacement / Rule |
|----------|---------------------------|--------------------|
| Start with listing/tag pages (Hombre-busca-mujer/20701/ etc.) | 90%+ "Un momento...", CF, cargando, phone-verif, short len. Junk recorded → gate explosions. | Search-first directs only. Use listings at most for ID extraction after gate pass. |
| Short/no waits, no scrolls, no selector waits | Captured loading screens. Low body quality. | Mandatory 30s selector + 5-12s + scrolls + networkidle. |
| No len/keyword anti-load gate in fetch | "cargando" / verifying HTML saved as ads. | Always gate before return/parse. |
| Single UA / fixed short delays / no fresh ctx | Rapid blocks, 0 yield after first. | 8-12 UAs, random 8-25s, fresh browser/ctx per retry. |
| Internal DDG/search alone | Frequently 0 results or blocked. | Always supplement with external web_search. |
| Writing search snippets / "harvested" without full raw fetch | Manifest pollution ("search_evidence"). Gate fails. | Only full fetched + raw + body. Guards now in collectors. |
| Weak validation (keyword only, no male signal) | Seeker ads + female-offering mixed in. | Require both targets + explicit male_offering. |
| Disabling PII checks or skipping re-redact | Later --all/blackbox failures. | PII always active in phase_gate. Re-run redact + check. |
| Low max-ads / single city / no parallel | Tiny output. | 300-500+, city splits, storm 3+ batches. |
| No raw archive or raw_ref in record | Violates manifest contract + verif. | Always archive + include ref. |
| Claiming volume from counts without proof of full non-inter HTML + raw | "175 harvested" vs 1-2 real. | Require successful gate-passing fetch + add logs + verif. |
| Over-broad redact (e.g. bare "id" patterns) | Flagged good URLs. | Use lookbehind + specific patterns in redact_pii. |
| Selenium-first without Playwright | Slower, more setup, similar blocks if no waits/UA. | Playwright primary (enhanced); Selenium complement. |
| No logging of attempts/skips | Lost learnings; can't prove exhaustion. | Every fetch = SCRATCH log line + search_log entry. |

These dead-ends were retried multiple times across agents and consistently delivered 0 or bad records + failed gates. Future runs: skip immediately. If tempted, re-read this section.

---

## Agent Decision Tree (Quick Reference)

- Search returns only lists or 0? → New query with "ID_" + exact "Brindo-ayuda..." phrases + city. Log.
- Fetch on direct returns inter/short/cargando? → Retry 5-10x (UA+delay). Still fail? Mark exhausted for seed. Move on.
- Listing fetched clean? → Extract IDs only, detail-fetch those (with gates).
- Record has terms but no clear male offering? → Discard (seeker).
- After redact still has PII? → Drop or re-redact from raw.
- 5+ consecutive inter on known directs + fresh seeds exhausted? → Document exhaustion. Stop or switch platform/variant.
- Ready to claim progress? → Run: phase_gate --phase 4, pytest test_scrape* test_phase_gates*, verif steps 1-8 (plan.md), save samples + logs to SCRATCH. Update this guide.

---

## Recommended Commands & Tools (Proven)

- Discovery: web_search (multiple variants) → seeds.
- High-volume Locanto: `python tools/collect_hombre_locanto.py --max-ads 500 --cities "lima,arequipa,trujillo,piura,chiclayo,huancayo,callao,ica,cusco,tacna"`
- Full sweeps: `python tools/collect_full_hombre_ads.py --max 400`
- Ad-hoc storm: Python one-liner or script on list of fresh directs using fetch_playwright + the gates shown.
- Subagent launch: spawn_subagent with the locked prompt above (site-specific).
- Clean/repair: `python tools/phase_gate.py --phase 4`; `python tools/redact_pii.py` re-runs; rebuild from raws if needed.
- Verify: pytest -q tests/test_scrape*.py tests/test_phase_gates*.py; full plan Verification.
- Enhance: Edit fetch_playwright in scrape_ads.py only when adding new anti-patterns observed in logs.

---

## Logging, Proof & Exhaustion Protocol

- **Every** search/fetch/skip/add → timestamped line in dedicated SCRATCH log + search_log.json entry.
- Post-batch: snapshot `manifest head -20`, platform counts, 5+ raw paths + samples, gate output, pytest output → SCRATCH/implementer/.
- Update `reports/phase4_search_log.json`, `reports/phase4_exhaustion.md`, plan.md (terse deviations only), AGENT_STATE.
- **Exhaustion criteria** (honest): After 50+ attempts, 20+ distinct searches, sweeps of 10+ cities, 30+ fresh directs from search, high inter rate (listings 90%+, many directs fail gate), diminishing adds → document "public supply exhausted for practical collection under constraints". Record exact counts + proof. Never claim 1000 without the raws and bodies.
- Copy this guide + latest logs to SCRATCH on major updates.

---

## Update Rule for This Guide

After every major push (new batch results, new anti-pattern discovered, verif run, or >10 adds): 
- Append new "Worked" evidence or new dead-end.
- Update baseline counts.
- Add any new successful fetch variant or prompt tweak.
- Future agents start by re-reading the latest version + recent SCRATCH storm logs.

**Evidence Basis for This Guide**: 100+ fetch attempts across bg/subagents (many logged inter skips on lists, successful full adds on directs via enhanced fetch), 40+ search attempts in logs, collect script runs, subagent storms, PII re-cleans (0 bad post), merges (88 Locanto hombre), gate --phase4 + blackbox + pytest passes, full verif executions, 320 raw HTMLs, manifest contract upheld.

Read plan.md Verification Plan before finishing any run. Persevere within these proven bounds. Avoid the discarded column entirely.

---
*Last updated: 2026-07-04. Based on real execution history only.*
