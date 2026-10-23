"""Themenbild fuer Weltlage-Thumbnails (23.10.2026): Label-Woerter nie Suchbegriff, Merkliste, Quellen-Ablehnung."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from video import weltlage_thumbnail_bild as tb  # noqa: E402
from video import weltlage_thumbnail_eil as eil  # noqa: E402


class Begriffe(unittest.TestCase):
    def test_breaking_ist_nie_suchbegriff(self):
        for t in ("BREAKING: Macron verliert nach den Krawallen die KONTROLLE?",
                  "BREAKING: Lula gegen Bolsonaro: Entscheidet Trump Brasiliens Stichwahl?"):
            q = " ".join(tb.begriffe(t)).lower()
            self.assertNotIn("breaking", q)
        self.assertEqual(tb.begriffe("BREAKING: Macron verliert nach den Krawallen die KONTROLLE?")[0].split()[0], "Macron")
        self.assertIn("Lula Bolsonaro", tb.begriffe("BREAKING: Lula gegen Bolsonaro: Entscheidet Trump Brasiliens Stichwahl?"))

    def test_themenwort_uebersetzt(self):
        self.assertTrue(any("oil tanker" in q for q in tb.begriffe("Trump wartet auf Deal, 2 Tanker brennen: Dreht Iran den Ölhahn zu?")))


class Merkliste(unittest.TestCase):
    def test_nie_fremdes_thema(self):
        v = {"a": {"themen": {"ordner1": ["short_1"]}}}
        self.assertFalse(tb.zulaessig("a", "ordner2", "short_1", v, False))
        self.assertTrue(tb.zulaessig("a", "ordner1", "short_1", v, True))     # eigener Short, Neurendern
        self.assertFalse(tb.zulaessig("a", "ordner1", "short_2", v, True))    # Teil 2 bevorzugt anderes Bild
        self.assertTrue(tb.zulaessig("a", "ordner1", "short_2", v, False))    # ... aber nur Rueckfall erlaubt
        self.assertTrue(tb.zulaessig("neu", "ordner2", "short_1", v, True))


class Lizenz(unittest.TestCase):
    def _k(self, titel, datei="https://x/y.jpg"):
        return {"quelle": "commons", "lizenz": "CC BY-SA 3.0", "titel": titel, "herkunftstext": titel.lower(),
                "breite": 1600, "datei": datei}

    def test_screenshots_und_gewalt_abgelehnt(self):
        self.assertIsNone(eil._lizenz_ok(self._k("President Trump Signs an EO")))
        self.assertIsNotNone(eil._lizenz_ok(self._k("Trump Truth Social post")))
        self.assertIsNotNone(eil._lizenz_ok(self._k("Kill Trump banner")))
        self.assertIsNotNone(eil._lizenz_ok(self._k("Trump", "https://x/y.png?utm=1")))

    def test_verlagsquelle_abgelehnt(self):
        p = []
        news = Path(__file__).parent / "_tmp_bild"
        news.mkdir(exist_ok=True)
        (news / "news.json").write_text('[{"articles":[{"url":"https://www.cnbc.com/a","title":"Macron"}]}]', encoding="utf-8")
        try:
            self.assertIsNone(tb.quellbild(news, "Macron Krawalle", p))
            self.assertTrue(any("cnbc.com abgelehnt" in z for z in p))
        finally:
            (news / "news.json").unlink()
            news.rmdir()


if __name__ == "__main__":
    unittest.main()
