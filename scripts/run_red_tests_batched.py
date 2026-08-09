"""Run Red tests in batches against the live deployment.

Splits the 48 tests into 6 batches of 8 tests each, with per-test timeouts
and per-batch subprocess timeouts. Saves a final consolidated report.
"""
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
EXPECTED_SHA = os.environ.get("SOLARIZE_EXPECTED_SHA", "e8b2a75a")

# Batches of test name prefixes
BATCHES = [
    ["R001", "R002", "R003", "R004", "R005", "R006", "R007", "R008"],
    ["R009", "R010", "R011", "R012", "R013", "R014", "R015", "R016"],
    ["R017", "R018", "R019", "R020", "R021", "R022", "R023", "R024"],
    ["R025", "R026", "R027", "R028", "R029", "R030", "R031", "R032"],
    ["R033", "R034", "R035", "R036", "R037", "R038", "R039", "R040"],
    ["R041", "R042", "R043", "R044", "R045", "R046", "R047", "R048"],
]

env = os.environ.copy()
env["SOLARIZE_LIVE_URL"] = LIVE_URL
env["SOLARIZE_EXPECTED_SHA"] = EXPECTED_SHA

print(f"Live URL: {LIVE_URL}")
print(f"Expected SHA: {EXPECTED_SHA}")
print(f"Batches: {len(BATCHES)} × {len(BATCHES[0])} tests = {sum(len(b) for b in BATCHES)} tests")
print("---")

all_results = []

for batch_idx, batch in enumerate(BATCHES):
    print(f"\n=== Batch {batch_idx + 1}/{len(BATCHES)} ===")
    # Build pytest -k expression: R001 or R002 or ...
    expr = " or ".join(batch)
    cmd = [
        sys.executable, "-m", "pytest",
        "tests/adintel/test_solarize_rebuild_red.py",
        f"-k={expr}",
        "--tb=line", "-v",
        "--timeout=60",
        "--no-header",
        "-p", "no:cacheprovider",
    ]
    try:
        result = subprocess.run(
            cmd, env=env, cwd="/home/z/my-project/repo",
            capture_output=True, text=True, timeout=600
        )
        # Parse results
        for line in result.stdout.splitlines():
            line = line.strip()
            m = re.match(r"^(test_R\d+_\w+)\s+(PASSED|FAILED|ERROR|SKIPPED)", line)
            if m:
                test_name = m.group(1)
                status = m.group(2)
                all_results.append({"test": test_name, "status": status, "batch": batch_idx + 1})
                marker = "✓" if status == "PASSED" else "✗"
                print(f"  {marker} {test_name}: {status}")
        # Show failures with details
        if "FAILED" in result.stdout or "ERROR" in result.stdout:
            print("  --- Failure details (last 20 lines) ---")
            for line in result.stdout.splitlines()[-20:]:
                if line.strip():
                    print(f"  {line}")
    except subprocess.TimeoutExpired:
        print(f"  ✗ BATCH TIMEOUT — killing")
        for t in batch:
            all_results.append({"test": f"test_{t}_*", "status": "TIMEOUT", "batch": batch_idx + 1})
    except Exception as e:
        print(f"  ✗ BATCH ERROR: {e}")
        for t in batch:
            all_results.append({"test": f"test_{t}_*", "status": "ERROR", "batch": batch_idx + 1, "error": str(e)})

# Summary
passed = sum(1 for r in all_results if r["status"] == "PASSED")
failed = sum(1 for r in all_results if r["status"] == "FAILED")
errors = sum(1 for r in all_results if r["status"] == "ERROR")
skipped = sum(1 for r in all_results if r["status"] == "SKIPPED")
timeouts = sum(1 for r in all_results if r["status"] == "TIMEOUT")

print("\n" + "=" * 60)
print(f"FINAL SUMMARY")
print(f"=" * 60)
print(f"PASSED:  {passed}")
print(f"FAILED:  {failed}")
print(f"ERROR:   {errors}")
print(f"TIMEOUT: {timeouts}")
print(f"SKIPPED: {skipped}")
print(f"TOTAL:   {len(all_results)}")
print(f"=" * 60)

if failed > 0 or errors > 0:
    print("\nFailed/Error tests:")
    for r in all_results:
        if r["status"] in ("FAILED", "ERROR"):
            print(f"  {r['status']:7s} {r['test']}")

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

out_path = Path(f"/home/z/my-project/audit/solarize-rebuild/round5/red_test_post_deploy_{TS}.json")
out_path.write_text(json.dumps(report, indent=2))
print(f"\nReport saved to: {out_path}")
