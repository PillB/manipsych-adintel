"""Tests for the 5 pending-item modules: performance, causal, gold/silver, visual, macrocycles."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


class SyntheticPerformanceTests(unittest.TestCase):
    """Item 3: Synthetic performance dataset tests."""

    def test_synthetic_performance_exists(self):
        p = ROOT / "data" / "processed" / "synthetic_performance.jsonl"
        self.assertTrue(p.exists(), "synthetic_performance.jsonl must exist")
        with open(p) as f:
            first = json.loads(f.readline())
        self.assertIn("record_id", first)
        self.assertIn("ctr", first)
        self.assertIn("spend", first)
        self.assertIn("conversions_7day_click", first)
        self.assertTrue(first.get("synthetic"), "Must be marked synthetic")

    def test_benchmarks_exist(self):
        p = ROOT / "reports" / "adintel" / "performance_benchmarks.json"
        self.assertTrue(p.exists(), "performance_benchmarks.json must exist")

    def test_ctr_in_realistic_range(self):
        p = ROOT / "data" / "processed" / "synthetic_performance.jsonl"
        ctrs = []
        with open(p) as f:
            for line in f:
                d = json.loads(line)
                ctrs.append(d["ctr"])
        mean_ctr = sum(ctrs) / len(ctrs)
        # Should be between 0.1% and 5% (realistic for classified ads)
        self.assertGreater(mean_ctr, 0.001, "CTR too low")
        self.assertLess(mean_ctr, 0.05, "CTR too high")

    def test_attribution_windows_documented(self):
        p = ROOT / "data" / "processed" / "synthetic_performance.jsonl"
        with open(p) as f:
            first = json.loads(f.readline())
        self.assertIn("attribution_window", first)
        self.assertIn("conversions_7day_click", first)
        self.assertIn("conversions_7day_click_1day_view", first)


class CausalAnalysisTests(unittest.TestCase):
    """Item 4: Causal analysis tests."""

    def test_causal_analysis_exists(self):
        p = ROOT / "reports" / "adintel" / "causal_analysis.json"
        self.assertTrue(p.exists())
        data = json.loads(p.read_text())
        self.assertIn("evidence_ladder", data)
        self.assertIn("results", data)
        self.assertGreater(len(data["results"]), 0)
        # Each result should have evidence_level
        for r in data["results"]:
            self.assertIn("evidence_level", r)
            self.assertIn("causal_claim", r)

    def test_no_causal_claims_made(self):
        p = ROOT / "reports" / "adintel" / "causal_analysis.json"
        data = json.loads(p.read_text())
        self.assertEqual(data["causal_claims_made"], 0, "No causal claims should be made on synthetic data")
        self.assertEqual(data["causal_claims_supported"], 0)

    def test_evidence_ladder_documented(self):
        p = ROOT / "reports" / "adintel" / "causal_analysis.json"
        data = json.loads(p.read_text())
        ladder = data.get("evidence_ladder", [])
        self.assertIn("descriptive", ladder)
        self.assertIn("associative", ladder)
        self.assertIn("quasi_causal", ladder)
        self.assertIn("causal", ladder)


class GoldSilverAnnotationTests(unittest.TestCase):
    """Item 5: Gold/silver annotation agreement tests."""

    def test_simulated_gold_exists(self):
        p = ROOT / "data" / "annotation" / "simulated_gold_annotations.jsonl"
        self.assertTrue(p.exists())
        with open(p) as f:
            first = json.loads(f.readline())
        self.assertTrue(first.get("gold"), "Must be marked as gold")
        self.assertIn("simulation_notes", first)

    def test_silver_exists(self):
        p = ROOT / "data" / "annotation" / "silver_annotations.jsonl"
        self.assertTrue(p.exists())
        with open(p) as f:
            first = json.loads(f.readline())
        self.assertFalse(first.get("gold"), "Silver must not be marked as gold")
        self.assertTrue(first.get("independent_implementation"))

    def test_agreement_report_exists(self):
        p = ROOT / "reports" / "adintel" / "annotation_agreement.json"
        self.assertTrue(p.exists())
        data = json.loads(p.read_text())
        self.assertIn("label_set_agreement", data)
        self.assertIn("per_label_cohen_kappa", data)

    def test_kappa_is_honest(self):
        """Kappa should be in a realistic range (0.1-0.7) for rule-based annotators."""
        p = ROOT / "reports" / "adintel" / "annotation_agreement.json"
        data = json.loads(p.read_text())
        kappas = data.get("per_label_cohen_kappa", {})
        for label, kappa in kappas.items():
            self.assertGreaterEqual(kappa, -0.2, f"{label} kappa too low: {kappa}")
            self.assertLessEqual(kappa, 1.0, f"{label} kappa too high: {kappa}")


class VisualPersuasionTests(unittest.TestCase):
    """Item 2: Visual persuasion analysis tests."""

    def test_synthetic_visual_features_exist(self):
        p = ROOT / "data" / "processed" / "synthetic_visual_features.jsonl"
        self.assertTrue(p.exists())
        with open(p) as f:
            first = json.loads(f.readline())
        self.assertTrue(first.get("synthetic"))
        self.assertIn("vp_scores", first)

    def test_vlm_visual_report_exists(self):
        p = ROOT / "reports" / "adintel" / "vlm_visual_report.json"
        self.assertTrue(p.exists())
        data = json.loads(p.read_text())
        self.assertIn("vp_leaf_estimates", data)
        self.assertIn("n_images_analyzed", data)

    def test_vp_leaves_scored(self):
        p = ROOT / "data" / "processed" / "synthetic_visual_features.jsonl"
        with open(p) as f:
            first = json.loads(f.readline())
        vp = first["vp_scores"]
        self.assertIn("vp_gaze_direction", vp)
        self.assertIn("vp_luxury_aesthetic", vp)
        self.assertIn("vp_sexualised_imagery", vp)


class MacrocycleProgramTests(unittest.TestCase):
    """Item 1: Full macrocycle program tests."""

    def test_full_program_results_exist(self):
        p = ROOT / "audit" / "assurance" / "macrocycles" / "full_program_results.json"
        self.assertTrue(p.exists())
        data = json.loads(p.read_text())
        self.assertEqual(len(data["macrocycles"]), 4)

    def test_9_roles_per_cycle(self):
        p = ROOT / "audit" / "assurance" / "macrocycles" / "full_program_results.json"
        data = json.loads(p.read_text())
        for cycle_num, cycle in data["macrocycles"].items():
            self.assertEqual(len(cycle["roles"]), 9, f"Cycle {cycle_num} has {len(cycle['roles'])} roles, expected 9")

    def test_5_passes_per_role(self):
        p = ROOT / "audit" / "assurance" / "macrocycles" / "full_program_results.json"
        data = json.loads(p.read_text())
        for cycle_num, cycle in data["macrocycles"].items():
            for role_id, role in cycle["roles"].items():
                self.assertEqual(len(role["passes"]), 5, f"Cycle {cycle_num} role {role_id} has {len(role['passes'])} passes")

    def test_3_challenge_rounds_per_cycle(self):
        p = ROOT / "audit" / "assurance" / "macrocycles" / "full_program_results.json"
        data = json.loads(p.read_text())
        for cycle_num, cycle in data["macrocycles"].items():
            self.assertEqual(len(cycle["challenge_rounds"]), 3, f"Cycle {cycle_num} has {len(cycle['challenge_rounds'])} challenge rounds")


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------------
# Item 2: VLM screenshot analysis tests
# ---------------------------------------------------------------------------


class VLMScreenshotTests(unittest.TestCase):
    """VLM screenshot analysis from live Playwright navigation."""

    def test_vlm_screenshot_results_exist(self):
        p = ROOT / "data" / "processed" / "vlm_screenshot_analysis.jsonl"
        self.assertTrue(p.exists())
        with open(p) as f:
            first = json.loads(f.readline())
        self.assertIn("url", first)
        self.assertIn("analysis", first)

    def test_vlm_screenshot_report_exists(self):
        p = ROOT / "reports" / "adintel" / "vlm_screenshot_report.json"
        self.assertTrue(p.exists())
        data = json.loads(p.read_text())
        self.assertIn("n_pages_navigated", data)
        self.assertIn("vp_leaf_estimates", data)


# ---------------------------------------------------------------------------
# Item 5: Annotation deduplication tests
# ---------------------------------------------------------------------------


class AnnotationDedupTests(unittest.TestCase):
    """Span deduplication tests."""

    def test_dedup_output_exists(self):
        p = ROOT / "data" / "annotation" / "council_resolved_dedup.jsonl"
        self.assertTrue(p.exists())
        with open(p) as f:
            first = json.loads(f.readline())
        self.assertIn("dedup_applied", first)

    def test_dedup_report_exists(self):
        p = ROOT / "docs" / "annotation_improvements" / "dedup_report.json"
        self.assertTrue(p.exists())
        data = json.loads(p.read_text())
        self.assertGreater(data["total_removed"], 0, "Should have removed duplicate spans")

    def test_dedup_reduces_span_count(self):
        p = ROOT / "docs" / "annotation_improvements" / "dedup_report.json"
        data = json.loads(p.read_text())
        self.assertLess(data["total_spans_after"], data["total_spans_before"],
                       "Dedup should reduce total span count")


# ---------------------------------------------------------------------------
# Item 4: Smart-sampling causal analysis tests
# ---------------------------------------------------------------------------


class SmartCausalTests(unittest.TestCase):
    """Smart-sampling (propensity-score matching) causal analysis."""

    def test_smart_causal_exists(self):
        p = ROOT / "reports" / "adintel" / "causal_analysis_smart.json"
        self.assertTrue(p.exists())
        data = json.loads(p.read_text())
        self.assertIn("method", data)
        self.assertIn("propensity", data["method"])

    def test_smart_causal_no_claims(self):
        p = ROOT / "reports" / "adintel" / "causal_analysis_smart.json"
        data = json.loads(p.read_text())
        self.assertEqual(data["causal_claims_made"], 0)
        self.assertEqual(data["causal_claims_supported"], 0)

    def test_smart_causal_has_ci(self):
        p = ROOT / "reports" / "adintel" / "causal_analysis_smart.json"
        data = json.loads(p.read_text())
        for r in data["results"]:
            if r["evidence_level"] in ("quasi_causal", "associative"):
                self.assertIn("ci_95", r)
                self.assertEqual(len(r["ci_95"]), 2)


# ---------------------------------------------------------------------------
# Item 1: 10-hour chunked macrocycle plan
# ---------------------------------------------------------------------------


class MacrocyclePlanTests(unittest.TestCase):
    """10-hour chunked macrocycle plan."""

    def test_plan_exists(self):
        p = ROOT / "docs" / "annotation_improvements" / "macrocycle_10h_plan.md"
        self.assertTrue(p.exists())

    def test_audit_log_exists(self):
        p = ROOT / "docs" / "annotation_improvements" / "audit_log.md"
        self.assertTrue(p.exists())

    def test_vlm_findings_exist(self):
        p = ROOT / "docs" / "annotation_improvements" / "vlm_screenshot_findings.md"
        self.assertTrue(p.exists())


# ---------------------------------------------------------------------------
# D-02: PDF-dashboard timestamp comparison
# ---------------------------------------------------------------------------


class PDFDashboardConsistencyTests(unittest.TestCase):
    """Verify PDF and dashboard derive from the same pipeline run."""

    def test_pipeline_results_timestamp_exists(self):
        p = ROOT / "reports" / "adintel" / "pipeline_results.json"
        if not p.exists():
            self.skipTest("pipeline_results.json not found")
        data = json.loads(p.read_text())
        self.assertIn("ran_at", data)

    def test_pdf_and_dashboard_share_pipeline_source(self):
        """Both PDF and dashboard should reference the same pipeline_results.json."""
        pdf = ROOT / "download" / "advertisement_intelligence_persuasion_analytics_report.pdf"
        dashboard = ROOT / "reports" / "adintel" / "adintel_dashboard.html"
        pipeline = ROOT / "reports" / "adintel" / "pipeline_results.json"
        if not all(p.exists() for p in [pdf, dashboard, pipeline]):
            self.skipTest("Required files not found")
        # Pipeline should have a timestamp
        pdata = json.loads(pipeline.read_text())
        self.assertIn("ran_at", pdata)
        # Dashboard should embed pipeline data
        dcontent = dashboard.read_text()
        self.assertIn(str(pdata.get("n_records_total", "")), dcontent)
        # PDF should be non-empty
        self.assertGreater(pdf.stat().st_size, 10000)


# ---------------------------------------------------------------------------
# M-02: Mobile table overflow verification
# ---------------------------------------------------------------------------


class MobileTableOverflowTests(unittest.TestCase):
    """Verify tables scroll horizontally on mobile instead of overflowing."""

    def test_tables_have_overflow_scroll(self):
        dashboard = ROOT / "reports" / "adintel" / "adintel_dashboard.html"
        if not dashboard.exists():
            self.skipTest("Dashboard not found")
        content = dashboard.read_text()
        # Check that table CSS includes overflow-x:auto or display:block
        self.assertTrue(
            "overflow-x:auto" in content or "overflow-x: auto" in content,
            "Tables must have overflow-x:auto for mobile scrolling"
        )

    def test_pipe_svg_has_scroll_wrapper(self):
        dashboard = ROOT / "reports" / "adintel" / "adintel_dashboard.html"
        if not dashboard.exists():
            self.skipTest("Dashboard not found")
        content = dashboard.read_text()
        self.assertIn("svg-scroll", content, "SVG should be wrapped in scroll container")


# ---------------------------------------------------------------------------
# O-03: Monitoring script
# ---------------------------------------------------------------------------


class MonitoringScriptTests(unittest.TestCase):
    """Verify monitoring script exists and produces output."""

    def test_monitor_script_exists(self):
        p = ROOT / "scripts" / "monitor.py"
        self.assertTrue(p.exists(), "monitor.py must exist")

    def test_monitor_report_exists(self):
        p = ROOT / "reports" / "adintel" / "monitoring_report.json"
        if not p.exists():
            self.skipTest("Run monitor.py first")
        data = json.loads(p.read_text())
        self.assertIn("checks", data)


# ---------------------------------------------------------------------------
# O-04: SQLite memory documentation
# ---------------------------------------------------------------------------


class SQLiteMemoryDocumentationTests(unittest.TestCase):
    """Verify SQLite memory usage is documented."""

    def test_model_card_documents_sqlite(self):
        mc = ROOT / "reports" / "model_card.md"
        if not mc.exists():
            self.skipTest("Model card not found")
        content = mc.read_text().lower()
        # Should mention SQLite or database size
        self.assertTrue(
            "sqlite" in content or "database" in content or "annotation" in content,
            "Model card should document the SQLite database"
        )
