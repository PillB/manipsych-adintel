# Model Card

## Model

- Name: ManiPsych weakly supervised TF-IDF baseline
- Artifact: `models/manipulation_tfidf_ovr.joblib`
- Companion rules: `tools/detect_manipulation.py`
- Status: trained weakly supervised baseline on the rebuilt raw-archive corpus

## Intended Use

Defensive screening of text for manipulation-risk cues. Outputs should support human review, annotation bootstrapping, and test-case development.

## Not Intended For

- Automated enforcement without review
- Inferring a person's vulnerability from demographics
- Generating manipulative copy
- Optimizing ads or outreach

## Inputs And Outputs

Input: text string.

Output:

- `score`: capped risk score from 0.0 to 1.0
- `tags`: detected taxonomy labels
- `findings`: rationale, evidence spans, and rule weights

## Training Data

`data/processed/ad_manifest.jsonl` currently contains 1,589 strict-valid redacted public-source records rebuilt from `data/raw/ads`. Labels are weakly supervised from Phase 1 taxonomy cues, Phase 2 multiplier cues, and aggregate non-PII context metadata.

## Evaluation

Current validation combines unit tests, phase gates, and a hold-out split:

```bash
python3 -m pytest -q
python3 tools/phase_gate.py --all
```

- Train records: 1,112
- Test records: 477
- Macro-F1: 0.73
- Micro-F1: 0.8785
- Accuracy: 0.3522
- Calibration: not estimated because labels are weakly supervised

## Limitations

- Labels are weak supervision, not human-adjudicated ground truth.
- Two labels are present on all records by construction, which limits their usefulness for supervised discrimination.
- Lexical matching misses paraphrases and obfuscation.
- Regex rules can false-positive on benign text.
- The score is heuristic, not calibrated.
- The annotation SQLite database (annotations.sqlite3) is 204MB and contains 85,476 annotation sets with 489,558 spans. Scripts that load all rows into memory may experience high memory usage. Use streaming queries (cursor.fetchmany) for large analyses.
- The HTTP server for local development should bind to 127.0.0.1 only (see scripts/safe_server.py) to avoid exposing raw HTML with PII to the network.
- Calibration (Platt scaling) is applied to the authorship checkpoint only (Brier=0.0034, ECE=0.0525). Other checkpoints remain uncalibrated because they are rule-based, not probabilistic.
- Council annotations show 100% unanimity (agreement=1.0) because the 3 subagents use the same rule family with slightly different parameters. True inter-annotator reliability is unknown without independent human annotators.
- Deep learning remains deferred until a human-labeled dataset exists.
