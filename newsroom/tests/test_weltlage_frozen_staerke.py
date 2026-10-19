"""Offline-Test fuer tools/weltlage_abnahme.guidance_probleme: eingefrorene Sprechszenen (Begruessung/
Verabschiedung) duerfen nicht unbemerkt mit einer alten Lipsync-Staerke/HD-Stufe weiterverwendet werden
(Task 20261002-163146-afaf, 02.10.2026).

Seit 20.10.2026 (Task 20261020-002406-1486) dazu guidance_einordnung/guidance_hinweise: die Staerke einer
HOEHEREN Drosselstufe (config.settings.NEWS_LIPSYNC_STUFEN, kleinere Nummer = mehr Staerke/Schritte) ist kein
Abbruch mehr, nur ein Hinweis - Vorfall 19.10.2026: Marlons Umstellung von Stufe 1 (2,0) auf Stufe 2 (1,5) kam
in den Code, waehrend der Rohschnitt der 10:00-Folge mit 2,0 lief; die Abnahme liess die 9-h-Folge durchfallen.

    .venv\\Scripts\\python -m unittest tests.test_weltlage_frozen_staerke
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import weltlage_abnahme as a  # noqa: E402


class GuidanceProbleme(unittest.TestCase):
    def test_passende_fassung_ok(self):
        self.assertEqual(a.guidance_probleme({"guidance": 2.0, "hd": True}, 2.0, True), [])

    def test_fehlendes_feld_ist_nur_warnung(self):
        probleme = a.guidance_probleme({}, 2.0, True)
        self.assertEqual(len(probleme), 1)
        self.assertIn("ohne 'guidance'-Feld", probleme[0])

    def test_alte_staerke_wird_erkannt(self):
        """Schwaechere Stufe als heute verlangt (1,5 = Stufe 2, Standard 2,0 = Stufe 1) bleibt ein Fehler."""
        probleme = a.guidance_probleme({"guidance": 1.5, "hd": True}, 2.0, True)
        self.assertTrue(any("1.5" in p for p in probleme))

    def test_falsche_hd_stufe_wird_erkannt(self):
        probleme = a.guidance_probleme({"guidance": 2.0, "hd": False}, 2.0, True)
        self.assertTrue(any("hd=False" in p for p in probleme))

    def test_hd_default_false_wenn_feld_fehlt(self):
        probleme = a.guidance_probleme({"guidance": 2.0}, 2.0, False)
        self.assertEqual(probleme, [])


class HoehereStufeBleibtGueltig(unittest.TestCase):
    """Vorfall 19.10.2026: Stuecke/Szenen mit der Staerke einer hoeheren Drosselstufe (gebaut vor einer
    Umstellung nach unten) sind mindestens gleich gut - Hinweis statt Abbruch."""

    def test_einordnung_gleich_ist_ok(self):
        self.assertEqual(a.guidance_einordnung(1.5, 1.5), ("ok", ""))

    def test_einordnung_hoehere_stufe_ist_hinweis(self):
        art, text = a.guidance_einordnung(2.0, 1.5)
        self.assertEqual(art, "hinweis")
        self.assertIn("Drosselstufe 1", text)
        self.assertIn("bleibt gueltig", text)

    def test_einordnung_schwaechere_stufe_ist_fehler(self):
        self.assertEqual(a.guidance_einordnung(1.2, 1.5)[0], "fehler")
        self.assertEqual(a.guidance_einordnung(1.0, 1.5)[0], "fehler")

    def test_einordnung_unbekannter_wert_ist_fehler(self):
        """Werte ausserhalb der Stufentabelle (z.B. frei per Umgebungsvariable gesetzt) nur bei Gleichheit ok."""
        self.assertEqual(a.guidance_einordnung(2.5, 1.5)[0], "fehler")
        self.assertEqual(a.guidance_einordnung(None, 1.5)[0], "fehler")
        self.assertEqual(a.guidance_einordnung("kaputt", 1.5)[0], "fehler")
        self.assertEqual(a.guidance_einordnung(2.5, 2.5), ("ok", ""))

    def test_einordnung_standard_ausserhalb_der_tabelle_nur_gleichheit(self):
        """Ist der Standard selbst kein Tabellenwert, gibt es keine Stufen-Toleranz."""
        self.assertEqual(a.guidance_einordnung(2.0, 1.7)[0], "fehler")

    def test_stufe_von_guidance(self):
        self.assertEqual(a.guidance_stufe(2.0), 1)
        self.assertEqual(a.guidance_stufe("1.5"), 2)
        self.assertIsNone(a.guidance_stufe(1.7))
        self.assertIsNone(a.guidance_stufe(None))

    def test_eingefrorene_szene_hoehere_stufe_kein_problem_aber_hinweis(self):
        meta = {"guidance": 2.0, "hd": True}
        self.assertEqual(a.guidance_probleme(meta, 1.5, True), [])
        hinweise = a.guidance_hinweise(meta, 1.5)
        self.assertEqual(len(hinweise), 1)
        self.assertIn("Drosselstufe 1", hinweise[0])

    def test_eingefrorene_szene_streng_vor_neuem_render(self):
        """Vor einem neuen Render (tools/weltlage_tageslauf.feste_szenen_veraltet) zaehlt jede Abweichung."""
        probleme = a.guidance_probleme({"guidance": 2.0, "hd": True}, 1.5, True, streng=True)
        self.assertEqual(len(probleme), 1)
        self.assertIn("2.0", probleme[0])
        self.assertEqual(a.guidance_probleme({"guidance": 1.5, "hd": True}, 1.5, True, streng=True), [])

    def test_keine_hinweise_ohne_feld_oder_bei_gleichheit(self):
        self.assertEqual(a.guidance_hinweise({}, 1.5), [])
        self.assertEqual(a.guidance_hinweise({"guidance": 1.5}, 1.5), [])
        self.assertEqual(a.guidance_hinweise({"guidance": 1.2}, 1.5), [])   # Fehler, kein Hinweis


if __name__ == "__main__":
    unittest.main()
