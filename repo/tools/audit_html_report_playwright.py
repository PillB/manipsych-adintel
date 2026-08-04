#!/usr/bin/env python3
"""Playwright audit for the self-contained ManiPsych HTML report.

The audit focuses on regressions that are easy to miss in static tests:
runtime JavaScript errors, mobile overflow, inaccessible controls, broken
keyboard interactions, missing deep-link behavior, and annotation/span
rendering consistency.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = ROOT / "reports/ad_manipulation_report.html"
DEFAULT_OUT = ROOT / "reports/html_report_playwright_audit.json"


def collect_metrics(page: Page) -> dict[str, Any]:
    return page.evaluate(
        """() => {
          const payload = JSON.parse(document.getElementById('report-data').textContent);
          const top = payload.report.top_by_review_priority[0];
          const ids = [...document.querySelectorAll('[id]')].map(el => el.id);
          const duplicateIds = [...new Set(ids.filter((id, i) => ids.indexOf(id) !== i))];
          const unnamedButtons = [...document.querySelectorAll('button')].filter(
            b => !(b.textContent || '').trim() && !b.getAttribute('aria-label') && !b.title
          ).length;
          const unlabelledControls = [...document.querySelectorAll('input,select,textarea')].filter(el => {
            const id = el.getAttribute('id');
            return !el.getAttribute('aria-label') && !(id && document.querySelector(`label[for="${CSS.escape(id)}"]`));
          }).map(el => el.id || el.tagName.toLowerCase());
          const activeSegments = [...document.querySelectorAll('#annotatedText .seg')];
          const labelGroups = [...document.querySelectorAll('#termNetworkViz .network-label-group')];
          const labelBoxes = labelGroups.map(g => {
            const r = g.getBoundingClientRect();
            return {left: r.left, right: r.right, top: r.top, bottom: r.bottom, width: r.width, height: r.height};
          }).filter(r => r.width > 0 && r.height > 0);
          let networkLabelOverlaps = 0;
          for (let i = 0; i < labelBoxes.length; i++) {
            for (let j = i + 1; j < labelBoxes.length; j++) {
              const a = labelBoxes[i], b = labelBoxes[j];
              if (!(a.right + 1 < b.left || b.right + 1 < a.left || a.bottom + 1 < b.top || b.bottom + 1 < a.top)) {
                networkLabelOverlaps += 1;
              }
            }
          }
          const annotated = document.getElementById('annotatedText');
          const selectedButton = document.querySelector('#rankList .rank[aria-current="true"]');
          const selectedTitle = document.querySelector('.annotated-title')?.textContent || document.querySelector('.detail-title')?.textContent || '';
          const selected = payload.report.top_by_review_priority.find(r => r.title === selectedTitle) || top;
          const selectedText = selected.text || `${selected.title}\\n${selected.excerpt || ''}`;
          const selectedSpanCount = selected.spans?.length || 0;
          const selectedOutOfRange = (selected.spans || []).filter(s =>
            (s.segments || []).some(([a,b]) => a < 0 || b > selectedText.length || a >= b)
          ).length;
          return {
            htmlBytes: new Blob([document.documentElement.outerHTML]).size,
            viewport: {width: window.innerWidth, height: window.innerHeight},
            documentWidth: document.documentElement.scrollWidth,
            bodyWidth: document.body.scrollWidth,
            horizontalOverflowPx: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) - window.innerWidth,
            navLinks: document.querySelectorAll('nav a[href^="#"]').length,
            rankButtons: document.querySelectorAll('#rankList .rank').length,
            selectedButtonPresent: Boolean(selectedButton),
            duplicateIds,
            unnamedButtons,
            unlabelledControls,
            detailTitle: selectedTitle,
            annotatedTextLength: annotated?.textContent?.length || 0,
            bodyStartsWithTitle: Boolean(annotated?.textContent?.trim().startsWith(selectedTitle.trim())),
            activeRenderedSegments: activeSegments.length,
            selectedSpanCount,
            selectedOutOfRange,
            selectedHasFullText: Boolean(selected.text),
            selectedFullTextLength: selected.text?.length || 0,
            selectedExcerptLength: selected.excerpt?.length || 0,
            ledgerRows: document.querySelectorAll('#ledger .ledger-row').length,
            modelRows: document.querySelectorAll('#modelPredictions .rowline').length,
            waterfallRows: document.querySelectorAll('#waterfall .rowline').length,
            obsRows: document.querySelectorAll('#obsTable tr').length,
            labelRows: document.querySelectorAll('#labelChart .rowline').length,
            explainabilityCards: document.querySelectorAll('#explainabilityAtlas .coef-card').length,
            networkNodes: document.querySelectorAll('#termNetworkViz .network-node').length,
            networkEdges: document.querySelectorAll('#termNetworkViz .network-edge').length,
            visibleNetworkLabels: document.querySelectorAll('#termNetworkViz .network-label-group').length,
            networkLabelOverlaps,
            networkLabelModePresent: Boolean(document.querySelector('#networkLabelMode')),
            corpusPoints: document.querySelectorAll('#corpusMapViz .scatter-point').length,
            corpusAxisLabels: [...document.querySelectorAll('#corpusMapViz text')].filter(t => /Deep neural projection axis|Legacy SVD diagnostic axis|axis 1|axis 2/.test(t.textContent || '')).length,
            mapProjectionPresent: Boolean(document.querySelector('#mapProjection')),
            mapProjectionValue: document.querySelector('#mapProjection')?.value || '',
            mapOverlayPresent: Boolean(document.querySelector('#mapOverlay')),
            mapLegendItems: document.querySelectorAll('#mapLegend .legend-item').length,
            mapQuadrantCards: document.querySelectorAll('#mapQuadrants .map-card').length,
            mapSelectedDetailText: document.querySelector('#mapSelectedDetail')?.textContent || '',
            mapNeighborButtons: document.querySelectorAll('#mapNeighbors button').length,
            deepClusterCards: document.querySelectorAll('#deepClusterPanel .map-card').length,
            isolationCards: document.querySelectorAll('#isolationPanel .map-card').length,
            isolationMetricText: document.querySelector('#isolationPanel')?.textContent || '',
            deepClusterEli5Text: document.querySelector('#deepClusterPanel')?.textContent || '',
            clusterLayerButtons: document.querySelectorAll('#mapClusterLayers button').length,
            mapClusterHulls: document.querySelectorAll('#corpusMapViz ellipse').length,
            mapIsolationBoxes: document.querySelectorAll('#corpusMapViz rect').length,
            mapColorHasDeepCluster: Boolean([...document.querySelectorAll('#mapColor option')].some(option => option.value === 'deep_cluster')),
            mapResetLayersPresent: Boolean(document.querySelector('#mapResetLayers')),
            facetCards: document.querySelectorAll('#facetOverview .facet-card').length,
            taxonomyRows: document.querySelectorAll('#taxonomyMatrix tr').length,
            hasVisualizationRuntime: Boolean(window.d3LiteForce || window.d3),
            payloadHasAdvancedAnalytics: Boolean(payload.report.global_explainability && payload.report.term_network && payload.report.corpus_map && payload.report.facet_overview),
            payloadHasDeepClusters: Boolean(payload.report.corpus_map?.deep_clusters?.clusters?.length),
            payloadClustersHaveEli5: Boolean(payload.report.corpus_map?.deep_clusters?.clusters?.every(c => c.eli5_title && c.eli5_description && c.risk_characterization && c.review_guidance)),
            payloadHasDeepProjectionModes: Boolean(payload.report.corpus_map?.deep_clusters?.default_projection === 'deep_separation' && payload.report.corpus_map?.deep_clusters?.projection_modes?.deep_separation && payload.report.corpus_map?.deep_clusters?.projection_modes?.deep_bottleneck),
            payloadHasDeepIsolation: Boolean(payload.report.corpus_map?.deep_clusters?.deep_isolation?.slices?.length && payload.report.corpus_map?.deep_clusters?.deep_isolation?.metrics?.deep_isolation_bottleneck),
            reportRecordCount: payload.report.records,
            topReviewRows: payload.report.top_by_review_priority.length,
            topManipRows: payload.report.top_by_manipulation.length,
            topPersRows: payload.report.top_by_persuasion.length,
            topRowHasAllModelPredictions: Boolean(top.model_predictions),
            topModelCount: top.top_model?.length || 0,
            modelPredictionCount: top.model_predictions?.length || 0,
            hash: location.hash
          };
        }"""
    )


def exercise_interactions(page: Page) -> dict[str, Any]:
    title_locator = page.locator(".annotated-title")
    initial_title = title_locator.inner_text(timeout=5_000)
    page.keyboard.press("n")
    after_next = title_locator.inner_text(timeout=5_000)
    page.keyboard.press("p")
    after_prev = title_locator.inner_text(timeout=5_000)
    page.keyboard.press("/")
    active_id = page.evaluate("() => document.activeElement?.id || ''")
    page.keyboard.press("Escape")
    page.keyboard.press("2")
    mode_after_two = page.locator("#rankMode").input_value(timeout=5_000)
    rank_count_after_two = page.locator("#rankList .rank").count()
    page.locator("#rankList .rank").first.click()
    hash_after_click = page.evaluate("() => location.hash")
    page.locator("#networkKind").select_option("term")
    network_nodes_after_filter = page.locator("#termNetworkViz .network-node").count()
    page.locator("#networkLabelMode").select_option("hidden")
    hidden_label_count = page.locator("#termNetworkViz .network-label-group").count()
    page.locator("#networkLabelMode").select_option("smart")
    smart_label_count = page.locator("#termNetworkViz .network-label-group").count()
    page.locator("#networkReset").click()
    page.locator("#mapQuery").fill("apoyo")
    corpus_points_after_search = page.locator("#corpusMapViz .scatter-point").count()
    page.eval_on_selector("#corpusMapViz .scatter-point", "el => el.dispatchEvent(new MouseEvent('click', {bubbles: true}))")
    map_selected_detail_after_click = page.locator("#mapSelectedDetail").inner_text(timeout=5_000)
    page.locator("#mapQuery").fill("")
    page.locator("#mapColor").select_option("deep_cluster")
    projection_default = page.locator("#mapProjection").input_value(timeout=5_000)
    map_deep_cluster_legend_count = page.locator("#mapLegend .legend-item").count()
    deep_cluster_card_count = page.locator("#deepClusterPanel .map-card").count()
    layer_button_count = page.locator("#mapClusterLayers button").count()
    hull_count = page.locator("#corpusMapViz ellipse").count()
    initial_deep_points = page.locator("#corpusMapViz .scatter-point").count()
    page.locator("#deepClusterPanel button", has_text="Highlight on map").first.click()
    isolated_points = page.locator("#corpusMapViz .scatter-point").count()
    page.locator("#mapResetLayers").click()
    reset_points = page.locator("#corpusMapViz .scatter-point").count()
    page.locator("#mapProjection").select_option("deep_bottleneck")
    projection_after_bottleneck = page.locator("#mapProjection").input_value(timeout=5_000)
    bottleneck_axis_text = page.locator("#corpusMapViz").inner_text(timeout=5_000)
    page.locator("#mapProjection").select_option("legacy_svd")
    projection_after_legacy = page.locator("#mapProjection").input_value(timeout=5_000)
    legacy_axis_text = page.locator("#corpusMapViz").inner_text(timeout=5_000)
    page.locator("#mapProjection").select_option("deep_separation")
    page.locator("#mapColor").select_option("isolation_slice")
    isolation_legend_count = page.locator("#mapLegend .legend-item").count()
    page.locator("#mapColor").select_option("isolation_score")
    isolation_score_legend_text = page.locator("#mapLegend").inner_text(timeout=5_000)
    page.locator("#mapOverlay").select_option("isolation")
    isolation_box_count = page.locator("#corpusMapViz rect").count()
    page.locator("#mapOverlay").select_option("both")
    both_hull_count = page.locator("#corpusMapViz ellipse").count()
    isolation_panel_text = page.locator("#isolationPanel").inner_text(timeout=5_000)
    quadrant_text = page.locator("#mapQuadrants").inner_text(timeout=5_000)
    return {
        "keyboardNextChanged": after_next != initial_title,
        "keyboardPrevReturned": after_prev == initial_title,
        "slashFocusesSearch": active_id == "query",
        "numberShortcutChangesRanking": mode_after_two == "top_by_manipulation",
        "rankCountAfterShortcut": rank_count_after_two,
        "clickSetsHash": hash_after_click.startswith("#") and len(hash_after_click) > 1,
        "networkFilterLeavesNodes": network_nodes_after_filter > 0,
        "networkHiddenModeHidesLabels": hidden_label_count == 0,
        "networkSmartModeShowsLabels": smart_label_count > 0,
        "mapSearchLeavesPoints": corpus_points_after_search > 0,
        "mapClickPopulatesDetail": "Selected point" in map_selected_detail_after_click and "Review:" in map_selected_detail_after_click,
        "mapDeepClusterColorWorks": map_deep_cluster_legend_count > 0 and deep_cluster_card_count > 1,
        "mapClusterLayerControlsWork": layer_button_count > 0 and hull_count > 0 and 0 < isolated_points < initial_deep_points and reset_points >= initial_deep_points,
        "mapProjectionControlsWork": projection_default == "deep_separation" and projection_after_bottleneck == "deep_bottleneck" and "Deep neural projection axis" in bottleneck_axis_text and projection_after_legacy == "legacy_svd" and "Legacy SVD diagnostic axis" in legacy_axis_text,
        "mapIsolationControlsWork": isolation_legend_count > 0 and "higher anomaly score" in isolation_score_legend_text and isolation_box_count > 0 and both_hull_count > 0 and "SOTA-style clustering metric comparison" in isolation_panel_text and "Davies" in isolation_panel_text,
        "mapQuadrantsUseful": "Top clusters:" in quadrant_text and "Visible/full ads:" in quadrant_text and not any(token in quadrant_text.lower() for token in ["n/a"]),
    }


def issue_list(metrics: dict[str, Any], interactions: dict[str, Any], console_errors: list[str], page_errors: list[str]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if console_errors or page_errors:
        issues.append(
            {
                "issue": "Runtime browser errors",
                "root_cause": "The report JavaScript threw errors or logged console errors during page load/interactions.",
                "evidence": f"console={console_errors[:3]} page={page_errors[:3]}",
                "severity": "high",
            }
        )
    if metrics["horizontalOverflowPx"] > 2:
        issues.append(
            {
                "issue": "Page-level horizontal overflow",
                "root_cause": "One or more fixed/min-width report elements exceed the viewport instead of scrolling within their own container.",
                "evidence": f"overflow={metrics['horizontalOverflowPx']}px viewport={metrics['viewport']}",
                "severity": "high",
            }
        )
    if not metrics["selectedHasFullText"]:
        issues.append(
            {
                "issue": "Annotations render against excerpts, not immutable text",
                "root_cause": "The report rows omit full text and render spans against title + excerpt even though offsets are based on full immutable document text.",
                "evidence": f"excerpt={metrics['selectedExcerptLength']} fullTextPresent={metrics['selectedHasFullText']}",
                "severity": "high",
            }
        )
    if metrics["selectedOutOfRange"]:
        issues.append(
            {
                "issue": "Selected ad has out-of-range highlight offsets",
                "root_cause": "Rendered text length does not match the text used to create standoff annotation offsets.",
                "evidence": f"outOfRangeSpans={metrics['selectedOutOfRange']} spans={metrics['selectedSpanCount']}",
                "severity": "high",
            }
        )
    if metrics.get("bodyStartsWithTitle"):
        issues.append(
            {
                "issue": "Ad body repeats selected title",
                "root_cause": "The detail body pane is rendering immutable title+body text after already rendering the title in the heading.",
                "evidence": f"title={metrics['detailTitle'][:80]}",
                "severity": "medium",
            }
        )
    if not interactions["keyboardNextChanged"] or not interactions["keyboardPrevReturned"]:
        issues.append(
            {
                "issue": "Keyboard navigation is inconsistent",
                "root_cause": "The n/p shortcuts do not consistently update and restore the selected row.",
                "evidence": json.dumps(interactions, sort_keys=True),
                "severity": "medium",
            }
        )
    if not interactions["slashFocusesSearch"]:
        issues.append(
            {
                "issue": "Search shortcut is broken",
                "root_cause": "The slash shortcut does not focus the search input.",
                "evidence": json.dumps(interactions, sort_keys=True),
                "severity": "medium",
            }
        )
    if not interactions["numberShortcutChangesRanking"]:
        issues.append(
            {
                "issue": "Ranking shortcut is broken",
                "root_cause": "Numeric shortcuts do not keep the select control and rendered ranking in sync.",
                "evidence": json.dumps(interactions, sort_keys=True),
                "severity": "medium",
            }
        )
    if not interactions["clickSetsHash"]:
        issues.append(
            {
                "issue": "Deep-link hash is not set by row selection",
                "root_cause": "Row clicks fail to write the selected record id into location.hash.",
                "evidence": json.dumps(interactions, sort_keys=True),
                "severity": "medium",
            }
        )
    if metrics["duplicateIds"]:
        issues.append(
            {
                "issue": "Duplicate element ids",
                "root_cause": "The static HTML or dynamic rendering reused ids, which breaks label and anchor targeting.",
                "evidence": ", ".join(metrics["duplicateIds"][:10]),
                "severity": "medium",
            }
        )
    if metrics["unnamedButtons"] or metrics["unlabelledControls"]:
        issues.append(
            {
                "issue": "Controls missing accessible names",
                "root_cause": "Interactive controls lack visible text, aria-label, or associated labels.",
                "evidence": f"unnamedButtons={metrics['unnamedButtons']} unlabelled={metrics['unlabelledControls']}",
                "severity": "medium",
            }
        )
    if not metrics["topRowHasAllModelPredictions"]:
        issues.append(
            {
                "issue": "Council-vs-model comparison uses truncated predictions",
                "root_cause": "Only the top eight model labels are embedded, so labels below rank eight but above threshold can be omitted from agreement analysis.",
                "evidence": f"topModelCount={metrics['topModelCount']} allPredictionCount={metrics['modelPredictionCount']}",
                "severity": "medium",
            }
        )
    if metrics["rankButtons"] != 25:
        issues.append(
            {
                "issue": "Top-25 explorer does not render 25 rows",
                "root_cause": "Filters, data shape, or rendering errors changed the expected default ranking size.",
                "evidence": f"rankButtons={metrics['rankButtons']}",
                "severity": "medium",
            }
        )
    if not metrics.get("payloadHasAdvancedAnalytics"):
        issues.append(
            {
                "issue": "Advanced analytics payload missing",
                "root_cause": "The generated embedded report data lacks one or more required explainability/network/map/facet sections.",
                "evidence": json.dumps({k: metrics.get(k) for k in ["payloadHasAdvancedAnalytics"]}),
                "severity": "high",
            }
        )
    if (
        not metrics.get("payloadHasDeepClusters")
        or not metrics.get("payloadClustersHaveEli5")
        or not metrics.get("payloadHasDeepProjectionModes")
        or not metrics.get("payloadHasDeepIsolation")
        or not metrics.get("mapColorHasDeepCluster")
        or not metrics.get("mapProjectionPresent")
        or not metrics.get("mapOverlayPresent")
        or metrics.get("mapProjectionValue") != "deep_separation"
        or not metrics.get("mapResetLayersPresent")
        or metrics.get("deepClusterCards", 0) <= 1
        or metrics.get("clusterLayerButtons", 0) == 0
        or metrics.get("isolationCards", 0) <= 1
        or metrics.get("mapIsolationBoxes", 0) == 0
        or "SOTA-style clustering metric comparison" not in metrics.get("isolationMetricText", "")
        or "What this means" not in metrics.get("deepClusterEli5Text", "")
    ):
        issues.append(
            {
                "issue": "Explainable deep clusters missing",
                "root_cause": "The corpus map lacks the trained cluster payload, ELI5 characterization, layer controls, or rendered explanation cards.",
                "evidence": json.dumps(
                    {
                        "payloadHasDeepClusters": metrics.get("payloadHasDeepClusters"),
                        "payloadClustersHaveEli5": metrics.get("payloadClustersHaveEli5"),
                        "payloadHasDeepProjectionModes": metrics.get("payloadHasDeepProjectionModes"),
                        "payloadHasDeepIsolation": metrics.get("payloadHasDeepIsolation"),
                        "mapColorHasDeepCluster": metrics.get("mapColorHasDeepCluster"),
                        "mapProjectionPresent": metrics.get("mapProjectionPresent"),
                        "mapOverlayPresent": metrics.get("mapOverlayPresent"),
                        "mapProjectionValue": metrics.get("mapProjectionValue"),
                        "mapResetLayersPresent": metrics.get("mapResetLayersPresent"),
                        "deepClusterCards": metrics.get("deepClusterCards"),
                        "isolationCards": metrics.get("isolationCards"),
                        "clusterLayerButtons": metrics.get("clusterLayerButtons"),
                        "mapIsolationBoxes": metrics.get("mapIsolationBoxes"),
                    },
                    sort_keys=True,
                ),
                "severity": "medium",
            }
        )
    if not metrics.get("hasVisualizationRuntime"):
        issues.append(
            {
                "issue": "Bundled visualization runtime missing",
                "root_cause": "The local report asset did not load, so interactive network rendering may fall back or fail.",
                "evidence": "window.d3/window.d3LiteForce unavailable",
                "severity": "medium",
            }
        )
    if metrics.get("explainabilityCards", 0) < 2 or metrics.get("networkNodes", 0) == 0 or metrics.get("corpusPoints", 0) == 0:
        issues.append(
            {
                "issue": "Advanced visualization sections did not render",
                "root_cause": "Explainability, network, or corpus-map renderers failed to populate their containers.",
                "evidence": f"cards={metrics.get('explainabilityCards')} network={metrics.get('networkNodes')} points={metrics.get('corpusPoints')}",
                "severity": "high",
            }
        )
    if not metrics.get("networkLabelModePresent") or metrics.get("visibleNetworkLabels", 0) == 0:
        issues.append(
            {
                "issue": "Network smart label controls or labels missing",
                "root_cause": "The term network lacks the label-mode control or rendered smart labels.",
                "evidence": f"labelMode={metrics.get('networkLabelModePresent')} visibleLabels={metrics.get('visibleNetworkLabels')}",
                "severity": "medium",
            }
        )
    if metrics.get("networkLabelOverlaps", 0) > 0:
        issues.append(
            {
                "issue": "Network labels overlap",
                "root_cause": "Collision-aware label placement allowed visible label bounding boxes to intersect.",
                "evidence": f"overlaps={metrics.get('networkLabelOverlaps')} visibleLabels={metrics.get('visibleNetworkLabels')}",
                "severity": "medium",
            }
        )
    if metrics.get("corpusAxisLabels", 0) < 4 or metrics.get("mapLegendItems", 0) == 0 or metrics.get("mapQuadrantCards", 0) < 4:
        issues.append(
            {
                "issue": "Corpus map explanatory scaffolding missing",
                "root_cause": "The corpus map lacks axis labels, legend, or quadrant summaries needed to interpret the dot cloud.",
                "evidence": f"axis={metrics.get('corpusAxisLabels')} legend={metrics.get('mapLegendItems')} quadrants={metrics.get('mapQuadrantCards')}",
                "severity": "medium",
            }
        )
    if "Selected point" not in metrics.get("mapSelectedDetailText", "") or metrics.get("mapNeighborButtons", 0) == 0:
        issues.append(
            {
                "issue": "Corpus map selected-point detail missing",
                "root_cause": "The corpus map does not expose selected-ad detail and nearest-neighbor examples.",
                "evidence": f"detail={metrics.get('mapSelectedDetailText', '')[:80]} neighbors={metrics.get('mapNeighborButtons')}",
                "severity": "medium",
            }
        )
    if metrics.get("facetCards", 0) == 0 or metrics.get("taxonomyRows", 0) <= 1:
        issues.append(
            {
                "issue": "Facet or taxonomy sections did not render",
                "root_cause": "The Facets-inspired overview or annotation taxonomy matrix is empty.",
                "evidence": f"facets={metrics.get('facetCards')} taxonomyRows={metrics.get('taxonomyRows')}",
                "severity": "medium",
            }
        )
    if (
        not interactions.get("networkFilterLeavesNodes")
        or not interactions.get("networkHiddenModeHidesLabels")
        or not interactions.get("networkSmartModeShowsLabels")
        or not interactions.get("mapSearchLeavesPoints")
        or not interactions.get("mapClickPopulatesDetail")
        or not interactions.get("mapDeepClusterColorWorks")
        or not interactions.get("mapClusterLayerControlsWork")
        or not interactions.get("mapProjectionControlsWork")
        or not interactions.get("mapIsolationControlsWork")
        or not interactions.get("mapQuadrantsUseful")
    ):
        issues.append(
            {
                "issue": "Advanced visualization controls are broken",
                "root_cause": "Network filtering/label modes or corpus-map search/click detail failed during audit interactions.",
                "evidence": json.dumps(interactions, sort_keys=True),
                "severity": "medium",
            }
        )
    if metrics["ledgerRows"] == 0 or metrics["modelRows"] == 0 or metrics["waterfallRows"] == 0:
        issues.append(
            {
                "issue": "Detail panes are incomplete",
                "root_cause": "One or more synchronized detail panes failed to populate after row selection.",
                "evidence": f"ledger={metrics['ledgerRows']} model={metrics['modelRows']} waterfall={metrics['waterfallRows']}",
                "severity": "high",
            }
        )
    return issues[:10]


def audit(report: Path, out: Path) -> dict[str, Any]:
    results: dict[str, Any] = {"report": str(report), "viewports": {}}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            for name, viewport in {"desktop": {"width": 1440, "height": 1000}, "mobile": {"width": 390, "height": 844}}.items():
                page = browser.new_page(viewport=viewport)
                console_errors: list[str] = []
                page_errors: list[str] = []
                page.on("console", lambda msg, bucket=console_errors: bucket.append(msg.text) if msg.type in {"error", "warning"} else None)
                page.on("pageerror", lambda exc, bucket=page_errors: bucket.append(str(exc)))
                page.goto(report.resolve().as_uri(), wait_until="load")
                page.wait_for_selector("#rankList .rank", timeout=20_000)
                page.wait_for_selector("#annotatedText", timeout=20_000)
                metrics = collect_metrics(page)
                interactions = exercise_interactions(page)
                after_metrics = collect_metrics(page)
                results["viewports"][name] = {
                    "metrics": metrics,
                    "afterInteractions": after_metrics,
                    "interactions": interactions,
                    "consoleErrors": console_errors,
                    "pageErrors": page_errors,
                    "issues": issue_list(metrics, interactions, console_errors, page_errors),
                }
                page.close()
        finally:
            browser.close()
    all_issues: list[dict[str, str]] = []
    seen: set[str] = set()
    for viewport_result in results["viewports"].values():
        for issue in viewport_result["issues"]:
            key = issue["issue"]
            if key not in seen:
                seen.add(key)
                all_issues.append(issue)
    results["topIssues"] = all_issues[:10]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    results = audit(args.report, args.out)
    print(json.dumps({"out": str(args.out), "topIssues": results["topIssues"]}, indent=2, sort_keys=True))
    return 1 if results["topIssues"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
