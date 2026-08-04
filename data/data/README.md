# Data folder

This folder is **not versioned** in the git repo (see `.gitignore`). It contains
~2 GB of raw HTML archives, processed manifests, and annotation data that are
too large for git but are required to run the pipeline.

## Structure

```
data/
├── raw/ads/                          # Raw HTML archives (per-platform per-record)
├── processed/
│   └── ad_manifest.jsonl             # 5,189 PII-redacted records (title + body_redacted)
├── annotation/
│   ├── documents.jsonl               # 5,717 immutable annotation documents
│   ├── council_resolved_annotations.jsonl  # 5,717 records, 36,585 accepted candidate spans (v1)
│   ├── council_resolved_annotations_v2.jsonl  # v1 projected to v2 taxonomy (post-migration)
│   ├── similarity_links.jsonl        # 642 accepted near-template links (SimHash + Jaccard)
│   ├── corpus_snapshot.json          # Frozen corpus metadata
│   ├── label_schema.json             # v1 20-label schema
│   ├── expert_manual_review_round4.jsonl  # Direct expert review overlay
│   └── annotations.locked.sqlite3    # Transactional annotation store (human/subagent/adjudicated layers)
├── sources/                          # Source bibliography
└── agent_runs/                       # Collection agent run logs
```

## How to obtain

The data folder is distributed separately as `data.zip` (~13 MB sample) and the
full 2 GB raw archive. Contact the project owner for access.

## How the data is used

1. **`data/processed/ad_manifest.jsonl`** is the canonical input to:
   - `tools/train_manipulation_model.py` (TF-IDF OVR baseline)
   - `tools/train_council_candidate_model.py` (council model)
   - `scripts/run_adintel_pipeline.py` (new adintel pipeline)

2. **`data/annotation/council_resolved_annotations.jsonl`** is the canonical
   v1 annotation source. Each line is a JSON object with:
   - `record_id` — matches manifest record_id
   - `spans` — list of `{label, exact_text, segments: [[start, end]], intensity, manipulativeness, harm_risk, explicitness, rationale, provenance}`
   - `document` — adjudication metadata (persuasive_intensity 0-4, manipulativeness 0-3, harm_risk 0-3, explicitness, vulnerability_target)
   - `layer=subagent`, `gold=false` (council suggestions, not human gold)

3. **`data/annotation/council_resolved_annotations_v2.jsonl`** is the v1
   annotations projected to the v2 taxonomy via `scripts/migrate_v1_annotations_to_v2.py`.
   Each span retains its `v1_label` and gains `v2_labels` (list of v2 leaves;
   one v1 label may project to multiple v2 leaves).

4. **`data/annotation/similarity_links.jsonl`** is the ground truth for
   authorship verification. Each line is a `{left_record_id, right_record_id,
   token_trigram_jaccard, character_5gram_jaccard, length_ratio, decision}`
   record. The 642 `decision=accepted` links are the known same-source pairs
   used to evaluate `adintel.authorship.pairwise_verify`.

5. **`data/annotation/annotations.locked.sqlite3`** is the transactional store.
   Tables: `assignments` (per-ad per-reviewer assignment), `submissions`
   (immutable submitted annotation sets), `drafts` (autosave), `suggestions`
   (blinded until submit). The v1 export script
   `tools/export_annotations.py` reads this and produces
   `council_resolved_annotations.jsonl`.

## Schema inference for missing files

If `annotations_export.jsonl` or `annotations.sqlite3` are unavailable, infer
their structure from:
- `tools/annotation_store.py` (SQLite schema and methods)
- `tools/export_annotations.py` (JSONL export format)
- `data/annotation/label_schema.json` (label list and document fields)
- `data/annotation/corpus_snapshot.json` (corpus version and split policy)
- `docs/ANNOTATION.md` and `docs/ANNOTATOR_PRIMER.md` (annotation protocol)

The pipeline is designed to work with just `ad_manifest.jsonl` and
`council_resolved_annotations.jsonl`; the SQLite store is only needed for
in-progress annotation campaigns.
