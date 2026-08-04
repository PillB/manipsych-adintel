"""Checkpoint registry and calibration helpers.

The spec requires that for each checkpoint:
  - document the version and configuration;
  - return a typed output;
  - evaluate on held-out fixtures;
  - calibrate confidence;
  - compare against an interpretable baseline;
  - record disagreement;
  - preserve evidence references;
  - test robustness;
  - calculate cost and latency;
  - define conditions for abstention.

Do NOT average uncalibrated model scores. Use model disagreement to route
difficult cases to human review.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from adintel.types import CheckpointOutput


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


@dataclass
class CheckpointSpec:
    """Static spec for a checkpoint: identity, version, config, abstention
    conditions, cost, latency baseline."""

    checkpoint_id: str
    version: str
    config: dict[str, Any]
    abstention_conditions: list[str]
    cost_usd_per_1k: float
    latency_ms_p50: float
    baseline_checkpoint_id: str | None  # for comparison
    calibration_status: str = "uncalibrated"
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "checkpoint_id": self.checkpoint_id,
            "version": self.version,
            "config": self.config,
            "abstention_conditions": self.abstention_conditions,
            "cost_usd_per_1k": self.cost_usd_per_1k,
            "latency_ms_p50": self.latency_ms_p50,
            "baseline_checkpoint_id": self.baseline_checkpoint_id,
            "calibration_status": self.calibration_status,
            "description": self.description,
        }


# The registry of known checkpoints. New checkpoints must be registered here
# before they can be used in the pipeline.
REGISTRY: dict[str, CheckpointSpec] = {}


def register(spec: CheckpointSpec) -> None:
    REGISTRY[spec.checkpoint_id] = spec


def get_spec(checkpoint_id: str) -> CheckpointSpec:
    if checkpoint_id not in REGISTRY:
        raise KeyError(f"Checkpoint not registered: {checkpoint_id}")
    return REGISTRY[checkpoint_id]


def all_specs() -> dict[str, CheckpointSpec]:
    return dict(REGISTRY)


# ---------------------------------------------------------------------------
# Default checkpoint registrations
# ---------------------------------------------------------------------------

# These are the checkpoints the system actually runs. Adding a new checkpoint
# means registering a new spec here, supplying a typed-output function, and
# adding a baseline comparison.

register(CheckpointSpec(
    checkpoint_id="rule-detector-v1",
    version="rule-detector-v1.0.0",
    config={
        "source": "tools/detect_manipulation.py",
        "rules": "scarcity_urgency_pressure, reciprocity_obligation, platform_migration, safety_and_privacy_multiplier, financial_emergency_multiplier, confirmshaming_guilt_pressure",
        "weights": "0.15-0.25 per rule, capped at 1.0",
    },
    abstention_conditions=["empty_text", "no_rule_match"],
    cost_usd_per_1k=0.0,
    latency_ms_p50=1.0,
    baseline_checkpoint_id=None,
    calibration_status="uncalibrated",
    description="Lexical rule-based baseline. Transparent but brittle. Used as the interpretable baseline for every other checkpoint.",
))

register(CheckpointSpec(
    checkpoint_id="tfidf-ovr-v1",
    version="tfidf-ovr-v1.0.0",
    config={
        "vectorizer": "TfidfVectorizer(ngram_range=(1,2), min_df=1, max_features=3000)",
        "classifier": "OneVsRestClassifier(LogisticRegression(max_iter=1000, class_weight=balanced))",
        "training_data": "data/processed/ad_manifest.jsonl (5,189 records)",
        "labels": "weak-supervised from rule-based detector + metadata cues",
    },
    abstention_conditions=["text_below_5_tokens", "all_probabilities_below_0.3"],
    cost_usd_per_1k=0.0,
    latency_ms_p50=10.0,
    baseline_checkpoint_id="rule-detector-v1",
    calibration_status="uncalibrated",
    description="TF-IDF + OVR logistic regression. Existing v1 council model. Metrics are agreement-with-council, NOT independent validity.",
))

register(CheckpointSpec(
    checkpoint_id="persuasive-profile-v1",
    version="persuasive-profile-v1.0.0",
    config={
        "dimensions": 17,
        "scoring": "rule-based signal inventories with saturating transform",
        "calibration": "uncalibrated (no held-out labels)",
        "composites": "transparent summary only; no universal score",
    },
    abstention_conditions=["empty_text", "dimension_specific_signal_absence"],
    cost_usd_per_1k=0.0,
    latency_ms_p50=5.0,
    baseline_checkpoint_id="rule-detector-v1",
    calibration_status="uncalibrated",
    description="17-dimension persuasive profile. Per-dimension signal inventories are auditable. Composites are transparent summaries, not universal scores.",
))

register(CheckpointSpec(
    checkpoint_id="authorship-v1",
    version="authorship-v1.0.0",
    config={
        "stylometry": "TfidfVectorizer(char_wb, 4-5-grams, 2000 features, sublinear_tf)",
        "weighting": "0.50 stylometry + 0.15 lexical_richness + 0.20 template + 0.10 structural + 0.05 council_overlap",
        "min_tokens_for_verification": 15,
        "min_tokens_for_attribution": 15,
        "reduced_confidence_threshold": 60,
        "short_text_confidence_floor": 0.30,
        "calibration": "Platt scaling fitted on 400 pairs (200 pos, 200 neg); Brier=0.0034, ECE=0.0525",
        "calibration_artifact": "models/authorship_platt_calibration.pkl",
    },
    abstention_conditions=["below_min_tokens", "empty_candidate_set_in_open_set", "ambiguous_zone"],
    cost_usd_per_1k=0.0,
    latency_ms_p50=20.0,
    baseline_checkpoint_id="rule-detector-v1",
    calibration_status="platt",
    description="Multi-signal authorship / common-source analysis. Length-aware abstention. NEVER names a person from similarity alone. Platt-calibrated on 400 pairs (Brier=0.0034).",
))

register(CheckpointSpec(
    checkpoint_id="outlier-v1",
    version="outlier-v1.0.0",
    config={
        "detectors": "creative_novelty, unusual_technique_combination, style_outlier, visual_outlier, performance_over/under, temporal, duplicate, extraction_error, metadata_error, model_error",
        "performance_proxy": "quality_score (corpus has no real performance metrics)",
    },
    abstention_conditions=["corpus_below_5_records"],
    cost_usd_per_1k=0.0,
    latency_ms_p50=50.0,
    baseline_checkpoint_id="rule-detector-v1",
    calibration_status="uncalibrated",
    description="10+ outlier detectors. Every report carries comparison population, feature space, alternative explanation, and uncertainty.",
))

register(CheckpointSpec(
    checkpoint_id="clustering-v1",
    version="clustering-v1.0.0",
    config={
        "spaces": "persuasive, semantic, rhetorical, visual, multimodal, authorial, performance",
        "algorithm": "MiniBatchKMeans (deterministic seed)",
        "stability_eval": "ARI over 5 bootstrap resamples",
        "leakage_eval": "per-cluster platform / platform_family dominance",
    },
    abstention_conditions=["corpus_below_10_records", "k_greater_than_n_records"],
    cost_usd_per_1k=0.0,
    latency_ms_p50=200.0,
    baseline_checkpoint_id=None,
    calibration_status="uncalibrated",
    description="7-space clustering with stability, leakage, and explanation reports.",
))


# ---------------------------------------------------------------------------
# Typed-output runner
# ---------------------------------------------------------------------------


@dataclass
class CheckpointRunResult:
    """A single execution of a checkpoint on one input."""

    checkpoint_id: str
    typed_output: dict[str, Any]
    held_out_metrics: dict[str, float]
    disagreement: list[str]  # other checkpoint_ids that disagreed
    abstained: bool
    abstention_reason: str | None
    elapsed_ms: float
    evidence_refs_preserved: bool

    def to_checkpoint_output(self, baseline_comparison: dict[str, float] | None = None) -> CheckpointOutput:
        spec = get_spec(self.checkpoint_id)
        return CheckpointOutput(
            checkpoint_id=self.checkpoint_id,
            version=spec.version,
            config=spec.config,
            typed_output=self.typed_output,
            held_out_metrics=self.held_out_metrics,
            calibration_status=spec.calibration_status,
            baseline_comparison=baseline_comparison or {},
            disagreement=self.disagreement,
            cost_usd_per_1k=spec.cost_usd_per_1k,
            latency_ms_p50=self.elapsed_ms,
            abstention_rate=1.0 if self.abstained else 0.0,
            abstention_conditions=spec.abstention_conditions,
            evidence_refs_preserved=self.evidence_refs_preserved,
        )


def run_checkpoint(
    checkpoint_id: str,
    run_fn: Callable[..., dict[str, Any]],
    held_out_metrics: dict[str, float] | None = None,
    disagreement: list[str] | None = None,
    baseline_comparison: dict[str, float] | None = None,
    *args,
    **kwargs,
) -> CheckpointOutput:
    """Execute a checkpoint function, time it, and wrap its output in a
    typed CheckpointOutput. This is the single entry point that guarantees
    every checkpoint returns the same typed contract."""
    spec = get_spec(checkpoint_id)
    t0 = time.perf_counter()
    typed_output, abstained, abstention_reason, evidence_preserved = run_fn(*args, **kwargs)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    run = CheckpointRunResult(
        checkpoint_id=checkpoint_id,
        typed_output=typed_output,
        held_out_metrics=held_out_metrics or {},
        disagreement=disagreement or [],
        abstained=abstained,
        abstention_reason=abstention_reason,
        elapsed_ms=elapsed_ms,
        evidence_refs_preserved=evidence_preserved,
    )
    return run.to_checkpoint_output(baseline_comparison)


# ---------------------------------------------------------------------------
# Calibration helpers
# ---------------------------------------------------------------------------


def platt_scale(scores: list[float], labels: list[int]) -> list[float]:
    """Platt scaling: fit a logistic regression on (score, label) pairs.

    Returns the calibrated probabilities. Used to convert raw model scores
    into calibrated confidence values. Requires labels (typically from a
    held-out set)."""
    if not scores or not labels or len(scores) != len(labels):
        return list(scores)
    from sklearn.linear_model import LogisticRegression
    import numpy as np
    X = np.array(scores).reshape(-1, 1)
    y = np.array(labels)
    if len(set(y.tolist())) < 2:
        return list(scores)  # can't fit
    lr = LogisticRegression(max_iter=1000)
    lr.fit(X, y)
    return [float(p[1]) for p in lr.predict_proba(X)]


def temperature_scale(scores: list[float], temperature: float = 1.0) -> list[float]:
    """Temperature scaling: divide logit by temperature. Requires scores in
    [0, 1]; we convert to logit, scale, and convert back."""
    import numpy as np
    if temperature <= 0:
        return list(scores)
    out: list[float] = []
    for s in scores:
        s = max(1e-6, min(1 - 1e-6, s))
        logit = np.log(s / (1 - s))
        scaled = logit / temperature
        out.append(float(1.0 / (1.0 + np.exp(-scaled))))
    return out


# ---------------------------------------------------------------------------
# Disagreement-based human routing
# ---------------------------------------------------------------------------


def should_route_to_human(checkpoint_outputs: list[CheckpointOutput], min_disagreement: int = 1) -> bool:
    """If two or more checkpoints disagree on the same input, route to human
    review. The spec: 'Use model disagreement to route difficult cases to
    human review.'"""
    n_abstained = sum(1 for c in checkpoint_outputs if c.abstention_rate > 0.5)
    n_disagreed = sum(1 for c in checkpoint_outputs if len(c.disagreement) > 0)
    return (n_abstained + n_disagreed) >= min_disagreement


