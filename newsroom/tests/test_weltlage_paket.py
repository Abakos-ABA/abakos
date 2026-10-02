"""Offline-Tests der Paket-Regeln vom 01.10.2026 (Task 20261001-152131-dffa): Hook/Titel/Thumbnail/Ich-Form/
Kommentarfrage-Pruefung, Upload-Fortschritt, Slot-Planung des Tageslaufs, Metadaten, Thumbnail-Vorlage.

    .venv\\Scripts\\python.exe -m unittest tests.test_weltlage_paket -v
"""
import copy
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import weltlage_skript as ws  # noqa: E402
import weltlage_tageslauf as wt  # noqa: E402
from upload.youtube_playwright import upload_stand  # noqa: E402

GUT = {
    "analyse": {"akteure": [{"person": "Donald Trump", "funktion": "US-Präsident"},
                            {"person": "Wolodymyr Selenskyj", "funktion": "Präsident der Ukraine"},
                            {"person": "Christine Lagarde", "funktion": "EZB-Präsidentin"}]},
    "titel": "Trump stellt Kiew ein Ultimatum + Lagarde warnt vor 4 Prozent?",
    "titel_varianten": ["Trump stellt Kiew ein Ultimatum + Lagarde warnt vor 4 Prozent?",
                        "Selenskyj unter Druck: Was will Trump wirklich?",
                        "Lagarde warnt, Trump droht: Wer zahlt die Rechnung?"],
    "thumbnail": {"banderole": "ULTIMATUM", "zeile1": "TRUMP DROHT", "zeile2": "KIEW 48 STUNDEN",
                  "farbe": "konflikt"},
    "thumbnail_text": "TRUMP DROHT KIEW 48 STUNDEN",
    "zentrale_these": "Zwei Drohungen, ein Preis.",
    "hook": "Trump gibt Selenskyj 48 Stunden für eine Antwort, und Lagarde warnt gleichzeitig vor vier Prozent "
            "Inflation [BILD: EZB-Turm]. Wie hängt das zusammen? Das alles gleich in Weltlage Kompakt.",
    "hook_themen": [{"meldung": 1, "stichwort": "Selenskyj"}, {"meldung": 2, "stichwort": "Lagarde"}],
    "abschnitte": [
        {"rolle": "ausgangslage", "kurz": "Trumps Frist", "meldungen": [1],
         "text": "Am Montag schreibt Trump auf Truth Social: «Time is running out for Kiev». Ich finde den Ton "
                 "bemerkenswert [BILD: Post]."},
        {"rolle": "verbindung", "kurz": "Geld und Krieg", "meldungen": [1, 2],
         "text": "Lagarde sagte in Frankfurt, die Lage sei ernst. Meine Einschätzung: Beides gehört zusammen."},
        {"rolle": "einordnung", "kurz": "was jetzt kommt", "meldungen": [2],
         "text": "Ich halte eine Einigung in 48 Stunden für unwahrscheinlich. Mir fällt auf, wie still Brüssel bleibt."},
        {"rolle": "schluss", "kurz": "die offene Frage", "meldungen": [1],
         "text": "Die eigentliche Frage ist, wer zuerst nachgibt. Schreib mir deine Antwort in die Kommentare: "
                 "Gibt Selenskyj nach, eher ja oder eher nein?"},
    ],
    "meinungen": ["Ich finde den Ton bemerkenswert.", "Meine Einschätzung: Beides gehört zusammen.",
                  "Ich halte eine Einigung in 48 Stunden für unwahrscheinlich."],
    "kommentarfrage": "Gibt Selenskyj nach, eher ja oder eher nein?",
    "zitate": [], "handlungen": [],
}


