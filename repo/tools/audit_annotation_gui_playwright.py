#!/usr/bin/env python3
"""Playwright smoke audit for the generated local annotation GUI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_APP = ROOT / "annotation_app/index.html"
DEFAULT_OUT = ROOT / "reports/annotation_gui_playwright_audit.json"


def metrics(page: Page) -> dict[str, Any]:
    return page.evaluate(
        """() => ({
          rows: document.querySelectorAll('#queue .qitem').length,
          tutorialOpen: document.getElementById('tutorialModal').classList.contains('open'),
          labels: document.querySelectorAll('#label option').length,
          labelButtons: document.querySelectorAll('#labelGrid .labelbtn').length,
          selectedDoc: document.querySelector('#docHead .small')?.textContent || '',
          textLength: document.getElementById('textPanel').textContent.length,
          spanRows: document.querySelectorAll('#spanList .spanrow').length,
          suggestionsText: document.getElementById('suggestions').textContent,
          overflow: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) - window.innerWidth,
          unnamedButtons: [...document.querySelectorAll('button')].filter(b => !(b.textContent||'').trim() && !b.getAttribute('aria-label')).length,
          unlabelledControls: [...document.querySelectorAll('input,select,textarea')].filter(el => {
            const id = el.id; return !el.getAttribute('aria-label') && !(id && document.querySelector(`label[for="${CSS.escape(id)}"]`));
          }).map(el => el.id || el.tagName.toLowerCase()),
          storedKeys: Object.keys(localStorage).filter(k => k.startsWith('manipsych.annotation.')).length
        })"""
    )


def exercise(page: Page) -> dict[str, Any]:
    page.locator("#completeTraining").click()
    page.wait_for_timeout(100)
    training_closed = not page.locator("#tutorialModal").evaluate("el => el.classList.contains('open')")
    page.locator("#label").select_option("reciprocity_obligation")
    page.evaluate("() => window.__annotationTestSelect(0, Math.min(18, document.getElementById('textPanel').textContent.length))")
    page.locator("#rationale").fill("Smoke-test selected evidence")
    page.locator("#addSpan").click()
    span_count_after_add = page.locator("#spanList .spanrow").count()
    page.locator("#saveDraft").click()
    draft_saved = page.evaluate("() => Object.values(JSON.parse(localStorage.getItem('manipsych.annotation.reviewer_a')||'{}'))[0]?.state === 'draft'")
    suggestions_hidden = "Hidden until" in page.locator("#suggestions").inner_text()
    page.locator("#submitReview").click()
    submitted = page.evaluate("() => Object.values(JSON.parse(localStorage.getItem('manipsych.annotation.reviewer_a')||'{}'))[0]?.state === 'submitted'")
    suggestions_unlocked = "Hidden until" not in page.locator("#suggestions").inner_text()
    page.keyboard.press("?")
    tutorial_reopened = page.locator("#tutorialModal").evaluate("el => el.classList.contains('open')")
    page.locator("#closeTutorial").click()
    page.keyboard.press("/")
    slash_focuses_search = page.evaluate("() => document.activeElement?.id === 'search'")
    page.keyboard.press("Escape")
    page.locator("body").click(position={"x": 5, "y": 5})
    before = page.locator("#docHead h2").inner_text()
    page.keyboard.press("n")
    after = page.locator("#docHead h2").inner_text()
    return {
        "trainingClosed": training_closed,
        "spanCountAfterAdd": span_count_after_add,
        "draftSaved": draft_saved,
        "suggestionsHiddenBeforeSubmit": suggestions_hidden,
        "submitted": submitted,
        "suggestionsUnlockedAfterSubmit": suggestions_unlocked,
        "tutorialShortcutReopens": tutorial_reopened,
        "slashFocusesSearch": slash_focuses_search,
        "nextShortcutChangesDoc": before != after,
    }


def issues(m: dict[str, Any], e: dict[str, Any], console_errors: list[str], page_errors: list[str]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if console_errors or page_errors:
        out.append({"issue": "runtime errors", "evidence": f"console={console_errors[:3]} page={page_errors[:3]}", "severity": "high"})
    if m["rows"] == 0 or m["textLength"] == 0:
        out.append({"issue": "app did not render queue/text", "evidence": json.dumps(m), "severity": "high"})
    if not m["tutorialOpen"]:
        out.append({"issue": "first-run tutorial not open", "evidence": json.dumps(m), "severity": "high"})
    if m["labels"] < 20 or m["labelButtons"] < 20:
        out.append({"issue": "label schema incomplete", "evidence": json.dumps(m), "severity": "high"})
    if m["overflow"] > 2:
        out.append({"issue": "horizontal overflow", "evidence": str(m["overflow"]), "severity": "medium"})
    if m["unnamedButtons"] or m["unlabelledControls"]:
        out.append({"issue": "accessibility naming gaps", "evidence": json.dumps({"buttons": m["unnamedButtons"], "controls": m["unlabelledControls"]}), "severity": "medium"})
    checks = {
        "trainingClosed": "training completion did not close modal",
        "draftSaved": "draft did not save to localStorage",
        "suggestionsHiddenBeforeSubmit": "suggestions visible before independent submit",
        "submitted": "submit did not persist submitted state",
        "suggestionsUnlockedAfterSubmit": "suggestions did not unlock after submit",
        "tutorialShortcutReopens": "tutorial shortcut failed",
        "slashFocusesSearch": "search shortcut failed",
        "nextShortcutChangesDoc": "next shortcut failed",
    }
    for key, label in checks.items():
        if not e.get(key):
            out.append({"issue": label, "evidence": json.dumps(e), "severity": "high"})
    if e.get("spanCountAfterAdd", 0) < 1:
        out.append({"issue": "span creation failed", "evidence": json.dumps(e), "severity": "high"})
    return out[:10]


def audit(app: Path, out: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"app": str(app), "viewports": {}}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            for name, viewport in {"desktop": {"width": 1440, "height": 1000}, "mobile": {"width": 390, "height": 844}}.items():
                page = browser.new_page(viewport=viewport)
                page.goto(app.resolve().as_uri(), wait_until="load")
                page.evaluate("() => localStorage.clear()")
                console_errors: list[str] = []
                page_errors: list[str] = []
                page.on("console", lambda msg, bucket=console_errors: bucket.append(msg.text) if msg.type in {"error", "warning"} else None)
                page.on("pageerror", lambda exc, bucket=page_errors: bucket.append(str(exc)))
                page.reload(wait_until="load")
                page.wait_for_selector("#queue .qitem", timeout=20_000)
                before = metrics(page)
                actions = exercise(page)
                after = metrics(page)
                result["viewports"][name] = {
                    "before": before,
                    "after": after,
                    "actions": actions,
                    "consoleErrors": console_errors,
                    "pageErrors": page_errors,
                    "issues": issues(before, actions, console_errors, page_errors),
                }
                page.close()
        finally:
            browser.close()
    seen: set[str] = set()
    top: list[dict[str, str]] = []
    for vp in result["viewports"].values():
        for issue in vp["issues"]:
            if issue["issue"] not in seen:
                seen.add(issue["issue"])
                top.append(issue)
    result["topIssues"] = top[:10]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, default=DEFAULT_APP)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    result = audit(args.app, args.out)
    print(json.dumps({"out": str(args.out), "topIssues": result["topIssues"]}, indent=2))
    return 1 if result["topIssues"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
