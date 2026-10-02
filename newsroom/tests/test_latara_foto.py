"""Tests fuer die Latara-Fotoauswahl nach Stimmung (video/latara_foto.py, Task 20261002-220950-b2d6).

    .venv\\Scripts\\python.exe -m unittest tests.test_latara_foto -v
"""
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from video import latara_foto as lf  # noqa: E402


def _bild(pfad: Path) -> None:
    Image.new("RGBA", (10, 10), (0, 0, 0, 0)).save(pfad)


class LataraFoto(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        self._alt = (lf.ORDNER, lf.INDEX, lf.VERLAUF)
        lf.ORDNER = tmp / "pool"
        lf.INDEX = tmp / "index.json"
        lf.VERLAUF = tmp / "verlauf.json"
        lf.ORDNER.mkdir()
        for name in ("latara_geschockt_a.png", "latara_geschockt_b.png", "latara_geschockt_c.png",
                     "latara_with_paper_in_hand.png", "latara_unbekannte_pose.png"):
            _bild(lf.ORDNER / name)

    def tearDown(self):
        lf.ORDNER, lf.INDEX, lf.VERLAUF = self._alt
        self._tmp.cleanup()

    def test_index_erkennt_dateinamen_und_markiert_unbekannte(self):
        idx = lf.lade_index()
        self.assertEqual(idx["latara_geschockt_a.png"]["stimmungen"], ["geschockt"])
        self.assertIn("papier", idx["latara_with_paper_in_hand.png"]["stimmungen"])
        self.assertEqual(idx["latara_unbekannte_pose.png"]["quelle"], "ungeklaert")
        self.assertTrue(lf.INDEX.exists())

    def test_index_laesst_handklassifizierte_eintraege_in_ruhe(self):
        lf.lade_index()
        idx = lf.lade_index()
        idx["latara_with_paper_in_hand.png"]["stimmungen"].append("laechelnd")
        lf.INDEX.write_text(__import__("json").dumps(idx, ensure_ascii=False), encoding="utf-8")
        idx2 = lf.lade_index()
        self.assertIn("laechelnd", idx2["latara_with_paper_in_hand.png"]["stimmungen"])

    def test_index_entfernt_geloeschte_dateien(self):
        lf.lade_index()
        (lf.ORDNER / "latara_geschockt_a.png").unlink()
        idx = lf.lade_index()
        self.assertNotIn("latara_geschockt_a.png", idx)

    def test_stimmung_aus_text_erkennt_schock(self):
        rang = lf.stimmung_aus_text("Putin droht mit Eskalation, Nato im Alarm")
        self.assertEqual(rang[0], "geschockt")

    def test_waehle_foto_passend_zur_stimmung(self):
        pfad = lf.waehle_foto("Eskalation und Chaos an der Grenze", merken=False)
        self.assertIsNotNone(pfad)
        self.assertIn("geschockt", pfad.name)

    def test_waehle_foto_merken_false_schreibt_keinen_verlauf(self):
        lf.waehle_foto("Eskalation und Chaos", merken=False)
        self.assertEqual(lf._verlauf_lesen(), [])

    def test_waehle_foto_wiederholt_nicht_die_letzten_folgen(self):
        gezeigt = {lf.waehle_foto("Eskalation und Chaos", merken=True).name for _ in range(3)}
        self.assertEqual(len(gezeigt), 3)   # alle 3 geschockt-Bilder genutzt, kein Bild zweimal

    def test_waehle_foto_ohne_ordner_gibt_none(self):
        lf.ORDNER = lf.ORDNER / "fehlt"
        self.assertIsNone(lf.waehle_foto("irgendwas"))


if __name__ == "__main__":
    unittest.main()
