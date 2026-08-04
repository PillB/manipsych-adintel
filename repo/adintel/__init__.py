"""Advertisement Intelligence and Persuasion Analytics System.

A defensive, evidence-governed package that extends the existing ManiPsych
manipulation-detection pipeline with:

* a hierarchical multi-label technique taxonomy (v2);
* a 17-dimension persuasive-language profile;
* multi-space clustering with stability and leakage evaluation;
* authorship / common-source analysis (pairwise, closed-set, open-set, creative-source);
* outlier and novelty analysis (10 outlier types);
* a checkpoint registry with typed outputs, calibration, and abstention;
* a small JSON API surface for dashboard integration.

The package is deliberately local-first and CPU-friendly. It never names a
person from model similarity alone, never equates persuasion with performance,
and never collapses the 17 profile dimensions into an unexplained universal
score.
"""

from __future__ import annotations

__version__ = "adintel-0.1.0"

__all__ = [
    "types",
    "taxonomy",
    "profile",
    "clustering",
    "authorship",
    "outlier",
    "checkpoints",
    "api",
    "calibration",
]
