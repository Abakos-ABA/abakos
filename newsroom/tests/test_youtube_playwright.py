"""Tests fuer upload/youtube_playwright.py: nur die reinen Funktionen (kein Playwright/Browser noetig).

    .venv\\Scripts\\python.exe -m unittest tests.test_youtube_playwright -v
"""
import os
import sys
import tempfile
import types
import unittest
from unittest import mock
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


class _Uhr:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class _TransferSeite:
    """Studio-Fortschritt: je Abfrage der naechste Text, das Warten laeuft auf der Test-Uhr."""

    def __init__(self, texte, uhr, schritt_s=60):
        self.texte, self.uhr, self.schritt_s = list(texte), uhr, schritt_s

    def evaluate(self, _js):
        return self.texte.pop(0) if len(self.texte) > 1 else self.texte[0]

    def wait_for_timeout(self, _ms):
        self.uhr.t += self.schritt_s


class WarteAufTransferTest(unittest.TestCase):
    def _lauf(self, texte, timeout_min, schritt_s=60):
        uhr = _Uhr()
        with mock.patch("time.time", uhr):
            try:
                return yp._warte_auf_transfer(_TransferSeite(texte, uhr, schritt_s), lambda m: None, timeout_min), uhr.t - 1000
            except RuntimeError as e:
                return e, uhr.t - 1000

    def test_langsamer_transfer_mit_fortschritt_laeuft_ueber_das_limit(self):
        # Vorfall 08.11.2026: rund 1 % pro Minute, Limit 60 min, frueher Abbruch bei 75 %
        texte = [f"Wird hochgeladen {p} % ... Noch {100 - p} Minuten" for p in range(1, 100)]
        text, dauer = self._lauf(texte + ["Upload abgeschlossen ... wird verarbeitet"], 60)
        self.assertIn("abgeschlossen", text)
        self.assertGreater(dauer, 60 * 60)

    def test_stillstand_bricht_ab(self):
        fehler, dauer = self._lauf(["Wird hochgeladen 40 % ... Noch 9 Minuten"], 5)
        self.assertIsInstance(fehler, RuntimeError)
        self.assertLessEqual(dauer, (yp.TRANSFER_STILLSTAND_MIN + 1) * 60)

    def test_harte_obergrenze(self):
        fehler, dauer = self._lauf([f"Wird hochgeladen {p} %" for p in range(1, 100)], 60, schritt_s=600)
        self.assertIsInstance(fehler, RuntimeError)
        self.assertLessEqual(dauer, yp.TRANSFER_MAX_MIN * 60 + 600)


class _Treffer:
    def __init__(self, n, beim_klick=None, klick_fehler=False):
        self.n, self.beim_klick, self.klick_fehler = n, beim_klick, klick_fehler

    @property
    def first(self):
        return self

    def count(self):
        return self.n

    def scroll_into_view_if_needed(self):
        pass

    def click(self, timeout=None):
        if self.klick_fehler:
            raise RuntimeError("Timeout: Knopf nicht klickbar")
        if self.beim_klick:
            self.beim_klick()


class _Dialog:
    def __init__(self, text, assistent=False, abbrechen=None):
        self.text, self.assistent, self.abbrechen = text, assistent, abbrechen

    def inner_text(self):
        return self.text

    def locator(self, sel):
        if sel == "#title-textarea":
            return _Treffer(1 if self.assistent else 0)
        return _Treffer(1 if self.abbrechen else 0, self.abbrechen)


class _ChooserFehlt:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        raise RuntimeError("Timeout: keine Dateiauswahl")


class _ThumbSeite:
    def __init__(self, dialoge, knopf=None):
        self.dialoge, self.knopf = dialoge, knopf or _Treffer(1)
        self.tasten = []
        self.keyboard = types.SimpleNamespace(press=self.tasten.append)

    def locator(self, sel):
        if sel.startswith("ytcp-thumbnail-uploader"):
            return self.knopf
        return types.SimpleNamespace(all=lambda: list(self.dialoge))

    def expect_file_chooser(self, timeout=None):
        return _ChooserFehlt()

    def wait_for_timeout(self, _ms):
        pass


