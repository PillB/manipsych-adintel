import unittest

from tools.discover_sources import extract_ddg_result_urls, is_soft_challenge


class DiscoverSourcesTests(unittest.TestCase):
    def test_extracts_duckduckgo_redirect_target(self):
        html = 'href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.locanto.com.pe%2Flima%2Ftag%2Fayuda-economica%2F"'
        urls = extract_ddg_result_urls(html)
        self.assertEqual(urls, ["https://www.locanto.com.pe/lima/tag/ayuda-economica/"])

    def test_detects_soft_challenge(self):
        self.assertTrue(is_soft_challenge("<html>captcha anomaly</html>"))


if __name__ == "__main__":
    unittest.main()
