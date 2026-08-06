"""Quick local check of the new Round 2 sections via file://."""
from playwright.sync_api import sync_playwright
from pathlib import Path

DASHBOARD = Path("/home/z/my-project/repo/reports/adintel/adintel_dashboard.html")

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(viewport={"width": 1366, "height": 900})
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)

    pg.goto(f"file://{DASHBOARD}#adintel-methodology", wait_until="networkidle")
    pg.wait_for_timeout(1500)
    print("=== #adintel-methodology ===")
    text = pg.locator("#adintel-methodology").inner_text()
    for term in ("wilson", "cohen", "benjamini", "min-support", "k=5", "meaningfully"):
        print(f"  {term}: {'FOUND' if term in text.lower() else 'MISSING'}")
    print(f"  section length: {len(text)} chars")

    pg.goto(f"file://{DASHBOARD}#adintel-audit", wait_until="networkidle")
    pg.wait_for_timeout(1500)
    print("\n=== #adintel-audit ===")
    text = pg.locator("#adintel-audit").inner_text()
    for term in ("red phase", "verification round", "playwright", "build fingerprint"):
        print(f"  {term}: {'FOUND' if term in text.lower() else 'MISSING'}")
    print(f"  section length: {len(text)} chars")

    pg.goto(f"file://{DASHBOARD}#adintel-data", wait_until="networkidle")
    pg.wait_for_timeout(1500)
    print("\n=== #adintel-data ===")
    text = pg.locator("#adintel-data").inner_text()
    for term in ("download", "solarize_summary.json", "solarize_per_ad.jsonl", "4,540"):
        print(f"  {term}: {'FOUND' if term in text.lower() else 'MISSING'}")
    print(f"  section length: {len(text)} chars")
    # Check the full-ad-search input exists
    full_search = pg.locator("#adintel-full-ad-search").count()
    print(f"  #adintel-full-ad-search: {full_search}")

    # Test the full-ad-table fetch (file:// won't work for fetch, but check the UI is there)
    pg.goto(f"file://{DASHBOARD}#adintel-data", wait_until="networkidle")
    pg.wait_for_timeout(1500)
    full_search_el = pg.locator("#adintel-full-ad-search")
    if full_search_el.count() > 0:
        full_search_el.first.click()
        pg.wait_for_timeout(500)
        full_search_el.first.fill("h_")
        pg.wait_for_timeout(2000)
        results_text = pg.locator("#adintel-full-ad-results").inner_text()
        print(f"\n=== Full-ad-table search results (file://) ===")
        print(f"  results: {results_text[:200]}")

    # Test cluster-card click sets the filter
    pg.goto(f"file://{DASHBOARD}#adintel-clustering", wait_until="networkidle")
    pg.wait_for_timeout(2000)
    cluster_card = pg.locator(".cluster-card").first
    if cluster_card.count() > 0:
        cluster_card.click()
        pg.wait_for_timeout(500)
        filter_val = pg.locator("#adintel-cluster-filter").first.evaluate("el => el.value")
        print(f"\n=== Cluster-card click ===")
        print(f"  cluster filter set to: {filter_val!r}")

    print(f"\n=== Errors ({len(errors)}) ===")
    for e in errors[:5]:
        print(f"  {e}")

    ctx.close()
    b.close()
