# Scraping Strategy Step-by-Step Guide for Agents
## Ayuda Economica / Apoyo Economico / Brindo Ayuda — Male-Offering ("Hombre Busca Mujer" / Contactos) Public Ads

**Goal**: Collect ONLY real, full, non-duplicate public ads with valid `raw_archive_ref`, substantial body, target terms + male-offering signals. Append **only** to `data/processed/ad_manifest.jsonl`. Target >=1000 per platform if public supply allows; otherwise document honest exhaustion after documented high-effort attempts (50+ searches/attempts, city sweeps, 30-50+ fresh directs, multiple parallel techniques).

**Current Verified Baseline (2026-07-05)**: 255 strict-valid unique records (all with raw refs; raws present verified). 
- Locanto Peru (hombre busca mujer real): 132 (126 male-offering perspective tagged)
- Doplim Peru (hombre busca mujer or Contactos): 89
- Facebook Public (indexed / search-first / groups): ~30
- Other indexed public: 4
- 456+ raw `.html` archives in `data/raw/ads/`
- Gate `phase_gate.py --phase 4`: **PASSED** (PII=0 via _contains, no dups, no inters, raw coherence, required fields)
- All collection via search-first + full gates + strict filters per this guide.

This is after 100+ fetch attempts, 50+ searches, storms, subagents, parallel bg, strict rebuilds from good raws, dedup, PII fixes. Public indexed supply is limited + high block rate. Guide is the single source of truth distilled from all runs. **Future agents MUST read and follow this exactly before any action.**

---

## Core Principles (Non-Negotiable)

1. Public indexed pages only. No login, no private groups, no CAPTCHA bypass.
2. **Search-first** for direct links (`/ID_...`, `id-XXXX`, group posts). Never start broad listing/tag pages.
3. Only full ads: TARGET terms + explicit male-offering perspective. Substantial clean body.
4. Always `archive_raw` → `raw_archive_ref`. Aggressive `redact_text`. Full PII gate. Dedup by `sha256(url)` record_id (pre-load existing set in every loop).
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

**Recent observation (persevere batches)**: Even directs frequently hit inter gate (many "inter gate skip" / "dup skip"). Need massive seed lists (20-50+). "nueva app" banner is usually OK if real body present — do **not** over-reject on it.

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
   - Pre-load `existing = set()` from manifest before loop. Skip if present.
6. `rp = archive_raw(RAWDIR, collector_tag, url, html)`
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
       "collector": "persevere_big_guide | locanto_known_focused | ...",
       "male_offering_perspective": true,
       "section": "Hombre-busca-mujer or Contactos",
       "full_public_ad": true
     }
   }
   ```
8. Append **only** to main `ad_manifest.jsonl`. Log "ADDED N raw=..."

**List extract (secondary only)**: After clean listing fetch (len>2500 && !inter), extract /ID_ then detail-fetch each with full gates.

**Worked**: Strict order + re-redact + full PII check + pre-dedup + raw always produced gate-passing clean manifest (227 records, PII=0).

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

## What Worked (Ranked — These Produced the 227 Clean Records)

1. **Search-first web_search + direct /ID_ + exact title phrases + cities** — avoided list blocks; surfaced usable directs.
2. **Full fetch_playwright gates** (12 UAs, es-PE, google.pe Referer, 30s h1 waits, scrolls, len>2500 + cargando/un momento/verificando/inter gate, 5-10 retries + 8-25s backoff + fresh ctx) — enabled real full bodies.
3. **Strict TARGETS + MALE filter** + aggressive `redact_text` + `_contains...` PII gate + pre-dedup.
4. **Always archive_raw + raw_archive_ref** in every record.
5. **Locked subagent prompts + parallel city/site storms + bg collectors**.
6. **Rebuild manifest cleanly from good raws + post-batch dedup** after any pollution.
7. **Every step logged to real SCRATCH + search_log + exhaustion updates**. Tests + gate after every edit.
8. Secondary list-ID-extract **only** on clean (len>2500 !inter) renders.

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

## Additional Recent Learnings (2026-07-05, from fresh_doplim_push / more_doplim / mixed_push / fb_fresh / extra_fresh bg batches per guide)

- Latest short bg batches (search-first directs + full UA/waits/len+anti-inter gate + TARGETS+MALE + pre-dedup + redact + PII gate): 80-95%+ dups or "inter"/"short"/"no filter" skips. Net +1 to +3 ADDED per batch (Doplim and occasional FB when varied phrases/cities used).
- Locanto directs: extremely high "dup skip" + "inter gate skip" even on /ID_ from recent web_search. Rarely yields new after initial seeds.
- Doplim: more reliable for adds when using fresh id- seeds from web_search (e.g. more_doplim added 1; fresh pushes mostly dups on repeats).
- FB indexed group posts: many "no filter" (not male-offering or no target terms), low conversion; 1 add in recent fresh batch.
- Mixed + list extract: added 0 net in latest (all dups after clean gate passes); list-extract only on rare fully clean listing renders remains low-yield secondary.
- Confirms: Must compile 30-50+ **fresh** seeds per push via repeated web_search (exact title phrases + city variants + "ID_" / "id-"); pre-load dedup critical; shorter batches essential (EPIPE risk + diminishing).
- All records continue to meet: raw_archive_ref present, male+target, PII=0 post-redact, gate pass.
- Legacy dedicated (84 lines, 0 raws) remains excluded.
- "nueva app" banners OK if body substantial and gates pass (as implemented in fetch_playwright).
- Exhaustion status unchanged: public indexed supply very limited; high effort (many attempts) yields slow incremental adds only. Persevere per this guide or document.

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

- Guided bg batches (fresh_doplim_push, more_doplim, mixed_push, extra_fresh_doplim, fb_fresh_batch using exact recipe): 
  - Logs show: mostly "dup skip", "inter", "short", "no filter", "no target+male".
  - Net adds: 1 (more_doplim Lima), 1 (fb_fresh), 0- few from others. Doplim/FB occasionally succeed with fresh seeds.
- Current: 255 total (Locanto 132 platform / 126 male H; Doplim 89; FB ~30), 456+ raws, PII=0 (_contains), all referenced raws present, gate --phase 4 PASSED.
- Proofs saved to REAL_SCRATCH/implementer/ (reassess_state_*.log, state_reassess_*.json, *_doplim_*.log, fb_fresh_*.log, mixed_*.log, pytest_*, gate_*.txt) + SCRATCH/implementer/.
- Exhaustion holds: despite 100+ attempts / 50+ searches / multiple bg storms + subagents + 30+ directs per wave, volume far below 1000/site. Public indexed male-offering full ads are scarce + heavily blocked. Continue only with fresh discovery per guide; document honestly when no-new streak after high effort.

Copy of this guide + artifacts saved to SCRATCH/implementer/ on update.

**Future agents**: Follow this document exactly. All dead-ends (listings-first, weak gates, no search-first, no dedup, no PII, legacy no-raw, long batches) already catalogued and discarded. Search-first + full Playwright gates (12 UA, es-PE, 30s waits, len+keyword+inter gate, retries/backoff) + TARGETS+MALE + redact + _contains + raw archive + pre-dedup + append main ONLY = the sole path that produced the clean 254. Persevere with fresh seeds or document exhaustion with proof. Never retry discarded approaches.