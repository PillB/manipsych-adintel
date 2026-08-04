import json
import tempfile
import unittest
from pathlib import Path

from tools.scrape_ads import append_attempt_log, discover_links, extract_candidate, fetch_http, write_record


ROOT = Path(__file__).resolve().parents[1]


class ScrapeAdsTests(unittest.TestCase):
    def test_discovers_target_links(self):
        html = (ROOT / "tests" / "fixtures" / "locanto_sample.html").read_text(encoding="utf-8")
        links = discover_links(html, "https://www.locanto.com.pe/")
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]["url"], "https://www.locanto.com.pe/lima/sample-ad-1.html")

    def test_discovers_locanto_id_links_even_without_target_anchor_text(self):
        html = '<a href="/lima/ID_1234567890/SOME-AD.html">Ver aviso</a>'
        links = discover_links(html, "https://www.locanto.com.pe/")
        self.assertEqual(links[0]["url"], "https://www.locanto.com.pe/lima/ID_1234567890/SOME-AD.html")

    def test_extract_candidate_and_write_redacted_record(self):
        html = (ROOT / "tests" / "fixtures" / "locanto_sample.html").read_text(encoding="utf-8")
        candidate = extract_candidate("Locanto Peru", "https://example.test/ad", html)
        self.assertIsNotNone(candidate)
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.jsonl"
            raw_ref = ROOT / "data" / "raw" / "ads" / "sample.html"
            self.assertTrue(write_record(manifest, candidate, raw_ref))
            record = json.loads(manifest.read_text(encoding="utf-8"))
        self.assertIn("[REDACTED_CONTACT]", record["body_redacted"])
        self.assertNotIn("987654321", record["body_redacted"])
        self.assertEqual(record["source_platform"], "Locanto Peru")

    def test_write_record_caches_and_rejects_duplicates_in_process(self):
        html = (ROOT / "tests" / "fixtures" / "locanto_sample.html").read_text(encoding="utf-8")
        candidate = extract_candidate("Locanto Peru", "https://example.test/ad2", html)
        self.assertIsNotNone(candidate)
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.jsonl"
            raw_ref = ROOT / "data" / "raw" / "ads" / "sample.html"
            self.assertTrue(write_record(manifest, candidate, raw_ref))
            self.assertFalse(write_record(manifest, candidate, raw_ref))
            lines = [line for line in manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(len(lines), 1)

    def test_append_attempt_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "phase4_search_log.json"
            append_attempt_log(
                log,
                [
                    {
                        "url": "https://example.test/search",
                        "fetched": True,
                        "links": 2,
                        "records_written": 1,
                        "error": ""
                    }
                ],
            )
            data = json.loads(log.read_text(encoding="utf-8"))
        self.assertEqual(data["attempts"][0]["result_count"], 1)
        self.assertIn("records_written=1", data["attempts"][0]["notes"])

    def test_fetch_http_uses_provided_session(self):
        class FakeResponse:
            status_code = 200
            text = "<html>ok</html>"

            def raise_for_status(self):
                return None

        class FakeSession:
            def __init__(self):
                self.calls = []

            def get(self, url, timeout=None, allow_redirects=None):
                self.calls.append((url, timeout, allow_redirects))
                return FakeResponse()

        session = FakeSession()
        html = fetch_http("https://example.test/page", timeout=7, session=session)
        self.assertEqual(html, "<html>ok</html>")
        self.assertEqual(session.calls, [("https://example.test/page", 7, True)])


if __name__ == "__main__":
    unittest.main()
