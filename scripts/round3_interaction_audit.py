"""Round 3 interaction audit: find functional gaps in the live dashboard."""
from playwright.sync_api import sync_playwright
import os, json, time

LIVE_URL = os.environ.get("SOLARIZE_LIVE_URL", "https://pillb.github.io/manipsych-adintel/reports/adintel/adintel_dashboard.html")
CB = str(int(time.time()))
URL = f"{LIVE_URL}?cb={CB}"

findings = []

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(viewport={"width": 1366, "height": 900})
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)

    pg.goto(URL, wait_until="networkidle", timeout=60_000)
    pg.wait_for_timeout(3000)

    # 1. Check that the full-ad-table fetch actually works on HTTPS
    pg.goto(f"{URL}#adintel-data", wait_until="networkidle")
    pg.wait_for_timeout(2000)
    search = pg.locator("#adintel-full-ad-search")
    if search.count() > 0:
        search.first.click()
        pg.wait_for_timeout(500)
        search.first.fill("h_")
        pg.wait_for_timeout(3000)
        count_text = pg.locator("#adintel-full-ad-count").inner_text()
        results_count = pg.locator("#adintel-full-ad-results .ad-result-row").count()
        findings.append({
            "test": "full_ad_table_fetch",
            "count_text": count_text,
            "results_rendered": results_count,
            "passed": results_count > 0 and "match" in count_text.lower(),
        })
        if results_count == 0:
            findings.append({"test": "full_ad_table_fetch", "issue": "fetch returned 0 results — check CORS or fetch failure"})

    # 2. Check cluster-card click sets the filter
    pg.goto(f"{URL}#adintel-clustering", wait_until="networkidle")
    pg.wait_for_timeout(2000)
    cluster_card = pg.locator(".cluster-card").first
    if cluster_card.count() > 0:
        cluster_card.click()
        pg.wait_for_timeout(1000)
        filter_val = pg.locator("#adintel-cluster-filter").first.evaluate("el => el.value")
        findings.append({
            "test": "cluster_card_click_sets_filter",
            "filter_value": filter_val,
            "passed": filter_val != "",
        })

    # 3. Check ad selector + detail panel
    pg.goto(f"{URL}#adintel-clustering", wait_until="networkidle")
    pg.wait_for_timeout(2000)
    selector = pg.locator("#adintel-ad-selector")
    selector.first.fill("h_")
    pg.wait_for_timeout(1500)
    results = pg.locator("#adintel-ad-results .ad-result-row")
    if results.count() > 0:
        results.first.click()
        pg.wait_for_timeout(1500)
        detail_text = pg.locator("#adintel-ad-detail").first.inner_text().lower()
        findings.append({
            "test": "ad_selector_detail",
            "has_cluster": "cluster" in detail_text,
            "has_outlier": "outlier" in detail_text or "inlier" in detail_text,
            "has_alternative": "alternative_cluster" in detail_text,
            "has_neighbors": "neighbor" in detail_text,
            "has_uncertainty": "uncertainty" in detail_text or "limitation" in detail_text,
            "detail_length": len(detail_text),
        })

    # 4. Check term-comparison tables are interactive (sortable? filterable?)
    pg.goto(f"{URL}#adintel-outliers", wait_until="networkidle")
    pg.wait_for_timeout(2000)
    term_blocks = pg.locator("[data-field='term_comparison']").count()
    term_rows = pg.locator("[data-field='term_comparison_row']").count()
    # Check if any rows are marked meaningful
    meaningful_rows = pg.locator("[data-field='term_comparison_row'][data-meaningful='true']").count()
    findings.append({
        "test": "term_comparison_tables",
        "n_blocks": term_blocks,
        "n_rows": term_rows,
        "n_meaningful": meaningful_rows,
        "passed": term_blocks == 3 and term_rows > 0,
    })

    # 5. Check mobile rendering of new sections
    ctx2 = b.new_context(viewport={"width": 375, "height": 750}, is_mobile=True, has_touch=True)
    pg2 = ctx2.new_page()
    pg2.goto(f"{URL}#adintel-data", wait_until="networkidle", timeout=60_000)
    pg2.wait_for_timeout(2000)
    overflow = pg2.evaluate("() => ({scrollW: document.documentElement.scrollWidth, clientW: document.documentElement.clientWidth})")
    findings.append({
        "test": "mobile_data_section_overflow",
        "scrollW": overflow["scrollW"],
        "clientW": overflow["clientW"],
        "passed": overflow["scrollW"] <= overflow["clientW"] + 5,
    })
    # Check the full-ad-table search works on mobile
    search2 = pg2.locator("#adintel-full-ad-search")
    if search2.count() > 0:
        search2.first.click()
        pg2.wait_for_timeout(500)
        search2.first.fill("doplim")
        pg2.wait_for_timeout(3000)
        mobile_results = pg2.locator("#adintel-full-ad-results .ad-result-row").count()
        findings.append({
            "test": "mobile_full_ad_search",
            "results": mobile_results,
            "passed": mobile_results > 0,
        })
    ctx2.close()

    # 6. Check for any console/page errors
    findings.append({
        "test": "no_js_errors",
        "n_errors": len(errors),
        "errors": errors[:5],
        "passed": len(errors) == 0,
    })

    # 7. Check deep-link hash works
    pg.goto(f"{URL}#adintel-methodology", wait_until="networkidle")
    pg.wait_for_timeout(1000)
    meth_visible = pg.locator("#adintel-methodology").count() > 0
    findings.append({"test": "methodology_deep_link", "passed": meth_visible})

    pg.goto(f"{URL}#adintel-audit", wait_until="networkidle")
    pg.wait_for_timeout(1000)
    audit_visible = pg.locator("#adintel-audit").count() > 0
    findings.append({"test": "audit_deep_link", "passed": audit_visible})

    # 8. Check that the ad selector has a "no results" graceful state
    pg.goto(f"{URL}#adintel-clustering", wait_until="networkidle")
    pg.wait_for_timeout(2000)
    selector.first.fill("zzzzz_no_match_zzzzz")
    pg.wait_for_timeout(1000)
    no_results_text = pg.locator("#adintel-ad-results").inner_text()
    findings.append({
        "test": "ad_selector_no_results_state",
        "text": no_results_text[:200],
        "passed": "no ads match" in no_results_text.lower() or "no results" in no_results_text.lower(),
    })

    ctx.close()
    b.close()

print(json.dumps(findings, indent=2))
