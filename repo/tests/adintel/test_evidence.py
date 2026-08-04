"""Tests for evidence-discipline helpers (adintel.evidence).

Red phase. Encodes:
- causal verbs without qualifier trigger a warning
- PerformanceClaim must have strength
- PersuasiveProfile composite_summary must not collapse to universal
- authorship must not identify a person
"""

from __future__ import annotations

import unittest

from adintel import evidence as ev
from adintel.types import PerformanceClaim, PersuasiveProfile, ProfileScore


class ClaimLintTests(unittest.TestCase):
    def test_bare_causal_verb_triggers_warning(self):
        text = "Ads with urgency perform better."
        # 'better' is not in CAUSAL_VERBS; use a stronger verb
        text = "Urgency improves conversion."
        warnings = ev.lint_claim_text(text)
        self.assertGreater(len(warnings), 0)
        self.assertEqual(warnings[0]["verb"], "improves")

    def test_causal_verb_with_associative_qualifier_does_not_trigger(self):
        text = "Urgency is associated with conversion."
        warnings = ev.lint_claim_text(text)
        # 'associated with' should suppress the warning for nearby causal verb
        # but 'associated' is not itself a causal verb, so no warning fires.
        self.assertEqual(warnings, [])

    def test_causal_verb_with_may_does_not_trigger(self):
        text = "Urgency may improve conversion in this sample."
        warnings = ev.lint_claim_text(text)
        self.assertEqual(warnings, [])

    def test_causal_verb_with_quasi_causal_qualifier_does_not_trigger(self):
        text = "This is quasi-causal: urgency improves conversion after controls."
        warnings = ev.lint_claim_text(text)
        # 'quasi-causal' should suppress
        self.assertEqual(warnings, [])


class StrengthRequirementTests(unittest.TestCase):
    def test_claim_without_strength_raises(self):
        c = PerformanceClaim(
            record_id="r1",
            population="all doplim ads",
            claim="x",
            strength="",  # empty
            controls=[],
            missing_controls=[],
            uncertainty=0.5,
        )
        with self.assertRaises(ValueError):
            ev.require_strength(c)

    def test_claim_with_invalid_strength_raises(self):
        c = PerformanceClaim(
            record_id="r1",
            population="all",
            claim="x",
            strength="definitely",
            controls=[],
            missing_controls=[],
            uncertainty=0.5,
        )
        with self.assertRaises(ValueError):
            ev.require_strength(c)

    def test_claim_with_valid_strength_passes(self):
        c = PerformanceClaim(
            record_id="r1",
            population="all",
            claim="x",
            strength="associative",
            controls=[],
            missing_controls=[],
            uncertainty=0.5,
        )
        ev.require_strength(c)  # should not raise


class UniversalScoreGuardTests(unittest.TestCase):
    def _profile(self, composite: dict) -> PersuasiveProfile:
        from adintel.types import PROFILE_DIMENSIONS
        dims = {d: ProfileScore(dimension=d, score=0.1, raw_score=0.1, signals=[], supporting_evidence=[], abstained=False) for d in PROFILE_DIMENSIONS}
        return PersuasiveProfile(
            record_id="r1",
            taxonomy_version="test",
            checkpoint_id="test",
            dimensions=dims,
            composite_summary=composite,
        )

    def test_overall_key_triggers_guard(self):
        p = self._profile({"overall": 0.5, "max_dimension": 0.5})
        with self.assertRaises(AssertionError):
            ev.assert_no_universal_score(p)

    def test_max_dimension_does_not_trigger(self):
        p = self._profile({"max_dimension": 0.5, "mean_dimension": 0.3, "n_abstained": 0, "high_risk_dimensions": []})
        ev.assert_no_universal_score(p)  # should not raise


class AuthorshipIdentityGuardTests(unittest.TestCase):
    def test_person_named_true_raises(self):
        with self.assertRaises(AssertionError):
            ev.assert_authorship_does_not_identify_person({"person_named": True})

    def test_person_name_field_populated_raises(self):
        with self.assertRaises(AssertionError):
            ev.assert_authorship_does_not_identify_person({"person_named": False, "person_name": "Manuel"})

    def test_clean_result_passes(self):
        ev.assert_authorship_does_not_identify_person({"person_named": False, "verdict": "same_source"})


class HumanRoutingTests(unittest.TestCase):
    def test_low_confidence_routes_to_human(self):
        self.assertTrue(ev.route_to_human_if_low_confidence_or_disagreement(confidence=0.2, disagreement=[]))

    def test_high_confidence_no_disagreement_does_not_route(self):
        self.assertFalse(ev.route_to_human_if_low_confidence_or_disagreement(confidence=0.8, disagreement=[]))

    def test_disagreement_routes_to_human(self):
        self.assertTrue(ev.route_to_human_if_low_confidence_or_disagreement(confidence=0.8, disagreement=["a", "b"]))


if __name__ == "__main__":
    unittest.main()
