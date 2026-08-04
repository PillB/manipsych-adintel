import json
import tempfile
import unittest
from pathlib import Path

from tools.ingest_candidate_urls import append_candidates, extract_urls, is_candidate


class IngestCandidateUrlsTests(unittest.TestCase):
    def test_extract_urls(self):
        urls = extract_urls("See https://www.locanto.com.pe/lima/tag/ayuda-economica/ and https://example.com/x.")
        self.assertIn("https://www.locanto.com.pe/lima/tag/ayuda-economica/", urls)

    def test_candidate_filter(self):
        self.assertTrue(is_candidate("https://www.locanto.com.pe/lima/tag/ayuda-economica/"))
        self.assertFalse(is_candidate("https://example.com/ayuda-economica"))

    def test_append_candidates_to_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.json"
            added = append_candidates(log, ["https://www.locanto.com.pe/lima/tag/ayuda-economica/"], "unit-test")
            self.assertEqual(added, 1)
            data = json.loads(log.read_text(encoding="utf-8"))
        self.assertEqual(data["attempts"][0]["result_count"], 1)


if __name__ == "__main__":
    unittest.main()
