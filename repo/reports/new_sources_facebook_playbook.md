# Playbook: Facebook + newly identified sources

**Date:** 2026-07-08  
**Goal:** Grow **processed** volume beyond Doplim/Locanto caps via public surfaces named by PeruTops and discovery work.

## Priority ranking (for *this* project)

| Rank | Source | Why | How to get more |
|-----:|--------|-----|-----------------|
| 1 | **Ciudad Anuncios** (`*.ciudadanuncios.pe`) | HTTP works; related-ad graph expands to 100s of on-topic titles; PeruTops-named | `tools/collect_ciudadanuncios.py` |
| 2 | **Facebook public posts** | Live male-offer posts in city groups; PeruTops primary social surface | Search-first URLs → `tools/collect_facebook_public.py` |
| 3 | **Evisex** (`evisex.pe/encuentros/apoyo-economico`) | Dense list (400+ filtered seeds) | Focused list gather; details need PW after rate-limit cool-down |
| 4 | **Doplim** | Already dominant | CAP for TF-IDF model; only reopen for new model |
| 5 | **Locanto** | Already ≥1500 processed | CAP |
| 6 | **Twitter/X** | Named on PeruTops as “works for posting” | Public search only; thin tooling (nitter empty); optional later |
| 7 | **Blidoo** | Named but dead | Skip (`blidoo.com` empty shell; `blidoo.pe` NXDOMAIN) |
| 8 | **Evisos.com.pe broad lists** | Polluted (bandas, empleo) | Only strict focused collector / Evisex |

---

## 1. Ciudad Anuncios (best new HTTP source)

### What works

- Detail pages: **HTTP 200**, full title + body + contact block.
- **Related ads** on each detail page form a dense graph of `ayuda/apoyo económica` items across cities.
- Site search (`/search?q=…`) is **broken** (returns unrelated latest ads) — do **not** use as primary discovery.

### Collector

```bash
python3 -u tools/collect_ciudadanuncios.py --target 250 --max-visit 900
```

- Seeds: indexed URLs + BFS related links  
- Gates: TARGET + OFFER, reject seeker-only / academic junk  
- Output: `data/raw/ads/ciudadanuncios_*.html`  
- Rebuild: platform_family `ciudadanuncios`

### How to get still more

1. Re-run collector with higher `--max-visit` (queue grows while crawling).  
2. Web-search seed top-ups:  
   `site:ciudadanuncios.pe ("brindo ayuda economica" OR "doy ayuda economica")`  
   Append hits to `SCRATCH/implementer/seeds_ciudadanuncios_extra.jsonl` → `--seeds-extra`.  
3. City hosts already covered by graph (lima, cusco, juliaca, piura, …).

---

## 2. Facebook (public, search-first only)

### Constraints (hard)

- **No login**, no private groups, no CAPTCHA bypass.  
- Unauthenticated HTML often skeleton; body may be **og:description** only.  
- Throughput will never match Doplim API.

### What works

1. **Discover post URLs via web search** (not feed scroll):

```
site:facebook.com/groups ("brindo ayuda economica" OR "doy ayuda economica")
(señoritas OR universitarias) (lima OR arequipa OR trujillo OR huancayo)

site:facebook.com/groups/posts ("brindo apoyo economico" OR "doy apoyo economico") lima
```

2. Prefer **`/groups/{id}/posts/{id}/`** permalinks over bare group pages.  
3. Fetch with Playwright (`fetch_playwright` already tries www + m.facebook).  
4. Strict gates: TARGET ayuda/apoyo; **reject** pets (“DOY AYUDA ECONOMICA Y ALIMENTO”), school support, legal, dental spam.

### Collector

```bash
# 1) Maintain seeds jsonl from web_search hits
# 2) Fetch
python3 -u tools/collect_facebook_public.py \
  --target 25 --max-try 40 \
  --seeds-jsonl SCRATCH/implementer/seeds_facebook_public.jsonl
```

Query bank: `data/sources/query_bank.json` → `facebook` (expanded).

### How to get still more FB

| Tactic | Notes |
|--------|--------|
| Rotate city + phrase queries weekly | lima, callao, “zona norte”, huancayo, arequipa, chiclayo |
| Harvest only **post** URLs | Group walls need login; posts sometimes indexed |
| Save og:description | Often the only usable body for rebuild |
| Accept low yield | Expect tens, not thousands, of processed records |
| Never join groups | Out of scope |

Known public post examples (seed bank):

- Huancayo: `groups/2382711485285084/posts/4105697169653165`  
- Arequipa: `groups/2709450222624428/posts/4381946475374786`  
- Lima: `groups/2058190747802106/posts/4331004727187352`  
- Zona norte: `groups/955328711711298/posts/1968258663751626`  
- San Miguel: `groups/citas.sanmiguel.lima.lima.peru/posts/1516274410064624`

---

## 3. Evisex

- Best list: `https://www.evisex.pe/encuentros/apoyo-economico.htm` (~30 cards/page, 15+ pages).  
- After burst requests → **403 / soft block**.  
- Use `tools/collect_evisos_focused.py` **after cool-down**, single base first, slow detail PW.  
- Seeds already: `SCRATCH/implementer/seeds_evisos_focused_*.jsonl` (~418 evisex IDs).

---

## 4. Twitter / X

- PeruTops: some posters prefer Twitter for publishing.  
- Nitter probe empty; official X needs auth for useful search.  
- **Optional later:** public `x_keyword_search` for `brindo ayuda economica lima` if product tools allow; archive only public text — not primary volume path.

## 5. Blidoo

- **Skip.** Dead/empty in probes.

---

## Rebuild / learning curve notes

- `rebuild_manifest_from_raw.py` now tags **`ciudadanuncios`** and maps **evisex → evisos** family.  
- After a Ciudad Anuncios wave: incremental rebuild, then re-check platform counts.  
- Do not force FB/Evisos to 1500 if public supply exhausts (data-scale policy).

---

## Commands (quick)

```bash
# Ciudad Anuncios (primary growth)
python3 -u tools/collect_ciudadanuncios.py --target 250 --max-visit 900

# Facebook public posts
python3 -u tools/collect_facebook_public.py --target 25 \
  --seeds-jsonl SCRATCH/implementer/seeds_facebook_public.jsonl

# Evisex (when not rate-limited)
python3 -u tools/collect_evisos_focused.py --target 100 --max-pages 15

# Rebuild
python3 tools/rebuild_manifest_from_raw.py
```
