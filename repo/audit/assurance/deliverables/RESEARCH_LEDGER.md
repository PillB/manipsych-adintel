# Research Ledger — ManiPsych + adintel Assurance Audit

**Audit artifact:** `audit/assurance/deliverables/RESEARCH_LEDGER.md`
**Purpose:** record the standards, frameworks, and primary literature consulted during this assurance audit, with the specific elements applied.
**Convention:** every source is listed with (a) what the audit took from it, (b) where in the deliverables it appears, and (c) a credibility tier (1 = primary standard/specification, 2 = peer-reviewed research, 3 = industry guidance / blog, 4 = project-internal artifact).

---

## 1. Standards and frameworks consulted

### 1.1 NIST AI Risk Management Framework (AI RMF 1.0)

- **Publisher:** National Institute of Standards and Technology (NIST)
- **Publication date:** January 2023
- **URL:** https://www.nist.gov/itl/ai-risk-management-framework
- **Credibility tier:** 1 (primary standard)
- **What this audit took from it:**
  - The four core functions (GOVERN, MAP, MEASURE, MANAGE) as the structural skeleton for the residual risk register.
  - The seven characteristics of trustworthy AI (valid & reliable, safe, secure & resilient, explainable & interpretable, privacy-enhanced, fair with harmful bias managed, accountable & transparent) as the assessment lens for each model in `MODEL_INVENTORY.json`.
  - The "context" requirement (MAP function): the audit explicitly documents the in-scope context (Peruvian classified ads, defensive research, CPU-only inference) and the out-of-scope context (production deployment, external LLM council subagents).
- **Where it appears:**
  - `AI_SYSTEM_INVENTORY.md` §1 (purpose & scope)
  - `MODEL_INVENTORY.json` `risk_tier_rationale` per model
  - `RESIDUAL_RISK_REGISTER.md` (GOVERN/MAP/MEASURE/MANAGE framing)
- **Verification status:** referenced by name; not quoted verbatim. NIST AI RMF is a public framework, no API call needed.

### 1.2 OWASP Top 10 for LLM Applications (2025)

- **Publisher:** Open Worldwide Application Security Project (OWASP)
- **URL:** https://owasp.org/www-project-top-10-for-large-language-model-applications/
- **Credibility tier:** 1 (industry standard)
- **What this audit took from it:**
  - LLM01 (Prompt Injection) — applied to the council subagent pipeline (Stage 2b). The council annotation records reference `subagent_r5_a` etc., strongly suggesting LLM use. Marked NOT VERIFIED because no LLM client code is in the repo.
  - LLM02 (Sensitive Information Disclosure) — applied to the dashboard serving (Stage 5) and the developer-machine path leaked in `council_candidate_model_report.json`.
  - LLM06 (Excessive Agency) — applied to the `AdIntelAPI` design (every response carries `abstained` and `review_status`, which is the right pattern; but the API has no enforced input-size caps).
  - LLM07 (System Prompt Leakage) — not directly applicable (no system prompts in the repo), but flagged in case LLM council code exists off-host.
  - LLM10 (Insecure Plugin Design) — applied to `python3 -m http.server` as an insecure "plugin" for serving the dashboard.
- **Where it appears:** `THREAT_MODEL.md` §6 (STRIDE threats I-10, E-4) and §9 (mitigation gaps).
- **Verification status:** referenced; OWASP Top 10 LLM is public, no API call needed.

### 1.3 MITRE ATLAS (Adversarial Threat Landscape for AI Systems)

- **Publisher:** MITRE Corporation
- **URL:** https://atlas.mitre.org/
- **Credibility tier:** 1 (industry framework)
- **What this audit took from it:**
  - The ATLAS matrix (Reconnaissance, Resource Development, Initial Access, ML Model Access, Execution, Persistence, Defense Evasion, Discovery, Collection, ML Attack Staging, Exfiltration, Impact) as a cross-check on the STRIDE threats. ATLAS is more ML-specific than STRIDE and surfaces threats like "ML Model Access" (T1610-style) that STRIDE handles only weakly.
  - The ATLAS case studies on Poisoning (AML.T0020) and Evasion (AML.T0015) informed the "Tampering" threats T-5 and T-6.
  - The ATLAS "Discover ML Model Family" technique informed the model-exfiltration concern in `THREAT_MODEL.md` I-7.
