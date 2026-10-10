"""Reiner CPU-Test fuer das Buendeln mehrerer Bilder durch Real-ESRGAN/GFPGAN (video/gesicht_hd.py, Task
20261010-081311-ca9f, Laufzeit-Analyse Weltlage Kompakt): esrgan_many()/gfpgan_many() mit batch > 1 muessen
rechnerisch dasselbe liefern wie batch=1 (= der bisherige Weg, ein Bild pro Netzdurchlauf). Erzwingt die CPU
(GESICHT_HD_DEVICE=cpu, vor dem Import gesetzt) statt der GPU: lauffaehig auch waehrend ein echter Weltlage-Render
die GPU belegt, ohne ihn zu stoeren oder um die Warteschlange zu konkurrieren.

    .venv-lipsync\\Scripts\\python.exe -m unittest tests.test_gesicht_hd_batch
"""
import os
import sys
import unittest
from pathlib import Path

os.environ["GESICHT_HD_DEVICE"] = "cpu"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

MODELS_OK = (ROOT / "models" / "upscale" / "RealESRGAN_x2plus.pth").exists() and \
    (ROOT / "models" / "upscale" / "GFPGANv1.4.pth").exists()


@unittest.skipUnless(MODELS_OK, "models/upscale fehlt (RealESRGAN/GFPGAN)")
class GesichtHdBatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from video import gesicht_hd
        cls.gh = gesicht_hd
        rng = np.random.default_rng(42)
        cls.frames = [rng.integers(0, 256, (64, 64, 3), dtype=np.uint8) for _ in range(5)]
        # Fuenf plausible, nicht kollineare Punkte je Bild (reicht fuer estimateAffinePartial2D); kein echtes
        # Gesicht noetig, nur eine gueltige Affin-Transformation fuer den Test.
        base = np.array([[20, 24], [44, 24], [32, 36], [24, 48], [40, 48]], np.float32)
        cls.kps = [base + i for i in range(5)]
        cls.kps_mit_luecke = list(cls.kps[:2]) + [None] + list(cls.kps[3:])

    def tearDown(self):
        self.gh.free()

    def test_esrgan_many_batch_wie_einzeln(self):
        einzeln = self.gh.esrgan_many(self.frames, scale=2, batch=1)
        gebuendelt = self.gh.esrgan_many(self.frames, scale=2, batch=3)
        self.assertEqual(len(einzeln), len(gebuendelt))
        for e, g in zip(einzeln, gebuendelt):
            self.assertEqual(e.shape, g.shape)
            diff = np.abs(e.astype(np.int16) - g.astype(np.int16))
            self.assertLessEqual(int(diff.max()), 2, "Stapel-Rechnung weicht sichtbar vom Einzelbild ab")

    def test_esrgan_many_batch_eins_ist_alte_funktion(self):
        einzeln_alt = [self.gh.esrgan(f, 2) for f in self.frames]
        einzeln_neu = self.gh.esrgan_many(self.frames, scale=2, batch=1)
        for a, n in zip(einzeln_alt, einzeln_neu):
            np.testing.assert_array_equal(a, n)

    def test_gfpgan_many_batch_wie_einzeln(self):
        einzeln = self.gh.gfpgan_many(self.frames, self.kps, 0.6, batch=1)
        gebuendelt = self.gh.gfpgan_many(self.frames, self.kps, 0.6, batch=3)
        self.assertEqual(len(einzeln), len(gebuendelt))
        for e, g in zip(einzeln, gebuendelt):
            self.assertEqual(e.shape, g.shape)
            diff = np.abs(e.astype(np.int16) - g.astype(np.int16))
            # GFPGAN liefert gebuendelt nicht bitgleich: die CPU-BLAS-Summationsreihenfolge bei Stapelgroesse > 1
            # ist nicht deterministisch (schwankt auch zwischen zwei Laeufen mit demselben Zufalls-Seed, beobachtet
            # 6-14 von 255 auf Rauschbildern, die ausserhalb dessen liegen, was das Netz je gesehen hat - anders als
            # bei ESRGAN, das hier bitgleich blieb). Die Toleranz prueft darum nur auf grobe Fehler (z.B. vertauschte
            # Bilder im Stapel), nicht auf Bitgleichheit; vor dem produktiven Einsatz trotzdem mit einem echten
            # Gesicht/Vergleichsclip pruefen (siehe Taskbericht Task 20261010-081311-ca9f).
            self.assertLessEqual(int(diff.max()), 40, "Stapel-Rechnung weicht grob vom Einzelbild ab")

    def test_gfpgan_many_luecke_bleibt_unveraendert(self):
        out = self.gh.gfpgan_many(self.frames, self.kps_mit_luecke, 0.6, batch=3)
        np.testing.assert_array_equal(out[2], self.frames[2])

    def test_restore_mit_batch_entspricht_batch_eins(self):
        # kps_of (insightface) findet in synthetischem Rauschen kein Gesicht; fuer den Weiterleitungs-Test an
        # gfpgan_many reichen die festen Testpunkte statt echter Gesichtserkennung.
        from unittest import mock
        kps_seq = list(self.kps)
        with mock.patch.object(self.gh, "kps_of", side_effect=lambda f: kps_seq.pop(0)):
            einzeln = self.gh.restore(list(self.frames), 0.6, batch=1)
        kps_seq = list(self.kps)
        with mock.patch.object(self.gh, "kps_of", side_effect=lambda f: kps_seq.pop(0)):
            gebuendelt = self.gh.restore(list(self.frames), 0.6, batch=3)
        # Nur die Weiterleitung von restore() an gfpgan_many pruefen (die Zahlen-Nahe selbst steckt in den beiden
        # Tests oben); Zufallsbilder durch ein auf echte Gesichter trainiertes Netz koennen das Rundungsrauschen
        # staerker zeigen als auf einem echten Gesicht, darum hier grosszuegiger.
        for e, g in zip(einzeln, gebuendelt):
            diff = np.abs(e.astype(np.int16) - g.astype(np.int16))
            self.assertLessEqual(int(diff.max()), 25)


if __name__ == "__main__":
    unittest.main()
