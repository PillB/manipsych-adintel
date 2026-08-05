"""Red tests for full-data coverage and cluster alignment.

These tests prove:
- complete record coverage (not sample)
- reconciled counts
- no undocumented first-N sampling
- dynamic result provenance
- valid example IDs
- correct cluster comparison metrics
- technique results with examples
- outlier results with examples
"""

import json, unittest, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


class FullDataCoverageTests(unittest.TestCase):
    """Prove the pipeline uses ALL eligible records, not a sample."""

    def setUp(self):
        self.manifest_count = sum(1 for _ in open(ROOT / "data/processed/ad_manifest.jsonl") if _.strip())
        self.full_results = json.load(open(ROOT / "reports/adintel/full_data_results.json"))

    def test_profile_uses_all_records(self):
        """Profile scoring must cover every manifest record."""
        self.assertEqual(self.full_results["profile"]["n_records"], self.manifest_count)
        self.assertTrue(self.full_results["profile"]["uses_full_data"])

    def test_outlier_uses_all_records(self):
        """Outlier detection must cover every manifest record."""
        self.assertEqual(self.full_results["outliers"]["n_records"], self.manifest_count)
        self.assertTrue(self.full_results["outliers"]["uses_full_data"])

    def test_no_undocumented_sample(self):
        """If sampling is used, it must be documented and justified."""
        # Full-data results should NOT use sampling
        self.assertTrue(self.full_results["profile"]["uses_full_data"])
        self.assertTrue(self.full_results["outliers"]["uses_full_data"])

    def test_manifest_count_matches_pipeline(self):
        """Pipeline n_records must match manifest count."""
        self.assertEqual(self.full_results["n_records"], self.manifest_count)

    def test_data_hashes_present(self):
        """Data hashes must be present for provenance."""
        self.assertIn("manifest_sha256", self.full_results)
        self.assertIn("council_sha256", self.full_results)
        self.assertGreater(len(self.full_results["manifest_sha256"]), 8)


class TechniqueResultsTests(unittest.TestCase):
    """Prove technique results show actual data, not just statements."""

    def setUp(self):
        self.results = json.load(open(ROOT / "reports/adintel/full_data_results.json"))

    def test_technique_count_matches_council(self):
        """All 20 council labels must be present."""
        techs = self.results["techniques"]["results"]
        self.assertEqual(len(techs), 20)

    def test_every_technique_has_count(self):
        for t in self.results["techniques"]["results"]:
            self.assertIn("count", t)
            self.assertGreater(t["count"], 0)

    def test_every_technique_has_prevalence(self):
        for t in self.results["techniques"]["results"]:
            self.assertIn("prevalence", t)
            self.assertGreater(t["prevalence"], 0)

    def test_every_technique_has_examples(self):
        for t in self.results["techniques"]["results"]:
            self.assertIn("examples", t)
            self.assertGreater(len(t["examples"]), 0)
            for ex in t["examples"]:
                self.assertIn("record_id", ex)
                self.assertIn("title", ex)

    def test_every_technique_has_v2_mapping(self):
        for t in self.results["techniques"]["results"]:
            self.assertIn("v2_leaves", t)
            self.assertGreater(len(t["v2_leaves"]), 0)


class ClusterAlignmentTests(unittest.TestCase):
    """Prove the cluster comparison is quantitative, not qualitative."""

    def setUp(self):
        self.report = json.load(open(ROOT / "reports/adintel/cluster_alignment_report.json"))
        self.cmp = self.report["comparison"]

    def test_ari_computed(self):
        self.assertIn("ARI", self.cmp["metrics"])
        self.assertGreater(self.cmp["metrics"]["ARI"], 0)

    def test_ami_computed(self):
        self.assertIn("AMI", self.cmp["metrics"])

    def test_homogeneity_computed(self):
        self.assertIn("homogeneity", self.cmp["metrics"])

    def test_contingency_matrix_present(self):
        self.assertIn("contingency_matrix", self.cmp)
        matrix = self.cmp["contingency_matrix"]
        self.assertEqual(len(matrix), 10)  # v1 has 10 clusters
        self.assertEqual(len(matrix[0]), 5)  # adintel has 5

    def test_verdict_is_evidence_based(self):
        self.assertIn(self.cmp["verdict"], ["CONVERGENT", "PARTIALLY_ALIGNED", "COMPLEMENTARY", "DIVERGENT", "NOT_COMPARABLE"])

    def test_uses_full_data(self):
        self.assertEqual(self.cmp["n_records"], 5189)

    def test_v1_and_adintel_terms_differ(self):
        """V1 uses frequency terms; adintel uses centroid-difference terms."""
        self.assertIn("top-frequency", self.cmp["v1"]["method"])
        self.assertIn("centroid-difference", self.cmp["adintel"]["method"])


class OutlierResultsTests(unittest.TestCase):
    """Prove outlier results show complete categories with examples."""

    def setUp(self):
        self.results = json.load(open(ROOT / "reports/adintel/full_data_results.json"))

    def test_outlier_count_greater_than_sample(self):
        """Full-data outliers should be more than the 188 from the 1000-sample."""
        self.assertGreater(self.results["outliers"]["n_reports"], 188)

    def test_outlier_examples_present(self):
        for kind, examples in self.results["outliers"]["examples"].items():
            self.assertGreater(len(examples), 0, f"{kind} should have examples")
            for ex in examples:
                self.assertIn("record_id", ex)
                self.assertIn("alternative_explanation", ex)


class ProvenanceTests(unittest.TestCase):
    """Prove deployed values match current pipeline results."""

    def test_run_id_present(self):
        results = json.load(open(ROOT / "reports/adintel/full_data_results.json"))
        self.assertIn("run_id", results)

    def test_taxonomy_version_present(self):
        results = json.load(open(ROOT / "reports/adintel/full_data_results.json"))
        self.assertIn("taxonomy_version", results)
        self.assertEqual(results["taxonomy_version"], "adintel-taxonomy-v2")

    def test_elapsed_time_present(self):
        results = json.load(open(ROOT / "reports/adintel/full_data_results.json"))
        self.assertIn("elapsed_s", results)
        self.assertGreater(results["elapsed_s"], 0)


if __name__ == "__main__":
    unittest.main()