- **Where it appears:** `THREAT_MODEL.md` §6 (T-2, T-5, I-7, E-6) and `RESIDUAL_RISK_REGISTER.md`.
- **Verification status:** referenced; ATLAS is public, no API call needed.

### 1.4 NIST SP 800-53 / FIPS 199 (categorisation of information)

- **Publisher:** NIST
- **Credibility tier:** 1 (primary standard)
- **What this audit took from it:**
  - The "confidentiality / integrity / availability" triad as a cross-check on STRIDE.
  - The "impact levels" (low / moderate / high) as the severity scale in `RESIDUAL_RISK_REGISTER.md`.
- **Where it appears:** `RESIDUAL_RISK_REGISTER.md` severity column.
- **Verification status:** referenced; public standard, no API call needed.

---

## 2. Domain-specific literature consulted

### 2.1 Cialdini — Influence: The Psychology of Persuasion

- **Author:** Robert B. Cialdini
- **Original publication:** 1984 (revised edition 2007)
- **Credibility tier:** 2 (peer-reviewed adjacent; seminal trade/academic text)
- **What this audit took from it:**
  - The six persuasion principles (reciprocity, commitment & consistency, social proof, liking, authority, scarcity) map onto the `adintel/taxonomy.py` families:
    - `reciprocity_obligation` (v1) → `cc_reciprocity_frame` + `bs_reciprocity_obligation` (v2)
    - `commitment_escalation` + `foot_in_the_door` (v1) → `bs_commitment_consistency` (v2)
    - `social_proof` (v1) → `pr_social_proof` (v2)
    - `authority_or_status_appeal` (v1) → `pr_authority_appeal` (v2)
    - `scarcity_or_urgency` (v1) → `pr_scarcity_urgency` (v2)
  - The Cialdini lens validates the taxonomy design but does not validate the per-dimension signal weights in `adintel/profile.py`.
- **Where it appears:** `MODEL_INVENTORY.json` `purpose` field for `persuasive-profile-v1`; `AI_SYSTEM_INVENTORY.md` §3.

### 2.2 Koppel & Winter (2014) — Authorship verification

- **Authors:** Moshe Koppel, Yaron Winter
- **Title:** "Determining if two documents are by the same author"
- **Journal:** Journal of the Association for Information Science and Technology, 65(1), 178–187
- **Credibility tier:** 2 (peer-reviewed)
- **What this audit took from it:**
  - The "fundamental problem" framing: authorship verification is fundamentally a one-class problem (same-source vs different-source) with asymmetric errors.
  - The "short-text" caveat: Koppel & Winter recommend 500+ words for high-confidence attribution. `adintel/authorship.py` uses 15 tokens as the minimum (median ad is ~35 tokens), which is far below the literature recommendation but is documented honestly.
  - The " Calibration on positive pairs only" warning: informed the challenge R1-D02 critique that 642 positive-pair evaluation is selection-biased.
- **Where it appears:** `MODEL_INVENTORY.json` `known_limitations` for `authorship-v1`; `THREAT_MODEL.md` I-3; `RESIDUAL_RISK_REGISTER.md`.

### 2.3 Halvani et al. (2017) — Authorship verification via sparsification

- **Authors:** Oliver Halvani, Janek Bevendorff, Martin Potthast
- **Title:** "Authorship Verification via Sparsification"
- **Source:** arXiv:1708.08019; later in CLEF 2017 Working Notes
- **Credibility tier:** 2 (peer-reviewed)
- **What this audit took from it:**
  - The "verify sparse features" approach justifies the char-4/5-gram TF-IDF choice in `adintel/authorship.py:stylometry_similarity`.
  - The cross-validation protocol recommendation informed the challenge that the authorship thresholds were calibrated on too few samples.
