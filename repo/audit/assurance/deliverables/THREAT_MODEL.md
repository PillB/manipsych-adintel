# Threat Model — ManiPsych + adintel

**Audit artifact:** `audit/assurance/deliverables/THREAT_MODEL.md`
**Method:** STRIDE (Spoofing, Tampering, Repudiation, Information Disclosure, Denial of Service, Elevation of Privilege) augmented with the OWASP LLM Top 10 perspective where relevant.
**Scope:** the in-repo Python package, v1 tooling, trained models, data files, generated reports, the live HTTP server, and the (claimed but missing) PDF pipeline.
**Convention:** each threat lists assets, actors, entry points, trust boundaries, attack surface, STRIDE categorisation, severity, and current mitigation. Anything not verifiable on disk is marked `NOT VERIFIED — [reason]`.

---

## 1. Assets

### 1.1 Data assets

| Asset | Location | Sensitivity | Notes |
|-------|----------|-------------|-------|
| Raw HTML ad archive | `data/raw/ads/*.html` | Medium | Contains public web content; some ads may include user-visible contact info (phone, social handles) — PII redaction applies to derived data only, not raw |
| Processed ad manifest | `data/processed/ad_manifest.jsonl` | Medium | PII-redacted (`body_redacted` field) but still contains ad content; 5,189 records |
| Council annotations | `data/annotation/council_resolved_annotations.jsonl` | Medium | 5,717 annotations with span-level rationale text; rationale may quote ad surface text |
| Similarity links | `data/annotation/similarity_links.jsonl` | Medium | 642 known same-source pairs; reveals which ads share authors (de-anonymisation risk if cross-referenced) |
| Annotation SQLite store | `data/annotation/annotations.locked.sqlite3` | Medium | "Locked" but served read-only by `python3 -m http.server`; accessible to anyone with network access to port 8765 |
| Expert manual review | `data/annotation/expert_manual_review_round4.jsonl` | Medium-High | Contains expert judgements; could identify reviewer if attribution is present |
| Source / query bank | `data/sources/query_bank.json`, `harvested_seeds.jsonl`, `ad_sources.json`, `expanded_ad_sources.json`, `rejected_seed_urls.json` | Medium | Reveals the project's collection strategy; could be misused to evade future collection |

### 1.2 Model assets

| Asset | Location | Sensitivity | Notes |
|-------|----------|-------------|-------|
| v1 TF-IDF + OVR model | `models/manipulation_tfidf_ovr.joblib` (390 KB) | Medium | Trained on weak labels; full model weights including vocabulary; reproducible from manifest + detect_manipulation |
| Council TF-IDF + OVR model | `models/manipulation_council_tfidf_ovr.joblib` (3.4 MB) | Medium | Trained on 5,717 council annotations; larger vocabulary; reproducible |
| adintel package | `adintel/*.py` (10 modules, ~4,400 LOC) | Low | Source code; all weights and thresholds are visible |
| v1 tools | `tools/*.py` (50 scripts) | Low | Source code |

### 1.3 Report assets

| Asset | Location | Sensitivity | Notes |
|-------|----------|-------------|-------|
| v1 dashboard | `reports/ad_manipulation_report.html` (12.86 MB) | Medium | Self-contained; embeds 1,589 ranked ad excerpts (PII-redacted but ad content visible); served over HTTP |
| Unified dashboard | `reports/adintel/adintel_dashboard.html` (12.86 MB) | Medium | Same; embeds adintel pipeline outputs |
| Pipeline JSON outputs | `reports/adintel/*.json` (10 files) | Medium | Includes sample record IDs and similarity scores |
| Council inferences | `reports/council_candidate_inferences.json` (18.8 MB) | Medium | Full inferences dump; record-level |
| Council model report | `reports/council_candidate_model_report.json` | Low | Contains metrics, label counts, platform counts; no individual record data |
| Self-audit defects | `reports/adintel/challenge_round1_defects.md`, `challenge_round2_defects.md` | Low | Candid disclosure of 18 known defects |

### 1.4 Service assets

