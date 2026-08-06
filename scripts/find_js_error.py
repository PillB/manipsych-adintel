"""Find the JS syntax error in the generated dashboard."""
from playwright.sync_api import sync_playwright
from pathlib import Path

DASHBOARD = Path("/home/z/my-project/repo/reports/adintel/adintel_dashboard.html")

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context()
    pg = ctx.new_page()
    errors = []
    pg.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
    pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    pg.goto(f"file://{DASHBOARD}", wait_until="networkidle")
    pg.wait_for_timeout(2000)
    print("Errors:")
    for e in errors[:10]:
        print(f"  {e}")
    # Try to evaluate the Solarize IIFE manually to find the line
    try:
        result = pg.evaluate("""() => {
            try {
                const el = document.getElementById('solarize-data');
                if (!el) return 'no solarize-data';
                const d = JSON.parse(el.textContent);
                return `per_ad_selector: ${d.per_ad_selector ? d.per_ad_selector.length : 0}`;
            } catch (e) { return 'error: ' + e.message; }
        }""")
        print(f"\nsolarize-data: {result}")
    except Exception as e:
        print(f"\nEvaluate failed: {e}")
    # Check if the ad selector input exists
    sel = pg.locator("#adintel-ad-selector").count()
    print(f"\n#adintel-ad-selector count: {sel}")
    # Check if #adintel-methodology exists
    meth = pg.locator("#adintel-methodology").count()
    print(f"#adintel-methodology count: {meth}")
    # Check if #adintel-data exists
    data = pg.locator("#adintel-data").count()
    print(f"#adintel-data count: {data}")
    # Check if #adintel-audit exists
    audit = pg.locator("#adintel-audit").count()
    print(f"#adintel-audit count: {audit}")
    ctx.close()
    b.close()
