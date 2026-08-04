# No-code AI expert review proof of concept

Status: proof of concept, not human-adjudicated gold.

## Coverage

- Corpus records: `5717`
- Direct no-code AI expert records completed: `1`
- Localized automated council records available for triage: `5717`

## What this proves

The seed record shows that expert review can catch Spanish localization and orthographic omissions that exact matching missed. The phrase `Brindó apoyo económica` is malformed Spanish, but a fluent reviewer understands it as economic-support framing and labels it as `reciprocity_obligation`.

## Completed no-code expert overlays

- `h_f4fc363a9b8f997059ec332d2ec0effd3960edf30c9f677131a8a9061e43fd81`: 12 expert spans, document harm `3`, manipulativeness `3`.

## Methodology

1. Read the full ad text before consulting council/model outputs.
2. Identify persuasion/manipulation techniques using the project primer and research taxonomy.
3. Treat Spanish gender mismatch, accent loss, typos, slang, and euphemism as semantic evidence when context supports it.
4. Select exact spans and preserve immutable offsets.
5. Assign intensity, manipulativeness, harm risk, explicitness, vulnerability target, and rationale.
6. Compare to candidate annotations only after independent judgment.

## Full-corpus funded review plan

- Pilot: 100 source-stratified ads, two Spanish-speaking reviewers, adjudication, guideline revision.
- Full corpus: 5,717 ads × two independent reviews = 11,434 review tasks plus adjudication.
- Quality controls: repeated controls, span F1, weighted kappa, drift reports, disagreement queues, and blind first-pass review.

## Current limitation

The current proof-of-concept is an AI expert overlay, not human gold. It is designed to demonstrate workflow, annotation depth, and fundable reviewer operations.
