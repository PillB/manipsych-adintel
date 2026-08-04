# Residual Risk Register — ManiPsych + adintel

**Audit artifact:** `audit/assurance/deliverables/RESIDUAL_RISK_REGISTER.md`
**Method:** NIST AI RMF (GOVERN / MAP / MEASURE / MANAGE) framing; severity × likelihood with current-mitigation effectiveness factored in.
**Scope:** the top 10 risks that remain after the existing mitigations (documented in [`THREAT_MODEL.md`](./THREAT_MODEL.md) §8) have been applied.
**Convention:** every risk lists ID, summary, severity, likelihood, affected assets, current mitigation, residual mitigation gap, owner, recommended next action, and cross-references.

---

## Severity and likelihood scales

| Level | Severity | Likelihood |
|-------|----------|------------|
| Critical | Direct harm to data subjects (e.g. PII exposure, misidentification of a person) or system-wide integrity loss | Already occurring or near-certain on current deployment |
| High | Significant degradation of trust, accuracy, or compliance; could escalate to direct harm if untreated | Plausible within weeks of normal operation |
| Medium | Localised quality, governance, or compliance degradation | Plausible within months |
| Low | Minor or cosmetic issue; no direct harm path | Unlikely under normal operation |

---

## Top 10 residual risks

### RR-01 — Unauthenticated HTTP server exposes the entire repo, including raw HTML with PII

