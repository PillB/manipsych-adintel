# Architecture and Data Flow — ManiPsych + adintel

**Audit artifact:** `audit/assurance/deliverables/ARCHITECTURE_AND_DATA_FLOW.md`
**System under audit:** ManiPsych + adintel advertisement-intelligence pipeline
**Repo root:** `/home/z/my-project/repo`
**Convention:** each pipeline stage is described with its **input → transform → output** and a verification status. Stages that could not be re-executed in this audit are marked `NOT VERIFIED — [reason]`.

---

## 1. End-to-end pipeline overview

```
                    ┌─────────────────────────────────────────────────────┐
                    │  EXTERNAL WEB (Peruvian classifieds + Facebook)     │
                    │  doplim.com.pe, locanto.com.pe, evisos.com.pe,      │
                    │  ciudadanuncios.com, facebook.com public pages      │
                    └───────────────────────┬─────────────────────────────┘
                                            │ Playwright + Selenium harvesters
                                            ▼
   ┌────────────────────────────────────────────────────────────────────────┐
   │  STAGE 0 — Collection (tools/collect_*, tools/scrape_ads.py,           │
   │            tools/run_phase4_parallel.py, tools/run_query_harvest_*      │
   │  Output: data/raw/ads/*.html (10,293 files per raw_rebuild_summary)    │
   └───────────────────────┬────────────────────────────────────────────────┘
                           │
                           ▼
   ┌────────────────────────────────────────────────────────────────────────┐
   │  STAGE 1 — Manifest rebuild (tools/rebuild_manifest_from_raw.py)       │
   │  + PII redaction (tools/redact_pii.py)                                 │
   │  + dedup (tools/scrub_manifest.py, scrub_invalid_ads.py)               │
   │  Output: data/processed/ad_manifest.jsonl (5,189 records)              │
   └───────────────────────┬────────────────────────────────────────────────┘
                           │
              ┌────────────┴────────────┐
              │                         │
              ▼                         ▼
   ┌──────────────────────┐   ┌──────────────────────────────────────────┐
   │  STAGE 2a — v1       │   │  STAGE 2b — Council annotation campaign  │
   │  Rule-based detector │   │  (tools/run_council_annotation_pass.py,   │
   │  (tools/detect_      │   │   council_consensus.py,                  │
   │   manipulation.py)   │   │   export_resolved_council_annotations.py,│
   │  → weak labels       │   │   scientist_validate_council_annotations)│
   └──────────┬───────────┘   │  Output: data/annotation/                │
              │               │    council_resolved_annotations.jsonl    │
              │               │    (5,717 annotations)                   │
              │               │    similarity_links.jsonl (642 pairs)     │
              │               │    documents.jsonl                       │
              │               └──────────────┬───────────────────────────┘
              │                              │
              ▼                              ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │  STAGE 3 — Model training                                             │
   │  3a. tools/train_manipulation_model.py                                │
   │      → models/manipulation_tfidf_ovr.joblib (TF-IDF + OVR LR)         │
   │  3b. tools/train_council_candidate_model.py                           │
   │      → models/manipulation_council_tfidf_ovr.joblib                   │
   │      → reports/council_candidate_model_report.json                    │
   └───────────────────────┬──────────────────────────────────────────────┘
                           │
                           ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │  STAGE 4 — Inference + dashboard generation                           │
   │  4a. tools/generate_council_inferences_report.py                      │
   │      → reports/ad_manipulation_report.html (12.86 MB, self-contained) │
   │      → reports/council_candidate_inferences.json (18.8 MB)            │
   │  4b. adintel package pipeline (adintel.api.AdIntelAPI)                │
   │      → reports/adintel/*.json (10 outputs)                            │
   │      → reports/adintel/adintel_dashboard.html (12.86 MB)              │
   └───────────────────────┬──────────────────────────────────────────────┘
                           │
                           ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │  STAGE 5 — Serving                                                    │
   │  python3 -m http.server 8765 --directory /home/z/my-project/repo      │
   │  (pid 993, 0.0.0.0:8765)                                              │
   │  Routes:                                                              │
   │    /reports/ad_manipulation_report.html        → v1 dashboard         │
   │    /reports/adintel/adintel_dashboard.html     → unified dashboard    │
   │    /annotation_app/index.html                  → annotation studio    │
   └───────────────────────┬──────────────────────────────────────────────┘
                           │
                           ▼
                   ┌───────────────────────┐
                   │  PDF REPORT (claimed) │
                   │  scripts/generate_    │
                   │  final_report_pdf.py  │
                   │  → download/*.pdf     │
                   └───────────────────────┘
                   NOT VERIFIED — neither the script nor the
                   download/ directory exists in the repo.
```

