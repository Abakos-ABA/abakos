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
            self.assertEqual(tl.faellig(t - timedelta(hours=9), {}, vorlauf=8), [])
            self.assertEqual(tl.faellig(t - timedelta(hours=7), {}, vorlauf=8), [("2026-10-03", "11:00")])
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
        ub.vorschlag = lambda texte, fb, modell=None: {"szenen": {"s5_a2": "kurz."}, "zusammenfassung": "z"}
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


if __name__ == "__main__":
    unittest.main()
