"""Tests for the JSON API surface (adintel.api).

Red phase. Encodes:
- every endpoint returns an APIResponse with the required fields
- request_id is deterministic
- abstention is reported correctly
- monitoring summary is available
- evidence refs are preserved
"""

from __future__ import annotations

import unittest

from adintel.api import AdIntelAPI, APIResponse, API_VERSION


SAMPLE = (
    "AYUDA ECONÓMICA URGENTE HOY para chicas estudiantes de 18 a 20 años. "
    "Escríbeme por WhatsApp privado. Solo por esta semana. 100% garantizado, "
    "discreto y confidencial. Dinero semanal fijo. No esperes, escribeme ya."
)


class APIContractTests(unittest.TestCase):
    def setUp(self):
        self.api = AdIntelAPI()

    def test_every_response_has_required_fields(self):
        r = self.api.score_profile(SAMPLE, record_id="r1")
        self.assertIsInstance(r, APIResponse)
        for field in (
            "request_id", "api_version", "checkpoint_id", "typed_output",
            "held_out_metrics", "calibration_status", "cost_usd_per_1k",
            "latency_ms", "abstained", "abstention_reason", "review_status",
            "evidence_refs_preserved",
        ):
            self.assertTrue(hasattr(r, field), f"Missing field: {field}")
        self.assertEqual(r.api_version, API_VERSION)

    def test_request_id_is_deterministic(self):
        r1 = self.api.score_profile(SAMPLE, record_id="r1")
        r2 = self.api.score_profile(SAMPLE, record_id="r1")
        self.assertEqual(r1.request_id, r2.request_id)

    def test_request_id_differs_for_different_inputs(self):
        r1 = self.api.score_profile(SAMPLE, record_id="r1")
        r2 = self.api.score_profile(SAMPLE + " extra", record_id="r1")
        self.assertNotEqual(r1.request_id, r2.request_id)


class ProfileEndpointTests(unittest.TestCase):
    def test_profile_endpoint_returns_17_dimensions(self):
        api = AdIntelAPI()
        r = api.score_profile(SAMPLE, record_id="r1")
        self.assertFalse(r.abstained)
        dims = r.typed_output["dimensions"]
        self.assertEqual(len(dims), 17)

    def test_profile_endpoint_abstains_on_empty_text(self):
        api = AdIntelAPI()
        r = api.score_profile("", record_id="r1")
        self.assertTrue(r.abstained)
        self.assertEqual(r.abstention_reason, "empty_text")


class AuthorshipEndpointTests(unittest.TestCase):
    def test_pairwise_endpoint_returns_verdict(self):
        api = AdIntelAPI()
        r = api.pairwise_verify(SAMPLE, SAMPLE + " otra cosa.")
        self.assertIn(r.typed_output["verdict"], ("same_source", "different_source", "insufficient_evidence"))

    def test_open_set_endpoint_handles_empty_candidates(self):
        api = AdIntelAPI()
        r = api.open_set_attrib(SAMPLE, {})
        self.assertEqual(r.typed_output["verdict"], "unknown_in_open_set")


class TaxonomyEndpointTests(unittest.TestCase):
    def test_taxonomy_endpoint_returns_full_taxonomy(self):
        api = AdIntelAPI()
        r = api.get_taxonomy()
        self.assertEqual(r.typed_output["taxonomy_version"], "adintel-taxonomy-v2")
        self.assertGreater(len(r.typed_output["nodes"]), 10)


class MonitoringTests(unittest.TestCase):
    def test_monitoring_summary_returns_latency_stats(self):
        api = AdIntelAPI()
        api.score_profile(SAMPLE, record_id="r1")
        api.score_profile(SAMPLE, record_id="r2")
        s = api.monitoring_summary()
        self.assertEqual(s["n_calls"], 2)
        self.assertIn("p50_latency_ms", s)
        self.assertIn("p95_latency_ms", s)
        self.assertIn("by_endpoint", s)


class EvidenceDisciplineTests(unittest.TestCase):
    """The spec: 'Do not treat technique presence as proof of persuasion;
    persuasive intensity as proof of performance; performance association as
    proof of causation; authorship similarity as proof of personal identity.'"""

    def test_profile_does_not_claim_persuasion(self):
        api = AdIntelAPI()
        r = api.score_profile(SAMPLE, record_id="r1")
        # The composite summary must NOT have a 'persuasion_proof' or similar
        # field; profile scores are signals, not proof.
        composite = r.typed_output.get("composite_summary", {})
        for forbidden in ("persuasion_proof", "persuasion_score", "proven_persuasion"):
            self.assertNotIn(forbidden, composite)

    def test_authorship_result_does_not_name_person(self):
        api = AdIntelAPI()
        r = api.pairwise_verify(SAMPLE, SAMPLE)
        self.assertFalse(r.typed_output["person_named"])


if __name__ == "__main__":
    unittest.main()


class OutputVersionTests(unittest.TestCase):
    """R2-D02 fix: every typed_output must include an output_version field
    so future schema migrations can be detected."""

    def test_profile_output_has_version(self):
        api = AdIntelAPI()
        r = api.score_profile(SAMPLE, record_id="r1")
        self.assertIn("output_version", r.typed_output)
        self.assertTrue(r.typed_output["output_version"].startswith("persuasive-profile-v"))

    def test_authorship_output_has_version(self):
        api = AdIntelAPI()
        r = api.pairwise_verify(SAMPLE, SAMPLE)
        self.assertIn("output_version", r.typed_output)
        self.assertTrue(r.typed_output["output_version"].startswith("authorship-v"))

    def test_taxonomy_output_has_version(self):
        api = AdIntelAPI()
        r = api.get_taxonomy()
        self.assertIn("taxonomy_version", r.typed_output)
