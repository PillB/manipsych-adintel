#!/usr/bin/env python3
"""Comprehensive Playwright dashboard audit using ONLY mouse and keyboard emulation.

Tests every button, dropdown, keyboard shortcut, and interactive element in the
unified dashboard. Does NOT use shell commands during test execution — only
Playwright's mouse and keyboard APIs.

The script:
1. Launches a visible Chromium browser (so the user can watch and test)
2. Navigates to the dashboard served by the local HTTP server
3. Runs through every interactive element
4. Collects results into a JSON report
5. Keeps the browser open for manual user testing

Usage:
  python3 scripts/playwright_dashboard_audit.py [--headless]

The --headless flag runs without a visible browser (for CI). Default is visible
so the user can test alongside the automation.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, Browser, sync_playwright

REPO = Path("/home/z/my-project/repo")
DASHBOARD_URL = "http://localhost:8765/reports/adintel/adintel_dashboard.html"
REPORT_OUT = REPO / "audit" / "dashboard" / "research" / "benchmark-results" / "playwright_audit.json"


def log(msg: str) -> None:
    print(f"[audit] {msg}", flush=True)


def safe(fn):
    """Wrap a test step so failures don't abort the entire audit."""
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            return {"error": str(e), "step": fn.__name__}
    return wrapper


# ---------------------------------------------------------------------------
# Test steps — each tests one feature family using mouse/keyboard emulation
# ---------------------------------------------------------------------------


def test_page_loads(page: Page) -> dict[str, Any]:
    """Verify the dashboard loads without JS errors."""
    errors: list[str] = []
    page.on("pageerror", lambda err: errors.append(str(err)))
    page.on("console", lambda msg: errors.append(f"console.{msg.type}: {msg.text}") if msg.type == "error" else None)
    page.goto(DASHBOARD_URL, wait_until="networkidle", timeout=30_000)
    page.wait_for_timeout(2000)
    title = page.title()
    h1 = page.locator("header.hero h1").inner_text(timeout=5_000)
    return {
        "title": title,
        "h1": h1,
        "js_errors": errors[:10],
        "n_js_errors": len(errors),
    }


def test_kpi_cards(page: Page) -> dict[str, Any]:
    """Test KPI cards render and have correct values."""
    cards = page.locator("#metrics .kpi")
    n = cards.count()
    values = []
    for i in range(min(n, 12)):
        label = cards.nth(i).locator(".label").inner_text(timeout=2_000)
        value = cards.nth(i).locator(".value").inner_text(timeout=2_000)
        values.append({"label": label, "value": value})
    return {"n_cards": n, "cards": values}


def test_pipeline_diagram(page: Page) -> dict[str, Any]:
    """Test pipeline SVG diagram renders."""
    svg = page.locator("#pipeline svg.pipe-svg")
    n_rects = svg.locator("rect").count()
    n_texts = svg.locator("text").count()
    n_paths = svg.locator("path").count()
    return {"svg_present": svg.count() > 0, "n_rects": n_rects, "n_texts": n_texts, "n_paths": n_paths}


def test_diagnostics_curves(page: Page) -> dict[str, Any]:
    """Test ROC and PR curves render."""
    curve_chart = page.locator("#curveChart")
    svgs = curve_chart.locator("svg")
    n_svgs = svgs.count()
    paths = curve_chart.locator("svg path")
    n_paths = paths.count()
    return {"n_curve_svgs": n_svgs, "n_paths": n_paths}


def test_iteration_timeline(page: Page) -> dict[str, Any]:
    """Test training/test iteration timeline renders."""
    timeline = page.locator("#iterationTimeline")
    rows = timeline.locator(".timeline-row").count()
    first_row = timeline.locator(".timeline-row").first.inner_text(timeout=2_000) if rows > 0 else ""
    return {"n_rows": rows, "first_row_snippet": first_row[:100]}


def test_metric_heatmap(page: Page) -> dict[str, Any]:
    """Test per-label metric heatmap renders."""
    heatmap = page.locator("#metricHeatmap")
    rows = heatmap.locator(".heat-row").count()
    cells = heatmap.locator(".heat-cell").count()
    return {"n_rows": rows, "n_cells": cells}


def test_error_timeline(page: Page) -> dict[str, Any]:
    """Test error and review lifecycle renders."""
    timeline = page.locator("#errorTimeline")
    rows = timeline.locator(".timeline-row").count()
    return {"n_rows": rows}


