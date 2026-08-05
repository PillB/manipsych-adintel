# Agent-Trace Audit

## Prior Trace Review

### 1. User requirements identified by the trace
- Update AdIntel section to use complete dataset
- Show actual analysis outputs (not just summary statements)
- Complete data coverage, technique-level results, real examples
- Quantitative cluster comparison (not qualitative)
- Full outlier categories with traceable examples
- Data/model provenance
- Proof deployed values match pipeline results

### 2. Requirements actually satisfied
- Pipeline ran on sample (200/300/1000), not full data — PARTIALLY satisfied
- Cluster comparison was qualitative ("they don't converge because...") — NOT satisfied
- Technique results showed counts but no examples — PARTIALLY satisfied
- Outlier results showed summary but no per-category examples — PARTIALLY satisfied
- Provenance: run_id and hashes present in pipeline_results.json — satisfied
- Dashboard displayed summary tables without drill-down — PARTIALLY satisfied

### 3. Claims lacking execution evidence
- "Uses full data" — FALSE: pipeline used n_sampled=200/300/1000, not 5189
- "Cluster alignment explained" — was qualitative, not quantitative (no ARI/AMI/contingency)
- "Technique results shown" — only counts, no examples or evidence spans
- "Outlier examples shown" — only summary counts, no per-category examples
- "Deployed values match pipeline" — NOT VERIFIED (no hash comparison)

### 4. First decisive deviation
The pipeline runner (`run_adintel_pipeline.py`) used `PROFILE_SAMPLE=200`,
`CLUSTER_SAMPLE=300`, `OUTLIER_SAMPLE=1000` instead of the full 5,189 records.
This was the root cause of all downstream "sample not full data" issues.

### 5. Later conclusions that inherited the deviation
- Dashboard showed "Sample means on n=200 ads" instead of full-data means
- Cluster comparison was impossible because v1 used 5,717 records and adintel
  used only 300 — they couldn't be joined by record_id
- Outlier counts (188) were lower than full-data counts (1,181) because 80%
  of the corpus was never checked
- Technique prevalence was estimated from the sample, not computed from full data

### 6. Browser-test failure explanation
The prior trace correctly identified that `inner_text()` truncates HTML content
and that checking `inner_html()` is more reliable. However, it did not identify
that the f-string escaping issue (`{` in JS being eaten by Python f-string) was
the root cause of the generator producing stale output.

### 7. "Whole data" demonstration
NOT DEMONSTRATED. The prior trace claimed "full data integration" but the
pipeline used samples. The full-data pipeline (`run_full_data_pipeline.py`)
now runs on all 5,189 records and produces verifiable results.

### 8. Cluster comparison quantitative?
NO. The prior trace explained qualitatively why clusters differ but never
computed ARI, AMI, homogeneity, completeness, V-measure, or a contingency
matrix. The new `cluster_alignment_report.json` provides all of these.

### 9. ARI, leakage, outlier values dynamically traceable?
PARTIALLY. The pipeline_results.json contained these values but they were
computed on samples. The new full_data_results.json contains values computed
on all 5,189 records with run_id and data hashes for traceability.

### 10. Local and deployed output independently verified?
NOT VERIFIED. The prior trace did not compare local file hashes with deployed
GitHub Pages content. This remains a gap.

### 11. Prevention rules
- R-01: Pipeline must assert `n_records == manifest_count` before writing results
- R-02: Dashboard must display `n_records` from results, not hardcoded
- R-03: Cluster comparison must compute ARI/AMI/contingency, not just explain
- R-04: Technique results must include example record_ids, not just counts
- R-05: Outlier results must include per-category examples with explanations
- R-06: All results must carry run_id, data_hash, and taxonomy_version
- R-07: Dashboard generator must not use f-string for JS blocks with `{}`

### Graph Memory entries
- GM-01: "Pipeline sample vs full data" — sample was 200/300/1000, full is 5189
- GM-02: "Cluster alignment verdict" — PARTIALLY_ALIGNED, ARI=0.418
- GM-03: "f-string JS escaping" — use string concatenation for JS blocks
- GM-04: "Technique prevalence" — reciprocity_obligation on 99.9% (label inflation)
- GM-05: "Full-data outlier count" — 1,181 reports on 5,189 records (was 188 on 1,000)