---

## 2. Stage-by-stage data flow

### Stage 0 — Collection (external → raw archive)

**Inputs:** public classified-ad websites (Doplim Peru, Locanto Peru, Evisos Peru, Ciudad Anuncios, Facebook public pages).

**Transform:** Playwright + Selenium headless harvesters (`tools/collect_locanto_fast.py`, `tools/collect_doplim_evisos_fast.py`, `tools/collect_evisos_playwright.py`, `tools/collect_ciudadanuncios.py`, `tools/collect_facebook_public.py`, `tools/collect_full_hombre_ads.py`, `tools/collect_hombre_locanto.py`, `tools/collect_doplim_ayuda_topup.py`, `tools/collect_doplim_evisos_sections.py`, `tools/collect_evisos_focused.py`, `tools/collect_evisos_mass.py`, `tools/collect_evisos_pw_details.py`, `tools/collect_seed_inventory.py`, `tools/scrape_ads.py`, `tools/selenium_search_first_harvester.py`, `tools/harvest_seeds.py`, `tools/ingest_candidate_urls.py`, `tools/expand_sources.py`, `tools/discover_sources.py`, `tools/build_query_bank.py`, `tools/run_phase4_parallel.py`, `tools/run_query_harvest_parallel.py`).

**Output:** `data/raw/ads/*.html` (10,293 files per `reports/raw_rebuild_summary.json:1`).

**Verified:** directory exists, contains HTML files with prefix patterns `arequipa_p1_*.html`, `agent_doplimfb_*.html`, `agent_full_searchfirst_*.html` (verified by `LS` on `data/raw/ads/`).

**NOT VERIFIED — the collection stage is not re-runnable in the sandbox** (it requires live network access to external ad sites, which is out of audit scope). The collection logic is documented in `docs/COLLECTION_AGENTS.md` and `reports/scraping_strategy_guide.md`.

---

### Stage 1 — Manifest rebuild (raw HTML → processed JSONL)

**Inputs:** `data/raw/ads/*.html`.

**Transform:** `tools/rebuild_manifest_from_raw.py` parses each HTML, extracts title/body/fields, applies target-term filtering, off-topic rejection, seeker-only rejection, PII redaction (`tools/redact_pii.py`), and dedup (`tools/scrub_manifest.py`, `tools/scrub_invalid_ads.py`).

**Output:** `data/processed/ad_manifest.jsonl` — 5,189 records (verified by `wc -l`).

**Rebuild statistics (from `reports/raw_rebuild_summary.json`):**

```
raw_files_scanned:         10,293
records_written:            5,738    (pre-dedup)
platform_counts: {doplim: 2845, locanto: 1562, ciudadanuncios: 1303, evisos: 2, facebook: 26}
reject_counts:   {seeker_only: 357, no_target_terms: 1782, low_body_text: 21,
                  tiny_or_corrupt: 14, offtopic_context: 3, access_interstitial: 7}
dedup_counts:    {duplicate_record_id: 2360, duplicate_normalized_text: 11}
manifest:        data/processed/ad_manifest.jsonl
gates:           TARGET+OFFTOPIC+seeker+dedup+PII
elapsed_sec:     1144.1
```

