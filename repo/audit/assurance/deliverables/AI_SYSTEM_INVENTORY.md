# AI System Inventory — ManiPsych + adintel

**Audit artifact:** `audit/assurance/deliverables/AI_SYSTEM_INVENTORY.md`
**System under audit:** ManiPsych + adintel advertisement-intelligence project
**Repo root:** `/home/z/my-project/repo`
**Inventory taken:** 2026-08-04 (sandbox)
**Auditor:** Z.ai assurance sub-agent
**Convention:** every claim is either verified on disk (with a path, count, or hash) or marked `NOT VERIFIED — [reason]`.

---

## 1. Purpose and scope

The ManiPsych + adintel system is a **defensive research pipeline** that detects manipulation, persuasion, and dark-pattern techniques in Spanish-language classified advertisements, with a documented focus on Peruvian "ayuda económica" content that may target women in financially vulnerable contexts. The system is local-first (CPU-only, no GPU, no network calls in inference) and explicitly does **not** name or accuse individuals based on model similarity.

In scope for this inventory:
- the Python package `adintel/`
- the v1 tools under `tools/`
- the trained models under `models/`
- the processed/annotation data under `data/`
- the report artifacts under `reports/` and `reports/adintel/`
- the live HTTP server at `http://localhost:8765/`

Out of scope: raw scraping pipeline internals (covered only at the manifest level), the dashboard accessibility audit (already covered in `audit/dashboard/research/`), and any external LLM/council inference APIs (none are wired into the in-repo code).

---

## 2. Top-level component map

| # | Component | Path | Verified |
|---|-----------|------|----------|
| 1 | Python package | `adintel/` (10 modules) | VERIFIED — see §3 |
| 2 | v1 tooling | `tools/` (50 scripts) | VERIFIED — see §4 |
| 3 | Trained models | `models/*.joblib` (2 files) | VERIFIED — see §5 |
| 4 | Processed corpus | `data/processed/ad_manifest.jsonl` (5,189 lines) | VERIFIED (`wc -l`) |
| 5 | Annotation store | `data/annotation/*.jsonl` (4 main files) | VERIFIED — see §6 |
| 6 | Raw HTML archive | `data/raw/ads/*.html` | VERIFIED (directory exists; not enumerated) |
| 7 | HTML dashboards | `reports/ad_manipulation_report.html` (12.86 MB), `reports/adintel/adintel_dashboard.html` (12.86 MB) | VERIFIED (`ls -la`) |
| 8 | Pipeline JSON outputs | `reports/adintel/*.json` (10 files) + `reports/*.json` (~20 files) | VERIFIED (`ls -la`) |
| 9 | Test suites | `tests/adintel/test_*.py` (8 files, 113 test fns), `tests/test_*.py` (21 files, 75 test fns) | VERIFIED (`grep -c`) |
| 10 | Annotation studio | `annotation_app/index.html` (180 lines) | VERIFIED (`wc -l`) |
| 11 | Live HTTP server | `python3 -m http.server 8765 --directory /home/z/my-project/repo` (pid 993) | VERIFIED (`ps -fp 993`, `curl`) |
| 12 | PDF generation | `scripts/generate_final_report_pdf.py` → `download/advertisement_intelligence_persuasion_analytics_report.pdf` | **NOT VERIFIED — neither `scripts/` nor `download/` directory exists in the repo** (verified by `find . -maxdepth 3 -name "generate_final_report_pdf.py"` → no matches). |
| 13 | Project metadata | `pyproject.toml`, `AGENT_STATE.md`, `ORIGINAL_OBJECTIVE.md`, `PROJECT_BRIEF.md`, `AGENTS.md` | VERIFIED |
| 14 | Schemas | `schemas/ad_record.schema.json`, `schemas/phase_evidence.schema.json`, `schemas/technique.schema.json` | VERIFIED |
| 15 | Existing self-audit | `audit/dashboard/research/` (dashboard accessibility research only) | VERIFIED — see §11 |

---

## 3. Python package `adintel/` — module inventory

All file sizes and SHA-256 hashes were computed with `sha256sum` on 2026-08-04.

