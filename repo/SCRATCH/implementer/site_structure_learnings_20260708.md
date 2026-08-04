# Site structure learnings — Doplim + Evisos Peru (2026-07-08)

## Throughput problem (v1 browser collector)

- Serial Playwright: city × section × show_more clicks (~3s each) → **25+ min gather, 0 saves**.
- Phase A fully completed before Phase B → no streaming.
- Full browser per detail URL → ~few ads/min when it eventually ran.

## Doplim structure (learned)

### Listing / section URLs
- Correct: `https://www.doplim.com.pe/s/{section}/{city}/`
- Sections: `hombre-busca-mujer`, `relaciones-ocasionales`, `mujer-busca-hombre`, `contactos`
- Bare `/s/hombre-busca-mujer/` without city returns **unrelated** product cards (tools, cars).
- Adult modal `#modalWarning` blocks clicks until "Soy mayor de 18" / force-hide + cookie.

### Main ad cards
- Selector: `li.cnt-list_ads` (expect **~30 per page / API chunk**)
- Detail pattern: `*-id-{N}.html` on city subdomains (`lima.doplim.com.pe/...`)

### Pagination (critical)
- UI: `a.show_more` with `data-page`, text "Ver más anuncios"
- JS posts to **`POST /api/getAdsSearch`** with:
  ```
  page, cityid=0, areaid=0, catid, subcatid, query={city}, gal=0, price_min, price_max, sort_by
  ```
- Max **page 10** then control removed (`if (page == 10) $('.show_more').remove()`)
- Learned cat/subcat:
  | section | catid | subcatid |
  |---------|-|-------|----------|
  | hombre-busca-mujer | 5 | 51 |
  | relaciones-ocasionales | 5 | 54 |
  | mujer-busca-hombre | 5 | 50 |
  | contactos | 5 | 0 |
- Filter string form: `{catid}-{subcatid}-{cityid}-{areaid}` e.g. `5-51-0-0`

### HTTP viability
- List warm-up + `adult_content=1` cookie → API returns full card HTML fragments.
- Detail HTTP GET: **~96% success**, substantial HTML, no CF interstitial in tests.
- Benchmark: **300 list IDs / 3.4s** (Lima HBM 10 pages); **detail ~277 ads/min** (10 workers).

## Evisos structure (learned)

### Listing
- Keyword/section bases: `por-ayuda-economica.htm`, `apoyo-economico.htm`, `encuentros.htm`, `hombre-busca-mujer.htm`, `contactos-ocasionales-peru.htm`
- Main cards: `h2.title a` inside `.info` / `.col-md-7` (+ `.category-zone`, `.desc`)
- Pagination: `{stem}/clasificados/{N}` (page 1 is base `.htm`)
- ~25–30 title links/page when healthy; keyword search is **noisy** (jobs, products).

### Relevance
- Require personal/economic signals on detail; reject product/job junk (`NEG` patterns).
- True "Encuentros / Hombre busca Mujer" volume is thinner than Doplim HBM.

### HTTP viability
- List + detail plain HTTP 200 in current runtime (no browser required for happy path).

## Collector evolution

| version | approach | gather rate | detail rate | notes |
|---------|----------|-------------|-------------|-------|
| v1 browser | Playwright show_more + later detail | ~tens/min | blocked until gather done | too slow |
| v2 fast HTTP | `/api/getAdsSearch` + parallel HTTP detail | **thousands/min IDs** | **~200+/min** | current |

## Tooling
- `tools/collect_doplim_evisos_sections.py` — browser two-phase (kept for Selenium/headed debugging)
- `tools/collect_doplim_evisos_fast.py` — high-throughput HTTP API collector (preferred)

## Next iterative improvements
1. Stream fetch as soon as candidate buffer ≥ N (don't wait full national gather).
2. Early-stop API gather when unique IDs ≥ 2× remaining target.
3. Evisos: prefer category-zone containing Encuentros/Hombre busca; expand city hosts.
4. Optional Selenium headed only when HTTP returns inter/short.
5. Persist learned cat/subcat JSON for offline runs.
