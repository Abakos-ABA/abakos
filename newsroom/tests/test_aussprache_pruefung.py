"""Offline-Tests (nur Text, kein Ton) fuer den Aussprache-Ausbau vom 18.10.2026 (Task ad90): Buchstabieren,
Betonungs-Grossschrift, Datum/Uhrzeit/Jahr/Zahlen, Sonderzeichen, Lexikon-Filter, Pruefschritt, Satzmelodie-Plan.

    .venv\\Scripts\\python.exe -m unittest tests.test_aussprache_pruefung -v
    .venv-tts\\Scripts\\python.exe -m unittest tests.test_aussprache_pruefung.ProsodieTest -v
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
from tts import aussprache_pruefung as ap  # noqa: E402
from tts.normalize_de import normalize_for_tts  # noqa: E402

LEER = {"eintraege": {}}


def norm(text: str) -> str:
    with mock.patch("tts.aussprache_lexikon.laden", return_value=LEER):
        return normalize_for_tts(text)


class AbkuerzungenTest(unittest.TestCase):
    def test_marlons_beispiele_buchstabiert(self):
        out = norm("Das FBI, die CIA, die USA, die EU, die UN, die WHO, die CDU und die AfD.")
        for soll in ("Eff Beh Ih", "Zeh Ih Ah", "Uh Ess Ah", "Eh Uh", "Uh Enn", "Weh Hah Oh", "Zeh Deh Uh",
                     "Ah Eff Deh"):
            self.assertIn(soll, out)

    def test_als_wort_gesprochene_bleiben(self):
        out = norm("Die NATO und die UNO, die NASA und die OPEC.")
        for soll in ("NATO", "UNO", "NASA", "OPEC"):
            self.assertIn(soll, out)

    def test_zusammensetzung_und_plural(self):
        self.assertIn("Uh-Ess-Angriffe", norm("US-Angriffe"))
        self.assertIn("Enn Geh Ohs", norm("die NGOs"))
        self.assertIn("Uh Ess", norm("die U.S. Army"))

    def test_betonung_in_grossschrift_wird_wort(self):
        out = norm("Die WAHL ist JETZT, NICHTS ist klar.")
        self.assertIn("Wahl", out)
        self.assertIn("Jetzt", out)
        self.assertIn("Nichts", out)
        self.assertNotIn("Weh Ah", out)

    def test_unbekanntes_kuerzel_ohne_vokal_buchstabiert(self):
        self.assertIn("Kah Kah Emm", norm("Laut KKM steigt der Preis."))


class ZahlenTest(unittest.TestCase):
    def test_datum(self):
        self.assertIn("achtzehnten Oktober zweitausendsechsundzwanzig", norm("am 18.10.2026"))
        self.assertIn("dritten Oktober", norm("am 3.10. war Feiertag"))

    def test_uhrzeit(self):
        self.assertIn("vierzehn Uhr dreißig", norm("um 14:30 Uhr"))
        self.assertIn("neun Uhr", norm("um 9:00 Uhr"))
        self.assertIn("ein Uhr dreißig", norm("um 1:30 Uhr"))

    def test_jahreszahl_wie_ein_sprecher(self):
        self.assertIn("neunzehnhundertvierundneunzig", norm("seit 1994"))
        self.assertIn("zweitausendsechsundzwanzig", norm("im Jahr 2026"))

    def test_prozent_vorzeichen_spanne(self):
        out = norm("Minus -3,5 % und +2 %, von 2010-2015.")
        self.assertIn("minus drei Komma fünf Prozent", out)
        self.assertIn("plus zwei Prozent", out)
        self.assertIn("zweitausendzehn bis zweitausendfünfzehn", out)

    def test_eins_vor_nomen(self):
        self.assertIn("eine Milliarde", norm("1 Milliarde Euro"))
        self.assertIn("ein Prozent", norm("nur 1 Prozent"))

    def test_ordinal_nach_artikel(self):
        self.assertIn("der zweite Weltkrieg", norm("der 2. Weltkrieg"))
        self.assertIn("am dritten Oktober", norm("am 3. Oktober"))

    def test_tausender_und_waehrung_unveraendert(self):
        out = norm("800.000 Menschen, 4,2 Mrd. €")
        self.assertIn("achthunderttausend", out)
        self.assertIn("vier Komma zwei Milliarden Euro", out)


class ZeichenTest(unittest.TestCase):
    def test_zeichen(self):
        self.assertIn("Paragraf zweihundertachtzehn", norm("§ 218"))
        self.assertIn("fünf Grad Celsius", norm("5 °C"))
        self.assertIn("zehn Quadratkilometer", norm("10 km²"))
        self.assertIn("Procter und Gamble", norm("Procter & Gamble"))

    def test_fremdzeichen_ohne_lexikon(self):
        out = norm("Sébastien, Nicușor und Łódź")
        self.assertIn("Sebastien", out)
        self.assertIn("Nicuschor", out)
        self.assertIn("Lodz", out)

    def test_umlaute_bleiben(self):
        self.assertEqual(norm("Zölle für Österreich"), "Zölle für Österreich")


class LexikonFilterTest(unittest.TestCase):
    def test_buchstabier_kuerzel_wird_nicht_gelernt(self):
        self.assertTrue(al.ist_buchstabier_kuerzel("CNN", "Si En En"))
        self.assertTrue(al.ist_buchstabier_kuerzel("US-Wahlen", "U-Es-Wahlen"))
        self.assertFalse(al.ist_buchstabier_kuerzel("AAA", "Tripel Ä"))
        self.assertFalse(al.ist_buchstabier_kuerzel("Trump", "Tramp"))

    def test_echtes_lexikon_ohne_englische_buchstabierung(self):
        e = al.laden()["eintraege"]
        for k in ("CIA", "BBC", "CNN", "CNBC", "AFP", "RTL", "G7"):
            self.assertNotIn(k, e, f"{k} gehoert in die Regel, nicht ins Lexikon")
        for k in ("Trump", "Selenskyj", "Biden", "Washington", "Erdoğan"):
            self.assertIn(k, e)

    def test_lerne_verwirft_buchstabier_vorschlag(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "texte.json").write_text(json.dumps({"titel": "t", "szenen": [
                {"id": "s1", "text": "Laut CNN sagte Burnham etwas."}]}), encoding="utf-8")
            antwort = {"vorschlaege": [{"name": "CNN", "sprich": "Si En En"}, {"name": "Burnham", "sprich": "Börnem"}]}
            with mock.patch.object(al, "laden", return_value=al.leer()), mock.patch.object(al, "sichern"):
                e = al.lerne_aus_folge(Path(tmp), frage_modell=lambda _p: antwort, log=lambda *_: None)
        self.assertEqual(e["neu"], ["Burnham"])


class PruefschrittTest(unittest.TestCase):
    def setUp(self):
        for p in (mock.patch("tts.aussprache_lexikon.laden", return_value=LEER),
                  mock.patch.object(ap, "_lexikon_laden", return_value=LEER),
                  mock.patch.object(ap, "_haeufig", return_value=set())):
            p.start()
            self.addCleanup(p.stop)

    def test_unbekannte_abkuerzung_wird_gemeldet_und_aufgeloest(self):
        e = ap.pruefe("Laut XKQ steigt der Preis.")
        m = [x for x in e["meldungen"] if x["art"] == "abkuerzung_unbekannt"]
        self.assertEqual([x["wort"] for x in m], ["XKQ"])
        self.assertTrue(m[0]["aufgeloest"])
        self.assertIn("buchstabiert", m[0]["hinweis"])

    def test_bekannte_abkuerzung_still(self):
        e = ap.pruefe("Das FBI und die NATO ermitteln.")
        self.assertEqual(e["meldungen"], [])
        self.assertTrue(e["ok"])

    def test_englischer_name_ohne_eintrag_offen(self):
        e = ap.pruefe("Gouverneur Whatley sprach in Juneau.")
        woerter = {x["wort"] for x in e["meldungen"] if x["art"] == "englisch_verdacht"}
        self.assertIn("Whatley", woerter)
        self.assertFalse(e["ok"])

    def test_deutsche_zusammensetzung_kein_verdacht(self):
        e = ap.pruefe("Der Strafgerichtshof prüft die Untersuchungshaft und den Haushaltsplan.")
        self.assertEqual([x for x in e["meldungen"] if x["art"] == "englisch_verdacht"], [])

    def test_fremdzeichen_gemeldet_und_aufgeloest(self):
        e = ap.pruefe("Premier Feijóo sprach.")
        m = [x for x in e["meldungen"] if x["art"] == "fremdzeichen"]
        self.assertEqual(m[0]["wort"], "Feijóo")
        self.assertTrue(m[0]["aufgeloest"])

    def test_kein_rest_nach_normalisierung(self):
        e = ap.pruefe("Am 18.10.2026 um 14:30 Uhr stiegen die Preise um 3,5 % auf 1.200 Euro, seit 1994.")
        self.assertEqual([x for x in e["meldungen"] if x["art"] == "rest"], [])

    def test_folge_schreibt_bericht(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "texte.json").write_text(json.dumps({"titel": "t", "szenen": [
                {"id": "s1", "text": "Laut XKQ sprach Whatley."}]}), encoding="utf-8")
            e = ap.pruefe_folge(Path(tmp), log=lambda *_: None)
            self.assertTrue((Path(tmp) / "aussprache_pruefung.json").exists())
        self.assertEqual({x["szene"] for x in e["meldungen"]}, {"s1"})
        self.assertEqual([x["wort"] for x in e["offen"]], ["Whatley"])


class ProsodieTest(unittest.TestCase):
    """Satzmelodie-Plan (tts/chatterbox_worker.prosodie_plan). Der Worker braucht torch und laeuft nur in .venv-tts:
    der Plan wird dort per Unterprozess (ohne Fenster, ohne Modell, ohne Ton) berechnet."""

    SAETZE = ["Das ist ein normaler Aussagesatz mit einigen Woertern darin.", "Was steckt dahinter?", "Ende."]

    def _plan(self):
        import subprocess
        py = ROOT / ".venv-tts" / "Scripts" / "python.exe"
        if not py.exists():
            self.skipTest(".venv-tts fehlt")
        code = ("import sys, json, numpy as np; sys.path.insert(0, r'%s'); import chatterbox_worker as c; "
                "print(json.dumps(c.prosodie_plan(json.loads(sys.argv[1]), 0.5, np.random.default_rng(3))))"
                % (ROOT / "tts"))
        r = subprocess.run([str(py), "-c", code, json.dumps(self.SAETZE)], capture_output=True, text=True,
                           timeout=240, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        return json.loads(r.stdout.strip().splitlines()[-1])

    def test_frage_mehr_ausdruck_langsamer_und_schluss_ohne_pause(self):
        plan = self._plan()
        self.assertGreater(plan[1]["ex"], plan[0]["ex"])
        self.assertGreater(plan[1]["pause_s"], plan[0]["pause_s"] - 0.05)
        self.assertLess(plan[1]["tempo"], 1.0)
        self.assertEqual(plan[-1]["pause_s"], 0.0)
        for p in plan:
            self.assertTrue(0.3 <= p["ex"] <= 0.9)
            self.assertTrue(0.9 <= p["tempo"] <= 1.1)


class StimmProfilTest(unittest.TestCase):
    """Profil G (Kerstin lebendig, 18.10.2026) ist aktiv; C-Aufnahmen derselben Figur bleiben gueltig."""

    def test_aktives_profil_g_mit_c_kompatibel(self):
        from tts import stimme_profil as sp
        d = sp.alle()
        self.assertEqual(d["aktiv"], "G")
        g, c = d["profile"]["G"], d["profile"]["C"]
        self.assertEqual(g["tempo"], c["tempo"])
        self.assertEqual((g["exaggeration"], g["cfg"]), (c["exaggeration"], c["cfg"]))
        self.assertEqual(sp.figur_ref_hashes("G"), {g["ref_sha256"], c["ref_sha256"]})
        self.assertEqual(sp.figur_ref_hashes("C"), {c["ref_sha256"]})

    def test_referenz_datei_passt_zum_hash(self):
        import hashlib
        from tts import stimme_profil as sp
        p = sp.profil("G")
        self.assertEqual(hashlib.sha256(p["ref_pfad"].read_bytes()).hexdigest(), p["ref_sha256"])

    def test_pruefe_stimme_akzeptiert_c_und_g_lehnt_fremde_ab(self):
        import hashlib
        import wave
        sys.path.insert(0, str(ROOT / "tools"))
        import weltlage_tts as wt
        from tts import stimme_profil as sp
        d = sp.alle()["profile"]
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "s1.wav"
            with wave.open(str(wav), "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(b"\0\0" * 2400)
            for profil, ok in (("G", True), ("C", True), ("A", False)):
                meta = {"engine": "chatterbox", "ref_sha256": d[profil]["ref_sha256"], "tempo": d[profil]["tempo"],
                        "wav_sha256": hashlib.sha256(wav.read_bytes()).hexdigest()}
                wav.with_suffix(".tts.json").write_text(json.dumps(meta), encoding="utf-8")
                fehler = wt.pruefe_stimme(wav)
                self.assertEqual(fehler is None, ok, f"Profil {profil}: {fehler}")


if __name__ == "__main__":
    unittest.main()
