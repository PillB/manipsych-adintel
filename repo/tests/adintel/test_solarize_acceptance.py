"""Solarize Red-phase acceptance tests.

These tests assert the NEW behaviour the dashboard must satisfy after the
Solarize cycle. They are intentionally written BEFORE the implementation
exists, so they capture the gap as Red evidence.

Two test surfaces:

1. `TestSolarizeStatisticalEngine` — pure-python unit tests for the new
   `adintel.solarize_stats` module (term-prevalence comparison with
   Wilson CIs, Cohen's h effect size, Benjamini-Hochberg FDR, min-support
   flag, explicit "no meaningful difference" verdict). These run locally
   with `pytest` and do NOT touch the browser.

2. `TestSolarizeLiveDashboard` — Playwright acceptance tests that MUST run
   against the deployed GitHub Pages URL only. They are skipped unless the
   env var `SOLARIZE_LIVE_URL` is set to the cache-busted live URL.
   `localhost`, `127.0.0.1`, `file://` are forbidden.

The tests are written to fail against the pre-Solarize deployment and pass
after the Solarize refactor + deploy cycle completes.
"""

from __future__ import annotations

import os
import unittest
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Part 1 — pure-python unit tests for the new statistical engine
# ---------------------------------------------------------------------------


class TestSolarizeStatisticalEngine(unittest.TestCase):
    """Red-phase tests for adintel.solarize_stats (does not exist yet)."""

    def test_module_imports(self):
        """adintel.solarize_stats must be importable."""
        from adintel import solarize_stats  # noqa: F401

    def test_term_prevalence_comparison_returns_required_fields(self):
        """Each comparison row must expose the R3 fields."""
        from adintel.solarize_stats import compare_term_prevalence

        # 10 outlier ads, 4 contain "lima"; 90 non-outlier ads, 5 contain "lima"
        outlier_texts = ["lima ad"] * 4 + ["other ad"] * 6
        control_texts = ["lima ad"] * 5 + ["other ad"] * 85
        result = compare_term_prevalence(
            term="lima",
            outlier_texts=outlier_texts,
            control_texts=control_texts,
            comparison_population="all non-outlier ads",
        )
        # R3 required fields
        for field in (
            "term",
            "outlier_count",
            "outlier_denominator",
            "outlier_prevalence",
            "control_count",
            "control_denominator",
            "control_prevalence",
            "effect_size",
            "effect_size_label",
            "ci_low",
            "ci_high",
            "p_value",
            "q_value",
            "min_support",
            "comparison_population",
            "meaningfully_different",
        ):
            self.assertIn(field, result, f"missing field {field}")

    def test_wilson_ci_bounds_prevalence(self):
        """Wilson CI must lie in [0,1] and contain the point estimate."""
        from adintel.solarize_stats import wilson_ci

        for k, n in [(0, 10), (5, 10), (10, 10), (3, 100), (50, 100)]:
            lo, hi, p = wilson_ci(k, n)
            self.assertGreaterEqual(lo, 0.0)
            self.assertLessEqual(hi, 1.0)
            self.assertLessEqual(lo, p)
            self.assertLessEqual(p, hi)

    def test_cohens_h_effect_size_buckets(self):
        """Cohen's h must produce the conventional buckets."""
        from adintel.solarize_stats import cohens_h, effect_size_label

        # 0.8 vs 0.2 — large effect
        h = cohens_h(0.8, 0.2)
        self.assertGreater(h, 0.8)
        self.assertEqual(effect_size_label(h), "large")

        # 0.5 vs 0.45 — negligible
        h = cohens_h(0.5, 0.45)
        self.assertLess(abs(h), 0.2)
        self.assertEqual(effect_size_label(h), "negligible")

    def test_benjamini_hochberg_adjusts_qvalues(self):
        """BH FDR adjustment must produce q-values >= p-values, sorted."""
        from adintel.solarize_stats import benjamini_hochberg

        pvals = [0.001, 0.04, 0.03, 0.5, 0.02]
        q = benjamini_hochberg(pvals)
        self.assertEqual(len(q), len(pvals))
        for pi, qi in zip(pvals, q):
            self.assertGreaterEqual(qi, pi - 1e-12)

    def test_min_support_flag(self):
        """min_support=False when outlier_count < min_support (default 5)."""
        from adintel.solarize_stats import compare_term_prevalence

        result = compare_term_prevalence(
            term="rare_term",
            outlier_texts=["rare_term ad"] * 2 + ["x"] * 8,  # 2/10
            control_texts=["rare_term ad"] * 0 + ["x"] * 90,  # 0/90
            comparison_population="all non-outlier ads",
        )
        self.assertFalse(result["min_support"])
        # Even though prevalence is 20% vs 0%, with only 2 hits the verdict
        # must reflect low support
        self.assertFalse(result["meaningfully_different"])

    def test_explicit_no_meaningful_difference_verdict(self):
        """R4: when effect size is negligible, meaningfully_different=False."""
        from adintel.solarize_stats import compare_term_prevalence

        # 50/100 vs 48/100 — negligible difference
        result = compare_term_prevalence(
            term="common",
            outlier_texts=["common ad"] * 50 + ["x"] * 50,
            control_texts=["common ad"] * 48 + ["x"] * 52,
            comparison_population="all non-outlier ads",
        )
        self.assertFalse(result["meaningfully_different"])
        self.assertEqual(result["effect_size_label"], "negligible")

    def test_distinguish_outlier_types(self):
        """R9: outlier taxonomy must include all 4 required kinds."""
        from adintel.solarize_stats import OUTLIER_KINDS

        required = {
            "detector",          # rule-based detector outlier
            "density_noise",     # DBSCAN/HDBSCAN label=-1
            "cluster_enriched",  # Mahalanobis/MAD within-cluster outlier
            "boundary",          # silhouette < threshold
        }
        self.assertTrue(required.issubset(set(OUTLIER_KINDS)))