| Asset | Endpoint | Sensitivity | Notes |
|-------|----------|-------------|-------|
| Live HTTP server | `http://0.0.0.0:8765/` (pid 993) | High exposure | Static file server over the entire repo; no auth, no TLS, no rate limit |
| (claimed) PDF generator | `scripts/generate_final_report_pdf.py` | — | **NOT VERIFIED — does not exist in the repo** |

### 1.5 Integrity assets

| Asset | Verification |
|-------|--------------|
| Source code SHA-256s | Verified and recorded in [`AI_SYSTEM_INVENTORY.md`](./AI_SYSTEM_INVENTORY.md) §3 and §4 |
| Model SHA-256s | Verified — `manipulation_tfidf_ovr.joblib` = `6bb0fbe2…a05cecc`; `manipulation_council_tfidf_ovr.joblib` = `25b1bcab…9fe77b28` |
| Data file line counts | Verified — 5,189 / 5,717 / 642 |
| Annotation `text_hash` field | Present in annotation records (verified by inspecting first record); per-document SHA-256 of the source text |
| `record_id` field | `h_<sha256>` format (verified) |

---

## 2. Actors

| Actor | Trust level | Motivation | Notes |
|-------|-------------|------------|-------|
| Project implementer (developer) | High | Build the system | Has full filesystem access; the only actor who can sign off on model releases |
| Council subagent (LLM-driven annotation) | Medium | Generate technique-label proposals | Referenced in `accepted_actor_id` (e.g. `subagent_r5_a`); LLM-based, so susceptible to prompt injection via ad text |
| Scientist validator | Medium-High | Review council outputs | Human-in-the-loop check on subagent labels |
| Expert reviewer (round 4) | High | Adjudicate disputed labels | Final human authority on label quality |
| Dashboard end-user (analyst) | Medium | Read dashboards to understand the corpus | Reads HTML dashboards; should not need filesystem access |
| Anonymous network client | Low (untrusted) | Could be anyone | Can reach port 8765 from any routable network; no auth |
| Target of an ad (data subject) | N/A — passive | Privacy interest | The ad text describes them; never named by the system per the privacy guardrail |
| Ad author / source | Low (adversarial) | Evade detection or pollute the corpus | Could submit adversarial ad text via the public web (Stage 0) to influence future training |

---

## 3. Entry points

### 3.1 External entry points

| Entry point | Protocol | Trust boundary | Verified |
|-------------|----------|----------------|----------|
| Public web (Stage 0 collection) | HTTPS | External → repo | Yes — collection tools exist (`tools/collect_*`) |
| `python3 -m http.server 8765 --bind 0.0.0.0` | HTTP (cleartext) | Repo → any network client | Yes — `ps -fp 993` confirms; **binds to `0.0.0.0`, not `127.0.0.1`** |
| `AdIntelAPI` (in-process Python) | Python import | Within repo | Yes — but **NOT exposed over HTTP**; only callable from a Python process running on the host |
| (claimed) PDF generation | Filesystem | Within repo | **NOT VERIFIED — script does not exist** |
| Annotation studio | Static HTML | Repo → analyst browser | Yes — `annotation_app/index.html` (180 LOC) |

### 3.2 Internal entry points (function-level)

| Function | File | What it accepts | Risk |
|----------|------|-----------------|------|
| `adintel.api.AdIntelAPI.score_profile(text, record_id)` | `adintel/api.py:132` | Arbitrary `str` | Low — pure function, no I/O |
| `adintel.api.AdIntelAPI.pairwise_verify(left, right, ...)` | `adintel/api.py:173` | Two arbitrary strings | Low |
| `adintel.api.AdIntelAPI.cluster_all_spaces(records, texts, ...)` | `adintel/api.py:219` | Lists of dicts/strings | Medium — runs MiniBatchKMeans; CPU-bound; no upper bound on input size |
| `adintel.api.AdIntelAPI.detect_outliers(...)` | `adintel/api.py:249` | Lists of dicts/strings | Medium — runs TF-IDF + z-scores; CPU-bound |
| `tools/detect_manipulation.py:analyze_text(text)` | `tools/detect_manipulation.py:31` | stdin/argv text | Low |
| `tools/train_manipulation_model.py` | CLI | Manifest path | Low — local file only |
| `tools/generate_council_inferences_report.py` | CLI | Doc/annotation paths | Low |