So 5,738 records were written pre-dedup, 2,371 were dropped by dedup → 5,738 − ~2,371 ≈ ~3,367? This does not reconcile cleanly with the 5,189-record current manifest. **Discrepancy: the `raw_rebuild_summary.json` says 5,738 records written, but the manifest has 5,189 lines.** The difference (549 records) is unaccounted for in the summary. Possible explanation: a later scrub pass (e.g. `tools/scrub_invalid_ads.py`) removed additional records after the rebuild summary was written. **NOT VERIFIED — exact cause not traced.**

**Record schema (verified from first line of `data/processed/ad_manifest.jsonl`):**

```json
{
  "record_id":            "h_<sha256-hex>",
  "source_platform":      "Doplim Peru" | "Locanto Peru" | "Ciudad Anuncios" | "Evisos Peru" | "Facebook Public",
  "source_url_hash":      "h_<sha256-hex>",
  "collected_at":         "<ISO-8601 UTC>",
  "title":                "<string, PII-redacted>",
  "body_redacted":        "<string, PII-redacted>",
  "raw_archive_ref":      "data/raw/ads/<filename>.html",
  "metadata":             { ... platform + extraction metadata ... }
}
```

`record_id` is `h_<sha256>` — i.e. the SHA-256 of the canonical URL hash. The `h_` prefix is a stable identifier convention.

**Schema file:** `schemas/ad_record.schema.json` exists (verified by `LS`).

---

### Stage 2a — Rule-based weak labelling (manifest → tags + score)

**Inputs:** `data/processed/ad_manifest.jsonl`.

**Transform:** `tools/detect_manipulation.py:analyze_text(text)` runs 6 lexical `Rule` patterns over the ad text:

| Tag | Pattern (case-insensitive) | Weight |
|-----|----------------------------|-------:|
| `scarcity_urgency_pressure` | `(hoy\|urgente\|ultimo\|último\|rapido\|rápido\|solo por\|limited\|last chance)` | 0.25 |
| `reciprocity_obligation` | `(ayuda\|apoyo\|favor\|te puedo ayudar\|gift\|regalo\|debes\|agradec)` | 0.20 |
| `platform_migration` | `(inbox\|dm\|privado\|whatsapp\|wsp\|telegram\|escribeme\|escríbeme)` | 0.25 |
| `safety_and_privacy_multiplier` | `(discreto\|discreta\|secreto\|sin que nadie\|confidencial\|privado)` | 0.25 |
| `financial_emergency_multiplier` | `(dinero\|economica\|económica\|efectivo\|pago\|soles\|prestamo\|préstamo)` | 0.20 |
| `confirmshaming_guilt_pressure` | `(si de verdad\|no seas\|demuestra\|no te cuesta\|por tu familia)` | 0.15 |

Score is the capped sum of matched weights (cap = 1.0). Output is `{"score", "tags", "findings"}`.

**Output:** in-memory dict consumed by `tools/train_manipulation_model.py:weak_labels()` to produce weak supervision labels.

**Verified:** yes — by reading the source.

---

### Stage 2b — Council annotation campaign (manifest → resolved annotations)

**Inputs:** `data/processed/ad_manifest.jsonl` + ad texts.

**Transform:** multi-round council annotation workflow:
1. `tools/prepare_annotation_campaign.py` generates annotation queues (`council_round1_second_pass_queue.jsonl`, `council_round2_queue.jsonl`, `council_second_pass_queue.jsonl`).
2. `tools/run_council_annotation_pass.py` runs council subagents over the queues. Council subagents produce span-level technique labels.
3. `tools/council_consensus.py` reconciles subagent outputs.
4. `tools/scientist_validate_council_annotations.py` runs scientist validation pass.
5. `tools/export_resolved_council_annotations.py` exports the resolved set.

**Output:**
- `data/annotation/council_resolved_annotations.jsonl` — 5,717 annotations (verified `wc -l`)
- `data/annotation/similarity_links.jsonl` — 642 known same-source pairs (verified `wc -l`)
- `data/annotation/documents.jsonl` — source documents
- `data/annotation/expert_manual_review_round4.jsonl` — expert manual review pass
- `data/annotation/annotations.locked.sqlite3` — locked SQLite annotation store (and `-journal`)

