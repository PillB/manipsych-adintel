#!/usr/bin/env python3
"""Audit accepted council annotations for noisy Spanish cue omissions.

The audit is intentionally conservative: it looks for high-value surface cues
that should usually have an overlapping accepted span of the expected label.
It is a QA report, not a new labeling source.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOCS = ROOT / "data/annotation/documents.jsonl"
DEFAULT_ANNOTATIONS = ROOT / "data/annotation/council_resolved_annotations.jsonl"
DEFAULT_OUTPUT = ROOT / "reports/noisy_span_omission_audit.json"

ECON_WORD = r"econ(?:o|ó|0)m(?:o)?(?:i|í)[ck][oa]s?"

CHECKS: tuple[tuple[str, str, str], ...] = (
    (
        "reciprocity_obligation",
        rf"\b(?:ayuda|alluda|apoyo|apoya|apollo|apoyito)\s+{ECON_WORD}\b",
        "financial-support phrase with gender/accent/typo variation",
    ),
    (
        "economic_vulnerability_targeting",
        rf"\b(?:apuros?|apurad[ao]s?|urgencias?|emergencias?|necesidad(?:es)?|nesecidad(?:es)?|problemas?\s+{ECON_WORD}|deudas?|sin\s+trabajo|misio|misia)\b",
        "economic hardship or urgency cue",
    ),
    (
        "privacy_or_secrecy_pressure",
        r"\b(?:discret[ao]s?|discreci(?:o|ó)n|discrecion|reservad[ao]s?|confidencial|secreto|privad[ao]s?|calladit[ao])\b",
        "privacy, discretion, or secrecy cue",
    ),
    (
        "education_or_student_targeting",
        r"\b(?:estudiantes?|estudiant[eai]s?|universitari[ao]s?|univ(?:ers)?\.?|instituto|colegial[ao]s?|estudios|carrera)\b",
        "student or education dependency cue",
    ),
    (
        "age_or_youth_targeting",
        r"\b(?:18\s*(?:a|hasta|-)\s*(?:20|21|22|23|24|25)|2[0-5]\s+a(?:ñ|n)os?\s+(?:para\s+abajo|m[aá]ximo)|menores?\s+de\s+26|jovencitas?|j[oó]venes?|se(?:ñ|n)oritas?|srtas?|chicas?|xicas?|chibolas?)\b",
        "youth/gender-targeted cue",
    ),
    (
        "conditional_financial_support",
        r"\b(?:a\s*cambio\s*(?:de)?|por\s+(?:sexo|intimidad|relaciones?|encuentr(?:os?|it[oa]s?)|salid(?:as?|it[oa]s?)|citas?|compa(?:ñ|n)[ií]a)|la\s+cantidad\s+depende\s+de\s+c[oó]mo\s+seas)\b",
        "conditional exchange cue",
    ),
)


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def overlaps(left: tuple[int, int], right: tuple[int, int]) -> bool:
    return left[0] < right[1] and right[0] < left[1]


def has_label_overlap(spans: list[dict], label: str, candidate: tuple[int, int]) -> bool:
    for span in spans:
        if span.get("label") != label:
            continue
        if any(overlaps(candidate, tuple(segment)) for segment in span.get("segments", [])):
            return True
    return False


def audit(docs_path: Path, annotations_path: Path, output_path: Path) -> dict:
    docs = {row["record_id"]: row for row in load_jsonl(docs_path)}
    annotations = {row["record_id"]: row for row in load_jsonl(annotations_path)}
    totals = Counter()
    omissions = Counter()
    examples: list[dict] = []
    for record_id, doc in docs.items():
        text = doc["text"]
        spans = annotations.get(record_id, {}).get("spans", [])
        for label, pattern, reason in CHECKS:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                totals[label] += 1
                start, end = match.span()
                if has_label_overlap(spans, label, (start, end)):
                    continue
                omissions[label] += 1
                if len(examples) < 100:
                    examples.append(
                        {
                            "record_id": record_id,
                            "platform": doc.get("platform"),
                            "label": label,
                            "reason": reason,
                            "span": [start, end],
                            "exact_text": text[start:end],
                            "context": text[max(0, start - 80): min(len(text), end + 80)],
                        }
                    )
    result = {
        "status": "ok" if not omissions else "omissions_found",
        "checks": len(CHECKS),
        "candidate_cue_counts": dict(sorted(totals.items())),
        "omission_counts": dict(sorted(omissions.items())),
        "omission_total": int(sum(omissions.values())),
        "examples": examples,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--documents", type=Path, default=DEFAULT_DOCS)
    parser.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(json.dumps(audit(args.documents, args.annotations, args.output), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
