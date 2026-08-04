# Evisos quality audit + PeruTops / source research

**Date:** 2026-07-08  
**Trigger:** Many archived `evisos*.html` were off-target (band members, jobs, pets, classes).

## What’s wrong with current Evisos raws

Audit of ~68 `evisos_pw_*.html` titles showed **mostly junk**:

| Example title | Category noise |
|---------------|----------------|
| Se busca gente para formar grupo coverss de paramore | Band / music |
| Buesco gente seria para formar banda | Band |
| Se busca cantante de punk rock / Busco vocalista / baterista | Band |
| Asistente administrativo / Operador de retroescavadora | Jobs |
| Hermosa cachorrita shih tzu / Cachorro cavalier | Pets |
| Drywall / Aluzinc / Radio midland walkie talkie | Products |
| Masajes terapeuticos / Clases de matematicas | Services |

Only a **handful** matched `ayuda/apoyo económica` male-offer language. Rebuild correctly kept almost none (processed Evisos ≈ 2).

### Root cause in collectors

`tools/collect_evisos_pw_details.py`:

1. **ID neighborhood expansion** (`base_id ± 20`) around known ads → random neighboring IDs (bands, jobs).
2. **Loose `POS` gate** (`encuentro|sexo|busco mujer|…`) accepted almost any personal/contact page.
3. **Broad list bases** (`encuentros.htm`) on evisos.com.pe are **SEO tag soup**, not a clean category feed — card titles mix industrial, pets, employment.

## PeruTops (and similar forums)

Public PeruTops threads (meta discussion, **not** ad hosts):

- [Ayuda economica a mujeres](https://perutops.com/foro-relax/threads/ayuda-economica-a-mujeres.471378/)
- [Grupos de Ayuda Economica](https://perutops.com/foro-relax/threads/grupos-de-ayuda-economica.509551/)

### Platforms named by users for **publishing** these ads

| Surface | Role | Collector implication |
|---------|------|------------------------|
| **Doplim** | Explicitly named (“blidoo, doplim, ciudad anuncios”) | Already gold path — keep |
| **Facebook groups** | Search “ayuda económica”; alt FB profiles | Existing public search-first FB collector only |
| **Twitter / X** | “la que más me funciona” for some posters | Optional public search later; not implemented |
| **Blidoo** | Named | `blidoo.com/pe` probe returned empty shell (~114 bytes) — dead/thin |
| **Ciudad Anuncios** | Named | Generic marketplace home; no dense target list found in probe |
| **PeruTops itself** | Discussion / kines reviews | **Do not scrape as ad source**; login/community forum |
| **Locanto** | Not the main name in that thread but proven elsewhere | Already capped ~1500 processed |

Forums are useful for **where to look**, not for bulk ad HTML.

## Where to find ads on Evisos-family sites

### Prefer: **Evisex** (`evisex.pe`) encuentros paths

HTTP probes (200, ~30 cards/page, on-topic titles):

| Base | Notes |
|------|--------|
| `https://www.evisex.pe/encuentros/apoyo-economico.htm` | **Best** — 646+ ads claimed; focused collector got **425 unique** card-filtered seeds in 15 pages |
| `.../ayuda-economica-a-mujeres-de-lima.htm` | On-topic titles in probe (rate-limit 403 after burst) |
| `.../sexo-a-cambio-de-ayuda-economica.htm` | On-topic |
| `.../mujer-busca-hombre/mujer-busca-ayuda-economica.htm` | Mix seeker + offer |
| `.../ayuda-economica-a-cambio-de-intimidad.htm` | On-topic |

Example list titles: “Se brinda apoyo economico a mujeres…”, “Doy ayuda economica senoras mayores”, “Doy un rico sexo a mujeres a cambio de apoyo…”.

### Secondary: **Evisos.com.pe** tight slugs only

| Base | Reality |
|------|---------|
| `por-ayuda-economica.htm` / `apoyo-economico.htm` | HTTP 200 but **noisy**; after **card TARGET filter** only ~11 relevant titles/page |
| `brindo-ayuda.htm` | Mostly masajes/clases unless prefiltered |
| `encuentros.htm` | Heavily polluted — **do not use as primary seed** |
| `search.php?keyword=…` | **403** |

Indexed good details still exist, e.g.:

- `lima-city.evisos.com.pe/apoyo-economico-id-780526`
- `cusco-city.evisos.com.pe/ayuda-economica-para-chicas-en-apuros-cusco-id-657602`

## New collector

```bash
python3 tools/collect_evisos_focused.py --target 150 --max-pages 15
```

- No ID expansion  
- Card + detail gates aligned with rebuild `TARGET_RE` / `OFFER_RE` / seeker reject  
- Junk regex: banda, baterista, vocalista, empleo, mascotas, aluzinc, etc.  
- Tags: `evisex_pw_*` / `evisos_pw_*`

Stop old `collect_evisos_pw_details.py` when running this (it pollutes raw).

## Practical recommendation

1. **Do not chase 1500 Evisos** via broad lists — public clean supply is thin after filters.  
2. Use **Evisex apoyo-economico** pagination as the Evisos-family volume path.  
3. Keep **Doplim + Locanto** as primary model data (already past ROI elbow).  
4. FB/Twitter: public-only, opportunistic (PeruTops points there; private groups out of scope).  
5. Optionally quarantine or ignore existing junk `evisos_pw_*` raws (rebuild already rejects most).

## Commands

```bash
# Stop polluted collector
# kill <pid of collect_evisos_pw_details>

# Focused gather + PW details
python3 -u tools/collect_evisos_focused.py --target 200 --max-pages 25

# Rebuild yield check
python3 tools/rebuild_manifest_from_raw.py
```
