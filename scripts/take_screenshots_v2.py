"""Take comprehensive screenshots for VLM analysis — all new features."""
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

LIVE_URL = "https://pillb.github.io/manipsych-adintel/reports/adintel/adintel_dashboard_v2.html"
OUT_DIR = Path("/home/z/my-project/audit/solarize-rebuild/round10/screenshots")
OUT_DIR.mkdir(parents=True, exist_ok=True)

def click_js(page, selector_js):
    """Safely click via JS dispatch."""
    page.evaluate(f'''() => {{
        const el = {selector_js};
        if (el) {{
            const evt = new MouseEvent('click', {{bubbles: true}});
            el.dispatchEvent(evt);
        }}
    }}''')

def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        
        console_errors = []
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        
        # 1. Mission Control
        print("1. Mission Control...")
        page.goto(LIVE_URL + "?cb=" + str(int(time.time())), wait_until="networkidle", timeout=60_000)
        page.wait_for_timeout(3000)
        page.screenshot(path=str(OUT_DIR / "01_mission_control.png"))
        
        # 2. Corpus Map — UMAP (default)
        print("2. Corpus Map (UMAP)...")
        page.evaluate('document.querySelector(\'nav.task-nav a[data-section="explore"]\').click();')
        page.wait_for_timeout(1000)
        page.evaluate('document.querySelector(\'[data-subtab="corpus-map"]\').click();')
        page.wait_for_timeout(6000)
        page.screenshot(path=str(OUT_DIR / "02_corpus_map_umap.png"))
        
        # 3. Switch to t-SNE
        print("3. Corpus Map (t-SNE)...")
        page.evaluate('document.getElementById("projMode").value = "tsne";')
        page.evaluate('document.getElementById("projMode").dispatchEvent(new Event("change"));')
        page.wait_for_timeout(6000)
        page.screenshot(path=str(OUT_DIR / "03_corpus_map_tsne.png"))
        
        # 4. Switch back to UMAP, HDBSCAN color mode
        print("4. Corpus Map (UMAP + HDBSCAN color)...")
        page.evaluate('document.getElementById("projMode").value = "umap";')
        page.evaluate('document.getElementById("umapColor").value = "hdbscan";')
        page.evaluate('document.getElementById("umapColor").dispatchEvent(new Event("change"));')
        page.wait_for_timeout(8000)
        page.screenshot(path=str(OUT_DIR / "04_corpus_map_hdbscan.png"))
        
        # 5. Click cluster card (go to clusters first, then click)
        print("5. Cluster highlight...")
        page.evaluate('document.querySelector(\'[data-subtab="clusters"]\').click();')
        page.wait_for_timeout(2000)
        # Click first HDBSCAN cluster card
        page.evaluate('''() => {
            const b = document.querySelector('details summary b');
            if (b) {
                const evt = new MouseEvent('click', {bubbles: true});
                b.dispatchEvent(evt);
            }
        }''')
        page.wait_for_timeout(10000)
        page.screenshot(path=str(OUT_DIR / "05_cluster_highlighted.png"))
        
        # 6. Click a point on the map
        print("6. Ad detail with cluster drivers...")
        page.evaluate('''() => {
            const circles = document.querySelectorAll('circle.umap-point');
            if (circles.length > 5) {
                const evt = new MouseEvent('click', {bubbles: true});
                circles[5].dispatchEvent(evt);
            }
        }''')
        page.wait_for_timeout(2000)
        page.screenshot(path=str(OUT_DIR / "06_ad_detail_drivers.png"))
        
        print(f"\nConsole errors: {len(console_errors)}")
        for e in console_errors[:5]:
            print(f"  - {e[:150]}")
        
        browser.close()
        print(f"\nScreenshots saved to: {OUT_DIR}")

if __name__ == "__main__":
    main()