---

## 4. Trust boundaries

```
┌─────────────────────────────────────────────────────────────────────────┐
│ EXTERNAL INTERNET (untrusted)                                           │
│   ┌──────────────────────────────────────────────────────────┐          │
│   │ Public ad sites (doplim, locanto, evisos, ciudadanuncios,│          │
│   │ facebook public pages)                                    │          │
│   └──────────────────────┬───────────────────────────────────┘          │
└──────────────────────────┼──────────────────────────────────────────────┘
                           │  Trust boundary TB-1 (web → repo)
                           │  Controls: PII redaction, target-term filter,
                           │            off-topic rejection, dedup
                           ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ REPO (semi-trusted)                                                     │
│   ┌──────────────────────────────────────────────────────────┐          │
│   │ data/raw/ads/*.html (immutable raw archive)               │          │
│   └──────────────────────┬───────────────────────────────────┘          │
│                          │  Trust boundary TB-2 (raw → processed)        │
│                          │  Controls: rebuild_manifest_from_raw gates    │
│                          ▼                                               │
│   ┌──────────────────────────────────────────────────────────┐          │
│   │ data/processed/ad_manifest.jsonl (PII-redacted)           │          │
│   └──────────────────────┬───────────────────────────────────┘          │
│                          │  Trust boundary TB-3 (manifest → labels)      │
│                          │  Controls: rule-based detector + council      │
│                          │            consensus + scientist validation   │
│                          ▼                                               │
│   ┌──────────────────────────────────────────────────────────┐          │
│   │ data/annotation/*.jsonl (resolved council labels)         │          │
│   └──────────────────────┬───────────────────────────────────┘          │
│                          │  Trust boundary TB-4 (labels → models)        │
│                          │  Controls: train/val/test split, metrics      │
│                          ▼                                               │
│   ┌──────────────────────────────────────────────────────────┐          │
│   │ models/*.joblib (trained weights)                         │          │
│   └──────────────────────┬───────────────────────────────────┘          │
│                          │  Trust boundary TB-5 (models → reports)       │
│                          │  Controls: self-contained HTML, vendored JS   │
│                          ▼                                               │
│   ┌──────────────────────────────────────────────────────────┐          │
│   │ reports/*.html, reports/adintel/*.json (outputs)          │          │
│   └──────────────────────┬───────────────────────────────────┘          │
│                          │  Trust boundary TB-6 (repo → HTTP)            │
│                          │  Controls: NONE (no auth, no TLS, 0.0.0.0)   │
│                          ▼                                               │
└──────────────────────────┼──────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ ANY NETWORK CLIENT (untrusted) — can read the entire repo via HTTP      │
│   including data/, models/, audit/, etc.                                │
└─────────────────────────────────────────────────────────────────────────┘
```

**Critical observation:** trust boundary TB-6 has **no controls**. The `python3 -m http.server` exposes the whole repo tree, not just `reports/`. Any client that can reach port 8765 can `GET /data/processed/ad_manifest.jsonl`, `GET /models/manipulation_council_tfidf_ovr.joblib`, `GET /audit/assurance/deliverables/THREAT_MODEL.md` (this very file), etc.

---

## 5. Attack surface

