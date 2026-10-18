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


if __name__ == "__main__":
    unittest.main()
