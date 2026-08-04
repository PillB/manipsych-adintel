"""Tests for the checkpoint registry (adintel.checkpoints).

Red phase. Encodes:
- every checkpoint has version, config, abstention conditions, cost, latency
- run_checkpoint returns a typed CheckpointOutput
- calibration helpers exist (platt, temperature)
- DO NOT average uncalibrated scores
- model disagreement routes to human review
"""

from __future__ import annotations

import unittest

from adintel import checkpoints as cp
from adintel.types import CheckpointOutput


class RegistryTests(unittest.TestCase):
    def test_registry_has_required_checkpoints(self):
        for cid in ("rule-detector-v1", "tfidf-ovr-v1", "persuasive-profile-v1", "authorship-v1", "outlier-v1", "clustering-v1"):
            self.assertIn(cid, cp.REGISTRY, f"Missing checkpoint: {cid}")

    def test_every_spec_has_version_and_config(self):
        for cid, spec in cp.REGISTRY.items():
            self.assertIsInstance(spec.version, str)
            self.assertIsInstance(spec.config, dict)
            self.assertGreater(len(spec.version), 0)

    def test_every_spec_has_abstention_conditions(self):
        for cid, spec in cp.REGISTRY.items():
            self.assertIsInstance(spec.abstention_conditions, list)

    def test_every_spec_has_cost_and_latency(self):
        for cid, spec in cp.REGISTRY.items():
            self.assertIsInstance(spec.cost_usd_per_1k, float)
            self.assertIsInstance(spec.latency_ms_p50, float)
            self.assertGreaterEqual(spec.cost_usd_per_1k, 0.0)
            self.assertGreaterEqual(spec.latency_ms_p50, 0.0)


class TypedOutputTests(unittest.TestCase):
    def test_run_checkpoint_returns_typed_output(self):
        def fake_run(text: str) -> tuple[dict, bool, str | None, bool]:
            return ({"score": 0.5}, False, None, True)

        out = cp.run_checkpoint("rule-detector-v1", fake_run, held_out_metrics={"f1": 0.7}, text="hola")
        self.assertIsInstance(out, CheckpointOutput)
        self.assertEqual(out.checkpoint_id, "rule-detector-v1")
        self.assertEqual(out.typed_output["score"], 0.5)
        self.assertEqual(out.held_out_metrics["f1"], 0.7)
        self.assertFalse(out.abstention_rate > 0.5)
        self.assertTrue(out.evidence_refs_preserved)


class CalibrationTests(unittest.TestCase):
    def test_platt_scale_returns_calibrated_probabilities(self):
        scores = [0.1, 0.2, 0.8, 0.9]
        labels = [0, 0, 1, 1]
        calibrated = cp.platt_scale(scores, labels)
        self.assertEqual(len(calibrated), 4)
        for c in calibrated:
            self.assertGreaterEqual(c, 0.0)
            self.assertLessEqual(c, 1.0)

    def test_temperature_scale_with_high_temperature_flattens(self):
        scores = [0.1, 0.5, 0.9]
        cold = cp.temperature_scale(scores, temperature=0.5)
        hot = cp.temperature_scale(scores, temperature=5.0)
        # Hot temperature should flatten the distribution toward 0.5
        self.assertLess(abs(hot[2] - hot[0]), abs(cold[2] - cold[0]))


class NoAveragingUncalibratedTests(unittest.TestCase):
    """The spec: 'Do not average uncalibrated model scores.'"""

    def test_average_returns_none_when_any_uncalibrated(self):
        # Build two fake outputs, one uncalibrated
        from adintel.types import CheckpointOutput

        uncalibrated = CheckpointOutput(
            checkpoint_id="a",
            version="1",
            config={},
            typed_output={"score": 0.7},
            held_out_metrics={},
            calibration_status="uncalibrated",
            baseline_comparison={},
            disagreement=[],
        )
        calibrated = CheckpointOutput(
            checkpoint_id="b",
            version="1",
            config={},
            typed_output={"score": 0.6},
            held_out_metrics={},
            calibration_status="platt",
            baseline_comparison={},
            disagreement=[],
        )
        # Mix uncalibrated + calibrated -> should refuse to average
        result = cp.average_calibrated_only([uncalibrated, calibrated])
        self.assertIsNone(result, "Must NOT average when any input is uncalibrated")

    def test_average_returns_value_when_all_calibrated(self):
        from adintel.types import CheckpointOutput

        a = CheckpointOutput(
            checkpoint_id="a", version="1", config={}, typed_output={"score": 0.7},
            held_out_metrics={}, calibration_status="platt", baseline_comparison={}, disagreement=[],
        )
        b = CheckpointOutput(
            checkpoint_id="b", version="1", config={}, typed_output={"score": 0.5},
            held_out_metrics={}, calibration_status="isotonic", baseline_comparison={}, disagreement=[],
        )
        result = cp.average_calibrated_only([a, b])
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, 0.6)


class HumanRoutingTests(unittest.TestCase):
    """The spec: 'Use model disagreement to route difficult cases to human review.'"""

    def test_disagreement_triggers_human_routing(self):
        from adintel.types import CheckpointOutput

        a = CheckpointOutput(
            checkpoint_id="a", version="1", config={}, typed_output={},
            held_out_metrics={}, calibration_status="uncalibrated",
            baseline_comparison={}, disagreement=["b"],
        )
        b = CheckpointOutput(
            checkpoint_id="b", version="1", config={}, typed_output={},
            held_out_metrics={}, calibration_status="uncalibrated",
            baseline_comparison={}, disagreement=["a"],
        )
        self.assertTrue(cp.should_route_to_human([a, b]))

    def test_no_disagreement_does_not_route(self):
        from adintel.types import CheckpointOutput

        a = CheckpointOutput(checkpoint_id="a", version="1", config={}, typed_output={}, held_out_metrics={}, calibration_status="uncalibrated", baseline_comparison={}, disagreement=[])
        self.assertFalse(cp.should_route_to_human([a]))


if __name__ == "__main__":
    unittest.main()
