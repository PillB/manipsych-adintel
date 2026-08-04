import unittest

from tools.scrape_ads import is_access_interstitial


class ScrapeInterstitialTests(unittest.TestCase):
    def test_detects_captcha_interstitial(self):
        html = "<html><head><title>Un momento…</title></head><body>captcha requerido</body></html>"
        self.assertTrue(is_access_interstitial(html))

    def test_detects_locanto_browser_verification_message(self):
        html = """
        <html><head><title>Un momento…</title></head>
        <body>Estamos verificando tu navegador antes de acceder a Locanto.
        Este proceso es automático. En breve seras redirigido a la página solicitada.</body></html>
        """
        self.assertTrue(is_access_interstitial(html))

    def test_allows_normal_listing_html(self):
        html = "<html><head><title>Ayuda económica Lima</title></head><body>999+ Resultados</body></html>"
        self.assertFalse(is_access_interstitial(html))

    def test_allows_locanto_app_banner_inside_real_ad(self):
        html = """
        <html><head><title>Brindo ayuda económica a señorita, Lima</title></head>
        <body><h1>Brindo ayuda económica a señorita, Lima</h1>
        Nueva app disponible ¡Compra, vende y conecta al instante! Instalar
        <article><section class="description">Descripción Soy hombre y brindo apoyo económico a señorita estudiante con respeto y discreción.</section></article>
        </body></html>
        """
        self.assertFalse(is_access_interstitial(html))


if __name__ == "__main__":
    unittest.main()
