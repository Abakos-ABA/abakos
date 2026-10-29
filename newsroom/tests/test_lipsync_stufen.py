"""Lipsync-Drosselstufen: Stufe 2 ist seit rexemres Entscheid 19.10.2026 der Standard fuer alle
Lipsync-Pipelines (Task 20261019-120910-a2ea, Drosselprobe-Werte aus jarvis/reports/
lipsync_drossel_vergleich_20261019/ergebnis.json). Dieser Test haelt fest, dass die Werte an EINER
zentralen Stelle (config.settings.NEWS_LIPSYNC_STUFEN) stehen und beide Pipelines (video/
freisteller_lipsync.py fuer Weltlage Kompakt + die daraus geschnittenen Shorts, video/lipsync.py
fuer die aeltere Master-Clip-Pipeline) von dort und nicht aus eigenen hartkodierten Zahlen lesen.

    .venv\\Scripts\\python -m unittest tests.test_lipsync_stufen
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import settings


class LipsyncStufen(unittest.TestCase):
    def test_vier_stufen_mit_den_gemessenen_werten(self):
        self.assertEqual(settings.NEWS_LIPSYNC_STUFEN, {
            1: dict(steps=8, guidance=2.0, zoom=768),
            2: dict(steps=5, guidance=1.5, zoom=768),
            3: dict(steps=4, guidance=1.2, zoom=512),
            4: dict(steps=3, guidance=1.0, zoom=384),
        })

    def test_stufe_2_ist_standard(self):
        self.assertEqual(settings.NEWS_LIPSYNC_STUFE, 2)
        stufe2 = settings.NEWS_LIPSYNC_STUFEN[2]
        self.assertEqual(settings.NEWS_WELTLAGE_LIPSYNC_STEPS, stufe2["steps"])
        self.assertEqual(settings.NEWS_WELTLAGE_LIPSYNC_GUIDANCE, stufe2["guidance"])
        self.assertEqual(settings.NEWS_WELTLAGE_LIPSYNC_ZOOM, stufe2["zoom"])
        self.assertEqual(settings.NEWS_LIPSYNC_STEPS, stufe2["steps"])
        self.assertEqual(settings.NEWS_LIPSYNC_GUIDANCE, stufe2["guidance"])

    def test_freisteller_lipsync_liest_aus_der_zentralen_stelle_statt_eigener_zahlen(self):
        from video import freisteller_lipsync as fl
        self.assertEqual(fl.STEPS, settings.NEWS_WELTLAGE_LIPSYNC_STEPS)
        self.assertEqual(fl.GUIDANCE, settings.NEWS_WELTLAGE_LIPSYNC_GUIDANCE)
        self.assertEqual(fl.ZOOM, settings.NEWS_WELTLAGE_LIPSYNC_ZOOM)


if __name__ == "__main__":
    unittest.main()
