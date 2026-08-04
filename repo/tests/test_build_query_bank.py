import json
import tempfile
import unittest
from pathlib import Path

from tools.build_query_bank import build_queries, normalize_phrase


class BuildQueryBankTests(unittest.TestCase):
    def test_normalize_phrase_removes_generic_terms(self):
        self.assertEqual(normalize_phrase("Brindo ayuda económica a chicas de Lima"), "chicas lima")

    def test_build_queries_includes_city_and_phrase_variants(self):
        titles = ["AYUDA ECONÓMICA A CHICAS", "Brindo ayuda económica para señoritas universitarias"]
        queries = build_queries("locanto", titles, per_platform_limit=3)
        self.assertTrue(any("site:locanto.com.pe" in q for q in queries))
        self.assertTrue(any('"chicas"' in q for q in queries))
        self.assertTrue(any("lima" in q for q in queries))
        self.assertGreaterEqual(len(queries), 5)


if __name__ == "__main__":
    unittest.main()
