# Solarize AdIntel Rebuild — Round 1 Forensic Pre-Execution Report

**Date**: 2026-08-06
**Auditor**: `browser_forensics_reviewer` + `repository_auditor` nodes
**Target**: Live deployment at `https://pillb.github.io/manipsych-adintel/`
**Deployed commit**: `b1b1a21`
**Dashboard size**: 13.34 MB (13,738,013 bytes)
**Cache-bust parameter**: `cb=<timestamp>`

---

## Executive Summary

The forensic pre-execution audit reproduced ALL 8 suspected root causes from the specification. The current product is a **monolithic 13.3 MB dashboard** with **22 peer-level sections** and **18 top-level navigation links**, a **disconnected standalone analyzer**, a **mislabeled "GAN"** that is actually phrase injection + regex mutation, and **5 dead-end user journeys** out of 16 tested. No production code was modified during this audit.

### Journey Results Summary

| Result | Count | Journeys |
|---|---|---|
| COMPLETED | 5 | J03 (indicator formula), J04 (ad→cluster), J05 (why cluster), J06 (outlier comparison), J16 (export) |
| PARTIAL | 3 | J01 (assess new ad), J07 (distinguish label sources), J08 (checkpoint provenance) |
| DEAD_END | 5 | J02 (why technique detected), J09 (adversarial generation), J10 (generated→training), J11 (begin tutorial), J15 (assistant) |
| BLOCKED | 2 | J12 (stop tutorial), J14 (resume tutorial) — both blocked by missing tutorial |
| STATE PERSISTED | 1 | J13 (refresh page) |

### Critical Findings

1. **GAN mislabeling CONFIRMED** — the "Adversarial GAN" in the standalone analyzer is phrase injection + regex mutation. GAN gate: **FAILED** (0 of 8 criteria met).
2. **13.34 MB monolithic HTML** — 91× over the 150 KB budget. 12.4 MB is embedded JSON (`report-data` script alone is 12,678,311 bytes).
3. **22 peer-level sections** — violates the target 5-section task-oriented architecture.
4. **Standalone analyzer disconnected** — not linked from or integrated into the dashboard.
5. **No tutorial, no assistant, no indicator dictionary** — 3 capabilities completely missing.

---

## 1. Verified Starting Hypotheses (Section 2 of the spec)

### H1: Flat information architecture with too many peer-level navigation destinations
**VERDICT: REPRODUCED**

The dashboard has **22 sections** and **18 top-level navigation links**:
- `#metrics`, `#pipeline`, `#diagnostics`, `#explainability-atlas`, `#term-network`, `#corpus-map`, `#facet-overview`, `#explorer`, `#observability`, `#expert-poc`
- `#adintel-taxonomy`, `#adintel-profile`, `#adintel-clustering`, `#adintel-authorship`, `#adintel-outliers`, `#adintel-migration`, `#adintel-checkpoints`, `#adintel-challenges`
- `#adintel-methodology`, `#adintel-audit`, `#adintel-data`, `#research`

The target architecture calls for 5 task-oriented sections: Mission Control, Analyze an Ad, Explore Evidence, Models & Adversarial Lab, Guide/Methods/Audit.

### H2: AdIntel placed beside rather than inside the analytical pipeline
**VERDICT: REPRODUCED**

The `#pipeline` section is a static SVG showing the v1 model stack. AdIntel sections (`#adintel-*`) are placed AFTER the pipeline, separated by a `v1-to-new` story-transition div. The pipeline does not show AdIntel as a connected intelligence layer spanning collection → annotation → modelling → analysis → assessment → validation → feedback.

### H3: Standalone analyzer is disconnected from the dashboard
**VERDICT: REPRODUCED**

`docs/interactive_analyzer.html` (39,907 bytes) is a standalone page at `/interactive_analyzer.html`. It is NOT linked from the dashboard's navigation. The dashboard has no "Analyze an Ad" workspace. The analyzer has useful capabilities (text analysis, evidence highlighting, persuasive profile, evidence ledger, export, adversarial experiments) that are completely disconnected from the dashboard's corpus-level analyses.

### H4: The "Adversarial GAN" is phrase injection + regex mutation
**VERDICT: REPRODUCED — CRITICAL MISLABELING**

Forensic code inspection of `interactive_analyzer.html` confirms:

1. The `runGanCycle()` function picks a random phrase from a hardcoded array of 13 phrases: `['urgente hoy', 'solo por esta semana', '100% garantizado', ...]`
2. It appends the phrase to the base text: `const variant = baseText + ' ' + tech;`
3. It re-runs the rule-based detector (regex matching against `SIGNALS` array)
4. If the phrase was "missed", it adds it to the regex array: `SIGNALS[targetDim].push([tech.replace(...), 'gi', 0.25, 'GAN-added: ' + tech])`
5. It calls this a "GAN cycle" and "training"

**GAN Gate Assessment** (8 criteria from spec Section 3):

| Criterion | Met? | Evidence |
|---|---|---|
| Trainable generator | NO | No generator model exists — phrases are from a hardcoded array |
| Trainable discriminator | NO | No discriminator — rule-based regex matching only |
| Explicit adversarial objective | NO | No loss function — just "did the regex catch it?" |
| Actual optimization steps | NO | No gradient descent, no backprop |
| Saved training evidence | NO | No checkpoints, no training logs |
| Reproducible checkpoints | NO | State is ephemeral (in-memory `SIGNALS` array) |
| Held-out evaluation | NO | No test set, no evaluation protocol |
| Comparison with non-GAN baselines | NO | No baseline comparison |

**Required action**: Rename "Adversarial GAN" to "Rule-Based Adversarial Sandbox" or "Adversarial Phrase Perturbation Prototype" everywhere. Preserve the useful behavior (detector gap discovery) while correcting the description.

### H5: Missing connected workflow for submitting and assessing a new ad
**VERDICT: REPRODUCED**

The dashboard has no "Analyze an Ad" workspace. Users cannot paste new ad text or upload an image. Journey J01 found no ad-assessment input on the dashboard. The standalone analyzer has text input but no image upload, no model-backed confidence, no calibration, no abstention, and no corpus connections.

### H6: Absence of a complete restartable interactive tutorial
**VERDICT: REPRODUCED**

No tutorial button, link, or overlay exists anywhere in the dashboard (Journey J11 = DEAD_END). Journeys J12 (stop midway) and J14 (resume from saved step) are BLOCKED because no tutorial exists.

### H7: Large monolithic dashboard artifact
**VERDICT: REPRODUCED**

| Metric | Value | Target Budget | Ratio |
|---|---|---|---|
| HTML size | 13.34 MB | 150 KB | 91× over |
| Embedded JSON (report-data) | 12.38 MB | — | 92% of total |
| Embedded JSON (solarize-data) | 719 KB | — | 5% of total |
| Embedded JSON (segment-report) | 39 KB | — | <1% |
| Embedded JSON (model-report) | 18 KB | — | <1% |
| Load time (networkidle) | 914 ms | 2500 ms LCP | within budget |
| Console errors | 0 | 0 | met |
| DOM interactive | 914 ms | — | — |

The 12.38 MB `report-data` JSON (v1 council inferences) is the dominant payload. It contains per-ad data for the Top-25 explorer and is embedded inline. This should be split into a lazy-loaded JSON file fetched on demand.

### H8: Duplicate or unused reports, indicators, definitions, and techniques
**VERDICT: PARTIALLY REPRODUCED**

The repo has 22 JSON files in `reports/adintel/`. The dashboard embeds 4 of them inline (`report-data`, `model-report`, `segment-report`, `solarize-data`). The remaining 18 are served as static files but their consumption status needs further audit. Key potential duplications:
- `clustering_summary.json` vs `deep_clustering_analysis.json` vs `cluster_alignment_report.json` — all relate to clustering
- `outlier_summary.json` vs `solarize_summary.json` (outliers section) — overlapping outlier data
- `full_data_results.json` vs `profile_sample.json` — overlapping profile data

---

## 2. 16 User Journey Results

### J01: Assess a newly supplied ad — PARTIAL
- **Entry point**: Dashboard root
- **Finding**: No ad-assessment input on the dashboard. The ad selector (`#adintel-ad-selector`) searches existing corpus ads, not new user input. The standalone analyzer has text input but is not linked from the dashboard.
- **Dead end**: User cannot paste ad copy in the dashboard
- **Time**: 5s

