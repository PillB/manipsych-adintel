"""Local smoke test — load the patched v2 dashboard HTML in headless Playwright
and verify no console errors + key elements render.
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

HTML_PATH = Path("/home/z/my-project/docs/reports/adintel/adintel_dashboard_v2.html").resolve()

def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        console_errors = []
        page_errors = []
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: page_errors.append(str(e)))

        url = f"file://{HTML_PATH}"
        print(f"Loading: {url}")
        page.goto(url, wait_until="networkidle", timeout=30_000)
        page.wait_for_timeout(2000)

        # Check key elements
        checks = []
        nav_links = page.locator("nav.task-nav a").all_text_contents()
        checks.append(("5 nav sections", len(nav_links) >= 5))
        checks.append(("Mission Control visible", "Mission Control" in " ".join(nav_links)))

        # Click Models & Lab tab
        page.locator('nav.task-nav a[data-section="models-lab"]').click()
        page.wait_for_timeout(800)
        # Click validation subtab — use evaluate to force-click
        page.evaluate('document.querySelector(\'[data-subtab="validation"]\').click();')
        page.wait_for_timeout(800)
        validation_text = page.locator("#validation-detail").inner_text()
        checks.append(("Contrast-set table in validation", "Contrast-set evaluation" in validation_text))
        checks.append(("Platt formula in validation", "sigmoid" in validation_text))

        # Click Explore tab
        page.locator('nav.task-nav a[data-section="explore"]').click()
        page.wait_for_timeout(800)
        # Click clusters subtab
        page.evaluate('document.querySelector(\'[data-subtab="clusters"]\').click();')
        page.wait_for_timeout(800)
        clusters_text = page.locator("#subtab-clusters").inner_text()
        checks.append(("Real HDBSCAN benchmark", "68 clusters" in clusters_text))
        checks.append(("Real HDBSCAN noise fraction", "83.9%" in clusters_text))

        # Click corpus map subtab
        page.evaluate('document.querySelector(\'[data-subtab="corpus-map"]\').click();')
        page.wait_for_timeout(3000)  # Wait for fetch
        map_text = page.locator("#corpus-map-viz").inner_text()
        checks.append(("Real UMAP projection label", "Real UMAP" in map_text))
        # Check that real coords were loaded (not fallback)
        checks.append(("Real UMAP coords loaded (not fallback)", "real coords" in map_text))

        # Click registry subtab
        page.evaluate('document.querySelector(\'[data-subtab="registry"]\').click();')
        page.wait_for_timeout(800)
        registry_text = page.locator("#subtab-registry").inner_text()
        checks.append(("Real Platt metrics in registry", "Brier" in registry_text and "0.0001" in registry_text))

        # Click authorship subtab
        page.evaluate('document.querySelector(\'[data-subtab="authorship"]\').click();')
        page.wait_for_timeout(800)
        auth_text = page.locator("#subtab-authorship").inner_text()
        checks.append(("Authorship calibrated label", "Platt-calibrated" in auth_text or "Brier" in auth_text))

        print("\n--- Local smoke test results ---")
        for name, ok in checks:
            print(f"  {'✓' if ok else '✗'} {name}")
        print(f"\n--- Console errors: {len(console_errors)} ---")
        for e in console_errors[:5]:
            print(f"  - {e[:200]}")
        print(f"--- Page errors: {len(page_errors)} ---")
        for e in page_errors[:5]:
            print(f"  - {e[:200]}")

        n_pass = sum(1 for _, ok in checks if ok)
        n_total = len(checks)
        print(f"\nResult: {n_pass}/{n_total} checks passed, {len(console_errors)} console errors, {len(page_errors)} page errors")

        browser.close()
        return 0 if n_pass == n_total and not console_errors and not page_errors else 1

if __name__ == "__main__":
    sys.exit(main())
