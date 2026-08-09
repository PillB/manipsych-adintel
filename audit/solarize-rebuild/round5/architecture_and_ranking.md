# Phase C — Gap Closure Architecture & Strategy Ranking

**Task ID:** SOLARIZE-ROUND-5-ARCH
**Date:** 2026-08-09
**Inputs:** Phase A audit + Phase B research report (`audit/solarize-rebuild/round5/research_best_in_class.md`)

## 1. Gap Inventory (from Phase A audit)

| # | Gap | Current State | Target State | Severity |
|---|-----|---------------|--------------|----------|
| G1 | UMAP projection is fake | `renderUmapMap()` places points on a circle by cluster_id + Math.random() noise (lines 1214-1217 of `adintel_dashboard_v2.html`) | Real UMAP 2D projection of TF-IDF cosine space, pre-computed and embedded | **Critical** — advertised feature is misleading |
| G2 | HDBSCAN baseline is placeholder | Text says "Not yet benchmarked. Expected to outperform" | Actually run HDBSCAN with research-recommended params; report real n_clusters, noise%, ARI vs KMeans | **Critical** — false claim |
| G3 | Authorship scores uncalibrated | "97.6% accuracy" shown, calibration status = UNCALIBRATED | Platt-scaled probabilities with Brier/ECE on held-out set | High — research defensibility |
| G4 | Contrast-set eval is rule-based sandbox only | Interactive contrast-set UI exists, but no measured detection rates per perturbation type | Static table with per-type detection rate + robustness drop, flagged defects | Medium — adversarial robustness story |
| G5 | Analyzer may not be fully integrated | "Analyze an Ad" tab exists; need to verify it has 17-dim profile + evidence + export | Confirmed parity with the standalone analyzer | Medium |
| G6 | Local↔live parity | Verified — `git diff` of `docs/reports/adintel/adintel_dashboard_v2.html` shows committed version matches live | Maintain parity through all changes | Process |
| G7 | Red test pass rate | 48 tests written, last summary said 21/22 passed; 48-test status unknown | All 48 pass on live | Process |

## 2. Strategy Comparison & Ranking

For each gap, multiple strategies are possible. We rank by **impact × (1/cost)** = "value density".

### G1 — Fake UMAP → Real UMAP

| Strategy | Description | Impact | Cost | Value |
|----------|-------------|--------|------|-------|
| **S1.1** ✅ | Server-side UMAP on TF-IDF, pack coords as Float32 base64 inline | High | Low | **9.0** |
| S1.2 | Server-side UMAP, fetch coords as separate `.bin` file | High | Low | 7.5 (extra request) |
| S1.3 | Client-side UMAP via `umap-js` CDN | High | High (3MB+ tfidf matrix shipped) | 2.0 |
| S1.4 | Use PCA instead of UMAP (faster, deterministic) | Medium | Very Low | 6.0 |
| S1.5 | Skip — keep radial proxy but rename to "Cluster wheel" | Low | Zero | 1.0 |

**Chosen: S1.1** — server-side UMAP, Float32 base64 inline. Best UX (no extra request), respects 145KB HTML budget, deterministic with `random_state=42`.

### G2 — HDBSCAN placeholder → Real HDBSCAN benchmark

| Strategy | Description | Impact | Cost | Value |
|----------|-------------|--------|------|-------|
| **S2.1** ✅ | Run HDBSCAN with research params on full corpus, replace placeholder with real metrics | High | Low | **9.5** |
| S2.2 | Run HDBSCAN + replace KMeans in pipeline (full migration) | High | High | 6.0 (risky) |
| S2.3 | Document the comparison only, don't actually run | Low | Very Low | 3.0 (still misleading) |

**Chosen: S2.1** — real benchmark with KMeans kept as baseline. Report n_clusters, noise%, silhouette, ARI vs KMeans labels, top-10 cluster sizes.

### G3 — Authorship calibration

| Strategy | Description | Impact | Cost | Value |
|----------|-------------|--------|------|-------|
| **S3.1** ✅ | Platt scaling (LogisticRegression) on existing 41 known pairs + 50 synthetic negatives | Medium | Low | **7.5** |
| S3.2 | Isotonic regression on same data | Medium | Low | 7.0 (less stable on small n) |
| S3.3 | Temperature scaling | Low | Very Low | 5.0 (typically for NN, not heuristic scores) |
| S3.4 | Defer to v2.1, document limitation in dashboard | Low | Zero | 4.0 |