**Annotation schema (verified from first line of `council_resolved_annotations.jsonl`):**

```json
{
  "accepted_actor_id":  "<subagent id>",
  "accepted_round":     <int>,
  "agreement":          <float>,
  "corpus_version":     "<string>",
  "document":           "<doc id>",
  "gold":               false,                       // all are non-gold (per council_candidate_model_report.json:gold=false)
  "layer":              "subagent",                  // or "expert"
  "platform":           "<platform name>",
  "record_id":          "h_<sha256>",
  "spans": [
    {
      "exact_text":         "<surface>",
      "explicitness":       "explicit" | "implicit" | "unclear",
      "harm_risk":          <0..3>,
      "intensity":          <0..4>,
      "label":              "<v1 label>",
      "manipulativeness":   <0..3>,
      "provenance":         "<actor_id>",
      "rationale":          "<free text>",
      "segments":           [[start, end], ...],     // zero-based, end-exclusive Unicode code points
      "vulnerability_target": "age_youth" | "education_student" | "economic_vulnerability" | "family_obligation" | "gendered_appearance"
    }
  ],
  "split_name":         "train" | "validation" | "test" | "challenge",
  "text_hash":          "<sha256>"
}
```

**v1 label schema (from `data/annotation/label_schema.json`):** `manipsych-span-v1`, 20 labels (matches the `v1_equivalents` mapping in `adintel/taxonomy.py`).

**Split counts (from `reports/council_candidate_model_report.json`):** `train: 3983, validation: 853, test: 853, challenge: 28` (sum 5,717).

**Verified:** yes — by reading schema files and inspecting first records.

---

### Stage 3 — Model training

#### Stage 3a — TF-IDF + OVR LR (weak-supervised baseline)

**Inputs:** `data/processed/ad_manifest.jsonl` + `tools/detect_manipulation.analyze_text` (weak labels) + metadata context labels (paid/featured/follower/engagement/repeat-poster).

**Transform:** (`tools/train_manipulation_model.py`)
1. Load records from `data/processed/ad_manifest.jsonl`.
2. Build text = `f"{title}\n{body_redacted}"`.
3. Generate weak labels per record via `weak_labels(text)` (rule-based + keyword heuristics) and `metadata_context_labels(record, account_counts)`.
4. `MultiLabelBinarizer` → multi-hot label matrix.
5. `Pipeline([TfidfVectorizer(ngram_range=(1,2), min_df=1, max_features=3000, sublinear_tf=True, lowercase=True), OneVsRestClassifier(LogisticRegression(max_iter=1000, class_weight="balanced"))])`.
6. `train_test_split` with stratification.
7. Compute accuracy, F1 (micro/macro), precision/recall, ROC AUC, PR curve.
8. `joblib.dump` to `models/manipulation_tfidf_ovr.joblib`.

**Output:** `models/manipulation_tfidf_ovr.joblib` (390,941 B; sha256 `6bb0fbe2…a05cecc`). Report: `reports/phase5_model_report.json`.

**Verified:** yes.

#### Stage 3b — Council candidate model (trained on resolved council annotations)

**Inputs:** `data/annotation/council_resolved_annotations.jsonl` + `data/annotation/documents.jsonl`.

**Transform:** (`tools/train_council_candidate_model.py`)
1. Load annotations and documents.
2. Aggregate span-level labels to document-level multi-label sets.
3. Same TF-IDF + OVR LR pipeline as 3a.
4. Three-way split: train (3,983) / validation (853) / test (853); plus a 28-record "challenge" set.
5. Evaluate per-label: accuracy, F1, precision, recall, ROC AUC; plus micro/macro aggregates; plus ROC and PR curves (downsampled to 80 points for embedding).
6. `joblib.dump` to `models/manipulation_council_tfidf_ovr.joblib`.

