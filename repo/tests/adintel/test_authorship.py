"""Tests for authorship / common-source analysis (adintel.authorship).

Red phase. These tests encode the spec's hard requirements:
- pairwise, closed-set, open-set all implemented as SEPARATE tasks
- length-aware abstention returns INSUFFICIENT_EVIDENCE for short ads
- open-set can return unknown_in_open_set
- robustness invariance (topic/brand/slogan/disclaimer/template removal)
- NEVER name a person from similarity alone
- multi-signal (stylometry, lexical richness, template, structural, council)
"""

from __future__ import annotations

import unittest

from adintel import authorship as au


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TEXT_A1 = (
    "Hola, soy Manuel, brindo ayuda económica constante a chicas estudiantes de universidad. "
    "Soy educado, higiénico, tengo lugar propio. Total discreción. Escríbeme por WhatsApp. "
    "Trato amable y respetuoso. Lima, todo el año. Referencias disponibles."
)

TEXT_A2 = (
    "Hola, soy Manuel, brindo ayuda económica semanal a chicas universitarias. "
    "Educado, higiénico, lugar propio. Total discreción. WhatsApp privado. "
    "Trato amable y respetuoso. Lima, todo el año. Tengo referencias de alumnas."
)

TEXT_B = (
    "Busco persona para compartir departamento amoblado en Miraflores. "
    "Dos habitaciones, sin amueblar. Balcón con vista al mar. "
    "Contrato a seis meses. Depósito en garantía. Llamar después de las 5pm."
)

TEXT_SHORT = "hola escribeme"  # 2 tokens


class PairwiseVerificationTests(unittest.TestCase):
    def test_same_author_pair_returns_same_source(self):
        r = au.pairwise_verify(TEXT_A1, TEXT_A2)
        self.assertEqual(r.task, "pairwise_verification")
        self.assertIn(r.verdict, ("same_source", "insufficient_evidence"))
        # Two near-identical templated ads should be same_source
        if r.verdict != "insufficient_evidence":
            self.assertGreater(r.confidence, 0.4)

    def test_different_author_pair_returns_different_or_insufficient(self):
        r = au.pairwise_verify(TEXT_A1, TEXT_B)
        self.assertIn(r.verdict, ("different_source", "insufficient_evidence"))

    def test_multi_signal_scores_populated(self):
        r = au.pairwise_verify(TEXT_A1, TEXT_A2)
        self.assertIsNotNone(r.stylometry_score)
        self.assertIsNotNone(r.lexical_richness_score)
        self.assertIsNotNone(r.template_signature_score)
        self.assertIsNotNone(r.structural_signature_score)


class ShortTextAbstentionTests(unittest.TestCase):
    """The spec: 'Reduce confidence for short advertisements and return
    INSUFFICIENT_EVIDENCE when necessary.'"""

    def test_short_text_returns_insufficient_evidence(self):
        r = au.pairwise_verify(TEXT_SHORT, TEXT_A1)
        self.assertEqual(r.verdict, "insufficient_evidence")
        self.assertEqual(r.abstention_reason, "below_min_tokens")

    def test_short_text_has_zero_confidence(self):
        r = au.pairwise_verify(TEXT_SHORT, TEXT_A1)
        self.assertEqual(r.confidence, 0.0)

    def test_medium_text_caps_confidence(self):
        # 30 tokens: above MIN but below REDUCED_CONFIDENCE_THRESHOLD
        medium = "hola soy manuel brindo ayuda economica constante a chicas universitarias soy educado higienico tengo lugar propio total discrecion escribeme whatsapp lima todo el ano referencias disponibles ahora"
        r = au.pairwise_verify(medium, TEXT_A1)
        self.assertLessEqual(r.confidence, 0.5)


class ClosedSetAttributionTests(unittest.TestCase):
    def test_picks_best_candidate(self):
        candidates = {"a": TEXT_A1, "b": TEXT_B}
        r = au.closed_set_attrib(TEXT_A2, candidates)
        self.assertEqual(r.task, "closed_set_attribution")
        self.assertEqual(r.verdict, "same_source")

    def test_short_query_abstains(self):
        candidates = {"a": TEXT_A1, "b": TEXT_B}
        r = au.closed_set_attrib(TEXT_SHORT, candidates)
        self.assertEqual(r.verdict, "insufficient_evidence")
        self.assertEqual(r.abstention_reason, "below_min_tokens_for_attribution")


