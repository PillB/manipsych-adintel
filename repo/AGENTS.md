# AGENTS.md — ManiPsych agent operating notes

## Mandatory cycle

1. Read `AGENT_STATE.md`
2. Act on the current sub-task
3. Write and compress updates into `AGENT_STATE.md`

## Collection (Phase 4 volume)

**Authoritative playbook:** [`docs/COLLECTION_AGENTS.md`](docs/COLLECTION_AGENTS.md)  
**Modeling pipeline:** [`docs/MODELING.md`](docs/MODELING.md)  
**New sources (FB / Ciudad Anuncios):** [`reports/new_sources_facebook_playbook.md`](reports/new_sources_facebook_playbook.md)  
**Data scale policy:** [`reports/data_scale_recommendation.md`](reports/data_scale_recommendation.md)

### Skills (project)

| Slash | Skill dir |
|-------|-----------|
| `/collect-doplim` | `.grok/skills/collect-doplim/` |
| `/collect-locanto` | `.grok/skills/collect-locanto/` |
| `/collect-evisos` | `.grok/skills/collect-evisos/` |
| `/collect-facebook` | `.grok/skills/collect-facebook/` |
| `/collect-ciudadanuncios` | `.grok/skills/collect-ciudadanuncios/` |

### Quick targets

```bash
# Doplim (reference high-throughput path)
python3 tools/collect_doplim_evisos_fast.py --platform doplim --target-doplim 1500 --workers 14

# Locanto detail raws (mine listing archives first)
python3 tools/collect_locanto_fast.py --mode mine --target 1500 --workers 5

# Ciudad Anuncios (major new HTTP source)
python3 tools/collect_ciudadanuncios.py --target 200 --max-visit 1200

# Facebook public posts (HTTP-first)
python3 tools/collect_facebook_public.py --target 25 \
  --seeds-jsonl SCRATCH/implementer/seeds_facebook_public.jsonl

# Evisos/Evisex focused (avoid polluted broad lists)
python3 tools/collect_evisos_focused.py --target 100 --max-pages 15
```

Raw HTML **must** land under `data/raw/ads/`.

### After collection → modeling

```bash
python3 tools/rebuild_manifest_from_raw.py
python3 tools/build_modeling_dataset.py
python3 tools/train_manipulation_model.py --manifest data/processed/modeling_manifest.jsonl
python3 tools/learning_curve_data_scale.py --manifest data/processed/modeling_manifest.jsonl --base-target 1500
```

## Other key paths

- Strategy guide: `reports/scraping_strategy_guide.md`
- Shared fetch/extract: `tools/scrape_ads.py`
- Structure notes: `SCRATCH/implementer/site_structure_learnings_20260708.md`
