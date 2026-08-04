"""Typed outputs for the adintel package.

Every checkpoint returns a typed dataclass (or its `to_dict` form) so that
schemas, tests, and the dashboard can rely on a stable contract. These types
are intentionally explicit about uncertainty, evidence references, and
human-review status — the existing ManiPsych outputs were untyped dicts and
that made downstream validation brittle.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


# ---------------------------------------------------------------------------
# Shared enums
# ---------------------------------------------------------------------------

Modality = Literal["text", "image", "audio", "video", "metadata", "multimodal"]
ReviewStatus = Literal["unreviewed", "reviewed", "adjudicated", "disputed"]
EvidenceKind = Literal["text_span", "image_region", "timestamp", "metadata_field"]
ClaimStrength = Literal["descriptive", "associative", "predictive", "quasi_causal", "causal"]


# ---------------------------------------------------------------------------
# Taxonomy / technique prediction
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvidenceRef:
    """A reference to the exact slice of the ad that supports a prediction."""

    kind: EvidenceKind
    modality: Modality
    # Text span: zero-based, end-exclusive Unicode code points (matches the
    # manipsych-span-v1 offset convention).
    start: int | None = None
    end: int | None = None
    # For image region: bounding box in [x_min, y_min, x_max, y_max] normalised 0..1.
    bbox: tuple[float, float, float, float] | None = None
    # For video/audio: seconds offset.
    timestamp_s: float | None = None
    # The surface string that was matched (for text spans). Useful for audit.
    surface: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.bbox is None:
            d.pop("bbox", None)
        return d


@dataclass(frozen=True)
class TechniquePrediction:
    """A single predicted technique label with full provenance.

    Required fields (per spec): label, confidence, supporting evidence,
    modality, checkpoint outputs, agreement, uncertainty, taxonomy version,
    human-review status.
    """

    label: str
    confidence: float  # 0.0 .. 1.0, post-calibration when available
    evidence: list[EvidenceRef]
    modality: Modality
    taxonomy_version: str
    checkpoint_id: str
    # Per-checkpoint raw scores: checkpoint_id -> {score, calibrated, abstained}
    checkpoint_outputs: dict[str, dict[str, Any]]
    agreement: float  # fraction of agreeing checkpoints, 0.0..1.0
    disagreement: list[str]  # checkpoint_ids that disagreed
    uncertainty: float  # 0.0..1.0, complement of confidence after disagreement
    review_status: ReviewStatus = "unreviewed"
    parent_label: str | None = None  # hierarchical taxonomy parent
    rationale: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["evidence"] = [e.to_dict() if hasattr(e, "to_dict") else e for e in self.evidence]
        return d


# ---------------------------------------------------------------------------
# Persuasive profile
# ---------------------------------------------------------------------------

# The 17 required dimensions, in the spec's order. The order matters for
# dashboard rendering and is part of the public contract.
PROFILE_DIMENSIONS: tuple[str, ...] = (
    "urgency",
    "scarcity",
    "emotional_intensity",
    "directiveness",
    "certainty",
    "specificity",
    "benefit_density",
    "evidence_density",
    "social_proof",
    "objection_handling",
    "risk_reversal",
    "claim_extremity",
    "readability",
    "offer_clarity",
    "action_clarity",
    "trust_risk",
    "manipulation_risk",
)


@dataclass(frozen=True)
class ProfileScore:
    """One persuasive-profile dimension score for one ad."""

    dimension: str
    score: float  # 0.0 .. 1.0
    raw_score: float  # pre-normalisation signal count or intensity
    signals: list[str]  # human-readable signal inventory
    supporting_evidence: list[EvidenceRef]
    abstained: bool  # True when there is insufficient signal to score
    abstention_reason: str | None = None
    confidence: float = 0.5  # post-calibration confidence in the score itself

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["supporting_evidence"] = [e.to_dict() for e in self.supporting_evidence]
        return d


@dataclass(frozen=True)
class PersuasiveProfile:
    """Full 17-dimension profile for one ad."""

    record_id: str
    taxonomy_version: str
    checkpoint_id: str
    dimensions: dict[str, ProfileScore]
    # The composite is intentionally NOT a single manipulation score; it is a
    # transparency summary that always carries the per-dimension breakdown.
    composite_summary: dict[str, float] = field(default_factory=dict)
    review_status: ReviewStatus = "unreviewed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "output_version": "persuasive-profile-v1.0.0",
            "record_id": self.record_id,
            "taxonomy_version": self.taxonomy_version,
            "checkpoint_id": self.checkpoint_id,
            "dimensions": {k: v.to_dict() for k, v in self.dimensions.items()},
            "composite_summary": self.composite_summary,
            "review_status": self.review_status,
            "dimensions_present": len(self.dimensions),
            "dimensions_abstained": sum(1 for v in self.dimensions.values() if v.abstained),
        }


# ---------------------------------------------------------------------------
# Clustering
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClusterAssignment:
    record_id: str
    cluster_id: int
    space: str  # persuasive | semantic | rhetorical | visual | multimodal | authorial | performance
    is_noise: bool = False  # HDBSCAN/DBSCAN noise flag
    silhouette: float | None = None
    distance_to_centroid: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ClusterReport:
    space: str
    n_clusters: int
    n_noise: int
    stability_ari: float  # mean ARI over resamples
    resampling_consistency: float  # fraction of pairs that stay together
    parameter_sensitivity: float  # std of n_clusters across parameter grid
    brand_leakage: dict[str, float]  # brand -> fraction of cluster dominated by it
    topic_leakage: dict[str, float]
    representative_ids: list[str]
    boundary_ids: list[str]
    cluster_explanations: list[dict[str, Any]]
    human_coherence_note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["output_version"] = "cluster-report-v1.0.0"
        return d


# ---------------------------------------------------------------------------
# Authorship / common-source
# ---------------------------------------------------------------------------

AuthorshipVerdict = Literal[
    "same_source",
    "different_source",
    "unknown_in_open_set",
    "insufficient_evidence",
]


@dataclass(frozen=True)
class AuthorshipResult:
    task: Literal["pairwise_verification", "closed_set_attribution", "open_set_attribution", "creative_source_clustering"]
    verdict: AuthorshipVerdict
    confidence: float
    # Multi-signal scores, each in 0..1
    stylometry_score: float | None = None
    lexical_richness_score: float | None = None
    template_signature_score: float | None = None
    structural_signature_score: float | None = None
    council_label_overlap: float | None = None
    # Robustness: did the verdict survive each invariance test?
    survived: dict[str, bool] = field(default_factory=dict)
    # Length-aware abstention
    left_token_count: int | None = None
    right_token_count: int | None = None
    abstention_reason: str | None = None
    # Privacy guardrail
    person_named: bool = False  # always False — we never name a person
    review_status: ReviewStatus = "unreviewed"
    checkpoint_id: str = "authorship-v1"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["output_version"] = "authorship-v1.0.0"
        return d


# ---------------------------------------------------------------------------
# Outlier analysis
# ---------------------------------------------------------------------------

OutlierKind = Literal[
    "creative_novelty",
    "unusual_technique_combination",
    "style_outlier",
    "visual_outlier",
    "performance_overperformer",
    "performance_underperformer",
    "temporal_outlier",
    "duplicate",
    "extraction_error",
    "metadata_error",
    "model_error",
]


@dataclass(frozen=True)
class OutlierReport:
    record_id: str
    kind: OutlierKind
    score: float  # 0..1, larger = more outlying
    method: str  # e.g. "isolation_forest", "z_score", "exact_hash"
    comparison_population: str  # e.g. "all doplim ads", "training split"
    feature_space: str  # e.g. "persuasive_profile", "char5_jaccard"
    supporting_features: dict[str, float]
    alternative_explanation: str | None  # always populated
    uncertainty: float  # 0..1
    review_status: ReviewStatus = "unreviewed"
    checkpoint_id: str = "outlier-v1"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["output_version"] = "outlier-v1.0.0"
        return d


# ---------------------------------------------------------------------------
# Checkpoint registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CheckpointOutput:
    checkpoint_id: str
    version: str
    config: dict[str, Any]
    typed_output: dict[str, Any]  # serialised dataclass from above
    held_out_metrics: dict[str, float]
    calibration_status: Literal["uncalibrated", "platt", "isotonic", "temperature"]
    baseline_comparison: dict[str, float]  # checkpoint_id -> delta
    disagreement: list[str]  # other checkpoint_ids that disagreed
    cost_usd_per_1k: float | None = None
    latency_ms_p50: float | None = None
    abstention_rate: float = 0.0
    abstention_conditions: list[str] = field(default_factory=list)
    evidence_refs_preserved: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Performance claim
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PerformanceClaim:
    """A disciplined performance statement.

    `strength` follows the spec's ladder:
    descriptive < associative < predictive < quasi_causal < causal.
    """

    record_id: str | None
    population: str
    claim: str
    strength: ClaimStrength
    controls: list[str]  # which context fields were controlled/stratified
    missing_controls: list[str]  # which material controls were unavailable
    uncertainty: float
    recommendation: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