def test_underperforming_slices(page: Page) -> dict[str, Any]:
    """Test underperforming slices render."""
    slices = page.locator("#sliceWeakness")
    cards = slices.locator(".slice-card").count()
    return {"n_slice_cards": cards}


def test_latent_clusters(page: Page) -> dict[str, Any]:
    """Test latent ad clusters render."""
    clusters = page.locator("#clusterSummary")
    cards = clusters.locator(".slice-card").count()
    return {"n_cluster_cards": cards}


def test_threshold_overlay(page: Page) -> dict[str, Any]:
    """Test threshold overlay table renders."""
    overlay = page.locator("#thresholdOverlay")
    rows = overlay.locator("tr").count()
    return {"n_rows": rows}


def test_explainability_atlas(page: Page) -> dict[str, Any]:
    """Test explainability atlas — select different labels and verify content changes."""
    select = page.locator("#explainLabel")
    option_count = select.locator("option").count()
    # Select first option
    first_option = select.locator("option").first.get_attribute("value", timeout=2_000)
    select.select_option(first_option)
    page.wait_for_timeout(500)
    cards_before = page.locator("#explainabilityAtlas .coef-card").count()
    # Select last option if different
    if option_count > 1:
        last_option = select.locator("option").last.get_attribute("value", timeout=2_000)
        if last_option != first_option:
            select.select_option(last_option)
            page.wait_for_timeout(500)
            cards_after = page.locator("#explainabilityAtlas .coef-card").count()
        else:
            cards_after = cards_before
    else:
        cards_after = cards_before
    return {"n_labels": option_count, "cards_before": cards_before, "cards_after": cards_after}


def test_term_network(page: Page) -> dict[str, Any]:
    """Test term network — verify d3-lite-force is loaded, change filters, click nodes."""
    # Check if d3LiteForce is available
    has_d3_lite = page.evaluate("() => typeof window.d3LiteForce !== 'undefined'")
    has_d3 = page.evaluate("() => typeof window.d3 !== 'undefined'")

    # Initial render
    initial_nodes = page.locator("#termNetworkViz circle").count()
    initial_edges = page.locator("#termNetworkViz line").count()

    # Change node type filter to "term" only
    page.locator("#networkKind").select_option("term")
    page.wait_for_timeout(500)
    nodes_after_term = page.locator("#termNetworkViz circle").count()

    # Change to "label" only
    page.locator("#networkKind").select_option("label")
    page.wait_for_timeout(500)
    nodes_after_label = page.locator("#termNetworkViz circle").count()

    # Reset
    page.locator("#networkReset").click()
    page.wait_for_timeout(500)
    nodes_after_reset = page.locator("#termNetworkViz circle").count()

    # Click first node — scroll to section first so sticky header doesn't intercept
    page.locator("#term-network").scroll_into_view_if_needed()
    page.wait_for_timeout(300)
    inspector_before = page.locator("#networkInspector").inner_text(timeout=2_000)
    first_node = page.locator("#termNetworkViz .network-node").first
    if first_node.count() > 0:
        first_node.click(force=True)
        page.wait_for_timeout(300)
        inspector_after = page.locator("#networkInspector").inner_text(timeout=2_000)
    else:
        inspector_after = inspector_before

    return {
        "d3_lite_force_loaded": has_d3_lite,
        "d3_loaded": has_d3,
        "initial_nodes": initial_nodes,
        "initial_edges": initial_edges,
        "nodes_after_term_filter": nodes_after_term,
        "nodes_after_label_filter": nodes_after_label,
        "nodes_after_reset": nodes_after_reset,
        "inspector_changed_on_click": inspector_before != inspector_after,
        "CRITICAL_REGRESSION": "d3-lite-force.js NOT loaded — network uses circular fallback" if not has_d3_lite else None,
    }


