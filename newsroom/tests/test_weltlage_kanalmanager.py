"""Tests fuer tools/weltlage_kanalmanager.py: Uploads-Befund (folgen_24h/shorts_24h), Kennzahlen-Regex
(kennzahlen_aus_text), Strategie (strategie_ableiten) und das Ein-Experiment-Gatter. Komplett offline: kein
Playwright, kein Netz, Zustand in einem Temp-Ordner (Marlon 13.10.2026, Task 20261013-164355-df82).

    .venv\\Scripts\\python -m unittest tests.test_weltlage_kanalmanager
"""
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))

import weltlage_kanalmanager as km  # noqa: E402

JETZT = datetime(2026, 10, 13, 20, 0, tzinfo=timezone.utc).astimezone()


class FolgenTest(unittest.TestCase):
    def setUp(self):
        self._alt_slots = km.NEWS_WELTLAGE_SLOTS
        km.NEWS_WELTLAGE_SLOTS = ["11:00", "19:00"]

    def tearDown(self):
        km.NEWS_WELTLAGE_SLOTS = self._alt_slots

    def test_beide_slots_veroeffentlicht(self):
        laeufe = {
            "2026-10-13_11:00": {"video_id": "abc", "upload": {"veroeffentlicht_um":
                                 (JETZT - timedelta(hours=9)).isoformat()}},
            "2026-10-13_19:00": {"video_id": "def", "upload": {"veroeffentlicht_um":
                                 (JETZT - timedelta(hours=1)).isoformat()}},
        }
        r = km.folgen_24h(laeufe, JETZT)
        self.assertEqual(r["erwartet"], 2)
        self.assertEqual(r["fehlend"], [])
        self.assertEqual(len(r["hochgeladen"]), 2)

    def test_slot_fehlt(self):
        laeufe = {"2026-10-13_11:00": {"video_id": "abc", "upload": {"veroeffentlicht_um":
                  (JETZT - timedelta(hours=9)).isoformat()}}}
        r = km.folgen_24h(laeufe, JETZT)
        self.assertEqual(r["erwartet"], 2)
        self.assertEqual(r["fehlend"], ["2026-10-13_19:00"])

    def test_alter_lauf_faellt_aus_dem_fenster(self):
        laeufe = {"2026-10-12_19:00": {"video_id": "alt", "upload": {"veroeffentlicht_um":
                  (JETZT - timedelta(hours=25)).isoformat()}}}
        r = km.folgen_24h(laeufe, JETZT)
        self.assertEqual(r["hochgeladen"], [])

    def test_lauf_ohne_upload_wird_ignoriert(self):
        laeufe = {"2026-10-13_19:00": {"status": "laeuft"}}
        r = km.folgen_24h(laeufe, JETZT)
        self.assertEqual(r["hochgeladen"], [])
        self.assertIn("2026-10-13_19:00", r["fehlend"])


class ShortsTest(unittest.TestCase):
    def setUp(self):
        self._alt = km.NEWS_WELTLAGE_SHORTS_SLOTS
        km.NEWS_WELTLAGE_SHORTS_SLOTS = "02:00,08:00,14:00,20:00"

    def tearDown(self):
        km.NEWS_WELTLAGE_SHORTS_SLOTS = self._alt

    def test_erwartung_ueber_24h(self):
        r = km.shorts_24h({"hochgeladen": []}, JETZT, fenster_h=24)
        self.assertEqual(r["erwartet"], 4)

    def test_hochgeladene_im_fenster_gezaehlt(self):
        verlauf = {"hochgeladen": [
            {"zeit": (JETZT - timedelta(hours=2)).isoformat(), "video_id": "s1"},
            {"zeit": (JETZT - timedelta(hours=30)).isoformat(), "video_id": "zu_alt"},
        ]}
        r = km.shorts_24h(verlauf, JETZT, fenster_h=24)
        self.assertEqual(len(r["hochgeladen"]), 1)
        self.assertEqual(r["hochgeladen"][0]["video_id"], "s1")

    def test_leerer_verlauf(self):
        r = km.shorts_24h(None, JETZT)
        self.assertEqual(r["hochgeladen"], [])


