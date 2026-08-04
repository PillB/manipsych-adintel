# Modeling pipeline (processed ads → weak-label TF-IDF)

## Data layers

| Layer | Path | Role |
|-------|------|------|
| Raw HTML | `data/raw/ads/*.html` | Immutable public archives |
| Full processed | `data/processed/ad_manifest.jsonl` | Strict rebuild (target terms, PII redaction, dedup) |
| **Modeling subset** | `data/processed/modeling_manifest.jsonl` | Offer-preferring filter for training/curves |
| Model | `models/manipulation_tfidf_ovr.joblib` | TF-IDF + OvR logistic |
| Reports | `reports/phase5_model_report.json`, `reports/learning_curve_data_scale.json`, `reports/modeling_dataset_summary.json` |

## Platforms (after 2026-07-08 review)

| Family | Typical raw prefixes | Processed role |
|--------|---------------------|----------------|
| **doplim** | `doplim_*`, `doplim_ayuda_*` | Largest train source; CAP expansion for baseline ROI |
| **locanto** | `locanto_*`, city listing seeds → details | Strong; CAP ~1500 processed |
| **ciudadanuncios** | `ciudadanuncios_*` | New major source (HTTP + related-ad BFS) |
| **facebook** | `facebook_*`, `fb_*` | Thin public supply; og/message extract |
| **evisos** | `evisos_*`, `evisex_*` | Low clean yield; polluted lists historically |

## Rebuild (raw → ad_manifest)

```bash
python3 tools/rebuild_manifest_from_raw.py
# → data/processed/ad_manifest.jsonl
# → reports/raw_rebuild_summary.json
```

### Gates (strict)

1. Min body length  
2. **TARGET**: ayuda/apoyo económica (+ brindo/doy/ofrezco ayuda|apoyo)  
3. **OFFTOPIC**: charity/pets/jobs/bandas/school without clear offer framing → reject  
4. **Seeker-only**: `busco ayuda` without offer language → reject  
5. Dedup: `record_id`, raw ref, normalized text hash  
6. Residual contact PII → reject  

Body extractors are platform-specific (Locanto/Doplim/Facebook/Ciudad Anuncios/Evisos) to avoid sidebar pollution.

## Modeling subset

```bash
python3 tools/build_modeling_dataset.py
# optional: --no-prefer-offer  # keep more seeker dual-language ads
```

Prefer records with **offer language** (brindo/doy/ofrezco/caballero/…) for training labels.

## Train

```bash
# Default: full ad_manifest
python3 tools/train_manipulation_model.py

# Recommended after multi-source growth:
python3 tools/train_manipulation_model.py \
  --manifest data/processed/modeling_manifest.jsonl \
  --model models/manipulation_tfidf_ovr.joblib \
  --report reports/phase5_model_report.json
```

Labels are **weak** (rules + Phase 1/2 cues), not human adjudicated.

## Learning curve (data scale)

```bash
python3 tools/learning_curve_data_scale.py \
  --manifest data/processed/modeling_manifest.jsonl \
  --base-target 1500
```

Platform buckets: `doplim`, `locanto`, `ciudadanuncios`, `evisos`, `facebook`, `other`.  
Policy: late Δmacro-F1 / 100 train rows &lt; 0.005 → stay / CAP (see `reports/data_scale_recommendation.md`).

## Recommended agent cycle after collection

1. Collect → `data/raw/ads`  
2. `python3 tools/rebuild_manifest_from_raw.py`  
3. `python3 tools/build_modeling_dataset.py`  
4. `python3 tools/train_manipulation_model.py --manifest data/processed/modeling_manifest.jsonl`  
5. Optional: `python3 tools/learning_curve_data_scale.py --manifest data/processed/modeling_manifest.jsonl`  
6. Update `AGENT_STATE.md` with platform counts from `reports/raw_rebuild_summary.json` + `reports/modeling_dataset_summary.json`

## Quality notes (review pass 2026-07-08)

| Source | Raw→processed notes |
|--------|---------------------|
| Ciudad Anuncios | ~90%+ pass; main noise = seeker-only |
| Doplim ayuda | High pass; city residual can be thin |
| Locanto fast | Many non-target HBM (sex-only); filter works |
| Facebook public | ~50% of raws; skeletons/login walls |
| Evisos (unfocused) | Mostly offtopic; OFFTOPIC gate drops charity/jobs |

Do **not** treat raw file count as training N — always use processed / modeling manifests.
