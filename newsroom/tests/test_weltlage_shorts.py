"""titel_frage: Regressionstest fuer den Doppel-Upload-Befund vom 18.10.2026 (Task 20261018-152136-0684).

Root Cause: _baue_einen rief bisher titel_frage(ordner, hook or fakten, meta) - der Hook ist immer der Cold
Open (immer in FIXE_SZENEN_ERSTE), darum bekam JEDER Short des Tages denselben Titel (die volle Folgen-
Schlagzeile), obwohl die Fakten-Szene sich zwischen den Shorts unterscheidet. Zwei Shorts mit identischem
Titel sehen auf dem Kanal wie ein Doppel-Upload aus.

    .venv\\Scripts\\python -m unittest tests.test_weltlage_shorts
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))

import tools.weltlage_shorts as ws  # noqa: E402

META = {"title": "Pulver an Wahlämter, Klage von Trump: Wer bedroht die WAHL?"}
ORDNER = Path("unbenutzt")   # meta wird immer explizit uebergeben, ordner wird dann nie gelesen


class TitelFrageTest(unittest.TestCase):
    def test_hook_coldopen_liefert_folgentitel(self):
        hook = {"id": "s_coldopen", "text": "Beliebiger Hook-Text."}
        self.assertEqual(ws.titel_frage(ORDNER, hook, META), META["title"])

    def test_fakten_mit_fragesatz_liefert_eigenen_titel(self):
        fakten = {"id": "s5_a3_kontext", "text": "Erste Aussage. Wer haftet am Ende für die Vorwürfe?"}
        titel = ws.titel_frage(ORDNER, fakten, META)
        self.assertEqual(titel, "Wer haftet am Ende für die Vorwürfe?")

    def test_fakten_mit_kommentarfrage_liefert_diese(self):
        meta = dict(META, kommentarfrage="Wer bedroht die Wahl wirklich")
        fakten = {"id": "s5_a2_wendepunkt", "text": "Kontext. Wer bedroht die Wahl wirklich. Weiterer Satz."}
        self.assertEqual(ws.titel_frage(ORDNER, fakten, meta), "Wer bedroht die Wahl wirklich?")

    def test_zwei_shorts_derselben_folge_bekommen_nie_denselben_titel(self):
        """Hauptfix: faellt die Fakten-Szene (kein Fragesatz, keine Kommentarfrage) auf den Folgentitel zurueck,
        bekommt nur der erste Short den vollen Titel - jeder weitere einen eindeutigen Zusatz."""
        fakten_ohne_frage = {"id": "s5_a4_verbindung", "text": "Nur Aussagesaetze ohne Frage am Ende."}
        titel_1 = ws.titel_frage(ORDNER, fakten_ohne_frage, META, 1)
        titel_2 = ws.titel_frage(ORDNER, fakten_ohne_frage, META, 2)
        self.assertEqual(titel_1, META["title"])
        self.assertNotEqual(titel_1, titel_2)
        self.assertTrue(titel_2.startswith(META["title"]))

    def test_ohne_fakten_szene_bleibt_hook_titel_wie_bisher(self):
        """Gibt es keine Fakten-Szene (reiner Hook-Short), bleibt das alte Verhalten unveraendert."""
        hook = {"id": "s_coldopen", "text": "Hook-Text."}
        self.assertEqual(ws.titel_frage(ORDNER, hook, META, 1), META["title"])


class IstStehendTest(unittest.TestCase):
    """Postur-Zuordnung muss zum Langschnitt (tools/weltlage_rohschnitt.py) passen: Cold Open/Themen/
    Verabschiedung/Abschluss stehend, nur die Meldungen-Szene (szene 5) sitzend."""

    def test_coldopen_ist_stehend(self):
        self.assertTrue(ws._ist_stehend("s_coldopen"))
        self.assertTrue(ws._ist_stehend("coldopen"))

    def test_themen_ist_stehend(self):
        self.assertTrue(ws._ist_stehend("s_themen"))
        self.assertTrue(ws._ist_stehend("themen"))

    def test_outro_verabschiedung_abschluss_ist_stehend(self):
        self.assertTrue(ws._ist_stehend("s6_outro"))
        self.assertTrue(ws._ist_stehend("verabschiedung"))
        self.assertTrue(ws._ist_stehend("abschluss"))

    def test_meldung_ist_sitzend(self):
        self.assertFalse(ws._ist_stehend("s5_a3_kontext"))


class BumperNoetigTest(unittest.TestCase):
    """Regressionstest fuer den Telegram-Auftrag vom 19.10.2026 (holpriger Steh-Sitz-Wechsel in den
    Shorts): zwischen Hook (immer Cold Open, stehend) und Fakten (immer eine Meldung, sitzend) muss der
    WK-Logo-Bumper eingesetzt werden; fehlt eine der beiden Szenen oder ist die Vorlage nicht gebaut, darf
    nichts eingefuegt werden."""

    def test_coldopen_zu_meldung_braucht_bumper(self):
        hook = {"id": "s_coldopen"}
        fakten = {"id": "s5_a3_kontext"}
        self.assertTrue(ws._bumper_noetig(hook, fakten))

    def test_gleiche_postur_braucht_keinen_bumper(self):
        hook = {"id": "s_coldopen"}
        fakten_stehend = {"id": "s_themen"}
        self.assertFalse(ws._bumper_noetig(hook, fakten_stehend))

    def test_fehlender_hook_oder_fakten_braucht_keinen_bumper(self):
        self.assertFalse(ws._bumper_noetig(None, {"id": "s5_a3_kontext"}))
        self.assertFalse(ws._bumper_noetig({"id": "s_coldopen"}, None))

    def test_ohne_vorlage_kein_bumper(self):
        alt = ws.UEBERGANG
        ws.UEBERGANG = None
        try:
            self.assertFalse(ws._bumper_noetig({"id": "s_coldopen"}, {"id": "s5_a3_kontext"}))
        finally:
            ws.UEBERGANG = alt


if __name__ == "__main__":
    unittest.main()
