"""Run the 48 Solarize Red tests against the live v2 dashboard, save a JSON report."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

TS = int(time.time())
LIVE_URL = os.environ.get(
    "SOLARIZE_LIVE_URL",
    f"https://pillb.github.io/manipsych-adintel/reports/adintel/adintel_dashboard_v2.html?cb={TS}",
)
EXPECTED_SHA = os.environ.get("SOLARIZE_EXPECTED_SHA", "655cb0f576fee8d6f813c01bf6abcd4fe4720f8b")

env = os.environ.copy()
env["SOLARIZE_LIVE_URL"] = LIVE_URL
env["SOLARIZE_EXPECTED_SHA"] = EXPECTED_SHA

print(f"Live URL: {LIVE_URL}")
print(f"Expected SHA: {EXPECTED_SHA}")
print("---")

cmd = [
    sys.executable, "-m", "pytest",
    "tests/adintel/test_solarize_rebuild_red.py",
    "--tb=line", "-v",
    "--timeout=90",
    "--no-header",
    "-p", "no:cacheprovider",
]

result = subprocess.run(
    cmd, env=env, cwd="/home/z/my-project/repo",
    capture_output=True, text=True, timeout=1500
)

print("STDOUT:")
print(result.stdout)
print("STDERR (tail):")
print(result.stderr[-3000:])

# Parse the pytest output to extract per-test results
import re
test_results = []
for line in result.stdout.splitlines():
    line = line.strip()
    # Match lines like "test_R001_... PASSED [  5%]" or "FAILED"
    m = re.match(r"^(test_R\d+_\w+)\s+(PASSED|FAILED|ERROR|SKIPPED)", line)
    if m:
        test_results.append({"test": m.group(1), "status": m.group(2)})

passed = sum(1 for t in test_results if t["status"] == "PASSED")
failed = sum(1 for t in test_results if t["status"] == "FAILED")
errors = sum(1 for t in test_results if t["status"] == "ERROR")
skipped = sum(1 for t in test_results if t["status"] == "SKIPPED")

report = {
    "live_url": LIVE_URL,
    "expected_sha": EXPECTED_SHA,
    "ran_at": int(time.time()),
    "passed": passed,
    "failed": failed,
    "errors": errors,
    "skipped": skipped,
    "total": len(test_results),
    "tests": test_results,
    "stdout_tail": result.stdout[-5000:],
}

out_path = Path(f"/home/z/my-project/audit/solarize-rebuild/round5/red_test_baseline_{TS}.json")
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(json.dumps(report, indent=2))
print(f"\nReport saved to: {out_path}")
print(f"PASSED: {passed} / FAILED: {failed} / ERROR: {errors} / SKIPPED: {skipped} / TOTAL: {len(test_results)}")
