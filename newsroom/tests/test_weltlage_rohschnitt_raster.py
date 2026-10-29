"""Offline-Tests fuer tools/weltlage_rohschnitt.py: Schnittbild-Raster + Vollbild-Spannen der Quellen-Screenshot-
Karten (rexemre 19.10.2026, Ergaenzung zu Task 20261019-182613-44c1 - skip_spans fuer den Lipsync).

    .venv\\Scripts\\python -m unittest tests.test_weltlage_rohschnitt_raster
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import weltlage_rohschnitt as r  # noqa: E402


def shot(n=1):
    return [{"png": f"source{i}.png", "domain": "example.com"} for i in range(n)]


class Raster(unittest.TestCase):
    def test_ohne_shots_nur_host(self):
        segs = r.bild_segmente([], 30.0)
        self.assertTrue(all(s[0] == "host" for s in segs))
        self.assertAlmostEqual(sum(s[1] for s in segs), 30.0, places=3)
        self.assertEqual(r.bild_spannen(segs), [])

    def test_bild_segmente_liegen_zwischen_host_segmenten(self):
        segs = r.bild_segmente(shot(1), 20.0)
        arten = [s[0] for s in segs]
        self.assertGreaterEqual(arten.count("bild"), 1)
        self.assertEqual(arten[0], "host")   # Latara am Anfang sichtbar
        self.assertEqual(arten[-1], "host")  # Latara am Ende sichtbar

    def test_bild_spannen_deckt_genau_die_bild_segmente_ab(self):
        segs = r.bild_segmente(shot(2), 40.0)
        spannen = r.bild_spannen(segs)
        gesamt_bild = sum(s[1] for s in segs if s[0] == "bild")
        self.assertEqual(len(spannen), sum(1 for s in segs if s[0] == "bild"))
        self.assertAlmostEqual(sum(b - a for a, b in spannen), gesamt_bild, places=3)
        # keine Ueberlappung, aufsteigend
        for (a0, b0), (a1, b1) in zip(spannen, spannen[1:]):
            self.assertLessEqual(b0, a1)

    def test_spannen_liegen_nie_am_allerersten_oder_letzten_zeitpunkt(self):
        segs = r.bild_segmente(shot(3), 60.0)
        spannen = r.bild_spannen(segs)
        L = sum(s[1] for s in segs)
        for a0, b0 in spannen:
            self.assertGreater(a0, 0.0)
            self.assertLess(b0, L)

    def test_kurze_meldung_ohne_platz_bleibt_ganz_host(self):
        segs = r.bild_segmente(shot(5), 5.0)
        self.assertTrue(all(s[0] == "host" for s in segs))
        self.assertAlmostEqual(sum(s[1] for s in segs), 5.0, places=3)
        self.assertEqual(r.bild_spannen(segs), [])


if __name__ == "__main__":
    unittest.main()
