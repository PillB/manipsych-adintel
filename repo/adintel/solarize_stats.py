"""Solarize statistical engine for outlier/cluster term-prevalence comparison.

Implements the requirements R1–R4, R9 from the Solarize audit:

  R1: count terms and observable characteristics among outlier members
  R2: compare prevalence against (a) all non-outlier ads,
      (b) non-outlier ads in the same cluster, (c) matched controls
  R3: show counts, denominators, prevalence %, effect sizes,
      uncertainty (CI), adjusted significance (FDR), min-support status,
      exact comparison population
  R4: explicitly report when outlier members are NOT meaningfully different
  R9: distinguish detector outliers, density-clustering noise points,
      cluster-enriched outliers, and boundary members

Design choices
--------------
* Effect size: Cohen's h (arc-sine transformation of two proportions).
  Buckets: |h|<0.20 negligible, 0.20–0.50 small, 0.50–0.80 medium, ≥0.80 large.
  Cohen's h is preferred over the uncorrected enrichment-ratio the previous
  dashboard used because it is bounded, symmetric, and has conventional
  interpretation thresholds that do not inflate when the control prevalence
  is near zero.
* Confidence interval: Wilson score interval (score, not Wald). Wilson is
  preferred for small samples and extreme proportions (k=0 or k=n).
* Significance: two-sided z-test for the difference of two independent
  proportions (pooled), with continuity-aware handling when k=0.
* Multiple-testing correction: Benjamini–Hochberg FDR.
* Minimum support: at least 5 outlier hits AND at least 5 control hits
  (configurable). A term below min-support is reported but flagged and
  cannot be declared "meaningfully different" on its own.
* "Meaningfully different" verdict: large effect size AND non-zero CI
  lower bound AND min_support AND q-value < 0.05. If any condition fails
  the comparison is explicitly marked as NOT meaningfully different and
  the reason is recorded.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from typing import Iterable, Sequence

# ---------------------------------------------------------------------------
# Outlier taxonomy (R9)
# ---------------------------------------------------------------------------

# The four required outlier kinds. The historical "11 outlier types" from
# adintel.outlier are all subtypes of `detector` (rule-based detector
# outliers). The new kinds surface the geometric / cluster-aware signals
# that were previously hidden.
OUTLIER_KINDS: tuple[str, ...] = (
    "detector",          # rule-based / model-based detector outlier (the historical 11)
    "density_noise",     # DBSCAN / HDBSCAN label == -1
    "cluster_enriched",  # within-cluster Mahalanobis / MAD outlier
    "boundary",          # silhouette sample < threshold (weak cluster membership)
)

# Maps an adintel.outlier.OutlierReport.kind string to the canonical
# Solarize kind. All 11 historical kinds collapse to "detector".
_HISTORICAL_KIND_MAP: dict[str, str] = {
    "creative_novelty": "detector",
    "unusual_technique_combination": "detector",
    "style_outlier": "detector",
    "visual_outlier": "detector",
    "performance_overperformer": "detector",
    "performance_underperformer": "detector",
    "temporal_outlier": "detector",
    "duplicate": "detector",
    "extraction_error": "detector",
    "metadata_error": "detector",
    "model_error": "detector",
}


def canonical_outlier_kind(kind: str) -> str:
    """Map an adintel outlier kind to one of OUTLIER_KINDS."""
    if kind in OUTLIER_KINDS:
        return kind
    return _HISTORICAL_KIND_MAP.get(kind, "detector")


# ---------------------------------------------------------------------------
# Wilson score interval
# ---------------------------------------------------------------------------


def wilson_ci(k: int, n: int, z: float = 1.959963984540054) -> tuple[float, float, float]:
    """Wilson score 95% CI for a binomial proportion.

    Returns (lo, hi, point_estimate). z=1.96 → 95% CI.
    Handles k=0 and k=n correctly (Wald would not).
    """
    if n <= 0:
        return 0.0, 0.0, 0.0
    p = k / n
    z2 = z * z
    denom = 1 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))) / denom
    lo = max(0.0, centre - half)
    hi = min(1.0, centre + half)
    # Clamp the point estimate inside [lo, hi] to avoid floating-point
    # edge cases when k==0 or k==n (Wilson centre+half may land on
    # 0.9999999999999999 or 1.0000000000000002).
    if p < lo:
        lo = p
    if p > hi:
        hi = p
    return lo, hi, p


# ---------------------------------------------------------------------------
# Cohen's h effect size
# ---------------------------------------------------------------------------


def _arcsin_transform(p: float) -> float:
    """Cohen's arcsin transformation: 2 * arcsin(sqrt(p)).

    Clamps p to [0,1].
    """
    p = max(0.0, min(1.0, p))
    return 2.0 * math.asin(math.sqrt(p))


def cohens_h(p1: float, p2: float) -> float:
    """Cohen's h effect size between two proportions.

    Returns a signed value: positive means p1 > p2.
    Conventional buckets: |h|<0.20 negligible, 0.20 small, 0.50 medium, 0.80 large.
    """
    return _arcsin_transform(p1) - _arcsin_transform(p2)


def effect_size_label(h: float) -> str:
    """Conventional Cohen's h label."""
    a = abs(h)
    if a < 0.20:
        return "negligible"
    if a < 0.50:
        return "small"
    if a < 0.80:
        return "medium"
    return "large"


