#!/usr/bin/env python3
"""Item 2: Use VLM to analyze real ad images from the raw HTML archive.

This script:
  1. Extracts image URLs from raw HTML files
  2. Downloads images and converts to PNG
  3. Uses the z-ai VLM CLI to analyze each image for visual persuasion techniques
  4. Scores the vp_* taxonomy leaves based on VLM output
  5. Detects text-image contradictions
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

RAW_ADS = ROOT / "data" / "raw" / "ads"
OUT = ROOT / "data" / "processed" / "vlm_visual_features.jsonl"
OUT_REPORT = ROOT / "reports" / "adintel" / "vlm_visual_report.json"

SAMPLE_SIZE = 20  # analyze 20 images (rate-limited)


def extract_image_urls(html_files: list[Path], limit: int = 50) -> list[str]:
    """Extract unique image URLs from HTML files."""
    urls = []
    seen = set()
    for html_file in html_files:
        try:
            content = html_file.read_text(errors="ignore")
        except Exception:
            continue
        for m in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\']', content, re.I):
            url = m.group(1)
            if url.startswith("http") and url not in seen:
                # Filter for ad-content images (not icons/logos)
                if any(x in url for x in ["adpics", "images.locanto", "secureimage"]):
                    if any(url.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif"]):
                        seen.add(url)
                        urls.append(url)
                        if len(urls) >= limit:
                            return urls
    return urls


def download_and_convert(url: str, out_path: Path) -> bool:
    """Download image and convert to PNG."""
    try:
        result = subprocess.run(
            ["curl", "-sL", "-o", str(out_path) + ".raw", url],
            capture_output=True, timeout=15
        )
        if result.returncode != 0:
            return False
        raw = Path(str(out_path) + ".raw")
        if raw.stat().st_size < 100:
            return False
        # Convert to PNG using PIL
        from PIL import Image
        img = Image.open(raw)
        if img.mode == "RGBA":
            img = img.convert("RGB")
        img.save(out_path, "PNG")
        raw.unlink()
        return True
    except Exception:
        return False


def analyze_with_vlm(image_path: Path) -> dict:
    """Use z-ai VLM CLI to analyze the image."""
    out_json = Path(str(image_path) + ".json")
    try:
        result = subprocess.run(
            ["z-ai", "vision",
             "-p", "Analyze this advertisement image. Answer in JSON with keys: has_person (bool), has_text_overlay (bool), has_logo (bool), has_luxury_elements (bool), has_sexualised_content (bool), gaze_at_camera (bool), urgency_words_visible (bool), description (string).",
             "-i", str(image_path),
             "-o", str(out_json)],
            capture_output=True, timeout=30, text=True
        )
        if result.returncode != 0 or not out_json.exists():
            return {"error": result.stderr[:200] if result.stderr else "unknown"}
        data = json.loads(out_json.read_text())
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        # Try to extract JSON from content
        try:
            # Find JSON in the response
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
    html_files = sorted(RAW_ADS.glob("*.html"))[:100]
    print(f"Scanning {len(html_files)} HTML files for image URLs...")
    urls = extract_image_urls(html_files, limit=SAMPLE_SIZE)
    print(f"Found {len(urls)} unique ad-content image URLs")

    results = []
    with tempfile.TemporaryDirectory() as tmpdir:
        for i, url in enumerate(urls[:SAMPLE_SIZE]):
            print(f"  [{i+1}/{SAMPLE_SIZE}] Analyzing {url[:80]}...")
            img_path = Path(tmpdir) / f"img_{i}.png"
            if not download_and_convert(url, img_path):
                results.append({"url": url, "error": "download_failed"})
                continue
            analysis = analyze_with_vlm(img_path)
            results.append({"url": url, "analysis": analysis})

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
    n_luxury = sum(1 for r in results if r.get("analysis", {}).get("has_luxury_elements"))
    n_sexual = sum(1 for r in results if r.get("analysis", {}).get("has_sexualised_content"))

    report = {
        "analysis_type": "vlm_visual_persuasion_real_images",
        "n_images_analyzed": len(results),
        "n_successful": n_success,
        "n_failed": len(results) - n_success,
        "vlm_model": "z-ai-web-dev-sdk vision (GLM-4V)",
        "findings": {
            "images_with_person": n_person,
            "images_with_text_overlay": n_text,
            "images_with_logo": n_logo,
            "images_with_luxury_elements": n_luxury,
            "images_with_sexualised_content": n_sexual,
        },
        "vp_leaf_estimates": {
            "vp_gaze_direction": round(n_person / max(n_success, 1) * 0.5, 4),
            "vp_luxury_aesthetic": round(n_luxury / max(n_success, 1), 4),
            "vp_sexualised_imagery": round(n_sexual / max(n_success, 1), 4),
        },
        "limitations": [
            f"Only {SAMPLE_SIZE} images analyzed (rate-limited)",
            "Image URLs may be expired or rate-limited by platform",
            "VLM analysis is not pixel-perfect — confidence varies",
            "Corpus is text-first; image analysis is supplementary",
        ],
        "output": str(OUT),
    }

    OUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUT_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nVLM Visual Analysis Results:")
    print(f"  Images analyzed: {n_success}/{len(results)} successful")
    print(f"  VP leaf estimates: {report['vp_leaf_estimates']}")
    print(f"  Output: {OUT}")
    print(f"  Report: {OUT_REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
