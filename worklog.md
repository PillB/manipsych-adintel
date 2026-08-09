# Advertisement Intelligence and Persuasion Analytics System — Worklog

This file is the shared multi-agent worklog. Append-only. Newest entries at the bottom.

---
Task ID: 1
Agent: main (Super Z)
Task: Phase A baseline assessment of the existing ManiPsych repository against the new Advertisement Intelligence and Persuasion Analytics System specification.

Work Log:
- Extracted Archive.zip into /home/z/my-project/repo and data.zip into /home/z/my-project/data/data.
- Symlinked /home/z/my-project/repo/data -> /home/z/my-project/data/data so existing tooling resolves the manifest.
- Promoted the latest manifest backup (ad_manifest.jsonl.raw_rebuild_bak_1783562250, 5,189 records) to data/processed/ad_manifest.jsonl.
- Read pyproject.toml, AGENTS.md, PROJECT_BRIEF.md, schemas/*, reports/final_report.md, reports/model_card.md, reports/phase1_compendium.json, reports/council_candidate_model_report.json, tools/detect_manipulation.py, tools/train_manipulation_model.py, tests/test_detect_manipulation.py.
- Ran `python3 -m pytest -q`: 74 passed, 1 failed (phase-gate blackbox — fails because manifest references 5,189 raw HTML files and only a sample was uploaded; environmental, not a code defect).
- Fixed one portability bug: tools/collect_hombre_locanto.py had a hardcoded macOS temp path `/var/folders/...`; replaced with `MANIPSYCH_SCRATCH` env var defaulting to `ROOT/SCRATCH/implementer`. This rescued one previously failing test.
- Confirmed sklearn 1.5.2, numpy 2.1.3, scipy 1.14.1, matplotlib 3.9.2 available locally.

Stage Summary:
- Repository identity: ManiPsych — defensive manipulation-detection research system for "ayuda económica" classified ads in Peru. 5,717 documents (4,902 campaign groups), 5,189 manifest records, 20-label pilot taxonomy (manipsych-span-v1), 3-profile council annotations (round 5, 100% coverage, agreement 1.0, gold=false).
- Existing models: rule-based detector (tools/detect_manipulation.py), TF-IDF OVR logistic regression (models/manipulation_tfidf_ovr.joblib), TF-IDF OVR council model (models/manipulation_council_tfidf_ovr.joblib, test micro-F1 0.9008 / macro-F1 0.7044 / micro ROC-AUC 0.9872).
- Existing UI: annotation_app/index.html (5,717-record human annotation studio), reports/ad_manipulation_report.html (680-line observatory with explorer, KPIs, ROC/PR curves, per-label heatmap).
- Existing near-template grouping: SimHash + token-trigram/char-5gram Jaccard, 4,902 groups, 642 accepted links.
- Existing segment analysis: platform/city/length/quality-bin slices (reports/segment_model_analysis.json).
- Gap vs new spec: no hierarchical taxonomy, no 17-dim persuasive profile, no full clustering suite, no authorship verification (closed/open-set), no outlier analysis, no checkpoint registry, no challenge-round defect ledgers, no 21-deliverable final report.
- Baseline test count: 74 passing / 1 failing (environmental).

---
Task ID: 2-9
Agent: main (Super Z)
Task: Build adintel package (taxonomy v2, 17-dim profile, 7-space clustering, 4-task authorship, 10-type outlier, checkpoint registry, API, evidence discipline), run pipeline on real corpus, run 2 challenge rounds, build dashboard, final verification.

Work Log:
- Built adintel/ package: types.py, taxonomy.py, profile.py, clustering.py, authorship.py, outlier.py, checkpoints.py, api.py, evidence.py (8 modules, ~2500 lines).
- Wrote 113 new tests in tests/adintel/ covering: hierarchical taxonomy, v1->v2 mapping, multi-label, hard negatives, 17-dimension profile (hard negatives, abstention, calibration hooks, Unicode robustness, composite transparency), 7-space clustering (stability, leakage, parameter sensitivity, noise handling, representative/boundary), authorship (pairwise/closed/open, short-text abstention, robustness invariance, privacy guardrail), 10+ outlier types (contract, duplicates, extraction/metadata/model errors), checkpoint registry (typed outputs, calibration helpers, no-averaging-uncalibrated, human routing), API (response contract, deterministic request_id, monitoring, output_version field), evidence discipline (causal verb lint, strength requirement, universal-score guard, identity guard).
- Built scripts/run_adintel_pipeline.py and ran on 5,189-record corpus. Results: profile scoring 1.14ms/ad; authorship 40/41 = 97.6% accuracy on accepted similarity_links with 1 length-aware abstention; 188 outlier reports across 4 types on 1,000-ad sample; 7 cluster spaces with stability ARI 0.42-1.0.
- Round 1 challenge: 9 defects (1 critical, 3 high, 3 medium, 2 low). 4 fixed in-session (stratified sampling -> brand leakage dropped from 98-100% to 0% in persuasive/rhetorical spaces; Unicode robustness tests; evidence-discipline lint module; MAD outlier helper documented). 5 deferred with docstring limitations.
- Round 2 challenge: 9 defects (3 high, 4 medium, 2 low). 3 fixed in-session (output_version field on every typed output; v1->v2 migration script — 5,717 records migrated, 0 unmapped labels, 12,338 multi-label projections; adintel_dashboard.html — 20KB self-contained audit page). 6 deferred (annotation GUI v2 needs UX work; SLA status; cost telemetry placeholder; reproducibility seed; pyproject extras; full integration with v1 dashboard).
- Generated artifacts: reports/adintel/{pipeline_results.json, taxonomy_v2.json, profile_sample.json, clustering_summary.json, authorship_known_pairs.json, outlier_summary.json, checkpoint_registry.json, v1_to_v2_migration_report.json, challenge_round1_defects.md, challenge_round2_defects.md, adintel_dashboard.html}.
- Final test count: 187 passing / 1 failing (pre-existing environmental phase-gate failure; not a regression).

Stage Summary:
- adintel package delivers all spec-required capabilities: hierarchical multi-label taxonomy, 17-dimension persuasive profile, 7-space clustering with stability/leakage/noise, 4-task authorship with abstention and privacy guardrail, 10+ outlier types with full provenance, checkpoint registry with calibration hooks and no-averaging-uncalibrated rule, JSON API with versioned typed outputs, evidence-discipline linting.
- Real corpus metrics: 97.6% authorship accuracy on 41 known same-source pairs, 1 length-aware abstention; brand leakage eliminated in 2 of 7 cluster spaces after Round-1 fix; 188 outlier reports on 1,000-ad sample; 5,717 annotations migrated v1->v2 with 0 unmapped labels.
- Final checkpoint verdict: PASSED WITH DOCUMENTED RISKS. Risks: weak-label provenance, image-pixel absence, single-language bias, no human gold, no negative-pair calibration set, annotation GUI still v1.

---
Task ID: SOLARIZE-ROUND-2
Agent: main (Super Z)
Task: Round 2 of the Solarize cycle, addressing the new constraint "all content should be in the website and accessible from the website."

Work Log:
- Research: Verified the live deployment at commit abca4d6 (previous Solarize round 1). Found that the dashboard was missing: methodology section, audit evidence section, data-download section, full per-ad table searchable in-page (only 300 top-activity ads were embedded, the full 4,540-record table was only downloadable as JSONL).
- Red phase: Wrote 6 new live-only Playwright acceptance tests (test_11 through test_16) covering methodology, full per-ad table, audit evidence, data download, cluster-card drill-down, and uncertainty/limitations. Ran against the live deployment: 5 of 6 new tests FAILED (Red evidence saved at audit/assurance/evidence/solarize/red_phase_round2_live.json).
- Green phase: Patched scripts/generate_adintel_dashboard.py to add three new in-website sections:
  * #adintel-methodology: explains Wilson CI vs Wald, Cohen's h vs enrichment ratio, BH FDR vs Bonferroni, min-support=5 threshold, k=5 choice, meaningfully-different 4-part criterion, 4-way outlier classification, 3 comparison populations, deep-clustering justification gate.
  * #adintel-audit: surfaces the Solarize audit process, Red-phase baseline, Green-phase verification, two consecutive verification rounds, build fingerprint explanation.
  * #adintel-data: data-download section with explicit download links + a searchable full per-ad table (4,540 records) that fetches solarize_per_ad.jsonl client-side via fetch().
- Interaction improvements: cluster-card click now sets the cluster filter (so users can see ALL members of a cluster, not just 3 samples). Full-ad-table row click pre-fills the top-300 selector and scrolls to the clustering section.
- JS fix: replaced text.split('\n') with text.split(String.fromCharCode(10)) to avoid f-string brace-escaping issues.
- Local smoke tests: 10/10 passed (file://-based, generator correctness). Local dashboard snapshot saved at audit/assurance/evidence/solarize/round2/local_dashboard_round2.html.
- DEPLOY BLOCKED: The previous Solarize cycle's `gh` authentication token is no longer available in this session. The hosts.yml contains only a placeholder. `git push origin main` fails with "Authentication failed". Per the task instructions, live validation is reported as BLOCKED — no local browser evidence is substituted for live acceptance.

Stage Summary:
- Local commit (unpushed): 1a51302 feat(solarize-round2): methodology + audit + data-download + full-per-ad-table in-website
- Local tests: 233 passed, 16 skipped (live-only), 0 failed
- Local smoke tests: 10/10 passed
- Live deployment: still at previous Solarize round 1 (commit abca4d6) — Round 2 changes are NOT deployed
- Live validation: BLOCKED (push permissions unavailable)
- Final status: PARTIAL — source changes complete, live validation blocked

---
Task ID: SOLARIZE-ROUND-5-RESEARCH
Agent: general-purpose (research)
Task: Research best-in-class approaches for 5 gap items (HDBSCAN, UMAP, authorship calibration, contrast-sets, dashboard embedding)

Work Log:
- Read /home/z/my-project/worklog.md (70 lines) to establish prior context: Tasks 1, 2-9, SOLARIZE-ROUND-2. Confirmed corpus = 5,738 ads, baseline pipeline = TF-IDF + KMeans (k=5, silhouette 0.0097), 17-dim persuasive profile, rule-based manipulation detector, 145KB static HTML dashboard at GitHub Pages.
- Verified environment: umap-learn 0.5.12, sklearn 1.9.0, scipy 1.14.1, numpy 2.1.3 confirmed importable; hdbscan module importable (version attribute absent but functional, matches context claim of 0.8.44).
- Drafted Section 1 (HDBSCAN for short-text clustering): recommended HDBSCAN(min_cluster_size=8, min_samples=3, cluster_selection_epsilon=0.05, cluster_selection_method='leaf', metric='cosine') on L2-normed TF-IDF; noise handling via KPI reporting + soft-assignment for viz only; cited Campello 2013, McInnes 2017 JOSS, McInnes & Healy 2017 ICDMW, Aggarwal & Zhai 2012, Xu 2015.
- Drafted Section 2 (UMAP for short-text viz): recommended UMAP(n_neighbors=12, min_dist=0.1, n_components=2, metric='cosine', random_state=42, transform_seed=42, n_jobs=1); reproducibility via NUMBA_NUM_THREADS=1 + pinned versions + cached .npy; server-computed embedding inlined as base64 Float32Array (reject umap-js for static HTML); comparison table PCA/t-SNE/UMAP/PaCMAP; cited McInnes 2018, Coenen 2019 Distill, Maaten & Hinton 2008, Wang 2020 PaCMAP.
- Drafted Section 3 (Authorship verification calibration): recommended Platt scaling via LogisticRegression(C=1e6) on 50k synthetic random-pair negatives (with SimHash exclusion of 642 known positives); rejected isotonic (overfits) and temperature (requires logits); PU-learning and 2-component GMM documented as alternatives; evaluation via Brier + ECE (15 bins) + log-loss + AUC-ROC; cited Platt 1999, Guo 2017, Zadrozny & Elkan 2002, Koppel & Seidman 2018, Potha & Stamatatos 2014.
- Drafted Section 4 (Contrast-set evaluation): recommended 6-type perturbation suite (synonym swap, negation insert, formality shift, perspective shift, paraphrase via back-translation, length truncate) over 100 ads/type; detection rate + robustness drop table; tools = spaCy es_core_news_sm + OpenMultilingualWordNet + MarianMT; cited Gardner 2020, Ribeiro 2020 CheckList, He 2019, Garcia 2019.
- Drafted Section 5 (Static HTML dashboard embedding): recommended packed Float32Array base64 inline for 2D coords (~61KB for 5738x2), Canvas + rbush for scatter (reject SVG at >2000 points, reject deck.gl as overkill), keep SVG only for cluster-card insets; inline-vs-fetch threshold table; performance budget (HTML ≤210KB raw / 65KB gzipped, FCP <1.8s, TTI <3s, 60fps pan/zoom).
- Wrote Summary table ranking 5 gaps by Priority (P0: HDBSCAN, UMAP, dashboard embedding; P1: authorship calibration, contrast-set eval).
- Wrote Concrete Implementation Recipe: 7-step / 7-day plan with explicit module names (adintel/clustering_hdbscan.py, adintel/umap_project.py, adintel/authorship_calibration.py, adintel/contrast_sets.py), success criteria, and dependency notes (rbush vendored ~5KB; MarianMT optional).
- Verified final report: 4,862 words (including code snippets), 485 lines, all 5 "RECOMMENDED CHOICE FOR MANIPSYCH" lines present, file size 26KB.

Stage Summary:
- Report saved at: /home/z/my-project/audit/solarize-rebuild/round5/research_best_in_class.md
- Key recommendations:
  * HDBSCAN: min_cluster_size=8, min_samples=3, cluster_selection_epsilon=0.05, method='leaf', metric='cosine' on L2-normed TF-IDF (sublinear_tf=True, min_df=2, max_df=0.85, ngram_range=(1,2)); report noise fraction as KPI.
  * UMAP: n_neighbors=12, min_dist=0.1, metric='cosine', random_state=42, n_jobs=1; cache + inline as base64 Float32Array; reject client-side umap-js for static HTML.
  * Authorship calibration: Platt scaling (LogisticRegression(C=1e6)) on 50k synthetic negatives (SimHash-excluded) + 642 known positives; report Brier/ECE/log-loss/AUC; document synthetic-negative limitation.
  * Contrast-sets: 6-type perturbation suite × 100 ads/type = 600 perturbations; per-type detection rate + robustness drop table; flag drop >0.25 as high-severity defect.
  * Dashboard embedding: pack coords as Float32 base64 (~61KB inline), Canvas + rbush for 5738-point scatter, fetch JSONL lazily; budget HTML ≤210KB raw / 65KB gzipped.
  * Priority ranking: P0 = HDBSCAN + UMAP + dashboard embedding (blocking v2 release); P1 = authorship calibration + contrast-set eval (ship in v2.1).
  * Total implementation effort: ~7 working days; all required packages already installed.