def test_corpus_map(page: Page) -> dict[str, Any]:
    """Test corpus map — verify points render, change projection/color, click points."""
    map_viz = page.locator("#corpusMapViz")
    initial_points = map_viz.locator("circle").count()
    legend_items = page.locator("#mapLegend .legend-item").count()

    # Change color to "split"
    page.locator("#mapColor").select_option("split")
    page.wait_for_timeout(500)
    legend_after_split = page.locator("#mapLegend .legend-item").count()

    # Change color to "score"
    page.locator("#mapColor").select_option("score")
    page.wait_for_timeout(500)
    legend_after_score = page.locator("#mapLegend .legend-item").count()

    # Change projection to "deep_bottleneck"
    page.locator("#mapProjection").select_option("deep_bottleneck")
    page.wait_for_timeout(500)
    points_after_bottleneck = map_viz.locator("circle").count()

    # Change projection to "legacy_svd"
    page.locator("#mapProjection").select_option("legacy_svd")
    page.wait_for_timeout(500)
    points_after_svd = map_viz.locator("circle").count()

    # Reset to defaults
    page.locator("#mapProjection").select_option("deep_separation")
    page.locator("#mapColor").select_option("platform")
    page.wait_for_timeout(500)

    # Click first point — scroll to map first so sticky header doesn't intercept
    page.locator("#corpus-map").scroll_into_view_if_needed()
    page.wait_for_timeout(300)
    selected_before = page.locator("#mapSelectedDetail").inner_text(timeout=2_000)
    first_point = map_viz.locator("circle").first
    if first_point.count() > 0:
        # Use force=True to bypass any overlay; the scroll should have cleared the header
        first_point.click(force=True)
        page.wait_for_timeout(300)
        selected_after = page.locator("#mapSelectedDetail").inner_text(timeout=2_000)
    else:
        selected_after = selected_before

    # Search filter
    page.locator("#mapQuery").fill("apoyo")
    page.wait_for_timeout(500)
    points_after_search = map_viz.locator("circle").count()
    page.locator("#mapQuery").fill("")
    page.wait_for_timeout(500)

    return {
        "initial_points": initial_points,
        "legend_items_initial": legend_items,
        "legend_after_split": legend_after_split,
        "legend_after_score": legend_after_score,
        "points_after_bottleneck": points_after_bottleneck,
        "points_after_svd": points_after_svd,
        "selected_changed_on_click": selected_before != selected_after,
        "points_after_search_apoyo": points_after_search,
    }


def test_facet_overview(page: Page) -> dict[str, Any]:
    """Test facet overview cards and taxonomy matrix."""
    facets = page.locator("#facetOverview .facet-card").count()
    taxonomy_rows = page.locator("#taxonomyMatrix tr").count()
    return {"n_facet_cards": facets, "n_taxonomy_rows": taxonomy_rows}


def test_top_explorer_keyboard(page: Page) -> dict[str, Any]:
    """Test the top-25 explorer using KEYBOARD navigation (n/p/1/2/3/slash)."""
    # First, click on the body to ensure focus is NOT in an input/select
    # (the keydown handler correctly ignores keys when typing in inputs)
    page.locator("body").click()
    page.wait_for_timeout(200)

    # Scroll to the explorer so it's in view
    page.locator("#explorer").scroll_into_view_if_needed()
    page.wait_for_timeout(300)

    # Get initial selected title
    detail_head = page.locator("#detailHead")
    initial_text = detail_head.inner_text(timeout=5_000)

    # Press 'n' (next)
    page.keyboard.press("n")
    page.wait_for_timeout(300)
    after_next = detail_head.inner_text(timeout=2_000)

    # Press 'n' again
    page.keyboard.press("n")
    page.wait_for_timeout(300)
    after_next2 = detail_head.inner_text(timeout=2_000)

    # Press 'p' (previous)
    page.keyboard.press("p")
    page.wait_for_timeout(300)
    after_prev = detail_head.inner_text(timeout=2_000)

    # Press '2' (change ranking to manipulation)
    page.keyboard.press("2")
    page.wait_for_timeout(500)
    rank_mode_after_2 = page.locator("#rankMode").input_value(timeout=2_000)

    # Press '3' (change ranking to persuasion)
    page.keyboard.press("3")
    page.wait_for_timeout(500)
    rank_mode_after_3 = page.locator("#rankMode").input_value(timeout=2_000)

    # Press '1' (back to review priority)
    page.keyboard.press("1")
    page.wait_for_timeout(500)
    rank_mode_after_1 = page.locator("#rankMode").input_value(timeout=2_000)

    # Press '/' (focus search)
    page.keyboard.press("/")
    page.wait_for_timeout(200)
    active_id = page.evaluate("() => document.activeElement?.id || ''")

    # Type a search query
    page.keyboard.type("ayuda")
    page.wait_for_timeout(500)
    rank_count_after_search = page.locator("#rankList .rank").count()

    # Clear search
    page.locator("#query").fill("")
    page.wait_for_timeout(300)

    # Press Escape
    page.keyboard.press("Escape")

    return {
        "initial_detail_snippet": initial_text[:80],
        "changed_after_n": initial_text != after_next,
        "changed_after_n2": after_next != after_next2,
        "changed_after_p": after_next2 != after_prev,
        "rank_mode_after_2": rank_mode_after_2,
        "rank_mode_after_3": rank_mode_after_3,
        "rank_mode_after_1": rank_mode_after_1,
        "slash_focuses_search": active_id == "query",
        "rank_count_after_search_ayuda": rank_count_after_search,
    }


