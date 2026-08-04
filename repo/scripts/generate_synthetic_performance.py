#!/usr/bin/env python3
"""Item 3: Generate a realistic synthetic performance dataset from researched benchmarks.

The corpus has NO real performance metrics (no CTR, conversion, spend). This
script constructs a defensible synthetic dataset using:
  - Peru-specific Meta benchmarks (Adamigo 2026): CTR 1.29%, CPC $0.36, CPM $3.70
  - LatAm Finance benchmarks (Emplifi Q2 2026)
  - Peru seasonality (CréditoLab 2026): peaks in May/Jul/Nov/Dec
  - Attribution windows: 7-day click (conservative) vs 7-day+1-day view (Meta default)

Every value is sampled from a researched distribution and tagged with its
source. The dataset is explicitly marked SYNTHETIC so it is never confused
with real observed performance.
"""

from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path
from datetime import datetime, timedelta

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BENCHMARKS = ROOT / "reports" / "adintel" / "performance_benchmarks.json"
OUT = ROOT / "data" / "processed" / "synthetic_performance.jsonl"


def load_benchmarks() -> dict:
    if not BENCHMARKS.exists():
        return {}
    return json.loads(BENCHMARKS.read_text())


# Platform-specific parameters (from benchmarks research)
PLATFORM_PARAMS = {
    "doplim": {"ctr_median": 0.0072, "ctr_std": 0.003, "cpc_median": 0.08, "cpc_std": 0.02,
               "spend_range": (20, 250), "frequency_median": 2.5, "source": "derived from display CTR + Peru Meta"},
    "locanto": {"ctr_median": 0.0085, "ctr_std": 0.004, "cpc_median": 0.10, "cpc_std": 0.03,
                "spend_range": (25, 300), "frequency_median": 2.8, "source": "derived from display CTR + Peru Meta"},
    "ciudadanuncios": {"ctr_median": 0.0055, "ctr_std": 0.002, "cpc_median": 0.05, "cpc_std": 0.015,
                       "spend_range": (10, 120), "frequency_median": 2.0, "source": "derived from display CTR + Peru Meta"},
    "facebook": {"ctr_median": 0.0129, "ctr_std": 0.006, "cpc_median": 0.36, "cpc_std": 0.08,
                 "spend_range": (100, 2000), "frequency_median": 4.5, "source": "Peru Meta (Adamigo 2026)"},
    "evisos": {"ctr_median": 0.0068, "ctr_std": 0.003, "cpc_median": 0.07, "cpc_std": 0.02,
               "spend_range": (15, 180), "frequency_median": 2.2, "source": "derived from display CTR + Peru Meta"},
}

# Peru seasonality multipliers (CréditoLab 2026)
SEASONALITY = {
    1: 1.15, 2: 0.85, 3: 0.80, 4: 1.10, 5: 1.20, 6: 0.95,
    7: 1.35, 8: 0.85, 9: 0.80, 10: 1.05, 11: 1.25, 12: 1.40,
}

# Conversion rate benchmarks (Finance & Insurance, WordStream 2025)
CVR_SEARCH = 0.0255  # 2.55%
CVR_DISPLAY = 0.0072  # 0.72%
CVR_FACEBOOK = 0.0098  # 0.98%


