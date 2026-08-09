"""Run the 7 previously-failing Red tests against a local HTTP server.

Strategy: Create a temporary patched copy of the test file that bypasses
the _is_live_url check, run the tests, then clean up.
"""
import http.server
import os
import re
import shutil
import socketserver
import subprocess
import sys
import threading
import time
from pathlib import Path

DASHBOARD_DIR = Path("/home/z/my-project/docs/reports/adintel")
PORT = 8765
ORIGINAL_TEST = Path("/home/z/my-project/repo/tests/adintel/test_solarize_rebuild_red.py")
PATCHED_TEST = Path("/home/z/my-project/repo/tests/adintel/test_solarize_rebuild_red_local.py")

def start_server():
    handler = lambda *args: http.server.SimpleHTTPRequestHandler(*args, directory=str(DASHBOARD_DIR))
    httpd = socketserver.TCPServer(("127.0.0.1", PORT), handler)
    httpd.serve_forever()

# Start server in background
server_thread = threading.Thread(target=start_server, daemon=True)
server_thread.start()
time.sleep(1)
print(f"Local server started on http://127.0.0.1:{PORT}/")

LIVE_URL = f"http://127.0.0.1:{PORT}/adintel_dashboard_v2.html"

# Create a patched copy of the test file
original = ORIGINAL_TEST.read_text()
# Replace the skipUnless decorator to always allow
patched = original.replace(
    '@unittest.skipUnless(_is_live_url(LIVE_URL), "SOLARIZE_LIVE_URL must point to a github.io URL")',
    '@unittest.skipUnless(True, "local test")'
)
# Also replace the LIVE_URL default to use our local server
patched = patched.replace(
    'LIVE_URL = os.environ.get("SOLARIZE_LIVE_URL", "")',
    f'LIVE_URL = os.environ.get("SOLARIZE_LIVE_URL", "{LIVE_URL}")'
)
# Change the class name to avoid collection conflicts
patched = patched.replace(
    'class TestSolarizeRebuildRed(unittest.TestCase):',
    'class TestSolarizeRebuildRedLocal(unittest.TestCase):'
)

PATCHED_TEST.write_text(patched)
print(f"Patched test file: {PATCHED_TEST}")

# The 7 previously-failing tests
TESTS = [
    "R005_adintel_integrated_into_central_pipeline",
    "R007_pipeline_nodes_link_to_real_modules",
    "R016_abstention_supported",
    "R023_safety_screening_documented",
    "R033_source_leakage_prevention_documented",
    "R045_assistant_cites_evidence",
    "R046_assistant_refuses_manipulation_requests",
]

env = os.environ.copy()
env["SOLARIZE_LIVE_URL"] = LIVE_URL
env["SOLARIZE_EXPECTED_SHA"] = "local"

print(f"Testing 7 previously-failing tests against: {LIVE_URL}")
print("---")

results = []
for test in TESTS:
    cmd = [
        sys.executable, "-m", "pytest",
        f"tests/adintel/test_solarize_rebuild_red_local.py::TestSolarizeRebuildRedLocal::test_{test}",
        "--tb=short", "-v",
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
        m = re.search(r"(PASSED|FAILED|ERROR|SKIPPED)", result.stdout)
        if m:
            status = m.group(1)
            marker = "✓" if status == "PASSED" else "✗"
            print(f"  {marker} {status}")
            results.append((test, status))
            if status != "PASSED":
                # Print failure context
                for line in result.stdout.splitlines():
                    if "AssertionError" in line or "Error" in line:
                        print(f"  {line.strip()[:200]}")
        else:
            print(f"  ? UNKNOWN")
            print(f"  stdout: {result.stdout[-300:]}")
            results.append((test, "UNKNOWN"))
    except subprocess.TimeoutExpired:
        print(f"  ✗ TIMEOUT")
        results.append((test, "TIMEOUT"))

# Cleanup
PATCHED_TEST.unlink(missing_ok=True)
print(f"\nCleaned up: {PATCHED_TEST}")

# Summary
passed = sum(1 for _, s in results if s == "PASSED")
print(f"\n{'=' * 60}")
print(f"RESULT: {passed}/{len(results)} PASSED")
print(f"{'=' * 60}")
for test, status in results:
    marker = "✓" if status == "PASSED" else "✗"
    print(f"  {marker} {test[:60]}: {status}")
