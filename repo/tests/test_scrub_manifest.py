import json
import tempfile
import unittest
from pathlib import Path

from tools.scrub_manifest import scrub_manifest
from tools.scrub_invalid_ads import scrub_invalid_ads


class ScrubManifestTests(unittest.TestCase):
    def test_scrubs_body_redacted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.jsonl"
            path.write_text(json.dumps({"title": "x", "body_redacted": "wsp: +51 999 888 777"}) + "\n")
            changed = scrub_manifest(path)
            record = json.loads(path.read_text())
        self.assertEqual(changed, 1)
        self.assertEqual(record["body_redacted"], "[REDACTED_CONTACT]")

    def test_scrub_invalid_ads_drops_interstitial_and_duplicate_raw(self):
        with tempfile.TemporaryDirectory() as tmp:
            root_like = Path.cwd()
            raw_dir = root_like / "data" / "raw" / "ads"
            good_raw = raw_dir / "unit_good_scrub_test.html"
            bad_raw = raw_dir / "unit_bad_scrub_test.html"
            good_raw.write_text("<html><title>Brindo ayuda</title><body><h1>Brindo ayuda económica</h1><article>Descripción real de anuncio público.</article></body></html>", encoding="utf-8")
            bad_raw.write_text("<html><title>Un momento…</title><body>Estamos verificando tu navegador antes de acceder a Locanto. En breve seras redirigido.</body></html>", encoding="utf-8")
            path = Path(tmp) / "manifest.jsonl"
            records = [
                {"record_id": "1", "source_platform": "Locanto Peru", "source_url_hash": "1", "title": "Brindo ayuda", "body_redacted": "Brindo ayuda económica a señorita.", "raw_archive_ref": "data/raw/ads/unit_good_scrub_test.html"},
                {"record_id": "2", "source_platform": "Locanto Peru", "source_url_hash": "2", "title": "Otro", "body_redacted": "Brindo ayuda económica.", "raw_archive_ref": "data/raw/ads/unit_good_scrub_test.html"},
                {"record_id": "3", "source_platform": "Locanto Peru", "source_url_hash": "3", "title": "Un momento", "body_redacted": "Estamos verificando tu navegador.", "raw_archive_ref": "data/raw/ads/unit_bad_scrub_test.html"},
            ]
            path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
            try:
                result = scrub_invalid_ads(path)
                kept = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
            finally:
                good_raw.unlink(missing_ok=True)
                bad_raw.unlink(missing_ok=True)
        self.assertEqual(result["kept_records"], 1)
        self.assertEqual(kept[0]["record_id"], "1")
        self.assertIn("duplicate_raw_ref", result["removal_reasons"])
        self.assertIn("raw_interstitial", result["removal_reasons"])

    def test_scrub_invalid_ads_drops_duplicate_record_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root_like = Path.cwd()
            raw_dir = root_like / "data" / "raw" / "ads"
            good_raw_a = raw_dir / "unit_good_scrub_dup_a.html"
            good_raw_b = raw_dir / "unit_good_scrub_dup_b.html"
            good_raw_a.write_text("<html><title>Brindo ayuda</title><body><h1>Brindo ayuda económica</h1><article>Descripción real de anuncio público A.</article></body></html>", encoding="utf-8")
            good_raw_b.write_text("<html><title>Brindo ayuda</title><body><h1>Brindo ayuda económica</h1><article>Descripción real de anuncio público B.</article></body></html>", encoding="utf-8")
            path = Path(tmp) / "manifest.jsonl"
            records = [
                {"record_id": "dup", "source_platform": "Locanto Peru", "source_url_hash": "dup", "title": "Brindo ayuda", "body_redacted": "Brindo ayuda económica A.", "raw_archive_ref": "data/raw/ads/unit_good_scrub_dup_a.html"},
                {"record_id": "dup", "source_platform": "Locanto Peru", "source_url_hash": "dup", "title": "Brindo ayuda", "body_redacted": "Brindo ayuda económica B.", "raw_archive_ref": "data/raw/ads/unit_good_scrub_dup_b.html"},
            ]
            path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
            try:
                result = scrub_invalid_ads(path)
                kept = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
            finally:
                good_raw_a.unlink(missing_ok=True)
                good_raw_b.unlink(missing_ok=True)
        self.assertEqual(result["kept_records"], 1)
        self.assertEqual(len(kept), 1)
        self.assertIn("duplicate_record_id", result["removal_reasons"])


if __name__ == "__main__":
    unittest.main()