def generate_performance_record(record: dict, rng: random.Random, idx: int) -> dict:
    """Generate a synthetic performance record for one ad."""
    meta = record.get("metadata", {}) if isinstance(record, dict) else {}
    platform = str(meta.get("platform_family", record.get("source_platform", "unknown"))).lower()
    params = PLATFORM_PARAMS.get(platform, PLATFORM_PARAMS["doplim"])

    # Parse collection date for seasonality
    collected = record.get("collected_at", "2026-07-01T00:00:00Z")
    try:
        dt = datetime.fromisoformat(collected.replace("Z", "+00:00"))
        month = dt.month
    except Exception:
        month = rng.randint(1, 12)

    season_mult = SEASONALITY.get(month, 1.0)

    # Impressions: based on spend and CPM
    spend = rng.uniform(*params["spend_range"]) * season_mult
    cpm = params["cpc_median"] / max(params["ctr_median"], 0.001) * 1000
    impressions = int(spend / max(cpm, 0.01) * 1000)
    impressions = max(100, impressions)

    # CTR: lognormal around median, scaled by ad quality (proxy: manipulation_risk)
    quality_score = float(meta.get("quality_score", 0.5))
    ctr_base = rng.lognormvariate(math.log(params["ctr_median"]), 0.3)
    ctr = min(0.15, max(0.001, ctr_base * (0.5 + quality_score)))

    # Clicks
    clicks = int(impressions * ctr)

    # Frequency
    frequency = max(1.0, rng.gauss(params["frequency_median"], 0.8))

    # CPC
    cpc = max(0.01, rng.gauss(params["cpc_median"], params["cpc_std"]))

    # Conversion rate (depends on platform type)
    if platform == "facebook":
        cvr = CVR_FACEBOOK * (0.5 + quality_score)
    else:
        cvr = CVR_DISPLAY * (0.5 + quality_score)
    cvr = min(0.20, max(0.001, cvr))

    # Conversions — use fractional model so low-click ads still get fractional conversions
    # (in reality, conversions are tracked at the campaign level, not per-ad)
    conversions_exact = clicks * cvr
    conversions = int(conversions_exact)
    # Stochastic rounding so fractional conversions are represented
    if rng.random() < (conversions_exact - conversions):
        conversions += 1

    # Attribution window: 7-day click (conservative) vs 7-day+1-day view (Meta default)
    view_through_inflation = 1.0
    if platform == "facebook":
        # Meta default includes 1-day view; ~60-70% inflation
        view_through_inflation = rng.uniform(1.4, 1.7)
    conversions_with_view = int(conversions * view_through_inflation)

    # CPM
    cpm_actual = (spend / max(impressions, 1)) * 1000

    return {
        "record_id": record.get("record_id"),
        "platform": platform,
        "month": month,
        "seasonality_multiplier": round(season_mult, 2),
        "impressions": impressions,
        "clicks": clicks,
        "ctr": round(ctr, 6),
        "cpc": round(cpc, 4),
        "cpm": round(cpm_actual, 4),
        "spend": round(spend, 2),
        "frequency": round(frequency, 2),
        "conversions_7day_click": conversions,
        "conversions_7day_click_1day_view": conversions_with_view,
        "cvr": round(cvr, 6),
        "attribution_window": "7d_click" if platform != "facebook" else "7d_click_1d_view",
        "quality_score": quality_score,
        "synthetic": True,
        "source": params["source"],
        "generated_at": "2026-08-04T20:30:00Z",
    }


def main() -> int:
    rng = random.Random(42)
    manifest = ROOT / "data" / "processed" / "ad_manifest.jsonl"
    if not manifest.exists():
        print("ERROR: manifest not found")
        return 1

    records = []
    with open(manifest) as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))

    print(f"Generating synthetic performance for {len(records)} ads...")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w") as f:
        for i, record in enumerate(records):
            perf = generate_performance_record(record, rng, i)
            f.write(json.dumps(perf, ensure_ascii=False) + "\n")

    # Summary stats
    total_impressions = 0
    total_clicks = 0
    total_spend = 0
    total_conversions = 0
    by_platform = {}
    with open(OUT) as f:
        for line in f:
            d = json.loads(line)
            total_impressions += d["impressions"]
            total_clicks += d["clicks"]
            total_spend += d["spend"]
            total_conversions += d["conversions_7day_click"]
            p = d["platform"]
            by_platform.setdefault(p, {"n": 0, "impressions": 0, "clicks": 0, "spend": 0})
            by_platform[p]["n"] += 1
            by_platform[p]["impressions"] += d["impressions"]
            by_platform[p]["clicks"] += d["clicks"]
            by_platform[p]["spend"] += d["spend"]

    print(f"\nSynthetic performance dataset:")
    print(f"  Total ads: {len(records)}")
    print(f"  Total impressions: {total_impressions:,}")
    print(f"  Total clicks: {total_clicks:,}")
    print(f"  Overall CTR: {total_clicks/total_impressions:.4f} ({total_clicks/total_impressions*100:.2f}%)")
    print(f"  Total spend: ${total_spend:,.2f}")
    print(f"  Total conversions (7d click): {total_conversions:,}")
    print(f"  Overall CVR: {total_conversions/total_clicks:.4f} ({total_conversions/total_clicks*100:.2f}%)")
    print(f"\nBy platform:")
    for p, s in sorted(by_platform.items()):
        ctr = s["clicks"] / max(s["impressions"], 1)
        print(f"  {p:20s}: n={s['n']:5d}  imp={s['impressions']:>10,}  clicks={s['clicks']:>7,}  ctr={ctr:.4f}  spend=${s['spend']:>10,.2f}")

    print(f"\nOutput: {OUT}")
    print("NOTE: This is SYNTHETIC data based on researched benchmarks. Do NOT treat as real observed performance.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
