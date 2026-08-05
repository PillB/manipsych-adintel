#!/usr/bin/env python3
"""Deep-dive Playwright audit: screenshot every section, capture layout metrics,
and identify visual defects for VLM review."""

from playwright.sync_api import sync_playwright
import json, time, os
from pathlib import Path

BASE = "https://pillb.github.io/manipsych-adintel/reports/adintel/adintel_dashboard.html"
OUT = Path("/home/z/my-project/repo/audit/assurance/evidence/deep_dive")
OUT.mkdir(parents=True, exist_ok=True)

SECTIONS = [
    ("metrics", "01_metrics"),
    ("pipeline", "02_pipeline"),
    ("diagnostics", "03_diagnostics"),
    ("curveChart", "04_curves"),
    ("iterationTimeline", "05_timeline"),
    ("metricHeatmap", "06_heatmap"),
    ("errorTimeline", "07_error_lifecycle"),
    ("sliceWeakness", "08_slices"),
    ("clusterSummary", "09_clusters"),
    ("thresholdOverlay", "10_threshold"),
    ("explainability-atlas", "11_explainability"),
    ("term-network", "12_term_network"),
    ("corpus-map", "13_corpus_map"),
    ("facet-overview", "14_facets"),
    ("explorer", "15_explorer"),
    ("observability", "16_observability"),
    ("expert-poc", "17_expert_poc"),
    ("adintel-taxonomy", "18_taxonomy"),
    ("adintel-profile", "19_profile"),
    ("adintel-clustering", "20_clustering"),
    ("adintel-authorship", "21_authorship"),
    ("adintel-outliers", "22_outliers"),
    ("adintel-checkpoints", "23_checkpoints"),
    ("adintel-challenges", "24_challenges"),
    ("research", "25_research"),
]

def capture(page, section_id, name):
    """Capture screenshot + layout metrics for one section."""
    # Click nav link
    link = page.locator(f'nav.nav a[href="#{section_id}"]')
    if link.count() > 0:
        link.click()
    else:
        page.evaluate(f'document.getElementById("{section_id}")?.scrollIntoView()')
    page.wait_for_timeout(1500)

    # Screenshot
    ss_path = OUT / f"{name}.png"
    page.screenshot(path=str(ss_path), full_page=False)

    # Layout metrics: check for overflow, clipping, overlap
    metrics = page.evaluate(f"""() => {{
        const el = document.getElementById("{section_id}");
        if (!el) return {{found: false}};
        const rect = el.getBoundingClientRect();
        const style = window.getComputedStyle(el);
        // Check children for overflow
        const children = el.querySelectorAll('*');
        let overflowCount = 0;
        let clippedCount = 0;
        for (const child of children) {{
            const cr = child.getBoundingClientRect();
            const cs = window.getComputedStyle(child);
            // Check if child extends beyond parent
            if (cr.right > rect.right + 5 || cr.bottom > rect.bottom + 5) {{
                overflowCount++;
            }}
            // Check if child is clipped (has content but zero visible height)
            if (cs.overflow === 'hidden' && cr.height > 0 && cr.width > 0) {{
                const innerHeight = child.scrollHeight;
                if (innerHeight > cr.height + 10) {{
                    clippedCount++;
                }}
            }}
        }}
        // Check for elements with negative or zero dimensions
        let zeroDimCount = 0;
        for (const child of children) {{
            const cr = child.getBoundingClientRect();
            if (cr.width === 0 || cr.height === 0) {{
                zeroDimCount++;
            }}
        }}
        return {{
            found: true,
            top: rect.top,
            left: rect.left,
            width: rect.width,
            height: rect.height,
            scrollWidth: el.scrollWidth,
            scrollHeight: el.scrollHeight,
            clientWidth: el.clientWidth,
            clientHeight: el.clientHeight,
            overflowX: rect.width < el.scrollWidth,
            overflowY: rect.height < el.scrollHeight,
            childOverflowCount: overflowCount,
            childClippedCount: clippedCount,
            zeroDimCount: zeroDimCount,
            nChildren: children.length,
        }};
    }}""")
    return {"section": section_id, "name": name, "screenshot": str(ss_path), "metrics": metrics}

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        page = context.new_page()

        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)

        page.goto(BASE, wait_until="networkidle", timeout=30_000)
        page.wait_for_timeout(3000)

        # Hero screenshot
        page.screenshot(path=str(OUT / "00_hero.png"))

        results = []
        for sid, name in SECTIONS:
            print(f"  Capturing {name}...", flush=True)
            r = capture(page, sid, name)
            results.append(r)

        # Mobile screenshot
        page.set_viewport_size({"width": 375, "height": 812})
        page.wait_for_timeout(500)
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(300)
        page.screenshot(path=str(OUT / "26_mobile.png"))
        overflow = page.evaluate("""() => ({
            scrollWidth: document.documentElement.scrollWidth,
            clientWidth: document.documentElement.clientWidth,
            overflow: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) - window.innerWidth
        })""")
        page.set_viewport_size({"width": 1400, "height": 900})

        # Interactive analyzer
        page.goto("https://pillb.github.io/manipsych-adintel/interactive_analyzer.html", wait_until="networkidle")
        page.wait_for_timeout(2000)
        page.screenshot(path=str(OUT / "27_analyzer.png"))
        page.locator("button:has-text('Run GAN')").click()
        page.wait_for_timeout(2000)
        page.locator("#gan").scroll_into_view_if_needed()
        page.wait_for_timeout(500)
        page.screenshot(path=str(OUT / "28_gan.png"))

        browser.close()

    report = {
        "url": BASE,
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "n_screenshots": len(list(OUT.glob("*.png"))),
        "console_errors": errors[:10],
        "n_console_errors": len(errors),
        "sections": results,
        "mobile_overflow_px": overflow["overflow"],
    }
    (OUT / "deep_dive_report.json").write_text(json.dumps(report, indent=2))
    print(f"\n{report['n_screenshots']} screenshots, {report['n_console_errors']} errors, mobile overflow: {report['mobile_overflow_px']}px")

if __name__ == "__main__":
    main()