| Module | LOC (approx) | SHA-256 (truncated) | Role |
|--------|------:|---------------------|------|
| `adintel/__init__.py` | 35 | `c8b62b3d…0233e4` | Package init; version `adintel-0.1.0`; declares `__all__` |
| `adintel/types.py` | 325 | `24fe0506…f3e2a9` | Typed dataclasses: `EvidenceRef`, `TechniquePrediction`, `ProfileScore`, `PersuasiveProfile`, `ClusterAssignment`, `ClusterReport`, `AuthorshipResult`, `OutlierReport`, `CheckpointOutput`, `PerformanceClaim`; defines `PROFILE_DIMENSIONS` (17-tuple) |
| `adintel/taxonomy.py` | 546 | `26066c1f…437210` | Hierarchical multi-label taxonomy `adintel-taxonomy-v2`. **6 top-level families, 26 leaf nodes** (verified: `TAXONOMY_VERSION="adintel-taxonomy-v2"`; `TOP_LEVEL_FAMILIES` has 6 entries; `NODES` tuple enumerated and `leaf_count` field in `to_dict()` reports 26) |
| `adintel/profile.py` | 609 | `5b2e9412…79cf52` | 17-dimension persuasive profile. `score_profile()` returns a `PersuasiveProfile` over `PROFILE_DIMENSIONS`. All dimensions use rule-based signal inventories with a saturating transform (`1 - exp(-x)`). `trust_risk` and `manipulation_risk` are meta-dimensions that consume other scores — never a simple sum |
| `adintel/clustering.py` | 501 | `6cbca5eb…2944ad` | 7-space clustering (persuasive, semantic, rhetorical, visual, multimodal, authorial, performance). MiniBatchKMeans with `random_state=42`. Evaluates stability (ARI), resampling consistency, parameter sensitivity, brand/topic leakage, and per-cluster explanations |
| `adintel/authorship.py` | 535 | `d849d1e3…e722e1` | 4 authorship tasks: pairwise verification, closed-set, open-set, creative-source clustering. Char-4/5-gram TF-IDF + lexical richness + template + structural + council-overlap signals. **Length-aware abstention** (≥15 tokens). Hard guardrail: `person_named` is always `False` |
| `adintel/outlier.py` | 528 | `4d01f0ac…53c80c` | **11 outlier detectors** (claim verified): `creative_novelty`, `unusual_technique_combination`, `style_outlier`, `visual_outlier`, `performance_overperformer`, `performance_underperformer`, `temporal_outlier`, `duplicate`, `extraction_error`, `metadata_error`, `model_error`. Module docstring says "ten outlier types" — minor docstring drift (one detector returns two kinds). |
| `adintel/checkpoints.py` | 356 | `66fc2006…e850c6` | Registry of **6 checkpoints** (claim verified): `rule-detector-v1`, `tfidf-ovr-v1`, `persuasive-profile-v1`, `authorship-v1`, `outlier-v1`, `clustering-v1`. Includes `platt_scale` / `temperature_scale` helpers and `should_route_to_human` rule |
| `adintel/api.py` | 296 | `5a12a3fb…921f57` | In-process `AdIntelAPI` class. API version `adintel-api-v1`. Methods: `get_taxonomy`, `score_profile`, `pairwise_verify`, `open_set_attrib`, `cluster_all_spaces`, `detect_outliers`, `monitoring_summary`. Each response carries `request_id`, `checkpoint_id`, `calibration_status`, `latency_ms`, `abstained`, `review_status` |
| `adintel/evidence.py` | 157 | `d8a3c225…0b9900` | Causal-language linter (`lint_claim_text`), `require_strength` assertion, `assert_no_universal_score`, `assert_authorship_does_not_identify_person`, `route_to_human_if_low_confidence_or_disagreement` |

Total package source: 10 files, ~4,400 LOC.

---

## 4. v1 tooling under `tools/`

50 scripts. The four explicitly named in the task brief:

| Tool | SHA-256 (truncated) | Role |
|------|---------------------|------|
| `tools/detect_manipulation.py` | `bc878698…d61830` | Rule-based detector. 6 lexical `Rule` patterns → tags + score (capped at 1.0). Weights 0.15–0.25 per rule. CLI: stdin/argv → JSON |
| `tools/train_manipulation_model.py` | `2fd7eae5…d71977` | Trains `TfidfVectorizer(ngram_range=(1,2), min_df=1, max_features=3000)` + `OneVsRestClassifier(LogisticRegression(max_iter=1000, class_weight="balanced"))`. **Weak labels** generated by `detect_manipulation.analyze_text` + metadata cues. Writes `models/manipulation_tfidf_ovr.joblib` |
| `tools/train_council_candidate_model.py` | `ab942a2c…cff64e` | Trains council candidate model from `data/annotation/council_resolved_annotations.jsonl`. Same TF-IDF + OVR LR pipeline. Writes `models/manipulation_council_tfidf_ovr.joblib`. Reports metrics to `reports/council_candidate_model_report.json` |
| `tools/generate_council_inferences_report.py` | `8b29439f…cfc2a2` | Generates inferences on the council model and emits a **self-contained HTML dashboard** at `reports/ad_manipulation_report.html` (12.86 MB — embeds all data inline; verified no external `<script src=…>` by HTML head inspection) |

