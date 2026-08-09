"""Quick Red test runner — runs a small subset of critical tests."""
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

env = os.environ.copy()
env["SOLARIZE_LIVE_URL"] = LIVE_URL
env["SOLARIZE_EXPECTED_SHA"] = EXPECTED_SHA

# Critical tests for our changes
TESTS = [
    "R001_top_level_navigation_is_task_oriented",
    "R008_rule_based_not_labeled_as_trained_model",
    "R020_checkpoint_provenance_for_results",
    "R032_no_console_errors",
    "R034_calibration_evidence_present",
    "R036_html_size_under_150kb",
    "R044_ask_adintel_assistant_exists",
    "R047_indicator_dictionary_exists",
    "R048_indicator_dictionary_in_dashboard",
]

print(f"Live URL: {LIVE_URL}")
print(f"Expected SHA: {EXPECTED_SHA}")
print(f"Running {len(TESTS)} critical tests")
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
            capture_output=True, text=True, timeout=90
        )
        # Find PASSED/FAILED in stdout
        m = re.search(r"(PASSED|FAILED|ERROR|SKIPPED)", result.stdout)
        if m:
            status = m.group(1)
            marker = "✓" if status == "PASSED" else "✗"
            print(f"  {marker} {status}")
            results.append({"test": test, "status": status})
            if status != "PASSED":
                # Print failure context
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
            print("  stderr tail:", result.stderr[-500:] if result.stderr else "")
            results.append({"test": test, "status": "UNKNOWN"})
    except subprocess.TimeoutExpired:
        print(f"  ✗ TIMEOUT")
        results.append({"test": test, "status": "TIMEOUT"})

# Summary
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
out_path = Path(f"/home/z/my-project/audit/solarize-rebuild/round5/red_test_critical_{TS}.json")
out_path.write_text(json.dumps(report, indent=2))
print(f"\nReport saved to: {out_path}")
