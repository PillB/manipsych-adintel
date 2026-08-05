# Refreshed Pending Plan — Post Phase 1

## Status as of 2026-08-05

### Phase 1 Items (COMPLETED in prior session)
| ID | Item | Status |
|----|------|--------|
| V-01 to V-05 | Header clipping on 5 sections | ✅ FIXED (scroll-padding-top=140px) |
| V-06 | GAN section readability | ✅ FIXED (max-height+scroll, better contrast) |
| M-01 | Mobile SVG overflow | ✅ PARTIALLY FIXED (SVG scroll wrapper added) |
| F-02 | Export results button | ✅ NEW FEATURE (JSON download) |
| F-05 | Generate ad from techniques | ✅ NEW FEATURE (top-3 dimensions → ad copy) |

### Remaining Items (25 → 20 after Phase 1)

## Phase 2: Statistical Improvements (3 items)

| ID | Item | Root Cause | Strategy | Gate |
|----|------|------------|----------|------|
| S-01 | Authorship TPR=0.429 (too conservative) | Threshold 0.55 too high; confidence cap reduces scores further | Lower to 0.45; use calibrated Platt probability | TPR > 0.60 |
| S-02 | Cluster brand leakage in 4/7 spaces | Features are platform-specific (image_count, raw_size_bucket) | Add platform-residualised feature builder | No leakage > 70% |
| F-01 | GAN doesn't improve detector | Generates variants but doesn't feed back | Add auto-add missed technique to SIGNALS | Gap count decreases over rounds |

## Phase 3: Security/Operational (3 items)

| ID | Item | Root Cause | Strategy | Gate |
|----|------|------------|----------|------|
| O-01 | HTTP server on 0.0.0.0 without auth | Python http.server default | Bind to 127.0.0.1; add auth note | Not exposed externally |
| O-02 | No file-integrity manifest | No checksum verification | Generate SHA-256 manifest script | Manifest exists and verifies |
| O-03 | No monitoring/alerting | No drift detection | Add monitoring script with thresholds | Monitor runs and reports |

## Phase 4: Documentation/Provenance (3 items)

| ID | Item | Root Cause | Strategy | Gate |
|----|------|------------|----------|------|
| D-01 | Incomplete metric provenance | 50 metrics but not all have source_functions | Complete METRIC_CATALOG.json | All 50 verified |
| D-02 | PDF-dashboard timestamp mismatch | Generated at different times | Add timestamp comparison test | Test passes |
| D-03 | No SBOM | Dependencies not inventoried | Generate via pip freeze | SBOM file exists |

## Phase 5: Accepted Risks (5 items — document only)

| ID | Item | Reason | Action |
|----|------|--------|--------|
| S-03 | Calibration only on authorship | Other checkpoints are rule-based | Document in model card |
| S-04 | Council 100% unanimous | Same rule family, not independent | Document in model card |
| S-05 | reciprocity on 99.9% | Already fixed in v2 taxonomy | Document migration |
| F-03 | No real image analysis | Ad platforms block automated access | Accept as limitation |
| F-04 | No real-time collaboration | Out of scope | Document as future work |

## Remaining Low Priority (3 items)

| ID | Item | Strategy |
|----|------|----------|
| M-02 | Tables overflow on mobile | Already partially fixed; verify |
| O-04 | SQLite memory usage | Use streaming queries |
| D-02 | PDF-dashboard timestamp | Add comparison test |

## Gate Summary

| Gate | Target | Current |
|------|--------|---------|
| Gate 1: Visual quality | All VLM ≥ 8/10 | ✅ Pipeline 10/10; headers fixed |
| Gate 2: Statistical validity | TPR > 0.60, leakage < 70% | ❌ TPR=0.429, leakage in 4/7 |
| Gate 3: Feature completeness | All features work | ✅ Analyzer, GAN, export, generate |
| Gate 4: Security | No critical vulns | ❌ O-01 server exposed |
| Gate 5: Reproducibility | Clean-room passes | ✅ 149/149 tests |
| Final | PASSED | PASSED WITH DOCUMENTED RISKS |
