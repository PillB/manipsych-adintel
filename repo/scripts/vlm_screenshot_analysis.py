#!/usr/bin/env python3
"""Item 2: Use Playwright to navigate to live ad pages and capture screenshots,
then use VLM to analyze the images for visual persuasion techniques.

This deploys a local browser session, navigates to each ad URL, captures a
screenshot, and analyzes it with the z-ai VLM.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

RAW_ADS = ROOT / "data" / "raw" / "ads"
SCREENSHOTS_DIR = ROOT / "data" / "processed" / "ad_screenshots"
OUT = ROOT / "data" / "processed" / "vlm_screenshot_analysis.jsonl"
OUT_REPORT = ROOT / "reports" / "adintel" / "vlm_screenshot_report.json"

SAMPLE_SIZE = 10  # navigate to 10 live ad pages


def extract_ad_urls(html_files: list[Path], limit: int = 20) -> list[str]:
    """Extract ad detail-page URLs from raw HTML files."""
    urls = []
    seen = set()
    for html_file in html_files:
        try:
            content = html_file.read_text(errors="ignore")
        except Exception:
            continue
        # Find canonical or og:url
        for m in re.finditer(r'(?:canonical|og:url)[^>]*href=["\']([^"\']+)["\']', content, re.I):
            url = m.group(1)
            if "doplim" in url or "locanto" in url:
                if url not in seen and "/ID_" not in url:
                    seen.add(url)
                    urls.append(url)
                    if len(urls) >= limit:
                        return urls
        # Also check for raw links in the HTML
        for m in re.finditer(r'href=["\'](https://(?:www\.)?(?:doplim|locanto)[^"\']+)["\']', content, re.I):
            url = m.group(1)
            if "/ID_" in url or "/-/" in url:
                if url not in seen:
                    seen.add(url)
                    urls.append(url)
                    if len(urls) >= limit:
                        return urls
    return urls


def capture_screenshot(url: str, out_path: Path) -> bool:
    """Use Playwright to navigate to URL and capture screenshot."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(2000)
            page.screenshot(path=str(out_path), full_page=False)
            browser.close()
        return out_path.exists() and out_path.stat().st_size > 1000
    except Exception as e:
        print(f"  Screenshot failed for {url[:60]}: {e}")
        return False


def analyze_with_vlm(image_path: Path) -> dict:
    """Use z-ai VLM CLI to analyze the screenshot."""
    out_json = Path(str(image_path) + ".json")
    try:
        result = subprocess.run(
            ["z-ai", "vision",
             "-p", "Analyze this advertisement screenshot. Answer in JSON: {has_person, has_text_overlay, has_logo, has_luxury_elements, has_sexualised_content, gaze_at_camera, urgency_words_visible, contact_info_visible, description}.",
             "-i", str(image_path),
             "-o", str(out_json)],
            capture_output=True, timeout=30, text=True
        )
        if result.returncode != 0 or not out_json.exists():
            return {"error": result.stderr[:200] if result.stderr else "unknown"}
        data = json.loads(out_json.read_text())
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        try:
            json_match = re.search(r'\{[^}]+\}', content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except Exception:
            pass
        return {"raw_content": content[:500]}
    except Exception as e:
        return {"error": str(e)}
    finally:
        out_json.unlink(missing_ok=True)


def main() -> int:
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    html_files = sorted(RAW_ADS.glob("*.html"))[:200]
    print(f"Scanning {len(html_files)} HTML files for ad URLs...")
    urls = extract_ad_urls(html_files, limit=SAMPLE_SIZE)
    print(f"Found {len(urls)} ad URLs to screenshot")

    results = []
    for i, url in enumerate(urls[:SAMPLE_SIZE]):
        print(f"  [{i+1}/{SAMPLE_SIZE}] {url[:80]}")
        screenshot_path = SCREENSHOTS_DIR / f"ad_screenshot_{i}.png"
        if capture_screenshot(url, screenshot_path):
            analysis = analyze_with_vlm(screenshot_path)
            results.append({
                "url": url,
                "screenshot": str(screenshot_path),
                "analysis": analysis,
            })
        else:
            results.append({"url": url, "error": "screenshot_failed"})

    # Write results
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Summary
    n_success = sum(1 for r in results if "analysis" in r and "error" not in r.get("analysis", {}))
    n_person = sum(1 for r in results if r.get("analysis", {}).get("has_person"))
    n_text = sum(1 for r in results if r.get("analysis", {}).get("has_text_overlay"))
    n_logo = sum(1 for r in results if r.get("analysis", {}).get("has_logo"))
    n_sexual = sum(1 for r in results if r.get("analysis", {}).get("has_sexualised_content"))
    n_urgency = sum(1 for r in results if r.get("analysis", {}).get("urgency_words_visible"))

    report = {
        "analysis_type": "vlm_screenshot_analysis_live_pages",
        "n_pages_navigated": len(results),
        "n_successful": n_success,
        "vlm_model": "z-ai-web-dev-sdk vision (GLM-4V)",
        "findings": {
            "pages_with_person": n_person,
            "pages_with_text_overlay": n_text,
            "pages_with_logo": n_logo,
            "pages_with_sexualised_content": n_sexual,
            "pages_with_urgency_words": n_urgency,
        },
        "vp_leaf_estimates": {
            "vp_gaze_direction": round(n_person / max(n_success, 1) * 0.5, 4),
            "vp_luxury_aesthetic": round(sum(1 for r in results if r.get("analysis", {}).get("has_luxury_elements")) / max(n_success, 1), 4),
            "vp_sexualised_imagery": round(n_sexual / max(n_success, 1), 4),
        },
        "method": "Playwright navigated to live ad URLs, captured screenshots, VLM analyzed each",
        "output": str(OUT),
        "screenshots_dir": str(SCREENSHOTS_DIR),
    }

    OUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUT_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nVLM Screenshot Analysis:")
    print(f"  Pages navigated: {len(results)}")
    print(f"  Successful: {n_success}")
    print(f"  VP estimates: {report['vp_leaf_estimates']}")
    print(f"  Output: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