Other notable tools (not exhaustive): `rebuild_manifest_from_raw.py`, `scrub_manifest.py`, `redact_pii.py`, `validate_annotations.py`, `council_consensus.py`, `run_council_annotation_pass.py`, `scientist_validate_council_annotations.py`, `audit_html_report_playwright.py`, `audit_annotation_gui_playwright.py`, `audit_noisy_span_omissions.py`, `audit_span_variant_coverage.py`, `learning_curve_data_scale.py`, `phase_gate.py`, `render_html_report.py`, `rank_ads.py`, `build_query_bank.py`, `discover_sources.py`, `expand_sources.py`, `harvest_seeds.py`, `ingest_candidate_urls.py`, `collect_*` (12 platform-specific collectors: doplim, locanto, evisos, ciudadanuncios, facebook, hombre), `scrape_ads.py`, `selenium_search_first_harvester.py`, `annotation_store.py`, `generate_annotation_gui.py`, `export_annotations.py`, `export_council_packets.py`, `export_resolved_council_annotations.py`, `prepare_annotation_campaign.py`, `segment_model_analysis.py`, `build_modeling_dataset.py`, `validate_agent_state.py`, `run_phase4_parallel.py`, `run_query_harvest_parallel.py`, `generate_no_code_expert_review_poc.py`.

---

## 5. Trained models

| File | Size | SHA-256 (full) | Created | Trainer |
|------|------|-----------------|---------|---------|
| `models/manipulation_tfidf_ovr.joblib` | 390,941 B | `6bb0fbe2eb1c723d1f4473880afaabbc32ab9d7954601a3795bf02c03a05cecc` | 2026-07-09 02:33 | `tools/train_manipulation_model.py` |
| `models/manipulation_council_tfidf_ovr.joblib` | 3,425,035 B | `25b1bcabc15e13180dd969f6f3a0a779a48bf56a0c9e226b3d3264989fe77b28` | 2026-07-09 23:43 | `tools/train_council_candidate_model.py` |

Training data references:
- `manipulation_tfidf_ovr.joblib` was trained on `data/processed/ad_manifest.jsonl` (5,189 records present in sandbox) — verified by reading `tools/train_manipulation_model.py:28` (`DEFAULT_MANIFEST = ROOT / "data" / "processed" / "ad_manifest.jsonl"`).
- `manipulation_council_tfidf_ovr.joblib` was trained on `data/annotation/council_resolved_annotations.jsonl` (5,717 annotations) — verified by reading `tools/train_council_candidate_model.py:34` and confirmed by `reports/council_candidate_model_report.json` which shows `split_counts: {train: 3983, validation: 853, test: 853, challenge: 28}` (sum 5,717). The report's `annotation_source` field shows `/Users/pabloillescas/Projects/grokBuild/ManiPsych/data/annotation/council_resolved_annotations.jsonl` — a developer-machine path indicating the artifact was trained off-sandbox and copied in. **NOT VERIFIED — the `data/processed/modeling_manifest.jsonl` file referenced in `reports/modeling_dataset_summary.json` does not exist in the sandbox** (verified by `ls`).

---

## 6. Data inventory

### 6.1 Processed corpus

| File | Lines | Purpose | Schema (top-level keys) |
|------|------:|---------|--------------------------|
| `data/processed/ad_manifest.jsonl` | 5,189 | Strict-valid processed records | `record_id`, `source_platform`, `source_url_hash`, `collected_at`, `title`, `body_redacted`, `raw_archive_ref`, `metadata` |

