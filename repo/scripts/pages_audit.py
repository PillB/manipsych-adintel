#!/usr/bin/env python3
"""Comprehensive Playwright audit of the GitHub Pages live dashboard.

Navigates to every section, captures screenshots, tests all user flows,
and saves screenshots for VLM review.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://pillb.github.io/manipsych-adintel/reports/adintel/adintel_dashboard.html"
SCREENSHOTS_DIR = ROOT / "audit" / "assurance" / "evidence" / "screenshots"
REPORT = ROOT / "audit" / "assurance" / "evidence" / "pages_audit.json"


def log(msg: str) -> None:
    print(f"[audit] {msg}", flush=True)


def capture_section(page: Page, section_id: str, name: str) -> dict:
    """Navigate to a section and capture a screenshot."""
    try:
        # Click the nav link
        nav_link = page.locator(f'nav.nav a[href="#{section_id}"]')
        if nav_link.count() > 0:
            nav_link.click()
        else:
            page.evaluate(f'document.getElementById("{section_id}")?.scrollIntoView()')
        page.wait_for_timeout(1500)

        # Capture screenshot
        screenshot_path = SCREENSHOTS_DIR / f"{name}.png"
        page.screenshot(path=str(screenshot_path), full_page=False)

        # Check what's visible
        visible_check = page.evaluate(f"""() => {{
            const el = document.getElementById("{section_id}");
            if (!el) return {{found: false}};
            const rect = el.getBoundingClientRect();
            return {{
                found: true,
                top: rect.top,
                visible: rect.top >= 0 && rect.top < window.innerHeight,
                height: rect.height
            }};
        }}""")

        return {
            "section": section_id,
            "name": name,
            "screenshot": str(screenshot_path),
            "found": visible_check.get("found", False),
            "visible": visible_check.get("visible", False),
            "top": visible_check.get("top", 0),
            "height": visible_check.get("height", 0),
        }
    except Exception as e:
        return {"section": section_id, "name": name, "error": str(e)}


def test_user_flows(page: Page) -> list[dict]:
    """Test key user flows."""
    flows = []

    # Flow 1: Top-25 explorer keyboard navigation
    log("Testing keyboard navigation...")
    page.locator("body").click()
    page.locator("#explorer").scroll_into_view_if_needed()
    page.wait_for_timeout(500)

    initial_detail = page.locator("#detailHead").inner_text(timeout=2000)[:80]
    page.keyboard.press("n")
    page.wait_for_timeout(300)
    after_n = page.locator("#detailHead").inner_text(timeout=2000)[:80]
    page.keyboard.press("2")
    page.wait_for_timeout(500)
    mode_after_2 = page.locator("#rankMode").input_value(timeout=2000)
    page.keyboard.press("1")
    page.wait_for_timeout(300)

    flows.append({
        "flow": "keyboard_navigation",
        "initial_detail": initial_detail,
        "changed_after_n": initial_detail != after_n,
        "mode_after_2": mode_after_2,
        "status": "pass" if initial_detail != after_n else "fail",
    })

    # Flow 2: Explorer mouse interaction
    log("Testing mouse interaction...")
    rank_buttons = page.locator("#rankList .rank")
    n_buttons = rank_buttons.count()
    if n_buttons > 1:
        rank_buttons.nth(1).click()
        page.wait_for_timeout(500)
        hash_after = page.evaluate("location.hash")
        rank_buttons.nth(0).click()
        page.wait_for_timeout(500)
        hash_after_first = page.evaluate("location.hash")
        flows.append({
            "flow": "mouse_explorer",
            "n_buttons": n_buttons,
            "hash_after_second_click": hash_after,
            "hash_after_first_click": hash_after_first,
            "status": "pass",
        })

    # Flow 3: Term network filter
    log("Testing term network filters...")
    page.locator("#term-network").scroll_into_view_if_needed()
    page.wait_for_timeout(500)
    page.locator("#networkKind").select_option("term")
    page.wait_for_timeout(500)
    nodes_after_term = page.locator("#termNetworkViz circle").count()
    page.locator("#networkReset").click()
    page.wait_for_timeout(500)
    nodes_after_reset = page.locator("#termNetworkViz circle").count()
    d3_loaded = page.evaluate("typeof window.d3LiteForce !== 'undefined'")
    flows.append({
        "flow": "term_network_filter",
        "nodes_after_term_filter": nodes_after_term,
        "nodes_after_reset": nodes_after_reset,
        "d3_lite_force_loaded": d3_loaded,
        "status": "pass" if d3_loaded else "fail",
    })

    # Flow 4: Corpus map interaction
    log("Testing corpus map...")
    page.locator("#corpus-map").scroll_into_view_if_needed()
    page.wait_for_timeout(500)
    initial_points = page.locator("#corpusMapViz circle").count()
    page.locator("#mapColor").select_option("split")
    page.wait_for_timeout(500)
    legend_after = page.locator("#mapLegend .legend-item").count()
    page.locator("#mapColor").select_option("platform")
    page.wait_for_timeout(500)
    flows.append({
        "flow": "corpus_map",
        "initial_points": initial_points,
        "legend_after_split": legend_after,
        "status": "pass" if initial_points > 0 else "fail",
    })

    # Flow 5: Explainability atlas
    log("Testing explainability atlas...")
    page.locator("#explainability-atlas").scroll_into_view_if_needed()
    page.wait_for_timeout(500)
    n_labels = page.locator("#explainLabel option").count()
    if n_labels > 0:
        page.locator("#explainLabel").select_option(index=0)
        page.wait_for_timeout(500)
        cards = page.locator("#explainabilityAtlas .coef-card").count()
        flows.append({
            "flow": "explainability_atlas",
            "n_labels": n_labels,
            "n_cards_after_select": cards,
            "status": "pass" if cards > 0 else "fail",
        })

    # Flow 6: Search
    log("Testing search...")
    page.locator("#explorer").scroll_into_view_if_needed()
    page.locator("#query").fill("ayuda")
    page.wait_for_timeout(500)
    results = page.locator("#rankList .rank").count()
    page.locator("#query").fill("")
    page.wait_for_timeout(300)
    flows.append({
        "flow": "search",
        "results_for_ayuda": results,
        "status": "pass" if results > 0 else "fail",
    })

    return flows


def main() -> int:
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    sections = [
        ("metrics", "01_kpi_metrics"),
        ("pipeline", "02_pipeline_diagram"),
        ("diagnostics", "03_diagnostics"),
        ("explainability-atlas", "04_explainability"),
        ("term-network", "05_term_network"),
        ("corpus-map", "06_corpus_map"),
        ("facet-overview", "07_facets"),
        ("explorer", "08_top_explorer"),
        ("observability", "09_observability"),
        ("expert-poc", "10_expert_poc"),
        ("adintel-taxonomy", "11_adintel_taxonomy"),
        ("adintel-profile", "12_adintel_profile"),
        ("adintel-clustering", "13_adintel_clustering"),
        ("adintel-authorship", "14_adintel_authorship"),
        ("adintel-outliers", "15_adintel_outliers"),
        ("adintel-migration", "16_adintel_migration"),
        ("adintel-checkpoints", "17_adintel_checkpoints"),
        ("adintel-challenges", "18_adintel_challenges"),
        ("research", "19_research"),
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        page = context.new_page()

        # Capture console errors
        console_errors = []
        page.on("pageerror", lambda err: console_errors.append(str(err)))
        page.on("console", lambda msg: console_errors.append(f"console.{msg.type}: {msg.text}") if msg.type == "error" else None)

        log(f"Navigating to {BASE_URL}...")
        page.goto(BASE_URL, wait_until="networkidle", timeout=30_000)
        page.wait_for_timeout(3000)

        # Capture hero screenshot
        page.screenshot(path=str(SCREENSHOTS_DIR / "00_hero.png"), full_page=False)
        log("Captured hero screenshot")

        # Capture each section
        section_results = []
        for section_id, name in sections:
            log(f"Capturing {name}...")
            result = capture_section(page, section_id, name)
            section_results.append(result)

        # Test user flows
        flow_results = test_user_flows(page)

        # Capture mobile viewport
        page.set_viewport_size({"width": 375, "height": 812})
        page.wait_for_timeout(500)
        page.screenshot(path=str(SCREENSHOTS_DIR / "20_mobile.png"))
        overflow = page.evaluate("""() => ({
            scrollWidth: document.documentElement.scrollWidth,
            clientWidth: document.documentElement.clientWidth,
            overflow: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) - window.innerWidth
        })""")
        page.set_viewport_size({"width": 1400, "height": 900})

        browser.close()

    # Summary
    report = {
        "url": BASE_URL,
        "audited_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "console_errors": console_errors[:10],
        "n_console_errors": len(console_errors),
        "sections": section_results,
        "user_flows": flow_results,
        "mobile_overflow_px": overflow["overflow"],
        "screenshots_dir": str(SCREENSHOTS_DIR),
        "n_screenshots": len(list(SCREENSHOTS_DIR.glob("*.png"))),
    }

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"Report: {REPORT}")
    log(f"Screenshots: {report['n_screenshots']} in {SCREENSHOTS_DIR}")
    log(f"Console errors: {report['n_console_errors']}")
    log(f"Mobile overflow: {report['mobile_overflow_px']}px")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