| Surface | Exposure | Risk |
|---------|----------|------|
| Port 8765 (HTTP, 0.0.0.0) | Any routable client | High — full repo read access |
| `data/raw/ads/*.html` (10,293 files) | Filesystem + HTTP | Medium — could be exfiltrated |
| `data/processed/ad_manifest.jsonl` | Filesystem + HTTP | Medium — 5,189 records of PII-redacted but ad-content-visible data |
| `data/annotation/annotations.locked.sqlite3` | Filesystem + HTTP | Medium — "locked" implies write-protection, but the file is still readable |
| `models/*.joblib` | Filesystem + HTTP | Low-Medium — model weights could be exfiltrated and reused; reproducible from data anyway |
| `tools/` (50 scripts) | Filesystem + HTTP | Low — source code is open by intent |
| `adintel/` (10 modules) | Filesystem + HTTP | Low — source code is open by intent |
| `audit/` (this directory) | Filesystem + HTTP | Low-Medium — exposes the project's own weaknesses |
| `AdIntelAPI.detect_outliers(...)` (in-process) | Python only | Low — but no input-size cap could cause resource exhaustion |
| `AdIntelAPI.cluster_all_spaces(...)` (in-process) | Python only | Low — same caveat |
| Council subagent pipeline (Stage 2b) | Not exposed | Low — but accepts ad text as input; vulnerable to prompt injection if the subagent is an LLM |

---

## 6. STRIDE threats

### S — Spoofing

| ID | Threat | Vector | Severity | Likelihood | Current mitigation |
|----|--------|--------|---------:|-----------:|--------------------|
| S-1 | Anonymous client spoofs a trusted analyst to read dashboards | HTTP server has no authentication | High | High | **None** — `python3 -m http.server` serves everything to anyone |
| S-2 | Ad author submits content that mimics a different author's style to pollute authorship clustering | Stage 0 collection | Medium | Medium | None — authorship clustering uses char-5-gram TF-IDF; an attacker who can read the model could craft adversarial text |
| S-3 | Council subagent is spoofed by an LLM prompt-injection inside ad text | Stage 2b annotation | Medium | Medium-Low | `accepted_actor_id` field records the subagent; `agreement` field records consensus; scientist validation gate exists |
| S-4 | `record_id` is `h_<sha256>` of canonical URL — if URLs are attacker-controlled, record_ids are attacker-computable, enabling record-id collisions | Stage 0/1 | Low | Low | Dedup by `canonical_url_hash` and `normalized_text_hash` (in `metadata`) — verified by reading `reports/raw_rebuild_summary.json` |
| S-5 | (claimed) PDF generation spoofed by a malicious `download/*.pdf` swap | Filesystem | Low | Low | **NOT VERIFIED — PDF pipeline does not exist** |

### T — Tampering

| ID | Threat | Vector | Severity | Likelihood | Current mitigation |
|----|--------|--------|---------:|-----------:|--------------------|
| T-1 | Attacker modifies `data/processed/ad_manifest.jsonl` to inject labelled-bad records | Filesystem | High | Low (filesystem is local) | None — file is writable by the `z` user; no checksum manifest; `data/processed/ad_manifest.jsonl.state.json` exists but is just rebuild state, not a tamper-evident log |
| T-2 | Attacker modifies `models/*.joblib` to backdoor predictions | Filesystem | High | Low | None — no signature on joblib files; SHA-256s recorded only in this audit (post-hoc, not enforced) |
| T-3 | Attacker modifies `reports/adintel/adintel_dashboard.html` to inject malicious JS | Filesystem + HTTP | High | Low | Partial — dashboards are described as "self-contained, no CDN"; but if the file itself is tampered, no integrity check |
| T-4 | Attacker modifies `data/annotation/council_resolved_annotations.jsonl` to flip labels | Filesystem | High | Low | Partial — `annotations.locked.sqlite3` exists (write-protected) but the JSONL export is plain text |
| T-5 | Adversarial ad text submitted via Stage 0 tampers with future model training | Stage 0 → Stage 3 | Medium | Low | Partial — `tools/redact_pii.py` runs; dedup catches duplicates; no adversarial-robustness evaluation |
| T-6 | `tools/detect_manipulation.py` rule set is hand-edited to weaken detection | Filesystem | Medium | Low | None — rules are in plain source; changes tracked only by git (not in scope of this audit) |

### R — Repudiation

