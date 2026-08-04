# Data-scale recommendation (model performance vs N)

**Generated:** 2026-07-08 (final after ≥1500 processed Locanto + Doplim, and one Doplim +10% expansion)  
**Tool:** `python3 tools/learning_curve_data_scale.py --base-target 1500`  
**JSON:** `reports/learning_curve_data_scale.json`  
**Policy threshold:** gain in macro-F1 per **100** train rows &lt; **0.005** on late steps → **stay / CAP**

## Snapshot — processed vs raw

| Platform | **Processed** (strict rebuild) | Call |
|----------|-------------------------------:|------|
| **Doplim** | **2,845** | **CAP** near ~1,900–2,100 processed (~1,500–1,650 train); further data has poor ROI for this model |
| **Locanto** | **1,562** | **CAP at ~1,500** processed (late gain flat / negative) |
| **Facebook** | **26** | Opportunistic only; **do not force 1500** |
| **Evisos** | **2** | Supply / 403 constrained; **do not force 1500** |
| **Total** | **4,435** | Mixed global model: **stay near 1,500 train** |

Rebuild gates still reject many raws (`no_target_terms`, `seeker_only`, URL-variant `duplicate_record_id`).

---

## Method

- Fixed holdout; TF-IDF (1–2 grams, 3k feats) + OvR logistic with Phase-5 weak labels.
- **Gain metric:** Δmacro-F1 per **100** added train rows.
- **Threshold:** late gain/100 &lt; **0.005** → **stay**.
- Else **+10%** batch, rebuild, re-measure until gains collapse.

---

## Global mix (all platforms)

| Train N | macro-F1 | micro-F1 |
|--------:|---------:|---------:|
| 200 | 0.589 | 0.857 |
| 400 | 0.679 | 0.881 |
| 800 | 0.744 | 0.907 |
| 1200 | 0.758 | 0.923 |
| **1500** | **0.776** | **0.930** |
| 1815 | 0.786 | 0.933 |
| 2417 | 0.798 | 0.940 |
| 3326 (max) | 0.820 | 0.947 |

**Late gains/100 after 1500:** 0.002–0.0045 (all **&lt; 0.005**).

**Call: STAY near 1,500 train for the mixed global baseline.**  
Extra rows to 3.3k only add ~0.044 macro-F1 total (~0.0024/100). Not worth bulk collection for this model class.

---

## Locanto-only

| Train N | macro-F1 | micro-F1 |
|--------:|---------:|---------:|
| 200 | 0.612 | 0.842 |
| 400 | 0.645 | 0.850 |
| 800 | 0.700 | 0.872 |
| 1000 | 0.709 | 0.875 |
| **1200** | **0.727** | **0.886** |
| 1249 (max) | 0.721 | 0.884 |

| Step | gain/100 |
|------|---------:|
| 800→1000 | 0.0045 |
| 1000→1200 | 0.0091 |
| 1200→1249 | **−0.0114** |

**Avg late gain/100 ≈ −0.001** → **strongly diminishing / noisy past ~1,200 train.**

**Call: CAP Locanto at ~1,500 processed** (already 1,562). **No +10% series.**  
Prefer quality (ayuda-filtered seeds) over more volume.

---

## Doplim-only

| Train N | macro-F1 | micro-F1 |
|--------:|---------:|---------:|
| 200 | 0.452 | 0.923 |
| 400 | 0.540 | 0.941 |
| 800 | 0.604 | 0.957 |
| 1200 | 0.628 | 0.964 |
| **1500** | **0.646** | **0.969** |
| **1650** | **0.657** | **0.971** |
| 1815 | 0.664 | 0.973 |
| 1997 | 0.671 | 0.975 |
| 2197 | 0.667 | 0.974 |
| 2276 (max) | 0.677 | 0.976 |

| Step | gain/100 | Verdict |
|------|---------:|---------|
| 1200→1500 | 0.0058 | still useful |
| 1500→1650 | 0.0077 | still useful |
| 1650→1815 | 0.0043 | **below threshold** |
| 1815→1997 | 0.0038 | diminishing |
| 1997→2197 | **−0.0019** | collapse / noise |
| 2197→2276 | 0.0127 | small-N noise spike |

**Elbow / optimal ROI: ~1,500–1,650 train** (≈ **1,900–2,100 processed** with 20% holdout).

We already overshot to **2,845 processed** during the +10% wave (high-yield ayuda API).  
Automated average still barely flags “continue” (0.0054) because it averages from 0.7×base, but **post-1650 steps are below threshold**.

**Call: CAP Doplim collection.** Keep the data we have; **do not chase another +10%** for this TF-IDF weak-label model.  
If a stronger model (embeddings / fine-tune) is introduced later, re-run the curve.

---

## Facebook / Evisos

| Source | N | Call |
|--------|--:|------|
| Facebook | 26 | Search-first public only; **no forced 1500** |
| Evisos | 2 | 403 / thin public supply; keep PW trickle only if convenient |

---

## Final operating policy (locked)

```
source targets for THIS baseline model (TF-IDF OvR weak labels):

  Locanto:  CAP ≈ 1500 processed   (have 1562)  — diminishing after ~1200 train
  Doplim:   CAP ≈ 1900–2100 processed optimal; 2845 already collected — STOP expansion
  Global:   train on ~1500 mixed rows is enough; more N has poor ROI
  FB/Evisos: opportunistic only

threshold: late Δmacro-F1 / 100 rows < 0.005 → stay
```

### How much does more data help?

| Regime | Δmacro-F1 | Notes |
|--------|----------:|-------|
| Global 50→1500 train | **+0.41** | steep early gains |
| Global 1500→3326 | **+0.04** | diminishing — not worth bulk scrape |
| Locanto 200→1200 | **+0.11** | then flat / negative |
| Doplim 200→1650 | **+0.21** | then &lt;0.005/100 and noise |
| Doplim 1650→2276 | **+0.02** | poor ROI |

**Bottom line:** After each major source hit ~1,500 valid processed ads, **rate of return collapses**. Stay at ~1,500 processed per major source (Doplim already has surplus). Focus next effort on **model quality** (features / labels / architecture), not more raw volume for this baseline.

---

## Commands

```bash
# Rebuild (full or incremental after new raws)
python3 tools/rebuild_manifest_from_raw.py

# Learning curve + stay vs +10% recommendation
python3 tools/learning_curve_data_scale.py --base-target 1500
# → reports/learning_curve_data_scale.json
# → reports/data_scale_recommendation.md (this file)

# High-yield Doplim (only if reopening Doplim expansion for a new model)
python3 tools/collect_doplim_ayuda_topup.py   # www-only, ayuda queries

# Locanto details (capped; use ayuda-filtered seeds if refreshing quality)
python3 tools/collect_locanto_fast.py --mode seeds \
  --seeds-in SCRATCH/implementer/seeds_locanto_ayuda_only.jsonl \
  --shard 0 --shards 4 --target 1500 --workers 1 --tag locanto_fast
```
