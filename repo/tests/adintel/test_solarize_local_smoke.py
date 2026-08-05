"""Local smoke test: render the generated dashboard via file:// and verify
all Solarize features are present in the DOM.

This is NOT acceptance evidence — acceptance requires the live GitHub Pages
URL. This is a fast smoke test that catches generator bugs before deploy.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

REPO = Path("/home/z/my-project/repo")
DASHBOARD_PATH = REPO / "reports" / "adintel" / "adintel_dashboard.html"

if not DASHBOARD_PATH.exists():
    print(f"ERROR: {DASHBOARD_PATH} not found")
    sys.exit(1)


class TestDashboardLocalSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls._pw = sync_playwright().start()
        cls._browser = cls._pw.chromium.launch(headless=True)
        cls._context = cls._browser.new_context(viewport={"width": 1366, "height": 900})
        cls._page = cls._context.new_page()
        cls._console_errors = []
        cls._page_errors = []
        cls._page.on("console", lambda m: cls._console_errors.append(m.text) if m.type == "error" else None)
        cls._page.on("pageerror", lambda e: cls._page_errors.append(str(e)))

    @classmethod
    def tearDownClass(cls):
        cls._context.close()
        cls._browser.close()
        cls._pw.stop()

    def test_01_page_loads_without_errors(self):
        url = f"file://{DASHBOARD_PATH}"
        self._page.goto(url, wait_until="networkidle", timeout=60_000)
        self._page.wait_for_timeout(2000)
        title = self._page.title()
        self.assertIn("ManiPsych", title)
        self.assertEqual(len(self._page_errors), 0, f"page errors: {self._page_errors[:5]}")
        hard = [e for e in self._console_errors if "Uncaught" in e or "SyntaxError" in e or "ReferenceError" in e]
        self.assertEqual(len(hard), 0, f"hard console errors: {hard[:5]}")

    def test_02_build_fingerprint_present(self):
        fp = self._page.locator("html").get_attribute("data-build-fingerprint") or ""
        sha = self._page.locator("html").get_attribute("data-commit-sha") or ""
        self.assertTrue(fp, "missing data-build-fingerprint on <html>")
        self.assertTrue(sha, "missing data-commit-sha on <html>")
        self.assertEqual(len(sha), 40, f"commit SHA must be 40 chars, got {sha!r}")

    def test_03_outlier_term_comparison_table_exists(self):
        self._page.goto(f"file://{DASHBOARD_PATH}#adintel-outliers", wait_until="networkidle")
        self._page.wait_for_timeout(1500)
        section = self._page.locator("#adintel-outliers")
        # Look for the term-comparison table with data-field="term_comparison_row"
        rows = section.locator("[data-field='term_comparison_row']")
        self.assertGreater(rows.count(), 0, "no term-comparison rows found")
        # Look for required column headers (data-field='term_comparison' blocks)
        blocks = section.locator("[data-field='term_comparison']")
        self.assertEqual(blocks.count(), 3, f"expected 3 comparison populations, got {blocks.count()}")
        # Look for outlier_count text
        body_text = section.inner_text().lower()
        self.assertIn("outlier_count", body_text)
        self.assertIn("effect_size", body_text)
        self.assertIn("q_value", body_text)
        self.assertIn("min_support", body_text)

    def test_04_outlier_kind_taxonomy_distinguishes_four_types(self):
        self._page.goto(f"file://{DASHBOARD_PATH}#adintel-outliers", wait_until="networkidle")
        self._page.wait_for_timeout(1500)
        section = self._page.locator("#adintel-outliers")
        text = section.inner_text().lower()
        for kind in ("detector", "density_noise", "cluster_enriched", "boundary"):
            self.assertIn(kind, text, f"outlier section missing kind '{kind}'")

    def test_05_explicit_no_meaningful_difference_statement(self):
        self._page.goto(f"file://{DASHBOARD_PATH}#adintel-outliers", wait_until="networkidle")
        self._page.wait_for_timeout(1500)
        body = self._page.locator("body").inner_text().lower()
        phrases = ("not meaningfully different", "no meaningful difference", "not_meaningfully_different")
        self.assertTrue(any(p in body for p in phrases), "missing explicit non-difference statement")

    def test_06_cluster_section_has_distinguishing_terms_and_examples(self):
        self._page.goto(f"file://{DASHBOARD_PATH}#adintel-clustering", wait_until="networkidle")
        self._page.wait_for_timeout(1500)
        section = self._page.locator("#adintel-clustering")
        text = section.inner_text().lower()
        self.assertIn("distinguishing", text)
        # Real examples via data-cluster-example
        examples = section.locator("[data-cluster-example]")
        self.assertGreaterEqual(examples.count(), 1, "no cluster-example cards found")

    def test_07_ad_selector_returns_cluster_and_neighbors(self):
        self._page.goto(f"file://{DASHBOARD_PATH}#adintel-clustering", wait_until="networkidle")
        self._page.wait_for_timeout(2000)
        selector = self._page.locator("#adintel-ad-selector")
        self.assertEqual(selector.count(), 1, "no ad selector input found")
        # Type a fragment and verify results render
        selector.first.fill("h_")
        self._page.wait_for_timeout(500)
        results = self._page.locator("#adintel-ad-results .ad-result-row")
        self.assertGreater(results.count(), 0, "no results rendered after typing")
        # Click the first result
        results.first.click()
        self._page.wait_for_timeout(500)
        detail = self._page.locator("#adintel-ad-detail")
        detail_text = detail.first.inner_text().lower()
        self.assertIn("cluster_id", detail_text)
        self.assertTrue("outlier" in detail_text or "inlier" in detail_text)
        # Should mention alternative cluster, silhouette, neighbors
        self.assertIn("alternative_cluster", detail_text)
        self.assertIn("silhouette", detail_text)
        self.assertIn("neighbor", detail_text)

    def test_08_benchmark_table_exists(self):
        self._page.goto(f"file://{DASHBOARD_PATH}#adintel-clustering", wait_until="networkidle")
        self._page.wait_for_timeout(1500)
        section = self._page.locator("#adintel-clustering")
        # Benchmark rows
        rows = section.locator("[data-field='benchmark_row']")
        self.assertEqual(rows.count(), 3, f"expected 3 benchmark rows, got {rows.count()}")
        # Deep-clustering verdict banner
        text = section.inner_text().lower()
        self.assertIn("deep-clustering verdict", text)
        self.assertIn("not justified", text)

    def test_09_no_duplicate_clustering_section(self):
        # The duplicate #adintel-deep-clustering section should be gone or clearly labeled
        deep = self._page.locator("#adintel-deep-clustering").count()
        # After consolidation, the section should not exist as a separate top-level section
        self.assertEqual(deep, 0, "duplicate #adintel-deep-clustering section still exists")

    def test_10_mobile_no_overflow(self):
        ctx = self._browser.new_context(viewport={"width": 375, "height": 750}, is_mobile=True, has_touch=True)
        pg = ctx.new_page()
        try:
            pg.goto(f"file://{DASHBOARD_PATH}", wait_until="networkidle", timeout=60_000)
            pg.wait_for_timeout(2000)
            overflow = pg.evaluate(
                "() => ({scrollW: document.documentElement.scrollWidth, clientW: document.documentElement.clientWidth})"
            )
            self.assertLessEqual(
                overflow["scrollW"],
                overflow["clientW"] + 5,
                f"horizontal overflow: scrollW={overflow['scrollW']} clientW={overflow['clientW']}",
            )
        finally:
            ctx.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
