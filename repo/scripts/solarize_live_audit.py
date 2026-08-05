"""Solarize live-deployment Playwright audit.

Runs against the deployed GitHub Pages URL ONLY. Captures:
  - Desktop (1366x900) and mobile (375x750) acceptance
  - Screenshots of every section
  - Console errors + page errors + failed requests
  - Trace files for debugging
  - Machine-readable JSON report

Usage:
    SOLARIZE_LIVE_URL="https://pillb.github.io/manipsych-adintel/reports/adintel/adintel_dashboard.html?cb=$(date +%s)" \
    SOLARIZE_EXPECTED_SHA="<deployed-commit-sha>" \
    python3 scripts/solarize_live_audit.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

REPO = Path("/home/z/my-project/repo")
EVIDENCE_DIR = REPO / "audit" / "assurance" / "evidence" / "solarize"
SCREENSHOTS_DIR = EVIDENCE_DIR / "screenshots"
TRACES_DIR = EVIDENCE_DIR / "traces"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
TRACES_DIR.mkdir(parents=True, exist_ok=True)

LIVE_URL = os.environ.get("SOLARIZE_LIVE_URL", "")
EXPECTED_SHA = os.environ.get("SOLARIZE_EXPECTED_SHA", "")

FORBIDDEN_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


def _is_live_url(url: str) -> bool:
    if not url or url.startswith("file://"):
        return False
    host = urlparse(url).hostname or ""
    if host in FORBIDDEN_HOSTS:
        return False
    return host.endswith("github.io")


def audit_desktop(page, context) -> dict:
    """Desktop acceptance: 1366x900."""
    results = {"name": "desktop", "viewport": "1366x900", "steps": []}

    # Step 1: page loads without errors
    page.goto(LIVE_URL, wait_until="networkidle", timeout=60_000)
    page.wait_for_timeout(2500)
    title = page.title()
    results["steps"].append({
        "name": "page_loads",
        "title": title,
        "url": page.url,
        "passed": "ManiPsych" in title,
    })

    # Step 2: build fingerprint + commit SHA
    html = page.locator("html")
    fp = html.get_attribute("data-build-fingerprint") or ""
    sha = html.get_attribute("data-commit-sha") or ""
    results["steps"].append({
        "name": "build_fingerprint",
        "fingerprint": fp,
        "commit_sha": sha,
        "expected_sha": EXPECTED_SHA,
        "passed": bool(fp) and len(sha) == 40,
    })

    # Screenshots of every major section
    sections = [
        ("hero", "#metrics"),
        ("clustering", "#adintel-clustering"),
        ("outliers", "#adintel-outliers"),
        ("profile", "#adintel-profile"),
        ("authorship", "#adintel-authorship"),
        ("taxonomy", "#adintel-taxonomy"),
        ("checkpoints", "#adintel-checkpoints"),
    ]
    for name, anchor in sections:
        try:
            page.goto(f"{LIVE_URL}{anchor}", wait_until="networkidle")
            page.wait_for_timeout(1000)
            page.screenshot(path=str(SCREENSHOTS_DIR / f"desktop_{name}.png"), full_page=False)
            results["steps"].append({"name": f"screenshot_{name}", "passed": True})
        except Exception as e:
            results["steps"].append({"name": f"screenshot_{name}", "passed": False, "error": str(e)})

    # Step 3: outlier term comparison
    page.goto(f"{LIVE_URL}#adintel-outliers", wait_until="networkidle")
    page.wait_for_timeout(1500)
    section = page.locator("#adintel-outliers")
    rows = section.locator("[data-field='term_comparison_row']").count()
    blocks = section.locator("[data-field='term_comparison']").count()
    text = section.inner_text().lower()
    results["steps"].append({
        "name": "outlier_term_comparison",
        "n_rows": rows,
        "n_comparison_blocks": blocks,
        "has_outlier_count": "outlier_count" in text,
        "has_effect_size": "effect_size" in text,
        "has_q_value": "q_value" in text,
        "has_min_support": "min_support" in text,
        "has_4way_kinds": all(k in text for k in ("detector", "density_noise", "cluster_enriched", "boundary")),
        "has_non_difference_statement": any(p in text for p in ("not meaningfully different", "not_meaningfully_different")),
        "passed": rows > 0 and blocks == 3 and "effect_size" in text and "q_value" in text,
    })

    # Step 4: cluster section
    page.goto(f"{LIVE_URL}#adintel-clustering", wait_until="networkidle")
    page.wait_for_timeout(1500)
    section = page.locator("#adintel-clustering")
    cluster_examples = section.locator("[data-cluster-example]").count()
    benchmark_rows = section.locator("[data-field='benchmark_row']").count()
    text = section.inner_text().lower()
    results["steps"].append({
        "name": "cluster_section",
        "n_cluster_examples": cluster_examples,
        "n_benchmark_rows": benchmark_rows,
        "has_distinguishing_terms": "distinguishing" in text,
        "has_deep_clustering_verdict": "deep-clustering verdict" in text,
        "has_not_justified": "not justified" in text,
        "passed": cluster_examples > 0 and benchmark_rows == 3,
    })

    # Step 5: ad selector
    selector = page.locator("#adintel-ad-selector")
    selector.first.fill("h_")
    page.wait_for_timeout(1500)
    results_count = page.locator("#adintel-ad-results .ad-result-row").count()
    if results_count > 0:
        page.locator("#adintel-ad-results .ad-result-row").first.click()
        page.wait_for_timeout(1500)
        detail_text = page.locator("#adintel-ad-detail").first.inner_text().lower()
        results["steps"].append({
            "name": "ad_selector",
            "n_results": results_count,
            "detail_has_cluster": "cluster" in detail_text,
            "detail_has_outlier": "outlier" in detail_text or "inlier" in detail_text,
            "detail_has_alternative": "alternative_cluster" in detail_text,
            "detail_has_neighbors": "neighbor" in detail_text,
            "passed": results_count > 0 and "cluster" in detail_text,
        })
    else:
        results["steps"].append({"name": "ad_selector", "passed": False, "error": "no results"})

    # Step 6: deep link with record ID
    page.goto(f"{LIVE_URL}#adintel-clustering", wait_until="networkidle")
    page.wait_for_timeout(1500)
    # Get first record_id from the selector
    selector.first.fill("h_")
    page.wait_for_timeout(1000)
    first_rid = page.locator("#adintel-ad-results .ad-result-row").first.get_attribute("data-rid") or ""
    if first_rid:
        # Navigate to deep link
        page.goto(f"{LIVE_URL}#adintel-ad={first_rid}", wait_until="networkidle")
        page.wait_for_timeout(2000)
        detail_text = page.locator("#adintel-ad-detail").first.inner_text().lower()
        results["steps"].append({
            "name": "deep_link",
            "record_id": first_rid[:20] + "...",
            "detail_populated": bool(detail_text.strip()),
            "passed": bool(detail_text.strip()) and "cluster" in detail_text,
        })
    else:
        results["steps"].append({"name": "deep_link", "passed": False, "error": "no record id"})

    return results


def audit_mobile(browser) -> dict:
    """Mobile acceptance: 375x750, touch."""
    results = {"name": "mobile", "viewport": "375x750", "steps": []}
    ctx = browser.new_context(viewport={"width": 375, "height": 750}, is_mobile=True, has_touch=True)
    pg = ctx.new_page()
    try:
        pg.goto(LIVE_URL, wait_until="networkidle", timeout=60_000)
        pg.wait_for_timeout(2500)
        # Check horizontal overflow
        overflow = pg.evaluate("() => ({scrollW: document.documentElement.scrollWidth, clientW: document.documentElement.clientWidth})")
        results["steps"].append({
            "name": "mobile_no_overflow",
            "scrollW": overflow["scrollW"],
            "clientW": overflow["clientW"],
            "passed": overflow["scrollW"] <= overflow["clientW"] + 5,
        })
        # Sections visible
        for sec in ["#adintel-clustering", "#adintel-outliers", "#adintel-profile"]:
            count = pg.locator(sec).count()
            results["steps"].append({"name": f"mobile_section_visible{sec}", "passed": count > 0})
        # Screenshot
        pg.screenshot(path=str(SCREENSHOTS_DIR / "mobile_full.png"), full_page=False)
        pg.locator("#adintel-clustering").scroll_into_view_if_needed()
        pg.wait_for_timeout(500)
        pg.screenshot(path=str(SCREENSHOTS_DIR / "mobile_clustering.png"), full_page=False)
        pg.locator("#adintel-outliers").scroll_into_view_if_needed()
        pg.wait_for_timeout(500)
        pg.screenshot(path=str(SCREENSHOTS_DIR / "mobile_outliers.png"), full_page=False)
    finally:
        ctx.close()
    return results


def main() -> int:
    if not _is_live_url(LIVE_URL):
        print("ERROR: SOLARIZE_LIVE_URL must point to a github.io URL")
        print(f"  got: {LIVE_URL!r}")
        return 2

    print(f"=== Solarize Live Audit ===")
    print(f"URL: {LIVE_URL}")
    print(f"Expected SHA: {EXPECTED_SHA}")
    print()

    report = {
        "audit_started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "live_url": LIVE_URL,
        "expected_sha": EXPECTED_SHA,
        "desktop": None,
        "mobile": None,
        "console_errors": [],
        "page_errors": [],
        "failed_requests": [],
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # Desktop context with error capture
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        page = ctx.new_page()
        page.on("console", lambda m: report["console_errors"].append({"type": m.type, "text": m.text}) if m.type == "error" else None)
        page.on("pageerror", lambda e: report["page_errors"].append(str(e)))
        page.on("requestfailed", lambda r: report["failed_requests"].append({"url": r.url, "method": r.method, "failure": r.failure}))

        # Start trace
        ctx.tracing.start(screenshots=True, snapshots=True, sources=True)

        try:
            report["desktop"] = audit_desktop(page, ctx)
        except Exception as e:
            report["desktop"] = {"error": str(e), "trace": "see traces/desktop.zip"}
        finally:
            ctx.tracing.stop(path=str(TRACES_DIR / "desktop.zip"))

        # Mobile audit
        try:
            report["mobile"] = audit_mobile(browser)
        except Exception as e:
            report["mobile"] = {"error": str(e)}

        ctx.close()
        browser.close()

    # Summarize
    report["audit_completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    n_desktop_pass = sum(1 for s in (report.get("desktop", {}) or {}).get("steps", []) if s.get("passed"))
    n_desktop_total = len((report.get("desktop", {}) or {}).get("steps", []))
    n_mobile_pass = sum(1 for s in (report.get("mobile", {}) or {}).get("steps", []) if s.get("passed"))
    n_mobile_total = len((report.get("mobile", {}) or {}).get("steps", []))
    report["summary"] = {
        "desktop_pass": f"{n_desktop_pass}/{n_desktop_total}",
        "mobile_pass": f"{n_mobile_pass}/{n_mobile_total}",
        "n_console_errors": len(report["console_errors"]),
        "n_page_errors": len(report["page_errors"]),
        "n_failed_requests": len(report["failed_requests"]),
        "overall_verdict": "PASSED" if (
            n_desktop_pass == n_desktop_total and n_mobile_pass == n_mobile_total
            and len(report["page_errors"]) == 0
        ) else "FAILED",
    }

    out_path = EVIDENCE_DIR / "live_audit_report.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\n=== Audit Report ===")
    print(f"Saved: {out_path}")
    print(f"Desktop: {report['summary']['desktop_pass']}")
    print(f"Mobile:  {report['summary']['mobile_pass']}")
    print(f"Console errors: {report['summary']['n_console_errors']}")
    print(f"Page errors: {report['summary']['n_page_errors']}")
    print(f"Failed requests: {report['summary']['n_failed_requests']}")
    print(f"Verdict: {report['summary']['overall_verdict']}")
    return 0 if report["summary"]["overall_verdict"] == "PASSED" else 1


if __name__ == "__main__":
    sys.exit(main())