class KennzahlenTest(unittest.TestCase):
    def test_deutsche_zahlen_tausenderpunkt(self):
        text = "Aufrufe\nAufrufe\n1.234\nAbonnenten\n+12"
        r = km.kennzahlen_aus_text(text)
        self.assertEqual(r["aufrufe"], 1234.0)
        self.assertEqual(r["abonnenten_aenderung_28_tage"], 12.0)

    def test_wiedergabezeit_ist_dezimalpunkt_kein_tausendertrenner(self):
        # Vorfall 13.10.2026 (live gegen den echten Kanal verifiziert): die Wiedergabezeit-Kachel zeigt "2.4"
        # (= 2,4 Stunden), waehrend Aufrufe/Abonnenten echten Tausenderpunkt nutzen ("1.234").
        text = "Wiedergabezeit (Stunden)\n2.4\nDie geschaetzte Gesamtwiedergabezeit"
        r = km.kennzahlen_aus_text(text)
        self.assertEqual(r["wiedergabezeit_std"], 2.4)

    def test_grosse_wiedergabezeit_waere_trotzdem_tausendertrenner(self):
        text = "Wiedergabezeit (Stunden)\n1.234\nText"
        r = km.kennzahlen_aus_text(text)
        self.assertEqual(r["wiedergabezeit_std"], 1234.0)

    def test_fehlende_zahl_bleibt_none(self):
        r = km.kennzahlen_aus_text("nur irrelevanter Text ohne Kennzahlen")
        self.assertIsNone(r["aufrufe"])
        self.assertIsNone(r["abonnenten_aenderung_28_tage"])

    def test_englische_variante(self):
        text = "Views\nViews\n980\nSubscribers\n+7"
        r = km.kennzahlen_aus_text(text)
        self.assertEqual(r["aufrufe"], 980.0)
        self.assertEqual(r["abonnenten_aenderung_28_tage"], 7.0)


# Realer Seitentext der Studio-Analytics-Uebersicht (.../analytics/tab-overview/period-default), live gegen den
# echten Kanal Weltlage Kompakt abgerufen (13.10.2026) - Titel/Zahlen echt, dient als stabiles Regressionsmuster
# fuer kennzahlen_aus_text/inhalte_tabelle, falls Studio die Seite umbaut.
ECHTER_SEITENTEXT = """Kanalanalysen
Dashboard
Inhalte
Analytics
15.09. - 12.10.2026
Letzte 28 Tage
Dein Kanal hat in den letzten 28 Tagen 524 Aufrufe erzielt
Aufrufe
Aufrufe
524
Gesamtzahl der Aufrufe fuer den ausgewaehlten Zeitraum.
Wiedergabezeit (Stunden)
2.4
Die geschaetzte Gesamtwiedergabezeit deiner Videos (in Stunden).
Abonnenten
+4
Die Veraenderung bei der Gesamtzahl der Abonnenten.
Deine erfolgreichsten Inhalte in diesem Zeitraum
Inhalte
Durchschnittliche Wiedergabedauer
Aufrufe
1
Trump verkuendet Waffenruhe - Selenskyj weiss von NICHTS?
12.10.2026
Neuer Upload
0:20
(78,0 %)
432
2
Burnham verdaechtigt Iran + London zahlt 6 Prozent: EIN Krieg?
02.10.2026
0:13
(4,3 %)
24
3
Trump will Putin wegen Pest-Tod anrufen + Ex-BND-Chef in Haft?
08.10.2026
Neuer Upload
1:39
(14,4 %)
18
Mehr anzeigen
Echtzeit
Echtzeitdaten
4
Abonnenten
Aktuelle Anzahl anzeigen
623
Aufrufe - Letzte 48 Stunden
"""


