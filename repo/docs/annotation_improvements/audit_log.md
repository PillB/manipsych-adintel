# Annotation Quality Audit and Improvements

## Audit Date: 2026-08-04
## Auditor: Z.ai Agent (independent review)

## Systematic Issues Found

### Issue 1: 100% Unanimous Agreement (CRITICAL)
- **Finding**: All 5,717 annotations have `agreement=1.0` (3/3 council unanimity)
- **Root cause**: The council uses the same rules with slightly different parameters, so 3-of-3 agreement is NOT independent confirmation
- **Impact**: Agreement metrics are inflated; true inter-annotator reliability is unknown
- **Fix**: Document this limitation in the annotation schema; do not treat agreement=1.0 as independent validation
- **Status**: Documented in `label_schema.json` and `corpus_snapshot.json`

### Issue 2: reciprocity_obligation on 99.9% of Records (HIGH)
- **Finding**: 5,711 of 5,717 records have the `reciprocity_obligation` label
- **Root cause**: The v1 rule fires on the word "ayuda" which is in the corpus inclusion criteria itself — the label is partially definitional
- **Impact**: The label has no discriminative power; it appears on essentially every ad
- **Fix**: In v2 taxonomy, `reciprocity_obligation` splits into `cc_reciprocity_frame` (copywriting) and `bs_reciprocity_obligation` (behavioural). The copywriting variant should NOT fire on every "ayuda" — only when the framing explicitly invokes reciprocity
- **Status**: Fixed in adintel/taxonomy.py v2; migration script applies the split

### Issue 3: 73.2% Have Duplicate Spans (MEDIUM)
- **Finding**: 4,187 records have duplicate spans (same label + same exact_text appearing multiple times)
- **Root cause**: The council regex finds the same word multiple times and creates a span for each occurrence
- **Impact**: Span counts are inflated; the same evidence is counted multiple times
- **Fix**: Deduplicate spans by (label, exact_text) before counting; keep the first occurrence only
- **Status**: Fix implemented in `scripts/deduplicate_annotations.py`

### Issue 4: No Missing Rationales (GOOD)
- **Finding**: 0 spans have missing rationale
- **Status**: No action needed

### Issue 5: No Low-Intensity/High-Harm Contradictions (GOOD)
- **Finding**: 0 records have persuasive_intensity ≤ 1 with harm_risk ≥ 3
- **Status**: No action needed

## Improvements Implemented

1. **v2 taxonomy split**: `reciprocity_obligation` → `cc_reciprocity_frame` + `bs_reciprocity_obligation`
2. **Span deduplication**: `scripts/deduplicate_annotations.py` removes duplicate (label, exact_text) pairs
3. **Documentation**: Limitations documented in `docs/annotation_improvements/audit_log.md`
4. **Silver annotation**: Independent annotator with different patterns (`scripts/simulate_gold_and_silver.py`)
5. **Agreement measurement**: Cohen's kappa computed between simulated-gold and silver

## Remaining Limitations

- Gold annotations are SIMULATED, not real human adjudication
- Council members are not truly independent (same rule family)
- Real human annotation would likely show LOWER agreement
- The 99.9% reciprocity prevalence means the label is not useful for discrimination
