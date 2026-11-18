"""Thumbnail-Schlagzeile (Themenbild-Vorlage): die Neugier-Frage am Ende darf nicht abgeschnitten werden (18.11.2026)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from video import weltlage_thumbnail_thema as t  # noqa: E402


class KurzTitelTest(unittest.TestCase):
    def test_frage_bleibt_ganz(self):
        self.assertEqual(t.kurz_titel(["NETANYAHU: 61 SITZE", "– WER KANN STÜRZEN?"]),
                         "NETANYAHU: 61 SITZE – WER KANN STÜRZEN?")

    def test_gedankenstrich_zaehlt_nicht(self):
        self.assertEqual(t.kurz_titel(["IRAN GREIFT AN –", "ÖLPREIS STEIGT"]), "IRAN GREIFT AN – ÖLPREIS STEIGT")

    def test_lange_aussage_wird_weiter_gekuerzt(self):
        self.assertLessEqual(len(t.kurz_titel(["EINS ZWEI DREI VIER FÜNF SECHS SIEBEN ACHT"]).split()), t.MAX_WOERTER)

    def test_zu_lange_frage_gekuerzt(self):
        self.assertLessEqual(len(t.kurz_titel(["A B C D E F G H I J WARUM?"]).split()), t.MAX_WOERTER + 1)

    def test_passt_im_bild(self):
        from PIL import Image, ImageDraw
        d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
        f, zeilen, size = t._schlagzeile_passend(d, t.kurz_titel(["NETANYAHU: 61 SITZE", "– WER KANN STÜRZEN?"]), 700, 720 - 74 - 120 - 150, 170)
        self.assertLessEqual(len(zeilen), 3)
        self.assertIn("STÜRZEN?", zeilen[-1])
        self.assertTrue(all(d.textlength(z, font=f) <= 700 for z in zeilen))


if __name__ == "__main__":
    unittest.main()
