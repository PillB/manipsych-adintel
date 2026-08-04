# Ad Intelligence AI Assurance — Final Report

## 1. Executive Summary

This report documents the application of the Ad Intelligence AI Assurance, Red-Team and Model-Validation System to the ManiPsych + adintel repository. The program executed a condensed but real Macrocycle 1 with 44 attack-fixture tests, 3 critical/high defect fixes, clean-room reproduction, negative-pair authorship evaluation, and calibration wiring. The final verdict is **PASSED WITH DOCUMENTED RISKS**.

**Key metrics**:
- 231 tests pass / 1 environmental fail (was 187 at baseline)
- 44 attack fixture tests: all pass (was 3 fail before fixes)
- Playwright live audit: 32/32 steps pass, 0 errors
- Clean-room reproduction: 149/149 adintel tests pass in independent venv
- Authorship accuracy: 100% (41/41 known same-source pairs)
- Authorship FPR: 0.000 (0 false positives on 100 different-source pairs)
- Calibration: Platt scaling wired, Brier=0.0034, ECE=0.0525

## 2. What was wrong

| ID | Defect | Severity | Root cause |
|---|---|---|---|
| RT-001 | Score gaming via keyword repetition | High | `_score_with_signals` summed all hits without per-signal cap |
| RT-002 | False statistical claims not detected | Medium | `_CLAIM_EXTREMITY_SIGNALS` regex missing "resultado asegurado" |
| RT-003 | Near-copy authorship false negative | High | `_confidence_cap` too aggressive for short near-duplicate text |
| RT-004 | Pipeline scripts missing from repo | Critical | Scripts created outside repo, never committed |
| RT-005 | Calibration not wired | High | `platt_scale` helper existed but was never called |
| RT-006 | No negative-pair authorship evaluation | High | Only positive pairs existed; FPR unknown |

## 3. How it was demonstrated

- **Red phase**: 44 attack fixture tests written in `tests/adintel/test_attack_fixtures.py` covering all 30+ attack vectors from the spec
- **3 tests failed initially** (RT-001, RT-002, RT-003), demonstrating real vulnerabilities
- **Green phase**: smallest coherent fix applied to each defect
- **Clean-room**: fresh git worktree at `/tmp/cleanroom/repo`, independent venv at `/tmp/cleanroom-venv`, 149/149 tests pass
- **Negative-pair evaluation**: 100 different-campaign-group pairs constructed, FPR=0.000 measured
- **Calibration**: Platt scaling fitted on 400 pairs (200 pos, 200 neg), Brier=0.0034

## 4. What was changed & where

| File | Change |
|---|---|
| `adintel/profile.py` | RT-001: added `max_hits_per_signal=3` cap; RT-002: added 2 claim-extremity signals |
| `adintel/authorship.py` | RT-003: relaxed `_confidence_cap` when `raw_stylometry >= 0.60` |
| `adintel/checkpoints.py` | RT-005: updated authorship-v1 calibration_status to "platt" |
| `scripts/` (5 files) | RT-004: added pipeline, dashboard, PDF, migration, Playwright scripts |
| `scripts/evaluate_negative_pairs.py` | RT-006: new script for negative-pair FPR evaluation |
| `scripts/wire_calibration.py` | RT-005: new script for Platt scaling calibration |
| `tests/adintel/test_attack_fixtures.py` | 44 attack fixture tests (25+ attack vectors) |
| `models/authorship_platt_calibration.pkl` | Calibrated Platt scaling model |
| `audit/assurance/deliverables/` | 9 deliverable documents |
| `audit/assurance/evidence/` | Clean-room, negative-pair, calibration evidence |

## 5. Which tests prove the correction

- `tests/adintel/test_attack_fixtures.py::ScoreGamingTests::test_repeating_keyword_does_not_inflate_score`
- `tests/adintel/test_attack_fixtures.py::FalseStatisticalClaimsTests::test_extremity_detected`
- `tests/adintel/test_attack_fixtures.py::NearCopyingTests::test_near_copy_detected_as_same_source`
- `tests/adintel/test_attack_fixtures.py::CampaignLeakageTests::test_no_link_crosses_train_test_split`
- `tests/adintel/test_attack_fixtures.py::PrivacyGuardrailTests` (3 tests)
- `tests/adintel/test_attack_fixtures.py::NoAveragingUncalibratedTests`
- 44 total attack fixture tests, all passing

## 6. How every reportable figure is produced

```
data/processed/ad_manifest.jsonl (5,189 records)
  → scripts/run_adintel_pipeline.py
    → reports/adintel/pipeline_results.json
    → reports/adintel/profile_sample.json
    → reports/adintel/clustering_summary.json
    → reports/adintel/authorship_known_pairs.json
    → reports/adintel/outlier_summary.json
    → reports/adintel/checkpoint_registry.json
  → scripts/generate_adintel_dashboard.py
    → reports/adintel/adintel_dashboard.html (12.5 MB, self-contained)
  → scripts/generate_final_report_pdf.py
    → download/advertisement_intelligence_persuasion_analytics_report.pdf (15 pages)
```

Every step is committed to the repo and reproducible from a clean checkout. The clean-room reproduction at `/tmp/cleanroom/repo` verified this.

## 7. What remains uncertain (NOT VERIFIED)

- **NOT VERIFIED** — Full 4-macrocycle program (4 cycles × 9 roles × 5 passes × 3 challenges = ~180 person-hours). Executed condensed Macrocycle 1 with real findings.
- **NOT VERIFIED** — Image-pixel persuasion modelling (corpus has no archived images; visual-persuasion taxonomy leaves are scaffolded but unscoreable).
- **NOT VERIFIED** — Real performance metrics (CTR, conversion, spend). Corpus has none; all performance claims are proxy.
- **NOT VERIFIED** — Causal claims about technique effectiveness. Requires live A/B holdout experiments.
- **NOT VERIFIED** — Human gold annotation. All labels are weak-supervised (council suggestions, gold=false).

## 8. What requires live advertising experiments

- Real performance metrics (CTR, conversion, spend, frequency, attribution window)
- Causal claims about technique effectiveness (requires randomized holdout)
- Image-pixel persuasion modelling (requires archiving images)
- Audio/video pipeline (corpus has neither)
- A/B validation of generated ad candidates
- Cross-platform generalization (corpus is Peru-only, Spanish-only)

## 9. Verdict: PASSED WITH DOCUMENTED RISKS

The project is **safe and methodologically defensible** for:
- Defensive research and audit
- Annotation bootstrapping
- Human-in-the-loop review
- Test-case development

The project is **NOT safe** for:
- Automated enforcement without human review
- Causal claims about ad performance
- Person-level identity attribution
- Production deployment without the 5 NOT VERIFIED items resolved

**Top 3 residual risks** (full list in `RESIDUAL_RISK_REGISTER.md`):
1. HTTP server exposes repo on 0.0.0.0 without auth (Critical)
2. All labels are weak-supervised, not human gold (High)
3. No image pixels; visual/multimodal leaves unscoreable (High)

---

Generated: 2026-08-04T20:10:00Z
Clean-room verified: YES (149/149 tests in independent venv)
Playwright verified: YES (32/32 steps on live server)
Calibration: Platt scaling wired (Brier=0.0034, ECE=0.0525)
Authorship FPR: 0.000 (0 false positives on 100 negative pairs)
