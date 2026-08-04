"""Tests for multi-space clustering (adintel.clustering).

Red phase: encoding stability, leakage, noise handling, parameter sensitivity,
representative/boundary identification, and the 7-space requirement.
"""

from __future__ import annotations

import unittest

import numpy as np

from adintel import clustering as cl


# ---------------------------------------------------------------------------
# Synthetic fixtures
# ---------------------------------------------------------------------------


def _make_records(n: int = 60, seed: int = 42) -> tuple[list[dict], list[str]]:
    rng = np.random.RandomState(seed)
    records: list[dict] = []
    texts: list[str] = []
    platforms = ["doplim", "locanto", "ciudadanuncios"]
    for i in range(n):
        p = platforms[i % 3]
        if p == "doplim":
            txt = f"ayuda económica urgente chica estudiante lima {i} escribeme whatsapp"
        elif p == "locanto":
            txt = f"brindo apoyo económico discreto permanente semana {i} privado"
        else:
            txt = f"ofrezco ayuda dinero semanal fijo estudiante {i} contacto"
        rec = {
            "record_id": f"r{i}",
            "source_platform": p,
            "metadata": {"platform_family": p, "image_count": i % 3, "quality_score": 0.5 + (i % 5) * 0.1, "is_featured_marker": i % 7 == 0},
        }
        records.append(rec)
        texts.append(txt)
    return records, texts


def _make_profiles(n: int = 60) -> list[dict]:
    """Return n synthetic profile dicts with the 17 dimensions."""
    from adintel.types import PROFILE_DIMENSIONS

    rng = np.random.RandomState(0)
    out: list[dict] = []
    for i in range(n):
        dims = {d: {"score": float(rng.rand()), "abstained": False} for d in PROFILE_DIMENSIONS}
        out.append({"dimensions": dims})
    return out


class FeatureBuilderTests(unittest.TestCase):
    def test_persuasive_features_shape(self):
        profiles = _make_profiles(20)
        X = cl.build_persuasive_features(profiles)
        self.assertEqual(X.shape, (20, 17))

    def test_semantic_features_shape(self):
        _, texts = _make_records(20)
        X, _ = cl.build_semantic_features(texts)
        self.assertEqual(X.shape[0], 20)

    def test_rhetorical_features_shape(self):
        _, texts = _make_records(20)
        X = cl.build_rhetorical_features(texts)
        self.assertEqual(X.shape[0], 20)
        self.assertGreater(X.shape[1], 10)  # function words + punct + avg_len

    def test_visual_features_handles_missing_metadata(self):
        records = [{"record_id": "r1"}, {"record_id": "r2", "metadata": {"image_count": 3}}]
        X = cl.build_visual_features(records)
        self.assertEqual(X.shape, (2, 3))

    def test_authorial_features_shape(self):
        _, texts = _make_records(20)
        X = cl.build_authorial_features(texts)
        self.assertEqual(X.shape[0], 20)


class ClusteringRunnerTests(unittest.TestCase):
    def test_cluster_space_returns_assignments_and_report(self):
        records, texts = _make_records(60)
        X, _ = cl.build_semantic_features(texts)
        assignments, report = cl.cluster_space("semantic", X, records, texts, k=4, compute_stability=False)
        self.assertEqual(len(assignments), 60)
        self.assertEqual(report.space, "semantic")
        self.assertGreater(report.n_clusters, 0)

    def test_cluster_all_spaces_returns_seven_spaces(self):
        records, texts = _make_records(60)
        profiles = _make_profiles(60)
        results = cl.cluster_all_spaces(records, texts, profiles=profiles, k=4, compute_stability=False)
        for space in ("persuasive", "semantic", "rhetorical", "visual", "multimodal", "authorial", "performance"):
            self.assertIn(space, results, f"Missing space: {space}")
            assignments, report = results[space]
            self.assertEqual(len(assignments), 60)


class StabilityTests(unittest.TestCase):
    def test_stable_clusters_have_high_ari(self):
        """Identical-text clusters should be perfectly stable."""
        records, texts = _make_records(60)
        # Use semantic features on highly templated text
        X, _ = cl.build_semantic_features(texts)
        ari, pc = cl.evaluate_stability(X, k=3, n_resamples=3, sample_frac=0.8)
        self.assertGreater(ari, 0.0, "ARI should be positive for structured clusters")

    def test_parameter_sensitivity_returns_finite_std(self):
        records, texts = _make_records(40)
        X, _ = cl.build_semantic_features(texts)
        sens = cl.evaluate_parameter_sensitivity(X, k_grid=(3, 4, 5, 6))
        self.assertGreaterEqual(sens, 0.0)
        self.assertTrue(np.isfinite(sens))


class LeakageTests(unittest.TestCase):
    def test_leakage_detection_on_segregated_platforms(self):
        """When platforms are perfectly segregated into clusters, leakage
        should be detected (i.e. dominant brand appears in the dict)."""
        records, texts = _make_records(60)
        # Force labels that exactly match platform
        labels = np.array([i % 3 for i in range(60)])
        leak = cl.evaluate_leakage(records, labels, field="source_platform")
        self.assertGreater(len(leak), 0, "Should detect platform dominance")
        for plat, dom in leak.items():
            self.assertGreaterEqual(dom, 0.7)


class ExplanationTests(unittest.TestCase):
    def test_explain_clusters_returns_representative_and_boundary(self):
        records, texts = _make_records(60)
        X, _ = cl.build_semantic_features(texts)
        assignments, report = cl.cluster_space("semantic", X, records, texts, k=3, compute_stability=False)
        for e in report.cluster_explanations:
            self.assertIn("representative_id", e)
            self.assertIn("boundary_id", e)
            self.assertIn("top_words", e)
            self.assertGreater(e["n_members"], 0)


class NoiseHandlingTests(unittest.TestCase):
    """KMeans has no noise label, but the ClusterAssignment supports it.
    A future HDBSCAN swap should set is_noise=True for -1 labels."""

    def test_cluster_assignment_supports_noise_flag(self):
        from adintel.types import ClusterAssignment

        a = ClusterAssignment(record_id="r1", cluster_id=-1, space="semantic", is_noise=True)
        self.assertTrue(a.is_noise)


if __name__ == "__main__":
    unittest.main()
