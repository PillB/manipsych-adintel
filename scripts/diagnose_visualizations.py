"""Diagnose all scatterplots and interactive controls on the live dashboard."""
from playwright.sync_api import sync_playwright
import json, time, os

LIVE_URL = os.environ.get("SOLARIZE_LIVE_URL", "https://pillb.github.io/manipsych-adintel/reports/adintel/adintel_dashboard.html")
CB = str(int(time.time()))
URL = f"{LIVE_URL}?cb={CB}"

findings = {}

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(viewport={"width": 1366, "height": 900})
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)

    pg.goto(URL, wait_until="networkidle", timeout=60_000)
    pg.wait_for_timeout(3000)

    # 1. Corpus map: check SVG + circles + controls
    pg.goto(f"{URL}#corpus-map", wait_until="networkidle")
    pg.wait_for_timeout(2000)
    corpus_map = {
        "svg_count": pg.locator("#corpusMapViz svg").count(),
        "circle_count": pg.locator("#corpusMapViz svg circle").count(),
        "map_point_count": pg.locator("#corpusMapViz circle.map-point").count(),
        "mapColor_count": pg.locator("#mapColor").count(),
        "mapQuery_count": pg.locator("#mapQuery").count(),
        "mapResetLayers_count": pg.locator("#mapResetLayers").count(),
        "mapSelectedDetail_count": pg.locator("#mapSelectedDetail").count(),
        "mapSelectedDetail_text": pg.locator("#mapSelectedDetail").first.inner_text()[:200] if pg.locator("#mapSelectedDetail").count() > 0 else "",
        "mapNeighbors_count": pg.locator("#mapNeighbors").count(),
        "mapLegend_count": pg.locator("#mapLegend").count(),
    }
    # Try clicking a point
    points = pg.locator("#corpusMapViz circle.map-point")
    if points.count() > 0:
        points.first.click(force=True, timeout=5000)
        pg.wait_for_timeout(1000)
        corpus_map["after_click_detail"] = pg.locator("#mapSelectedDetail").first.inner_text()[:300]
        corpus_map["after_click_neighbors"] = pg.locator("#mapNeighbors").first.inner_text()[:300]
    # Try mapColor change
    mapColor = pg.locator("#mapColor")
    if mapColor.count() > 0:
        # Get current value
        corpus_map["mapColor_initial"] = mapColor.first.evaluate("el => el.value")
        # Change to a different value
        mapColor.first.select_option(index=1)
        pg.wait_for_timeout(500)
        corpus_map["mapColor_after"] = mapColor.first.evaluate("el => el.value")
    # Try mapQuery
    mapQuery = pg.locator("#mapQuery")
    if mapQuery.count() > 0:
        mapQuery.first.fill("lima")
        pg.wait_for_timeout(1000)
        corpus_map["after_mapQuery"] = pg.locator("#corpusMapViz svg circle").count()
    findings["corpus_map"] = corpus_map

    # 2. Explorer: check rank list + filters + scatterplot
    pg.goto(f"{URL}#explorer", wait_until="networkidle")
    pg.wait_for_timeout(2000)
    explorer = {
        "rank_rows": pg.locator("#explorer .rank").count(),
        "rankMode_count": pg.locator("#rankMode").count(),
        "platformFilter_count": pg.locator("#platformFilter").count(),
        "labelFilter_count": pg.locator("#labelFilter").count(),
        "query_count": pg.locator("#query").count(),
    }
    # Check rank mode options
    rankMode = pg.locator("#rankMode")
    if rankMode.count() > 0:
        explorer["rankMode_options"] = rankMode.first.evaluate("el => Array.from(el.options).map(o => o.value)")
        explorer["rankMode_initial"] = rankMode.first.evaluate("el => el.value")
    # Check platform filter options
    platformFilter = pg.locator("#platformFilter")
    if platformFilter.count() > 0:
        explorer["platformFilter_options"] = platformFilter.first.evaluate("el => Array.from(el.options).map(o => o.value)")
    # Check if there's a scatterplot in the explorer
    explorer["explorer_svg_count"] = pg.locator("#explorer svg").count()
    explorer["explorer_canvas_count"] = pg.locator("#explorer canvas").count()
    findings["explorer"] = explorer

    # 3. Diagnostics: check curves + heatmap
    pg.goto(f"{URL}#diagnostics", wait_until="networkidle")
    pg.wait_for_timeout(2000)
    diagnostics = {
        "curveChart_count": pg.locator("#curveChart").count(),
        "curveChart_svg_count": pg.locator("#curveChart svg").count(),
        "curveChart_path_count": pg.locator("#curveChart svg path").count(),
        "heatmap_count": pg.locator("#heatmap, #heatmapChart, .heat").count(),
        "slices_count": pg.locator("#slices, .slice-card").count(),
    }
    findings["diagnostics"] = diagnostics

    # 4. Term network
    pg.goto(f"{URL}#term-network", wait_until="networkidle")
    pg.wait_for_timeout(2000)
    term_network = {
        "svg_count": pg.locator("#termNetwork svg, #termNetworkViz svg").count(),
        "circle_count": pg.locator("#termNetwork svg circle, #termNetworkViz svg circle").count(),
        "networkKind_count": pg.locator("#networkKind").count(),
        "networkTopN_count": pg.locator("#networkTopN").count(),
        "networkLabelMode_count": pg.locator("#networkLabelMode").count(),
    }
    findings["term_network"] = term_network

    # 5. Check all errors
    findings["errors"] = errors[:10]
    findings["n_errors"] = len(errors)

    ctx.close()
    b.close()

print(json.dumps(findings, indent=2))
