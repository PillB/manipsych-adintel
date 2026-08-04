import unittest

from tools.train_manipulation_model import build_dataset, weak_labels


class TrainManipulationModelTests(unittest.TestCase):
    def test_weak_labels_include_financial_and_privacy_cues(self):
        labels = weak_labels("Brindo apoyo economico discreto por privado para estudiante")
        self.assertIn("financial_emergency_multiplier", labels)
        self.assertIn("safety_and_privacy_multiplier", labels)
        self.assertIn("education_and_career_aspiration_multiplier", labels)

    def test_build_dataset(self):
        texts, labels = build_dataset([{"title": "Ayuda", "body_redacted": "apoyo economico"}])
        self.assertEqual(len(texts), 1)
        self.assertTrue(labels[0])


if __name__ == "__main__":
    unittest.main()
