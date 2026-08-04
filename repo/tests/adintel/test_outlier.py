"""Tests for outlier and novelty analysis (adintel.outlier).

Red phase. Each of the 10+ outlier types must:
- produce a typed OutlierReport
- include comparison_population, feature_space, score, method,
  supporting_features, alternative_explanation, uncertainty, review_status
- never return certainty 1.0 except for exact duplicates and metadata schema
  failures (which are definitionally certain)
"""

from __future__ import annotations

import unittest

from adintel import outlier as ot
from adintel.types import OutlierReport


def _make_records(n: int = 60) -> tuple[list[dict], list[str]]:
    records: list[dict] = []
    texts: list[str] = []
    for i in range(n):
        rec = {
            "record_id": f"r{i}",
            "source_platform": "doplim",
            "collected_at": f"2026-07-{(i % 28) + 1:02d}T12:00:00Z",
            "title": f"Title {i}",
            "body_redacted": f"Body {i}",
            "metadata": {"platform_family": "doplim", "quality_score": 0.5, "image_count": 1, "raw_size_bucket": "10kb_100kb"},
        }
        records.append(rec)
        texts.append(f"ayuda economica para chicas estudiante lima {i} whatsapp")
    # Inject one duplicate
    texts.append(texts[0])
    records.append({**records[0], "record_id": "r_dup"})
    # Inject one extraction error
    texts.append("null undefined")
    records.append({**records[0], "record_id": "r_err"})
    # Inject one metadata error
    records.append({"record_id": "r_meta_err", "source_platform": "", "collected_at": "", "title": "", "body_redacted": "", "metadata": {}})
    texts.append("ayuda economica")
    return records, texts


class OutlierReportContractTests(unittest.TestCase):
    """Every OutlierReport must carry the required fields per spec."""

    def test_every_report_has_required_fields(self):
        records, texts = _make_records(60)
        reports = ot.detect_all_outliers(texts, records)
        self.assertGreater(len(reports), 0)
        for r in reports:
            self.assertIsInstance(r, OutlierReport)
            self.assertIsInstance(r.record_id, str)
            self.assertIsInstance(r.kind, str)
            self.assertGreaterEqual(r.score, 0.0)
            self.assertLessEqual(r.score, 1.0)
            self.assertIsInstance(r.method, str)
            self.assertIsInstance(r.comparison_population, str)
            self.assertIsInstance(r.feature_space, str)
            self.assertIsInstance(r.supporting_features, dict)
            self.assertIsInstance(r.alternative_explanation, str)
            self.assertGreaterEqual(r.uncertainty, 0.0)
            self.assertLessEqual(r.uncertainty, 1.0)
            self.assertEqual(r.review_status, "unreviewed")


class CreativeNoveltyTests(unittest.TestCase):
    def test_detects_novelty_in_diverse_corpus(self):
        records, texts = _make_records(60)
        reports = ot.detect_creative_novelty(texts, records)
        self.assertIsInstance(reports, list)
        # Novelty detection should not crash and should return a list


class UnusualTechniqueCombinationTests(unittest.TestCase):
    def test_rare_combination_flagged(self):
        records, _ = _make_records(60)
        # Most ads get labels {a, b}; one gets {a, z} (rare)
        label_sets = [{"a", "b"}] * 60
        label_sets[5] = {"a", "z"}
        reports = ot.detect_unusual_technique_combination(label_sets, records, support_threshold=5)
        self.assertGreater(len(reports), 0)
        self.assertEqual(reports[0].kind, "unusual_technique_combination")


class StyleOutlierTests(unittest.TestCase):
    def test_style_outlier_detection_runs(self):
        records, texts = _make_records(60)
        reports = ot.detect_style_outliers(texts, records, z_threshold=2.0)
        self.assertIsInstance(reports, list)


class VisualOutlierTests(unittest.TestCase):
    def test_visual_outlier_detection_runs(self):
        records, _ = _make_records(60)
        reports = ot.detect_visual_outliers(records, z_threshold=2.0)
        self.assertIsInstance(reports, list)


class PerformanceOutlierTests(unittest.TestCase):
    def test_performance_outliers_returned_as_pair(self):
        records, _ = _make_records(60)
        over, under = ot.detect_performance_outliers(records, z_threshold=1.0)
        # With z=1.0 threshold we should get at least some outliers
        self.assertIsInstance(over, list)
        self.assertIsInstance(under, list)
        # All performance outliers must explicitly flag the proxy limitation
        for r in over + under:
            self.assertIn("proxy", r.alternative_explanation.lower())


class TemporalOutlierTests(unittest.TestCase):
    def test_temporal_outliers_run(self):
        records, _ = _make_records(60)
        reports = ot.detect_temporal_outliers(records, z_threshold=2.0)
        self.assertIsInstance(reports, list)


class DuplicateTests(unittest.TestCase):
    def test_exact_duplicates_flagged_with_certainty(self):
        records, texts = _make_records(60)
        # The fixture injects one exact duplicate
        reports = ot.detect_duplicates(texts, records)
        self.assertGreater(len(reports), 0, "Should detect the injected duplicate")
        for r in reports:
            self.assertEqual(r.kind, "duplicate")
            self.assertEqual(r.score, 1.0)
            self.assertEqual(r.uncertainty, 0.0, "Exact-text duplicates have certainty 1.0")


class ExtractionErrorTests(unittest.TestCase):
    def test_extraction_error_flagged(self):
        records, texts = _make_records(60)
        reports = ot.detect_extraction_errors(texts, records)
        kinds = {r.kind for r in reports}
        self.assertIn("extraction_error", kinds)


class MetadataErrorTests(unittest.TestCase):
    def test_metadata_error_flagged_for_missing_required_fields(self):
        records, _ = _make_records(60)
        reports = ot.detect_metadata_errors(records)
        kinds = {r.kind for r in reports}
        self.assertIn("metadata_error", kinds)
        # Find the injected one
        rec_ids = {r.record_id for r in reports}
        self.assertIn("r_meta_err", rec_ids)


class ModelErrorTests(unittest.TestCase):
    def test_low_confidence_flagged_as_model_error(self):
        records, _ = _make_records(60)
        preds = [{"confidence": 0.1}] * 60
        reports = ot.detect_model_errors(preds, records, confidence_floor=0.2)
        self.assertGreater(len(reports), 0)
        self.assertEqual(reports[0].kind, "model_error")

    def test_checkpoint_disagreement_flagged(self):
        records, _ = _make_records(60)
        preds = [{"confidence": 0.9, "disagreement": ["cp_a", "cp_b", "cp_c"]}] * 60
        reports = ot.detect_model_errors(preds, records, confidence_floor=0.2, disagreement_threshold=2)
        self.assertGreater(len(reports), 0)


class AllOutliersTests(unittest.TestCase):
    def test_detect_all_returns_full_list(self):
        records, texts = _make_records(60)
        reports = ot.detect_all_outliers(texts, records)
        kinds = {r.kind for r in reports}
        # At least duplicate, extraction_error, metadata_error should always fire
        self.assertIn("duplicate", kinds)
        self.assertIn("extraction_error", kinds)
        self.assertIn("metadata_error", kinds)


if __name__ == "__main__":
    unittest.main()
