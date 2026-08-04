"""Evidence-discipline helpers.

The spec says: 'Do not treat technique presence as proof of persuasion;
persuasive intensity as proof of performance; performance association as
proof of causation; authorship similarity as proof of personal identity.'

This module provides:
  - lint_claim_text(text) — scan a claim for causal verbs without a strength
    qualifier and return warnings.
  - require_strength(claim) — assert that a PerformanceClaim has a strength
    field, raise if missing.
  - forbidden_universal_score(profile) — assert that a PersuasiveProfile does
    not collapse the 17 dimensions into a single 'overall' score.
  - human_review_routing(checkpoint_outputs) — re-export of the
    checkpoints.should_route_to_human helper for convenience.
"""

from __future__ import annotations

import re
from typing import Iterable

from adintel.types import ClaimStrength, PerformanceClaim, PersuasiveProfile


# ---------------------------------------------------------------------------
# Causal language linting
# ---------------------------------------------------------------------------

# Verbs that imply causation. If they appear in a claim without an explicit
# strength qualifier (descriptive / associative / predictive / quasi_causal /
# causal), the lint should flag the claim.
CAUSAL_VERBS = (
    "causes", "caused", "cause",
    "improves", "improved", "improve",
    "drives", "drove", "drive",
    "boosts", "boosted", "boost",
    "reduces", "reduced", "reduce",
    "increases", "increased", "increase",
    "decreases", "decreased", "decrease",
    "produces", "produced", "produce",
    "generates", "generated", "generate",
    "creates", "created", "create",
    "leads to", "led to",
    "results in", "resulted in",
)

# Strength qualifiers (must appear within 80 chars of a causal verb to satisfy
# the lint).
STRENGTH_QUALIFIERS = (
    "descriptive",
    "associative",
    "predictive",
    "quasi-causal", "quasi_causal", "quasi causal",
    "causal",
    "correlation", "correlates",
    "associated with",
    "may", "might", "could",
    "appears to",
    "in this sample", "in our sample",
    "is not proof of", "does not prove",
)


def lint_claim_text(text: str) -> list[dict]:
    """Return a list of warnings for each causal verb that lacks a nearby
    strength qualifier.

    Each warning has: verb, position, suggestion.
    """
    warnings: list[dict] = []
    text_lower = text.lower()
    for verb in CAUSAL_VERBS:
        for m in re.finditer(re.escape(verb), text_lower):
            # Look within 80 chars before and after for a qualifier
            start = max(0, m.start() - 80)
            end = min(len(text_lower), m.end() + 80)
            window = text_lower[start:end]
            has_qualifier = any(q in window for q in STRENGTH_QUALIFIERS)
            if not has_qualifier:
                warnings.append({
                    "verb": verb,
                    "position": m.start(),
                    "window": text[max(0, m.start() - 40):m.end() + 40],
                    "suggestion": f"Add a strength qualifier near '{verb}' (e.g. 'is associated with', 'may', 'correlates with', 'descriptive', 'quasi-causal').",
                })
    return warnings


def require_strength(claim: PerformanceClaim) -> None:
    """Assert that the claim has a non-empty strength field. Raises ValueError
    if missing."""
    if not claim.strength:
        raise ValueError("PerformanceClaim.strength is required; cannot be empty.")
    valid: tuple[ClaimStrength, ...] = ("descriptive", "associative", "predictive", "quasi_causal", "causal")
    if claim.strength not in valid:
        raise ValueError(f"PerformanceClaim.strength must be one of {valid}, got: {claim.strength}")


# ---------------------------------------------------------------------------
# Universal-score guard
# ---------------------------------------------------------------------------

FORBIDDEN_COMPOSITE_KEYS = ("overall", "universal", "total_score", "composite_score", "single_score")


def assert_no_universal_score(profile: PersuasiveProfile) -> None:
    """Assert that the profile's composite_summary does not collapse the 17
    dimensions into a single universal score. The spec is explicit on this
    point."""
    for forbidden in FORBIDDEN_COMPOSITE_KEYS:
        if forbidden in profile.composite_summary:
            raise AssertionError(
                f"PRIVACY/DISCLOSURE GUARDRAIL: PersuasiveProfile.composite_summary "
                f"contains forbidden key '{forbidden}'. The spec forbids collapsing "
                f"the 17 dimensions into an unexplained universal score."
            )


# ---------------------------------------------------------------------------
# Authorship identity guard
# ---------------------------------------------------------------------------

def assert_authorship_does_not_identify_person(result_dict: dict) -> None:
    """Assert that an authorship result dict does not name a person.

    This is a redundant guard: adintel.authorship always sets person_named=False.
    But the spec says this is the highest-priority guardrail, so we add an
    independent check at the API boundary too.
    """
    if result_dict.get("person_named", False):
        raise AssertionError(
            "PRIVACY GUARDRAIL VIOLATION: authorship result has person_named=True. "
            "Model similarity is never sufficient to identify a person."
        )
    # Also check no string field looks like a person name heuristic
    # (very conservative: just check no 'name' field is populated)
    for k, v in result_dict.items():
        if "person_name" in k.lower() and v:
            raise AssertionError(f"PRIVACY GUARDRAIL: field '{k}' is populated: {v!r}")


# ---------------------------------------------------------------------------
# Convenience: route to human review
# ---------------------------------------------------------------------------


def route_to_human_if_low_confidence_or_disagreement(
    confidence: float,
    disagreement: list[str],
    confidence_floor: float = 0.4,
    disagreement_threshold: int = 1,
) -> bool:
    """Per spec: 'Use model disagreement to route difficult cases to human
    review.'"""
    return confidence < confidence_floor or len(disagreement) >= disagreement_threshold
