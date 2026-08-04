# Raw review pass — process & modeling alignment

**Date:** 2026-07-08  
**Scope:** Audit `data/raw/ads`, tighten rebuild gates, process → modeling manifests, update docs/scripts.

## Raw inventory (prefix samples)

| Prefix / source | Approx raw N | Rebuild accept (sample) | Notes |
|-----------------|-------------:|-------------------------|-------|
| `doplim*` (incl ayuda) | ~6,000+ | ~89% of recent ayuda sample | Primary volume |
| `ciudadanuncios_*` | 1,200+ (growing) | **~95%** (285/300 recent) | Best new HTTP source |
| `locanto*` / city seeds | ~670 details + city files | ~36% of recent locanto_fast | Many non-target HBM |
| `facebook*` / `fb_*` | ~75 | ~50% facebook_public | Skeletons / no_target |
| `evisos*` | ~69 | **~7%** | Historic pollution (jobs/bands); OFFTOPIC gate |

**Do not use raw counts as training N.**

## Issues found & fixes

| Issue | Fix |
|-------|-----|
| Evisos/job/charity ads with incidental “apoyo económico” entered processed | `OFFTOPIC_RE` in `rebuild_manifest_from_raw.py` |
| Full-page `text_from_html` polluted gates via sidebars | Platform body extractors for **ciudadanuncios** + **evisos** |
| Learning curve ignored Ciudad Anuncios | `platform_bucket` includes `ciudadanuncios` |
| No offer-preferring train set | `tools/build_modeling_dataset.py` → `modeling_manifest.jsonl` |
| Docs only covered Doplim/Locanto/Evisos/FB lists | `docs/MODELING.md`, AGENTS + COLLECTION scoreboard updated |

## Processing commands (canonical)

```bash
# 1) Strict rebuild (all raw HTML)
python3 tools/rebuild_manifest_from_raw.py

# 2) Modeling subset (prefer male-offer language)
python3 tools/build_modeling_dataset.py

# 3) Train
python3 tools/train_manipulation_model.py \
  --manifest data/processed/modeling_manifest.jsonl

# 4) Data-scale curve (optional)
python3 tools/learning_curve_data_scale.py \
  --manifest data/processed/modeling_manifest.jsonl \
  --base-target 1500
```

## Full rebuild results (10,293 raws, ~19 min threaded)

| Platform | Processed |
|----------|----------:|
| doplim | 2,845 |
| locanto | 1,562 |
| **ciudadanuncios** | **1,303** |
| facebook | 26 |
| evisos | 2 |
| **total** | **5,738** |

Rejects: `no_target_terms` 1782, `seeker_only` 357, `duplicate_record_id` 2360, `offtopic_context` 3, …

### Modeling subset + train

| Artifact | Value |
|----------|------:|
| `modeling_manifest.jsonl` | **5,717** (offer-preferring; −21 no_target) |
| TF-IDF OvR macro-F1 | **0.810** |
| micro-F1 | **0.941** |
| Global curve late gain/100 | **0.0024** → **stay** near 1500 train |
| Ciudad Anuncios curve | late gain/100 ≈ 0.004; still &lt;1500 processed |

See `reports/modeling_dataset_summary.json`, `reports/phase5_model_report.json`, `reports/learning_curve_data_scale.json`.

## Modeling guidance

1. **Train on `modeling_manifest.jsonl`**, not raw files.  
2. Platform stratification: Doplim / Locanto / Ciudad Anuncios are the only sources with meaningful N.  
3. Facebook / Evisos: keep collecting opportunistically; do not force 1500.  
4. Data-scale CAP still applies for TF-IDF baseline (see `data_scale_recommendation.md`) — more volume helps less than better labels/models.  
5. Weak labels remain exploratory; human adjudication is the next quality lever.

## Scripts touched

- `tools/rebuild_manifest_from_raw.py` — OFFTOPIC, body extractors, FB/CA platforms  
- `tools/learning_curve_data_scale.py` — `ciudadanuncios` bucket  
- `tools/build_modeling_dataset.py` — **new**  
- `docs/MODELING.md` — **new**  
- `docs/COLLECTION_AGENTS.md`, `AGENTS.md` — scoreboard + modeling cycle  
