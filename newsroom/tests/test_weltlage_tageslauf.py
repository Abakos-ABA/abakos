"""Tests fuer den Zweimal-taeglich-Ablauf (tools/weltlage_tageslauf.py, weltlage_entscheid.py, weltlage_themen.py,
weltlage_ueberarbeiten.py, Task fa4b 03.10.2026). Komplett offline: kein Telegram, keine Beta-App, kein LLM, keine GPU,
kein Upload - Zustandsdateien liegen in einem Temp-Ordner.

    .venv\\Scripts\\python -m unittest tests.test_weltlage_tageslauf
"""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))

import weltlage_entscheid as ent  # noqa: E402
import weltlage_tageslauf as tl  # noqa: E402
import weltlage_themen as th  # noqa: E402
import weltlage_ueberarbeiten as ub  # noqa: E402


def _texte():
    return {"titel": "Steht ein Angriff bevor?", "thumbnail": {"banderole": "ALARM", "zeile1": "A", "zeile2": "B",
                                                               "farbe": "konflikt"},
            "szenen": [{"id": "s_coldopen", "text": "Kalt rein."}, {"id": "s5_a1", "text": "Meldung eins mit Text."},
                       {"id": "s5_a2", "text": "Meldung zwei mit Text."}, {"id": "s6_outro", "text": "Tschuess."}]}


