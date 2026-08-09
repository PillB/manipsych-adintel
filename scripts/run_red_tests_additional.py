"""Run only the tests that are most relevant to my Round 5 changes."""
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
EXPECTED_SHA = os.environ.get("SOLARIZE_EXPECTED_SHA", "39186d9f")

env = os.environ.copy()
env["SOLARIZE_LIVE_URL"] = LIVE_URL
env["SOLARIZE_EXPECTED_SHA"] = EXPECTED_SHA

# Tests I haven't verified yet
TESTS = [
    "R009_phrase_injection_not_labeled_gan",
    "R010_uncalibrated_scores_not_labeled_calibrated",
    "R013_text_only_input_supported",
    "R021_gan_label_requires_genuine_gan_evidence",
    "R035_per_label_metrics_present",
    "R037_no_duplicated_data_payload",
]

print(f"Live URL: {LIVE_URL}")
print(f"Expected SHA: {EXPECTED_SHA}")
print(f"Running {len(TESTS)} additional tests")
print("---")

results = []
for test in TESTS:
    cmd = [
        sys.executable, "-m", "pytest",
        f"tests/adintel/test_solarize_rebuild_red.py::TestSolarizeRebuildRed::test_{test}",
        "--tb=line", "-v",
        "--timeout=45",
        "--no-header",
        "-p", "no:cacheprovider",
    ]
    print(f"\n>>> test_{test}")
    try:
        result = subprocess.run(
            cmd, env=env, cwd="/home/z/my-project/repo",
            capture_output=True, text=True, timeout=120
        )
        m = re.search(r"(PASSED|FAILED|ERROR|SKIPPED)", result.stdout)
        if m:
            status = m.group(1)
            marker = "✓" if status == "PASSED" else "✗"
            print(f"  {marker} {status}")
            results.append({"test": test, "status": status})
            if status != "PASSED":
                lines = result.stdout.splitlines()
                for i, line in enumerate(lines):
                    if "AssertionError" in line or "assert" in line.lower():
                        start = max(0, i - 1)
                        end = min(len(lines), i + 4)
                        print("  --- Failure context ---")
                        for l in lines[start:end]:
                            print(f"  {l}")
                        break
        else:
            print(f"  ? UNKNOWN")
            print("  stdout tail:", result.stdout[-500:] if result.stdout else "")
            results.append({"test": test, "status": "UNKNOWN"})
    except subprocess.TimeoutExpired:
        print(f"  ✗ TIMEOUT")
        results.append({"test": test, "status": "TIMEOUT"})

passed = sum(1 for r in results if r["status"] == "PASSED")
print(f"\n{'=' * 60}")
print(f"PASSED: {passed} / {len(results)}")
print(f"{'=' * 60}")
for r in results:
    marker = "✓" if r["status"] == "PASSED" else "✗"
    print(f"  {marker} {r['test']}: {r['status']}")

report = {
    "live_url": LIVE_URL,
    "expected_sha": EXPECTED_SHA,
    "ran_at": int(time.time()),
    "passed": passed,
    "total": len(results),
    "tests": results,
}
out_path = Path(f"/home/z/my-project/audit/solarize-rebuild/round5/red_test_additional_{TS}.json")
out_path.write_text(json.dumps(report, indent=2))
print(f"\nReport saved to: {out_path}")