**Output:**
- `models/manipulation_council_tfidf_ovr.joblib` (3,425,035 B; sha256 `25b1bcab…9fe77b28`)
- `reports/council_candidate_model_report.json` (40,641 B) — contains `metrics: {train, validation, test, challenge}` each with per-label breakdowns.

**Verified:** yes.

**Reported metrics (from `reports/council_candidate_model_report.json`):**

| Split | Records | Subset accuracy | Micro F1 | Macro F1 | Micro ROC AUC | Macro ROC AUC |
|-------|--------:|----------------:|---------:|---------:|--------------:|--------------:|
| train | 3,983   | (not in summary) | (not in summary) | (not in summary) | (not in summary) | (not in summary) |
| validation | 853 | 0.5182 | 0.9041 | 0.7119 | 0.9888 | 0.9706 |
| test | 853 | 0.5076 | 0.9008 | 0.7044 | 0.9872 | 0.9721 |
| challenge | 28 | 0.7143 | 0.9280 | 0.4706 | 0.9871 | 0.9312 |

**Audit interpretation:** Micro F1 ≈ 0.90 looks strong, but the label space is sparse (20 labels, mostly absent per record), so label-absence predictions dominate. Subset accuracy (exact-match) is only ~0.51 on validation/test, meaning the model predicts the **full label set correctly only half the time**. Macro F1 ≈ 0.70 is a more honest single-number summary. Challenge-set macro F1 of 0.47 indicates meaningful generalisation gap on adversarial examples. **Limitations (from `reports/council_candidate_model_report.json:limitations`):**
1. Training labels are resolved council suggestions, not two-human adjudicated gold.
2. Metrics evaluate agreement with the council labeling function and should not be presented as independently validated human performance.
3. Image pixels were unavailable; image-only persuasion remains unmodeled.

---

### Stage 4 — Inference and dashboard generation

#### Stage 4a — v1 dashboard (council inferences)

**Inputs:** `models/manipulation_council_tfidf_ovr.joblib`, `data/annotation/documents.jsonl`, `data/annotation/council_resolved_annotations.jsonl`, `reports/council_candidate_model_report.json`, `reports/segment_model_analysis.json`.

**Transform:** (`tools/generate_council_inferences_report.py`, 1,811 LOC)
1. Load council model.
2. Generate inferences on all annotation documents → `reports/council_candidate_inferences.json` (18.8 MB).
3. Compute manipulative-label subset, contextual multipliers, segment analyses, top-records rankings.
4. Build a self-contained HTML page that embeds all data inline (no external `<script src=…>`, no fetch/AJAX).
5. Embed a vendored mini-D3 helper (`reports/assets/d3-lite-force.js`, 89 LOC, 3,268 B) for the term-network visualization.

**Output:**
- `reports/council_candidate_inferences.json` (18,809,019 B)
- `reports/ad_manipulation_report.html` (12,858,658 B ≈ 12.27 MB; rounds to 12.2 MB)

**Verified:** yes (HTML head inspected; no external scripts).

#### Stage 4b — adintel package pipeline

**Inputs:** `data/processed/ad_manifest.jsonl`, `data/annotation/council_resolved_annotations.jsonl`, `data/annotation/similarity_links.jsonl`, `models/manipulation_council_tfidf_ovr.joblib`.

**Transform:** the `adintel` package exposes an in-process API (`adintel.api.AdIntelAPI`). A pipeline runner (NOT present in the repo as a standalone script — `scripts/run_adintel_pipeline.py` is referenced in `reports/adintel/challenge_round1_defects.md:91` but **does not exist on disk**) calls:
1. `AdIntelAPI.get_taxonomy()` → `reports/adintel/taxonomy_v2.json`
2. `AdIntelAPI.score_profile(text)` for a 200-record sample → `reports/adintel/profile_sample.json`
3. `AdIntelAPI.cluster_all_spaces(records, texts)` for a 300-record stratified sample → `reports/adintel/clustering_summary.json`
4. `AdIntelAPI.pairwise_verify(left, right)` for 41 known pairs → `reports/adintel/authorship_known_pairs.json`
5. `AdIntelAPI.detect_outliers(texts, records, label_sets, predictions)` for a 1,000-record sample → `reports/adintel/outlier_summary.json`
6. Checkpoint registry dump → `reports/adintel/checkpoint_registry.json`
7. v1→v2 migration projection → `reports/adintel/v1_to_v2_migration_report.json`
8. Top-level summary → `reports/adintel/pipeline_results.json`

