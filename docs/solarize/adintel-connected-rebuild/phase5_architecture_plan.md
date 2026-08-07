# Solarize AdIntel Rebuild — Phase 5 Architecture Plan

## Deep Audit: Pending Limitations and Gaps

### From Round 1 Forensic Audit (dead-end journeys)
1. **J02**: Explorer shows no highlighted evidence spans in ad detail
2. **J09**: Adversarial generation not in main dashboard (only standalone analyzer)
3. **J10**: No synthetic-data quarantine workflow visible
4. **J11/J12/J14**: No tutorial system exists
5. **J15**: No "Ask AdIntel" contextual assistant

### From Round 3 Red Tests (22 failing, now partially addressed by v2)
- v2 dashboard exists locally but the **v1 dashboard is still the primary live deployment** (13.7 MB)
- v2 is 80 KB with 5-section architecture but was never fully deployed (Pages build issues)
- **22 Red tests still fail against the v1 live deployment** because v1 lacks: task-oriented nav, ad grader, tutorial, assistant, indicator dictionary

### From Pipeline Re-run (body cleaning fix)
- Silhouette improved 0.0052 → 0.0097 but still very low
- 68% of ads are DBSCAN density-noise — clusters are weak
- "NOT_MEANINGFULLY_DIFFERENT" verdict for outlier_vs_all — outliers aren't term-different from corpus
- Deep clustering NOT JUSTIFIED (LSA only +0.026 over raw TF-IDF)

### From Spec Section 29 (Final Acceptance Gate) — items NOT met
1. ❌ Main navigation is NOT task-oriented (v1 has 22 sections, v2 not deployed)
2. ❌ Standalone analyzer NOT integrated (still separate URL)
3. ❌ "GAN" label removed in standalone analyzer but v1 dashboard still references "GAN"
4. ❌ Adversarial generator NOT visible in main dashboard
5. ❌ Tutorial does NOT exist
6. ❌ "Ask AdIntel" assistant does NOT exist
7. ❌ Indicator dictionary does NOT exist
8. ❌ Performance budget NOT met (13.7 MB HTML vs 150 KB target)

## SOTA Research Findings

### Clustering (HDBSCAN + BERTopic)
- **HDBSCAN** with mBERT embeddings achieves SOTA on short-text clustering
- **BERTopic** handles short texts better than plain TF-IDF
- **Key insight**: TF-IDF alone is weak for short Spanish ads. Embedding-based clustering (even lightweight) would improve silhouette.
- **Feasibility**: HDBSCAN is available in scikit-learn ecosystem. Can run offline, embed results in dashboard.
- **Action**: Add HDBSCAN as a clustering benchmark alongside KMeans. If it outperforms, use it as the canonical clustering.

### Visualization (UMAP + D3.js)
- **UMAP** preserves both local and global structure better than t-SNE for medium-large datasets
- **Interactive embedding viewers** (like Nomic Atlas) support hover, click, filter, lasso-select
- **D3.js force-directed graphs** allow interactive term networks with hover/click/filter
- **Action**: Replace the static SVG corpus map with a UMAP projection (pre-computed offline) + D3.js interactive scatter. Replace the static term network with a D3.js force-directed graph.

### Persuasion Detection (Transformer + Evidence Spans)
- **Transformer fusion** (mBERT + XLM-R) achieves SOTA on SemEval persuasion detection
- **Evidence span extraction** is a separate task — joint classification + span models exist
- **Key insight**: The current rule-based detector is a valid baseline but should be honestly labeled. A lightweight fine-tuned model would improve detection.
- **Feasibility**: Fine-tuning requires GPU + labeled data. Can be done offline, model card documented.
- **Action**: Document the rule-based detector as "Rule-Based Baseline" in the model registry. Add a research-only benchmark entry for transformer-based detection (not deployed).

### Adversarial Robustness (Contrast Sets + TextAttack)
- **Contrast sets** (minimal perturbations) are the gold standard for robustness evaluation
- **TextAttack** framework provides standardized adversarial attack/defense evaluation
- **Key insight**: The current "Rule-Based Adversarial Sandbox" (renamed from "GAN") is a primitive contrast-set tool. It should be formalized with proper evaluation metrics.
- **Action**: Formalize the adversarial sandbox as a contrast-set framework with: perturbation types, detection rate before/after, semantic validity check, and honest labeling.

## Architecture Plan

### Phase 5A: Deploy v2 as primary dashboard (fix build issues)
- Switch GitHub Pages to Actions build type
- Deploy v2 (80 KB) as primary, redirect v1 to v2
- Run live Red tests against v2

### Phase 5B: Improve clustering with HDBSCAN benchmark
- Add HDBSCAN to `solarize_engine.py` benchmark
- Compare KMeans vs HDBSCAN silhouette + stability
- If HDBSCAN wins, use it as canonical clustering
- Pre-compute UMAP 2D projection for corpus map

### Phase 5C: Integrate standalone analyzer into v2
- Move analyzer text-input + evidence highlighting into v2's "Analyze an Ad" section
- Remove the standalone analyzer page (redirect to v2#analyze)
- Preserve all analyzer capabilities (text analysis, evidence spans, profile, export)

### Phase 5D: Build tutorial system in v2
- Custom FSM + Driver.js (5 KB) overlay
- 6 tutorial modes with event-driven advancement
- localStorage persistence
- Keyboard accessible (Escape, Tab, Enter)

### Phase 5E: Build "Ask AdIntel" assistant in v2
- Local evidence assistant with deterministic templates
- Cites indicator definitions and evidence spans
- Refuses manipulation-optimization requests

### Phase 5F: Build indicator dictionary
- Canonical definitions for all 17 profile dimensions + outlier kinds + cluster metrics
- Per-indicator: formula, numerator, denominator, unit, range, thresholds, limitations
- Accessible from v2#guide > Indicator Dictionary subtab

### Phase 5G: Formalize adversarial sandbox as contrast-set framework
- Document perturbation types (phrase insertion, word swap, negation)
- Add detection-rate-before/after metrics
- Add semantic-validity check (does the perturbation change meaning?)
- Honest labeling throughout

## Deliverables
1. Deployed v2 dashboard (80 KB, 5-section architecture)
2. HDBSCAN clustering benchmark results
3. UMAP corpus map projection
4. Integrated ad-analysis workspace
5. Restartable tutorial system
6. "Ask AdIntel" contextual assistant
7. Canonical indicator dictionary
8. Formalized contrast-set adversarial framework
9. Live Playwright validation (all Red tests pass)
10. Comprehensive phase retrospective

## Tests
- All 48 Red tests from Round 3 must pass against the live v2 deployment
- HDBSCAN benchmark: silhouette ≥ KMeans baseline
- UMAP projection: all 5,738 points rendered, click-to-inspect works
- Tutorial: start, pause, resume, stop, restart, reset, persist-after-refresh
- Assistant: responds to indicator queries, refuses manipulation requests
- Indicator dictionary: all 17 dimensions + 4 outlier kinds + 6 cluster metrics defined
- Performance: HTML < 150 KB, no duplicated payload, LCP < 2.5s
