"""Offline-Tests: Lipsync nur wo Latara sichtbar ist (Schalter NEWS_LIPSYNC_NUR_SICHTBAR, Puffer an den Kanten).

    .venv\Scripts\python -m unittest tests.test_lipsync_nur_sichtbar
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from video import freisteller_lipsync as fl  # noqa: E402


class SichtbarSkip(unittest.TestCase):
    def test_puffer_schrumpft_beidseitig(self):
        self.assertEqual(fl.sichtbar_skip([(10.0, 15.5)], True, 0.3), [(10.3, 15.2)])

    def test_zu_kurze_spanne_entfaellt(self):
        self.assertEqual(fl.sichtbar_skip([(10.0, 10.9)], True, 0.3), [])

    def test_schalter_aus_rechnet_ueberall(self):
        self.assertEqual(fl.sichtbar_skip([(10.0, 15.5)], False, 0.3), [])

    def test_ohne_spannen(self):
        self.assertEqual(fl.sichtbar_skip(None, True, 0.3), [])


class Grenzen(unittest.TestCase):
    def test_nahe_schnitte_wandern_auf_die_kante(self):
        cuts = [0, 100, 173, 238, 312, 400]
        out = fl._mit_skip_grenzen(cuts, [(108, 230)], 400)
        self.assertIn(108, out)
        self.assertIn(230, out)
        self.assertNotIn(100, out)
        self.assertNotIn(238, out)

    def test_nie_zu_kurze_oder_zu_lange_stuecke(self):
        out = fl._mit_skip_grenzen([0, 100, 200, 300], [(10, 20), (105, 190)], 300)
        d = [b - a for a, b in zip(out, out[1:])]
        self.assertTrue(all(fl.MIN_CHUNK <= x <= round((fl.CHUNK + 1) * fl.FPS) for x in d), out)
        self.assertEqual(out[0], 0)
        self.assertEqual(out[-1], 300)


if __name__ == "__main__":
    unittest.main()