**Output:** the 10 JSON files under `reports/adintel/` listed in §7.2 of the AI System Inventory. Elapsed time: 5.35s.

**Verified:** yes — pipeline outputs exist and reconcile with `pipeline_results.json` header.

**NOT VERIFIED — the pipeline runner script itself is not in the repo.** The outputs were generated by some runner, but it cannot be re-executed from a script in the repo. The `AdIntelAPI` class is callable in-process from a Python REPL, but no CLI wrapper exists. This is documented in `reports/adintel/challenge_round2_defects.md` R2-D09 ("Repository integration: pyproject.toml not updated") and R2-D01 ("No dashboard page exists for the new adintel outputs" — partially addressed: a unified dashboard now exists but the runner is still ad-hoc).

#### Stage 4c — Unified dashboard

**Inputs:** all `reports/adintel/*.json` outputs + the v1 inferences.

**Transform:** HTML generator (NOT a standalone script — the unified dashboard appears to have been assembled manually or by a script that is not in the repo). Title: "ManiPsych + adintel — Unified Observatory".

**Output:** `reports/adintel/adintel_dashboard.html` (12,861,304 B).

**Verified:** yes (HTTP 200 from live server).

**NOT VERIFIED — the generator script for the unified dashboard is not present in the repo.** Only `tools/generate_council_inferences_report.py` (which produces the v1 dashboard) is present.

---

### Stage 5 — Serving

**Process:** `python3 -m http.server 8765 --bind 0.0.0.0 --directory /home/z/my-project/repo` (pid 993).

**Verified routes:**

| Route | HTTP | Bytes |
|-------|-----:|------:|
| `/` | 200 | 1,136 (directory listing) |
| `/reports/ad_manipulation_report.html` | 200 | 12,858,658 |
| `/reports/adintel/adintel_dashboard.html` | 200 | 12,861,304 |

**Binding:** `0.0.0.0:8765` — exposed on **all network interfaces**, not just localhost. This is a security concern (see Threat Model).

**Authentication:** none. Any client that can reach port 8765 can read the entire repo (including `models/`, `data/`, `audit/`, etc.).

**NOT VERIFIED — whether the Python `AdIntelAPI` is also exposed over HTTP** (it is not; only static files are served).

---

### Stage 6 — PDF generation (claimed but not verified)

**Claimed:** `scripts/generate_final_report_pdf.py` → `download/advertisement_intelligence_persuasion_analytics_report.pdf`.

**Status:** **NOT VERIFIED — neither `scripts/` nor `download/` directory exists in the repo.** No `.pdf` file exists at any depth ≤ 3 (verified by `find . -maxdepth 3 -name "*.pdf"`). No code in `tools/` references PDF generation. The PDF stage appears to be either planned, deleted, or performed outside the sandbox.

---

## 3. Data lineage and provenance

```
record_id (h_<sha256>) ───────────────────────────────┐
   │                                                   │
   │ ─── ad_manifest.jsonl ─────────────────────────┐  │
   │              │                                  │  │
   │              ├──► detect_manipulation ───► weak labels
   │              │                                  │  │
   │              └──► train_manipulation_model ──► manipulation_tfidf_ovr.joblib
   │                                                 │  │
   │ ─── council_resolved_annotations.jsonl ──┐      │  │
   │              │                            │      │  │
   │              ├──► train_council_candidate ─► manipulation_council_tfidf_ovr.joblib
   │              │                            │      │  │
   │              ├──► adintel.profile ────► profile_sample.json
   │              │                            │      │  │
   │              └──► adintel.authorship ──► authorship_known_pairs.json
   │                                               │  │  │
   └─── similarity_links.jsonl ───► calibration set │  │
                                                    │  │
   ─── ad_manifest.jsonl ──────► adintel.clustering ► clustering_summary.json
                                                    │  │
                              ─── adintel.outlier ──► outlier_summary.json
                                                    │  │
                              ─── adintel.checkpoints ► checkpoint_registry.json
                                                    │  │
                              ─── adintel.api ──────► pipeline_results.json
                                                    │  │
                              ─── adintel.taxonomy ─► taxonomy_v2.json
                                                    │  │
                              ─── v1→v2 migration ─► v1_to_v2_migration_report.json
```