**Chosen: S3.1** — Platt scaling with documented limitation that calibration set is small (41 positives + 50 synthetic negatives). Compute Brier score, ECE, log-loss on a held-out 20% split. Show calibration curve in dashboard.

### G4 — Contrast-set evaluation

| Strategy | Description | Impact | Cost | Value |
|----------|-------------|--------|------|-------|
| **S4.1** ✅ | Implement 6 perturbation types (synonym swap, negation insert, formality shift, perspective shift, paraphrase, length truncate) on 100 ads/type; compute detection rates; render table | Medium | Medium | **7.0** |
| S4.2 | Implement only 3 types (synonym, negation, length) — simpler | Medium | Low | 6.5 |
| S4.3 | Skip measured rates; keep interactive sandbox only | Low | Zero | 3.0 |

**Chosen: S4.1** — full 6-type suite. Back-translation (MarianMT) is replaced with a simpler rule-based paraphrase to avoid pulling in `transformers`. Document this trade-off in the dashboard.

### G5 — Analyzer integration verification

Quick verification: load the dashboard, click "Analyze an Ad", confirm:
- Text input works
- 17-dim profile renders
- Evidence highlighting works
- Export button produces JSON

If anything missing, integrate from `repo/scripts/generate_interactive_analyzer.py`.

## 3. Final Implementation Plan

| Step | Module | Deliverable | Hours |
|------|--------|-------------|-------|
| 1 | `repo/scripts/run_hdbscan_benchmark.py` | `repo/reports/adintel/hdbscan_benchmark.json` with real metrics | 1.5 |
| 2 | `repo/scripts/run_umap_projection.py` | `repo/reports/adintel/umap_coords.json` (5738×2) + `umap_coords.b64` (Float32) | 1.5 |
| 3 | `repo/scripts/run_authorship_calibration.py` | `repo/reports/adintel/authorship_calibration.json` with Brier/ECE/log-loss + per-pair calibrated probabilities | 2 |
| 4 | `repo/scripts/run_contrast_sets.py` | `repo/reports/adintel/contrast_set_results.json` with 6 perturbation types × 100 ads | 3 |
| 5 | `repo/scripts/generate_adintel_dashboard_v2.py` (patch) | Embed real UMAP coords, real HDBSCAN benchmark, real calibration curve, real contrast-set table | 3 |
| 6 | Local smoke test | Confirm HTML ≤ 250KB, no console errors, all subtabs render | 0.5 |
| 7 | `git commit && git push` | Deploy to GitHub Pages | 0.25 |
| 8 | Run all 48 Red tests against live | Iterate fixes | 2 |
| 9 | Verify local↔live parity | `diff <(curl live) local.html` | 0.25 |
| 10 | Update worklog + final commit | Document everything | 0.5 |

**Total: ~14.5 hours of implementation work.**

## 4. Risk Register

| Risk | Mitigation |
|------|------------|
| UMAP non-deterministic despite `random_state=42` | Set `n_jobs=1`, `transform_seed=42`, `NUMBA_NUM_THREADS=1`; verify byte-identical coords on re-run |
| HDBSCAN produces 1 giant cluster + 99% noise | Try `cluster_selection_method='eom'` as fallback; if still degenerate, report honestly as "HDBSCAN not suited to this corpus" |
| Calibration overfits on 41 positive pairs | Document the limitation; use leave-one-out CV for Brier score; report confidence interval |
| Contrast-set back-translation requires MarianMT (3GB model) | Use rule-based paraphrase (synonym swap from WordNet only); document the simplification |
| HTML budget exceeded | Aggressive minification of inline JS; pack coords as Float32; drop unused v1 dashboard sections |
| Push to GitHub Pages blocked by auth | Use `git` with stored HTTPS credentials or `gh` CLI |

## 5. Success Criteria

After completion, all of these must be true:
1. `repo/reports/adintel/hdbscan_benchmark.json` exists with real numbers (not placeholders)
2. `repo/reports/adintel/umap_coords.json` exists with 5,738 (x, y) pairs
3. `repo/reports/adintel/authorship_calibration.json` exists with Brier, ECE, log-loss
4. `repo/reports/adintel/contrast_set_results.json` exists with 6 perturbation types
5. Dashboard HTML ≤ 250KB (raw)
6. Dashboard renders without console errors
7. Live deployment matches local (`diff` empty)
8. All 48 Red tests pass on live
9. `worklog.md` updated with final summary