# ---------------------------------------------------------------------------
# DO NOT average uncalibrated scores
# ---------------------------------------------------------------------------


def average_calibrated_only(outputs: list[CheckpointOutput], score_path: str = "typed_output.score") -> float | None:
    """Average scores ONLY across checkpoints whose calibration_status is not
    'uncalibrated'. Returns None (and emits a warning) if any uncalibrated
    checkpoint is in the list, because the spec forbids averaging
    uncalibrated model scores."""
    calibrated = [c for c in outputs if c.calibration_status != "uncalibrated"]
    if len(calibrated) < len(outputs):
        # Some are uncalibrated; do NOT average
        return None
    # Extract score from each
    scores: list[float] = []
    for c in calibrated:
        parts = score_path.split(".")
        v: Any = c  # start from the CheckpointOutput itself
        for p in parts:
            if isinstance(v, dict):
                v = v.get(p)
            else:
                v = getattr(v, p, None)
            if v is None:
                break
        if isinstance(v, (int, float)):
            scores.append(float(v))
    if not scores:
        return None
    return sum(scores) / len(scores)


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------


def registry_to_dict() -> dict:
    return {cid: spec.to_dict() for cid, spec in REGISTRY.items()}


def registry_to_json(path: str | Path) -> None:
    Path(path).write_text(json.dumps(registry_to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