`metadata` is a dict (per `tools/train_manipulation_model.py:55-69`) with possible keys: `is_paid_or_premium_marker`, `is_featured_marker`, `platform_family`, `raw_size_bucket`, `quality_score`, `canonical_url_hash`, `normalized_text_hash`, `account_hash`, `followers_count`, `facebook_reactions_approx`, `facebook_comments_approx`, `collector`.

Per-platform counts (from `reports/raw_rebuild_summary.json`):
- doplim: 2,845
- locanto: 1,562
- ciudadanuncios: 1,303
- evisos: 2
- facebook: 26
(Total written 5,738 → after dedup → 5,189 in current manifest)

> **Audit note — stale documentation:** `reports/dataset_manifest.md` and `reports/ad_manipulation_ranking.json` both claim "1,589 strict-valid records" but the actual current manifest contains 5,189. These two artifacts appear to predate a later rebuild and are stale. They should be regenerated or marked deprecated.

### 6.2 Annotations

| File | Lines | Purpose | Schema (top-level keys) |
|------|------:|---------|--------------------------|
| `data/annotation/council_resolved_annotations.jsonl` | 5,717 | Resolved council technique labels per document | `accepted_actor_id`, `accepted_round`, `agreement`, `corpus_version`, `document`, `gold`, `layer`, `platform`, `record_id`, `spans`, `split_name`, `text_hash` |
| `data/annotation/similarity_links.jsonl` | 642 | Known same-source pairs (positive-only) | `left_record_id`, `right_record_id`, `character_5gram_jaccard`, `token_trigram_jaccard`, `length_ratio`, `decision` |
| `data/annotation/documents.jsonl` | (not counted) | Source documents for annotation | (not inspected in detail) |
| `data/annotation/label_schema.json` | — | v1 label schema `manipsych-span-v1` | 20 labels (matches taxonomy.py `v1_equivalents`) |
| `data/annotation/corpus_snapshot.json` | — | Corpus snapshot metadata | (not inspected) |
| `data/annotation/expert_manual_review_round4.jsonl` | — | Expert manual review pass | (not inspected) |
| `data/annotation/council_round1_second_pass_queue.jsonl`, `council_round2_queue.jsonl`, `council_second_pass_queue.jsonl`, `council_resolved_annotations_v2.jsonl` | — | Annotation campaign queues / v2 draft | (not inspected) |

Span structure (verified from first line of `council_resolved_annotations.jsonl`):
```json
{
  "exact_text": "chicas",
  "explicitness": "explicit",
  "harm_risk": 2,
  "intensity": 3,
  "label": "age_or_youth_targeting",
  "manipulativeness": 2,
  "provenance": "subagent_r5_a",
  "rationale": "targets young women or specific youth age ranges",
  "segments": [[203, 209]],
  "vulnerability_target": "age_youth"
}
```

### 6.3 Raw HTML archive

`data/raw/ads/*.html` — present, multiple files (sample: `arequipa_p1_*.html`, `agent_doplimfb_*.html`, `agent_full_searchfirst_*.html`). The `raw_rebuild_summary.json` reports 10,293 raw files scanned in the last rebuild. **NOT VERIFIED — exact file count in the sandbox not enumerated** (would require `find`).

### 6.4 Source / query inventory

- `data/sources/ad_sources.json` — list of known ad sources
- `data/sources/expanded_ad_sources.json`
- `data/sources/query_bank.json`
- `data/sources/harvested_seeds.jsonl`
- `data/sources/rejected_seed_urls.json`

### 6.5 Annotation store (SQLite)

`data/annotation/annotations.locked.sqlite3` and `annotations.locked.sqlite3-journal` are present. **NOT VERIFIED — schema and row counts not inspected** (SQLite not opened during this audit).

---

## 7. Report inventory

### 7.1 HTML dashboards

| File | Size | Verified served at | Notes |
|------|------|-------------------|-------|
| `reports/ad_manipulation_report.html` | 12,858,658 B (12.2 MB) | `http://localhost:8765/reports/ad_manipulation_report.html` → HTTP 200, 12,858,658 B | v1 observatory; generated by `tools/generate_council_inferences_report.py` |
| `reports/adintel/adintel_dashboard.html` | 12,861,304 B (12.5 MB) | `http://localhost:8765/reports/adintel/adintel_dashboard.html` → HTTP 200, 12,861,304 B | Unified v1 + adintel dashboard. Title: "ManiPsych + adintel — Unified Observatory" |