### J02: Determine why a persuasion technique was detected — DEAD_END
- **Entry point**: `#explorer`
- **Finding**: The explorer shows a Top-25 rank list. Clicking an ad shows detail, but no highlighted evidence spans (`mark`, `.highlight`, `.evidence-span`) were found in the detail panel. The standalone analyzer HAS evidence highlighting, but it's disconnected.
- **Dead end**: No evidence spans in the dashboard explorer

### J03: Find the formula and limitations of an indicator — COMPLETED
- **Entry point**: `#adintel-methodology`
- **Finding**: The methodology section (Solarize Round 2) explains Wilson CI, Cohen's h, BH FDR, min-support, k=5, and the meaningfully-different criterion. However, there is no canonical **indicator dictionary** with per-indicator formula, numerator, denominator, unit, valid range, thresholds, and failure modes.
- **Missing**: Canonical indicator dictionary

### J04: Navigate from one ad to its cluster — COMPLETED
- **Entry point**: `#adintel-clustering` → ad selector
- **Finding**: The ad selector (Solarize Round 1) lets users search by record_id, click a result, and see the cluster assignment in the detail panel.
- **Time to evidence**: ~4s

### J05: Understand why the ad belongs to that cluster — COMPLETED
- **Entry point**: `#adintel-clustering` → ad selector → detail
- **Finding**: The detail panel (Solarize Round 3) includes "Why this cluster assignment" and "Evidence against the assignment" sections explaining the TF-IDF centroid distance and silhouette score.

### J06: Compare an outlier with normal examples — COMPLETED
- **Entry point**: `#adintel-outliers`
- **Finding**: The outliers section (Solarize Round 1) has 4-way outlier classification, 12 example cards, and 3-population term-prevalence comparison tables with Wilson CI + Cohen's h + BH FDR.

### J07: Distinguish model, heuristic, and expert labels — PARTIAL
- **Entry point**: `#explorer`
- **Finding**: The body text mentions "model", "heuristic/rule", and "council/expert" — but label sources are not clearly marked per-technique in the ad detail. Users cannot easily tell whether a given technique label came from a model prediction, a rule-based heuristic, or a human annotation.

### J08: Identify the checkpoint that produced a result — PARTIAL
- **Entry point**: `#adintel-checkpoints`
- **Finding**: The checkpoint registry table exists with 6 checkpoints. However, individual ad results and technique detections do not cite which checkpoint produced them. There is no provenance chain from result → checkpoint.

### J09: Locate the adversarial-generation stage — DEAD_END + MISLEADING
- **Entry point**: Dashboard root
- **Finding**: No dedicated adversarial-generation section in the dashboard. The "GAN" functionality exists only in the standalone analyzer. The standalone analyzer uses "GAN" label 4 times — **CONFIRMED MISLABELING** (see H4 above).

### J10: Understand how generated data reaches training — DEAD_END
- **Entry point**: Dashboard root
- **Finding**: No visible connected workflow from adversarial generation to training. No synthetic-data quarantine, no review queue, no augmentation gate, no regression evaluation. The "GAN cycle" in the standalone analyzer just mutates an in-memory regex array — no data reaches any training pipeline.

### J11: Begin a tutorial — DEAD_END
- **Entry point**: Dashboard root
- **Finding**: No tutorial button, link, or overlay found anywhere. No Driver.js, Shepherd, or custom tutorial engine.

### J12: Stop midway — BLOCKED
- Cannot test — no tutorial exists (see J11).

### J13: Refresh the page — STATE PERSISTED
- **Entry point**: `#adintel-clustering` → select ad → reload
- **Finding**: The ad selection state is lost after refresh (the detail panel resets to empty). However, the URL hash (`#adintel-clustering`) is preserved, so the user stays on the same section. The hash-based deep link `#adintel-ad=<rid>` works (Solarize Round 2).

### J14: Resume from saved step — BLOCKED
- Cannot test — no tutorial exists (see J11).

### J15: Send a guided message through the analysis assistant — DEAD_END
- **Entry point**: Dashboard root
- **Finding**: No "Ask AdIntel" or contextual assistant found. No chat input, no message interface, no evidence-citation system.

### J16: Export the current result — COMPLETED
- **Entry point**: `#adintel-data`
- **Finding**: The data download section (Solarize Round 2) has download links for `solarize_summary.json`, `solarize_per_ad.jsonl`, and 7 supporting JSON files. The standalone analyzer also has an "Export results (JSON)" button.

