"""Tests fuer upload/youtube_playwright.py: nur die reinen Funktionen (kein Playwright/Browser noetig).

    .venv\\Scripts\\python.exe -m unittest tests.test_youtube_playwright -v
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from upload.youtube_playwright import braucht_nachzug, upload_stand  # noqa: E402


class UploadStand(unittest.TestCase):
    def test_laeuft(self):
        self.assertEqual(upload_stand("Uploading... 42%")[0], "laeuft")

    def test_fertig_bei_100_prozent(self):
        self.assertEqual(upload_stand("Upload complete. Processing... 100%")[0], "fertig")

    def test_fehler(self):
        self.assertEqual(upload_stand("Upload failed")[0], "fehler")

    def test_unbekannt_ohne_text(self):
        self.assertEqual(upload_stand("")[0], "unbekannt")


class BrauchtNachzug(unittest.TestCase):
    """Vorfall Fairford-Folge (05./06.10.2026): oeffentlich_bestaetigt=False darf nicht einfach stehen bleiben,
    solange das Video nicht privat gedacht war."""

    def test_nicht_bestaetigt_und_oeffentlich_gedacht_braucht_nachzug(self):
        self.assertTrue(braucht_nachzug({"oeffentlich_bestaetigt": False}, "PUBLIC"))

    def test_nicht_bestaetigt_aber_unlisted_braucht_auch_nachzug(self):
        self.assertTrue(braucht_nachzug({"oeffentlich_bestaetigt": False}, "unlisted"))

    def test_bestaetigt_braucht_keinen_nachzug(self):
        self.assertFalse(braucht_nachzug({"oeffentlich_bestaetigt": True}, "PUBLIC"))

    def test_privat_gedacht_braucht_nie_nachzug(self):
        self.assertFalse(braucht_nachzug({"oeffentlich_bestaetigt": False}, "PRIVATE"))

    def test_nie_geprueft_braucht_keinen_nachzug(self):
        # oeffentlich_bestaetigt ist None, wenn visibility == PRIVATE und oeffentlich_pruefen() nie lief.
        self.assertFalse(braucht_nachzug({"oeffentlich_bestaetigt": None}, "PUBLIC"))


if __name__ == "__main__":
    unittest.main()