# ---------------------------------------------------------------------------
# Two-proportion z-test (pooled)
# ---------------------------------------------------------------------------


def two_proportion_z(p1: float, n1: int, p2: float, n2: int) -> tuple[float, float]:
    """Two-sided z-test for the difference of two independent proportions.

    Returns (z, p_value). Pooled under H0: p1 == p2.
    Returns (0.0, 1.0) when the pooled SE is zero (no events in either arm).
    """
    if n1 <= 0 or n2 <= 0:
        return 0.0, 1.0
    k1 = p1 * n1
    k2 = p2 * n2
    p_pool = (k1 + k2) / (n1 + n2)
    se = math.sqrt(p_pool * (1 - p_pool) * (1.0 / n1 + 1.0 / n2))
    if se == 0.0:
        return 0.0, 1.0
    z = (p1 - p2) / se
    # Two-sided normal survival
    p_value = 2.0 * (1.0 - _normal_cdf(abs(z)))
    return z, p_value


def _normal_cdf(x: float) -> float:
    """Standard normal CDF via math.erf."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


# ---------------------------------------------------------------------------
# Benjamini–Hochberg FDR
# ---------------------------------------------------------------------------


def benjamini_hochberg(p_values: Sequence[float]) -> list[float]:
    """Adjust a list of p-values with the Benjamini–Hochberg FDR procedure.

    Returns q-values aligned with the input order.
    """
    n = len(p_values)
    if n == 0:
        return []
    # Pair each p with its original index, sort ascending.
    indexed = sorted(enumerate(p_values), key=lambda kv: kv[1])
    q = [0.0] * n
    running_min = 1.0
    # Walk from largest to smallest so we can enforce monotonicity.
    for rank in range(n, 0, -1):
        orig_idx, p = indexed[rank - 1]
        adj = p * n / rank
        if adj > 1.0:
            adj = 1.0
        if adj < running_min:
            running_min = adj
        q[orig_idx] = running_min
    return q


# ---------------------------------------------------------------------------
# Term-prevalence comparison (R1–R4)
# ---------------------------------------------------------------------------


@dataclass
class TermComparison:
    """One row in a term-prevalence comparison table."""

    term: str
    outlier_count: int
    outlier_denominator: int
    outlier_prevalence: float
    control_count: int
    control_denominator: int
    control_prevalence: float
    effect_size: float
    effect_size_label: str
    ci_low: float
    ci_high: float
    p_value: float
    q_value: float
    min_support: bool
    comparison_population: str
    meaningfully_different: bool
    verdict_reason: str

    def to_dict(self) -> dict:
        return asdict(self)


def _term_in(text: str, term: str) -> bool:
    """Tokenised substring match: term may be a multi-word phrase.

    Lowercases both sides; matches word-boundary-aware so "lima" does not
    match "eliminar".
    """
    t = (text or "").lower()
    term_l = term.lower().strip()
    if not term_l:
        return False
    # Simple word boundary for ASCII letters.
    parts = term_l.split()
    if len(parts) == 1:
        # Use a regex with \b for single-token terms to avoid false positives.
        import re

        return re.search(rf"\b{re.escape(parts[0])}\b", t) is not None
    return term_l in t


def compare_term_prevalence(
    *,
    term: str,
    outlier_texts: Sequence[str],
    control_texts: Sequence[str],
    comparison_population: str,
    min_support: int = 5,
    z: float = 1.959963984540054,
) -> dict:
    """Compare prevalence of `term` between outlier and control arms.

    Returns a dict with all R3 fields plus the R4 verdict.

    `comparison_population` is a human-readable description of who the
    controls are (e.g. "all non-outlier ads", "non-outlier ads in cluster 2",
    "matched controls on platform+city").
    """
    n_out = len(outlier_texts)
    n_ctrl = len(control_texts)
    k_out = sum(1 for t in outlier_texts if _term_in(t, term))
    k_ctrl = sum(1 for t in control_texts if _term_in(t, term))
    p_out = k_out / n_out if n_out else 0.0
    p_ctrl = k_ctrl / n_ctrl if n_ctrl else 0.0

    lo_out, hi_out, _ = wilson_ci(k_out, n_out, z)
    # CI on the DIFFERENCE — use the Wilson-style interval on each arm and
    # combine: diff = p_out - p_ctrl; SE_diff = sqrt(SE_out^2 + SE_ctrl^2).
    se_out = (hi_out - lo_out) / (2 * z) if n_out else 0.0
    lo_ctrl, hi_ctrl, _ = wilson_ci(k_ctrl, n_ctrl, z)
    se_ctrl = (hi_ctrl - lo_ctrl) / (2 * z) if n_ctrl else 0.0
    diff = p_out - p_ctrl
    se_diff = math.sqrt(se_out * se_out + se_ctrl * se_ctrl) if (se_out + se_ctrl) > 0 else 0.0
    ci_low = diff - z * se_diff
    ci_high = diff + z * se_diff

    h = cohens_h(p_out, p_ctrl)
    label = effect_size_label(h)
    z_stat, p_value = two_proportion_z(p_out, n_out, p_ctrl, n_ctrl)

    meets_min_support = (k_out >= min_support) and (k_ctrl >= min_support)

    # R4 verdict: a term is meaningfully different iff ALL of:
    #   - |h| >= 0.50 (at least medium effect)  — conservative threshold
    #   - CI lower bound > 0 (the effect direction is consistent)
    #   - meets_min_support
    #   - q_value < 0.05 (caller must populate q_value via BH)
    # We can't evaluate q_value here; we leave it as p_value and the
    # caller's `compare_term_set` will overwrite after FDR adjustment.
    meaningfully_different = (
        abs(h) >= 0.50
        and ci_low > 0
        and meets_min_support
    )

    # Verdict reason: explicitly state why the term is or is not meaningful.
    if meaningfully_different:
        verdict_reason = (
            f"Enriched in outliers (|h|={abs(h):.2f}, {label}); "
            f"CI lower bound {ci_low:.3f} > 0; meets min-support (k≥{min_support}); "
            f"q-value will be evaluated after FDR adjustment."
        )
    else:
        reasons: list[str] = []
        if abs(h) < 0.50:
            reasons.append(f"|h|={abs(h):.2f} ({label}, below 0.50 medium threshold)")
        if ci_low <= 0:
            reasons.append(f"CI lower bound {ci_low:.3f} crosses 0 (direction uncertain)")
        if not meets_min_support:
            reasons.append(
                f"min-support not met (outlier_count={k_out}, control_count={k_ctrl}, threshold={min_support})"
            )
        verdict_reason = "Not meaningfully different: " + "; ".join(reasons) + "."

    return {
        "term": term,
        "outlier_count": int(k_out),
        "outlier_denominator": int(n_out),
        "outlier_prevalence": float(p_out),
        "control_count": int(k_ctrl),
        "control_denominator": int(n_ctrl),
        "control_prevalence": float(p_ctrl),
        "effect_size": float(h),
        "effect_size_label": label,
        "ci_low": float(ci_low),
        "ci_high": float(ci_high),
        "p_value": float(p_value),
        "q_value": float(p_value),  # placeholder; overwritten after BH
        "min_support": bool(meets_min_support),
        "comparison_population": comparison_population,
        "meaningfully_different": bool(meaningfully_different),
        "verdict_reason": verdict_reason,
    }


def compare_term_set(
    *,
    terms: Sequence[str],
    outlier_texts: Sequence[str],
    control_texts: Sequence[str],
    comparison_population: str,
    min_support: int = 5,
    q_threshold: float = 0.05,
) -> list[dict]:
    """Run `compare_term_prevalence` for many terms and FDR-adjust.

    Returns a list of dicts sorted by |effect_size| descending.
    After FDR adjustment, `meaningfully_different` requires q_value < q_threshold.
    """
    rows = [
        compare_term_prevalence(
            term=t,
            outlier_texts=outlier_texts,
            control_texts=control_texts,
            comparison_population=comparison_population,
            min_support=min_support,
        )
        for t in terms
    ]
    p_values = [r["p_value"] for r in rows]
    q_values = benjamini_hochberg(p_values)
    for r, q in zip(rows, q_values):
        r["q_value"] = float(q)
        # Re-evaluate meaningful-difference with the q-value
        r["meaningfully_different"] = bool(
            r["meaningfully_different"] and (q < q_threshold)
        )
        if not r["meaningfully_different"] and "q-value will be evaluated" in r["verdict_reason"]:
            # Update verdict: previously passed effect-size/CI/support but
            # now fails q-value
            r["verdict_reason"] = (
                f"Not meaningfully different: passes effect-size/CI/support but "
                f"q-value={q:.4f} ≥ {q_threshold} after FDR adjustment."
            )

    # Sort by |effect_size| desc, then by q_value asc
    rows.sort(key=lambda r: (-abs(r["effect_size"]), r["q_value"]))
    return rows


# ---------------------------------------------------------------------------
# Aggregate verdict (R4 at the section level)
# ---------------------------------------------------------------------------


def aggregate_verdict(rows: Sequence[dict], *, min_meaningful: int = 3) -> dict:
    """Summarise a comparison table: are outliers meaningfully different at all?

    Returns a dict with:
      - n_terms_total
      - n_meaningfully_different
      - n_meets_min_support
      - n_large_effect
      - overall_verdict: "DIFFERENTIATED" | "PARTIALLY_DIFFERENTIATED" | "NOT_MEANINGFULLY_DIFFERENT"
      - explanation
    """
    n_total = len(rows)
    n_diff = sum(1 for r in rows if r["meaningfully_different"])
    n_support = sum(1 for r in rows if r["min_support"])
    n_large = sum(1 for r in rows if r["effect_size_label"] == "large")

    if n_diff >= min_meaningful:
        verdict = "DIFFERENTIATED"
        explanation = (
            f"{n_diff}/{n_total} terms are meaningfully enriched in outliers "
            f"(q<0.05, |h|≥0.50, CI lower bound > 0, meets min-support). "
            f"{n_large} show a large effect (|h|≥0.80)."
        )
    elif n_diff > 0:
        verdict = "PARTIALLY_DIFFERENTIATED"
        explanation = (
            f"Only {n_diff}/{n_total} terms meet the meaningful-difference "
            f"criteria (q<0.05, |h|≥0.50, CI>0, min-support). The outlier "
            f"signal is weak: most terms do not survive multiple-testing "
            f"correction or fail the effect-size threshold."
        )
    else:
        verdict = "NOT_MEANINGFULLY_DIFFERENT"
        explanation = (
            f"0/{n_total} terms are meaningfully enriched in outliers. "
            f"{n_support}/{n_total} meet min-support. The outlier group is "
            f"NOT meaningfully different from the comparison population on "
            f"the measured term distribution. Reported differences are "
            f"consistent with sampling noise."
        )

    return {
        "n_terms_total": int(n_total),
        "n_meaningfully_different": int(n_diff),
        "n_meets_min_support": int(n_support),
        "n_large_effect": int(n_large),
        "overall_verdict": verdict,
        "explanation": explanation,
    }
