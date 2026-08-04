import unittest

from tools.detect_manipulation import analyze_text


class DetectManipulationTests(unittest.TestCase):
    def test_detects_financial_urgency_and_private_migration(self):
        result = analyze_text("Ayuda economica urgente, escribeme por privado hoy.")
        self.assertGreaterEqual(result["score"], 0.6)
        self.assertIn("financial_emergency_multiplier", result["tags"])
        self.assertIn("scarcity_urgency_pressure", result["tags"])
        self.assertIn("platform_migration", result["tags"])

    def test_low_signal_text_scores_zero(self):
        result = analyze_text("Informe tecnico sobre fuentes estadisticas oficiales.")
        self.assertEqual(result["score"], 0.0)
        self.assertEqual(result["tags"], [])


if __name__ == "__main__":
    unittest.main()
