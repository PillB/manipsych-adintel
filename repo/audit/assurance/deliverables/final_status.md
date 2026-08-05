# Final Status: PASSED WITH DOCUMENTED RISKS

## Summary
- Full-data pipeline runs on ALL 5738 records (verified by 22 Red tests)
- Quantitative cluster alignment: PARTIALLY_ALIGNED (ARI=0.418)
- Technique results: 20 techniques with counts, prevalence, v2 mapping, examples
- Outlier results: 1849 reports across 6 categories with examples
- Dashboard displays full-data results with run_id and manifest hash
- 0 JS console errors on live GitHub Pages
- 215 tests pass

## Remaining Risks
1. Cluster alignment uses k=5 vs k=10 — different k makes comparison imperfect
2. V1 clusters run on full data but adintel pipeline sample uses 300 for stability
3. Deployed content verified via curl but not via Playwright DOM assertion on live
4. annotations_export.jsonl not present (0 records in manifest)
5. SQLite database (204MB) not loaded by pipeline scripts

## NOT VERIFIED
- Local/deployed hash equivalence (different timestamps in generated HTML)
- Source-mutation propagation test (not implemented)
- Model-run propagation test (not implemented)

Generated: 2026-08-05T21:20:37.331001+00:00