class Basis(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._alt = {(m, n): getattr(m, n) for m, n in [(tl, "ZUSTAND"), (tl, "PAUSE"), (ent, "DIR"), (ent, "OFFEN"),
                                                       (ent, "ANTWORTEN"), (ent, "telegram_senden"), (ent, "beta"),
                                                       (ent, "telegram_text"), (ent, "_knoepfe_weg"), (th, "POOL")]}
        tl.ZUSTAND = self.tmp / "tageslauf.json"
        tl.PAUSE = self.tmp / "pause"
        ent.DIR = self.tmp / "entscheid"
        ent.OFFEN = ent.DIR / "offen.json"
        ent.ANTWORTEN = ent.DIR / "antworten"
        self.gesendet = []
        ent.telegram_senden = lambda e, text, dokument=None, bild=None, log=print: self.gesendet.append(
            ("tg", e["phase"], e["runde"], text, dokument)) or [1]
        ent.beta = lambda befehl, daten, log=print: self.gesendet.append(("beta", befehl, daten)) or {"ok": True}
        ent.telegram_text = lambda text, log=print: self.gesendet.append(("text", text))
        ent._knoepfe_weg = lambda e, log=print: None
        th.POOL = self.tmp / "pool.json"

    def tearDown(self):
        for (m, n), v in self._alt.items():
            setattr(m, n, v)


class Zeitplan(Basis):
    def test_produktion_auto_aus_renderzeiten(self):
        d = self.tmp / "data"
        for name, sek in [("weltlage_a", 20446), ("weltlage_b", 8500), ("weltlage_test_x", 99999)]:
            (d / name).mkdir(parents=True)
            (d / name / f"{name}_renderzeiten.json").write_text(json.dumps({"gesamt": sek}), encoding="utf-8")
        h = tl.produktion_stunden(d)
        self.assertAlmostEqual(h, round(20446 / 3600 + tl.NEBENSCHRITTE_STUNDEN, 2))

    def test_produktion_ohne_messung_fallback(self):
        self.assertEqual(tl.produktion_stunden(self.tmp / "leer"), tl.PRODUKTION_FALLBACK_STUNDEN)

    def test_faellig_fenster_und_fortsetzen(self):
        slots = tl.NEWS_WELTLAGE_SLOTS
        tl.NEWS_WELTLAGE_SLOTS = ["11:00", "19:00"]
        try:
            t = tl.slot_zeit("2026-10-03", "11:00")
            self.assertEqual(tl.faellig(t - timedelta(hours=9), {}, vorlauf=8, produktion=6), [])
            self.assertEqual(tl.faellig(t - timedelta(hours=7), {}, vorlauf=8, produktion=6), [("2026-10-03", "11:00")])
            z = {"2026-10-03_11:00": {"status": "angehalten", "pid": None}}
            self.assertEqual(tl.faellig(t - timedelta(hours=1), z, vorlauf=8), [], "angehalten ohne Markierung bleibt")
            z["2026-10-03_11:00"]["auto_fortsetzen"] = True
            self.assertEqual(tl.faellig(t - timedelta(hours=1), z, vorlauf=8), [("2026-10-03", "11:00")])
            z = {"2026-10-03_11:00": {"status": "ersetzt"}}
            self.assertEqual(tl.faellig(t - timedelta(hours=1), z, vorlauf=8), [])
            z = {"2026-10-03_11:00": {"status": "laeuft", "pid": None, "neustarts": tl.MAX_NEUSTARTS}}
            self.assertEqual(tl.faellig(t - timedelta(hours=1), z, vorlauf=8), [], "Neustart-Grenze")
            # Vorfall 02.10. 23:55: vergangener Slot desselben Tages startet nie neu (Produktion passt nicht mehr)
            self.assertEqual(tl.faellig(tl.slot_zeit("2026-10-02", "23:55"), {}, vorlauf=8.2, produktion=6.7)
                             , [], "19:00-Slot um 23:55 nicht mehr neu starten")
            self.assertIn(("2026-10-03", "11:00"),
                          tl.faellig(t + timedelta(hours=1), {"2026-10-03_11:00": {"status": "laeuft", "pid": None}},
                                     vorlauf=8, produktion=6.7),
                             "abgestuerzter Lauf darf im ganzen Fenster weiter")
            # nur vorgemerkt (Vorgabe ohne Status) -> startet normal
            self.assertEqual(tl.faellig(t - timedelta(hours=7), {"2026-10-03_11:00": {"vorgabe": {"titel": "x?"}}},
                                        vorlauf=8, produktion=6.7), [("2026-10-03", "11:00")])
            # 07:00 ist kein Slot mehr
            self.assertEqual(tl.faellig(tl.slot_zeit("2026-10-03", "06:00"), {}, vorlauf=1), [])
        finally:
            tl.NEWS_WELTLAGE_SLOTS = slots


class Rohschnitt0510(Basis):
    """Vorfall 05.10.2026: 0 von 2 Folgen - Rohschnitt nach fester 8-h-Grenze abgeschossen, Zeitplan zu knapp."""

    LOG = ("2026-10-05 04:38:04 $ tools/weltlage_tts.py C:\\x\n"
           "2026-10-05 07:15:44 -> Exit 0\n"
           "2026-10-05 07:15:44 $ tools/weltlage_rohschnitt.py C:\\x --out C:\\x\\y.mp4\n"
           "  s5_01: 6.6 s Ton in 155 s gesynct\n"
           "[out#0] Broken pipe2026-10-05 15:15:45 ABBRUCH in Schritt schnitt: timed out\n")

    def test_schritt_dauern_auch_mitten_in_der_zeile(self):
        d = tl.schritt_dauern(self.LOG)
        self.assertAlmostEqual(d["stimme"], 2 * 3600 + 37 * 60 + 40)
        self.assertAlmostEqual(d["schnitt"], 8 * 3600 + 1)

    def test_schritt_dauern_laufend_zaehlt_als_untergrenze(self):
        log = "\n".join(self.LOG.splitlines()[:4])
        d = tl.schritt_dauern(log, datetime(2026, 10, 5, 9, 15, 44))
        self.assertAlmostEqual(d["schnitt"], 2 * 3600)

    def test_produktion_aus_logs_rechnet_auf_sprechdauer_hoch(self):
        d = self.tmp / "data"
        for name, sprech, log in [("weltlage_20261005_1100", 529, self.LOG),
                                  ("weltlage_20261004_1100", 278, self.LOG.replace("15:15:45", "11:15:44"))]:
            (d / name / "audio").mkdir(parents=True)
            (d / name / "tageslauf.log").write_text(log, encoding="utf-8")
            (d / name / "audio" / "s5.tts.json").write_text(json.dumps({"laenge_s": sprech}), encoding="utf-8")
        h = tl.produktion_stunden(d)
        stimme = 2 * 3600 + 37 * 60 + 40
        rate = max((stimme + 8 * 3600 + 1) / 529, (stimme + 4 * 3600) / 278)   # langsamste Folge zaehlt
        self.assertAlmostEqual(h, round(rate * 529 / 3600 + tl.NEBEN_OHNE_STIMME_STUNDEN, 2))
        self.assertGreater(h, 10, "8-Min.-Folge mit Lipsync-HD braucht mehr als 10 h - nicht mehr 5,9 h")

    def test_fremde_laeufe_nur_echte_aufrufe(self):
        o = Path(r"C:\n\data\weltlage_20261005_1900")
        pr = [{"pid": 1, "ppid": 9, "cmd": r"C:\n\.venv-lipsync\Scripts\python.exe tools/weltlage_rohschnitt.py "
                                            r"C:\n\data\weltlage_20261005_1900 --out C:\n\data\weltlage_20261005_1900\a.mp4"},
              {"pid": 2, "ppid": 1, "cmd": r'"C:\Py\python.exe" tools/weltlage_rohschnitt.py '
                                           r"C:\n\data\weltlage_20261005_1900 --out x"},
              {"pid": 3, "ppid": 8, "cmd": r"python.exe tools/weltlage_rohschnitt.py C:\n\data\weltlage_20261005_1100 --out y"},
              {"pid": 4, "ppid": 7, "cmd": r"bash -c grep weltlage_rohschnitt.py C:\n\data\weltlage_20261005_1900"},
              {"pid": 5, "ppid": 7, "cmd": r"python.exe tools/weltlage_rohschnitt.py C:\n\data\weltlage_20261005_19001 x"}]
        self.assertEqual(tl.fremde_laeufe(pr, "weltlage_rohschnitt.py", o, True), [1], "venv-Starter, ohne grep")
        self.assertEqual(tl.fremde_laeufe(pr, "weltlage_rohschnitt.py", o, False), [3, 5])

    def test_run_beendet_nur_bei_stillstand(self):
        alt = tl.POLL_S
        tl.POLL_S = 0.2
        try:
            log = tl._Log(self.tmp / "t.log")
            rc = tl._run(["-c", "import time; time.sleep(60)"], log, timeout_h=1, ordner=self.tmp, still_min=0.02)
            self.assertEqual(rc, tl.STILLSTAND_RC)
            rc = tl._run(["-c", "import time\nfor i in range(8):\n print(i, flush=True); time.sleep(0.4)"], log,
                         timeout_h=1, ordner=self.tmp, still_min=0.02)
            self.assertEqual(rc, 0, "Ausgabe alle 0,4 s = lebt, trotz 3,2 s Laufzeit > 1,2 s Stillstandsgrenze")
        finally:
            tl.POLL_S = alt

    def test_verspaetung_pro_lauf(self):
        tl._eintrag("2026-10-05_19:00", max_verspaetung_h=8)
        self.assertEqual(tl._laden()["2026-10-05_19:00"]["max_verspaetung_h"], 8)


class Entscheid(Basis):
    def test_text_auswerten(self):
        self.assertEqual(ent.text_auswerten("B, mehr zu China", "thema"), ("B", "mehr zu China"))
        self.assertEqual(ent.text_auswerten("weltlage c", "thema"), ("C", None))
        self.assertIsNone(ent.text_auswerten("Aber nein", "thema"))
        self.assertEqual(ent.text_auswerten("Freigeben", "freigabe"), ("freigeben", None))
        self.assertEqual(ent.text_auswerten("Stopp", "freigabe"), ("stopp", None))
        self.assertEqual(ent.text_auswerten("Feedback: Titel kuerzer", "freigabe"), ("feedback", "Titel kuerzer"))

    def test_frage_antwort_und_alte_runde(self):
        frist = datetime.now().astimezone() + timedelta(minutes=5)
        e = ent.fragen("2026-10-03_11:00", "thema", "Text", {"A": "A", "B": "B", "C": "C"}, frist, empfehlung="A")
        self.assertEqual(json.loads(ent.OFFEN.read_text(encoding="utf-8"))[0]["phase"], "thema")
        ok, _ = ent.antwort(e["id"], "B", runde=e["runde"] + 5)
        self.assertFalse(ok, "alte/fremde Runde zaehlt nicht")
        ok, _ = ent.antwort(e["id"], "B", "mehr Karten", quelle="test", runde=e["runde"])
        self.assertTrue(ok)
        self.assertEqual(ent.warten(e["id"], poll_s=0.01)["wahl"], "B")
        self.assertEqual(json.loads(ent.OFFEN.read_text(encoding="utf-8")), [])

    def test_frist_ohne_antwort(self):
        frist = datetime.now().astimezone() + timedelta(seconds=0.2)
        e = ent.fragen("k", "freigabe", "Text", {"freigeben": "Freigeben", "stopp": "Stopp"}, frist)
        self.assertIsNone(ent.warten(e["id"], poll_s=0.05))
        self.assertEqual(ent.laden(e["id"])["status"], "abgelaufen")

    def test_feedback_knopf_dann_text(self):
        frist = datetime.now().astimezone() + timedelta(minutes=5)
        e = ent.fragen("k2", "freigabe", "T", {"freigeben": "F", "feedback": "Fb", "stopp": "S"}, frist)
        ok, text = ent.antwort(e["id"], "feedback", None, runde=e["runde"])
        self.assertTrue(ok and "Was soll anders sein" in text)
        self.assertEqual(ent.laden(e["id"])["status"], "feedback_erwartet")
        ent.text_antwort("Titel kuerzer bitte", e["id"], als_antwort=True)
        a = ent.warten(e["id"], poll_s=0.01)
        self.assertEqual((a["wahl"], a["feedback"]), ("feedback", "Titel kuerzer bitte"))


class Themenwahl(Basis):
    def _storylines(self, ordner: Path):
        artikel = [{"nr": i, "title": f"T{i}", "url": f"https://x/{i}", "source": f"Q{i % 3}"} for i in range(1, 10)]
        d = {"storylines": [{"buchstabe": b, "titel": f"{b}?", "inhalt": "i", "meldungen": [[1 + k, 2 + k], [3 + k]],
                             "gruene_quellen": ["DVIDS"], "pool_id": None} for k, b in enumerate("ABC")],
             "empfehlung": "B", "grund": "g", "artikel": artikel}
        ordner.mkdir(parents=True, exist_ok=True)
        (ordner / "storylines.json").write_text(json.dumps(d), encoding="utf-8")
        return d

    def test_ohne_antwort_empfehlung(self):
        ordner = self.tmp / "folge"
        self._storylines(ordner)
        log = tl._Log(self.tmp / "log.txt")
        wahl = tl.thema_waehlen("2026-10-03_19:00", "19:00", ordner, log, minuten=0.003)
        self.assertEqual(wahl["wahl"], "B")
        self.assertIn("automatisch", wahl["quelle"])
        self.assertTrue((ordner / "news.json").exists() and (ordner / "vorgabe.txt").exists())
        self.assertTrue(any(g[0] == "tg" and g[1] == "thema" for g in self.gesendet), "Telegram-Rueckfrage")
        self.assertTrue(any(g[0] == "beta" and g[1] == "stellen" for g in self.gesendet), "Beta-App-Rueckfrage")

    def test_antwort_mit_hinweis_nach_neustart(self):
        ordner = self.tmp / "folge2"
        self._storylines(ordner)
        key = "2026-10-03_11:00"
        e = ent.fragen(key, "thema", "T", {"A": "A", "B": "B", "C": "C"},
                       datetime.now().astimezone() + timedelta(minutes=30), empfehlung="B")
        ent.antwort(e["id"], "C", "mehr zur Rolle Chinas", runde=e["runde"])   # Antwort kam waehrend des Neustarts
        n = len(self.gesendet)
        wahl = tl.thema_waehlen(key, "11:00", ordner, tl._Log(self.tmp / "l.txt"), minuten=30)
        self.assertEqual(wahl["wahl"], "C")
        self.assertFalse([g for g in self.gesendet[n:] if g[0] == "tg"], "keine zweite Rueckfrage nach Neustart")
        self.assertIn("mehr zur Rolle Chinas", (ordner / "vorgabe.txt").read_text(encoding="utf-8"))

    def test_vorab_gewaehlt_ohne_rueckfrage(self):
        ordner = self.tmp / "folge3"
        self._storylines(ordner)
        tl._eintrag("2026-10-04_11:00", vorgabe={"titel": "A?", "inhalt": "x"})
        wahl = tl.thema_waehlen("2026-10-04_11:00", "11:00", ordner, tl._Log(self.tmp / "l.txt"), minuten=30)
        self.assertEqual(wahl["wahl"], "A")
        self.assertFalse([g for g in self.gesendet if g[0] == "tg"])

    def test_pool_entfernt_nach_wahl(self):
        p = th.pool_add("Sudan?", "El-Obeid", tage=2)
        ordner = self.tmp / "folge4"
        d = self._storylines(ordner)
        d["storylines"][1]["pool_id"] = p["id"]
        (ordner / "storylines.json").write_text(json.dumps(d), encoding="utf-8")
        tl.thema_waehlen("2026-10-05_11:00", "11:00", ordner, tl._Log(self.tmp / "l.txt"), minuten=0.003)
        self.assertEqual(th.pool_laden(), [])


class Ueberarbeiten(Basis):
    def test_nur_geaenderte_szene_und_master_weg(self):
        ordner = self.tmp / "f"
        ordner.mkdir()
        (ordner / "texte.json").write_text(json.dumps(_texte()), encoding="utf-8")
        master = ordner / "m.mp4"
        master.write_bytes(b"x")
        modell = lambda p: {"szenen": {"s5_a2": "Meldung zwei kuerzer.", "s5_a1": "Meldung eins mit Text."},
                            "titel": None, "thumbnail": None, "zusammenfassung": "gekuerzt"}
        res = ub.ueberarbeiten(ordner, "Meldung zwei kuerzer", 1, master, modell=modell)
        self.assertEqual(res["szenen"], ["s5_a2"])
        self.assertTrue(res["neu_rendern"])
        self.assertFalse(master.exists())
        self.assertTrue((ordner / "m.vor_feedback_1.mp4").exists())
        self.assertTrue((ordner / "texte.vor_feedback_1.json").exists())

    def test_feste_szene_abgelehnt(self):
        fehler = ub.pruefen({"szenen": {"s6_outro": "neu"}}, _texte())
        self.assertTrue(fehler)

    def test_nur_titel_kein_rendern(self):
        ordner = self.tmp / "g"
        ordner.mkdir()
        (ordner / "texte.json").write_text(json.dumps(_texte()), encoding="utf-8")
        master = ordner / "m.mp4"
        master.write_bytes(b"x")
        res = ub.ueberarbeiten(ordner, "anderer Titel", 1, master,
                               modell=lambda p: {"szenen": {}, "titel": "Neuer Titel?", "zusammenfassung": "t"})
        self.assertFalse(res["neu_rendern"])
        self.assertTrue(master.exists())
        self.assertEqual(json.loads((ordner / "texte.json").read_text(encoding="utf-8"))["titel"], "Neuer Titel?")


class Freigabe(Basis):
    def _folge(self):
        ordner = self.tmp / "folge"
        ordner.mkdir()
        (ordner / "metadaten.json").write_text(json.dumps({"title": "Titel?"}), encoding="utf-8")
        master = ordner / "m.mp4"
        master.write_bytes(b"x")
        self._tf = tl.telegram_fassung
        tl.telegram_fassung = lambda datei, ordner, log: datei
        self.addCleanup(lambda: setattr(tl, "telegram_fassung", self._tf))
        return ordner, master

    def test_keine_reaktion_automatisch(self):
        ordner, master = self._folge()
        r = tl.freigabe_einholen("k", "11:00", ordner, master, tl._Log(self.tmp / "l"), 0.003, True, lambda s: None)
        self.assertEqual(r, "automatisch")
        tg = [g for g in self.gesendet if g[0] == "tg"]
        self.assertEqual(tg[0][4], master, "Video als Dokument")
        self.assertIn("TROCKENLAUF", tg[0][3])

    def test_stopp(self):
        ordner, master = self._folge()
        e = ent.fragen("k", "freigabe", "T", {"freigeben": "F", "stopp": "S"},
                       datetime.now().astimezone() + timedelta(minutes=5))
        ent.antwort(e["id"], "stopp", runde=e["runde"])
        with self.assertRaises(tl.Gestoppt):
            tl.freigabe_einholen("k", "11:00", ordner, master, tl._Log(self.tmp / "l"), 5, True, lambda s: None)

    def test_feedback_rendert_und_fragt_neu(self):
        ordner, master = self._folge()
        (ordner / "texte.json").write_text(json.dumps(_texte()), encoding="utf-8")
        key = "kf"
        e = ent.fragen(key, "freigabe", "T", {"freigeben": "F", "feedback": "Fb", "stopp": "S"},
                       datetime.now().astimezone() + timedelta(minutes=5))
        ent.antwort(e["id"], "feedback", "Meldung zwei kuerzer", runde=e["runde"])
        produziert = []
        alt = ub.vorschlag
        ub.vorschlag = lambda texte, fb, modell=None, max_wachstum_prozent=None: {"szenen": {"s5_a2": "kurz."}, "zusammenfassung": "z"}
        self.addCleanup(lambda: setattr(ub, "vorschlag", alt))

        def produktion(schritte):
            produziert.append(schritte)
            master.write_bytes(b"neu")     # Schnitt baut den Master neu

        r = tl.freigabe_einholen(key, "11:00", ordner, master, tl._Log(self.tmp / "l"), 0.003, True, produktion)
        self.assertEqual(r, "automatisch", "zweite Runde ohne Reaktion -> veroeffentlichen")
        self.assertEqual(produziert, [tl.PRODUKTION])
        self.assertEqual(tl._laden()[key]["feedback_runden"], 1)
        runden = [g[2] for g in self.gesendet if g[0] == "tg" and g[1] == "freigabe"]
        self.assertEqual(runden, [1, 2], "nach Feedback neue Runde mit neuem Video verschickt")


class Puenktlichkeit(Basis):
    """07.10.2026 (Task 3432): Freigabe vor dem Slot, Taktung, Vorrang regulaerer Slots, Frist vor dem Rohschnitt,
    True-Peak-Regelung im Master."""

    def test_freigabe_endet_vor_dem_slot(self):
        t = tl.slot_zeit("2026-10-08", "11:00")
        self.assertEqual(tl.freigabe_beginn(t, 60, 45), t - timedelta(minutes=105))
        self.assertEqual(tl.freigabe_beginn(t, 60, 0), t - timedelta(minutes=60))

    def test_taktung_legt_rohschnitte_hintereinander(self):
        r = tl.taktung_rechnen(["11:00", "19:00"], 9.75, 4.3, 2.5)
        self.assertTrue(r["machbar"])
        # 19:00 muss bis 16:30 fertig sein -> Beginn 06:45; 11:00 muss davor fertig sein -> Beginn 21:00 am Vortag
        self.assertEqual(r["schnitt_ab"], {"11:00": "21:00", "19:00": "06:45"})
        self.assertAlmostEqual(r["vorlauf_h"]["11:00"], 14 + 4.3)
        self.assertAlmostEqual(r["vorlauf_h"]["19:00"], 12.25 + 4.3)
        kurz = tl.taktung_rechnen(["11:00", "19:00"], 3, 4.3, 2.5)
        self.assertEqual(kurz["vorlauf_h"], {"11:00": 9.8, "19:00": 9.8}, "kurze Rohschnitte: keine Verschiebung")
        self.assertFalse(tl.taktung_rechnen(["11:00", "19:00"], 13, 4.3, 2.5)["machbar"], "2 x 13 h > 24 h")

    def test_vorrang_regulaerer_slots(self):
        slots = ["11:00", "19:00"]
        jetzt = tl.slot_zeit("2026-10-07", "12:00")
        self.assertTrue(tl.regulaer("2026-10-07_11:00", slots))
        self.assertFalse(tl.regulaer("2026-10-07_03:00", slots))
        self.assertIsNone(tl.vorrang_fuer("2026-10-07_19:00", {}, jetzt, 9, 17, slots), "regulaer wartet nie")
        z = {"2026-10-07_19:00": {"status": "laeuft", "schritt": "stimme"}}
        self.assertIn("produziert gerade", tl.vorrang_fuer("2026-10-07_03:00", z, jetzt, 9, 17, slots))
        # nichts laeuft, naechster regulaerer Lauf (08.10. 11:00) beginnt 18 h vorher = 17:00, Karte ab 20:00
        z = {"2026-10-07_19:00": {"status": "veroeffentlicht"}}
        self.assertIsNone(tl.vorrang_fuer("2026-10-07_14:00", z, jetzt, 7, 18, slots, vor_schnitt_h=3), "12+7 <= 20")
        self.assertIn("braucht die Karte", tl.vorrang_fuer("2026-10-07_14:00", z, jetzt, 9, 18, slots, vor_schnitt_h=3))

    def test_reine_montage_wartet_nicht_auf_regulaere(self):
        # Vorfall 08.10.2026: fertig gerenderte Folge als neuer Slot, regulaere 11:00/19:00 produzieren gerade
        from unittest import mock
        z = {"2026-10-08_11:00": {"status": "laeuft", "schritt": "schnitt"},
             "2026-10-08_19:00": {"status": "laeuft", "schritt": "thema"}}
        jetzt = datetime.now().astimezone()
        slot_t = jetzt + timedelta(hours=4)
        with mock.patch.object(tl, "_laden", return_value=z), mock.patch.object(tl, "taktung", return_value={}),                 mock.patch.object(tl, "vorlauf_stunden", return_value=17),                 mock.patch.object(tl, "_prozesse", return_value=[]), mock.patch.object(tl, "_eintrag"),                 mock.patch.object(tl.time, "sleep", side_effect=AssertionError("wartet")):
            with mock.patch.dict(tl.os.environ, {"NEWS_WELTLAGE_SKIP_SZENEN": "coldopen,s5"}):
                tl.schnitt_vorbereiten("2026-10-08_06:40", Path("x"), slot_t, lambda *_: None)
            with mock.patch.dict(tl.os.environ, {"NEWS_WELTLAGE_SKIP_SZENEN": ""}),                     mock.patch.object(tl, "schnitt_stunden", return_value=0.5), self.assertRaises(AssertionError):
                tl.schnitt_vorbereiten("2026-10-08_06:40", Path("x"), slot_t, lambda *_: None)

    def test_frist_vor_dem_rohschnitt(self):
        slot = tl.slot_zeit("2026-10-07", "03:00")
        # Vorfall 07.10.: um 14:05 einen ~9,8-h-Rohschnitt fuer den 03:00-Slot (Frist 13:00) beginnen = sinnlos
        self.assertIn("zu spät", "zu spät: " + (tl.schnitt_frist_problem(
            tl.slot_zeit("2026-10-07", "14:05"), slot, 10, 9.8) or ""))
        self.assertIsNotNone(tl.schnitt_frist_problem(tl.slot_zeit("2026-10-07", "14:05"), slot, 10, 9.8))
        self.assertIsNone(tl.schnitt_frist_problem(tl.slot_zeit("2026-10-07", "05:43"), slot, 10, 0.5),
                          "Montage aus dem Cache haette noch gereicht")

    def test_nur_pegel_fehler(self):
        self.assertTrue(tl.nur_pegel_fehler({"fehler": ["True Peak -0.9 dBTP ueber -1.5"]}))
        self.assertTrue(tl.nur_pegel_fehler({"fehler": ["Lautheit -12.7 LUFS, Ziel -14.0 +-1"]}))
        self.assertFalse(tl.nur_pegel_fehler({"fehler": ["True Peak -0.9 dBTP ueber -1.5", "Sprung 4.8 dB"]}))
        self.assertFalse(tl.nur_pegel_fehler({"fehler": []}))

    def test_true_peak_wird_nachgeregelt(self):
        import weltlage_rohschnitt as rs
        decke = rs.MASTER_TP - rs.TP_CODEC_RESERVE_DB
        self.assertIsNone(rs.naechste_tp_decke(decke, -1.6), "unter -1,5 dBTP: passt")
        self.assertIsNone(rs.naechste_tp_decke(decke, rs.MASTER_TP), "genau auf der Grenze: passt")
        # Vorfall 07.10.: -0,9 dBTP nach AAC -> Decke um Ueberschuss (0,6) + Sicherheit (0,2) tiefer
        self.assertAlmostEqual(rs.naechste_tp_decke(decke, -0.9), round(decke - 0.6 - rs.TP_SICHERHEIT_DB, 2))
        self.assertEqual(rs.naechste_tp_decke(-3.9, 0.5), rs.TP_MIN_DECKE, "nie unter die Mindestdecke")
        self.assertIsNone(rs.naechste_tp_decke(rs.TP_MIN_DECKE, -1.0), "an der Mindestdecke: nicht weiter")


if __name__ == "__main__":
    unittest.main()