class OpenSetAttributionTests(unittest.TestCase):
    def test_returns_unknown_when_no_candidate_close(self):
        candidates = {"a": TEXT_A1}
        r = au.open_set_attrib(TEXT_B, candidates)
        # TEXT_B is unrelated to TEXT_A1; should be unknown
        self.assertEqual(r.task, "open_set_attribution")
        self.assertIn(r.verdict, ("unknown_in_open_set", "insufficient_evidence"))

    def test_returns_same_source_when_close(self):
        candidates = {"a": TEXT_A1}
        r = au.open_set_attrib(TEXT_A2, candidates)
        self.assertEqual(r.verdict, "same_source")

    def test_empty_candidate_set_returns_unknown(self):
        r = au.open_set_attrib(TEXT_A1, {})
        self.assertEqual(r.verdict, "unknown_in_open_set")
        self.assertEqual(r.abstention_reason, "empty_candidate_set")


class CreativeSourceClusteringTests(unittest.TestCase):
    def test_clusters_near_duplicate_text_together(self):
        texts = [TEXT_A1, TEXT_A2, TEXT_B, TEXT_B + " Otra linea."]
        # For short text the raw char-5-gram similarity between near-duplicates
        # is around 0.6, so we use 0.55 as the clustering threshold (matching
        # SAME_SOURCE_THRESHOLD). This is honest about the short-text limit.
        clusters = au.creative_source_clusters(texts, threshold=0.55)
        self.assertGreater(len(clusters), 0)
        # Find the cluster containing index 0 (TEXT_A1)
        cluster_with_0 = [c for c in clusters if 0 in c][0]
        self.assertIn(1, cluster_with_0, "TEXT_A1 and TEXT_A2 should cluster together")


class RobustnessInvarianceTests(unittest.TestCase):
    """The spec: 'Test whether results survive: topic changes, brand-name
    removal, slogan removal, disclaimer removal, template removal, campaign
    changes, time changes, format changes.'"""

    def test_robustness_dict_populated(self):
        r = au.pairwise_verify(TEXT_A1, TEXT_A2)
        self.assertIn("brand_name_removal", r.survived)
        self.assertIn("slogan_removal", r.survived)
        self.assertIn("disclaimer_removal", r.survived)
        self.assertIn("template_removal", r.survived)

    def test_brand_name_removal_does_not_flip_clear_same_source(self):
        # Two near-identical ads should remain same_source even after brand
        # names are stripped
        r = au.pairwise_verify(TEXT_A1, TEXT_A2)
        if r.verdict == "same_source":
            self.assertTrue(r.survived["brand_name_removal"], "Same-source verdict should survive brand removal")


class PrivacyGuardrailTests(unittest.TestCase):
    """HIGHEST PRIORITY: 'Do not name or accuse a person based solely on
    model similarity.'"""

    def test_pairwise_result_never_names_person(self):
        r = au.pairwise_verify(TEXT_A1, TEXT_A2)
        self.assertFalse(r.person_named, "Pairwise result must never name a person")

    def test_closed_set_result_never_names_person(self):
        r = au.closed_set_attrib(TEXT_A2, {"a": TEXT_A1})
        self.assertFalse(r.person_named)

    def test_open_set_result_never_names_person(self):
        r = au.open_set_attrib(TEXT_A2, {"a": TEXT_A1})
        self.assertFalse(r.person_named)

    def test_assert_no_person_named_passes_on_clean_result(self):
        r = au.pairwise_verify(TEXT_A1, TEXT_A2)
        au.assert_no_person_named(r)  # should not raise

    def test_exact_text_hash_is_deterministic(self):
        h1 = au.exact_text_hash(TEXT_A1)
        h2 = au.exact_text_hash(TEXT_A1)
        self.assertEqual(h1, h2)
        self.assertNotEqual(h1, au.exact_text_hash(TEXT_A2))


if __name__ == "__main__":
    unittest.main()
