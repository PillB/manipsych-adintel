#!/usr/bin/env python3
"""Parallel public search-harvest and collection pipeline for Phase 4."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


DEFAULT_SCRATCH = ROOT / "SCRATCH" / "query_harvest_parallel"
DEFAULT_QUERY_BANK = ROOT / "data" / "sources" / "query_bank.json"
DEFAULT_MANIFEST = ROOT / "data" / "processed" / "ad_manifest.jsonl"


@dataclass(frozen=True)
class JobSpec:
    name: str
    command: list[str]
    output: Path


def shard_items(items: list[str], shard_count: int) -> list[list[str]]:
    shards: list[list[str]] = [[] for _ in range(max(1, shard_count))]
    for idx, item in enumerate(items):
        shards[idx % len(shards)].append(item)
    return shards


def start_job(job: JobSpec) -> subprocess.Popen:
    job.output.parent.mkdir(parents=True, exist_ok=True)
    print(f"[runner] start {job.name}: {' '.join(job.command)}", flush=True)
    return subprocess.Popen(job.command, cwd=ROOT)


def run_jobs_batched(jobs: list[JobSpec], max_parallel: int) -> tuple[int, list[Path]]:
    rc = 0
    outputs: list[Path] = []
    for start in range(0, len(jobs), max(1, max_parallel)):
        batch = jobs[start : start + max(1, max_parallel)]
        procs: list[tuple[JobSpec, subprocess.Popen]] = []
        for job in batch:
            outputs.append(job.output)
            procs.append((job, start_job(job)))
        for job, proc in procs:
            job_rc = proc.wait()
            print(f"[runner] done {job.name}: rc={job_rc}", flush=True)
            if job_rc != 0 and rc == 0:
                rc = job_rc
    return rc, outputs


def merge_jsonl(files: list[Path], output: Path, dedup_key: str) -> dict[str, int]:
    seen: set[str] = set()
    records: list[dict[str, object]] = []
    stats: Counter[str] = Counter()
    for file in files:
        if not file.exists():
            continue
        for line in file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                stats["invalid_json"] += 1
                continue
            key = str(record.get(dedup_key, ""))
            if not key or key in seen:
                stats["duplicate_or_empty"] += 1
                continue
            seen.add(key)
            records.append(record)
            stats["kept"] += 1
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records), encoding="utf-8")
    return dict(stats)


def build_harvest_jobs(args: argparse.Namespace, scratch: Path) -> tuple[list[JobSpec], list[Path]]:
    jobs: list[JobSpec] = []
    outputs: list[Path] = []
    bank = json.loads(args.query_bank.read_text(encoding="utf-8")) if args.query_bank.exists() else {}
    for platform in ("locanto", "doplim", "facebook"):
        queries = list(bank.get(platform, []))
        if not queries:
            continue
        shards = shard_items(queries, args.query_shards)
        for idx, shard in enumerate(shards):
            if not shard:
                continue
            out = scratch / f"harvested/{platform}_{idx}.jsonl"
            outputs.append(out)
            command = [
                sys.executable,
                str(ROOT / "tools" / "harvest_seeds.py"),
                "--query-bank",
                str(args.query_bank),
                "--query-platform",
                platform,
                "--query-shard-index",
                str(idx),
                "--query-shard-count",
                str(args.query_shards),
                "--query-limit",
                str(args.query_limit),
                "--mode",
                "playwright",
                "--max-pages",
                str(args.harvest_pages),
                "--out",
                str(out),
            ]
            jobs.append(JobSpec(name=f"harvest-{platform}-{idx}", command=command, output=out))
    return jobs, outputs


def build_collect_jobs(args: argparse.Namespace, scratch: Path, seeds_file: Path) -> tuple[list[JobSpec], list[Path]]:
    jobs: list[JobSpec] = []
    manifests: list[Path] = []
    for platform in ("locanto", "doplim", "facebook"):
        for idx in range(max(1, args.collect_shards)):
            job_root = scratch / f"collect/{platform}_{idx}"
            manifest = job_root / "manifest.jsonl"
            raw_dir = job_root / "raw"
            attempt_log = job_root / "attempts.json"
            manifests.append(manifest)
            command = [
                sys.executable,
                str(ROOT / "tools" / "collect_seed_inventory.py"),
                "--seeds",
                str(seeds_file),
                "--platform",
                platform,
                "--manifest",
                str(manifest),
                "--raw-dir",
                str(raw_dir),
                "--attempt-log",
                str(attempt_log),
                "--max-fetch",
                str(args.collect_max_fetch),
                "--timeout-ms",
                str(args.collect_timeout_ms),
                "--retries",
                str(args.collect_retries),
                "--delay",
                str(args.collect_delay),
                "--workers",
                str(args.collect_workers),
                "--http-only",
                "--seed-shard-index",
                str(idx),
                "--seed-shard-count",
                str(args.collect_shards),
                "--shuffle",
                "--verbose",
            ]
            jobs.append(JobSpec(name=f"collect-{platform}-{idx}", command=command, output=manifest))
    return jobs, manifests


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch-dir", type=Path, default=DEFAULT_SCRATCH)
    parser.add_argument("--query-bank", type=Path, default=DEFAULT_QUERY_BANK)
    parser.add_argument("--query-shards", type=int, default=6)
    parser.add_argument("--query-limit", type=int, default=30)
    parser.add_argument("--harvest-pages", type=int, default=1)
    parser.add_argument("--collect-shards", type=int, default=6)
    parser.add_argument("--collect-max-fetch", type=int, default=24)
    parser.add_argument("--collect-timeout-ms", type=int, default=22000)
    parser.add_argument("--collect-retries", type=int, default=2)
    parser.add_argument("--collect-delay", type=float, default=0.1)
    parser.add_argument("--collect-workers", type=int, default=12)
    parser.add_argument("--max-parallel", type=int, default=3)
    parser.add_argument("--collect-parallel", type=int, default=3)
    parser.add_argument("--output-manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--keep-temp", action="store_true")
    args = parser.parse_args()

    if args.scratch_dir.exists():
        shutil.rmtree(args.scratch_dir)
    args.scratch_dir.mkdir(parents=True, exist_ok=True)

    subprocess.run([sys.executable, str(ROOT / "tools" / "build_query_bank.py"), "--output", str(args.query_bank)], cwd=ROOT, check=False)

    harvest_jobs, harvest_outputs = build_harvest_jobs(args, args.scratch_dir)
    harvest_rc, harvest_outputs = run_jobs_batched(harvest_jobs, args.max_parallel)

    merged_seeds = args.scratch_dir / "merged_seeds.jsonl"
    seed_stats = merge_jsonl(harvest_outputs, merged_seeds, "url")
    print(json.dumps({"merged_seeds": seed_stats.get("kept", 0), "duplicate_or_empty": seed_stats.get("duplicate_or_empty", 0)}, ensure_ascii=False, indent=2))

    os.environ["PLAYWRIGHT_FORCE_BUNDLED_CHROMIUM"] = "1"
    collect_jobs, collect_manifests = build_collect_jobs(args, args.scratch_dir, merged_seeds)
    collect_rc, _ = run_jobs_batched(collect_jobs, args.collect_parallel)

    output_stats = merge_jsonl(collect_manifests, args.output_manifest, "record_id")
    print(json.dumps({
        "output_manifest": str(args.output_manifest),
        "merged_records": output_stats.get("kept", 0),
        "duplicate_or_empty": output_stats.get("duplicate_or_empty", 0),
    }, ensure_ascii=False, indent=2))

    if not args.keep_temp:
        shutil.rmtree(args.scratch_dir, ignore_errors=True)
    return harvest_rc or collect_rc


if __name__ == "__main__":
    raise SystemExit(main())
