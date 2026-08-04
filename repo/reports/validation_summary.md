# Validation Summary

## Commands

```bash
python3 -m pytest -q
python3 tools/phase_gate.py --all
python3 tools/validate_agent_state.py
```

## Current Verified State

- `data/processed/ad_manifest.jsonl`: 1,589 strict-valid records
- Raw refs: 1,589 unique refs, all present on disk
- Current model artifact: `models/manipulation_tfidf_ovr.joblib`
- Current model report: `reports/phase5_model_report.json`

## Coverage

- Agent-state checklist validation
- Phase 0 brief and gate validation
- Phase 1 compendium structure validation
- Phase 2 dossier structure validation
- Phase 3 defensive-pattern validation
- Phase 4 rebuilt processed-manifest and PII check validation
- Phase 5 model-report validation
- Phase 6 final-document validation
- Interactive HTML report generation and embedded-data validation
- Desktop and mobile browser checks for rendering, filters, dialogs, charts, console errors, and horizontal overflow
- PII redaction unit tests
- Rule-based detector unit tests
- Raw rebuild unit tests
- Weakly supervised training script unit tests

## Known Validation Gaps

- No live GitHub CI result because there is no configured git remote.
- The processed corpus is still below the original 10,000-record ambition.
- Phase 5 metrics are weak-label metrics and are not production performance estimates.
- No transformer/deep-learning model was fine-tuned because human-adjudicated labels are not yet available.
