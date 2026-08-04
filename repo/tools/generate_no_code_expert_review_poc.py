#!/usr/bin/env python3
"""Generate a no-code AI expert review proof-of-concept artifact.

This is intentionally not a regex/model annotation generator. It packages a
transparent expert-review methodology, the completed seed-record expert overlay,
and a full-corpus triage plan showing how the same no-code review would scale
with funded human reviewers.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOCS = ROOT / "data/annotation/documents.jsonl"
DEFAULT_COUNCIL = ROOT / "data/annotation/council_resolved_annotations.jsonl"
DEFAULT_OVERLAY = ROOT / "data/annotation/expert_manual_review_round4.jsonl"
DEFAULT_JSON = ROOT / "reports/no_code_ai_expert_review_poc.json"
DEFAULT_MD = ROOT / "reports/no_code_ai_expert_review_poc.md"


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def generate(docs_path: Path, council_path: Path, overlay_path: Path, json_out: Path, md_out: Path) -> dict:
    docs = load_jsonl(docs_path)
    council = load_jsonl(council_path)
    overlay = load_jsonl(overlay_path) if overlay_path.exists() else []
    platform_counts = Counter(row["platform"] for row in docs)
    label_counts = Counter(label for row in council for label in {span["label"] for span in row.get("spans", [])})
    poc = {
        "status": "proof_of_concept_not_human_gold",
        "review_type": "no_code_ai_expert_review",
        "records_in_corpus": len(docs),
        "direct_no_code_expert_records_completed": len(overlay),
        "automated_localized_council_records_available_for_triage": len(council),
        "platform_counts": dict(sorted(platform_counts.items())),
        "top_council_labels_for_triage": dict(label_counts.most_common(12)),
        "methodology": [
            "Read the full ad text as a persuasion/manipulation expert before looking at model/council outputs.",
            "Identify omissions caused by Spanish localization, gender agreement, accent omission, typos, slang, euphemism, or semantic paraphrase.",
            "Select exact zero-based/end-exclusive spans from immutable text.",
            "Assign label, intensity, manipulativeness, harm, explicitness, vulnerability target, and rationale.",
            "Compare against existing council/model annotations only after independent judgment.",
            "Record disagreements as proof-of-concept review notes, not as human gold.",
        ],
        "completed_overlay": overlay,
        "funded_human_review_scale_plan": {
            "pilot": "100 source-stratified ads, two Spanish-speaking reviewers, adjudication, then guideline revision.",
            "full_corpus": "5,717 ads × two independent reviews = 11,434 review tasks plus adjudication.",
            "quality_controls": [
                "Repeated adjudicated controls for reviewer drift.",
                "Exact and overlap span F1 by label/source.",
                "Weighted kappa for intensity/manipulativeness/harm.",
                "Disagreement queues for localization/typo/slang omissions.",
                "Separate candidate council/model suggestions until after independent submission.",
            ],
        },
        "proof_points": [
            "The seed record demonstrates the exact failure mode: `apoyo económica` was semantically support despite gender/orthographic mismatch.",
            "The no-code expert overlay corrects that phrase and documents linked conditional support/secrecy/youth-student targeting.",
            "The localized automated council export can triage likely omission classes but remains separate from no-code/human expert judgment.",
        ],
    }
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(poc, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    overlay_rows = []
    for row in overlay:
        overlay_rows.append(f"- `{row['record_id']}`: {len(row.get('spans', []))} expert spans, document harm `{row.get('document', {}).get('harm_risk')}`, manipulativeness `{row.get('document', {}).get('manipulativeness')}`.")
    md = f"""# No-code AI expert review proof of concept

Status: proof of concept, not human-adjudicated gold.

## Coverage

- Corpus records: `{len(docs)}`
- Direct no-code AI expert records completed: `{len(overlay)}`
- Localized automated council records available for triage: `{len(council)}`

## What this proves

The seed record shows that expert review can catch Spanish localization and orthographic omissions that exact matching missed. The phrase `Brindó apoyo económica` is malformed Spanish, but a fluent reviewer understands it as economic-support framing and labels it as `reciprocity_obligation`.

## Completed no-code expert overlays

{chr(10).join(overlay_rows) if overlay_rows else '- None yet.'}

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
"""
    md_out.write_text(md, encoding="utf-8")
    return {"json": str(json_out), "markdown": str(md_out), "direct_records": len(overlay), "corpus_records": len(docs)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--documents", type=Path, default=DEFAULT_DOCS)
    parser.add_argument("--council", type=Path, default=DEFAULT_COUNCIL)
    parser.add_argument("--overlay", type=Path, default=DEFAULT_OVERLAY)
    parser.add_argument("--json-out", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--md-out", type=Path, default=DEFAULT_MD)
    args = parser.parse_args()
    print(json.dumps(generate(args.documents, args.council, args.overlay, args.json_out, args.md_out), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
