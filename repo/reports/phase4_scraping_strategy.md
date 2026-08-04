# Phase 4 Scraping Strategy

## Boundary

The collection strategy is persistent but limited to public pages. It does not solve CAPTCHAs, bypass login gates, scrape private groups, or evade access controls. When a public URL returns an interstitial, the collector archives the page and records the stop condition.

## Current Robust Fetch Stack

- `requests` for simple public HTML endpoints.
- Playwright for JavaScript-rendered public pages.
- Optional Selenium mode for environments with Selenium and a compatible browser driver installed.
- BeautifulSoup-based link extraction with fallback to Python `html.parser`.

## Source Discovery Strategy

1. Generate city/tag URL candidates using `tools/expand_sources.py`.
2. Run public search discovery using `tools/discover_sources.py`.
3. Ingest copied/exported search-result URLs using `tools/ingest_candidate_urls.py`.
4. Fetch candidates with `tools/scrape_ads.py`, using Playwright for JS-rendered pages.
5. Archive raw HTML under `data/raw/ads/` and write only redacted processed JSONL records.
6. Stop and log when a source returns CAPTCHA/interstitial, login gates, 403/520, DNS failure, or duplicate-only results.

## Locanto Findings

Sub-agent discovery found that Locanto uses slash pagination:

- first page: `https://www.locanto.com.pe/{city}/tag/{tag}/`
- page 2: `https://www.locanto.com.pe/{city}/tag/{tag}/1/`
- page 3: `https://www.locanto.com.pe/{city}/tag/{tag}/2/`

Concrete public leads reported by the source-discovery agent include:

- `https://www.locanto.com.pe/lima/tag/ayuda-economica/` with `999+` reported results.
- `https://www.locanto.com.pe/arequipa/tag/ayuda-economica/` with `999+` reported results.
- `https://www.locanto.com.pe/cusco/tag/ayuda-economica/` with `286` reported results.
- `https://www.locanto.com.pe/lima/ID_8216548048/INVIERTE-Y-RECUPERA-EN-20-DIAS.html` as a concrete detail URL.

In this runtime, those Locanto URLs return a CAPTCHA/interstitial, so the collector stops without bypass.

## Documentation Basis

- Selenium WebDriver is intended to drive browsers natively and supports browser sessions, waits, elements, navigation, and supported-browser configuration: https://www.selenium.dev/documentation/webdriver/
- Playwright `Page` supports browser tab automation, `goto`, page content retrieval, events, and locator handling: https://playwright.dev/python/docs/api/class-page
- BeautifulSoup supports HTML parsing and link/content extraction: https://www.crummy.com/software/BeautifulSoup/bs4/doc/

## Next Work

- Install Selenium if a separate browser-driver path is needed: `python3 -m pip install selenium`.
- Run `tools/scrape_ads.py` with `mode: selenium` sources in an environment where a supported driver is configured.
- Continue expanding public search candidates and direct detail URLs.
- Prioritize sources that return public HTML without interstitials so the processed dataset can begin accumulating real records.