class PaketPruefung(unittest.TestCase):
    def test_gutes_skript_ohne_harte_fehler(self):
        hart, _ = ws.paket_pruefen(copy.deepcopy(GUT))
        self.assertEqual(hart, [])

    def test_hook_muss_alle_themen_nennen(self):
        s = copy.deepcopy(GUT)
        s["abschnitte"][1]["meldungen"] = [3, 1]
        s["abschnitte"][2]["meldungen"] = [3]
        hart, _ = ws.paket_pruefen(s)
        self.assertTrue(any("Meldung 3 fehlt im Hook" in h for h in hart), hart)

    def test_hook_zu_viele_saetze(self):
        s = copy.deepcopy(GUT)
        s["hook"] = "Trump droht. Selenskyj schweigt. Lagarde warnt. Brüssel zögert. Das alles gleich in Weltlage Kompakt."
        hart, _ = ws.paket_pruefen(s)
        self.assertTrue(any("Sätze" in h for h in hart), hart)

    def test_titel_ohne_namen_und_zu_lang(self):
        s = copy.deepcopy(GUT)
        s["titel"] = "Die Lage spitzt sich zu, und niemand weiss, was in den nächsten Tagen noch alles passiert?"
        hart, _ = ws.paket_pruefen(s)
        self.assertTrue(any("keine Person" in h for h in hart), hart)
        self.assertTrue(any("Zeichen" in h for h in hart), hart)

    def test_thumbnail_felder(self):
        s = copy.deepcopy(GUT)
        s["thumbnail"] = {"banderole": "GANZ GROSSE WENDE", "zeile1": "EIN", "zeile2": "", "farbe": "lila"}
        hart, _ = ws.paket_pruefen(s)
        self.assertTrue(any("Banderole" in h for h in hart))
        self.assertTrue(any("2 bis 5 Wörter" in h for h in hart))
        self.assertTrue(any("Farbe" in h for h in hart))

    def test_ich_form_zitate_zaehlen_nicht(self):
        s = copy.deepcopy(GUT)
        for a in s["abschnitte"]:
            a["text"] = "Trump schrieb: «Ich will, ich werde, mich kümmert es nicht, mein Wort gilt»."
        s["abschnitte"][-1]["text"] += " Kommentare: Gibt Selenskyj nach, eher ja oder eher nein?"
        s["meinungen"] = []
        hart, _ = ws.paket_pruefen(s)
        self.assertTrue(any("Ich-Form" in h for h in hart), hart)
        self.assertTrue(any("meinungen" in h for h in hart), hart)

    def test_meinung_muss_markiert_und_woertlich_sein(self):
        s = copy.deepcopy(GUT)
        s["meinungen"] = ["Das ist gefährlich.", "Ich halte das für einen Bluff."]
        hart, _ = ws.paket_pruefen(s)
        self.assertTrue(any("nicht wörtlich" in h for h in hart), hart)

    def test_genau_eine_konkrete_kommentarfrage(self):
        s = copy.deepcopy(GUT)
        s["abschnitte"][-1]["text"] = ("Wer gibt zuerst nach? Schreib es in die Kommentare: "
                                       "Gibt Selenskyj nach, eher ja oder eher nein?")
        hart, _ = ws.paket_pruefen(s)
        self.assertTrue(any("Fragezeichen" in h for h in hart), hart)
        s = copy.deepcopy(GUT)
        s["kommentarfrage"] = "Was denkst du?"
        s["abschnitte"][-1]["text"] = "Die Frage bleibt offen. Schreib es in die Kommentare: Was denkst du?"
        hart, _ = ws.paket_pruefen(s)
        self.assertTrue(any("nicht konkret" in h for h in hart), hart)
        s = copy.deepcopy(GUT)
        s["kommentarfrage"] = ""
        hart, _ = ws.paket_pruefen(s)
        self.assertTrue(any("kommentarfrage" in h for h in hart), hart)

    def test_texte_entwurf_traegt_paket(self):
        s = copy.deepcopy(GUT)
        news = [{"sources": ["a", "b"], "articles": [{"title": "X", "url": "https://a/1"}]},
                {"sources": ["a", "b"], "articles": [{"title": "Y", "url": "https://a/2"}]}]
        t = ws.texte_entwurf(s, news, "2026-10-02")
        self.assertEqual(t["kommentarfrage"], GUT["kommentarfrage"])
        self.assertEqual(t["thumbnail"]["farbe"], "konflikt")
        self.assertNotIn("[BILD", t["hook"])


class UploadFortschritt(unittest.TestCase):
    def test_stand(self):
        self.assertEqual(upload_stand("Wird hochgeladen … 45 %"), ("laeuft", 45))
        self.assertEqual(upload_stand("Uploading 99% ... 1 minute left")[0], "laeuft")
        self.assertEqual(upload_stand("Upload abgeschlossen … Verarbeitung beginnt in Kürze")[0], "fertig")
        self.assertEqual(upload_stand("Upload complete ... Processing will begin shortly")[0], "fertig")
        self.assertEqual(upload_stand("Verarbeitung bis HD … 40 %")[0], "fertig")
        self.assertEqual(upload_stand("Überprüfung abgeschlossen. Keine Probleme gefunden.")[0], "fertig")
        self.assertEqual(upload_stand("Hochladen fehlgeschlagen")[0], "fehler")
        self.assertEqual(upload_stand("")[0], "unbekannt")


