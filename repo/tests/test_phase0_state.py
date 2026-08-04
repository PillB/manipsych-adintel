import unittest
from pathlib import Path

from tools.phase_gate import _looks_like_ui_boilerplate, _platform_family, _raw_family, failures_for_phase


ROOT = Path(__file__).resolve().parents[1]


class Phase0GateTests(unittest.TestCase):
    def test_project_brief_contains_all_phases(self):
        text = (ROOT / "PROJECT_BRIEF.md").read_text(encoding="utf-8")
        for phase in range(7):
            self.assertIn(f"Phase {phase}", text)

    def test_phase0_gate_passes(self):
        self.assertEqual(failures_for_phase(0), [])

    def test_phase4_family_and_boilerplate_helpers(self):
        self.assertEqual(_raw_family("data/raw/ads/locanto_detail_x.html"), "locanto")
        self.assertEqual(_raw_family("data/raw/ads/fb_public_x.html"), "facebook")
        self.assertEqual(_platform_family("Facebook Public (indexed)"), "facebook")
        self.assertTrue(_looks_like_ui_boilerplate(":root { --fds-blue: #1877f2; }"))
        self.assertFalse(_looks_like_ui_boilerplate("Descripción Brindo ayuda económica a señorita."))


if __name__ == "__main__":
    unittest.main()
