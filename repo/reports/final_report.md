# ManiPsych Final Report

## Summary

This local research system implements a defensive pipeline for manipulation-technique research, Peru-context multiplier analysis, public-source forum/platform research, privacy-aware public ad collection, raw-archive rebuilding, and baseline detection.

The implementation completed all local phase gates. The latest rebuild uses the existing raw archive as source of truth and produces 1,589 strict-valid processed records. This is sufficient for the current weak-supervised baseline modeling pass, but still below the original 10,000-record ambition.

## Deliverables

- Project brief: `PROJECT_BRIEF.md`
- State tracker: `AGENT_STATE.md`
- Technique compendium: `reports/phase1_compendium.json`
- Peru sociological dossier: `reports/phase2_peru_dossier.json`
- Forum/platform defensive research: `reports/phase3_forum_research.json`
- Platform inventory: `reports/phase4_platform_inventory.json`
- Collection exhaustion report: `reports/phase4_exhaustion.md`
- Raw rebuild summary: `reports/raw_rebuild_summary.json`
- Processed ad manifest: `data/processed/ad_manifest.jsonl`
- Baseline detector: `tools/detect_manipulation.py`
- PII redactor: `tools/redact_pii.py`
- Rebuilt model report: `reports/phase5_model_report.json`
- Model card: `reports/model_card.md`
- Interactive model intelligence report: `reports/ad_manipulation_report.html`
- Machine-readable ranking: `reports/ad_manipulation_ranking.json`
- Validation summary: `reports/validation_summary.md`

## Research Findings

Phase 1 identified major manipulation families: scarcity and urgency pressure, social proof, authority laundering, reciprocity, foot-in-the-door commitment, dark-pattern obstruction, forced action, interface steering, hidden costs, guilt pressure, randomized monetization, coordinated inauthentic behavior, flooding, identity targeting, and narrative laundering.

Phase 2 identified Peru-specific defensive multipliers: financial emergency, economic independence, safety/privacy, family-care obligation, education/career aspiration, and status/respectability. These are risk contexts, not assumptions about individual women.

Phase 3 found reliable public evidence for Locanto Peru as a platform lead, but did not recover reliable indexed forum threads for the named communities. Findings were therefore summarized as defensive detection patterns with explicit evidence gaps.

Phase 4 now has 1,589 strict-valid redacted public-source records rebuilt from 2,372 local raw HTML archives: 1,364 Locanto, 199 Doplim, and 26 Facebook public records. The rebuild rejects duplicates, interstitials, seeker-only pages, no-target pages, tiny/corrupt pages, and residual PII.

Phase 5 implemented a transparent rule-based detector and retrained a weakly supervised TF-IDF one-vs-rest logistic regression baseline using text labels plus aggregate non-PII context labels for visibility and engagement signals. Deep learning remains deferred until human-adjudicated labels exist.

Phase 6 now includes an interactive HTML model-intelligence report. It visualizes data lineage, acceptance/rejection metrics, platform coverage, model limitations, the weighted ranking method, and the top 25 ads. Each ranked record separates deterministic annotations, inferred model labels, contextual signals, and redacted evidence spans. Search, filters, keyboard-accessible dialogs, reduced-motion handling, print styles, and runtime data checks are included.

## Safety Boundary

The system is for detection, auditing, research, and user protection. It must not be used to generate or optimize manipulative ads, target vulnerable people, bypass platform controls, or scrape private/login-gated content.

## Residual Risks

- Dataset volume is improved but still below the original 10,000-record ambition.
- Labels are weak-supervised and need human adjudication before production claims.
- Official Peru statistics need stronger direct PDF/table archival.
- The rule detector is lexical and brittle.
- No GitHub deployment was performed because the workspace is not connected to a git remote.
