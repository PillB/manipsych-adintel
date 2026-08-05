#!/usr/bin/env python3
"""Red-team Playwright audit: tests every section for real ad examples,
functional drill-downs, and verifies the spec requirements.

For each section, checks:
1. Does the section exist in the DOM?
2. Does it show actual data (not just "N/A" or empty)?
3. Can the user see real advertisement examples?
4. Are interactive elements functional?
5. Does it link to drill-downs?

Captures screenshots and saves a structured report.
"""

from __future__ import annotations
import json, time, sys
from pathlib import Path
from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://localhost:8765/reports/adintel/adintel_dashboard.html"
OUT = ROOT / "audit" / "assurance" / "evidence" / "red_team_audit.json"
SHOTS = ROOT / "audit" / "assurance" / "evidence" / "screenshots"
SHOTS.mkdir(parents=True, exist_ok=True)

SECTIONS = [
    ("metrics", "KPI Metrics"),
    ("pipeline", "Pipeline Diagram"),
    ("diagnostics", "Diagnostics"),
    ("explainability-atlas", "Explainability Atlas"),
    ("term-network", "Term Network"),
    ("corpus-map", "Corpus Map"),
    ("explorer", "Top 25 Explorer"),
    ("observability", "Observability"),
    ("adintel-taxonomy", "Taxonomy v2"),
    ("adintel-profile", "17-dim Profile + Techniques"),
    ("adintel-clustering", "7-Space Clustering"),
    ("adintel-authorship", "Authorship"),
    ("adintel-outliers", "Outliers"),
    ("adintel-checkpoints", "Checkpoints"),
]