class SlotPlanung(unittest.TestCase):
    def setUp(self):
        # seit Task fa4b (03.10.): Vorlauf = vorlauf_stunden() (Themenwahl + gemessene Produktion), hier fest 4 h
        self._alt = (wt.NEWS_WELTLAGE_SLOTS, wt.vorlauf_stunden, wt.NEWS_WELTLAGE_MAX_VERSPAETUNG_STUNDEN)
        wt.NEWS_WELTLAGE_SLOTS, wt.vorlauf_stunden, wt.NEWS_WELTLAGE_MAX_VERSPAETUNG_STUNDEN = ["07:00"], lambda *a: 4, 5

    def tearDown(self):
        wt.NEWS_WELTLAGE_SLOTS, wt.vorlauf_stunden, wt.NEWS_WELTLAGE_MAX_VERSPAETUNG_STUNDEN = self._alt

    def test_fenster(self):
        t = wt.slot_zeit("2026-10-02", "07:00")
        self.assertEqual(wt.faellig(t - timedelta(hours=5), {}), [])
        self.assertEqual(wt.faellig(t - timedelta(hours=4), {}), [("2026-10-02", "07:00")])
        self.assertEqual(wt.faellig(t + timedelta(hours=6), {}), [])
        # schon gestartet und Prozess lebt (eigene PID) -> nicht nochmals
        import os
        z = {"2026-10-02_07:00": {"status": "laeuft", "pid": os.getpid()}}
        self.assertEqual(wt.faellig(t - timedelta(hours=3), z), [])
        # fertig -> nie nochmals
        z = {"2026-10-02_07:00": {"status": "veroeffentlicht"}}
        self.assertEqual(wt.faellig(t, z), [])
        # abgestuerzt (PID weg) -> Wiederaufnahme
        z = {"2026-10-02_07:00": {"status": "laeuft", "pid": 999999, "neustarts": 0}}
        self.assertEqual(wt.faellig(t, z), [("2026-10-02", "07:00")])

    def test_ausgeschaltet_startet_nichts(self):
        alt = wt.NEWS_WELTLAGE_TAEGLICH
        wt.NEWS_WELTLAGE_TAEGLICH = False
        try:
            self.assertEqual(wt.pruefen_und_starten(datetime.now().astimezone()), [])
        finally:
            wt.NEWS_WELTLAGE_TAEGLICH = alt


class MetadatenUndThumbnail(unittest.TestCase):
    def test_metadaten_und_thumbnail(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            news = [{"sources": ["A", "B"], "articles": [{"title": "X", "url": "https://a.example/1",
                                                          "source": "A", "published_at": "2026-10-01T05:00"}]},
                    {"sources": ["A", "B"], "articles": [{"title": "Y", "url": "https://b.example/2",
                                                          "source": "B", "published_at": "2026-10-01T06:00"}]}]
            (d / "news.json").write_text(json.dumps(news), encoding="utf-8")
            t = ws.texte_entwurf(copy.deepcopy(GUT), news, "2026-10-02")
            (d / "texte.json").write_text(json.dumps(t, ensure_ascii=False), encoding="utf-8")
            m = wt.metadaten(d)
            self.assertEqual(m["title"], GUT["titel"])
            self.assertTrue(m["description"].startswith("Trump gibt Selenskyj 48 Stunden"))
            self.assertNotIn("Das alles gleich in Weltlage Kompakt", m["description"])
            self.assertIn(GUT["kommentarfrage"], m["description"])
            self.assertIn("https://a.example/1", m["description"])
            self.assertIn("KI-generiert", m["description"])
            self.assertIn("Weltlage Kompakt", m["tags"])
            from video.weltlage_thumbnail import fuer_folge
            from video import latara_foto as lf
            from PIL import Image
            # Foto-Auswahl von Marlons echtem Ordner/Verlauf isolieren (Task 20261002-220950-b2d6):
            # dieser Test soll nicht in die echte Wiederholungs-Historie schreiben.
            alt = (lf.ORDNER, lf.INDEX, lf.VERLAUF)
            lf.ORDNER = d / "kein_foto_ordner"
            lf.INDEX = d / "latara_index.json"
            lf.VERLAUF = d / "latara_verlauf.json"
            try:
                out = fuer_folge(d)
            finally:
                lf.ORDNER, lf.INDEX, lf.VERLAUF = alt
            with Image.open(out) as im:
                self.assertEqual(im.size, (1280, 720))


if __name__ == "__main__":
    unittest.main()
