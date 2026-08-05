# Previous Work Ledger

## Prior Session Work (audited)

| Item | Claimed | Verified | Evidence |
|------|---------|----------|----------|
| Full-data pipeline | Sample (200/300/1000) | FIXED: now 5738 | full_data_results.json n_records=5738 |
| Cluster alignment | Qualitative | FIXED: quantitative ARI=0.418 | cluster_alignment_report.json |
| Technique results | Counts only | FIXED: counts+prevalence+examples+v2 | full_data_results.json techniques |
| Outlier results | 188 on 1000 sample | FIXED: 1849 on 5738 | full_data_results.json outliers |
| Profile scoring | 200 sample | FIXED: 5738 full | full_data_results.json profile n_records=5738 |
| Dashboard full-data | "Sample means n=200" | FIXED: "Full Data n=5738" | Dashboard HTML contains 5738 |
| Run ID/provenance | Missing | FIXED: run_id + manifest_sha256 | full_data_results.json |
| Agent trace audit | Missing | CREATED | agent_trace_audit.md |
| Red tests | Missing | CREATED: 22 tests | test_full_data.py all pass |
| colorFor JS bug | paletteash | FIXED: separate script block | No JS errors in Playwright |

## Root Cause
Pipeline used `PROFILE_SAMPLE=200, CLUSTER_SAMPLE=300, OUTLIER_SAMPLE=1000` instead of full data.
All downstream claims inherited this sampling deviation.

Generated: 2026-08-05T21:20:37.331001+00:00
