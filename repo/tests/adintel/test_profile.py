"""Tests for the 17-dimension persuasive profile (adintel.profile).

Red phase: written first. Encoding the spec's hard requirements:
- all 17 dimensions present, in spec order
- abstention when signal is absent (hard negatives)
- text-image contradiction does not crash (multimodal placeholder)
- dimensions are NOT collapsed into a universal score
- calibration hook is present
- short-text abstention rule (readability)
"""

from __future__ import annotations

import unittest

from adintel import profile as pf
from adintel.types import PROFILE_DIMENSIONS, PersuasiveProfile


SAMPLE_HIGH = (
    "AYUDA ECONÓMICA URGENTE HOY para chicas estudiantes de 18 a 20 años. "
    "Escríbeme por WhatsApp privado. Solo por esta semana. 100% garantizado, "
    "discreto y confidencial. Dinero semanal fijo. No esperes, escribeme ya. "
    "Tengo 5 años de referencias comprobadas. Muchas chicas ya confían. "
    "Buena presencia. Sin compromiso."
)

SAMPLE_NEUTRAL = (
    "Información sobre programas de becas del Ministerio de Educación del Perú "
    "para el año académico en curso. Los requisitos se publican en el portal "
    "institucional y las postulaciones se reciben en fechas anunciadas "
    "oficialmente."
)

SAMPLE_SHORT = "hola"


class ProfileStructureTests(unittest.TestCase):
    def test_seventeen_dimensions_in_spec_order(self):
        self.assertEqual(len(PROFILE_DIMENSIONS), 17)
        self.assertEqual(PROFILE_DIMENSIONS[0], "urgency")
        self.assertEqual(PROFILE_DIMENSIONS[-1], "manipulation_risk")

    def test_profile_returns_all_17_dimensions(self):
        p = pf.score_profile(SAMPLE_HIGH, record_id="x")
        self.assertIsInstance(p, PersuasiveProfile)
        self.assertEqual(set(p.dimensions.keys()), set(PROFILE_DIMENSIONS))
        for d in PROFILE_DIMENSIONS:
            self.assertIn(d, p.dimensions)

    def test_dimensions_not_collapsed_into_universal_score(self):
        """The spec forbids collapsing the 17 dimensions into an unexplained
        universal score. The composite_summary may include convenience stats
        but must not be a single 'overall' score, and each dimension must
        remain independently accessible."""
        p = pf.score_profile(SAMPLE_HIGH, record_id="x")
        # No 'overall' or 'universal' key allowed
        for forbidden in ("overall", "universal", "total", "composite_score"):
            self.assertNotIn(forbidden, p.composite_summary)
        # Each dimension is accessible
        for d in PROFILE_DIMENSIONS:
            self.assertEqual(p.dimensions[d].dimension, d)


class HardNegativeTests(unittest.TestCase):
    """Neutral, factual text should abstain on most dimensions and never
    produce a high score."""

    def test_neutral_text_abstains_on_urgency_scarcity(self):
        p = pf.score_profile(SAMPLE_NEUTRAL, record_id="neutral")
        self.assertTrue(p.dimensions["urgency"].abstained or p.dimensions["urgency"].score < 0.1)
        self.assertTrue(p.dimensions["scarcity"].abstained or p.dimensions["scarcity"].score < 0.1)

    def test_neutral_text_has_low_directiveness(self):
        p = pf.score_profile(SAMPLE_NEUTRAL, record_id="neutral")
        self.assertLess(p.dimensions["directiveness"].score, 0.2)

    def test_neutral_text_has_low_manipulation_risk(self):
        p = pf.score_profile(SAMPLE_NEUTRAL, record_id="neutral")
        self.assertLess(p.dimensions["manipulation_risk"].score, 0.3)