def test_top_explorer_mouse(page: Page) -> dict[str, Any]:
    """Test the top-25 explorer using MOUSE clicks."""
    # Click second item in rank list
    rank_buttons = page.locator("#rankList .rank")
    n_buttons = rank_buttons.count()
    if n_buttons >= 2:
        rank_buttons.nth(1).click()
        page.wait_for_timeout(500)
        hash_after_click = page.evaluate("() => location.hash")
        detail_after = page.locator("#detailHead").inner_text(timeout=2_000)

        # Click first item
        rank_buttons.nth(0).click()
        page.wait_for_timeout(500)
        hash_after_first = page.evaluate("() => location.hash")
        detail_after_first = page.locator("#detailHead").inner_text(timeout=2_000)
    else:
        hash_after_click = ""
        detail_after = ""
        hash_after_first = ""
        detail_after_first = ""

    # Test platform filter
    platform_select = page.locator("#platformFilter")
    platform_options = platform_select.locator("option").count()
    if platform_options > 1:
        second_platform = platform_select.locator("option").nth(1).get_attribute("value", timeout=2_000) or platform_select.locator("option").nth(1).inner_text()
        platform_select.select_option(index=1)
        page.wait_for_timeout(500)
        ranks_after_platform = page.locator("#rankList .rank").count()
        platform_select.select_option(label="All platforms") if platform_options > 0 else None
        page.wait_for_timeout(300)
    else:
        ranks_after_platform = n_buttons

    # Test label filter
    label_select = page.locator("#labelFilter")
    label_options = label_select.locator("option").count()

    # Test copy deep link button
    page.locator("#copyLink").click()
    page.wait_for_timeout(500)

    return {
        "n_rank_buttons": n_buttons,
        "hash_after_second_click": hash_after_click,
        "hash_after_first_click": hash_after_first,
        "detail_changed_on_click": detail_after != detail_after_first,
        "n_platform_options": platform_options,
        "ranks_after_platform_filter": ranks_after_platform,
        "n_label_options": label_options,
    }


def test_annotated_text_and_spans(page: Page) -> dict[str, Any]:
    """Test that annotated text renders with span highlights."""
    annotated = page.locator("#annotatedText")
    text_content = annotated.inner_text(timeout=2_000) if annotated.count() > 0 else ""
    text_length = len(text_content)
    n_spans = annotated.locator(".seg").count()
    n_manip_spans = annotated.locator(".seg.manip").count()
    return {
        "annotated_text_length": text_length,
        "n_highlighted_spans": n_spans,
        "n_manip_spans": n_manip_spans,
    }


def test_score_waterfall(page: Page) -> dict[str, Any]:
    """Test score waterfall bars render."""
    waterfall = page.locator("#waterfall")
    n_bars = waterfall.locator(".rowline").count()
    return {"n_waterfall_bars": n_bars}


def test_explanation_ledger(page: Page) -> dict[str, Any]:
    """Test explanation ledger rows render."""
    ledger = page.locator("#ledger")
    n_rows = ledger.locator(".ledger-row").count()
    return {"n_ledger_rows": n_rows}


def test_annotation_dossier(page: Page) -> dict[str, Any]:
    """Test annotation dossier / ELI5 cards render."""
    dossier = page.locator("#annotationDossier")
    n_cards = dossier.locator(".dossier-card").count()
    return {"n_dossier_cards": n_cards}


def test_model_predictions(page: Page) -> dict[str, Any]:
    """Test model predictions bars render."""
    preds = page.locator("#modelPredictions")
    n_bars = preds.locator(".rowline").count()
    return {"n_prediction_bars": n_bars}


def test_council_vs_model(page: Page) -> dict[str, Any]:
    """Test council-vs-model agreement box renders."""
    box = page.locator("#agreementBox")
    text = box.inner_text(timeout=2_000) if box.count() > 0 else ""
    return {"agreement_text_length": len(text), "snippet": text[:100]}


