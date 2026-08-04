# Annotation campaign

`data/processed/modeling_manifest.jsonl` is the authoritative input. Prepare a
frozen campaign with:

```bash
python3 tools/prepare_annotation_campaign.py
python3 tools/validate_annotations.py
python3 tools/export_annotations.py
```

The preparation command creates `data/annotation/corpus_snapshot.json`,
`documents.jsonl`, and `annotations.sqlite3`. It never imports weak labels or
model suggestions into the human layer. Each document receives two human and
three subagent council assignments; the latter are suggestions only. The pilot contains
100 source-stratified records. `label_schema.json` is the pilot taxonomy and
must be revised and versioned after the pilot before main annotation.

Annotation spans use Unicode-code-point offsets that are zero-based and
end-exclusive. Discontinuous segments are stored as JSON pairs; `exact_text`
joins their substrings with ` … `. Overlapping spans are separate rows.
Promotion, engagement, follower, image, and platform signals live in
`documents.context_json`, not in persuasive-technique labels.

Subagent council review is round-based. Round 1 uses `subagent_a`,
`subagent_b`, and `subagent_c` for every ad. Export review packets with:

```bash
python3 tools/export_council_packets.py
```

Each packet includes the ad title, body, immutable text, context signals,
available image metadata, and the current label schema. After council reviewers
save their outputs, run:

```bash
python3 tools/run_council_annotation_pass.py
python3 tools/council_consensus.py --create-next-round
```

The command hashes each submitted subagent annotation payload after normalizing
document-level fields and spans. With a three-member council, the 90% agreement
threshold requires a unanimous 3/3 exact normalized match. Accepted records are
recorded in `council_consensus`; records with fewer than three submissions stay
`pending`; 2/3 or lower agreement is marked `second_pass` and, with
`--create-next-round`, receives a fresh `subagent_rN_a`/`b`/`c` assignment set.
The pass queue is exported to
`data/annotation/council_second_pass_queue.jsonl`. Council consensus is still
candidate data unless separately adjudicated.

For automated council-suggestion runs, `tools/run_council_annotation_pass.py`
uses three deterministic subagent profiles over the title, body, immutable text,
context, and image-availability metadata. It does not inspect image pixels unless
local image files are later added to the corpus. For records queued after round
1, run the second pass with the stricter shared disagreement rubric:

```bash
python3 tools/run_council_annotation_pass.py --round 2 --deliberated-second-pass
python3 tools/council_consensus.py --round 2 --create-next-round \
  --queue-output data/annotation/council_round2_queue.jsonl
python3 tools/export_resolved_council_annotations.py
```

The current council suggestion run resolved all 5,717 records: 93 accepted in
round 1 and 5,624 accepted in round 2. The accepted suggestion export is
`data/annotation/council_resolved_annotations.jsonl`; it is marked
`gold=false`.

Original human and subagent annotation sets are immutable after submission.
Adjudication creates a separate `adjudicated` layer. Only submitted,
adjudicated sets may be treated as gold. Run the validator before every export;
it rejects stale text hashes, invalid bounds, unordered segments, and substring
mismatches.

`tools/annotation_store.py` provides transactional draft autosave and submission
operations. It verifies assignments and exact substrings, prevents edits after
submission, and hides other reviewers, subagents, and model-like suggestion
layers until the current human review is submitted. Export ordering and JSON
key ordering are deterministic.

The split is campaign-group safe for known account, repost/campaign, exact text,
and conservatively matched near-template links. Candidate pairs come from
SimHash bands and are accepted using token-trigram and character-five-gram
Jaccard thresholds recorded in `corpus_snapshot.json`. Any campaign touching
Facebook or Evisos is assigned wholly to the challenge cohort. Similarity
thresholds still require review during the pilot. Every accepted automatic
merge and its two similarity scores is recorded in `similarity_links.jsonl`.
