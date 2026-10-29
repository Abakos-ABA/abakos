"""Tests fuer tools/weltlage_themen.py: Wiederholungs-Schutz (vergangene_folgen/aehnlichkeit/ist_wiederholung,
pruefen/vorschlagen) und Aktualitaets-Check (aktualitaet_pruefen) der Vortagswahl (rexemre 07.10.2026,
Task 20261007-174635-f7ff). Komplett offline: kein LLM, kein Telegram, keine GPU - Zustand in einem Temp-Ordner.

    .venv\\Scripts\\python -m unittest tests.test_weltlage_themen
"""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))

import weltlage_themen as th  # noqa: E402


JETZT = datetime(2026, 10, 7, 16, 0, tzinfo=timezone.utc).astimezone()


class Basis(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._alt_data, self._alt_pool = th.DATA_DIR, th.POOL
        th.DATA_DIR = self.tmp / "data"
        th.POOL = self.tmp / "state" / "weltlage_themenpool.json"
        th.DATA_DIR.mkdir(parents=True)

    def tearDown(self):
        th.DATA_DIR, th.POOL = self._alt_data, self._alt_pool

    def _ordner(self, name):
        p = th.DATA_DIR / name
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _raw(self, titel, snippet, published_at, source="Test", unterordner="2026-10-07"):
        d = th.DATA_DIR / "raw" / unterordner
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"{abs(hash((titel, published_at)))}.json"
        p.write_text(json.dumps({"title": titel, "snippet": snippet, "source": source, "url": f"https://x/{p.stem}",
                                  "published_at": published_at}, ensure_ascii=False), encoding="utf-8")


class Aehnlichkeit(Basis):
    def test_identisch(self):
        self.assertEqual(th.aehnlichkeit("Entreisst Saudi-Arabien den Huthis die Meerenge?",
                                          "Entreisst Saudi-Arabien den Huthis die Meerenge?"), 1.0)

    def test_voellig_verschieden(self):
        self.assertEqual(th.aehnlichkeit("Entreisst Saudi-Arabien den Huthis die Meerenge Bab al-Mandab?",
                                          "Stuerzt Flavio Bolsonaro in Brasilien Lula am 25. Oktober?"), 0.0)

    def test_gleiches_thema_anderer_titel(self):
        a = "Al-Alimi stuermt Mokha: Entreisst er den Huthis die Meerenge?"
        b = "Entreisst Saudi-Arabien den Huthis die Meerenge Bab al-Mandab?"
        self.assertGreaterEqual(th.aehnlichkeit(a, b), 0.3)

    def test_leerer_text(self):
        self.assertEqual(th.aehnlichkeit("", "Irgendein Titel?"), 0.0)


class VergangeneFolgen(Basis):
    def test_metadaten_json_bevorzugt(self):
        o = self._ordner("weltlage_20261005_1100")
        (o / "metadaten.json").write_text(json.dumps({"title": "Folge A?", "description": "Inhalt A"}),
                                          encoding="utf-8")
        out = th.vergangene_folgen(tage=14, jetzt=JETZT)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["titel"], "Folge A?")
        self.assertEqual(out[0]["inhalt"], "Inhalt A")

    def test_wahl_storylines_fallback_ohne_metadaten(self):
        o = self._ordner("weltlage_20261007_1900")
        (o / "wahl.json").write_text(json.dumps({"wahl": "B", "titel": "Folge B?"}), encoding="utf-8")
        (o / "storylines.json").write_text(json.dumps({"storylines": [
            {"buchstabe": "A", "titel": "Folge A?", "inhalt": "Inhalt A"},
            {"buchstabe": "B", "titel": "Folge B?", "inhalt": "Inhalt B"}]}), encoding="utf-8")
        out = th.vergangene_folgen(tage=14, jetzt=JETZT)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["titel"], "Folge B?")
        self.assertEqual(out[0]["inhalt"], "Inhalt B")

    def test_zu_alt_faellt_raus(self):
        o = self._ordner("weltlage_20260901_1100")
        (o / "metadaten.json").write_text(json.dumps({"title": "Alte Folge?", "description": "x"}), encoding="utf-8")
        self.assertEqual(th.vergangene_folgen(tage=14, jetzt=JETZT), [])

    def test_ordner_ohne_datum_ignoriert(self):
        o = self._ordner("weltlage_20261001_probe_dialog")
        (o / "metadaten.json").write_text(json.dumps({"title": "Probe?", "description": "x"}), encoding="utf-8")
        self.assertEqual(th.vergangene_folgen(tage=14, jetzt=JETZT), [])

    def test_neueste_zuerst(self):
        for name, titel in (("weltlage_20261001_1100", "Alt?"), ("weltlage_20261006_1900", "Neu?")):
            o = self._ordner(name)
            (o / "metadaten.json").write_text(json.dumps({"title": titel, "description": "x"}), encoding="utf-8")
        out = th.vergangene_folgen(tage=14, jetzt=JETZT)
        self.assertEqual([f["titel"] for f in out], ["Neu?", "Alt?"])