| ID | Threat | Vector | Severity | Likelihood | Current mitigation |
|----|--------|--------|---------:|-----------:|--------------------|
| R-1 | Council subagent denies producing a label | Annotation provenance | Medium | Low | Partial — `accepted_actor_id`, `accepted_round`, `provenance` fields in annotation spans (verified) |
| R-2 | Analyst denies reading a dashboard | HTTP server logs | Low | Medium | **None** — `python3 -m http.server` logs to stderr but does not record client identity or which files were accessed beyond default access logs |
| R-3 | Model trainer denies the training data used | Reproducibility | Medium | Low | Partial — `reports/council_candidate_model_report.json` records `annotation_source`, `split_counts`, `label_counts`; but `data/processed/modeling_manifest.jsonl` is missing |
| R-4 | Pipeline runner denies which adintel outputs were generated | Reproducibility | Low | Low | Partial — `pipeline_results.json:ran_at` and `elapsed_s` exist; no git SHA recorded |

### I — Information Disclosure

| ID | Threat | Vector | Severity | Likelihood | Current mitigation |
|----|--------|--------|---------:|-----------:|--------------------|
| I-1 | PII in `data/raw/ads/*.html` is exposed over HTTP | Port 8765 | High | High | **Insufficient** — `redact_pii.py` redacts PII in the *processed* manifest only; raw HTML still contains phone numbers, social handles, etc., and is served over HTTP at `GET /data/raw/ads/<file>.html` |
| I-2 | PII in `body_redacted` is incomplete (redactor missed something) | Stage 1 | Medium | Medium | Partial — `tools/redact_pii.py` exists with regex patterns; tests in `tests/test_redact_pii.py` (5 test functions) cover common patterns |
| I-3 | `data/annotation/similarity_links.jsonl` reveals which ads share authors | Port 8765 + filesystem | Medium | Medium | Partial — file is in-repo; no access control; ad authors could be indirectly identified if their ad text is unique |
| I-4 | `reports/ad_manipulation_ranking.json` exposes ad excerpts (title + first 200 chars of body) | Port 8765 | Medium | High | Partial — 1,589 records ranked with excerpts; PII-redacted but ad content visible |
| I-5 | Council annotation rationale text quotes ad surface | Port 8765 | Medium | High | Partial — `rationale` field in spans may quote the ad; redaction is on the manifest, not on the rationale |
| I-6 | The `audit/` directory itself exposes the project's weaknesses to anyone with port 8765 access | Port 8765 | Medium | High | None — `python3 -m http.server` serves `audit/` recursively |
| I-7 | Ad author is named based on model similarity | Authorship module | Critical | Low | **Strong guardrail** — `adintel/authorship.py:assert_no_person_named()` raises `AssertionError` if `person_named=True`; `person_named` is hardcoded `False` everywhere; `adintel/evidence.py:assert_authorship_does_not_identify_person()` is a redundant API-boundary check; tested in `tests/adintel/test_authorship.py` (19 tests) |
| I-8 | Dashboard embeds record_id (`h_<sha256>`) which could be reverse-looked-up | HTTP | Low | Low | Partial — record_ids are SHA-256 hashes of canonical URLs; reversing requires knowing the URL set |
| I-9 | `council_candidate_model_report.json` exposes the developer's local path (`/Users/pabloillescas/...`) | Port 8765 | Low | High (already happened) | None — the file is already in the repo; should be redacted |
| I-10 | LLM-driven council subagent leaks ad text to an external LLM API | Stage 2b | Medium | Unknown | **NOT VERIFIED — no LLM client code is in the repo**; if the council uses an external LLM, ad text is sent off-host |

### D — Denial of Service

| ID | Threat | Vector | Severity | Likelihood | Current mitigation |
|----|--------|--------|---------:|-----------:|--------------------|
| D-1 | Anonymous client downloads the 12.86 MB dashboards repeatedly to saturate bandwidth | Port 8765 | Medium | Medium | **None** — no rate limit on `python3 -m http.server` |
| D-2 | Anonymous client crawls `data/raw/ads/` (10,293 files) to exhaust file descriptors | Port 8765 | Low | Low | None |
| D-3 | In-process `AdIntelAPI.cluster_all_spaces(records, texts)` called with very large inputs | Python only | Low | Low | Partial — `evaluate_stability` has a 2000-point subsample cap; `cluster_space` falls back to "all in one cluster" if `n < k`; but no hard upper bound on input size |
| D-4 | `AdIntelAPI.detect_outliers(...)` called with very large inputs | Python only | Low | Low | Partial — most detectors early-return if `len(records) < 5`; no upper bound |
| D-5 | Disk exhaustion from large `reports/council_candidate_inferences.json` (18.8 MB) or duplicated backups | Filesystem | Low | Low | None — multiple `.bak_*` / `.pii_*` / `.dupfix_*` copies of `ad_manifest.jsonl` exist in `data/processed/` (verified by `LS`) |

