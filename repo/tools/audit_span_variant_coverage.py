#!/usr/bin/env python3
"""Audit Spanish orthographic/semantic variant coverage in council spans."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOCS = ROOT / "data/annotation/documents.jsonl"
DEFAULT_ANNOTATIONS = ROOT / "data/annotation/council_resolved_annotations.jsonl"
DEFAULT_REPORT = ROOT / "reports/span_variant_coverage_audit.json"

VARIANT_PATTERNS = {
    "support_economic_gender_typo": re.compile(
        r"\b(?:ayuda|apoy[oa]|apoyos?)\s+econ(?:o|ó|0)?m(?:[ií][ck][ao]s?|om?[ií][ck][ao]s?)\b",
        re.I,
    ),
    "support_economic_adverbial": re.compile(r"\b(?:apoyo|ayudo|ayuda)\s+economicamente\b", re.I),
    "conditional_exchange": re.compile(
        r"\b(?:a\s*cambio\s*(?:de)?|por\s+(?:compa(?:ñ|n)[ií]a|salidas?|encuentros?|intimidad|sexo)|por\s+cada\s+(?:salida|encuentro|vez))\b",
        re.I,
    ),
    "privacy_typo": re.compile(r"\b(?:discreci(?:o|ó)n|discrecion|discresi(?:o|ó)n|discrici(?:o|ó)n|discricion|discretamente|discret[ao]s?)\b", re.I),
    "platform_slang_typo": re.compile(r"\b(?:wsp|wasap|whasap|guasap|msj|msje|sms|nro|escr[ií]beme|escribeme|ecrivir|contactame|cont[aá]ctame)\b", re.I),
}

EXPECTED_LABELS = {
    "support_economic_gender_typo": {"reciprocity_obligation"},
    "support_economic_adverbial": {"reciprocity_obligation"},
    "conditional_exchange": {"conditional_financial_support"},
    "privacy_typo": {"privacy_or_secrecy_pressure"},
    "platform_slang_typo": {"platform_migration"},
}


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def overlaps(left: tuple[int, int], right: tuple[int, int]) -> bool:
    return left[0] < right[1] and right[0] < left[1]


def covered(match_span: tuple[int, int], spans: list[dict], labels: set[str]) -> bool:
    for span in spans:
        if span.get("label") not in labels:
            continue
        if any(overlaps(match_span, tuple(segment)) for segment in span.get("segments", [])):
            return True
    return False


def audit(docs_path: Path, annotations_path: Path, report_path: Path) -> dict:
    docs = {row["record_id"]: row for row in load_jsonl(docs_path)}
    annotations = {row["record_id"]: row for row in load_jsonl(annotations_path)}
    summary: dict[str, dict] = {}
    examples: list[dict] = []
    for name, pattern in VARIANT_PATTERNS.items():
        hits = 0
        missed = 0
        for record_id, doc in docs.items():
            spans = annotations.get(record_id, {}).get("spans", [])
            for match in pattern.finditer(doc["text"]):
                hits += 1
                match_span = match.span()
                ok = covered(match_span, spans, EXPECTED_LABELS[name])
                missed += int(not ok)
                if not ok and len(examples) < 50:
                    examples.append(
                        {
                            "record_id": record_id,
                            "variant_group": name,
                            "text": match.group(0),
                            "span": list(match_span),
                            "expected_labels": sorted(EXPECTED_LABELS[name]),
                        }
                    )
        summary[name] = {"hits": hits, "missed": missed, "coverage": round((hits - missed) / hits, 4) if hits else 1.0}
    report = {
        "status": "pass" if all(item["missed"] == 0 for item in summary.values()) else "review_needed",
        "variant_groups": summary,
        "missed_examples": examples,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--documents", type=Path, default=DEFAULT_DOCS)
    parser.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    print(json.dumps(audit(args.documents, args.annotations, args.report), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
