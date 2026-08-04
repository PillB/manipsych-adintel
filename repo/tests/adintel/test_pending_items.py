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
