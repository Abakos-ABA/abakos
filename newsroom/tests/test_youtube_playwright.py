"""Tests fuer upload/youtube_playwright.py: nur die reinen Funktionen (kein Playwright/Browser noetig).

    .venv\\Scripts\\python.exe -m unittest tests.test_youtube_playwright -v
"""
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import upload.youtube_playwright as yp  # noqa: E402
from upload.youtube_playwright import (braucht_nachzug, pruefung_laeuft, sichtbarkeit_aus_text,  # noqa: E402
                                       studio_status_aus, upload_stand, zwischendialog_art)


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


class Zwischendialog(unittest.TestCase):
    """Vorfall Bolsonaro-Folge 06.10.2026: Studio-Dialog nach «Veroeffentlichen», wortgleich vom Screenshot."""
    DIALOG = ("Die Vorabprüfung deiner Inhalte läuft noch Wir empfehlen dir, deine Inhalte bis zum Abschluss der "
              "Vorabprüfung privat zu lassen. Wenn du das Video jetzt veröffentlichst, kann das eine Verwarnung oder "
              "Einschränkungen bei Sichtbarkeit und Monetarisierung zur Folge haben. Trotzdem veröffentlichen Zurück")

    def test_deutscher_dialog_erkannt(self):
        self.assertEqual(zwischendialog_art(self.DIALOG), "vorab_laeuft")

    def test_englischer_dialog_erkannt(self):
        self.assertEqual(zwischendialog_art("Checks are still running. We recommend keeping your video private "
                                            "until checks are complete. Publish anyway Back"), "vorab_laeuft")

    def test_hinweis_im_assistenten_ist_kein_zwischendialog(self):
        # steht immer im Sichtbarkeits-Schritt und darf nie einen Klick ausloesen
        self.assertIsNone(zwischendialog_art("Wir empfehlen dir, das Video auf «privat» gesetzt zu lassen und nicht "
                                             "zu teilen, bis die Vorabprüfung abgeschlossen ist."))

    def test_echte_warnung_ist_kein_zwischendialog(self):
        self.assertIsNone(zwischendialog_art("Urheberrechtlich geschützte Inhalte gefunden. Der Inhaber kann ..."))


class Pruefung(unittest.TestCase):
    def test_laeuft(self):
        self.assertTrue(pruefung_laeuft("Wird geprüft: 7 % ... Noch 10 Minuten"))
        self.assertTrue(pruefung_laeuft("Checking 40% ... 3 minutes left"))

    def test_fertig(self):
        self.assertFalse(pruefung_laeuft("Prüfung abgeschlossen. Keine Probleme gefunden."))
        self.assertFalse(pruefung_laeuft("Checks complete. No issues found."))
        self.assertFalse(pruefung_laeuft(""))


class StudioStatus(unittest.TestCase):
    def test_sichtbarkeit(self):
        self.assertEqual(sichtbarkeit_aus_text("Sichtbarkeit\nÖffentlich"), "PUBLIC")
        self.assertEqual(sichtbarkeit_aus_text("Visibility Unlisted"), "UNLISTED")
        self.assertEqual(sichtbarkeit_aus_text("Sichtbarkeit Nicht gelistet"), "UNLISTED")
        self.assertEqual(sichtbarkeit_aus_text("Privat"), "PRIVATE")

    def test_mehrdeutig_oder_leer(self):
        self.assertIsNone(sichtbarkeit_aus_text("Öffentlich Privat"))
        self.assertIsNone(sichtbarkeit_aus_text(""))

    def test_entwurf_geht_vor(self):
        seite = 'Videodetails Dieses Video ist im Status "Entwurf" Entwurf bearbeiten Inhalte des Kanals'
        self.assertEqual(studio_status_aus(seite, "Privat"), "ENTWURF")

    def test_normale_seite(self):
        self.assertEqual(studio_status_aus("Videodetails Titel Beschreibung", "Öffentlich"), "PUBLIC")
        self.assertEqual(studio_status_aus("Videodetails", ""), "UNBEKANNT")


class Sperre(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp()) / "lock"
        yp._sperre_tiefe = 0

    def test_holen_freigeben_verschachtelt(self):
        yp.sperre_holen(self.d, warten_s=1)
        yp.sperre_holen(self.d, warten_s=1)        # gleicher Prozess: verschachtelt, kein Warten
        self.assertTrue(self.d.exists())
        yp.sperre_freigeben(self.d)
        self.assertTrue(self.d.exists(), "aeussere Sperre bleibt")
        yp.sperre_freigeben(self.d)
        self.assertFalse(self.d.exists())

    def test_verwaiste_sperre_wird_uebernommen(self):
        self.d.parent.mkdir(parents=True, exist_ok=True)
        self.d.write_text("999999")                # PID existiert nicht
        yp.sperre_holen(self.d, warten_s=1)
        self.assertEqual(self.d.read_text().strip(), str(os.getpid()))
        yp.sperre_freigeben(self.d)

    def test_fremde_lebende_sperre_blockiert(self):
        import subprocess
        pr = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            self.d.parent.mkdir(parents=True, exist_ok=True)
            self.d.write_text(str(pr.pid))
            with self.assertRaises(RuntimeError):
                yp.sperre_holen(self.d, warten_s=0)
            self.assertEqual(self.d.read_text().strip(), str(pr.pid), "fremde Sperre unangetastet")
        finally:
            pr.kill()
            pr.wait()

    def test_freigeben_ohne_eigene_sperre_loescht_nichts(self):
        self.d.parent.mkdir(parents=True, exist_ok=True)
        self.d.write_text("123")
        yp.sperre_freigeben(self.d)
        self.assertTrue(self.d.exists())


