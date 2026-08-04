"""JSON API surface for dashboard integration.

The spec calls for stable API schemas, migrations, latency, cost, and
monitoring. We expose a single `AdIntelAPI` class with typed request/response
methods. The dashboard can call these methods directly (in-process) or wrap
them in a Flask/FastAPI handler.

Every response includes:
  - request_id (deterministic from inputs)
  - checkpoint_id
  - typed_output (from adintel.types)
  - held_out_metrics (from the checkpoint registry)
  - calibration_status
  - cost_usd_per_1k
  - latency_ms
  - abstention (bool + reason)
  - review_status

This contract is the migration boundary: future versions may add fields but
must not remove or rename existing ones without a version bump.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any

from adintel import authorship as au
from adintel import checkpoints as cp
from adintel import clustering as cl
from adintel import outlier as ot
from adintel import profile as pf
from adintel import taxonomy as tx
from adintel.types import (
    AuthorshipResult,
    ClusterAssignment,
    ClusterReport,
    OutlierReport,
    PersuasiveProfile,
    TechniquePrediction,
)


API_VERSION = "adintel-api-v1"


def _request_id(*parts: Any) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(str(p).encode("utf-8", errors="replace"))
        h.update(b"|")
    return h.hexdigest()[:32]


# ---------------------------------------------------------------------------
# Request / response dataclasses
# ---------------------------------------------------------------------------


@dataclass
class APIResponse:
    request_id: str
    api_version: str
    checkpoint_id: str
    typed_output: dict[str, Any]
    held_out_metrics: dict[str, float]
    calibration_status: str
    cost_usd_per_1k: float
    latency_ms: float
    abstained: bool
    abstention_reason: str | None
    review_status: str
    evidence_refs_preserved: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "api_version": self.api_version,
            "checkpoint_id": self.checkpoint_id,
            "typed_output": self.typed_output,
            "held_out_metrics": self.held_out_metrics,
            "calibration_status": self.calibration_status,
            "cost_usd_per_1k": self.cost_usd_per_1k,
            "latency_ms": round(self.latency_ms, 3),
            "abstained": self.abstained,
            "abstention_reason": self.abstention_reason,
            "review_status": self.review_status,
            "evidence_refs_preserved": self.evidence_refs_preserved,
        }


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


class AdIntelAPI:
    """In-process API. Wrap in Flask/FastAPI for HTTP serving."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []  # monitoring log

    # -- taxonomy ------------------------------------------------------

    def get_taxonomy(self) -> APIResponse:
        t0 = time.perf_counter()
        typed = tx.to_dict()
        elapsed = (time.perf_counter() - t0) * 1000
        spec = cp.get_spec("rule-detector-v1")  # taxonomy shares the rule-detector baseline
        resp = APIResponse(
            request_id=_request_id("taxonomy", tx.TAXONOMY_VERSION),
            api_version=API_VERSION,
            checkpoint_id="taxonomy",
            typed_output=typed,
            held_out_metrics={},
            calibration_status="n/a",
            cost_usd_per_1k=0.0,
            latency_ms=elapsed,
            abstained=False,
            abstention_reason=None,
            review_status="unreviewed",
            evidence_refs_preserved=True,
        )
        self.calls.append({"endpoint": "get_taxonomy", "latency_ms": elapsed})
        return resp

    # -- persuasive profile --------------------------------------------

    def score_profile(self, text: str, record_id: str = "unknown") -> APIResponse:
        t0 = time.perf_counter()
        if not text or len(text.strip()) < 3:
            elapsed = (time.perf_counter() - t0) * 1000
            spec = cp.get_spec("persuasive-profile-v1")
            return APIResponse(
                request_id=_request_id("profile", record_id),
                api_version=API_VERSION,
                checkpoint_id="persuasive-profile-v1",
                typed_output={"record_id": record_id, "abstained": True},
                held_out_metrics={},
                calibration_status=spec.calibration_status,
                cost_usd_per_1k=spec.cost_usd_per_1k,
                latency_ms=elapsed,
                abstained=True,
                abstention_reason="empty_text",
                review_status="unreviewed",
                evidence_refs_preserved=False,
            )
        p = pf.score_profile(text, record_id=record_id)
        elapsed = (time.perf_counter() - t0) * 1000
        spec = cp.get_spec("persuasive-profile-v1")
        resp = APIResponse(
            request_id=_request_id("profile", record_id, text),
            api_version=API_VERSION,
            checkpoint_id="persuasive-profile-v1",
            typed_output=p.to_dict(),
            held_out_metrics={},
            calibration_status=spec.calibration_status,
            cost_usd_per_1k=spec.cost_usd_per_1k,
            latency_ms=elapsed,
            abstained=False,
            abstention_reason=None,
            review_status="unreviewed",
            evidence_refs_preserved=True,
        )
        self.calls.append({"endpoint": "score_profile", "latency_ms": elapsed, "record_id": record_id})
        return resp

    # -- authorship ----------------------------------------------------

    def pairwise_verify(self, left: str, right: str, left_labels: list[str] | None = None, right_labels: list[str] | None = None) -> APIResponse:
        t0 = time.perf_counter()
        result = au.pairwise_verify(left, right, left_labels or [], right_labels or [])
        elapsed = (time.perf_counter() - t0) * 1000
        spec = cp.get_spec("authorship-v1")
        resp = APIResponse(
            request_id=_request_id("pairwise", left[:32], right[:32]),
            api_version=API_VERSION,
            checkpoint_id="authorship-v1",
            typed_output=result.to_dict(),
            held_out_metrics={},
            calibration_status=spec.calibration_status,
            cost_usd_per_1k=spec.cost_usd_per_1k,
            latency_ms=elapsed,
            abstained=(result.verdict == "insufficient_evidence"),
            abstention_reason=result.abstention_reason,
            review_status=result.review_status,
            evidence_refs_preserved=True,
        )
        self.calls.append({"endpoint": "pairwise_verify", "latency_ms": elapsed, "verdict": result.verdict})
        return resp

    def open_set_attrib(self, query: str, candidates: dict[str, str]) -> APIResponse:
        t0 = time.perf_counter()
        result = au.open_set_attrib(query, candidates)
        elapsed = (time.perf_counter() - t0) * 1000
        spec = cp.get_spec("authorship-v1")
        resp = APIResponse(
            request_id=_request_id("open_set", query[:32]),
            api_version=API_VERSION,
            checkpoint_id="authorship-v1",
            typed_output=result.to_dict(),
            held_out_metrics={},
            calibration_status=spec.calibration_status,
            cost_usd_per_1k=spec.cost_usd_per_1k,
            latency_ms=elapsed,
            abstained=(result.verdict == "insufficient_evidence"),
            abstention_reason=result.abstention_reason,
            review_status=result.review_status,
            evidence_refs_preserved=True,
        )
        self.calls.append({"endpoint": "open_set_attrib", "latency_ms": elapsed, "verdict": result.verdict})
        return resp

    # -- clustering ----------------------------------------------------

    def cluster_all_spaces(self, records: list[dict], texts: list[str], profiles: list[dict] | None = None, k: int = 6) -> APIResponse:
        t0 = time.perf_counter()
        results = cl.cluster_all_spaces(records, texts, profiles=profiles, k=k, compute_stability=True)
        typed: dict[str, Any] = {}
        for space, (assignments, report) in results.items():
            typed[space] = {
                "assignments": [a.to_dict() for a in assignments],
                "report": report.to_dict(),
            }
        elapsed = (time.perf_counter() - t0) * 1000
        spec = cp.get_spec("clustering-v1")
        resp = APIResponse(
            request_id=_request_id("cluster", len(records), k),
            api_version=API_VERSION,
            checkpoint_id="clustering-v1",
            typed_output=typed,
            held_out_metrics={},
            calibration_status=spec.calibration_status,
            cost_usd_per_1k=spec.cost_usd_per_1k,
            latency_ms=elapsed,
            abstained=False,
            abstention_reason=None,
            review_status="unreviewed",
            evidence_refs_preserved=True,
        )
        self.calls.append({"endpoint": "cluster_all_spaces", "latency_ms": elapsed, "n_records": len(records)})
        return resp

    # -- outliers ------------------------------------------------------

    def detect_outliers(self, texts: list[str], records: list[dict], label_sets: list[set[str]] | None = None, predictions: list[dict] | None = None) -> APIResponse:
        t0 = time.perf_counter()
        reports = ot.detect_all_outliers(texts, records, label_sets=label_sets, predictions=predictions)
        elapsed = (time.perf_counter() - t0) * 1000
        spec = cp.get_spec("outlier-v1")
        typed = {
            "n_reports": len(reports),
            "by_kind": {},
            "reports": [r.to_dict() for r in reports],
        }
        for r in reports:
            typed["by_kind"][r.kind] = typed["by_kind"].get(r.kind, 0) + 1
        resp = APIResponse(
            request_id=_request_id("outliers", len(records)),
            api_version=API_VERSION,
            checkpoint_id="outlier-v1",
            typed_output=typed,
            held_out_metrics={},
            calibration_status=spec.calibration_status,
            cost_usd_per_1k=spec.cost_usd_per_1k,
            latency_ms=elapsed,
            abstained=False,
            abstention_reason=None,
            review_status="unreviewed",
            evidence_refs_preserved=True,
        )
        self.calls.append({"endpoint": "detect_outliers", "latency_ms": elapsed, "n_reports": len(reports)})
        return resp

    # -- monitoring ----------------------------------------------------

    def monitoring_summary(self) -> dict[str, Any]:
        n_calls = len(self.calls)
        if not n_calls:
            return {"n_calls": 0}
        by_endpoint: dict[str, int] = {}
        latencies: list[float] = []
        for c in self.calls:
            by_endpoint[c["endpoint"]] = by_endpoint.get(c["endpoint"], 0) + 1
            if "latency_ms" in c:
                latencies.append(c["latency_ms"])
        return {
            "n_calls": n_calls,
            "by_endpoint": by_endpoint,
            "p50_latency_ms": float(sorted(latencies)[len(latencies) // 2]) if latencies else 0.0,
            "p95_latency_ms": float(sorted(latencies)[int(len(latencies) * 0.95)]) if latencies else 0.0,
        }