class IstWiederholung(Basis):
    def setUp(self):
        super().setUp()
        self.vergangene = [{"ordner": "x", "datum": "2026-10-07T11:00",
                            "titel": "Al-Alimi stuermt Mokha: Entreisst er den Huthis die Meerenge?",
                            "inhalt": "Jemens Praesidialratschef schickt Truppen gegen die Huthis am Roten Meer."}]

    def test_aehnliches_thema_erkannt(self):
        s = {"buchstabe": "A", "titel": "Entreisst Saudi-Arabien den Huthis die Meerenge Bab al-Mandab?",
             "inhalt": "Saudi-Arabien unterstuetzt eine Offensive gegen die Huthis am Roten Meer."}
        dup = th.ist_wiederholung(s, self.vergangene, schwelle=0.25)
        self.assertIsNotNone(dup)
        self.assertEqual(dup["ordner"], "x")

    def test_anderes_thema_nicht_erkannt(self):
        s = {"buchstabe": "C", "titel": "Stuerzt Flavio Bolsonaro in Brasilien Lula am 25. Oktober?",
             "inhalt": "Eine Abstimmung in Brasilia koennte die Regierung Lula stuerzen."}
        self.assertIsNone(th.ist_wiederholung(s, self.vergangene, schwelle=0.25))


class Pruefen(Basis):
    def test_wiederholung_wird_als_fehler_gemeldet(self):
        artikel = [{"nr": 1}, {"nr": 2}, {"nr": 3}]
        vergangene = [{"ordner": "x", "datum": "2026-10-07T11:00", "titel": "Entreisst Saudi-Arabien den Huthis "
                      "die Meerenge Bab al-Mandab?", "inhalt": "Saudi-Arabien kaempft gegen die Huthis."}]
        d = {"storylines": [{"buchstabe": "A", "titel": "Entreisst Saudi-Arabien den Huthis die Meerenge erneut?",
                             "inhalt": "Saudi-Arabien kaempft weiter gegen die Huthis am Roten Meer.",
                             "meldungen": [[1, 2]]},
                            {"buchstabe": "B", "titel": "Stuerzt Lula ueber Bolsonaros Sohn?",
                             "inhalt": "Eine Abstimmung bedroht die Regierung.", "meldungen": [[2, 3]]},
                            {"buchstabe": "C", "titel": "Droht Irkutsk eine Pest-Welle?",
                             "inhalt": "Russland verschweigt einen Pest-Fall.", "meldungen": [[1, 3]]}],
             "empfehlung": "B"}
        fehler = th.pruefen(d, artikel, 3, vergangene)
        self.assertTrue(any("A" in f and "aehnlich" in f for f in fehler), fehler)

    def test_ohne_vergangene_kein_zusaetzlicher_fehler(self):
        artikel = [{"nr": 1}, {"nr": 2}]
        d = {"storylines": [{"buchstabe": "A", "titel": "Frage?", "inhalt": "Inhalt", "meldungen": [[1, 2]]}]}
        self.assertEqual(th.pruefen(d, artikel, 1, None), [])


class Vorschlagen(Basis):
    def setUp(self):
        super().setUp()
        self.artikel = [{"nr": i, "title": f"Artikel {i}", "source": "Test", "published_at": "2026-10-07T10:00",
                         "snippet": "x"} for i in range(1, 7)]
        self.vergangene = [{"ordner": "x", "datum": "2026-10-07T11:00", "titel": "Entreisst Saudi-Arabien den "
                           "Huthis die Meerenge Bab al-Mandab?", "inhalt": "Saudi-Arabien kaempft gegen die "
                           "Huthis am Roten Meer."}]
        self.gut = {"storylines": [
            {"buchstabe": "A", "titel": "Droht Irkutsk eine Pest-Welle?", "inhalt": "Russland verschweigt Faelle.",
             "meldungen": [[1, 2]], "gruene_quellen": []},
            {"buchstabe": "B", "titel": "Stuerzt Lula ueber Bolsonaros Sohn?", "inhalt": "Eine Abstimmung droht.",
             "meldungen": [[2, 3]], "gruene_quellen": []},
            {"buchstabe": "C", "titel": "Erreicht der Taifun Taiwan?", "inhalt": "Ein Sturm naehert sich.",
             "meldungen": [[3, 4]], "gruene_quellen": []}], "empfehlung": "A"}
        self.schlecht = {"storylines": [
            {"buchstabe": "A", "titel": "Entreisst Saudi-Arabien den Huthis die Meerenge erneut?",
             "inhalt": "Saudi-Arabien kaempft weiter gegen die Huthis am Roten Meer.", "meldungen": [[1, 2]],
             "gruene_quellen": []},
            {"buchstabe": "B", "titel": "Stuerzt Lula ueber Bolsonaros Sohn?", "inhalt": "Eine Abstimmung droht.",
             "meldungen": [[2, 3]], "gruene_quellen": []},
            {"buchstabe": "C", "titel": "Erreicht der Taifun Taiwan?", "inhalt": "Ein Sturm naehert sich.",
             "meldungen": [[3, 4]], "gruene_quellen": []}], "empfehlung": "A"}

    def test_retry_ersetzt_wiederholung(self):
        rufe = []

        def modell(prompt):
            rufe.append(prompt)
            return self.schlecht if len(rufe) == 1 else self.gut

        d = th.vorschlagen(self.tmp / "ordner", modell=modell, artikel=self.artikel, vergangene=self.vergangene)
        self.assertEqual(len(rufe), 2)
        self.assertIn("Entreisst Saudi-Arabien den Huthis die Meerenge Bab al-Mandab", rufe[0])
        titel_a = th.storyline(d, "A")["titel"]
        self.assertEqual(titel_a, "Droht Irkutsk eine Pest-Welle?")

    def test_bleibt_wiederholung_nach_retry_wirft_fehler(self):
        with self.assertRaises(RuntimeError):
            th.vorschlagen(self.tmp / "ordner", modell=lambda prompt: self.schlecht, artikel=self.artikel,
                           vergangene=self.vergangene)

    def test_feste_storyline_ueberspringt_wiederholungs_check(self):
        feste = {"titel": "Entreisst Saudi-Arabien den Huthis die Meerenge erneut?",
                 "inhalt": "Saudi-Arabien kaempft weiter gegen die Huthis am Roten Meer."}
        einzeln = {"storylines": [{"buchstabe": "A", **feste, "meldungen": [[1, 2]], "gruene_quellen": []}],
                   "empfehlung": "A"}
        d = th.vorschlagen(self.tmp / "ordner", feste=feste, modell=lambda prompt: einzeln, artikel=self.artikel,
                           vergangene=self.vergangene)
        self.assertEqual(th.storyline(d, "A")["titel"], feste["titel"])


