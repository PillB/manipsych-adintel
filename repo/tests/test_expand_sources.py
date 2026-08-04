import unittest

from tools.expand_sources import build_sources


class ExpandSourcesTests(unittest.TestCase):
    def test_generates_many_public_source_candidates(self):
        data = build_sources()
        sources = data["sources"]
        self.assertGreaterEqual(len(sources), 100)
        self.assertTrue(all(source["public_only"] for source in sources))

    def test_generates_locanto_city_tag_url(self):
        urls = {source["url"] for source in build_sources()["sources"]}
        self.assertIn("https://www.locanto.com.pe/lima/tag/ayuda-economica/", urls)
        self.assertIn("https://www.locanto.com.pe/arequipa/tag/apoyo-economico/1/", urls)


if __name__ == "__main__":
    unittest.main()
