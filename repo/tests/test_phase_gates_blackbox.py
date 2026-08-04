import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PhaseGateBlackBoxTests(unittest.TestCase):
    def test_phase0_cli_passes(self):
        result = subprocess.run(
            [sys.executable, "tools/phase_gate.py", "--phase", "0"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("Phase 0 gate passed", result.stdout)

    def test_all_cli_passes_when_all_phase_artifacts_exist(self):
        result = subprocess.run(
            [sys.executable, "tools/phase_gate.py", "--all"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("Phase 5 gate passed", result.stdout)
        self.assertIn("Phase 6 gate passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