class AktualitaetPruefen(Basis):
    def _folge(self, erstellt="2026-10-07T16:00:00+02:00"):
        o = self._ordner("weltlage_20261008_1100")
        (o / "wahl.json").write_text(json.dumps({"wahl": "A", "titel": "Entreisst Saudi-Arabien den Huthis die "
                                                 "Meerenge Bab al-Mandab?"}), encoding="utf-8")
        (o / "storylines.json").write_text(json.dumps({"erstellt": erstellt, "storylines": [
            {"buchstabe": "A", "titel": "Entreisst Saudi-Arabien den Huthis die Meerenge Bab al-Mandab?",
             "inhalt": "Saudi-Arabien unterstuetzt eine Offensive gegen die Huthis am Roten Meer."}]}),
            encoding="utf-8")
        return o

    def _mitteilen_abfangen(self):
        import weltlage_entscheid as ent
        alt = ent.mitteilen
        gerufen = []
        ent.mitteilen = lambda titel, text, *a, **kw: gerufen.append((titel, text))
        self.addCleanup(lambda: setattr(ent, "mitteilen", alt))
        return gerufen

    def test_neue_meldung_nach_recherche_warnt(self):
        o = self._folge()
        self._raw("Huthis ziehen sich aus Bab al-Mandab zurueck", "neue Entwicklung am Roten Meer",
                  "2026-10-08T09:00:00+00:00")
        gerufen = self._mitteilen_abfangen()
        jetzt = datetime(2026, 10, 8, 10, 30, tzinfo=timezone.utc)
        hinweis = th.aktualitaet_pruefen(o, jetzt=jetzt)
        self.assertIsNotNone(hinweis)
        self.assertEqual(len(hinweis["neue_artikel"]), 1)
        self.assertTrue((o / "aktualitaet_hinweis.json").exists())
        self.assertEqual(len(gerufen), 1)
        self.assertIn("Huthis ziehen sich", gerufen[0][1])

    def test_keine_neue_meldung_kein_hinweis(self):
        o = self._folge()
        self._raw("Huthis ziehen sich aus Bab al-Mandab zurueck", "neue Entwicklung am Roten Meer",
                  "2026-10-07T12:00:00+00:00")  # vor der Recherche (erstellt 16:00 lokal = 14:00 UTC)
        gerufen = self._mitteilen_abfangen()
        jetzt = datetime(2026, 10, 8, 10, 30, tzinfo=timezone.utc)
        self.assertIsNone(th.aktualitaet_pruefen(o, jetzt=jetzt))
        self.assertEqual(gerufen, [])

    def test_schon_gemeldet_kein_zweiter_hinweis(self):
        o = self._folge()
        (o / "aktualitaet_hinweis.json").write_text("{}", encoding="utf-8")
        gerufen = self._mitteilen_abfangen()
        self.assertIsNone(th.aktualitaet_pruefen(o, jetzt=datetime(2026, 10, 8, 10, 30, tzinfo=timezone.utc)))
        self.assertEqual(gerufen, [])

    def test_unaehnliche_meldung_ignoriert(self):
        o = self._folge()
        self._raw("Taifun erreicht Taiwan", "ein Sturm naehert sich der Insel", "2026-10-08T09:00:00+00:00")
        gerufen = self._mitteilen_abfangen()
        jetzt = datetime(2026, 10, 8, 10, 30, tzinfo=timezone.utc)
        self.assertIsNone(th.aktualitaet_pruefen(o, jetzt=jetzt))
        self.assertEqual(gerufen, [])


if __name__ == "__main__":
    unittest.main()