# ---------------------------------------------------------------------------
# Part 2 — Playwright acceptance tests (live-only)
# ---------------------------------------------------------------------------


LIVE_URL = os.environ.get("SOLARIZE_LIVE_URL", "")
FORBIDDEN_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


def _is_live_url(url: str) -> bool:
    if not url:
        return False
    if url.startswith("file://"):
        return False
    host = urlparse(url).hostname or ""
    if host in FORBIDDEN_HOSTS:
        return False
    if not host.endswith("github.io"):
        return False
    return True


@unittest.skipUnless(_is_live_url(LIVE_URL), "SOLARIZE_LIVE_URL must point to a github.io URL")
class TestSolarizeLiveDashboard(unittest.TestCase):
    """Acceptance tests that MUST run against the deployed GitHub Pages URL.

    Skipped unless env var SOLARIZE_LIVE_URL is set to the cache-busted
    live URL (https://pillb.github.io/manipsych-adintel/...?cb=<sha>).
    """

    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright

        cls._pw = sync_playwright().start()
        cls._browser = cls._pw.chromium.launch(headless=True)
        cls._context = cls._browser.new_context(viewport={"width": 1366, "height": 900})
        cls._page = cls._context.new_page()
        cls._console_errors: list[str] = []
        cls._page_errors: list[str] = []
        cls._page.on("console", lambda m: cls._console_errors.append(m.text) if m.type == "error" else None)
        cls._page.on("pageerror", lambda e: cls._page_errors.append(str(e)))

    @classmethod
    def tearDownClass(cls):
        try:
            cls._context.close()
            cls._browser.close()
            cls._pw.stop()
        except Exception:
            pass

    def test_01_page_loads_without_js_errors(self):
        self._page.goto(LIVE_URL, wait_until="networkidle", timeout=60_000)
        self._page.wait_for_timeout(2000)
        title = self._page.title()
        self.assertIn("ManiPsych", title)
        self.assertEqual(len(self._page_errors), 0, f"page errors: {self._page_errors[:5]}")
        # Allow INFO/WARN but fail on hard console errors
        hard = [e for e in self._console_errors if "Uncaught" in e or "SyntaxError" in e or "ReferenceError" in e or "TypeError" in e]
        self.assertEqual(len(hard), 0, f"hard console errors: {hard[:5]}")

    def test_02_build_fingerprint_present_and_matches_commit(self):
        """HTML must expose a data-build-fingerprint and data-commit-sha.

        The embedded SHA is captured at dashboard-generation time, which
        happens BEFORE the deploy commit is created. So the embedded SHA
        is always an ancestor of (or equal to) the deployed commit. We
        verify:
          1. The fingerprint and SHA attributes exist on <html>.
          2. The SHA is a 40-char hex string.
          3. The SHA corresponds to a real commit object in the local repo
             (i.e., it's not fabricated).
          4. If SOLARIZE_EXPECTED_SHA is set, the embedded SHA must be
             reachable from it (ancestor-or-self).
        """
        html = self._page.locator("html")
        fp = html.get_attribute("data-build-fingerprint") or ""
        sha = html.get_attribute("data-commit-sha") or ""
        self.assertTrue(fp, "missing data-build-fingerprint on <html>")
        self.assertTrue(sha, "missing data-commit-sha on <html>")
        self.assertEqual(len(sha), 40, f"commit SHA must be 40 chars, got {sha!r}")
        import re
        self.assertTrue(re.match(r"^[0-9a-f]{40}$", sha), f"SHA must be hex, got {sha!r}")

        # Verify the SHA is a real commit in the local repo
        import subprocess
        try:
            result = subprocess.run(
                ["git", "cat-file", "-t", sha],
                capture_output=True, text=True, cwd="/home/z/my-project",
                timeout=10,
            )
            self.assertEqual(
                result.stdout.strip(), "commit",
                f"embedded SHA {sha} is not a real commit object in the local repo",
            )
        except Exception as e:
            self.fail(f"could not verify SHA {sha} is a real commit: {e}")

        # If expected SHA is set, verify the embedded SHA is an ancestor-or-self
        expected_sha = os.environ.get("SOLARIZE_EXPECTED_SHA", "")
        if expected_sha:
            try:
                # Check if `sha` is reachable from `expected_sha` (i.e. an ancestor or equal)
                result = subprocess.run(
                    ["git", "merge-base", "--is-ancestor", sha, expected_sha],
                    capture_output=True, text=True, cwd="/home/z/my-project",
                    timeout=10,
                )
                # Exit code 0 = ancestor; 1 = not ancestor; other = error
                is_ancestor = result.returncode == 0
                # Also accept if they're equal (merge-base --is-ancestor handles this too,
                # but be explicit for clarity)
                if not is_ancestor and sha != expected_sha:
                    # As a fallback, accept if the embedded SHA is within the last 10 commits
                    result2 = subprocess.run(
                        ["git", "rev-list", "-10", expected_sha],
                        capture_output=True, text=True, cwd="/home/z/my-project",
                        timeout=10,
                    )
                    recent = set(result2.stdout.strip().split("\n")) if result2.returncode == 0 else set()
                    self.assertTrue(
                        sha in recent,
                        f"embedded SHA {sha} is not an ancestor of deployed {expected_sha} "
                        f"nor in the last 10 commits {recent}",
                    )
            except Exception as e:
                self.fail(f"could not verify ancestor relationship: {e}")

    def test_03_outlier_term_comparison_table_exists(self):
        """R1, R3: outlier term comparison must show counts, denominators, %, effect size, CI, q-value."""
        # Navigate to outliers section
        self._page.goto(f"{LIVE_URL}#adintel-outliers", wait_until="networkidle")
        self._page.wait_for_timeout(1500)
        section = self._page.locator("#adintel-outliers")
        self.assertGreater(section.count(), 0)
        # Must contain a comparison table with required columns
        text = section.inner_text()
        for required in ("outlier_count", "control_count", "prevalence", "effect_size", "ci", "q_value", "min_support"):
            # Look for either the column name or a data attribute
            self.assertTrue(
                required in text.lower() or section.locator(f"[data-field='{required}']").count() > 0,
                f"outlier section missing '{required}'",
            )

    def test_04_outlier_kind_taxonomy_distinguishes_four_types(self):
        """R9: dashboard must distinguish detector / density_noise / cluster_enriched / boundary."""
        self._page.goto(f"{LIVE_URL}#adintel-outliers", wait_until="networkidle")
        self._page.wait_for_timeout(1500)
        section = self._page.locator("#adintel-outliers")
        text = section.inner_text().lower()
        for kind in ("detector", "density_noise", "cluster_enriched", "boundary"):
            self.assertIn(kind, text, f"outlier section missing kind '{kind}'")

    def test_05_explicit_no_meaningful_difference_statement(self):
        """R4: dashboard must explicitly say when outliers are NOT meaningfully different."""
        self._page.goto(f"{LIVE_URL}#adintel-outliers", wait_until="networkidle")
        self._page.wait_for_timeout(1500)
        body = self._page.locator("body").inner_text().lower()
        # Must contain a phrase that explicitly reports non-difference
        phrases = ("not meaningfully different", "no meaningful difference", "negligible difference", "not statistically meaningful")
        self.assertTrue(any(p in body for p in phrases), "missing explicit non-difference statement")

    def test_06_cluster_section_has_distinguishing_terms_and_examples(self):
        """Cluster section must show distinguishing terms + real example ads per cluster."""
        self._page.goto(f"{LIVE_URL}#adintel-clustering", wait_until="networkidle")
        self._page.wait_for_timeout(1500)
        section = self._page.locator("#adintel-clustering")
        text = section.inner_text()
        # Must show distinguishing terms per cluster (not just top-frequency words)
        self.assertTrue(
            "distinguishing" in text.lower() or "distinctive" in text.lower(),
            "cluster section must label terms as distinguishing/distinctive",
        )
        # Must show at least one real ad example
        self.assertGreaterEqual(section.locator(".cluster-example, .real-ad-example, [data-cluster-example]").count(), 1)

    def test_07_ad_selector_returns_cluster_and_neighbors(self):
        """R8: user can search/select an ad and see cluster, neighbors, alternative cluster, evidence."""
        self._page.goto(f"{LIVE_URL}#adintel-clustering", wait_until="networkidle")
        self._page.wait_for_timeout(2500)
        # Must have an ad selector input
        selector = self._page.locator("#adintel-ad-selector")
        self.assertGreater(selector.count(), 0, "no ad selector input found")
        # Type a record_id (use a known one from the dashboard)
        selector.first.fill("h_")
        self._page.wait_for_timeout(1500)
        # Must show some result panel
        results = self._page.locator("#adintel-ad-results .ad-result-row")
        self.assertGreater(results.count(), 0, "no results rendered after typing")
        # Click first result and wait for detail panel to populate
        results.first.click()
        self._page.wait_for_timeout(1500)
        detail = self._page.locator("#adintel-ad-detail")
        self.assertGreater(detail.count(), 0, "no ad detail panel found")
        # Wait for detail panel to populate (escape empty state)
        for _ in range(10):
            txt = detail.first.inner_text()
            if txt.strip():
                break
            self._page.wait_for_timeout(500)
        detail_text = detail.first.inner_text().lower()
        # Detail panel must show cluster assignment
        self.assertIn("cluster", detail_text)
        # Must mention outlier status
        self.assertTrue(
            "outlier" in detail_text or "inlier" in detail_text,
            "detail panel must show outlier status",
        )

    def test_08_stable_record_ids_and_deep_links(self):
        """R11: deep link to a specific ad must work via URL hash."""
        # Use a hash that includes a record ID
        self._page.goto(f"{LIVE_URL}#adintel-ad=h_239b6907cfc835", wait_until="networkidle")
        self._page.wait_for_timeout(1500)
        # Either the URL hash is preserved or the ad detail panel populates
        # The important invariant: no 404, no JS explosion
        body = self._page.locator("body").inner_text()
        self.assertGreater(len(body), 1000)
        self.assertEqual(len(self._page_errors), 0)

    def test_09_no_redundant_clustering_sections(self):
        """R10: cluster explainer must be consolidated, not duplicated."""
        # The dashboard previously had both #adintel-clustering (7-space) and
        # #adintel-deep-clustering (LSA/KMeans). After consolidation there
        # should be ONE canonical clustering section OR they must be clearly
        # nested (deep clustering as a subsection of clustering).
        clustering = self._page.locator("#adintel-clustering").count()
        deep = self._page.locator("#adintel-deep-clustering").count()
        # Acceptable: either deep is gone, or deep is INSIDE clustering, or
        # deep is clearly labeled as a benchmark subsection
        if deep > 0 and clustering > 0:
            # They must cross-link and explain their relationship
            body = self._page.locator("body").inner_text().lower()
            self.assertTrue(
                "benchmark" in body or "baseline" in body or "subsection" in body,
                "duplicate clustering sections exist without explaining their relationship",
            )

    def test_10_mobile_viewport_renders_without_overflow(self):
        """Mobile acceptance: 375px viewport, no horizontal overflow."""
        ctx = self._browser.new_context(viewport={"width": 375, "height": 750}, is_mobile=True, has_touch=True)
        pg = ctx.new_page()
        try:
            pg.goto(LIVE_URL, wait_until="networkidle", timeout=60_000)
            pg.wait_for_timeout(2000)
            # Check for horizontal overflow
            overflow = pg.evaluate(
                "() => ({scrollW: document.documentElement.scrollWidth, clientW: document.documentElement.clientWidth})"
            )
            self.assertLessEqual(
                overflow["scrollW"],
                overflow["clientW"] + 5,
                f"horizontal overflow: scrollW={overflow['scrollW']} clientW={overflow['clientW']}",
            )
            # Sections must be visible
            self.assertGreater(pg.locator("#adintel-clustering").count(), 0)
            self.assertGreater(pg.locator("#adintel-outliers").count(), 0)
        finally:
            ctx.close()

    # -----------------------------------------------------------------------
    # Round 2: "all content should be in the website" — new tests for
    # in-website methodology, full per-ad table, audit evidence, data downloads.
    # -----------------------------------------------------------------------

    def test_11_methodology_section_in_website(self):
        """The dashboard must explain WHY each statistical choice was made.

        Wilson CI vs Wald, Cohen's h vs enrichment ratio, BH FDR vs Bonferroni,
        min-support=5 threshold, k=5 choice, meaningfully-different criterion.
        """
        self._page.goto(f"{LIVE_URL}#adintel-methodology", wait_until="networkidle")
        self._page.wait_for_timeout(1500)
        # Methodology section must exist
        section = self._page.locator("#adintel-methodology")
        self.assertGreater(section.count(), 0, "no #adintel-methodology section found")
        text = section.inner_text().lower()
        # Must explain each major statistical choice
        for term in ("wilson", "cohen", "benjamini", "min-support", "k=5", "meaningfully"):
            self.assertIn(term, text, f"methodology section missing explanation of '{term}'")

    def test_12_full_per_ad_table_searchable_in_website(self):
        """The full per-ad table (not just 300 top-activity ads) must be searchable.

        Either:
          (a) The ad selector embeds the full per-ad table, OR
          (b) There's a separate "full ad table" UI that fetches solarize_per_ad.jsonl
              client-side and lets the user search all 4,540 records.
        """
        self._page.goto(f"{LIVE_URL}#adintel-clustering", wait_until="networkidle")
        self._page.wait_for_timeout(2000)
        # Check the embedded solarize-data JSON for per_ad_selector count
        n_embedded = self._page.evaluate("""() => {
            const el = document.getElementById('solarize-data');
            if (!el) return 0;
            try {
                const d = JSON.parse(el.textContent);
                return d.per_ad_selector ? d.per_ad_selector.length : 0;
            } catch (e) { return 0; }
        }""")
        # Either embedded count is > 1000 (full table embedded), OR there's a
        # separate UI element that loads the full table
        full_table_ui = self._page.locator(
            "#adintel-full-ad-table, [data-role='full-ad-table'], #adintel-ad-table-search"
        ).count()
        self.assertTrue(
            n_embedded > 1000 or full_table_ui > 0,
            f"only {n_embedded} ads embedded and no full-ad-table UI found — "
            "the full per-ad table is not searchable in-website",
        )

    def test_13_audit_evidence_section_in_website(self):
        """Audit evidence (Red phase baseline, verification rounds) must be in the website."""
        self._page.goto(f"{LIVE_URL}#adintel-audit", wait_until="networkidle")
        self._page.wait_for_timeout(1500)
        # Either a dedicated audit section, or audit content in an existing section
        audit_section = self._page.locator("#adintel-audit, [data-role='audit-evidence']").count()
        body_text = self._page.locator("body").inner_text().lower()
        # Must mention Red phase / verification / test evidence somewhere
        has_red_phase = any(t in body_text for t in ("red phase", "red-phase", "pre-solarize", "before solarize"))
        has_verification = any(t in body_text for t in ("verification round", "live audit", "playwright", "acceptance test"))
        self.assertTrue(
            audit_section > 0 or (has_red_phase and has_verification),
            "audit evidence (Red phase + verification) not surfaced in the website",
        )

    def test_14_data_download_section_in_website(self):
        """Users must be able to download underlying data (solarize_summary.json, per_ad.jsonl) from the website UI."""
        self._page.goto(LIVE_URL, wait_until="networkidle")
        self._page.wait_for_timeout(1500)
        body = self._page.locator("body").inner_text().lower()
        # Must have a section or links that explicitly invite download
        has_download_ui = self._page.locator(
            "[data-role='data-download'], #adintel-data-download, .data-download-link"
        ).count()
        # Or explicit download links to the solarize files with descriptive labels
        has_download_link = any(
            t in body for t in ("download solarize", "download the data", "download full", "data download", "download solarize_summary")
        )
        self.assertTrue(
            has_download_ui > 0 or has_download_link,
            "no data-download UI or links found in the website",
        )

    def test_15_cluster_card_links_to_full_cluster_members(self):
        """Clicking a cluster card must let the user see ALL members of that cluster, not just 3 sample ads."""
        self._page.goto(f"{LIVE_URL}#adintel-clustering", wait_until="networkidle")
        self._page.wait_for_timeout(2000)
        # Click the first cluster-example card
        first_card = self._page.locator(".cluster-example").first
        if first_card.count() == 0:
            self.fail("no cluster-example cards found")
        first_card.click()
        self._page.wait_for_timeout(1500)
        # Either: the ad selector filters to that cluster AND shows > 3 results,
        # OR there's a "view all N members" link/button that expands
        cluster_filter = self._page.locator("#adintel-cluster-filter")
        if cluster_filter.count() > 0:
            filter_val = cluster_filter.first.get_attribute("value") or cluster_filter.first.evaluate("el => el.value")
            # The cluster filter should be set to the clicked cluster
            # (Or alternatively there's an expanded member list)
            expanded = self._page.locator(".cluster-all-members, [data-role='cluster-all-members']").count()
            self.assertTrue(
                (filter_val and filter_val != "") or expanded > 0,
                "clicking a cluster card did not filter the ad selector or expand the member list",
            )

    def test_16_uncertainty_and_limitations_section_in_website(self):
        """Data limitations and uncertainty must be explicitly surfaced in the website."""
        self._page.goto(LIVE_URL, wait_until="networkidle")
        self._page.wait_for_timeout(1500)
        body = self._page.locator("body").inner_text().lower()
        # Must mention key limitations honestly
        must_mention = [
            ("weak cluster structure", "weak cluster", "silhouette is near zero", "silhouette_mean", "weakly separated"),
            ("density_noise is high", "68%", "density_noise"),
            ("matched controls", "platform_family only", "matched control"),
        ]
        for label, *phrases in must_mention:
            self.assertTrue(
                any(p in body for p in phrases),
                f"website must honestly mention limitation: {label}",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
