import unittest

from tools.redact_pii import redact_text


class RedactPiiTests(unittest.TestCase):
    def test_redacts_peru_mobile_number_and_email(self):
        text = "Contactar al 987654321 o persona@example.com para detalles."
        redacted = redact_text(text)
        self.assertNotIn("987654321", redacted)
        self.assertNotIn("persona@example.com", redacted)
        self.assertIn("[REDACTED_PHONE]", redacted)
        self.assertIn("[REDACTED_EMAIL]", redacted)

    def test_redacts_whatsapp_labelled_contact(self):
        text = "wsp: +51 999 888 777"
        self.assertEqual(redact_text(text), "[REDACTED_CONTACT]")

    def test_redacts_obfuscated_phone_and_telegram(self):
        text = "Whatsapp  941(531 002 Telegram: trader01235"
        redacted = redact_text(text)
        self.assertNotIn("941", redacted)
        self.assertNotIn("trader01235", redacted)
        self.assertIn("[REDACTED_CONTACT]", redacted)

    def test_redacts_word_obfuscated_phone(self):
        text = "escribeme al 9diecisiete34seis20cero"
        redacted = redact_text(text)
        self.assertNotIn("9diecisiete34seis20cero", redacted)

    def test_redacts_glued_wsp_and_phone_from_scraped_text(self):
        text = "QUINCENAL S/. 850WSP: 902860342Me gustaComentarCompartir"
        redacted = redact_text(text)
        self.assertNotIn("902860342", redacted)
        self.assertIn("[REDACTED_PHONE]", redacted)


if __name__ == "__main__":
    unittest.main()