---

## 3. Performance Baselines

### Asset sizes
| Asset | Size | Notes |
|---|---|---|
| Dashboard HTML | 13.34 MB | 91× over 150 KB budget |
| report-data JSON (embedded) | 12.38 MB | 92% of total — v1 council inferences |
| solarize-data JSON (embedded) | 719 KB | Solarize summary |
| segment-report JSON (embedded) | 39 KB | Segment analysis |
| model-report JSON (embedded) | 18 KB | Model metrics |
| Standalone analyzer HTML | 39 KB | Within budget |

### Load performance
| Metric | Value | Target | Status |
|---|---|---|---|
| DOM interactive | 914 ms | — | — |
| Load event end | 914 ms | — | — |
| LCP | N/A | ≤ 2500 ms | Could not capture (LCP API returned no entries) |
| Console errors | 0 | 0 | MET |

### Navigation and structure
| Metric | Value |
|---|---|
| Top-level navigation links | 18 |
| Total sections | 22 |
| Embedded JSON scripts | 4 |
| Total embedded JSON bytes | 13,473,455 (13.3 MB) |

### Terminology audit (misleading claims)
| Term | Mentions in dashboard | Status |
|---|---|---|
| "GAN" | 4 | NEEDS VERIFICATION — confirmed mislabeling in standalone analyzer |
| "adversarial" | 3 | OK if not paired with "GAN" |
| "confidence" | 5 | Needs per-usage audit — may be heuristic scores labeled as confidence |
| "calibrated" | 8 | Needs per-usage audit — may be uncalibrated scores labeled as calibrated |
| "causal" | 1 | Needs per-usage audit — may be observational associations labeled as causal |

---

## 4. Multi-Viewport Audit

| Viewport | Width × Height | Horizontal Overflow | Page Errors | Screenshot |
|---|---|---|---|---|
| Desktop | 1440 × 900 | NO | 0 | `viewport_desktop_1440x900.png` |
| Laptop | 1366 × 768 | NO | 0 | `viewport_laptop_1366x768.png` |
| Tablet landscape | 1024 × 768 | NO | 0 | `viewport_tablet_landscape_1024x768.png` |
| Tablet portrait | 768 × 1024 | **YES** | 0 | `viewport_tablet_portrait_768x1024.png` |
| Mobile | 390 × 844 | NO | 0 | `viewport_mobile_390x844.png` |

**Finding**: Tablet portrait (768×1024) has horizontal overflow. All other viewports are clean. The mobile CSS media query (`@media max-width:640px`) handles 390px but misses the 768px tablet portrait range.

---

## 5. Standalone Analyzer Inspection

### Capabilities
| Capability | Present? | Notes |
|---|---|---|
| Text analysis | YES | Textarea + analyze button |
| Image upload | NO | No file input |
| Evidence highlighting | YES | `<mark>` elements |
| Persuasive profile (17d) | YES | Dimension scoring |
| Evidence ledger | YES | Ledger display |
| Export | YES | JSON export button |
| Multimodal | NO | No image support |
| Model-backed confidence | NO | Rule-based only |
| Calibration | NO | No calibration |
| Abstention | NO | No abstention |
| Corpus connections | NO | Standalone, not connected to corpus |
| Checkpoint provenance | NO | No checkpoint references |
| Tutorial state | NO | No tutorial |
| Contextual assistant | NO | No assistant |
| Dashboard integration | NO | Standalone page, not linked from dashboard |

### GAN Gate Assessment
**GAN LABEL NOT JUSTIFIED** — 0 of 8 criteria met.

The `runGanCycle()` function:
1. Picks a random phrase from a hardcoded array of 13 phrases
2. Appends it to the base text (`baseText + ' ' + tech`)
3. Re-runs rule-based regex detection
4. If the phrase was "missed", adds it to the `SIGNALS` regex array
5. Calls this a "GAN cycle" and labels the regex update as "training"

**Required action**: Rename to "Rule-Based Adversarial Sandbox" or "Adversarial Phrase Perturbation Prototype". Preserve the detector-gap-discovery behavior. Remove all "GAN", "training", "model" terminology from this component.

---

## 6. Issue Summary