| Field | Value |
|-------|-------|
| **Severity** | Critical |
| **Likelihood** | High (already occurring) |
| **Affected assets** | `data/raw/ads/*.html` (10,293 files), `data/processed/ad_manifest.jsonl`, `models/*.joblib`, `audit/` (this very file), `reports/*.html` |
| **STRIDE categories** | S-1, I-1, I-6, D-1, E-1, E-2 |
| **Current mitigation** | None. The server is `python3 -m http.server 8765 --bind 0.0.0.0 --directory /home/z/my-project/repo` (pid 993). It serves every file in the repo with no auth, no TLS, no rate limit. Verified by `curl http://localhost:8765/data/processed/ad_manifest.jsonl` would succeed. |
| **Residual gap** | The PII redaction in `tools/redact_pii.py` applies to the *processed* manifest only; the raw HTML in `data/raw/ads/` retains phone numbers, social handles, and other contact info. The HTTP server exposes raw HTML directly. |
| **Owner** | Project implementer / ops |
| **Recommended next action** | (1) Kill the `python3 -m http.server` process. (2) Replace with a static-file server that (a) binds to `127.0.0.1` if external access is not required, (b) serves only `reports/` and `annotation_app/` paths, (c) requires HTTP basic auth, (d) uses TLS. (3) Run `tools/redact_pii.py` over `data/raw/ads/*.html` if any external access is unavoidable. |
| **Cross-refs** | [`THREAT_MODEL.md`](./THREAT_MODEL.md) §5, §7 (priority threat #1, #2); [`AI_SYSTEM_INVENTORY.md`](./AI_SYSTEM_INVENTORY.md) §9.2; [`ARCHITECTURE_AND_DATA_FLOW.md`](./ARCHITECTURE_AND_DATA_FLOW.md) Stage 5 |

---

### RR-02 — Authorship model has no negative-pair evaluation; false-positive rate is unknown

| Field | Value |
|-------|-------|
| **Severity** | High |
| **Likelihood** | Medium (the model is already producing verdicts) |
| **Affected assets** | `adintel/authorship.py`, `reports/adintel/authorship_known_pairs.json`, dashboards that surface authorship verdicts |
| **STRIDE categories** | I-3, I-7 (residual after guardrail) |
| **Current mitigation** | (a) `person_named=False` hard guardrail (verified); (b) length-aware abstention (≥15 tokens); (c) conservative `SAME_SOURCE_THRESHOLD = 0.55`; (d) council-label overlap capped at 5% weight; (e) `assert_no_person_named` runtime assertion + 19 authorship tests. |
| **Residual gap** | The 642 known similarity links are all positive pairs (same source). No different-source pairs are evaluated. The reported 0.9756 accuracy is therefore a true-positive rate only; the false-positive rate (chance of wrongly asserting "same_source" for two genuinely independent ads) is **unknown**. This is the most important scientific residual risk because the entire authorship capability rests on a one-class evaluation. |
| **Owner** | Project implementer (model owner) |
| **Recommended next action** | Construct a labelled negative-pair evaluation set: sample ~200 pairs that are (a) from different platforms, (b) about different topics, (c) collected at different times, and have an expert confirm they are genuinely different-source. Run `pairwise_verify` over both positive (642) and negative (200) pairs. Report sensitivity, specificity, and ROC AUC at multiple thresholds. Tune `SAME_SOURCE_THRESHOLD` to a target false-positive rate (e.g. ≤ 5%). Apply Platt scaling on the calibrated set (the helper `platt_scale` already exists in `adintel/checkpoints.py:264`). This is challenge R1-D02's "selected change" — currently not implemented. |
| **Cross-refs** | [`MODEL_INVENTORY.json`](./MODEL_INVENTORY.json) `authorship-v1` `known_limitations`; [`THREAT_MODEL.md`](./THREAT_MODEL.md) §7 priority threat #5; `reports/adintel/challenge_round1_defects.md` R1-D02 |

---

### RR-03 — All checkpoints are uncalibrated; no probability calibration has been applied

| Field | Value |
|-------|-------|
| **Severity** | High |
| **Likelihood** | High (already the case) |
| **Affected assets** | All 6 registered checkpoints; `reports/adintel/checkpoint_registry.json` |
| **STRIDE categories** | T-2 (indirect), R-3 |
| **Current mitigation** | The `adintel/checkpoints.py` module provides `platt_scale` (line 264) and `temperature_scale` (line 283) helpers. The `average_calibrated_only` function (line 317) refuses to average scores across uncalibrated checkpoints, which is the right guard. |
| **Residual gap** | No checkpoint has `calibration_status` other than `"uncalibrated"` (verified in `reports/adintel/checkpoint_registry.json`). The helpers exist but are never called by any pipeline runner or training script. This means every probability reported by the council model is a raw sigmoid output, not a calibrated confidence. Downstream consumers (dashboards, rankings) treat these as if they were calibrated. |
| **Owner** | Project implementer (model owner) |
| **Recommended next action** | (1) Apply Platt scaling to the council model on the validation split (853 records). (2) Apply temperature scaling as a fallback if Platt overfits. (3) Compute Expected Calibration Error (ECE) before and after. (4) Update `CheckpointSpec.calibration_status` to `"platt"` or `"temperature"` in the registry. (5) Surface the calibration curve in the dashboard. |
| **Cross-refs** | [`MODEL_INVENTORY.json`](./MODEL_INVENTORY.json) (all entries `calibration_status: uncalibrated`); [`METRIC_CATALOG.json`](./METRIC_CATALOG.json) `calibration_status`; `reports/adintel/challenge_round1_defects.md` R1-D06; Guo et al. (2017) in [`RESEARCH_LEDGER.md`](./RESEARCH_LEDGER.md) §2.4 |

---

### RR-04 — Cluster brand leakage is near-total in 4 of 7 spaces; dashboards may mislead analysts

| Field | Value |
|-------|-------|
| **Severity** | High |
| **Likelihood** | High (already occurring in current pipeline output) |
| **Affected assets** | `adintel/clustering.py`, `reports/adintel/clustering_summary.json`, `reports/adintel/adintel_dashboard.html` (cluster cards) |
| **STRIDE categories** | T-5 (conceptual tampering with interpretation) |
| **Current mitigation** | (a) `stratified_sample` helper exists in `adintel/clustering.py:440`; (b) `evaluate_leakage` function reports per-platform and per-platform-family dominance; (c) `ClusterReport.brand_leakage` and `topic_leakage` fields are populated and surfaced in the JSON output. |
| **Residual gap** | Despite the helper existing, the latest pipeline run (`reports/adintel/clustering_summary.json`) shows brand leakage of 100% in `semantic`, 100% (Facebook Public) in `rhetorical`, 100% (Doplim) + 96.3% (Locanto) in `visual`, 100% (Doplim) + 96.3% (Locanto) in `multimodal`. The 300-record sample was not stratified by platform, so clusters are separating by platform, not by technique. An analyst seeing "Cluster 0 = Locanto ads about students" may believe they have found a technique cluster when they have found a platform cluster — exactly the "treat technique presence as proof of persuasion" failure mode the spec warns against. |
| **Owner** | Project implementer (pipeline owner) |
| **Recommended next action** | (1) Re-run `cluster_all_spaces` using `stratified_sample(records, by_field='source_platform', n_per_stratum=50)` so the 300-record sample is balanced across platforms. (2) Regenerate `reports/adintel/clustering_summary.json` and the dashboard. (3) If leakage persists, residualise platform from the feature vectors before clustering. (4) Add a dashboard warning banner when `brand_leakage >= 0.7` in any space. |
| **Cross-refs** | [`MODEL_INVENTORY.json`](./MODEL_INVENTORY.json) `clustering-v1` `latest_run_metrics`; [`METRIC_CATALOG.json`](./METRIC_CATALOG.json) `cluster_brand_leakage`; `reports/adintel/challenge_round1_defects.md` R1-D01 |

---

### RR-05 — No file-integrity manifest; model and data tampering is undetectable

| Field | Value |
|-------|-------|
| **Severity** | High |
| **Likelihood** | Low (filesystem is local, single user) |
| **Affected assets** | `models/*.joblib`, `data/processed/ad_manifest.jsonl`, `data/annotation/*.jsonl`, `reports/*.html`, `reports/adintel/*.json` |
| **STRIDE categories** | T-1, T-2, T-3, T-4, E-6 |
| **Current mitigation** | SHA-256 hashes of model files and source files are recorded in this audit (post-hoc). `data/annotation/annotations.locked.sqlite3` is "locked" (write-protected). Git is implied but not in scope. |
| **Residual gap** | No checksum manifest is generated or verified at boot. `joblib.load` will execute arbitrary code from a malicious pickle without warning. A tampered `data/processed/ad_manifest.jsonl` would silently change model training and dashboard content. The recorded SHA-256s in this audit are descriptive, not enforced. |
| **Owner** | Project implementer / ops |
| **Recommended next action** | (1) Generate `audit/assurance/integrity_manifest.json` listing every file under `adintel/`, `tools/`, `models/`, `data/processed/`, `data/annotation/`, `reports/adintel/` with its SHA-256. (2) Add a verification script `tools/verify_integrity.py` that loads the manifest and compares against current files; exit non-zero on mismatch. (3) Sign the manifest with a project key (or at minimum, store its own SHA-256 in a separate read-only location). (4) Refuse to load `models/*.joblib` if the hash does not match the manifest. (5) Run the verification script before every dashboard serve. |
| **Cross-refs** | [`THREAT_MODEL.md`](./THREAT_MODEL.md) §6 (T-1, T-2, T-3, T-4, E-6); [`AI_SYSTEM_INVENTORY.md`](./AI_SYSTEM_INVENTORY.md) §1.5 |

---

### RR-06 — Stale documentation claims 1,589 records when the actual manifest has 5,189

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Likelihood** | High (already the case) |
| **Affected assets** | `reports/dataset_manifest.md`, `reports/ad_manipulation_ranking.json`, `reports/final_report.md`, `reports/raw_rebuild_summary.json`, `reports/modeling_dataset_summary.json` |
| **STRIDE categories** | R-3 (repudiation of training data) |
| **Current mitigation** | None. The discrepancy is documented in [`AI_SYSTEM_INVENTORY.md`](./AI_SYSTEM_INVENTORY.md) §6.1 but not flagged in the source artifacts themselves. |
| **Residual gap** | `reports/dataset_manifest.md` claims "1,589 strict-valid records" and `reports/ad_manipulation_ranking.json` claims `total_records_scored: 1589`, but `data/processed/ad_manifest.jsonl` actually contains 5,189 records (verified by `wc -l`). An auditor or downstream consumer who reads the dataset manifest would form an incorrect view of the corpus size. Furthermore, `reports/council_candidate_model_report.json:annotation_source` references `/Users/pabloillescas/Projects/grokBuild/ManiPsych/data/annotation/council_resolved_annotations.jsonl` — a developer-machine path that should be redacted. |
| **Owner** | Project implementer (documentation owner) |
| **Recommended next action** | (1) Regenerate `reports/dataset_manifest.md` and `reports/ad_manipulation_ranking.json` from the current manifest, or mark them deprecated with a banner pointing to `reports/raw_rebuild_summary.json` and `reports/modeling_dataset_summary.json`. (2) Redact the developer-machine path in `reports/council_candidate_model_report.json:annotation_source` to a relative path or remove the field. (3) Add a "data lineage" section to the model card (`reports/model_card.md`) that explains which manifest was used for each model. |
| **Cross-refs** | [`AI_SYSTEM_INVENTORY.md`](./AI_SYSTEM_INVENTORY.md) §6.1, §12; [`THREAT_MODEL.md`](./THREAT_MODEL.md) I-9; [`ARCHITECTURE_AND_DATA_FLOW.md`](./ARCHITECTURE_AND_DATA_FLOW.md) §3 (provenance gaps) |

---

### RR-07 — Open-set attribution conflation with pairwise verification; no per-task threshold tuning

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Likelihood** | Medium (already the case) |
| **Affected assets** | `adintel/authorship.py:OPEN_SET_UNKNOWN_THRESHOLD`, `adintel/authorship.py:open_set_attrib`, `reports/adintel/authorship_known_pairs.json` |
| **STRIDE categories** | T-5 (conceptual) |
| **Current mitigation** | Documented as a limitation in the module docstring (challenge R1-D03). |
| **Residual gap** | `OPEN_SET_UNKNOWN_THRESHOLD = 0.30` is the same as `DIFFERENT_SOURCE_THRESHOLD = 0.30`. These are conceptually different decisions (pairwise asks "are these two specific texts from the same source?", open-set asks "is this query from ANY known source?"). Using the same threshold means an ad that is genuinely from a new source may be mis-attributed to the closest known source. The dashboard surfaces the limitation via `abstention_reason="empty_candidate_set_in_open_set"` but does not surface the conflation. |
| **Owner** | Project implementer (model owner) |
| **Recommended next action** | (1) Add a separate `OPEN_SET_REJECTION_THRESHOLD` constant, initialised to a different value (e.g. 0.40) and tuned on a held-out evaluation set with known-unknown cases. (2) Surface the conflation in the typed output via `abstention_reason="open_set_threshold_conflated_with_pairwise"` until the fix is complete. (3) Construct an evaluation set with ~50 known-unknown queries (ads from platforms NOT in the candidate set). |
| **Cross-refs** | [`MODEL_INVENTORY.json`](./MODEL_INVENTORY.json) `authorship-v1` `known_limitations`; `reports/adintel/challenge_round1_defects.md` R1-D03; Scheirer et al. (2013) in [`RESEARCH_LEDGER.md`](./RESEARCH_LEDGER.md) §2.6 |

---

### RR-08 — No pipeline runner script for adintel Stage 4b; outputs cannot be reproduced from in-repo code

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Likelihood** | High (already the case) |
| **Affected assets** | `reports/adintel/*.json` (10 pipeline output files), `reports/adintel/adintel_dashboard.html` |
| **STRIDE categories** | R-3, R-4 |
| **Current mitigation** | The `AdIntelAPI` class is callable in-process from a Python REPL. `pipeline_results.json:ran_at` records the run timestamp. |
| **Residual gap** | The script that produced `reports/adintel/*.json` is **not in the repo**. The `reports/adintel/challenge_round1_defects.md:91` references `scripts/run_adintel_pipeline.py` but no such file exists (`find . -maxdepth 3 -name "run_adintel*"` → no matches). This means: (a) the outputs cannot be reproduced from in-repo code, (b) the exact call sequence (sample sizes, random seeds, thresholds) is not captured, (c) the unified dashboard generator (`reports/adintel/adintel_dashboard.html`) is also not in the repo. The `tools/generate_council_inferences_report.py` script only produces the v1 dashboard. |
| **Owner** | Project implementer |
| **Recommended next action** | (1) Commit a `scripts/run_adintel_pipeline.py` (or `tools/run_adintel_pipeline.py`) that calls `AdIntelAPI` methods with the documented sample sizes and writes the 10 JSON outputs. (2) Commit a `tools/generate_adintel_dashboard.py` (or extend `generate_council_inferences_report.py`) that produces `reports/adintel/adintel_dashboard.html` from the JSON outputs. (3) Add a CI step that re-runs the pipeline on every push and verifies the outputs match (modulo timestamps). |
| **Cross-refs** | [`ARCHITECTURE_AND_DATA_FLOW.md`](./ARCHITECTURE_AND_DATA_FLOW.md) §5 (reproducibility table); [`AI_SYSTEM_INVENTORY.md`](./AI_SYSTEM_INVENTORY.md) §12; `reports/adintel/challenge_round2_defects.md` R2-D01, R2-D09 |

---

### RR-09 — LLM-driven council subagent pipeline is opaque; ad text may be sent off-host

| Field | Value |
|-------|-------|
| **Severity** | Medium-High |
| **Likelihood** | Unknown (the LLM client code is not in the repo) |
| **Affected assets** | `data/annotation/council_resolved_annotations.jsonl`, council annotation pipeline (Stage 2b) |
| **STRIDE categories** | I-10, E-4, S-3 |
| **Current mitigation** | `accepted_actor_id`, `accepted_round`, `provenance` fields record which subagent produced each annotation. `tools/scientist_validate_council_annotations.py` provides a human-in-the-loop validation gate. |
| **Residual gap** | The council annotation records reference `subagent_r5_a` and similar actor IDs, strongly suggesting that an LLM is involved in the annotation pipeline. **NOT VERIFIED — no LLM client code is in the repo.** If an external LLM is used, then ad text (potentially containing PII if redaction was incomplete, or sensitive content about vulnerable individuals) is sent off-host to an LLM provider. This would be an uncontrolled information disclosure and a prompt-injection attack surface (an attacker could craft ad text that instructs the LLM to produce misleading labels). |
| **Owner** | Project implementer (annotation pipeline owner) |
| **Recommended next action** | (1) Document the council subagent architecture: which LLM provider, what prompt template, what data is sent, what is logged. (2) If ad text is sent off-host, run `tools/redact_pii.py` over the text before sending, and log the redaction. (3) Add prompt-injection defences: wrap ad text in a structured envelope that instructs the LLM to treat the content as data, not instructions. (4) Log every LLM call with timestamp, prompt hash, response hash, and cost. (5) Add a `subagent_version` field to the annotation schema so the LLM model version is captured. |
| **Cross-refs** | [`THREAT_MODEL.md`](./THREAT_MODEL.md) §7 priority threat #5; [`AI_SYSTEM_INVENTORY.md`](./AI_SYSTEM_INVENTORY.md) §6.2; OWASP LLM Top 10 (LLM01, LLM02) in [`RESEARCH_LEDGER.md`](./RESEARCH_LEDGER.md) §1.2 |

---

### RR-10 — Spanish regex signals are ASCII-centric; profile scores may be systematically biased on accented text

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Likelihood** | Medium (already the case; affects every accented ad) |
| **Affected assets** | `adintel/profile.py` (all signal inventories), `reports/adintel/profile_sample.json`, dashboard profile cards |
| **STRIDE categories** | T-5 (conceptual; bias in measurement) |
| **Current mitigation** | All regex patterns use `re.IGNORECASE` flag. `TfidfVectorizer` calls use `strip_accents="unicode"` (in `clustering.py` and `authorship.py`). |
| **Residual gap** | The signal regexes in `adintel/profile.py` use `\b` word boundaries, which in Python's `re` module are ASCII-centric and may behave unexpectedly on accented characters. For example, `\b(urgente)\b` may not match "¡urgente!" because `!` is a non-word character but `¡` (inverted exclamation) may interact differently with `\b` depending on Unicode flag. The Spanish Flesch implementation uses `[aeiouáéíóúü]+` for syllable counting, which over-counts diphthongs (e.g. "ayuda" → 2 syllables by regex but 2 actual; "huerta" → 2 syllables by regex but 2 actual; "ciudad" → 2 syllables by regex but 2 actual — actually mostly OK, but "bueno" → 1 syllable by regex but 2 actual). The result is that readability scores may be biased upward (text appears easier than it is). |
| **Owner** | Project implementer (profile owner) |
| **Recommended next action** | (1) Add `re.UNICODE` flag to all signal regexes (Python 3 is Unicode by default, but explicit flag documents intent). (2) Replace `\b` with explicit Unicode-aware boundaries (`(?<![^\W\d_])` and `(?![^\W\d_])`) or use `re.findall` with explicit whitespace splitting. (3) Add a test in `tests/adintel/test_profile.py` that verifies accented text (e.g. "¡Urgente! Ayúdame hoy") scores the same as unaccented equivalent ("Urgente Ayudame hoy"). (4) Replace the syllable counter with a proper Spanish syllabifier (e.g. `silabeador` library) or document the limitation in the dashboard. |
| **Cross-refs** | [`MODEL_INVENTORY.json`](./MODEL_INVENTORY.json) `persuasive-profile-v1` `known_limitations`; `reports/adintel/challenge_round1_defects.md` R1-D04; Huerta (2007) in [`RESEARCH_LEDGER.md`](./RESEARCH_LEDGER.md) §2.7 |

---

## Risk summary table

| ID | Risk | Severity | Likelihood | Mitigation effectiveness | Owner |
|----|------|---------:|-----------:|-------------------------:|-------|
| RR-01 | Unauthenticated HTTP server exposes repo + raw HTML PII | Critical | High | None | Ops |
| RR-02 | Authorship model: no negative-pair evaluation | High | Medium | Partial (guardrails) | Model owner |
| RR-03 | All checkpoints uncalibrated | High | High | Partial (helpers exist) | Model owner |
| RR-04 | Cluster brand leakage near-total in 4/7 spaces | High | High | Partial (helper exists, not used) | Pipeline owner |
| RR-05 | No file-integrity manifest | High | Low | None | Ops |
| RR-06 | Stale documentation (1,589 vs 5,189) | Medium | High | None | Documentation owner |
| RR-07 | Open-set threshold conflated with pairwise | Medium | Medium | Partial (documented) | Model owner |
| RR-08 | No pipeline runner script for Stage 4b | Medium | High | Partial (API exists) | Implementer |
| RR-09 | LLM council subagent pipeline is opaque | Medium-High | Unknown | Partial (provenance fields) | Annotation owner |
| RR-10 | Spanish regex signals are ASCII-centric | Medium | Medium | Partial (strip_accents in vectorizers) | Profile owner |

---

## Risk heat map (severity × likelihood)

```
                  Likelihood
                Low    Medium   High    Unknown
Severity  Critical              RR-01
          High      RR-05  RR-02,07  RR-03,04,06
          Medium                  RR-10
          Medium-Hi                      RR-09
```

The cluster of risks in the High-severity × High-likelihood quadrant (RR-01, RR-03, RR-04, RR-06) represents the most urgent work. RR-01 (HTTP server) is the single highest-impact fix because it is the gateway for every other information-disclosure risk.

---

## Cross-references

- AI System Inventory: [`AI_SYSTEM_INVENTORY.md`](./AI_SYSTEM_INVENTORY.md)
- Architecture and data flow: [`ARCHITECTURE_AND_DATA_FLOW.md`](./ARCHITECTURE_AND_DATA_FLOW.md)
- Threat model: [`THREAT_MODEL.md`](./THREAT_MODEL.md)
- Model inventory: [`MODEL_INVENTORY.json`](./MODEL_INVENTORY.json)
- Metric catalog: [`METRIC_CATALOG.json`](./METRIC_CATALOG.json)
- Research ledger: [`RESEARCH_LEDGER.md`](./RESEARCH_LEDGER.md)
- Reproduction instructions: [`REPRODUCE.md`](./REPRODUCE.md)
- Project self-audit: `reports/adintel/challenge_round1_defects.md` (9 defects), `reports/adintel/challenge_round2_defects.md` (9 defects)

End of residual risk register.