class ThumbnailDialogTest(unittest.TestCase):
    def _setzen(self, seite):
        return yp._thumbnail_setzen(seite, "t.jpg", lambda m: None, lambda n: None)

    def test_ohne_neuen_dialog_bleibt_der_assistent_offen(self):
        # Vorfall 08.11.2026: Escape schloss den Assistenten, danach fehlte VIDEO_MADE_FOR_KIDS_NOT_MFK
        seite = _ThumbSeite([_Dialog("Details Titel", assistent=True)], _Treffer(1, klick_fehler=True))
        self.assertTrue(self._setzen(seite).startswith("unklar"))
        self.assertEqual(seite.tasten, [])

    def test_assistent_text_gilt_nicht_als_telefon_sperre(self):
        seite = _ThumbSeite([_Dialog("Bitte bestätigen Details", assistent=True)], _Treffer(1, klick_fehler=True))
        self.assertTrue(self._setzen(seite).startswith("unklar"))

    def test_telefon_dialog_wird_gemeldet_und_nur_er_geschlossen(self):
        seite = _ThumbSeite([_Dialog("Details Titel", assistent=True)])
        geklickt = []
        telefon = _Dialog("Du musst deine Telefonnummer bestätigen", abbrechen=lambda: geklickt.append(1))
        seite.knopf = _Treffer(1, lambda: seite.dialoge.append(telefon))
        self.assertTrue(self._setzen(seite).startswith("gesperrt"))
        self.assertEqual((geklickt, seite.tasten), ([1], []))


class _SprachTreffer:
    def __init__(self, seite, name):
        self.seite, self.name = seite, name

    @property
    def first(self):
        return self

    def count(self):
        return 1

    def scroll_into_view_if_needed(self):
        pass

    def locator(self, sel):
        return _SprachTreffer(self.seite, sel)

    def inner_text(self):
        return f"Videosprache\n{self.seite.aktuell}"

    def bounding_box(self):
        return {"x": 10, "y": 20, "width": 100, "height": 10}

    def click(self, timeout=None):
        self.seite.klicks.append((self.name, timeout))
        if "paper-item" in self.name:
            if self.seite.leer_bis >= self.seite.option_klicks():
                raise TimeoutError("Liste leer")


class _SprachSeite:
    def __init__(self, aktuell="Auswählen", leer_bis=0):
        self.aktuell, self.leer_bis, self.klicks, self.maus, self.tasten = aktuell, leer_bis, [], [], []
        self.mouse = types.SimpleNamespace(click=lambda x, y: self.maus.append((x, y)))
        self.keyboard = types.SimpleNamespace(press=self.tasten.append)

    def option_klicks(self):
        return sum("paper-item" in n for n, _ in self.klicks)

    def locator(self, sel):
        return _SprachTreffer(self, sel)

    def wait_for_timeout(self, _ms):
        pass


class SpracheSetzenTest(unittest.TestCase):
    def test_normalfall_waehlt_die_sprache(self):
        seite = _SprachSeite()
        yp._set_language(seite, "de")
        self.assertEqual(seite.option_klicks(), 1)
        self.assertEqual(seite.maus, [])

    def test_schon_richtig_oeffnet_die_liste_nicht(self):
        seite = _SprachSeite(aktuell="Deutsch")
        yp._set_language(seite, "de")
        self.assertEqual(seite.klicks, [])

    def test_leere_liste_beim_ersten_mal_wird_wiederholt(self):
        seite, meldungen = _SprachSeite(leer_bis=1), []
        yp._set_language(seite, "de", meldungen.append)
        self.assertEqual(seite.option_klicks(), 2)
        self.assertEqual(len(seite.maus), 1)
        self.assertEqual(meldungen, [])

    def test_dauerhaft_leere_liste_bricht_den_upload_nicht_ab(self):
        # Vorfall 08.11.2026: 120 s Warten und Abbruch der ganzen Folge; Escape wuerde den Assistenten schliessen
        seite, meldungen = _SprachSeite(leer_bis=99), []
        yp._set_language(seite, "de", meldungen.append)
        self.assertEqual(seite.option_klicks(), yp.SPRACH_VERSUCHE)
        self.assertEqual(seite.tasten, [])
        self.assertEqual(len(meldungen), 1)
        self.assertTrue(all(t == yp.SPRACH_WARTEN_MS for _, t in seite.klicks))


if __name__ == "__main__":
    unittest.main()