def check_section(page: Page, section_id: str, name: str) -> dict:
    """Deep-check one section for real content and ad examples."""
    result = {"section": section_id, "name": name, "issues": [], "has_real_ads": False, "has_examples": False, "has_drilldown": False}

    # Scroll to section
    page.evaluate(f'document.getElementById("{section_id}")?.scrollIntoView()')
    page.wait_for_timeout(1000)

    # Check section exists and has visible content
    section = page.locator(f'#{section_id}')
    if section.count() == 0:
        result["issues"].append("Section not found in DOM")
        return result

    visible = section.is_visible()
    if not visible:
        result["issues"].append("Section not visible")
        return result

    text = section.inner_text()
    html = section.inner_html()

    # Check for real ad examples (record IDs, ad titles, ad text)
    has_record_id = "h_" in text or "record_id" in text.lower()
    has_ad_title = any(word in text.lower() for word in ["ayuda", "economica", "brindo", "apoyo", "chicas", "señorita"])
    has_ad_text = "ayuda económica" in text.lower() or "ayuda economica" in text.lower()

    result["has_real_ads"] = has_record_id or has_ad_title or has_ad_text

    # Check for examples/cards
    has_cards = section.locator(".dossier-card").count() > 0
    has_table_rows = section.locator("table tbody tr").count() > 0
    has_example_text = "example" in text.lower() or "ejemplo" in text.lower() or "representative" in text.lower()

    result["has_examples"] = has_cards or has_table_rows or has_example_text

    # Check for interactive elements (clicks, dropdowns, filters)
    has_buttons = section.locator("button").count() > 0
    has_selects = section.locator("select").count() > 0
    has_links = section.locator("a[href]").count() > 0
    has_clickable = section.locator("[onclick], [role='option'], [role='button']").count() > 0

    result["has_drilldown"] = has_buttons or has_selects or has_links or has_clickable

    # Section-specific checks
    if section_id == "explorer":
        # Must have ranked ads
        rank_count = section.locator("#rankList .rank").count()
        if rank_count == 0:
            result["issues"].append("Explorer has no ranked ads")
        else:
            result["rank_count"] = rank_count
            result["has_real_ads"] = True

        # Must have annotated text
        annotated = section.locator("#annotatedText").inner_text()
        if len(annotated) < 50:
            result["issues"].append("Annotated text is too short — no real ad shown")
        else:
            result["annotated_text_length"] = len(annotated)
            result["has_real_ads"] = True

        # Must have adintel live profile
        waterfall = section.locator("#waterfall").inner_html()
        if "adintel" not in waterfall.lower():
            result["issues"].append("Explorer missing adintel live profile")

    elif section_id == "adintel-profile":
        # Must have technique table with real examples
        tables = section.locator("table")
        for i in range(tables.count()):
            rows = tables.nth(i).locator("tbody tr").count()
            if rows > 0 and "technique" in tables.nth(i).inner_text().lower():
                result["technique_rows"] = rows
                # Check if any row has a real ad title
                first_row = tables.nth(i).locator("tbody tr").first.inner_text()
                if any(w in first_row.lower() for w in ["ayuda", "chicas", "señorita", "apoyo"]):
                    result["has_real_ads"] = True

    elif section_id == "adintel-clustering":
        # Must have alignment metrics
        if "ARI" not in text and "PARTIALLY_ALIGNED" not in text:
            result["issues"].append("Clustering missing quantitative alignment")
        # Should show cluster members or representative ads
        if "representative" not in text.lower() and "distinguishing" not in text.lower():
            result["issues"].append("Clustering missing representative ads or distinguishing terms")

    elif section_id == "adintel-authorship":
        # Must have example pair
        if "same-source" not in text.lower() and "example" not in text.lower():
            result["issues"].append("Authorship missing example pair")

    elif section_id == "adintel-outliers":
        # Must have example outlier reports
        cards = section.locator(".dossier-card").count()
        if cards == 0:
            result["issues"].append("Outliers missing example cards")

    elif section_id == "term-network":
        # Must have visible nodes
        nodes = section.locator("#termNetworkViz circle").count()
        if nodes == 0:
            result["issues"].append("Term network has no visible nodes")
        else:
            result["network_nodes"] = nodes

    elif section_id == "corpus-map":
        # Must have visible points
        points = section.locator("#corpusMapViz circle").count()
        if points == 0:
            result["issues"].append("Corpus map has no visible points")
        else:
            result["map_points"] = points

    # Screenshot
    page.screenshot(path=str(SHOTS / f"redteam_{section_id}.png"))

    return result


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context(viewport={"width": 1400, "height": 900}).new_page()

        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)

        page.goto(BASE, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)

        results = []
        for sid, name in SECTIONS:
            print(f"  Checking {name}...", flush=True)
            r = check_section(page, sid, name)
            results.append(r)

        # Test explorer interaction (click an ad, check detail)
        page.evaluate('document.getElementById("explorer").scrollIntoView()')
        page.wait_for_timeout(500)
        page.locator("body").click()
        page.wait_for_timeout(200)
        rank = page.locator("#rankList .rank").first
        if rank.count() > 0:
            rank.click(timeout=5000)
            page.wait_for_timeout(1000)
            detail = page.locator("#detailHead").inner_text()
            annotated = page.locator("#annotatedText").inner_text()
            waterfall = page.locator("#waterfall").inner_html()
            ledger = page.locator("#ledger .ledger-row").count()

            explorer_test = {
                "section": "explorer_interaction",
                "detail_visible": len(detail) > 20,
                "annotated_text": len(annotated),
                "has_spans": page.locator("#annotatedText .seg").count() > 0,
                "has_waterfall": len(waterfall) > 100,
                "has_adintel_profile": "adintel" in waterfall.lower(),
                "ledger_rows": ledger,
                "has_real_ad_text": any(w in annotated.lower() for w in ["ayuda", "economica", "chicas"]),
            }
            results.append(explorer_test)

        # Test interactive analyzer
        page.goto("http://localhost:8765/docs/interactive_analyzer.html", wait_until="networkidle")
        page.wait_for_timeout(2000)
        analyzer_test = {
            "section": "interactive_analyzer",
            "tags": page.locator("#tagsOutput .tag").count(),
            "bars": page.locator("#profileOutput .bar-container").count(),
            "annotated_has_spans": page.locator("#annotatedText .highlight").count() > 0,
            "ledger_has_rows": page.locator("#evidenceLedger .evidence-item").count() > 0,
            "has_gan_button": page.locator('button[onclick="runGanCycle()"]').count() > 0,
            "has_generate_button": page.locator('button[onclick="generateAd()"]').count() > 0,
            "has_export_button": page.locator('button[onclick="exportResults()"]').count() > 0,
        }

        # Test GAN
        page.locator('button[onclick="runGanCycle()"]').click(timeout=10000)
        page.wait_for_timeout(3000)
        analyzer_test["gan_steps"] = page.locator("#ganLog .gan-step").count()
        page.screenshot(path=str(SHOTS / "redteam_analyzer_gan.png"))

        results.append(analyzer_test)

        browser.close()

    # Summarize
    report = {
        "audited_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "url": BASE,
        "js_errors": errors[:5],
        "n_js_errors": len(errors),
        "sections": results,
        "summary": {
            "total_sections": len(SECTIONS),
            "sections_with_real_ads": sum(1 for r in results if r.get("has_real_ads")),
            "sections_with_examples": sum(1 for r in results if r.get("has_examples")),
            "sections_with_drilldown": sum(1 for r in results if r.get("has_drilldown")),
            "total_issues": sum(len(r.get("issues", [])) for r in results),
        },
    }

    OUT.write_text(json.dumps(report, indent=2))
    print(f"\n=== RED TEAM SUMMARY ===")
    print(f"Sections: {report['summary']['total_sections']}")
    print(f"With real ads: {report['summary']['sections_with_real_ads']}")
    print(f"With examples: {report['summary']['sections_with_examples']}")
    print(f"With drilldown: {report['summary']['sections_with_drilldown']}")
    print(f"Total issues: {report['summary']['total_issues']}")
    print(f"JS errors: {report['n_js_errors']}")
    print(f"Report: {OUT}")

    # Print all issues
    print(f"\n=== ISSUES FOUND ===")
    for r in results:
        for issue in r.get("issues", []):
            print(f"  [{r['section']}] {issue}")

if __name__ == "__main__":
    main()