def test_observability_table(page: Page) -> dict[str, Any]:
    """Test observability table renders."""
    obs = page.locator("#obsTable")
    n_rows = obs.locator("tr").count()
    return {"n_obs_rows": n_rows}


def test_label_distribution(page: Page) -> dict[str, Any]:
    """Test label distribution bars render."""
    chart = page.locator("#labelChart")
    n_bars = chart.locator(".rowline").count()
    return {"n_label_bars": n_bars}


def test_expert_poc(page: Page) -> dict[str, Any]:
    """Test expert POC section renders."""
    poc = page.locator("#expertPoc")
    n_rows = poc.locator("tr").count()
    n_chips = poc.locator(".chip").count()
    return {"n_poc_rows": n_rows, "n_chips": n_chips}


def test_adintel_sections(page: Page) -> dict[str, Any]:
    """Test all adintel sections render with content."""
    results = {}
    for section_id in [
        "adintel-taxonomy", "adintel-profile", "adintel-clustering",
        "adintel-authorship", "adintel-outliers", "adintel-migration",
        "adintel-checkpoints", "adintel-challenges"
    ]:
        section = page.locator(f"#{section_id}")
        results[section_id] = {
            "present": section.count() > 0,
            "text_length": len(section.inner_text(timeout=2_000)) if section.count() > 0 else 0,
            "n_tables": section.locator("table").count() if section.count() > 0 else 0,
            "n_kpis": section.locator(".kpi").count() if section.count() > 0 else 0,
        }
    return results


def test_nav_links(page: Page) -> dict[str, Any]:
    """Test all nav links scroll to their targets."""
    nav_links = page.locator("nav.nav a[href^='#']")
    n = nav_links.count()
    results = []
    for i in range(n):
        href = nav_links.nth(i).get_attribute("href", timeout=1_000)
        nav_links.nth(i).click()
        page.wait_for_timeout(300)
        visible_target = page.evaluate(f"""() => {{
            const el = document.querySelector('{href}');
            if (!el) return false;
            const rect = el.getBoundingClientRect();
            return rect.top >= 0 && rect.top < window.innerHeight;
        }}""")
        results.append({"href": href, "scrolled_to_view": visible_target})
    return {"n_nav_links": n, "results": results}


def test_duplicate_ids(page: Page) -> dict[str, Any]:
    """Check for duplicate element IDs (HTML spec violation)."""
    duplicates = page.evaluate("""() => {
        const ids = [...document.querySelectorAll('[id]')].map(el => el.id);
        const seen = {};
        const dups = [];
        for (const id of ids) {
            seen[id] = (seen[id] || 0) + 1;
            if (seen[id] === 2) dups.push(id);
        }
        return dups;
    }""")
    return {"duplicate_ids": duplicates, "n_duplicates": len(duplicates)}


def test_accessibility_basics(page: Page) -> dict[str, Any]:
    """Test basic accessibility: unnamed buttons, unlabelled controls, missing alt text."""
    issues = page.evaluate("""() => {
        const unnamedButtons = [...document.querySelectorAll('button')].filter(
            b => !(b.textContent || '').trim() && !b.getAttribute('aria-label') && !b.title
        ).map(b => b.id || b.className || 'unnamed');
        const unlabelledControls = [...document.querySelectorAll('input,select,textarea')].filter(el => {
            const id = el.getAttribute('id');
            return !el.getAttribute('aria-label') && !(id && document.querySelector(`label[for="${CSS.escape(id)}"]`));
        }).map(el => el.id || el.tagName.toLowerCase());
        const svgsWithoutRole = [...document.querySelectorAll('svg')].filter(s => !s.getAttribute('role') && !s.querySelector('title')).length;
        return {unnamedButtons, unlabelledControls, svgsWithoutRole};
    }""")
    return issues


def test_mobile_viewport(page: Page) -> dict[str, Any]:
    """Test mobile viewport — check for horizontal overflow."""
    page.set_viewport_size({"width": 375, "height": 812})
    page.wait_for_timeout(500)
    overflow = page.evaluate("""() => {
        return {
            scrollWidth: document.documentElement.scrollWidth,
            clientWidth: document.documentElement.clientWidth,
            horizontalOverflow: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) - window.innerWidth
        };
    }""")
    # Reset to desktop
    page.set_viewport_size({"width": 1280, "height": 900})
    page.wait_for_timeout(300)
    return overflow