class EchterSeitentextTest(unittest.TestCase):
    """Regression gegen den am 13.10.2026 live erfassten Studio-Text (siehe ECHTER_SEITENTEXT oben)."""

    def test_kennzahlen(self):
        r = km.kennzahlen_aus_text(ECHTER_SEITENTEXT)
        self.assertEqual(r["aufrufe"], 524.0)
        self.assertEqual(r["wiedergabezeit_std"], 2.4)
        self.assertEqual(r["abonnenten_aenderung_28_tage"], 4.0)

    def test_inhalte_tabelle(self):
        r = km.inhalte_tabelle(ECHTER_SEITENTEXT)
        self.assertEqual(len(r), 3)
        self.assertEqual(r[0], {"rang": 1, "titel": "Trump verkuendet Waffenruhe - Selenskyj weiss von NICHTS?",
                                "aufrufe": 432})
        self.assertEqual(r[-1]["aufrufe"], 18)

    def test_inhalte_tabelle_fehlende_marker_gibt_leere_liste(self):
        self.assertEqual(km.inhalte_tabelle("Text ganz ohne die bekannten Marker"), [])


class StrategieTest(unittest.TestCase):
    def test_wenig_messpunkte_keine_anpassung(self):
        uploads = {"folgen": {"erwartet": 2, "hochgeladen": [1, 2], "fehlend": []},
                   "shorts": {"erwartet": 4, "hochgeladen": [1, 2, 3, 4]}}
        s = km.strategie_ableiten(uploads, {"aufrufe": 100.0, "abgerufen_um": "x"}, [])
        self.assertEqual(s["risikoarm_vorschlaege"], [])
        self.assertIsNone(s["experiment_vorschlag"])
        self.assertTrue(any("Messpunkte" in e for e in s["erkenntnisse"]))

    def test_fehlende_folge_wird_genannt(self):
        uploads = {"folgen": {"erwartet": 2, "hochgeladen": [], "fehlend": ["2026-10-13_19:00"]},
                   "shorts": {"erwartet": 4, "hochgeladen": []}}
        s = km.strategie_ableiten(uploads, {}, [])
        self.assertTrue(any("2026-10-13_19:00" in e for e in s["erkenntnisse"]))

    def test_analytics_fehler_wird_gemeldet_statt_absturz(self):
        uploads = {"folgen": {"erwartet": 0, "hochgeladen": [], "fehlend": []},
                   "shorts": {"erwartet": 0, "hochgeladen": []}}
        s = km.strategie_ableiten(uploads, {"fehler": "Studio nicht erreichbar"}, [])
        self.assertTrue(any("nicht lesbar" in e for e in s["erkenntnisse"]))

    def test_risikoarm_anwenden_ohne_vorschlaege_tut_nichts(self):
        self.assertEqual(km.risikoarm_anwenden([]), [])


class ExperimentTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._alt = km.EXPERIMENT_PFAD
        km.EXPERIMENT_PFAD = self.tmp / "experiment.json"

    def tearDown(self):
        km.EXPERIMENT_PFAD = self._alt

    def test_erstes_experiment_wird_angenommen(self):
        stand = km.experiment_vorschlagen("staerkere Gestik")
        self.assertEqual(stand["status"], "vorgeschlagen")
        self.assertEqual(stand["idee"], "staerkere Gestik")

    def test_zweites_experiment_wird_abgewiesen_solange_eins_offen_ist(self):
        km.experiment_vorschlagen("idee a")
        stand = km.experiment_vorschlagen("idee b")
        self.assertEqual(stand["idee"], "idee a")

    def test_antwort_setzt_status(self):
        km.experiment_vorschlagen("idee a")
        stand = km.experiment_antwort(True)
        self.assertEqual(stand["status"], "angenommen")
        stand2 = km.experiment_stand()
        self.assertEqual(stand2["status"], "angenommen")

    def test_nach_antwort_kann_neues_experiment_vorgeschlagen_werden(self):
        km.experiment_vorschlagen("idee a")
        km.experiment_antwort(False)
        stand = km.experiment_vorschlagen("idee b")
        self.assertEqual(stand["idee"], "idee b")

    def test_ohne_vorherigen_stand_ist_keins(self):
        self.assertEqual(km.experiment_stand(), {"status": "keins"})


if __name__ == "__main__":
    unittest.main()
