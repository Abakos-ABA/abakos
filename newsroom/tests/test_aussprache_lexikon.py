"""Offline-Tests fuer das Aussprache-Lexikon der Stimme (tts/aussprache_lexikon.py) und seine Einbindung in
tts/normalize_de.normalize_for_tts.

    .venv\\Scripts\\python.exe -m unittest tests.test_aussprache_lexikon -v
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tts import aussprache_lexikon as al  # noqa: E402
from tts.normalize_de import normalize_for_tts  # noqa: E402

BEISPIEL = {
    "Selenskyj": {"sprich": "Selenski", "quelle": "manuell", "hinzugefuegt": "2026-10-02"},
    "Xi Jinping": {"sprich": "Schi Dschinping", "quelle": "manuell", "hinzugefuegt": "2026-10-02"},
    "Xi": {"sprich": "Schi", "quelle": "manuell", "hinzugefuegt": "2026-10-02"},
}


class AnwendenTest(unittest.TestCase):
    def test_ersetzt_mit_wortgrenze(self):
        out = al.anwenden("Das sagte Selenskyj heute.", BEISPIEL)
        self.assertEqual(out, "Das sagte Selenski heute.")

    def test_genitiv_s_bleibt_erhalten(self):
        out = al.anwenden("Selenskyjs Rede dauerte lange.", BEISPIEL)
        self.assertEqual(out, "Selenskis Rede dauerte lange.")

    def test_mehrwort_eintrag_geht_vor_kurzem(self):
        out = al.anwenden("Xi Jinping traf sich mit Xi.", BEISPIEL)
        self.assertEqual(out, "Schi Dschinping traf sich mit Schi.")

    def test_unbekannter_name_bleibt_unveraendert(self):
        out = al.anwenden("Das sagte Mustermann.", BEISPIEL)
        self.assertEqual(out, "Das sagte Mustermann.")

    def test_leeres_lexikon_aendert_nichts(self):
        self.assertEqual(al.anwenden("Text mit Selenskyj.", {}), "Text mit Selenskyj.")


ORTE_BEISPIEL = {
    "Kiew": {"sprich": "Kijef", "quelle": "manuell", "hinzugefuegt": "2026-10-02"},
    "Kyiv": {"sprich": "Kijef", "quelle": "manuell", "hinzugefuegt": "2026-10-02"},
    "Charkiw": {"sprich": "Charkif", "quelle": "manuell", "hinzugefuegt": "2026-10-02"},
    "Beijing": {"sprich": "Peking", "quelle": "manuell", "hinzugefuegt": "2026-10-02"},
}


class OrteTest(unittest.TestCase):
    def test_deutsche_schreibweise_wird_respelled(self):
        out = al.anwenden("Die Lage in Kiew spitzt sich zu.", ORTE_BEISPIEL)
        self.assertEqual(out, "Die Lage in Kijef spitzt sich zu.")

    def test_englische_schreibweise_wird_auf_deutsche_aussprache_abgebildet(self):
        out = al.anwenden("Die Lage in Kyiv spitzt sich zu.", ORTE_BEISPIEL)
        self.assertEqual(out, "Die Lage in Kijef spitzt sich zu.")

    def test_beijing_wird_auf_peking_abgebildet(self):
        out = al.anwenden("Der Gipfel in Beijing dauert drei Tage.", ORTE_BEISPIEL)
        self.assertEqual(out, "Der Gipfel in Peking dauert drei Tage.")

    def test_wortgrenze_schuetzt_aehnlich_lautende_woerter(self):
        out = al.anwenden("Kyiva ist kein Ort.", ORTE_BEISPIEL)
        self.assertEqual(out, "Kyiva ist kein Ort.")  # kein eigenstaendiges Wort "Kyiv" -> unveraendert

    def test_echtes_lexikon_enthaelt_die_neuen_orte_und_abkuerzungen(self):
        eintraege = al.laden()["eintraege"]
        for name in ("Kiew", "Kiev", "Kyiv", "Kyjiw", "Charkiw", "Kharkiv", "Beijing", "Pyongyang", "Taipei"):
            self.assertIn(name, eintraege, f"{name} fehlt im Lexikon")


class NormalizeIntegrationTest(unittest.TestCase):
    def test_lexikon_wirkt_vor_der_zahlen_und_akronym_logik(self):
        with mock.patch("tts.aussprache_lexikon.laden", return_value={"eintraege": BEISPIEL}):
            out = normalize_for_tts("Erdoğan und Xi Jinping trafen Selenskyj, dazu 3 NATO-Staaten.")
        self.assertIn("Schi Dschinping", out)
        self.assertIn("Selenski", out)
        self.assertIn("NATO", out)   # Akronym-Liste bleibt unberuehrt vom Lexikon

    def test_haeufige_abkuerzungen_wie_ein_nachrichtensprecher(self):
        out = normalize_for_tts("UN, UNO, WHO, NATO, EU, IWF, WTO, OPEC, EZB, USA und UK sowie G7 und G20 trafen sich.")
        self.assertIn("U En", out)          # UN buchstabiert
        self.assertIn("UNO", out)           # als Wort gesprochen ("Uno")
        self.assertIn("We Ha O", out)       # WHO buchstabiert, nicht als Wort
        self.assertIn("NATO", out)          # als Wort gesprochen
        self.assertIn("E U", out)           # EU buchstabiert
        self.assertIn("I We Ef", out)       # IWF buchstabiert
        self.assertIn("We Te O", out)       # WTO buchstabiert
        self.assertIn("OPEC", out)          # als Wort gesprochen
        self.assertIn("E Zett Be", out)     # EZB buchstabiert
        self.assertIn("U Es A", out)        # USA buchstabiert
        self.assertIn("U Ka", out)          # UK buchstabiert
        self.assertIn("G Sieben", out)      # G7
        self.assertIn("G Zwanzig", out)     # G20

    def test_who_als_englisches_fragewort_bleibt_unberuehrt(self):
        out = normalize_for_tts('Im Zitat hiess es "who cares".')
        self.assertIn("who cares", out)     # kleingeschrieben, kein Akronym -> unveraendert


class LerneAusFolgeTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.tmp = Path(self._tmpdir.name)
        (self.tmp / "texte.json").write_text(json.dumps({
            "titel": "Test", "zentrale_these": "x",
            "szenen": [{"id": "s1", "text": "Recep Tayyip Erdoğan sprach mit Mario Mustermann."}],
        }), encoding="utf-8")

    def test_fuegt_vorgeschlagenen_eintrag_hinzu(self):
        fake_antwort = {"vorschlaege": [{"name": "Recep Tayyip Erdoğan", "sprich": "Redschep Tayyip Erdoan"},
                                        {"name": "Nicht Im Text", "sprich": "Unsinn"}]}
        with mock.patch.object(al, "laden", return_value=al.leer()), \
             mock.patch.object(al, "sichern") as sichern:
            ergebnis = al.lerne_aus_folge(self.tmp, frage_modell=lambda prompt: fake_antwort, log=lambda *_: None)
        self.assertEqual(ergebnis["neu"], ["Recep Tayyip Erdoğan"])
        sichern.assert_called_once()

    def test_fehlschlag_ist_nicht_fatal(self):
        def platzt(_prompt):
            raise RuntimeError("Claude-CLI nicht erreichbar")
        ergebnis = al.lerne_aus_folge(self.tmp, frage_modell=platzt, log=lambda *_: None)
        self.assertEqual(ergebnis["neu"], [])
        self.assertIn("Claude-CLI", ergebnis["fehler"])

    def test_bekannter_eintrag_wird_nicht_doppelt_vorgeschlagen(self):
        vorhanden = {"Recep Tayyip Erdoğan": {"sprich": "Redschep Tayyip Erdoan", "quelle": "manuell",
                                              "hinzugefuegt": "2026-10-01"}}
        gesehene_prompts = []

        def frage_modell(prompt):
            gesehene_prompts.append(prompt)
            return {"vorschlaege": []}

        with mock.patch.object(al, "laden", return_value={"eintraege": dict(vorhanden)}), \
             mock.patch.object(al, "sichern") as sichern:
            ergebnis = al.lerne_aus_folge(self.tmp, frage_modell=frage_modell, log=lambda *_: None)
        self.assertEqual(ergebnis["neu"], [])
        sichern.assert_not_called()
        self.assertIn("Recep Tayyip Erdoğan", gesehene_prompts[0])  # bekannte Liste steht im Prompt


if __name__ == "__main__":
    unittest.main()
