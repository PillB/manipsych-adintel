import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.collect_hombre_locanto import (
    fetch_http_first_after_delay,
    next_locanto_listing_url,
    search_ddg_directs_after_delay,
    shard_items as select_shard,
)
from tools.run_phase4_parallel import build_jobs, merge_manifests, shard_items as partition_shards


class RunPhase4ParallelTests(unittest.TestCase):
    def test_shard_items_evenly_partitions(self):
        self.assertEqual(select_shard(["a", "b", "c", "d", "e"], 0, 2), ["a", "c", "e"])
        self.assertEqual(select_shard(["a", "b", "c", "d", "e"], 1, 2), ["b", "d"])
        self.assertEqual(partition_shards(["a", "b", "c", "d", "e"], 2), [["a", "c", "e"], ["b", "d"]])

    def test_merge_manifests_deduplicates_record_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            m1 = tmp / "m1.jsonl"
            m2 = tmp / "m2.jsonl"
            out = tmp / "merged.jsonl"
            rec1 = {"record_id": "r1", "title": "a"}
            rec2 = {"record_id": "r2", "title": "b"}
            rec3 = {"record_id": "r1", "title": "dup"}
            m1.write_text("\n".join(json.dumps(r) for r in [rec1, rec2]) + "\n", encoding="utf-8")
            m2.write_text(json.dumps(rec3) + "\n", encoding="utf-8")
            stats = merge_manifests([m1, m2], out)
            lines = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(stats["kept"], 2)
        self.assertEqual(stats["duplicate_or_empty"], 1)
        self.assertEqual([rec["record_id"] for rec in lines], ["r1", "r2"])

    def test_next_locanto_listing_url_increments_slash_pages(self):
        self.assertEqual(
            next_locanto_listing_url("https://www.locanto.com.pe/lima/Hombre-busca-mujer/20701/", 1),
            "https://www.locanto.com.pe/lima/Hombre-busca-mujer/20701/1/",
        )
        self.assertEqual(
            next_locanto_listing_url("https://www.locanto.com.pe/lima/Hombre-busca-mujer/20701/1/", 2),
            "https://www.locanto.com.pe/lima/Hombre-busca-mujer/20701/2/",
        )

    def test_fetch_http_first_after_delay_waits_before_fetch(self):
        with patch("tools.collect_hombre_locanto.time.sleep") as sleep_mock, patch(
            "tools.collect_hombre_locanto.fetch_http_first",
            return_value="<html>ok</html>",
        ) as fetch_mock:
            html = fetch_http_first_after_delay("https://example.test", 12, 2, 0.75)
        self.assertEqual(html, "<html>ok</html>")
        sleep_mock.assert_called_once_with(0.75)
        fetch_mock.assert_called_once_with("https://example.test", 12, 2)

    def test_search_ddg_directs_after_delay_waits_before_search(self):
        with patch("tools.collect_hombre_locanto.time.sleep") as sleep_mock, patch(
            "tools.collect_hombre_locanto.search_ddg_directs",
            return_value=["https://example.test/ID_1.html"],
        ) as search_mock:
            urls = search_ddg_directs_after_delay("site:example.test", 10, 0.5)
        self.assertEqual(urls, ["https://example.test/ID_1.html"])
        sleep_mock.assert_called_once_with(0.5)
        search_mock.assert_called_once_with("site:example.test", 10)

    def test_search_ddg_directs_uses_shared_http_session(self):
        class DummyResponse:
            text = """
            <html>
              <a class="result__a" href="https://www.locanto.com.pe/lima/Hombre-busca-mujer/ID_1234567890.html">x</a>
            </html>
            """

        class DummySession:
            def __init__(self):
                self.headers = {"User-Agent": "original"}
                self.calls = []

            def get(self, url, timeout, allow_redirects, headers=None):
                self.calls.append((url, timeout, allow_redirects, headers))
                return DummyResponse()

        dummy_session = DummySession()
        with patch("tools.collect_hombre_locanto.get_http_session", return_value=dummy_session) as session_mock:
            urls = search_ddg_directs_after_delay("site:locanto.com.pe ID_", 5, 0.0)
        self.assertEqual(urls, ["https://www.locanto.com.pe/lima/Hombre-busca-mujer/ID_1234567890.html"])
        session_mock.assert_called_once()
        self.assertEqual(len(dummy_session.calls), 1)
        self.assertEqual(dummy_session.headers["User-Agent"], "original")

    def test_build_jobs_propagates_locanto_throughput_flags(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = type(
                "Args",
                (),
                {
                    "scratch_dir": Path(tmp),
                    "locanto_cities": "lima,arequipa",
                    "locanto_shards": 2,
                    "locanto_max_ads": 7,
                    "locanto_direct_only": False,
                    "locanto_direct_workers": 9,
                    "locanto_search_workers": 5,
                    "locanto_search_delay_min": 0.1,
                    "locanto_search_delay_max": 0.3,
                    "locanto_list_workers": 4,
                    "locanto_listing_pages": 2,
                    "locanto_skip_ddg": True,
                    "seed_platform": "doplim",
                    "seed_shards": 1,
                    "seed_max_fetch": 3,
                    "seed_timeout_ms": 1000,
                    "seed_retries": 1,
                    "seed_delay": 0.0,
                    "seed_workers": 6,
                },
            )()
            jobs, _ = build_jobs(args)
        locanto_cmd = " ".join(jobs[0].command)
        self.assertIn("--direct-workers 9", locanto_cmd)
        self.assertIn("--search-workers 5", locanto_cmd)
        self.assertIn("--search-delay-min 0.1", locanto_cmd)
        self.assertIn("--search-delay-max 0.3", locanto_cmd)
        self.assertIn("--list-workers 4", locanto_cmd)
        self.assertIn("--listing-pages 2", locanto_cmd)

    def test_build_jobs_propagates_manifest_state_to_seed_workers(self):
        with tempfile.TemporaryDirectory() as tmp:
            scratch = Path(tmp)
            output_manifest = scratch / "output.jsonl"
            output_manifest.write_text(
                json.dumps(
                    {
                        "record_id": "abc",
                        "raw_archive_ref": "data/raw/ads/x.html",
                        "metadata": {"original_url": "https://example.test/a"},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            args = type(
                "Args",
                (),
                {
                    "scratch_dir": scratch,
                    "output_manifest": output_manifest,
                    "locanto_cities": "lima",
                    "locanto_shards": 1,
                    "locanto_max_ads": 1,
                    "locanto_direct_only": True,
                    "locanto_direct_workers": 1,
                    "locanto_search_workers": 1,
                    "locanto_search_delay_min": 0.0,
                    "locanto_search_delay_max": 0.0,
                    "locanto_list_workers": 1,
                    "locanto_listing_pages": 1,
                    "locanto_skip_ddg": True,
                    "seed_platform": "doplim",
                    "seed_shards": 1,
                    "seed_max_fetch": 1,
                    "seed_timeout_ms": 1000,
                    "seed_retries": 1,
                    "seed_delay": 0.0,
                    "seed_workers": 2,
                },
            )()
            jobs, _ = build_jobs(args)
        seed_cmd = " ".join(jobs[-1].command)
        self.assertIn("--manifest-state", seed_cmd)
        self.assertIn(".state.json", seed_cmd)


if __name__ == "__main__":
    unittest.main()