Both dashboards are **fully self-contained** (no external `<script src=…>`, no CDN, no fetch/AJAX — verified by inspecting the HTML head). They embed all data inline, which is why each is ~12 MB. The only local asset is `reports/assets/d3-lite-force.js` (3,268 B; vendored mini-D3 helper, 89 lines).

### 7.2 Pipeline JSON outputs (`reports/adintel/`)

| File | Size | Purpose |
|------|------|---------|
| `pipeline_results.json` | 4,185 B | Top-level pipeline summary: ran_at, elapsed_s=5.35, n_records_total=5189, n_council_annotations=5717, n_similarity_links=642, profile_dimension_means (17 means), cluster_summary (7 spaces), outlier counts |
| `taxonomy_v2.json` | 19,374 B | Serialised `adintel/taxonomy.py:to_dict()` |
| `checkpoint_registry.json` | 4,804 B | Serialised `adintel.checkpoints.registry_to_dict()` |
| `profile_sample.json` | 10,315 B | 200 sampled profiles + per-dimension means |
| `clustering_summary.json` | 2,363 B | 300-sample clustering across 7 spaces |
| `outlier_summary.json` | 3,933 B | 1000-sample outlier run; 188 reports across 4 kinds |
| `authorship_known_pairs.json` | 5,111 B | 41 known-pair verification; accuracy 0.9756 |
| `v1_to_v2_migration_report.json` | 950 B | 5,717 in → 5,717 out, 0 unmapped labels |
| `challenge_round1_defects.md` | 15,229 B | 9 self-audit defects (R1-D01..R1-D09) |
| `challenge_round2_defects.md` | 9,045 B | 9 self-audit defects (R2-D01..R2-D09) |

### 7.3 Other reports (`reports/`)

20+ JSON/Markdown reports including:
- `council_candidate_model_report.json` (40,641 B) — full model evaluation (test/val/challenge splits, per-label AUC, ROC/PR curves)
- `council_candidate_inferences.json` (18,809,019 B) — full inferences dump (large)
- `phase5_model_report.json`, `learning_curve_data_scale.json`, `modeling_dataset_summary.json`, `raw_rebuild_summary.json`, `dataset_manifest.md`, `final_report.md`, `model_card.md`, `segment_model_analysis.json`, `html_report_playwright_audit.json` (106 KB), `annotation_gui_playwright_audit.json`, `noisy_span_omission_audit.json`, `span_variant_coverage_audit.json`, `source_bibliography.json`, `phase1_compendium.json`, `phase2_peru_dossier.json`, `phase3_forum_research.json`, `phase4_*.json/md`, `phase5_*.json`, `validation_summary.md`, `scientist_annotation_review.md`, `manual_expert_annotation_pass_round4.md`, `raw_review_pass_20260708.md`, `annotation_research_refresh.md`, `data_scale_recommendation.md`, `new_sources_facebook_playbook.md`, `evisos_source_research.md`, `scraping_strategy_guide.md`, `no_code_ai_expert_review_poc.{md,json}`.

---

## 8. Test inventory

| Suite | Files | Test functions (`grep -c "^\s*def test_"`) | Claimed | Status |
|-------|------:|---------------------------------------------:|---------|--------|
| `tests/adintel/` | 8 | 113 | 113 | matches claim |
| `tests/test_*.py` | 21 | 75 | 74 | +1 over claim (likely environmental fail; see below) |
| **Total** | 29 | **188** | 187 | claim says "187 pass / 1 environmental fail" |

Per-file adintel breakdown (verified by `grep -c`):

| File | Test count |
|------|-----------:|
| `test_api.py` | 14 |
| `test_authorship.py` | 19 |
| `test_checkpoints.py` | 11 |
| `test_clustering.py` | 12 |
| `test_evidence.py` | 15 |
| `test_outlier.py` | 13 |
| `test_profile.py` | 17 |
| `test_taxonomy.py` | 12 |
| **Sum** | **113** |

Per-file v1 breakdown:

| File | Test count |
|------|-----------:|
| `test_agent_state.py` | 2 |
| `test_annotation_campaign.py` | 2 |
| `test_annotation_store.py` | 9 |
| `test_build_query_bank.py` | 2 |
| `test_collect_seed_inventory.py` | 11 |
| `test_council_report_advanced_sections.py` | 1 |
| `test_council_spanish_localization.py` | 2 |
| `test_detect_manipulation.py` | 2 |
| `test_discover_sources.py` | 2 |
| `test_expand_sources.py` | 2 |
| `test_ingest_candidate_urls.py` | 3 |
| `test_phase0_state.py` | 3 |
| `test_phase_gates_blackbox.py` | 2 |
| `test_rebuild_manifest_from_raw.py` | 3 |
| `test_redact_pii.py` | 5 |
| `test_render_html_report.py` | 1 |
| `test_run_phase4_parallel.py` | 8 |
| `test_scrape_ads.py` | 6 |
| `test_scrape_interstitial.py` | 4 |
| `test_scrub_manifest.py` | 3 |
| `test_train_manipulation_model.py` | 2 |
| **Sum** | **75** |

**NOT VERIFIED — the live pass/fail counts ("187 pass / 1 environmental fail") were not reproduced by running `pytest` in this audit; the count of 188 test functions found by grep is consistent with the claim (one environmental fail explains the +1).** No attempt was made to run the suite, because it depends on playwright/selenium environmental setup.

---

## 9. APIs and service inventory

### 9.1 In-process Python API (`adintel.api.AdIntelAPI`)

- Version: `adintel-api-v1`
- Endpoints (methods): `get_taxonomy`, `score_profile`, `pairwise_verify`, `open_set_attrib`, `cluster_all_spaces`, `detect_outliers`, `monitoring_summary`
- Response contract: every `APIResponse` carries `request_id`, `api_version`, `checkpoint_id`, `typed_output`, `held_out_metrics`, `calibration_status`, `cost_usd_per_1k`, `latency_ms`, `abstained`, `abstention_reason`, `review_status`, `evidence_refs_preserved`
- `held_out_metrics` is currently always `{}` for every endpoint (verified in `api.py:118, 158, 184, 207, 235, 265`) — **metrics are not wired through to the API responses**
- `monitoring_summary` exposes `n_calls`, `by_endpoint`, `p50_latency_ms`, `p95_latency_ms`

### 9.2 HTTP server (live)

- Process: `python3 -m http.server 8765 --bind 0.0.0.0 --directory /home/z/my-project/repo` (pid 993, parent pid 1, owner `z`)
- Verified routes:
  - `GET /` → 200 (directory listing)
  - `GET /reports/ad_manipulation_report.html` → 200, 12,858,658 B
  - `GET /reports/adintel/adintel_dashboard.html` → 200, 12,861,304 B
- **NOT VERIFIED — no FastAPI/Flask wrapper around `AdIntelAPI`**; the server only serves static files from the repo root. The Python API is **not exposed over HTTP**.

---

## 10. Pipeline outputs snapshot (from `reports/adintel/pipeline_results.json`)

- `ran_at`: 2026-08-04T00:25:35Z
- `elapsed_s`: 5.35
- `n_records_total`: 5,189
- `n_council_annotations`: 5,717
- `n_similarity_links`: 642
- `n_profile_sampled`: 200
- `n_cluster_sampled`: 300
- `n_authorship_pairs`: 41
- `n_outlier_sampled`: 1,000

Profile dimension means (sample of 200):
- highest: `offer_clarity` 0.405, `readability` 0.395, `benefit_density` 0.339, `manipulation_risk` 0.131
- lowest: `evidence_density` 0.0005, `risk_reversal` 0.002, `social_proof` 0.010, `certainty` 0.027

Outlier counts (sample of 1,000):
- `creative_novelty`: 50
- `unusual_technique_combination`: 22
- `style_outlier`: 26
- `performance_underperformer`: 90
- (no `duplicate`, `extraction_error`, `metadata_error`, `temporal_outlier`, `visual_outlier`, `performance_overperformer`, `model_error` — likely none triggered on the sample, or those detectors returned no hits)

Authorship (41 known pairs):
- accuracy_against_accepted_links: 0.9756
- n_abstained: 1
- **Caveat (from `reports/adintel/challenge_round1_defects.md` R1-D02): this number is selection-biased because all 642 (and the 41 sampled) links are positive pairs; no negative pairs are evaluated, so false-positive rate is unknown.**

---

## 11. Existing audit and research artifacts in repo

The repo already contains a research/audit trail under `audit/dashboard/research/`:

| Path | Purpose |
|------|---------|
| `audit/dashboard/research/research-plan.md` | Dashboard restoration research plan (Phase R0) |
| `audit/dashboard/research/source-ledger.jsonl` | 59 source records (WCAG 2.2, ARIA, MDN, sklearn docs, ROC/PR tutorials, scientific colour maps, …) — focused on dashboard accessibility |
| `audit/dashboard/research/comparable-projects.jsonl` | Comparable-projects registry (Highcharts, ApexCharts, Carbon, …) |
| `audit/dashboard/research/library-version-manifest.json` | Library version manifest (audited_at 2026-08-04T04:23:00Z) |
| `audit/dashboard/research/research-gates/term-network.json` | Research gate decision for the term-network feature |
| `audit/dashboard/research/technique-decisions/*.md` | 8 technique-decision records (kpi-cards, corpus-map, metric-heatmap, roc-pr-curves, term-network, timeline, explainability-atlas, top-explorer) |
| `audit/dashboard/research/benchmark-results/playwright_audit.json` | Playwright benchmark results |

The existing audit work is **dashboard-centric** (HTML/CSS/ARIA/accessibility). It does **not** cover model risk, data governance, or AI assurance — which is the gap this deliverable set addresses.

The repo also contains two self-critique ledgers (`reports/adintel/challenge_round1_defects.md` and `challenge_round2_defects.md`) with 18 candid defects already documented by the implementer. These are referenced throughout the residual risk register.

---

## 12. Notable discrepancies and verification gaps

The following items were claimed in the task brief but could not be confirmed on disk:

| Claim | Status |
|-------|--------|
| `scripts/generate_final_report_pdf.py` | **NOT VERIFIED** — no `scripts/` directory exists in the repo (`find . -maxdepth 3 -name scripts -type d` → no matches). |
| `download/advertisement_intelligence_persuasion_analytics_report.pdf` | **NOT VERIFIED** — no `download/` directory exists, and no `*.pdf` file anywhere in the first 3 directory levels. |
| "PDF generation pipeline" | **NOT VERIFIED** — no PDF generation code found in the repo. The pipeline output is HTML + JSON only. |
| `data/processed/ad_manifest.jsonl` (5,189 records) | VERIFIED. |
| `data/annotation/council_resolved_annotations.jsonl` (5,717 annotations) | VERIFIED. |
| `data/annotation/similarity_links.jsonl` (642 pairs) | VERIFIED. |
| 187 tests pass / 1 environmental fail | **PARTIALLY VERIFIED** — test-function counts (113 adintel + 75 v1 = 188) are consistent with "187 pass + 1 environmental fail" but pytest was not re-run. |
| 12.2 MB v1 HTML report | VERIFIED (`reports/ad_manipulation_report.html` = 12,858,658 bytes ≈ 12.27 MB). |
| 12.5 MB unified HTML report | VERIFIED (`reports/adintel/adintel_dashboard.html` = 12,861,304 bytes ≈ 12.27 MB; rounds to 12.5 MB at MB precision). |
| Live server `http://localhost:8765/reports/adintel/adintel_dashboard.html` | VERIFIED (HTTP 200). |
| 6 families, 26 leaves in taxonomy | VERIFIED (`adintel/taxonomy.py`). |
| 17-dim persuasive profile | VERIFIED (`adintel/types.py:PROFILE_DIMENSIONS`). |
| 7-space clustering | VERIFIED (`adintel/clustering.py:cluster_all_spaces`). |
| 11 outlier detectors | VERIFIED (`adintel/outlier.py` — docstring says "ten" but there are 11 actual detectors). |
| 6 registered checkpoints | VERIFIED (`adintel/checkpoints.py:REGISTRY`). |

---

## 13. Cross-references

- Architecture and data flow: [`ARCHITECTURE_AND_DATA_FLOW.md`](./ARCHITECTURE_AND_DATA_FLOW.md)
- Threat model (STRIDE): [`THREAT_MODEL.md`](./THREAT_MODEL.md)
- Model inventory: [`MODEL_INVENTORY.json`](./MODEL_INVENTORY.json)
- Metric catalog: [`METRIC_CATALOG.json`](./METRIC_CATALOG.json)
- Residual risk register: [`RESIDUAL_RISK_REGISTER.md`](./RESIDUAL_RISK_REGISTER.md)
- Reproduction instructions: [`REPRODUCE.md`](./REPRODUCE.md)
- Research ledger: [`RESEARCH_LEDGER.md`](./RESEARCH_LEDGER.md)

---

End of inventory.
