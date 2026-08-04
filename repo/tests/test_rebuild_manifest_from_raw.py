import json
import tempfile
import unittest
from pathlib import Path

from tools.rebuild_manifest_from_raw import rebuild_manifest


LOCANTO_HTML = """
<html>
<head>
  <title>Brindo apoyo economico, Lima</title>
  <link rel="canonical" href="https://www.locanto.com.pe/lima/ID_123/Brindo-apoyo-economico.html">
</head>
<body>
  <h1>Brindo apoyo economico, Lima</h1>
  <div class="simple__description">Soy caballero profesional y brindo apoyo economico discreto a una estudiante.</div>
  <div class="js-followers_counter">3 Seguidores</div>
  <script>
    yalwa.v.posting_id = '123';
    yalwa.v.userID_viewed = '456';
    yalwa.v.pf_posting = true;
  </script>
  <span class="posting_listing__counter">2</span>
</body>
</html>
"""

FACEBOOK_HTML = """
<html>
<head>
  <title>Grupo | Doy ayuda economica urgente | Facebook</title>
  <meta property="og:url" content="https://www.facebook.com/groups/123456/posts/789">
  <meta property="og:title" content="Doy ayuda economica urgente">
  <meta property="og:description" content="Doy ayuda economica urgente por apoyo familiar. 12 reacciones 4 comentarios">
</head>
<body>Doy ayuda economica urgente por apoyo familiar. 12 reacciones 4 comentarios. Esta copia publica incluye texto suficiente para validar el registro.</body>
</html>
"""

INTERSTITIAL_HTML = """
<html><head><title>Un momento</title></head>
<body>Cloudflare captcha verify you are human. Estamos verificando tu navegador antes de acceder.
Contenido repetido para superar el umbral minimo de tamano sin dejar de ser una pagina de bloqueo.
Contenido repetido para superar el umbral minimo de tamano sin dejar de ser una pagina de bloqueo.
Contenido repetido para superar el umbral minimo de tamano sin dejar de ser una pagina de bloqueo.
Contenido repetido para superar el umbral minimo de tamano sin dejar de ser una pagina de bloqueo.
</body></html>
"""

SEEKER_HTML = """
<html><head><title>Busco ayuda economica</title></head>
<body>Busco ayuda economica para estudiante universitaria.
Esta pagina tiene texto adicional para parecer un registro real pero no contiene una oferta masculina de apoyo.
Busco apoyo para gastos de estudios, alquiler y transporte, sin ninguna frase de oferta masculina de ayuda.
El filtro debe rechazarla porque representa una solicitud de ayuda y no el tipo de anuncio objetivo.
Otra linea de texto neutral aumenta el tamano del HTML de prueba sin introducir señales de oferta.
</body></html>
"""

PII_HTML = """
<html><head><title>Brindo ayuda economica</title></head>
<body>Brindo ayuda economica por whatsapp 999888777 a estudiante.
Texto adicional de contexto publico para que el archivo supere el umbral minimo de tamano y contenido real.
Soy caballero profesional y ofrezco apoyo economico discreto con detalles por mensaje privado.
Este registro sirve para verificar que la salida procesada conserva el contenido defensivo pero elimina datos de contacto.
La descripcion contiene suficiente extension para simular una pagina publica archivada y no una respuesta vacia o corrupta.
</body></html>
"""


class RebuildManifestFromRawTests(unittest.TestCase):
    def run_rebuild(self, files):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_dir = root / "data" / "raw" / "ads"
            raw_dir.mkdir(parents=True)
            manifest = root / "data" / "processed" / "ad_manifest.jsonl"
            summary_path = root / "reports" / "raw_rebuild_summary.json"
            for name, content in files.items():
                (raw_dir / name).write_text(content, encoding="utf-8")
            summary = rebuild_manifest(raw_dir, manifest, summary_path, backup=False, root=root)
            records = [
                json.loads(line)
                for line in manifest.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            return summary, records

    def test_rebuild_extracts_locanto_quality_signals(self):
        summary, records = self.run_rebuild({"locanto.html": LOCANTO_HTML})
        self.assertEqual(summary["records_written"], 1)
        metadata = records[0]["metadata"]
        self.assertEqual(metadata["platform_family"], "locanto")
        self.assertTrue(metadata["is_paid_or_premium_marker"])
        self.assertEqual(metadata["followers_count"], 3)
        self.assertEqual(metadata["image_count"], 2)
        self.assertIn("posting_hash", metadata)
        self.assertNotIn("https://www.locanto.com.pe", json.dumps(records[0]))

    def test_rebuild_extracts_facebook_aggregate_engagement(self):
        summary, records = self.run_rebuild({"facebook.html": FACEBOOK_HTML})
        self.assertEqual(summary["records_written"], 1)
        metadata = records[0]["metadata"]
        self.assertEqual(metadata["platform_family"], "facebook")
        self.assertEqual(metadata["facebook_reactions_approx"], 12)
        self.assertEqual(metadata["facebook_comments_approx"], 4)
        self.assertTrue(metadata["facebook_group_present"])

    def test_rebuild_rejects_duplicates_invalid_and_redacts_pii(self):
        duplicate = LOCANTO_HTML.replace("locanto.html", "other.html")
        summary, records = self.run_rebuild(
            {
                "a.html": LOCANTO_HTML,
                "b.html": duplicate,
                "interstitial.html": INTERSTITIAL_HTML,
                "seeker.html": SEEKER_HTML,
                "pii.html": PII_HTML,
            }
        )
        self.assertEqual(len(records), 2)
        self.assertEqual(summary["reject_counts"]["duplicate_record_id"], 1)
        self.assertEqual(summary["reject_counts"]["access_interstitial"], 1)
        self.assertEqual(summary["reject_counts"]["seeker_only"], 1)
        serialized = "\n".join(json.dumps(record, ensure_ascii=False) for record in records)
        self.assertNotIn("999888777", serialized)


if __name__ == "__main__":
    unittest.main()