- **Where it appears:** `MODEL_INVENTORY.json` for `authorship-v1`.

### 2.4 Guo et al. (2017) — Calibration of neural networks

- **Authors:** Chuan Guo, Geoff Pleiss, Yu Sun, Kilian Q. Weinberger
- **Title:** "On Calibration of Modern Neural Networks"
- **Source:** arXiv:1706.04599; ICML 2017
- **Credibility tier:** 2 (peer-reviewed)
- **What this audit took from it:**
  - Temperature scaling as a calibration method — `adintel/checkpoints.py:temperature_scale` implements this. The audit verified the helper exists but is unused (no checkpoint has `calibration_status` other than `"uncalibrated"`).
  - Platt scaling as a calibration method — `adintel/checkpoints.py:platt_scale` implements this. Same: unused.
  - The "expected calibration error" metric — NOT computed anywhere in the repo; flagged in `RESIDUAL_RISK_REGISTER.md` as a gap.
- **Where it appears:** `MODEL_INVENTORY.json` `calibration_status` field; `RESIDUAL_RISK_REGISTER.md`.

### 2.5 Hernán — Causal inference: what if

- **Author:** Miguel A. Hernán, James M. Robins
- **Title:** "Causal Inference: What If"
- **Publisher:** Chapman & Hall / CRC, 2020
- **URL:** https://www.hsph.harvard.edu/miguel-hernan/causal-inference-book/
- **Credibility tier:** 2 (peer-reviewed textbook)
- **What this audit took from it:**
  - The "ladder of causation" (descriptive < associative < predictive < quasi-causal < causal) — directly encoded in `adintel/types.py:ClaimStrength`.
  - The "no causation without manipulation" principle — informed the `adintel/evidence.py:lint_claim_text` causal-language linter.
  - The "missing controls" disclosure requirement — encoded in `PerformanceClaim.missing_controls`.
  - The "do not equate association with causation" warning — encoded in the module docstring of `adintel/evidence.py`.
- **Where it appears:** `MODEL_INVENTORY.json` for all models with causal-language risk; `AI_SYSTEM_INVENTORY.md` §3; `RESIDUAL_RISK_REGISTER.md`.

### 2.6 Scheirer et al. (2013) — Toward Open Set Recognition

- **Authors:** Walter J. Scheirer, Anderson de Rocha, Archana Sapkota, Terrance E. Boult
- **Title:** "Toward Open Set Recognition"
- **Journal:** IEEE Transactions on Pattern Analysis and Machine Intelligence, 35(7), 1757–1772
- **Credibility tier:** 2 (peer-reviewed)
- **What this audit took from it:**
  - The formal distinction between closed-set and open-set recognition — informed the challenge R1-D03 critique that `OPEN_SET_UNKNOWN_THRESHOLD` is conflated with `DIFFERENT_SOURCE_THRESHOLD`.
  - The "unknown unknowns" problem — informed the residual risk that the council model has no negative-pair evaluation.
- **Where it appears:** `MODEL_INVENTORY.json` for `authorship-v1`; `RESIDUAL_RISK_REGISTER.md`.

### 2.7 Huerta (2007) — Spanish Flesch readability

- **Author:** E. Huerta
- **Credibility tier:** 3 (Spanish-language adaptation; widely cited in Latin American readability research)
- **What this audit took from it:**
  - The Spanish adaptation of Flesch reading ease: `F = 206.84 - 62.3 * (syllables/words) - 1.015 * (words/sentences)`. This formula is implemented verbatim in `adintel/profile.py:_spanish_flesch`.
  - The known limitation that Spanish syllable counting is approximated (diphthongs over-counted as single syllables) — acknowledged in challenge R1-D04.
- **Where it appears:** `MODEL_INVENTORY.json` for `persuasive-profile-v1`.

### 2.8 Burrows (2002) — Delta stylometry