### E — Elevation of Privilege

| ID | Threat | Vector | Severity | Likelihood | Current mitigation |
|----|--------|--------|---------:|-----------:|--------------------|
| E-1 | Anonymous client finds an arbitrary-file-read primitive in `python3 -m http.server` (it is a stdlib demo server) | Port 8765 | High | Low (stdlib server is well-audited but explicitly not for production) | **None** — Python docs explicitly warn against using `http.server` in production |
| E-2 | Path traversal in HTTP server returns files outside `/home/z/my-project/repo` | Port 8765 | Medium | Low | Partial — `python3 -m http.server --directory /home/z/my-project/repo` should confine traversal to that directory; not penetration-tested |
| E-3 | Adversarial ad text in Stage 0 triggers a code-execution bug in a Playwright/Selenium collector | Stage 0 | High | Low | Partial — collectors use headless browsers; browser sandbox contains most risk |
| E-4 | Council subagent prompt injection causes arbitrary code execution in the annotation pipeline | Stage 2b | High | Unknown | **NOT VERIFIED — no LLM client code in the repo** |
| E-5 | `tools/` scripts use `eval`/`exec`/`subprocess.shell=True` on user input | Filesystem | Medium | Low | **NOT VERIFIED — not audited line-by-line for unsafe deserialisation**; joblib.load is used (which can execute arbitrary code if the pickle is malicious) |
| E-6 | Maliciously-crafted `models/*.joblib` executes code on load | Filesystem | High | Low | None — `joblib.load` is unsafe by design; trust depends on file integrity |

---

## 7. Priority threats (top 5)

Ranked by Severity × Likelihood, with current-mitigation effectiveness factored in.

1. **I-1 (PII in raw HTML exposed over HTTP) — Critical.** The `python3 -m http.server` exposes `data/raw/ads/*.html` (10,293 files) with no authentication, and PII redaction only applies to the derived manifest. Phone numbers, social handles, and other contact info in the raw HTML are reachable by any network client.
2. **S-1 / I-6 (Anonymous client reads entire repo including audit/) — Critical.** The HTTP server has no auth, no TLS, and binds to `0.0.0.0`. Anyone with network reach can read models, data, source, and this very audit. This violates the principle of least exposure.
3. **T-2 / E-6 (Model tampering / malicious joblib) — High.** No signature or integrity check on `models/*.joblib`. A tampered model file would be loaded with `joblib.load` and could execute arbitrary code. SHA-256s recorded in this audit are not enforced anywhere.
4. **I-3 / I-4 / I-5 (Ad-content and similarity information disclosure) — High.** Multiple JSON and HTML artifacts expose ad text, similarity relationships, and annotation rationales. While PII is redacted in the manifest, the rationale text in annotations may quote surface strings, and `similarity_links.jsonl` reveals same-source relationships.
5. **I-10 / E-4 (Council subagent LLM data leakage) — Medium-High but unknown.** The council annotation pipeline references `subagent_r5_a` and similar actor IDs, strongly suggesting an LLM is involved. **NOT VERIFIED — no LLM client code is in the repo**, so we cannot confirm whether ad text is sent off-host to an LLM provider. If it is, that is an uncontrolled information disclosure.

---

## 8. Existing mitigations (what is already in place)

