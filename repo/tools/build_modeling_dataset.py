#!/usr/bin/env python3
"""Build a modeling-ready subset of ad_manifest.jsonl.

Filters weak/noisy processed records for TF-IDF OvR training and learning curves:
  - Prefer male-offer language (brindo/doy/ofrezco + ayuda/apoyo)
  - Drop residual offtopic / seeker-only when still present
  - Keep platform tags for stratified analysis

Writes:
  data/processed/modeling_manifest.jsonl
  reports/modeling_dataset_summary.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_IN = ROOT / "data" / "processed" / "ad_manifest.jsonl"
DEFAULT_OUT = ROOT / "data" / "processed" / "modeling_manifest.jsonl"
DEFAULT_SUMMARY = ROOT / "reports" / "modeling_dataset_summary.json"

OFFER_RE = re.compile(
    r"\b(brindo|doy|ofrezco|se brinda|se da|brinda apoyo|caballero|profesional|"
    r"hombre maduro|ejecutivo)\b",
    re.I,
)
TARGET_RE = re.compile(
    r"ayuda\s*econ|apoyo\s*econ|ayudo\s*econ|brindo\s+(?:ayuda|apoyo)|doy\s+(?:ayuda|apoyo)",
    re.I,
)
SEEKER_RE = re.compile(r"\bbusco\s+(ayuda|apoyo)\b", re.I)
OFFTOPIC_RE = re.compile(
    r"\b(ong|perros?\s+de\s+la\s+calle|animales?\s+desprotej|baterista|vocalista|"
    r"formar\s+banda|refuerzo\s+escolar|apoyo\s+acad|apoyo\s+legal|ofertas?\s+de\s+trabajo)\b",
    re.I,
)


def platform_of(rec: dict) -> str:
    meta = rec.get("metadata") if isinstance(rec.get("metadata"), dict) else {}
    fam = str(meta.get("platform_family") or "").lower()
    if fam:
        return fam
    p = str(rec.get("source_platform") or "").lower()
    for key in ("locanto", "doplim", "ciudadanuncios", "evisos", "facebook"):
        if key in p:
            return key
    ref = str(rec.get("raw_archive_ref") or "").lower()
    for key in ("locanto", "doplim", "ciudadanuncios", "evisos", "evisex", "facebook"):
        if key in ref:
            return "evisos" if key == "evisex" else key
    return "other"


def keep_for_modeling(rec: dict, prefer_offer: bool) -> tuple[bool, str]:
    text = f"{rec.get('title', '')}\n{rec.get('body_redacted', '')}"
    if len(re.sub(r"\s+", " ", text).strip()) < 40:
        return False, "short"
    if not TARGET_RE.search(text):
        return False, "no_target"
    if OFFTOPIC_RE.search(text) and not OFFER_RE.search(text):
        return False, "offtopic"
    if prefer_offer:
        if SEEKER_RE.search(text) and not OFFER_RE.search(text):
            return False, "seeker_only"
        if not OFFER_RE.search(text):
            # allow dual-language titles with target terms without clear seeker
            if SEEKER_RE.search(text):
                return False, "seeker_only"
    return True, "ok"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, default=DEFAULT_IN)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    ap.add_argument("--prefer-offer", action="store_true", default=True)
    ap.add_argument("--no-prefer-offer", action="store_true")
    args = ap.parse_args()
    prefer = not args.no_prefer_offer

    records = [json.loads(l) for l in args.input.read_text(encoding="utf-8").splitlines() if l.strip()]
    kept: list[dict] = []
    drop = Counter()
    plat_in = Counter()
    plat_out = Counter()
    for rec in records:
        plat = platform_of(rec)
        plat_in[plat] += 1
        ok, why = keep_for_modeling(rec, prefer_offer=prefer)
        if not ok:
            drop[why] += 1
            continue
        kept.append(rec)
        plat_out[plat] += 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in kept),
        encoding="utf-8",
    )
    summary = {
        "input": str(args.input.relative_to(ROOT)),
        "output": str(args.output.relative_to(ROOT)),
        "input_records": len(records),
        "modeling_records": len(kept),
        "prefer_offer": prefer,
        "platform_counts_input": dict(plat_in),
        "platform_counts_modeling": dict(plat_out),
        "dropped": dict(drop),
        "recommended_train_command": (
            "python3 tools/train_manipulation_model.py "
            f"--manifest {args.output.relative_to(ROOT)}"
        ),
        "recommended_curve_command": (
            "python3 tools/learning_curve_data_scale.py "
            f"--manifest {args.output.relative_to(ROOT)} --base-target 1500"
        ),
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
