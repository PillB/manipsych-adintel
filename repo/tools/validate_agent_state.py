#!/usr/bin/env python3
"""Validate AGENT_STATE.md structure and checklist evidence discipline."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


CHECKBOX_RE = re.compile(r"^(?P<indent>\s*)- \[(?P<mark>[ xX])\] (?P<title>.+)$")
CONDITION_RE = re.compile(r"^\s{2,}- Condition (?P<number>[123]): (?P<body>.+?) Evidence: (?P<evidence>.+)$")


@dataclass
class ChecklistItem:
    title: str
    completed: bool
    line_number: int
    conditions: list[str]
    evidence: list[str]


def parse_items(text: str) -> list[ChecklistItem]:
    lines = text.splitlines()
    items: list[ChecklistItem] = []
    current: ChecklistItem | None = None

    for index, line in enumerate(lines, start=1):
        checkbox = CHECKBOX_RE.match(line)
        if checkbox:
            if current:
                items.append(current)
            current = ChecklistItem(
                title=checkbox.group("title").strip(),
                completed=checkbox.group("mark").lower() == "x",
                line_number=index,
                conditions=[],
                evidence=[],
            )
            continue

        if current:
            condition = CONDITION_RE.match(line)
            if condition:
                current.conditions.append(condition.group("body").strip())
                current.evidence.append(condition.group("evidence").strip())

    if current:
        items.append(current)
    return items


def validate_state(path: Path) -> list[str]:
    errors: list[str] = []
    if not path.exists():
        return [f"{path} does not exist"]

    text = path.read_text(encoding="utf-8")
    required_phrases = ["Read `AGENT_STATE.md`", "Act on the current sub-task", "Write and compress"]
    for phrase in required_phrases:
        if phrase not in text:
            errors.append(f"missing operating-cycle phrase: {phrase}")

    if "Current task:" not in text:
        errors.append("missing current task in current status")

    items = parse_items(text)
    if not items:
        errors.append("no markdown checklist items found")

    for item in items:
        if len(item.conditions) != 3:
            errors.append(
                f"line {item.line_number}: {item.title!r} has {len(item.conditions)} conditions; expected exactly 3"
            )
        if item.completed:
            for evidence in item.evidence:
                if evidence.lower() == "pending" or evidence.lower().startswith("todo"):
                    errors.append(f"line {item.line_number}: completed item {item.title!r} has pending evidence")
        for condition in item.conditions:
            if len(condition.split()) < 5:
                errors.append(f"line {item.line_number}: condition too vague for {item.title!r}: {condition!r}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", default="AGENT_STATE.md", help="Path to AGENT_STATE.md")
    args = parser.parse_args()

    errors = validate_state(Path(args.state))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("AGENT_STATE.md validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