def test_reduced_motion(page: Page) -> dict[str, Any]:
    """Test prefers-reduced-motion media query is respected."""
    # This is a CSS check; we verify the media query exists in the stylesheet
    has_reduced_motion = page.evaluate("""() => {
        for (const sheet of document.styleSheets) {
            try {
                for (const rule of sheet.cssRules) {
                    if (rule.media && rule.media.mediaText && rule.media.mediaText.includes('prefers-reduced-motion')) {
                        return true;
                    }
                }
            } catch(e) {}
        }
        return false;
    }""")
    return {"has_reduced_motion_media_query": has_reduced_motion}


def test_print_styles(page: Page) -> dict[str, Any]:
    """Test print media query exists."""
    has_print = page.evaluate("""() => {
        for (const sheet of document.styleSheets) {
            try {
                for (const rule of sheet.cssRules) {
                    if (rule.media && rule.media.mediaText && rule.media.mediaText.includes('print')) {
                        return true;
                    }
                }
            } catch(e) {}
        }
        return false;
    }""")
    return {"has_print_media_query": has_print}


# ---------------------------------------------------------------------------
# Main audit runner
# ---------------------------------------------------------------------------


def run_audit(headless: bool = False) -> dict[str, Any]:
    results: dict[str, Any] = {}
    errors: list[dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
        )
        page = context.new_page()

        # Run each test step
        steps = [
            ("page_loads", test_page_loads),
            ("kpi_cards", test_kpi_cards),
            ("pipeline_diagram", test_pipeline_diagram),
            ("diagnostics_curves", test_diagnostics_curves),
            ("iteration_timeline", test_iteration_timeline),
            ("metric_heatmap", test_metric_heatmap),
            ("error_timeline", test_error_timeline),
            ("underperforming_slices", test_underperforming_slices),
            ("latent_clusters", test_latent_clusters),
            ("threshold_overlay", test_threshold_overlay),
            ("explainability_atlas", test_explainability_atlas),
            ("term_network", test_term_network),
            ("corpus_map", test_corpus_map),
            ("facet_overview", test_facet_overview),
            ("top_explorer_keyboard", test_top_explorer_keyboard),
            ("top_explorer_mouse", test_top_explorer_mouse),
            ("annotated_text_and_spans", test_annotated_text_and_spans),
            ("score_waterfall", test_score_waterfall),
            ("explanation_ledger", test_explanation_ledger),
            ("annotation_dossier", test_annotation_dossier),
            ("model_predictions", test_model_predictions),
            ("council_vs_model", test_council_vs_model),
            ("observability_table", test_observability_table),
            ("label_distribution", test_label_distribution),
            ("expert_poc", test_expert_poc),
            ("adintel_sections", test_adintel_sections),
            ("nav_links", test_nav_links),
            ("duplicate_ids", test_duplicate_ids),
            ("accessibility_basics", test_accessibility_basics),
            ("mobile_viewport", test_mobile_viewport),
            ("reduced_motion", test_reduced_motion),
            ("print_styles", test_print_styles),
        ]

        for name, fn in steps:
            log(f"Testing {name}...")
            try:
                result = fn(page)
                results[name] = result
                if isinstance(result, dict) and result.get("error"):
                    errors.append({"step": name, "error": result["error"]})
                    log(f"  ERROR: {result['error']}")
                else:
                    log(f"  OK")
            except Exception as e:
                results[name] = {"error": str(e)}
                errors.append({"step": name, "error": str(e)})
                log(f"  ERROR: {e}")

        # Summary
        results["_summary"] = {
            "total_steps": len(steps),
            "errors": len(errors),
            "error_details": errors,
            "dashboard_url": DASHBOARD_URL,
            "audited_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        # Write report
        REPORT_OUT.parent.mkdir(parents=True, exist_ok=True)
        REPORT_OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"Report written to {REPORT_OUT}")

        # Keep browser open for user testing if not headless
        if not headless:
            log("Browser staying open for manual testing. Press Ctrl+C to close.")
            log(f"Dashboard URL: {DASHBOARD_URL}")
            try:
                while True:
                    time.sleep(60)
            except KeyboardInterrupt:
                log("Closing browser...")

        browser.close()

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--headless", action="store_true", help="Run without visible browser")
    args = parser.parse_args()
    run_audit(headless=args.headless)
