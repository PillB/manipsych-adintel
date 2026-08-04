#!/usr/bin/env python3
"""Run machine-checkable gates for ManiPsych project phases."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.validate_agent_state import validate_state
from tools.redact_pii import redact_text
from tools.scrape_ads import is_access_interstitial


def _load_json(path: Path) -> object:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _failures_for_phase_0() -> list[str]:
    failures: list[str] = []
    brief = ROOT / "PROJECT_BRIEF.md"
    if not brief.exists():
        failures.append("PROJECT_BRIEF.md is missing")
    else:
        text = brief.read_text(encoding="utf-8")
        for phase in range(7):
            if f"Phase {phase}" not in text:
                failures.append(f"PROJECT_BRIEF.md missing Phase {phase}")

    failures.extend(validate_state(ROOT / "AGENT_STATE.md"))
    return failures


def _failures_for_phase_1() -> list[str]:
    path = ROOT / "reports" / "phase1_compendium.json"
    if not path.exists():
        return [f"{path.relative_to(ROOT)} is missing"]
    data = _load_json(path)
    failures: list[str] = []
    rounds = data.get("research_rounds", []) if isinstance(data, dict) else []
    techniques = data.get("techniques", []) if isinstance(data, dict) else []
    retrospective = data.get("retrospective", {}) if isinstance(data, dict) else {}
    if len(rounds) < 3:
        failures.append("Phase 1 requires at least three research rounds")
    required = {"name", "category", "psychological_mechanism", "examples", "triggers", "language_patterns", "citations"}
    for index, technique in enumerate(techniques):
        missing = required - set(technique)
        if missing:
            failures.append(f"technique {index} missing fields: {sorted(missing)}")
    for key in ("covered_categories", "weak_domains", "emerged_families"):
        if not retrospective.get(key):
            failures.append(f"Phase 1 retrospective missing {key}")
    return failures


def _failures_for_phase_2() -> list[str]:
    path = ROOT / "reports" / "phase2_peru_dossier.json"
    if not path.exists():
        return [f"{path.relative_to(ROOT)} is missing"]
    data = _load_json(path)
    failures: list[str] = []
    dimensions = set(data.get("dimensions", {}).keys()) if isinstance(data, dict) else set()
    required_dimensions = {"economic", "safety", "education", "employment", "family_status"}
    missing = required_dimensions - dimensions
    if missing:
        failures.append(f"Phase 2 dossier missing dimensions: {sorted(missing)}")
    if not data.get("multipliers"):
        failures.append("Phase 2 dossier missing multipliers")
    retrospective = data.get("retrospective", {})
    for key in ("strongest_multipliers", "additional_sources"):
        if not retrospective.get(key):
            failures.append(f"Phase 2 retrospective missing {key}")
    return failures


def _contains_contact_like_pii(text: str) -> bool:
    # STRICT: any raw phone/email pattern or if re-redacting would change the text (means unredacted PII remains)
    patterns = [
        r"\b\+?51\s?\d{3}\s?\d{3}\s?\d{3}\b",
        r"\b9\d{8}\b",
        r"[\w.+-]+@[\w-]+\.[\w.-]+",
        r"\b9(?:[\s.-]*\d){7,}\b",
    ]
    if any(re.search(p, text, re.I) for p in patterns):
        return True
    return redact_text(text) != text


def _raw_family(path: str) -> str:
    lowered = path.lower()
    if "locanto" in lowered or "hombre_busca_mujer" in lowered:
        return "locanto"
    if "doplim" in lowered or "dop_" in lowered:
        return "doplim"
    if "facebook" in lowered or "fb_" in lowered:
        return "facebook"
    return "other"


def _platform_family(platform: str) -> str:
    lowered = platform.lower()
    if "locanto" in lowered:
        return "locanto"
    if "doplim" in lowered:
        return "doplim"
    if "facebook" in lowered or lowered.startswith("fb"):
        return "facebook"
    return "other"


def _looks_like_ui_boilerplate(text: str) -> bool:
    lowered = text.lstrip().lower()
    markers = (
        ":root",
        ".__fb-light-mode:root",
        "--fds-",
        "var(--",
    )
    return any(lowered.startswith(marker) for marker in markers)


def _failures_for_phase_3() -> list[str]:
    path = ROOT / "reports" / "phase3_forum_research.json"
    if not path.exists():
        return [f"{path.relative_to(ROOT)} is missing"]
    data = _load_json(path)
    failures: list[str] = []
    if not data.get("sources"):
        failures.append("Phase 3 forum research missing sources")
    if not data.get("defensive_patterns"):
        failures.append("Phase 3 forum research missing defensive patterns")
    banned = ["copy this ad", "maximize responses", "best template"]
    serialized = json.dumps(data, ensure_ascii=False).lower()
    for phrase in banned:
        if phrase in serialized:
            failures.append(f"Phase 3 contains unsafe tactical phrase: {phrase}")
    retrospective = data.get("retrospective", {})
    for key in ("frequent_patterns", "vulnerability_links"):
        if not retrospective.get(key):
            failures.append(f"Phase 3 retrospective missing {key}")
    return failures


def _failures_for_phase_4() -> list[str]:
    path = ROOT / "data" / "processed" / "ad_manifest.jsonl"
    exhaustion = ROOT / "reports" / "phase4_exhaustion.md"
    search_log = ROOT / "reports" / "phase4_search_log.json"
    platform_inventory = ROOT / "reports" / "phase4_platform_inventory.json"
    if not path.exists():
        return [f"{path.relative_to(ROOT)} is missing"]
    failures: list[str] = []
    seen: set[str] = set()
    raw_refs: dict[str, str] = {}
    count = 0
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            count += 1
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                failures.append(f"line {line_number}: invalid JSON: {exc}")
                continue
            record_id = record.get("record_id")
            if record_id in seen:
                failures.append(f"line {line_number}: duplicate record_id {record_id}")
            seen.add(record_id)
            for field in ("source_platform", "source_url_hash", "title", "body_redacted", "raw_archive_ref"):
                if not record.get(field):
                    failures.append(f"line {line_number}: missing {field}")
            if _contains_contact_like_pii(json.dumps(record, ensure_ascii=False)):
                failures.append(f"line {line_number}: processed record appears to contain contact-like PII")
            title_body = f"{record.get('title', '')} {record.get('body_redacted', '')}"
            if is_access_interstitial(title_body):
                failures.append(f"line {line_number}: processed record appears to be a browser-verification/interstitial page")
            if _looks_like_ui_boilerplate(str(record.get("body_redacted", ""))):
                failures.append(f"line {line_number}: processed record appears to start with UI/CSS boilerplate")
            raw_ref = record.get("raw_archive_ref")
            if raw_ref:
                if raw_ref in raw_refs and raw_refs[raw_ref] != record_id:
                    failures.append(f"line {line_number}: raw archive ref reused by multiple record ids: {raw_ref}")
                raw_refs[str(raw_ref)] = str(record_id)
                raw_path = ROOT / str(raw_ref)
                if not raw_path.exists():
                    failures.append(f"line {line_number}: raw archive ref does not exist: {raw_ref}")
                else:
                    raw_html = raw_path.read_text(encoding="utf-8", errors="ignore")
                    if is_access_interstitial(raw_html):
                        failures.append(f"line {line_number}: raw archive appears to be a browser-verification/interstitial page")
                    raw_family = _raw_family(str(raw_ref))
                    platform_family = _platform_family(str(record.get("source_platform", "")))
                    if raw_family != "other" and platform_family != "other" and raw_family != platform_family:
                        failures.append(f"line {line_number}: raw archive family {raw_family} does not match platform family {platform_family}")
            # PII check is ALWAYS active for phase 4 - no pass-through or disable allowed per acceptance criteria and skeptic feedback.
    if count < 10000:
        if not exhaustion.exists():
            failures.append("Phase 4 requires at least 10,000 records or reports/phase4_exhaustion.md")
        if not search_log.exists():
            failures.append("Phase 4 exhaustion requires reports/phase4_search_log.json")
        else:
            search_data = _load_json(search_log)
            # support both dict and list-of-dicts (append history)
            if isinstance(search_data, list):
                # use last dict entry if present, else aggregate
                search_data = search_data[-1] if search_data and isinstance(search_data[-1], dict) else {"status": "exhaustive", "attempts": []}
                if isinstance(search_data, list):
                    search_data = {"status": "exhaustive", "attempts": [e for e in search_data if isinstance(e, dict)]}
            if search_data.get("status") != "exhaustive":
                failures.append("Phase 4 exhaustion log must have status='exhaustive' when fewer than 10,000 records are present")
            attempts = search_data.get("attempts", []) if isinstance(search_data, dict) else []
            if len(attempts) < 20:
                failures.append("Phase 4 exhaustion requires at least 20 documented collection/search attempts")
            if not any(attempt.get("result_count", 0) > 0 for attempt in attempts if isinstance(attempt, dict)):
                failures.append("Phase 4 exhaustion must include at least one concrete public source result or direct platform collection attempt")
        if not platform_inventory.exists():
            failures.append("Phase 4 exhaustion requires reports/phase4_platform_inventory.json")
    return failures


def _failures_for_phase_5() -> list[str]:
    path = ROOT / "reports" / "phase5_model_report.json"
    if not path.exists():
        return [f"{path.relative_to(ROOT)} is missing"]
    data = _load_json(path)
    failures: list[str] = []
    for key in ("training_data", "label_schema", "model_approaches", "evaluation_metrics", "robustness_tests", "red_team_cases"):
        if not data.get(key):
            failures.append(f"Phase 5 model report missing {key}")
    if data.get("status") == "baseline_only":
        failures.append("Phase 5 requires a trained model, not only a baseline report")
    approaches = data.get("model_approaches", [])
    if not any(approach.get("status") == "trained" for approach in approaches if isinstance(approach, dict)):
        failures.append("Phase 5 requires at least one model_approaches entry with status='trained'")
    metrics = data.get("evaluation_metrics", {})
    if isinstance(metrics, dict) and not any(key in metrics for key in ("macro_f1", "accuracy", "calibration_error")):
        failures.append("Phase 5 requires supervised evaluation metrics")
    retrospective = data.get("retrospective", {})
    for key in ("best_approaches", "limitations"):
        if not retrospective.get(key):
            failures.append(f"Phase 5 retrospective missing {key}")
    return failures


def _failures_for_phase_6() -> list[str]:
    required = [
        ROOT / "reports" / "final_report.md",
        ROOT / "reports" / "dataset_manifest.md",
        ROOT / "reports" / "model_card.md",
        ROOT / "reports" / "ad_manipulation_report.html",
        ROOT / "reports" / "validation_summary.md",
    ]
    failures = [f"{path.relative_to(ROOT)} is missing" for path in required if not path.exists()]
    for phase in range(6):
        failures.extend(f"dependency phase {phase}: {failure}" for failure in failures_for_phase(phase))
    return failures


def failures_for_phase(phase: int) -> list[str]:
    gates = {
        0: _failures_for_phase_0,
        1: _failures_for_phase_1,
        2: _failures_for_phase_2,
        3: _failures_for_phase_3,
        4: _failures_for_phase_4,
        5: _failures_for_phase_5,
        6: _failures_for_phase_6,
    }
    return gates[phase]()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", type=int, choices=range(7), help="Run a single phase gate")
    parser.add_argument("--all", action="store_true", help="Run all phase gates")
    args = parser.parse_args()

    if args.all:
        phases = range(7)
    elif args.phase is not None:
        phases = [args.phase]
    else:
        parser.error("provide --phase N or --all")

    all_failures: list[str] = []
    for phase in phases:
        failures = failures_for_phase(phase)
        if failures:
            all_failures.extend(f"Phase {phase}: {failure}" for failure in failures)
        else:
            print(f"Phase {phase} gate passed")

    if all_failures:
        for failure in all_failures:
            print(f"ERROR: {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
