#!/usr/bin/env python3
"""Rule-based baseline detector for manipulation technique tags."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    tag: str
    pattern: re.Pattern[str]
    rationale: str
    weight: float


RULES = [
    Rule("scarcity_urgency_pressure", re.compile(r"(?i)\b(hoy|urgente|ultimo|último|rapido|rápido|solo por|limited|last chance)\b"), "Urgency or scarcity wording", 0.25),
    Rule("reciprocity_obligation", re.compile(r"(?i)\b(ayuda|apoyo|favor|te puedo ayudar|gift|regalo|debes|agradec)\b"), "Help or obligation wording", 0.2),
    Rule("platform_migration", re.compile(r"(?i)\b(inbox|dm|privado|whatsapp|wsp|telegram|escribeme|escríbeme)\b"), "Private-channel migration cue", 0.25),
    Rule("safety_and_privacy_multiplier", re.compile(r"(?i)\b(discreto|discreta|secreto|sin que nadie|confidencial|privado)\b"), "Secrecy or discretion cue", 0.25),
    Rule("financial_emergency_multiplier", re.compile(r"(?i)\b(dinero|economica|económica|efectivo|pago|soles|prestamo|préstamo)\b"), "Financial-help cue", 0.2),
    Rule("confirmshaming_guilt_pressure", re.compile(r"(?i)\b(si de verdad|no seas|demuestra|no te cuesta|por tu familia)\b"), "Guilt or proof-pressure cue", 0.15),
]


def analyze_text(text: str) -> dict[str, object]:
    findings = []
    score = 0.0
    for rule in RULES:
        matches = [match.group(0) for match in rule.pattern.finditer(text)]
        if matches:
            score += rule.weight
            findings.append(
                {
                    "tag": rule.tag,
                    "rationale": rule.rationale,
                    "evidence": sorted(set(matches), key=str.lower),
                    "weight": rule.weight
                }
            )
    return {
        "score": min(round(score, 2), 1.0),
        "tags": [finding["tag"] for finding in findings],
        "findings": findings
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("text", nargs="?", help="Text to analyze. Reads stdin when omitted.")
    args = parser.parse_args()
    text = args.text if args.text is not None else sys.stdin.read()
    print(json.dumps(analyze_text(text), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
