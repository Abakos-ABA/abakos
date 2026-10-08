"""Offline-Test fuer tools/weltlage_abnahme.pipeline_probleme (Task 20261003-165139-41e9, 03.10.2026): eine
eingefrorene Sprechszene (Begruessung/Verabschiedung) darf nicht unbemerkt ohne einen neuen Pipeline-Schalter (z.B.
Compositing-FX, Schatten/Spiegelung/Licht) weiterverwendet werden, so wie es der heutigen Begruessungs-Szene
passierte: sie wurde vor der Einfuehrung von video/composite_fx.py eingefroren, 4e (Lipsync-Staerke/HD) war trotzdem
gruen, weil composite_fx kein Feld dieser Pruefung war. Anders als 4e/guidance_probleme() (ein Feld pro Pruefung,
von Hand ergaenzt) deckt pipeline_probleme() das vollstaendige, generische Signatur-Dict ab, damit der naechste neue
Schalter nicht denselben Weg wie composite_fx geht.

    .venv\\Scripts\\python -m unittest tests.test_weltlage_frozen_fx
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import weltlage_abnahme as a  # noqa: E402


class PipelineProbleme(unittest.TestCase):
    def test_passende_fassung_ok(self):
        meta = {"pipeline": {"guidance": 2.0, "hd": True, "composite_fx": True}}
        self.assertEqual(a.pipeline_probleme(meta, {"guidance": 2.0, "hd": True, "composite_fx": True}), [])

    def test_fehlendes_pipeline_feld_ist_nur_warnung(self):
        probleme = a.pipeline_probleme({}, {"composite_fx": True})
        self.assertEqual(len(probleme), 1)
        self.assertIn("ohne 'pipeline'-Feld", probleme[0])

    def test_alte_signatur_ohne_neuen_schalter_wird_erkannt(self):
        """Genau der heutige Vorfall: Signatur vorhanden (guidance/hd), aber ohne das composite_fx-Feld, das erst
        spaeter dazukam - das muss ein Problem sein, keine stille Ausnahme."""
        meta = {"pipeline": {"guidance": 2.0, "hd": True}}
        probleme = a.pipeline_probleme(meta, {"guidance": 2.0, "hd": True, "composite_fx": True})
        self.assertTrue(any("composite_fx" in p for p in probleme))

    def test_abweichender_wert_wird_erkannt(self):
        meta = {"pipeline": {"guidance": 1.5, "hd": True, "composite_fx": True}}
        probleme = a.pipeline_probleme(meta, {"guidance": 2.0, "hd": True, "composite_fx": True})
        self.assertTrue(any("1.5" in p for p in probleme))

    def test_kuenftiger_schalter_wird_ohne_codeaenderung_erfasst(self):
        """pipeline_probleme() ist generisch: ein ganz neuer, in diesem Test erfundener Schluessel wird genauso
        geprueft wie guidance/hd/composite_fx, ohne dass die Funktion dafuer angepasst werden muss."""
        meta = {"pipeline": {"irgendein_neuer_schalter": False}}
        probleme = a.pipeline_probleme(meta, {"irgendein_neuer_schalter": True})
        self.assertTrue(any("irgendein_neuer_schalter" in p for p in probleme))


    def test_steps_nur_rechenzeit_ist_warnung(self):
        """Vorfall 08.10.2026: das neue Signatur-Feld "steps" (Lipsync 12 statt 20 Schritte) liess jede Folge an der
        eingefrorenen Begruessung/Abschluss durchfallen - steps aendert nur die Rechenzeit, nie ein Abbruch."""
        aktuell = {"guidance": 2.0, "hd": True, "composite_fx": True, "steps": 12}
        alt = {"pipeline": {"guidance": 2.0, "hd": True, "composite_fx": True}}
        self.assertEqual(a.pipeline_probleme(alt, aktuell), [])
        self.assertIn("'steps'", a.pipeline_hinweise(alt, aktuell)[0])
        self.assertIn("steps=20", a.pipeline_hinweise({"pipeline": {**alt["pipeline"], "steps": 20}}, aktuell)[0])
        self.assertEqual(a.pipeline_hinweise({"pipeline": {**alt["pipeline"], "steps": 12}}, aktuell), [])
        self.assertTrue(a.pipeline_probleme({"pipeline": {"hd": True, "composite_fx": True, "steps": 12}}, aktuell),
                        "fehlende Bild-Felder bleiben ein Fehler")

if __name__ == "__main__":
    unittest.main()
