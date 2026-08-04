#!/usr/bin/env python3
"""Small deterministic PII redactor for processed research records."""

from __future__ import annotations

import argparse
import re
import sys


PATTERNS = [
    (re.compile(r"(?i)(?:^|[^\w])(?:whatsapp|wsp|wa|wasap|watsap|telegram|tel[eé]fono|cel(?:ular)?|n[uú]mero|llama|llamar)\s*[:=]?\s*[@\w().,\s*+-]{2,90}"), "[REDACTED_CONTACT]"),
    (re.compile(r"(?i)\b(?:whatsapp|wsp|wa|wasap|watsap|telegram|tel[eé]fono|cel(?:ular)?|n[uú]mero|llama|llamar|inbox|priv)\s*[:=]?\s*[@\w().,\s*+-]{2,90}"), "[REDACTED_CONTACT]"),
    (re.compile(r"(?i)\btelegram\s*[:=]?\s*@?[\w.-]{2,50}"), "[REDACTED_CONTACT]"),
    (re.compile(r"(?i)\b(?:me\s+)?(?:escr[ií]beme|escriben|escribir|contacta(?:me)?|escribeme)\s+(?:al|por|al wsp|a)\s+[@\w().,\s*+-]{2,90}"), "[REDACTED_CONTACT]"),
    (re.compile(r"\b\+?51\s?9\d{2}\s?\d{3}\s?\d{3}\b"), "[REDACTED_PHONE]"),
    (re.compile(r"\b9\d{8}\b"), "[REDACTED_PHONE]"),
    (re.compile(r"\b9\d{8}(?=[A-Za-zÁÉÍÓÚáéíóúÑñ])"), "[REDACTED_PHONE]"),
    (re.compile(r"\b9(?:[\s().,*-]*\d){7,8}\b"), "[REDACTED_PHONE]"),
    (re.compile(r"(?i)\b9(?:\d|cero|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|trece|catorce|quince|dieciseis|dieciséis|diecisiete|dieciocho|diecinueve|veinte){3,}\b"), "[REDACTED_PHONE]"),
    (re.compile(r"\b(?:51|9)\s*(?:\d[\s.-]*){6,10}\b"), "[REDACTED_PHONE]"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[REDACTED_EMAIL]"),
    (re.compile(r"\b\d{3}[\s.-]?\d{3}[\s.-]?\d{3}\b"), "[REDACTED_PHONE]"),
    (re.compile(r"(?i)(?<![/._-])\b(?:trader|user|id|nick|alias)[\w@.-]{3,30}\b(?![\w@.-])"), "[REDACTED_CONTACT]"),
]


def redact_text(text: str) -> str:
    redacted = text
    previous = None
    while previous != redacted:
        previous = redacted
        for pattern, replacement in PATTERNS:
            redacted = pattern.sub(replacement, redacted)
    return redacted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("text", nargs="?", help="Text to redact. Reads stdin when omitted.")
    args = parser.parse_args()
    text = args.text if args.text is not None else sys.stdin.read()
    print(redact_text(text))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
