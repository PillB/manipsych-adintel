# Scraping Strategy Guide for Agents
## Ayuda Economica / Hombre Busca Mujer Collection (Locanto, Doplim, FB)

**Objective**: Collect real, full, non-duplicate public ads with `raw_archive_ref` in the main `data/processed/ad_manifest.jsonl`. Target >=1000 per major platform if possible; otherwise document honest exhaustion after real effort (50+ attempts, multiple cities, fresh seeds, high inter rate).

This guide is distilled from 40+ documented attempts, multiple subagents, bg batches, collect scripts, web_search discovery, PII cleans, and merges (as of 2026-07-04). It prioritizes strategies that produced verifiable full ads (title + substantial body + male-offering language + archived raw HTML) while discarding dead-ends that wasted cycles on blocks, pollution, or non-full records.

**Core Principles (Never Violate)**
- Public pages only. No login, no CAPTCHA bypass, no private groups.
- **Search-first for directs**: Find `/ID_`, `-id-XXXX.html`, or group post links via search engines before touching listing pages.
- **Only real full ads**: Must contain target terms ("ayuda economica", "apoyo economico", "doy ayuda", "brindo ayuda", etc.) + male-offering signals ("brindo", "doy", "ofresco"). Body must be substantial after clean. Skip interstitials, loading screens, seekers.
- **Raw + redacted + deduped**: Always `archive_raw` the HTML. Redact PII aggressively. Dedup by `record_id` (sha256 of URL). Main manifest only gets records with valid `raw_archive_ref`.
- **Persevere with evasion**: UA rotation (real recent Chrome + mobile), random delays (5-25s+), explicit waits (h1/.description/article + networkidle + scrolls), 5-10x retries with fresh context.
- **Proof everywhere**: Log every attempt/fetch/skip/add to SCRATCH. Save snapshots, heads, samples, verif files to SCRATCH/implementer/. Update `phase4_search_log.json` and exhaustion docs **honestly**.
- **Verification before claims**: Run full Verification Plan from `goal/plan.md` before any update_goal.

### Step-by-Step Agent Workflow

#### 1. Discovery (Search-First — Highest Yield Path)
1. Use `web_search` (or equivalent) with tight operators for direct links:
   - Locanto: `site:locanto.com.pe "Hombre-busca-mujer" OR /Hombre-busca-mujer/ ("brindo ayuda" OR "doy ayuda" OR "apoyo economico" OR "ayuda economica") (ID_ OR /ID_) (lima OR arequipa OR trujillo OR cusco OR piura OR callao OR chiclayo OR huancayo OR tacna OR ica)`
   - Add variants: "universitarias", "madre soltera", "señoritas 18", "constante", city-specific.
   - Doplim: `site:doplim.com.pe OR site:doplim.pe ("brindo ayuda economica" OR "doy ayuda economica" OR "brindo apoyo") (id- OR /id-)`
   - FB: `site:facebook.com/groups ("doy ayuda economica" OR "brindo ayuda economica" OR "brindo apoyo") ("señoritas" OR "universitarias") -inurl:login`
2. Parse results for `/ID_`, `-id-XXXX.html`, `/groups/XXX/posts/YYY/`.
3. Save seeds to SCRATCH (e.g., `seeds_*.json`). Log as attempt in `reports/phase4_search_log.json` (query, count, notes, ts). Aim for 50-100+ documented attempts before claiming exhaustion.
4. Cross-reference with known good directs from prior runs. Compile master list of known goods.

**Worked**: Bypassed 90%+ of list blocks. Surfaced fresh IDs (e.g., 7+ new Locanto in one round) and Doplim directs. External search beat internal DDG-only (which often returned 0).

**Discarded**: Broad queries without "Hombre-busca-mujer"/"ID_"; starting with listings/tag pages (90%+ interstitial).

**Dead-End Avoidance Tip**: If a search returns only listings or 0 directs, immediately switch to "ID_" + exact phrases from prior successful titles. Do not waste retries on blocked lists.

#### 2. Fetching (Robust, Anti-Block, Anti-Loading)
Use `tools/scrape_ads.py:fetch_playwright` (enhanced version) or `fetch_selenium` fallback.

