# Prevention Rules

| Rule | Description | Test |
|------|-------------|------|
| R-01 | Pipeline must assert n_records == manifest_count | test_manifest_count_matches_pipeline |
| R-02 | Dashboard must display n_records from results, not hardcoded | test_profile_uses_all_records |
| R-03 | Cluster comparison must compute ARI/AMI/contingency | test_ari_computed, test_contingency_matrix_present |
| R-04 | Technique results must include example record_ids | test_every_technique_has_examples |
| R-05 | Outlier results must include per-category examples | test_outlier_examples_present |
| R-06 | All results must carry run_id and data_hash | test_run_id_present, test_data_hashes_present |
| R-07 | Dashboard JS must not be inside Python f-string with {} | Playwright 0 console errors |
| R-08 | Generator must not manually patch HTML | Git diff shows only .py changes |
| R-09 | Deployed content must match local build | curl grep count matches local |
| R-10 | Full-data pipeline must run on ALL records | test_no_undocumented_sample |