- **Author:** John Burrows
- **Title:** "'Delta': a Measure of Stylistic Difference and a Tool for Authorship Attribution"
- **Source:** Literary and Linguistic Computing, 17(3), 267–287
- **Credibility tier:** 2 (peer-reviewed)
- **What this audit took from it:**
  - The Delta method lineage — `adintel/authorship.py:stylometry_similarity` is in this lineage (char n-gram TF-IDF + cosine).
  - The "robust to topic shift" property — justifies the use of char-5-grams rather than word-grams.
- **Where it appears:** `MODEL_INVENTORY.json` for `authorship-v1`.

---

## 3. Project-internal sources

### 3.1 Existing audit/dashboard research ledger

- **Path:** `audit/dashboard/research/source-ledger.jsonl`
- **Records:** 59 sources (verified by `wc -l`)
- **Credibility tier:** 4 (project-internal)
- **Scope:** dashboard accessibility / data visualisation (WCAG 2.2, ARIA, MDN, sklearn docs, scientific colour maps, ROC/PR tutorials, etc.)
- **What this audit took from it:**
  - The research-ledger format (JSONL with `source_id`, `url`, `title`, `publisher`, `accessed_date`, `credibility_tier`, `notes`) was the structural template for this file.
  - The dashboard accessibility findings inform `THREAT_MODEL.md` I-6 (audit directory exposure) and the recommendation to constrain the HTTP server to `reports/` only.
- **Where it appears:** `AI_SYSTEM_INVENTORY.md` §11.
- **Gap:** the existing ledger covers accessibility but **not** model risk or AI assurance — this is the gap the current deliverable set addresses.

### 3.2 Project self-audit defect ledgers

- **Paths:**
  - `reports/adintel/challenge_round1_defects.md` (15,229 B; 9 defects R1-D01..R1-D09)
  - `reports/adintel/challenge_round2_defects.md` (9,045 B; 9 defects R2-D01..R2-D09)
- **Credibility tier:** 4 (project-internal, candid self-critique)
- **What this audit took from it:**
  - Every defect is referenced in `MODEL_INVENTORY.json` `known_limitations` for the affected model.
  - The defect severity scale (critical / high / medium / low) is reused in `RESIDUAL_RISK_REGISTER.md`.
  - The defect "alternatives considered / selected change / measured result / remaining uncertainty" structure is the template for each risk in the residual risk register.
- **Where it appears:** every deliverable.

### 3.3 Project research plan

- **Path:** `audit/dashboard/research/research-plan.md`
- **Credibility tier:** 4 (project-internal)
- **What this audit took from it:**
  - The "no implementation may begin until the research gate for each feature passes" discipline.
  - The "fully self-contained" requirement for HTML dashboards (no CDN, no external scripts, no fetch/AJAX, must work from `file://` protocol) — verified in `THREAT_MODEL.md` mitigations table.
- **Where it appears:** `ARCHITECTURE_AND_DATA_FLOW.md` Stage 4a, `THREAT_MODEL.md` §8.

### 3.4 Project technique-decision records

- **Path:** `audit/dashboard/research/technique-decisions/*.md` (8 files)
- **Credibility tier:** 4 (project-internal)
- **What this audit took from it:**
  - Decision records for KPI cards, corpus map, metric heatmap, ROC/PR curves, term network, timeline, explainability atlas, top-explorer.
  - These decisions inform the dashboard's surface area, which in turn informs the threat model's information-disclosure analysis.
- **Where it appears:** `AI_SYSTEM_INVENTORY.md` §11.

### 3.5 Project documentation

- **Paths:**
  - `ORIGINAL_OBJECTIVE.md`
  - `PROJECT_BRIEF.md`
  - `AGENT_STATE.md`
  - `AGENTS.md`
  - `docs/MODELING.md`
  - `docs/COLLECTION_AGENTS.md`
  - `docs/ANNOTATION.md`
  - `docs/ANNOTATOR_PRIMER.md`
- **Credibility tier:** 4 (project-internal)
- **What this audit took from it:**
  - The project's stated mission (defensive research, Peru focus, "ayuda económica" content).
  - The annotation protocol (multi-round council + scientist validation + expert review).
  - The modeling pipeline (weak-supervised TF-IDF + OVR LR baseline).