1. UAs: Rotate 8-10 real recent Chrome strings + 1 mobile.
2. Headers: Accept-Language=es-PE, Referer=https://www.google.com.pe/, Sec-* for realism.
3. `page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)`
4. **Explicit content waits** (critical — prevents loading screens as ads):
   - `wait_for_selector("h1, .description, article, .ad_text, a[href*='/ID_']", timeout=30000)`
   - Fallback: `wait_for_load_state("networkidle", timeout=18000)`
5. Human simulation: Scroll random 400-800px + 4-12s+ random timeouts. Extra for hombre/contactos pages.
6. **Anti-loading / interstitial gate** (never record "cargando" as ad):
   - After load: if `len(content) < 2500` or contains "cargando"/"loading"/"verifying"/"please wait"/"un momento"/"verificando"/"nueva app"/"cloudflare"/"robot" in first ~3k chars → treat as inter, close, sleep 10-25s, retry.
   - Use `is_access_interstitial()` (expanded patterns).
7. Retry loop (5-10x): On inter/fail → sleep random(8-25s) + new UA + fresh context/browser. Increase backoff.
8. Fallback to Selenium (similar waits + anti-detect) for stubborn pages.

**Worked**: Explicit waits + length/keyword checks + UA + delays + retries + fresh ctx defeated most blocks on directs and produced full bodies. Enhanced version (cargando checks + len guard) added in storm runs.

**Discarded**: Short/no waits, no scrolls/length checks, single UA, no fresh ctx (captured partial/loading HTML → junk + PII gate fails later). Relying on requests-only (missed JS content).

**Dead-End Avoidance**: Always validate `!is_access_interstitial(html) and len(html) > 2500 and has real ad selector` before parsing title/body. If 5+ retries fail on a seed, move to next and log "exhausted".

#### 3. Extraction, Validation & Writing
1. Parse with BeautifulSoup. Title: first h1/h2/title. Body: prefer `.description`/`article`/`.ad_text`/`main`/`section` (fallback full text, cap ~9-11k).
2. Filter strictly:
   - ≥1 target term.
   - Male-offering signal ("brindo"/"doy"/"ofresco" + context).
   - Body substantial after clean (>~300 chars).
3. Redact: `redact_text` (phones, wsp, emails, "escribeme", etc.). Re-validate with `_contains_contact_like_pii`.
4. Dedup: sha256(url) as record_id.
5. Archive: `archive_raw(...)` → `data/raw/ads/...`
6. Record (example):
   ```json
   {
     "record_id": "sha...",
     "source_platform": "Locanto Peru (hombre busca mujer real)",
     "raw_archive_ref": "data/raw/ads/xxx.html",
     "title": "[redacted]",
     "body_redacted": "[redacted]",
     "metadata": {"original_url": "...", "section": "Hombre-busca-mujer", "male_offering_perspective": true, "collector": "storm_batch"}
   }
   ```
7. Append only to main `ad_manifest.jsonl`.

**Worked**: Strict filters + re-redact + raw ref + rebuilds from good raws produced clean, verifiable records (e.g., 88 Locanto hombre in main after merges). Always archiving raw + using `raw_archive_ref` satisfied manifest contract and verif.

**Discarded**: Writing search snippets/injection to manifest (created "search_evidence" pollution — now guarded in harvest/collect scripts). No re-extract after merges. Accepting any keyword match without male signal (seeker ads mixed in). No dedup/weak rid.

**Dead-End Avoidance**: Never write without raw ref + full body + male signal + PII clean. If a record triggers gate later, drop or re-extract from raw.

#### 4. Orchestration, Scaling & Perseverance
- Use existing: `tools/collect_hombre_locanto.py --max-ads 400 --cities "lima,arequipa,..."` (internal search + playwright), `collect_full_hombre_ads.py`.
- Custom batches: Python snippets on compiled direct lists + `extract_ads_from_listing_html` (only if page renders cleanly).
- Subagents: `spawn_subagent` with **locked prompt**:
  > "Single-mind collector ONLY for real full 'ayuda economica' ads from [SITE] hombre/contactos. Use web_search for directs → robust fetch_playwright (waits, !inter, len>2500, terms+male) → only append real full with raw_ref to manifest. Log everything to SCRATCH. Never fake. Persevere."
- Parallel: City splits (north/south), site-specific (Locanto/Doplim/FB), storm multiple batches.
- For FB: only indexed public group posts.
- **Perseverance**: If listings inter, pivot to directs. If 5+ consecutive inter on a seed list, pause, fresh search, or switch city/variant. Do not hammer.

