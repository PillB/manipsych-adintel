import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.collect_seed_inventory import (
    classify_platform,
    collect,
    extract_title_body,
    get_facebook_variants,
    has_excluded_minor_signal,
    has_male_offering_signal,
    has_target_terms,
    is_direct_candidate,
    is_likely_seeker_side,
    load_seeds,
    load_manifest_state_snapshot,
    normalize_facebook_url,
    update_attempt_log,
)


class CollectSeedInventoryTests(unittest.TestCase):
    def test_classifies_direct_platforms(self):
        self.assertEqual(
            classify_platform("https://www.locanto.com.pe/lima/ID_1234567890/Test.html"),
            "Locanto Peru (hombre busca mujer real)",
        )
        self.assertEqual(
            classify_platform("https://doplim.com.pe/doy-ayuda-id-123"),
            "Doplim Peru (hombre busca mujer or Contactos)",
        )
        self.assertEqual(
            classify_platform("https://callao.doplim.com.pe/si-eres-gordita-te-doy-la-ayuda-economica-id-416701.html"),
            "Doplim Peru (hombre busca mujer or Contactos)",
        )
        self.assertEqual(
            classify_platform("https://www.facebook.com/groups/1/posts/2/"),
            "Facebook Public (indexed)",
        )

    def test_text_filters(self):
        self.assertTrue(has_target_terms("Brindo apoyo económico a señorita"))
        self.assertTrue(has_male_offering_signal("Caballero solvente brinda ayuda"))
        self.assertTrue(has_excluded_minor_signal("busco colegialas"))
        self.assertTrue(has_excluded_minor_signal("no importa la edad doy ayuda"))
        self.assertTrue(has_excluded_minor_signal("doy ayuda a chica pequeña"))
        self.assertTrue(has_excluded_minor_signal("ayuda economica pulpines"))
        self.assertTrue(is_likely_seeker_side("Alondra necesito ayuda económica por terminal"))
        self.assertFalse(is_likely_seeker_side("Caballero brinda ayuda económica discreta"))

    def test_load_seeds_keeps_unused_direct_target_urls(self):
        with tempfile.TemporaryDirectory() as tmp:
            seeds = Path(tmp) / "seeds.jsonl"
            rows = [
                {"url": "https://www.locanto.com.pe/lima/ID_1234567890/Brindo-ayuda-economica.html", "text": "Brindo ayuda económica"},
                {"url": "https://callao.doplim.com.pe/brindo-ayuda-economica-id-123.html", "title": "Brindo ayuda económica"},
                {"url": "https://www.locanto.com.pe/lima/tag/ayuda-economica/", "text": "listing"},
                {"url": "https://example.com/x", "text": "ayuda economica"},
            ]
            seeds.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            loaded = load_seeds(seeds, "locanto")
            doplim = load_seeds(seeds, "doplim")
        self.assertEqual(len(loaded), 1)
        self.assertIn("/ID_1234567890/", loaded[0].url)
        self.assertEqual(len(doplim), 1)

    def test_update_attempt_log_accepts_legacy_list_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "attempts.json"
            log_path.write_text(json.dumps([{"query": "legacy", "result_count": 1}]), encoding="utf-8")
            update_attempt_log(log_path, "doplim", {"added": 2, "attempted": 2}, 2)
            data = json.loads(log_path.read_text(encoding="utf-8"))
        self.assertEqual(data["status"], "exhaustive")
        self.assertEqual(len(data["attempts"]), 2)
        self.assertEqual(data["attempts"][-1]["result_count"], 2)

    def test_update_attempt_log_flattens_legacy_nested_attempts(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "attempts.json"
            log_path.write_text(
                json.dumps(
                    [
                        {"status": "exhaustive", "attempts": [{"query": "old", "result_count": 1}]},
                        {"query": "appended", "result_count": 3},
                    ]
                ),
                encoding="utf-8",
            )
            update_attempt_log(log_path, "locanto", {"added": 1}, 1)
            data = json.loads(log_path.read_text(encoding="utf-8"))
        self.assertEqual(data["status"], "exhaustive")
        self.assertEqual([attempt["result_count"] for attempt in data["attempts"]], [1, 3, 1])

    def test_load_manifest_state_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = Path(tmp) / "snapshot.json"
            snapshot.write_text(
                json.dumps(
                    {
                        "record_ids": ["a", "b"],
                        "raw_refs": ["x", "y"],
                        "urls": ["https://example.test/a", "https://example.test/b"],
                    }
                ),
                encoding="utf-8",
            )
            record_ids, raw_refs, urls = load_manifest_state_snapshot(snapshot)
        self.assertEqual(record_ids, {"a", "b"})
        self.assertEqual(raw_refs, {"x", "y"})
        self.assertEqual(urls, {"https://example.test/a", "https://example.test/b"})

    def test_collect_http_parallel_skips_browser_startup(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            seeds = tmp_path / "seeds.jsonl"
            manifest = tmp_path / "manifest.jsonl"
            raw_dir = tmp_path / "raw"
            attempt_log = tmp_path / "attempts.json"
            seeds.write_text(
                json.dumps(
                    {
                        "url": "https://www.locanto.com.pe/lima/ID_1234567890/Brindo-ayuda-economica.html",
                        "text": "Brindo ayuda económica",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            args = type(
                "Args",
                (),
                {
                    "seeds": seeds,
                    "manifest": manifest,
                    "raw_dir": raw_dir,
                    "attempt_log": attempt_log,
                    "rejected_urls": tmp_path / "rejected.json",
                    "platform": "locanto",
                    "max_fetch": 1,
                    "timeout_ms": 15000,
                    "retries": 1,
                    "delay": 0.0,
                    "min_body_chars": 20,
                    "raw_prefix": "seed_inventory",
                    "shuffle": False,
                    "seed_shard_index": 0,
                    "seed_shard_count": 1,
                    "workers": 4,
                    "http_only": True,
                    "verbose": False,
                },
            )()
            with patch("tools.collect_seed_inventory.open_browser_context", side_effect=AssertionError("browser should not start")), patch(
                "tools.collect_seed_inventory.fetch_page_http_first",
                return_value="<html><head><title>Brindo ayuda económica</title></head><body><h1>Brindo ayuda económica</h1><article>Brindo apoyo económico a señorita estudiante.</article></body></html>",
            ), patch("tools.collect_seed_inventory.process_fetched_html", return_value=True):
                result = collect(args)
        self.assertFalse(result["browser_failed"])
        self.assertEqual(result["stats"]["added"], 1)

    def test_normalize_facebook_url_stable_forms(self):
        self.assertEqual(
            normalize_facebook_url("https://m.facebook.com/groups/123/posts/456?fbclid=xxx&ref=1"),
            "https://www.facebook.com/groups/123/posts/456",
        )
        self.assertEqual(
            normalize_facebook_url("https://facebook.com/groups/foo/permalink/999"),
            "https://www.facebook.com/groups/foo/permalink/999",
        )

    def test_get_facebook_variants_includes_m_and_www(self):
        vs = get_facebook_variants("https://www.facebook.com/groups/1/posts/2")
        self.assertTrue(any("m.facebook.com" in v for v in vs))
        self.assertTrue(any("www.facebook.com" in v for v in vs))

    def test_is_direct_candidate_fb_broad_patterns(self):
        self.assertTrue(is_direct_candidate("https://www.facebook.com/groups/123/permalink/456/"))
        self.assertTrue(is_direct_candidate("https://facebook.com/groups/abc/posts/789"))
        self.assertTrue(is_direct_candidate("https://m.facebook.com/story.php?story_fbid=1"))

    def test_extract_title_body_fb_og_and_user_content(self):
        html = (
            '<html><meta property="og:title" content="Brindo ayuda economica a señoritas">'
            '<div class="userContent">Doy apoyo economico a universitarias en Lima discreto.</div></html>'
        )
        t, b = extract_title_body(html)
        self.assertIn("Brindo ayuda", t)
        self.assertIn("apoyo economico", b)


if __name__ == "__main__":
    unittest.main()