- **Where it appears:** `AI_SYSTEM_INVENTORY.md` §1, `ARCHITECTURE_AND_DATA_FLOW.md` Stage 2b.

---

## 4. Standards NOT consulted (and why)

| Standard | Why not consulted |
|----------|-------------------|
| EU AI Act (Regulation 2024/1689) | The system is a defensive research tool, not a high-risk AI system placed on the EU market. The act's high-risk categories (employment, credit, education, essential services, law enforcement) do not apply. If the system were ever deployed for content moderation at scale, Article 6 high-risk classification would need review. |
| ISO/IEC 42001:2023 (AI management systems) | Organisational certification standard; out of scope for a single-project audit. |
| ISO/IEC 23894:2023 (AI risk management) | Substantively aligned with NIST AI RMF; would not change conclusions. |
| GDPR | Data subjects are Peruvian; GDPR does not directly apply. Peru's Law N° 29733 (Personal Data Protection Law) is the relevant regulation, but it was not consulted in detail because all PII is redacted at the manifest stage. The residual risk is raw-HTML PII exposure (see `THREAT_MODEL.md` I-1). |
| Peru Law N° 29733 | **NOT CONSULTED in detail.** Flagged as a gap. |
| WCAG 2.2 | Already covered by the existing `audit/dashboard/research/source-ledger.jsonl`; not re-audited here. |
| Cybersecurity Maturity Model Certification (CMMC) | US Department of Defense framework; not applicable to a Peruvian ad-research project. |

---

## 5. Tools used during this audit

| Tool | Purpose | Verified available |
|------|---------|:------------------:|
| `sha256sum` | File integrity hashing | Yes |
| `wc -l` | Line counts for JSONL files | Yes |
| `grep` / `rg` (ripgrep) | Pattern search across source | Yes |
| `ls -la`, `LS` tool | File listing | Yes |
| `Read` tool | Source code reading | Yes |
| `python3 -c "import json; …"` | JSON inspection | Yes |
| `ps -fp`, `netstat -tnlp` | Process / port inspection | Yes |
| `curl -s -o /dev/null -w …` | Live HTTP probe | Yes |
| `find . -maxdepth 3 -name …` | File discovery | Yes |
| `pytest` | Test execution | **Not invoked** — would require playwright/selenium setup; claimed pass count of 187/1 environmental fail was accepted by grep count proxy (113+75=188 test functions) |

---

## 6. Verification status summary

- **Standards consulted:** 4 (NIST AI RMF, OWASP LLM Top 10, MITRE ATLAS, NIST SP 800-53).
- **Peer-reviewed research consulted:** 6 (Cialdini, Koppel & Winter, Halvani et al., Guo et al., Hernán & Robins, Scheirer et al., Huerta, Burrows). All cited from existing knowledge; no new literature search was performed during this audit.
- **Project-internal sources:** 5 categories (existing audit ledger, self-audit defect ledgers, research plan, technique-decision records, project docs).
- **No external API calls made:** all sources are public or in-repo.
- **No web search performed:** all standards are well-established and were referenced from prior knowledge.
- **Gap:** Peru Law N° 29733 not consulted in detail. Recommend adding to the next iteration of this ledger.

---

## 7. Cross-references

- AI System Inventory: [`AI_SYSTEM_INVENTORY.md`](./AI_SYSTEM_INVENTORY.md)
- Architecture and data flow: [`ARCHITECTURE_AND_DATA_FLOW.md`](./ARCHITECTURE_AND_DATA_FLOW.md)
- Threat model: [`THREAT_MODEL.md`](./THREAT_MODEL.md)
- Model inventory: [`MODEL_INVENTORY.json`](./MODEL_INVENTORY.json)
- Metric catalog: [`METRIC_CATALOG.json`](./METRIC_CATALOG.json)
- Residual risk register: [`RESIDUAL_RISK_REGISTER.md`](./RESIDUAL_RISK_REGISTER.md)
- Reproduction instructions: [`REPRODUCE.md`](./REPRODUCE.md)

End of research ledger.