**Provenance gaps identified:**
1. The `record_id` hash is `h_<sha256>` of the canonical URL — **NOT VERIFIED** whether this is the URL hash or content hash; `tools/rebuild_manifest_from_raw.py` would confirm but was not re-read in detail.
2. The `accepted_actor_id` in annotations references council subagents (`subagent_r5_a` was seen in the first record). The mapping from `accepted_actor_id` to a specific model/system version is **NOT VERIFIED**.
3. The 5,717 council annotations vs 5,189 manifest records: there are **528 more annotations than manifest records**. This is consistent with annotations being on a 5,717-record modeling superset (the modeling_manifest), but that file does not exist in the sandbox.

---

## 4. Trust boundaries

| Boundary | Crossing | Controls |
|----------|----------|----------|
| External web → repo (`data/raw/ads/`) | Ingress of third-party HTML | PII redaction (`tools/redact_pii.py`); off-topic + seeker-only rejection; target-term filtering |
| Raw HTML → processed manifest | Parsing and PII redaction | `redact_pii.py` patterns; locked manifest after rebuild; raw archive is immutable |
| Manifest → council annotations | Council labelling | Council consensus, scientist validation, expert review, locked SQLite store |
| Annotations → trained models | Supervised learning | Train/val/test/challenge splits; metrics report; per-label AUC; limitations disclosure |
| Models → HTML dashboards | Inference + rendering | Self-contained HTML (no CDN); vendored JS only; PII never embedded (verified in dashboard HTML head) |
| Repo → HTTP server | Static file serving | **No authentication, no rate limiting, no TLS, binds to 0.0.0.0** (open trust boundary — see Threat Model) |
| Repo → PDF (claimed) | Export | **NOT VERIFIED — pipeline does not exist on disk** |

---

## 5. Reproducibility status

| Stage | Reproducible from repo? | Notes |
|-------|:------------------------:|-------|
| 0. Collection | No | Requires live network access; harvesters exist but external sites may change |
| 1. Manifest rebuild | Yes | `python3 tools/rebuild_manifest_from_raw.py` |
| 2a. Rule-based labelling | Yes | `python3 tools/detect_manipulation.py "<text>"` |
| 2b. Council annotation | Partial | Council subagent system is referenced but its driver is **NOT VERIFIED** as present |
| 3a. v1 model training | Yes | `python3 tools/train_manipulation_model.py` |
| 3b. Council model training | Yes | `python3 tools/train_council_candidate_model.py` |
| 4a. v1 dashboard | Yes | `python3 tools/generate_council_inferences_report.py` |
| 4b. adintel pipeline | Partial | `AdIntelAPI` is callable; **the runner script is NOT in the repo** |
| 4c. Unified dashboard | No | **Generator script is NOT in the repo** |
| 5. HTTP serving | Yes | `python3 -m http.server 8765 --directory /home/z/my-project/repo` |
| 6. PDF | No | **Script does not exist** |

---

## 6. Cross-references

- AI System Inventory: [`AI_SYSTEM_INVENTORY.md`](./AI_SYSTEM_INVENTORY.md)
- Threat model: [`THREAT_MODEL.md`](./THREAT_MODEL.md)
- Reproduction instructions: [`REPRODUCE.md`](./REPRODUCE.md)
- Residual risks: [`RESIDUAL_RISK_REGISTER.md`](./RESIDUAL_RISK_REGISTER.md)

End of document.