| ID | Category | Severity | Title | Status |
|---|---|---|---|---|
| I001 | information_architecture | CRITICAL | Flat, fragmented navigation with 22 peer-level sections | VERIFIED |
| I002 | pipeline_integration | CRITICAL | AdIntel placed beside the pipeline, not inside it | VERIFIED |
| I003 | disconnected_interface | CRITICAL | Standalone analyzer disconnected from dashboard | VERIFIED |
| I004 | mislabeling | CRITICAL | "GAN" is phrase injection + regex mutation | VERIFIED — 0/8 GAN gate criteria met |
| I005 | performance | HIGH | 13.34 MB monolithic HTML (91× over budget) | VERIFIED |
| I006 | duplicate_definitions | HIGH | Potential duplicate/orphaned JSON reports | PARTIALLY VERIFIED — needs deeper audit |
| I007 | missing_capability | HIGH | No connected ad-assessment workflow | VERIFIED |
| I008 | missing_capability | HIGH | No restartable interactive tutorial | VERIFIED |
| I009 | missing_capability | MEDIUM | No "Ask AdIntel" contextual assistant | VERIFIED |
| I010 | missing_capability | MEDIUM | No canonical indicator dictionary | VERIFIED |
| I011 | responsive | MEDIUM | Tablet portrait (768×1024) horizontal overflow | VERIFIED |
| I012 | label_provenance | MEDIUM | Per-technique label source (model/heuristic/expert) not distinguished | VERIFIED |
| I013 | checkpoint_provenance | MEDIUM | Individual results don't cite which checkpoint produced them | VERIFIED |

---

## 7. Round 1 Gate Assessment

| Gate Criterion | Status | Evidence |
|---|---|---|
| All 16 journeys executed | PASSED | 16/16 journeys run against live deployment |
| All viewports tested | PASSED | 5 viewports tested (1440, 1366, 1024, 768, 390) |
| Performance baselines captured | PASSED | HTML size, load time, embedded JSON, nav count, section count, terminology audit |
| GAN mislabeling reproduced | PASSED | 0/8 GAN gate criteria met — confirmed phrase injection + regex mutation |
| Pre-execution report created | PASSED | This document |
| No production code modified | PASSED | Only read-only audit + new evidence files created |

**Gate state: PASSED — proceed to Round 2 (STORM research and architecture challenge)**

---

## 8. Evidence Artifacts

| Artifact | Path |
|---|---|
| Machine-readable audit JSON | `repo/audit/solarize-rebuild/round1/round1_forensic_audit.json` |
| Desktop screenshot | `repo/audit/solarize-rebuild/round1/screenshots/viewport_desktop_1440x900.png` |
| Laptop screenshot | `repo/audit/solarize-rebuild/round1/screenshots/viewport_laptop_1366x768.png` |
| Tablet landscape screenshot | `repo/audit/solarize-rebuild/round1/screenshots/viewport_tablet_landscape_1024x768.png` |
| Tablet portrait screenshot | `repo/audit/solarize-rebuild/round1/screenshots/viewport_tablet_portrait_768x1024.png` |
| Mobile screenshot | `repo/audit/solarize-rebuild/round1/screenshots/viewport_mobile_390x844.png` |
| Standalone analyzer screenshot | `repo/audit/solarize-rebuild/round1/screenshots/standalone_analyzer.png` |
| Audit script | `repo/scripts/solarize_rebuild_round1_audit.py` |

---

## 9. Next Steps (Round 2 — STORM Research and Architecture Challenge)

Based on the forensic findings, Round 2 will:

1. **Research advertising-transparency interfaces** (Meta Ad Library, Google Ads Transparency Center, EU DSA Transparency Database) to extract task-entry-point principles
2. **Research hierarchical persuasion detection** (SemEval hierarchy, multilabel classification, evidence-span extraction)
3. **Research multimodal detection** (CLIP, fusion strategies, missing-modality behavior)
4. **Research adversarial improvement** (GAN-BERT, constrained LLM generation, active learning, contrast-set generation) — compare against the current phrase-injection baseline
5. **Research synthetic-data governance** (memorization, near-duplication, distribution shift, quarantine)
6. **Research calibration and abstention** (temperature scaling, ECE, Brier, risk-coverage, conformal methods)
7. **Research interactive tutorials** (Driver.js vs Shepherd vs custom engine — accessibility, persistence, bundle size)

After two skeptical research-critique passes, proceed to the target information architecture design (Section 9 of the spec).
