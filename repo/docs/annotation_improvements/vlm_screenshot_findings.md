# VLM Screenshot Analysis — Live Page Navigation Report

## Method
1. Extracted ad URLs from raw HTML archive
2. Used Playwright to navigate to 10 live ad pages
3. Captured screenshots at 1280×900 viewport
4. Used z-ai VLM (GLM-4V) to analyze each screenshot

## Findings

### Doplim pages (3 navigated)
- All 3 returned Cloudflare security verification pages
- VLM correctly identified: "Cloudflare security verification page"
- No ad content visible — the site now requires JavaScript-enabled browser verification
- has_text_overlay=True (security text), has_logo=True (Cloudflare logo)
- No person, no luxury, no sexualised content, no urgency words

### Locanto pages (7 navigated)
- All 7 returned "temporary unavailability" error pages
- VLM correctly identified: "temporary error page for Locanto"
- has_text_overlay=True (error message), has_logo=True (Locanto logo)
- No person, no luxury, no sexualised content, no urgency words

## Interpretation
- The original ad URLs from the 2026-07 collection are now (2026-08-04) behind:
  - Cloudflare bot protection (Doplim)
  - Temporary server errors (Locanto)
- This is expected for classified-ad sites: ads expire, platforms add bot protection
- The VLM analysis is CORRECT — it accurately described what it saw
- Visual persuasion analysis on live pages is NOT possible because the ad content is no longer accessible

## What this means for the project
1. The corpus is a SNAPSHOT from July 2026; live pages have changed
2. Image-pixel persuasion modelling requires either:
   - Archiving images at collection time (not done for this corpus)
   - Re-collecting with a bot-protection bypass (out of scope)
3. The synthetic visual features (`generate_visual_features.py`) remain the best available approach
4. The VLM pipeline IS WORKING — it correctly analyzes whatever images it receives

## Recommendation
- For future collections: archive image pixels alongside raw HTML
- For this corpus: use synthetic visual features with documented limitations
- The VLM screenshot pipeline is ready for any future corpus that has accessible images