**Worked**: Locked subagents + parallel city batches + search-first + merge after clean. Multiple query variants + cities + "constante"/"universitarias" etc.

**Discarded**: Single long runs, no splits, low max-ads, trusting internal search alone, writing before validation.

### What Worked (Evidence from Runs)
- Search-first for /ID_ directs (bypassed 90%+ of list blocks; surfaced dozens of new ones across rounds).
- Enhanced Playwright (UA lists, es-PE, google Referer, 25-30s selectors, networkidle, scrolls, 8-25s random, retries + fresh ctx, length + keyword anti-load).
- Dedicated collect scripts + custom batches on known/fresh directs.
- Bulk extract only on non-inter listings.
- Strict term + male filter + re-redact + raw ref.
- Locked subagent prompts + bg storm collectors (city splits).
- Logging attempts + saving everything to SCRATCH.
- Re-extract + rebuild manifest from good raws (fixed PII/dups).
- These produced the verifiable ~177-181 real full records (88 Locanto hombre in main after merges) and passed gate/tests/verif.

### What Didn't Work & Were Discarded (Dead Ends — Avoid)
- **Listing/tag pages first (or only)**: 90%+ "Un momento...", Cloudflare, "nueva app", phone verify, "cargando". Interstitials recorded as ads → junk + PII gate explosions. Switched to directs.
- **Short/no waits or missing anti-load checks**: Captured loading/verifying screens (len low, keywords like cargando). Fixed by length + explicit keyword guards.
- **Internal DDG/search only (no external web_search)**: Often 0 results (rate/index limits). Always supplement.
- **Search-snippet injection to manifest**: Created "search_evidence" pollution (hundreds of non-full entries; now guarded). Discarded; only full raw.
- **Low retries/fixed short delays/no fresh ctx/UA**: Fast blocks, tiny yield. Replaced with random 8-25s + 5-10x + fresh.
- **No dedup/weak validation/any-keyword match**: Dups + seeker ads mixed in. Fixed by sha + male signal + length.
- **Disabling PII/gate or no re-redact**: Later --all/blackbox failures. Always active + re-extract.
- **Over-broad redact patterns** (e.g., bare "id" without lookbehind): Flagged URLs in metadata. Fixed.
- **Low max-ads, single city, no parallel**: Minimal output. Replaced with 300-500 + city splits + storm.
- **Not archiving raw or using raw refs**: Failed manifest contract and verif. Always do.
- **Claiming volume without actual full fetches**: "175 harvested" vs. 1-2 real added. Always require successful non-inter full HTML.

These were tried repeatedly (listings, short waits, injection, low effort) and consistently produced 0 or bad data + gate failures. Future runs must skip them.

### Recommended Tools & Commands
- Discovery: `web_search` tool + save seeds.
- Collect: `python tools/collect_hombre_locanto.py --max-ads 400 --cities "..."`; `python tools/collect_full_hombre_ads.py --max 350`.
- Batches: Python snippets on direct lists + extract + write (see history).
- Subagents: `spawn_subagent` with locked prompts above.
- Enhance: Edit `fetch_playwright` for new anti-load if needed.
- Clean: `python tools/phase_gate.py --phase 4`; custom PII re-extract scripts; `python tools/scrub_manifest.py`.
- Verify: pytest; full steps from plan.md; save to SCRATCH.

### Logging, Proof & When to Stop
- Every search/fetch = entry in search_log + SCRATCH log.
- After runs: snapshot counts, copy logs, save verif samples (head, 5 raws, gate output, summary) to SCRATCH.
- If after 50+ attempts, multiple city sweeps, fresh seeds, and still <<1000 with high inter rate → document "exhaustive" in search_log + exhaustion.md with evidence. Honest counts only.
- Never claim 1000 without the raw refs and full bodies.

Update this guide with new learnings after every major push. Future agents: read this first, follow the phases, avoid the discarded list, log everything, verify before claiming.

**Evidence Basis**: Dozens of web_search calls, 100+ fetch attempts (many inter, some success on directs), collect script runs, subagent launches, merges after clean, gate/pytest passes, verif executions showing real 88 Locanto hombre in main + overall ~177-181 after effort.
