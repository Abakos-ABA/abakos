"""Tests fuer die feste Rechts-Platzierung von Latara im Weltlage-Thumbnail (Task 20261002-222340-0165):
sie steht immer ganz rechts am Bildrand und reicht nie in die Textzone, egal wie breit die Pose im Foto ist.

    .venv\\Scripts\\python.exe -m unittest tests.test_weltlage_thumbnail -v
"""
import sys
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from video import weltlage_thumbnail as wt  # noqa: E402

# Rechte Kante der Textzone: render() beginnt den Schlagschatten bei bx-4 mit Breite TEXT_BREITE; etwas
# Sicherheitsabstand fuer die weiche Schlagschatten-Unschaerfe kommt dazu.
TEXT_GRENZE = wt.LEISTE + 34 - 4 + wt.TEXT_BREITE


def _opake_breite(breite: int, hoehe: int, opak_von: int, opak_bis: int) -> Image.Image:
    """Testfoto: RGBA-Bild mit einem undurchsichtigen Streifen [opak_von, opak_bis) - simuliert eine Person
    unterschiedlicher Pose-Breite/-Position, ohne echte Fotos zu brauchen."""
    im = Image.new("RGBA", (breite, hoehe), (0, 0, 0, 0))
    ImageDraw.Draw(im).rectangle((opak_von, 0, opak_bis - 1, hoehe - 1), fill=(200, 150, 120, 255))
    return im


class Platzierung(unittest.TestCase):
    def test_schmales_foto_bleibt_unveraendert(self):
        im = _opake_breite(400, 700, 50, 350)
        begrenzt = wt._sichtbare_breite_begrenzen(im)
        self.assertEqual(begrenzt.size, im.size)

    def test_breites_foto_wird_verkleinert_nicht_zugeschnitten(self):
        im = _opake_breite(1200, 700, 0, 1200)   # Person so breit wie das ganze Foto (Extremfall)
        begrenzt = wt._sichtbare_breite_begrenzen(im)
        self.assertLess(begrenzt.width, im.width)
        self.assertLess(begrenzt.height, im.height)   # proportional verkleinert, nicht seitlich zugeschnitten
        bbox = begrenzt.split()[3].point(lambda v: 255 if v > wt.ALPHA_SCHWELLE else 0).getbbox()
        self.assertLessEqual(bbox[2] - bbox[0], wt.MAX_PERSON_BREITE)

    def test_platzierung_reicht_nie_in_die_textzone(self):
        faelle = [(708, 139, 620), (708, 0, 708), (1158, 235, 1158), (1310, 0, 1310), (663, 0, 663)]
        for breite, opak_von, opak_bis in faelle:
            with self.subTest(breite=breite, opak_von=opak_von, opak_bis=opak_bis):
                im = wt._sichtbare_breite_begrenzen(_opake_breite(breite, 700, opak_von, opak_bis))
                x = wt._platzierung_x(im)
                bbox = im.split()[3].point(lambda v: 255 if v > wt.ALPHA_SCHWELLE else 0).getbbox()
                self.assertGreaterEqual(x + bbox[0], TEXT_GRENZE)

    def test_sichtbarer_rechter_rand_ragt_immer_gleich_weit_ueber_den_bildrand(self):
        for breite, opak_von, opak_bis in [(708, 139, 620), (900, 0, 500)]:
            im = wt._sichtbare_breite_begrenzen(_opake_breite(breite, 700, opak_von, opak_bis))
            x = wt._platzierung_x(im)
            bbox = im.split()[3].point(lambda v: 255 if v > wt.ALPHA_SCHWELLE else 0).getbbox()
            self.assertEqual(x + bbox[2], wt.W + wt.PERSON_BLEED)


class PlatzierungMitEchtenFotos(unittest.TestCase):
    """Task-Vorgabe: mit allen Fotos aus Marlons echtem Pool-Ordner testen. Wird uebersprungen, wenn der
    Ordner auf dieser Maschine nicht eingebunden ist."""

    def test_keine_ueberlappung_mit_der_textzone(self):
        from video import latara_foto as lf
        if not lf.ORDNER.is_dir():
            self.skipTest("Marlons Foto-Ordner ist auf dieser Maschine nicht eingebunden")
        fotos = [p for p in lf.ORDNER.iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg")]
        if not fotos:
            self.skipTest("Marlons Foto-Ordner ist leer")
        fc = wt.FARBEN["konflikt"]
        for pfad in fotos:
            with self.subTest(foto=pfad.name):
                lat, _ = wt._latara(pfad, fc)
                x = wt._platzierung_x(lat)
                bbox = lat.split()[3].point(lambda v: 255 if v > wt.ALPHA_SCHWELLE else 0).getbbox()
                self.assertIsNotNone(bbox)
                self.assertGreaterEqual(x + bbox[0], TEXT_GRENZE)


if __name__ == "__main__":
    unittest.main()
