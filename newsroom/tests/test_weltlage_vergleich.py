"""Tests fuer tools/weltlage_vergleich.py: Titel-Merkmale, Rang-Vergleich, Bericht. Komplett offline, kein
Playwright, kein Netz (Marlon 19.10.2026, Task 20261019-115559-7e79 im Jarvis-Repo).

    .venv\\Scripts\\python -m unittest tests.test_weltlage_vergleich
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))

import weltlage_vergleich as wv  # noqa: E402


class TitelMerkmaleTest(unittest.TestCase):
    def test_frage_und_zahl(self):
        m = wv.titel_merkmale("Trump schickt dritten Träger: Bomben auf Iran nach den Midterms?")
        self.assertTrue(m["frage"])
        self.assertFalse(m["zahl"])

    def test_leerer_titel_crasht_nicht(self):
        self.assertEqual(wv.titel_merkmale(None)["laenge"], 0)


class VergleichenTest(unittest.TestCase):
    def test_zu_wenig_inhalte(self):
        r = wv.vergleichen([{"rang": 1, "titel": "A", "aufrufe": 10}], n=3)
        self.assertFalse(r["ok"])
        self.assertIn("mind.", r["grund"])

    def test_rang_vergleich(self):
        inhalte = [
            {"rang": 1, "titel": "Krieg eskaliert: 10 Tote bei Angriff?", "aufrufe": 2000},
            {"rang": 2, "titel": "Gipfel in Genf: Einigung in letzter Minute?", "aufrufe": 900},
            {"rang": 3, "titel": "Praesident warnt vor neuer Eskalation?", "aufrufe": 500},
            {"rang": 4, "titel": "Bericht ueber Lage an der Grenze", "aufrufe": 100},
            {"rang": 5, "titel": "Analyse der aktuellen Wirtschaftslage", "aufrufe": 50},
            {"rang": 6, "titel": "Kurzer Rueckblick auf die Woche", "aufrufe": 10},
        ]
        r = wv.vergleichen(inhalte, n=3)
        self.assertTrue(r["ok"])
        self.assertEqual([v["rang"] for v in r["top"]], [1, 2, 3])
        self.assertEqual([v["rang"] for v in r["flop"]], [4, 5, 6])
        frage = next(m for m in r["muster"] if m["merkmal"] == "frage")
        self.assertEqual(frage["top"], "3/3")
        self.assertEqual(frage["flop"], "0/3")


class BerichtTest(unittest.TestCase):
    def test_bericht_ohne_verlauf(self):
        tmp = Path(tempfile.mkdtemp(prefix="wv-test-")) / "bericht.md"
        pfad = wv.bericht(verlauf=[], pfad=tmp)
        text = pfad.read_text(encoding="utf-8")
        self.assertIn("Noch kein Analytics-Verlauf", text)

    def test_bericht_mit_schnappschuss(self):
        verlauf = [{
            "abgerufen_um": "2026-10-16T09:15:30+02:00",
            "inhalte": [
                {"rang": i, "titel": f"Folge {i}: Was passiert als Naechstes?" if i <= 3 else f"Folge {i}",
                 "aufrufe": 1000 - i * 50}
                for i in range(1, 9)
            ],
        }]
        tmp = Path(tempfile.mkdtemp(prefix="wv-test-")) / "bericht.md"
        pfad = wv.bericht(verlauf=verlauf, pfad=tmp)
        text = pfad.read_text(encoding="utf-8")
        self.assertIn("Top (Rang 1-3)", text)
        self.assertIn("Einschraenkung", text)


if __name__ == "__main__":
    unittest.main()