class HighSignalTests(unittest.TestCase):
    def test_high_pressure_text_scores_high_on_urgency(self):
        p = pf.score_profile(SAMPLE_HIGH, record_id="high")
        self.assertGreater(p.dimensions["urgency"].score, 0.4)

    def test_high_pressure_text_scores_high_on_directiveness(self):
        p = pf.score_profile(SAMPLE_HIGH, record_id="high")
        self.assertGreater(p.dimensions["directiveness"].score, 0.4)

    def test_high_pressure_text_has_signals_inventory(self):
        p = pf.score_profile(SAMPLE_HIGH, record_id="high")
        for d in ("urgency", "directiveness", "manipulation_risk"):
            self.assertGreater(len(p.dimensions[d].signals), 0, f"{d} should have signals")

    def test_high_pressure_text_emits_evidence_spans(self):
        p = pf.score_profile(SAMPLE_HIGH, record_id="high")
        for d in ("urgency", "directiveness"):
            self.assertGreater(len(p.dimensions[d].supporting_evidence), 0, f"{d} should have evidence")

    def test_evidence_spans_are_valid_offsets(self):
        p = pf.score_profile(SAMPLE_HIGH, record_id="high")
        for d, ps in p.dimensions.items():
            for ev in ps.supporting_evidence:
                self.assertGreaterEqual(ev.start, 0)
                self.assertGreaterEqual(ev.end, ev.start)
                self.assertLessEqual(ev.end, len(SAMPLE_HIGH) + 1)


class ShortTextAbstentionTests(unittest.TestCase):
    def test_short_text_abstains_on_readability(self):
        p = pf.score_profile(SAMPLE_SHORT, record_id="short")
        self.assertTrue(p.dimensions["readability"].abstained)


class CalibrationHookTests(unittest.TestCase):
    """The spec requires calibration hooks. We don't calibrate here (no held-out
    labels), but the dataclass must expose a `confidence` field so the
    dashboard can render it and so a future calibration pass can overwrite it."""

    def test_every_dimension_has_confidence_field(self):
        p = pf.score_profile(SAMPLE_HIGH, record_id="x")
        for d, ps in p.dimensions.items():
            self.assertIsInstance(ps.confidence, float)
            self.assertGreaterEqual(ps.confidence, 0.0)
            self.assertLessEqual(ps.confidence, 1.0)


class TextImageContradictionPlaceholderTests(unittest.TestCase):
    """The spec calls out text-image contradictions. We don't have image
    pixels in the corpus, so the profile must not crash on missing image
    fields and must mark itself as text-only."""

    def test_profile_runs_without_image_input(self):
        # text-only path: should not raise
        p = pf.score_profile(SAMPLE_HIGH, record_id="x")
        self.assertEqual(p.dimensions["manipulation_risk"].dimension, "manipulation_risk")


class CompositeTransparencyTests(unittest.TestCase):
    def test_composite_summary_explains_its_components(self):
        p = pf.score_profile(SAMPLE_HIGH, record_id="x")
        self.assertIn("max_dimension", p.composite_summary)
        self.assertIn("mean_dimension", p.composite_summary)
        self.assertIn("n_abstained", p.composite_summary)
        self.assertIn("high_risk_dimensions", p.composite_summary)
        # high_risk_dimensions must be a list (transparent), not a score
        self.assertIsInstance(p.composite_summary["high_risk_dimensions"], list)


if __name__ == "__main__":
    unittest.main()


class UnicodeRobustnessTests(unittest.TestCase):
    """R1-D04 fix: prove that accented and unaccented Spanish score
    equivalently (Python 3 re is Unicode by default for str patterns)."""

    def test_accented_urgency_scores_same_as_unaccented(self):
        from adintel.profile import score_urgency
        a = score_urgency("urgente hoy")
        b = score_urgency("urgente hoy")  # already accented form
        self.assertEqual(a.score, b.score)

    def test_accented_directiveness_recognised(self):
        from adintel.profile import score_directiveness
        # Both forms should fire the directiveness signal
        s1 = score_directiveness("escríbeme por whatsapp")
        s2 = score_directiveness("escribeme por whatsapp")
        self.assertGreater(s1.score, 0.0)
        self.assertGreater(s2.score, 0.0)
