#!/usr/bin/env python3
"""Launch parallel Phase 4 collectors with isolated scratch outputs and merge them."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


DEFAULT_SCRATCH = ROOT / "SCRATCH" / "phase4_parallel"
DEFAULT_MANIFEST = ROOT / "data" / "processed" / "ad_manifest.jsonl"
DEFAULT_RAW_DIR = ROOT / "SCRATCH" / "phase4_parallel" / "raw"


@dataclass(frozen=True)
class JobSpec:
    name: str
    command: list[str]
    manifest: Path
    raw_dir: Path


def shard_items(items: list[str], shard_count: int) -> list[list[str]]:
    shards: list[list[str]] = [[] for _ in range(max(1, shard_count))]
    for idx, item in enumerate(items):
        shards[idx % len(shards)].append(item)
    return shards


def start_job(job: JobSpec) -> subprocess.Popen:
    job.manifest.parent.mkdir(parents=True, exist_ok=True)
    job.raw_dir.mkdir(parents=True, exist_ok=True)
    print(f"[runner] start {job.name}: {' '.join(job.command)}", flush=True)
    return subprocess.Popen(job.command, cwd=ROOT)


def merge_manifests(manifests: list[Path], output: Path) -> dict[str, int]:
    seen: set[str] = set()
    records: list[dict[str, object]] = []
    stats: Counter[str] = Counter()
    # load pre-existing from output for incremental merge + dedup (correct accounting across launches)
    if output.exists():
        for line in output.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                rid = str(record.get("record_id", ""))
                if rid:
                    seen.add(rid)
                    records.append(record)
            except Exception:
                stats["invalid_existing"] += 1
    for manifest in manifests:
        if not manifest.exists():
            continue
        for line in manifest.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            record_id = str(record.get("record_id", ""))
            if not record_id or record_id in seen:
                stats["duplicate_or_empty"] += 1
                continue
            seen.add(record_id)
            records.append(record)
            stats["kept"] += 1
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records), encoding="utf-8")
    return dict(stats)


def build_manifest_state_snapshot(path: Path) -> Path:
    snapshot = path.with_suffix(path.suffix + ".state.json")
    record_ids: set[str] = set()
    raw_refs: set[str] = set()
    urls: set[str] = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            record_id = str(record.get("record_id", ""))
            if record_id:
                record_ids.add(record_id)
            raw_ref = str(record.get("raw_archive_ref", ""))
            if raw_ref:
                raw_refs.add(raw_ref)
            metadata = record.get("metadata")
            if isinstance(metadata, dict):
                original_url = metadata.get("original_url")
                if original_url:
                    urls.add(str(original_url))
    snapshot.write_text(
        json.dumps(
            {
                "record_ids": sorted(record_ids),
                "raw_refs": sorted(raw_refs),
                "urls": sorted(urls),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return snapshot


def build_jobs(args: argparse.Namespace) -> tuple[list[JobSpec], list[Path]]:
    scratch = args.scratch_dir
    scratch.mkdir(parents=True, exist_ok=True)

    jobs: list[JobSpec] = []
    manifests: list[Path] = []
    output_manifest = getattr(args, "output_manifest", DEFAULT_MANIFEST)
    manifest_state = build_manifest_state_snapshot(output_manifest)

    cities = [item.strip() for item in args.locanto_cities.split(",") if item.strip()]
    city_shards = shard_items(cities, args.locanto_shards)
    for idx, shard in enumerate(city_shards):
        if not shard:
            continue
        job_root = scratch / f"locanto_{idx}"
        manifest = job_root / "manifest.jsonl"
        raw_dir = job_root / "raw"
        manifests.append(manifest)
        command = [
            sys.executable,
            str(ROOT / "tools" / "collect_hombre_locanto.py"),
            "--max-ads",
            str(args.locanto_max_ads),
            "--cities",
            ",".join(shard),
            "--manifest",
            str(manifest),
            "--manifest-state",
            str(manifest_state),
            "--raw-dir",
            str(raw_dir),
            "--scratch-dir",
            str(job_root),
            "--city-shard-index",
            "0",
            "--city-shard-count",
            "1",
            "--direct-workers",
            str(args.locanto_direct_workers),
            "--search-workers",
            str(args.locanto_search_workers),
            "--search-delay-min",
            str(args.locanto_search_delay_min),
            "--search-delay-max",
            str(args.locanto_search_delay_max),
            "--list-workers",
            str(args.locanto_list_workers),
            "--listing-pages",
            str(args.locanto_listing_pages),
        ]
        if args.locanto_direct_only:
            command.append("--direct-only")
        if args.locanto_skip_ddg:
            command.append("--skip-ddg")
        jobs.append(JobSpec(name=f"locanto-{idx}", command=command, manifest=manifest, raw_dir=raw_dir))

    for idx in range(max(1, args.seed_shards)):
        job_root = scratch / f"seed_{idx}"
        manifest = job_root / "manifest.jsonl"
        raw_dir = job_root / "raw"
        attempt_log = job_root / "attempts.json"
        manifests.append(manifest)
        command = [
            sys.executable,
            str(ROOT / "tools" / "collect_seed_inventory.py"),
            "--platform",
            args.seed_platform,
            "--max-fetch",
            str(args.seed_max_fetch),
            "--timeout-ms",
            str(args.seed_timeout_ms),
            "--retries",
            str(args.seed_retries),
            "--delay",
            str(args.seed_delay),
            "--manifest",
            str(manifest),
            "--manifest-state",
            str(manifest_state),
            "--raw-dir",
            str(raw_dir),
            "--attempt-log",
            str(attempt_log),
            "--seed-shard-index",
            str(idx),
            "--seed-shard-count",
            str(args.seed_shards),
            "--workers",
            str(args.seed_workers),
            "--http-only",
            "--shuffle",
            "--verbose",
        ]
        jobs.append(JobSpec(name=f"seed-{idx}", command=command, manifest=manifest, raw_dir=raw_dir))

    return jobs, manifests


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch-dir", type=Path, default=DEFAULT_SCRATCH)
    parser.add_argument("--output-manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--locanto-cities", default="lima,arequipa,trujillo,cusco,piura,chiclayo,huancayo")
    parser.add_argument("--locanto-shards", type=int, default=6)
    parser.add_argument("--locanto-max-ads", type=int, default=8)
    parser.add_argument("--locanto-direct-only", action="store_true")
    parser.add_argument("--locanto-direct-workers", type=int, default=12)
    parser.add_argument("--locanto-search-workers", type=int, default=6)
    parser.add_argument("--locanto-search-delay-min", type=float, default=0.2)
    parser.add_argument("--locanto-search-delay-max", type=float, default=0.8)
    parser.add_argument("--locanto-list-workers", type=int, default=10)
    parser.add_argument("--locanto-listing-pages", type=int, default=3)
    parser.add_argument("--locanto-skip-ddg", action="store_true")
    parser.add_argument("--seed-platform", choices=("all", "locanto", "doplim", "facebook"), default="doplim")
    parser.add_argument("--seed-shards", type=int, default=6)
    parser.add_argument("--seed-max-fetch", type=int, default=24)
    parser.add_argument("--seed-timeout-ms", type=int, default=22000)
    parser.add_argument("--seed-retries", type=int, default=2)
    parser.add_argument("--seed-delay", type=float, default=0.1)
    parser.add_argument("--seed-workers", type=int, default=16)
    parser.add_argument("--keep-temp", action="store_true")
    args = parser.parse_args()

    if args.scratch_dir.exists():
        shutil.rmtree(args.scratch_dir)
    args.scratch_dir.mkdir(parents=True, exist_ok=True)

    start_ts = time.time()
    jobs, manifests = build_jobs(args)
    if not jobs:
        print("No jobs scheduled.", flush=True)
        return 0

    procs: list[tuple[JobSpec, subprocess.Popen]] = []
    for job in jobs:
        procs.append((job, start_job(job)))

    rc = 0
    for job, proc in procs:
        job_rc = proc.wait()
        print(f"[runner] done {job.name}: rc={job_rc}", flush=True)
        if job_rc != 0 and rc == 0:
            rc = job_rc

    stats = merge_manifests(manifests, args.output_manifest)
    elapsed = time.time() - start_ts
    added = stats.get("kept", 0)
    rate = (added / (elapsed / 60.0)) if elapsed > 0 else 0.0
    rate_note = f"{rate:.2f} ads/min" if added > 0 else "rate limited by supply/blocks/interstitials (0 added in this run)"
    print(json.dumps({
        "output_manifest": str(args.output_manifest),
        "jobs": len(jobs),
        "merged_records": added,
        "duplicates_or_empty": stats.get("duplicate_or_empty", 0),
        "elapsed_s": round(elapsed, 1),
        "throughput": rate_note,
    }, ensure_ascii=False, indent=2))
    print(f"[runner] elapsed={elapsed:.1f}s added={added} throughput={rate_note} (target >=10 ads/min via parallel; env may limit)", flush=True)

    if not args.keep_temp:
        shutil.rmtree(args.scratch_dir, ignore_errors=True)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