class _FakePage:
    def set_default_timeout(self, ms):
        pass

    def wait_for_timeout(self, ms):
        pass

    def screenshot(self, **kw):
        pass

    def get_by_text(self, *a, **k):
        return types.SimpleNamespace(count=lambda: 0)


class Veroeffentlichen(unittest.TestCase):
    """Ablauf mit nachgebautem Browser: Status frisch lesen, Entwurf abschliessen, erneut frisch pruefen."""

    def setUp(self):
        self.orig = {n: getattr(yp, n) for n in ("_launch", "_status_seite", "_entwurf_abschliessen",
                                                  "_sichtbarkeit_bearbeiten", "oeffentlich_pruefen")}
        self.eingriffe = []
        ctx = types.SimpleNamespace(new_page=lambda: _FakePage(), close=lambda: None)
        yp._launch = lambda p, headless: ctx
        yp._entwurf_abschliessen = lambda page, vis, log, shot: self.eingriffe.append(("entwurf", vis))
        yp._sichtbarkeit_bearbeiten = lambda page, vis, log, shot: self.eingriffe.append(("feld", vis))
        yp.oeffentlich_pruefen = lambda vid, minuten=30, log=None: False

        class _PW:
            def __enter__(self):
                return object()

            def __exit__(self, *a):
                return False
        fake = types.ModuleType("playwright.sync_api")
        fake.sync_playwright = lambda: _PW()
        self.alt_mod = sys.modules.get("playwright.sync_api")
        sys.modules["playwright.sync_api"] = fake

    def tearDown(self):
        for n, f in self.orig.items():
            setattr(yp, n, f)
        if self.alt_mod is not None:
            sys.modules["playwright.sync_api"] = self.alt_mod
        else:
            sys.modules.pop("playwright.sync_api", None)

    def _status_folge(self, *folge):
        it = iter(folge)
        yp._status_seite = lambda page, vid, warten_s=60: next(it)

    def test_schon_oeffentlich_kein_eingriff(self):
        self._status_folge("PUBLIC")
        r = yp.veroeffentlichen("BiYN6eaqnA4", "public", log=lambda m: None, pause_s=0)
        self.assertTrue(r["ok"])
        self.assertEqual(self.eingriffe, [])

    def test_entwurf_wird_abgeschlossen_und_frisch_geprueft(self):
        self._status_folge("ENTWURF", "PUBLIC")
        r = yp.veroeffentlichen("BiYN6eaqnA4", "PUBLIC", log=lambda m: None, pause_s=0)
        self.assertTrue(r["ok"])
        self.assertEqual(self.eingriffe, [("entwurf", "PUBLIC")])
        self.assertEqual(r["verlauf"], ["ENTWURF", "PUBLIC"])

    def test_privat_ueber_sichtbarkeitsfeld(self):
        self._status_folge("PRIVATE", "PUBLIC")
        r = yp.veroeffentlichen("x" * 11, "PUBLIC", log=lambda m: None, pause_s=0)
        self.assertTrue(r["ok"])
        self.assertEqual(self.eingriffe, [("feld", "PUBLIC")])

    def test_nachklicken_bis_wirklich_oeffentlich(self):
        # erster Klick wirkt nicht (Studio bleibt Entwurf), zweiter Durchgang klappt
        self._status_folge("ENTWURF", "ENTWURF", "ENTWURF", "PUBLIC")
        r = yp.veroeffentlichen("x" * 11, "PUBLIC", log=lambda m: None, pause_s=0)
        self.assertTrue(r["ok"])
        self.assertEqual(len(self.eingriffe), 2)

    def test_gibt_nach_allen_durchgaengen_auf(self):
        self._status_folge(*["ENTWURF"] * 6)
        r = yp.veroeffentlichen("x" * 11, "PUBLIC", log=lambda m: None, pause_s=0, versuche=3)
        self.assertFalse(r["ok"])
        self.assertEqual(r["status"], "ENTWURF")
        self.assertEqual(len(self.eingriffe), 3)

    def test_fehler_im_durchgang_fuehrt_zum_naechsten(self):
        def kaputt(page, vis, log, shot):
            raise RuntimeError("Timeout 120000ms")
        yp._entwurf_abschliessen = kaputt
        self._status_folge("ENTWURF", "PUBLIC")
        r = yp.veroeffentlichen("x" * 11, "PUBLIC", log=lambda m: None, pause_s=0)
        self.assertTrue(r["ok"])
        self.assertIn("Timeout", r["fehler"])


if __name__ == "__main__":
    unittest.main()