| Mitigation | Location | Effectiveness |
|------------|----------|---------------|
| PII redaction (`tools/redact_pii.py`) | Stage 1 | Medium — covers phone/email/ID patterns; regex-based, so miss-prone |
| Off-topic + seeker-only rejection | `tools/rebuild_manifest_from_raw.py` | Medium — corpus-quality filter |
| Dedup by `canonical_url_hash` and `normalized_text_hash` | Stage 1 | High — verified by `raw_rebuild_summary.json:dedup_counts` |
| Locked annotation SQLite store | `data/annotation/annotations.locked.sqlite3` | Low — write-protected but readable; the JSONL export is plain text |
| `person_named=False` hard guardrail | `adintel/authorship.py` | High — verified by code reading and 19 authorship tests |
| `assert_no_universal_score` guard | `adintel/evidence.py` | High — runtime assertion prevents collapsing 17 dimensions into a single score |
| `assert_authorship_does_not_identify_person` | `adintel/evidence.py` | High — redundant API-boundary check |
| Causal-language linter | `adintel/evidence.py:lint_claim_text` | Medium — flags causal verbs without strength qualifiers in claim text |
| `should_route_to_human` disagreement rule | `adintel/checkpoints.py` | Medium — routes to human review when ≥1 checkpoint abstains or disagrees |
| `average_calibrated_only` rule | `adintel/checkpoints.py` | High — refuses to average uncalibrated model scores (all current checkpoints are `uncalibrated`, so averaging is forbidden by design) |
| Self-contained HTML dashboards | `reports/*.html` | High — no external CDN, no fetch/AJAX; verified by HTML head inspection |
| Vendored mini-D3 helper | `reports/assets/d3-lite-force.js` | High — 89 LOC, auditable, no external dependency |
| Train/val/test split + challenge set | Stage 3b | High — verified by `split_counts` in council model report |
| Limitations disclosure in model report | `reports/council_candidate_model_report.json:limitations` | High — 3 explicit limitations listed |
| 18-defect self-audit | `reports/adintel/challenge_round{1,2}_defects.md` | High — candid, evidence-graded defect ledger |

---

## 9. Mitigation gaps

| Gap | Affected threats | Recommended fix |
|-----|------------------|-----------------|
| No HTTP authentication or TLS | S-1, I-1, I-6, D-1 | Replace `python3 -m http.server` with a proper static-file server behind TLS + basic auth; bind to `127.0.0.1` if external access is not required |
| No file-integrity manifest | T-1, T-2, T-3, T-4, E-6 | Generate and commit a SHA-256 manifest of all data/model/report files; verify on boot |
| No signature on joblib models | T-2, E-6 | Sign model files with a project key; refuse to load unsigned models |
| No LLM-client audit | I-10, E-4 | If the council uses external LLMs, document the data flow, redact ad text before sending, log all calls |
| No rate limiting | D-1, D-2 | Add rate limiting to the HTTP server |
| No input-size caps in `AdIntelAPI` | D-3, D-4 | Add explicit `max_records` parameters with sensible defaults |
| Stale documentation (1,589 records) | R-3 | Regenerate or deprecate `reports/dataset_manifest.md` and `reports/ad_manipulation_ranking.json` |
| Developer-machine path in `council_candidate_model_report.json` | I-9 | Redact `/Users/pabloillescas/...` from the JSON |
| Raw HTML served over HTTP | I-1 | Do not serve `data/raw/` over HTTP; restrict to `reports/` only |
| No pipeline runner script for adintel stage 4b | R-3, R-4 | Commit the runner that produced `reports/adintel/*.json` |
| No PDF generation script | (claimed) | Either add the script or remove the claim from project documentation |

---

## 10. Cross-references

- AI System Inventory: [`AI_SYSTEM_INVENTORY.md`](./AI_SYSTEM_INVENTORY.md)
- Architecture and data flow: [`ARCHITECTURE_AND_DATA_FLOW.md`](./ARCHITECTURE_AND_DATA_FLOW.md)
- Model inventory: [`MODEL_INVENTORY.json`](./MODEL_INVENTORY.json)
- Residual risk register: [`RESIDUAL_RISK_REGISTER.md`](./RESIDUAL_RISK_REGISTER.md)

End of threat model.
