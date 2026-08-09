"""Take screenshots of the live dashboard for VLM analysis.

Captures:
1. Mission Control (default view)
2. Explore Evidence → Corpus Map (after UMAP coords load)
3. Explore Evidence → Clusters (HDBSCAN cluster cards)
4. After clicking a cluster card (highlighted on map)
5. After clicking an ad point (ad detail)
"""
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

LIVE_URL = "https://pillb.github.io/manipsych-adintel/reports/adintel/adintel_dashboard_v2.html"
OUT_DIR = Path("/home/z/my-project/audit/solarize-rebuild/round9/screenshots")
OUT_DIR.mkdir(parents=True, exist_ok=True)

def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        
        console_errors = []
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append(str(e)))
        
        # 1. Mission Control
        print("1. Mission Control...")
        page.goto(LIVE_URL + "?cb=" + str(int(time.time())), wait_until="networkidle", timeout=60_000)
        page.wait_for_timeout(3000)
        page.screenshot(path=str(OUT_DIR / "01_mission_control.png"))
        
        # 2. Corpus Map
        print("2. Corpus Map...")
        page.evaluate('document.querySelector(\'nav.task-nav a[data-section="explore"]\').click();')
        page.wait_for_timeout(1000)
        page.evaluate('document.querySelector(\'[data-subtab="corpus-map"]\').click();')
        page.wait_for_timeout(5000)  # Wait for UMAP fetch
        page.screenshot(path=str(OUT_DIR / "02_corpus_map.png"))
        
        # 3. Clusters
        print("3. Clusters...")
        page.evaluate('document.querySelector(\'[data-subtab="clusters"]\').click();')
        page.wait_for_timeout(2000)
        page.screenshot(path=str(OUT_DIR / "03_clusters.png"))
        
        # 4. Click first HDBSCAN cluster card
        print("4. Click cluster card...")
        page.evaluate('document.querySelector(\'[data-subtab="corpus-map"]\').click();')
        page.wait_for_timeout(2000)
        # Click first cluster summary
        page.evaluate('''() => {
            const summaries = document.querySelectorAll('details summary');
            if (summaries.length > 0) {
                const firstClusterLink = summaries[0].querySelector('b');
                if (firstClusterLink) firstClusterLink.click();
            }
        }''')
        page.wait_for_timeout(5000)  # Wait for highlight + UMAP
        page.screenshot(path=str(OUT_DIR / "04_cluster_highlighted.png"))
        
        # 5. Click a point on the map
        print("5. Click map point...")
        page.evaluate('''() => {
            const circles = document.querySelectorAll('circle.umap-point');
            if (circles.length > 0) circles[0].click();
        }''')
        page.wait_for_timeout(1000)
        page.screenshot(path=str(OUT_DIR / "05_ad_detail.png"))
        
        # Print console errors
        print(f"\nConsole errors: {len(console_errors)}")
        for e in console_errors[:5]:
            print(f"  - {e[:150]}")
        
        browser.close()
        print(f"\nScreenshots saved to: {OUT_DIR}")

if __name__ == "__main__":
    main()
