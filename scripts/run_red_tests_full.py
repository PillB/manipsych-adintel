"""Run all 48 Red tests in batches with timeouts, save consolidated report."""
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

# Run tests in batches of 4 to keep each batch under ~3 min
ALL_TESTS = [f"R{n:03d}" for n in range(1, 49)]
BATCH_SIZE = 4
BATCHES = [ALL_TESTS[i:i+BATCH_SIZE] for i in range(0, len(ALL_TESTS), BATCH_SIZE)]

print(f"Live URL: {LIVE_URL}")
print(f"Expected SHA: {EXPECTED_SHA}")
print(f"Total tests: {len(ALL_TESTS)} in {len(BATCHES)} batches of {BATCH_SIZE}")
print("---")

all_results = []
batch_failures = []

for batch_idx, batch in enumerate(BATCHES):
    print(f"\n=== Batch {batch_idx + 1}/{len(BATCHES)}: {batch} ===")
    expr = " or ".join(batch)
    cmd = [
        sys.executable, "-m", "pytest",
        "tests/adintel/test_solarize_rebuild_red.py",
        f"-k={expr}",
        "--tb=line", "-v",
        "--timeout=45",
        "--no-header",
        "-p", "no:cacheprovider",
    ]
    try:
        result = subprocess.run(
            cmd, env=env, cwd="/home/z/my-project/repo",
            capture_output=True, text=True, timeout=300
        )
        if result.returncode != 0 and not result.stdout.strip():
            print(f"  ⚠ Empty stdout. stderr tail: {result.stderr[-500:]}")
        for line in result.stdout.splitlines():
            line = line.strip()
            m = re.match(r"^(test_R\d+_\w+)\s+(PASSED|FAILED|ERROR|SKIPPED)", line)
            if m:
                test_name = m.group(1)
                status = m.group(2)
                all_results.append({"test": test_name, "status": status, "batch": batch_idx + 1})
                marker = "✓" if status == "PASSED" else "✗"
                print(f"  {marker} {test_name[:60]}: {status}")
                if status != "PASSED":
                    batch_failures.append((test_name, batch_idx + 1))
        if not any(r["batch"] == batch_idx + 1 for r in all_results):
            print(f"  ⚠ No test results parsed. stderr tail: {result.stderr[-500:]}")
    except subprocess.TimeoutExpired:
        print(f"  ✗ BATCH TIMEOUT — marking all as TIMEOUT")
        for t in batch:
            all_results.append({"test": f"test_{t}_unknown", "status": "TIMEOUT", "batch": batch_idx + 1})
    except Exception as e:
        print(f"  ✗ BATCH ERROR: {e}")
        for t in batch:
            all_results.append({"test": f"test_{t}_unknown", "status": "ERROR", "batch": batch_idx + 1, "error": str(e)})

# Show failure details
if batch_failures:
    print("\n" + "=" * 60)
    print("FAILED TESTS — re-running individually for details")
    print("=" * 60)
    for test_name, batch_idx in batch_failures:
        print(f"\n>>> {test_name}")
        cmd = [
            sys.executable, "-m", "pytest",
            f"tests/adintel/test_solarize_rebuild_red.py::TestSolarizeRebuildRed::{test_name}",
            "--tb=short", "-v",
            "--timeout=45",
            "-p", "no:cacheprovider",
        ]
        try:
            result = subprocess.run(
                cmd, env=env, cwd="/home/z/my-project/repo",
                capture_output=True, text=True, timeout=120
            )
            # Print failure context
            lines = result.stdout.splitlines()
            for i, line in enumerate(lines):
                if "AssertionError" in line or "Error" in line:
                    start = max(0, i - 2)
                    end = min(len(lines), i + 6)
                    for l in lines[start:end]:
                        print(f"  {l}")
                    break
        except Exception as e:
            print(f"  Re-run error: {e}")

# Summary
passed = sum(1 for r in all_results if r["status"] == "PASSED")
failed = sum(1 for r in all_results if r["status"] == "FAILED")
errors = sum(1 for r in all_results if r["status"] == "ERROR")
skipped = sum(1 for r in all_results if r["status"] == "SKIPPED")
timeouts = sum(1 for r in all_results if r["status"] == "TIMEOUT")

print("\n" + "=" * 60)
print(f"FINAL SUMMARY: {passed}/{len(all_results)} PASSED")
print(f"=" * 60)
print(f"PASSED:  {passed}")
print(f"FAILED:  {failed}")
print(f"ERROR:   {errors}")
print(f"TIMEOUT: {timeouts}")
print(f"SKIPPED: {skipped}")
print(f"TOTAL:   {len(all_results)}")

report = {
    "live_url": LIVE_URL,
    "expected_sha": EXPECTED_SHA,
    "ran_at": int(time.time()),
    "passed": passed,
    "failed": failed,
    "errors": errors,
    "timeouts": timeouts,
    "skipped": skipped,
    "total": len(all_results),
    "tests": all_results,
}
out_path = Path(f"/home/z/my-project/audit/solarize-rebuild/round6/red_test_full_{TS}.json")
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(json.dumps(report, indent=2))
print(f"\nReport saved to: {out_path}")
