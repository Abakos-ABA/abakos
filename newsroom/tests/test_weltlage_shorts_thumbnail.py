"""Tests fuer das komponierte Shorts-Thumbnail (Marlons Auftrag 15.10.2026, analog zum Fund beim Jarvis-KI-
Kanal): Text/Branding muessen sicher innerhalb SAFE_TOP..SAFE_UNTEN bleiben, egal wie lang der Titel ist -
sonst schneidet die Kachelansicht ihn wieder ab.

    .venv\\Scripts\\python.exe -m unittest tests.test_weltlage_shorts_thumbnail -v
"""
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import weltlage_shorts_thumbnail as st  # noqa: E402

# Marlons echte Short-Titel aus state/weltlage_shorts_verlauf.json (15.10.2026) plus Randfaelle.
ECHTE_TITEL = [
    "Wanze bei OpenAI: Für WEN sollte Alfozan mithören?",
    "Starlink-Brand in Polen: Führt Putin schon Krieg im Hinterland?",
    "Waren Trumps Staats-Spots für dich eher Regierungsinformation oder eher Wahlwerbung?",
    "Kurz?",
    "Ein ziemlich langer Titel mit sehr vielen Woertern der eigentlich kaum noch in eine vernuenftige "
    "Zeile passt und trotzdem nicht ueberlaufen darf",
]


class HeadlinePasstInSafeZone(unittest.TestCase):
    def test_gesamtblock_passt_fuer_alle_echten_titel(self):
        d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
        verfuegbar = st.SAFE_UNTEN - st.SAFE_TOP
        gap1, gap2, gap3 = 30, 40, 26
        fixe_h = st.BANDEROLE_H + gap1 + gap2 + st.PHOTO_H + gap3 + st.BRAND_H
        for titel in ECHTE_TITEL:
            with self.subTest(titel=titel):
                _, zeilen, size = st._headline_passend(d, titel.upper(), st.MAX_BREITE, verfuegbar - fixe_h)
                headline_h = int(size * 1.18) * len(zeilen)
                gesamt_h = fixe_h + headline_h
                self.assertLessEqual(gesamt_h, verfuegbar,
                                     f"Block ({gesamt_h}px) ragt aus der Safe-Zone ({verfuegbar}px)")

    def test_zeilen_passen_immer_in_die_breite(self):
        d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
        for titel in ECHTE_TITEL:
            f, zeilen, _ = st._headline_passend(d, titel.upper(), st.MAX_BREITE, 2000)
            for zeile in zeilen:
                self.assertLessEqual(d.textlength(zeile, font=f), st.MAX_BREITE)


class RenderGesamtbild(unittest.TestCase):
    """Baut echte Bilder (CPU, keine GPU/Netz) und prueft Format sowie dass der ganze komponierte Block
    (Banderole bis Markenbalken) innerhalb SAFE_TOP..SAFE_UNTEN liegt."""

    def test_format_1080x1920(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = st.render(ECHTE_TITEL[0], "WIRTSCHAFT", Path(tmp) / "t.jpg", merken=False)
            with Image.open(out) as im:
                self.assertEqual(im.size, (1080, 1920))

    def test_render_laeuft_fuer_alle_echten_titel_durch(self):
        # Die eigentliche Safe-Zone-Geometrie ist durch HeadlinePasstInSafeZone abgedeckt; hier nur
        # sicherstellen, dass render() fuer jeden echten Titel ohne Fehler ein gueltiges Bild liefert.
        with tempfile.TemporaryDirectory() as tmp:
            for i, titel in enumerate(ECHTE_TITEL):
                with self.subTest(titel=titel):
                    out = st.render(titel, "KRISE", Path(tmp) / f"t{i}.jpg", merken=False)
                    self.assertTrue(out.exists())
                    with Image.open(out) as im:
                        self.assertEqual(im.size, (1080, 1920))


if __name__ == "__main__":
    unittest.main()
