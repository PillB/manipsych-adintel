"""Run Red tests one-by-one with incremental save — survives context timeouts."""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

TS = int(time.time())
LIVE_URL = os.environ.get(
    "SOLARIZE_LIVE_URL",
    f"https://pillb.github.io/manipsych-adintel/reports/adintel/adintel_dashboard_v2.html?cb={TS}",
)
EXPECTED_SHA = os.environ.get("SOLARIZE_EXPECTED_SHA", "02da76d")

env = os.environ.copy()
env["SOLARIZE_LIVE_URL"] = LIVE_URL
env["SOLARIZE_EXPECTED_SHA"] = EXPECTED_SHA

OUT_PATH = Path(f"/home/z/my-project/audit/solarize-rebuild/round6/red_test_full_{TS}.json")
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

# Resume support — if the output file exists, load previous results
results = {}
if OUT_PATH.exists():
    prev = json.loads(OUT_PATH.read_text())
    for r in prev.get("tests", []):
        results[r["test"]] = r
    print(f"Resuming: {len(results)} tests already run")

# Get all test names by collecting
print("Collecting tests...")
collect_result = subprocess.run(
    [sys.executable, "-m", "pytest",
     "tests/adintel/test_solarize_rebuild_red.py",
     "--collect-only", "-q",
     "-p", "no:cacheprovider"],
    cwd="/home/z/my-project/repo", capture_output=True, text=True, timeout=60
)
test_names = []
for line in collect_result.stdout.splitlines():
    m = re.search(r"::(test_R\d+_\w+)$", line.strip())
    if m:
        test_names.append(m.group(1))
print(f"Collected {len(test_names)} tests")

# Filter out already-run tests
to_run = [t for t in test_names if t not in results]
print(f"To run: {len(to_run)} (skipping {len(test_names) - len(to_run)} already done)")

for i, test_name in enumerate(to_run):
    print(f"\n[{i+1}/{len(to_run)}] {test_name[:70]}", flush=True)
    cmd = [
        sys.executable, "-m", "pytest",
        f"tests/adintel/test_solarize_rebuild_red.py::TestSolarizeRebuildRed::{test_name}",
        "--tb=line", "-v",
        "--timeout=40",
        "--no-header",
        "-p", "no:cacheprovider",
    ]
    try:
        result = subprocess.run(
            cmd, env=env, cwd="/home/z/my-project/repo",
            capture_output=True, text=True, timeout=90
        )
        m = re.search(r"(PASSED|FAILED|ERROR|SKIPPED)", result.stdout)
        if m:
            status = m.group(1)
        else:
            status = "UNKNOWN"
        marker = "✓" if status == "PASSED" else "✗"
        print(f"  {marker} {status}", flush=True)

        # Extract failure detail
        detail = ""
        if status != "PASSED":
            for line in result.stdout.splitlines():
                if "AssertionError" in line or "Error" in line:
                    detail = line.strip()[:300]
                    break

        results[test_name] = {"test": test_name, "status": status, "detail": detail}
    except subprocess.TimeoutExpired:
        print(f"  ✗ TIMEOUT", flush=True)
        results[test_name] = {"test": test_name, "status": "TIMEOUT", "detail": "90s subprocess timeout"}
    except Exception as e:
        print(f"  ✗ ERROR: {e}", flush=True)
        results[test_name] = {"test": test_name, "status": "ERROR", "detail": str(e)[:300]}

    # Save incrementally
    passed = sum(1 for r in results.values() if r["status"] == "PASSED")
    failed = sum(1 for r in results.values() if r["status"] == "FAILED")
    errors = sum(1 for r in results.values() if r["status"] == "ERROR")
    timeouts = sum(1 for r in results.values() if r["status"] == "TIMEOUT")
    skipped = sum(1 for r in results.values() if r["status"] == "SKIPPED")
    unknown = sum(1 for r in results.values() if r["status"] == "UNKNOWN")

    report = {
        "live_url": LIVE_URL,
        "expected_sha": EXPECTED_SHA,
        "ran_at": int(time.time()),
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "timeouts": timeouts,
        "skipped": skipped,
        "unknown": unknown,
        "total": len(results),
        "tests": list(results.values()),
    }
    OUT_PATH.write_text(json.dumps(report, indent=2))

# Final summary
print("\n" + "=" * 60)
print(f"FINAL: {passed}/{len(results)} PASSED")
print(f"=" * 60)
print(f"PASSED: {passed}, FAILED: {failed}, ERROR: {errors}, TIMEOUT: {timeouts}, UNKNOWN: {unknown}")

# Show failures
print("\nFailures:")
for r in results.values():
    if r["status"] not in ("PASSED",):
        print(f"  {r['status']:7s} {r['test'][:70]}")
        if r.get("detail"):
            print(f"          {r['detail'][:200]}")

print(f"\nReport: {OUT_PATH}")
