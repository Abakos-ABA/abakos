"""Vertonung: Dauerprozess (Modell einmal laden) und parallele Spuren (Folge 30.10.2026: 45 Modell-Ladevorgaenge, alle
Szenen nacheinander = 55 von 84 Minuten). Komplett offline: ein kleiner Python-Ersatz fuer den GPU-Worker, keine GPU,
kein Audio, kein Modell.

    .venv\\Scripts\\python -m unittest tests.test_tts_spuren
"""
import contextlib
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from tts import gpu_spur  # noqa: E402
from tts import tts_client as tc  # noqa: E402

# Spricht das Protokoll von tts/chatterbox_worker.py --server: "@@FERTIG bereit" nach dem Laden, je Auftrag (JSON-Liste
# auf stdin) eine Ausgabedatei und "@@FERTIG <rc>"; ein Auftrag "absturz" beendet den Prozess wie ein Treiberabsturz.
FAKE_WORKER = r'''
import json, os, sys
print("model loaded on cuda in 0s", flush=True)
print("@@FERTIG bereit", flush=True)
n = 0
for zeile in sys.stdin:
    zeile = zeile.strip()
    if zeile == "quit":
        break
    args = json.loads(zeile)
    n += 1
    if "--absturz" in args:
        os._exit(3)
    if "--fehler" in args:
        print("Error: kaputt", flush=True)
        print("@@FERTIG 1", flush=True)
        continue
    if "--haenger" in args:
        import time
        time.sleep(60)                 # haengt wie ein Worker, der in CUDA stecken bleibt (04.11.2026: 20'038 s)
        print("@@FERTIG 0", flush=True)
        continue
    out = args[args.index("--out") + 1]
    open(out, "w").write(str(os.getpid()) + ":" + str(n))
    print("chunk 1/1: 1.0s audio in 0.1s", flush=True)
    print("@@FERTIG 0", flush=True)
'''


class DauerprozessTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "worker.py").write_text(FAKE_WORKER, encoding="utf-8")
        self.sv = tc._ChatterboxServer(sys.executable, self.tmp / "worker.py", str(self.tmp), "test")

    def tearDown(self):
        self.sv.schliessen()

    def test_mehrere_auftraege_ein_prozess(self):
        a, b = self.tmp / "a.txt", self.tmp / "b.txt"
        self.assertEqual(self.sv.lauf(["--out", str(a)]).returncode, 0)
        self.assertEqual(self.sv.lauf(["--out", str(b)]).returncode, 0)
        pid_a, n_a = a.read_text().split(":")
        pid_b, n_b = b.read_text().split(":")
        self.assertEqual(pid_a, pid_b, "beide Auftraege muessen im selben Prozess laufen (Modell nur einmal geladen)")
        self.assertEqual((n_a, n_b), ("1", "2"))

    def test_fehler_exit_laesst_prozess_leben(self):
        r = self.sv.lauf(["--fehler"])
        self.assertEqual(r.returncode, 1)
        self.assertIn("Error: kaputt", r.stderr)
        out = self.tmp / "c.txt"
        self.assertEqual(self.sv.lauf(["--out", str(out)]).returncode, 0)
        self.assertEqual(out.read_text().split(":")[1], "2", "derselbe Prozess hat den Folgeauftrag gemacht")

    def test_absturz_wird_gemeldet_und_naechster_auftrag_startet_neu(self):
        out = self.tmp / "d.txt"
        self.assertEqual(self.sv.lauf(["--out", str(out)]).returncode, 0)
        pid_vorher = out.read_text().split(":")[0]
        r = self.sv.lauf(["--absturz"])
        self.assertEqual(r.returncode, 3)               # Exit-Code des toten Prozesses bleibt sichtbar (Absturz-Erkennung)
        self.assertEqual(self.sv.lauf(["--out", str(out)]).returncode, 0)
        pid_nachher, n = out.read_text().split(":")
        self.assertNotEqual(pid_vorher, pid_nachher)
        self.assertEqual(n, "1", "neuer Prozess, neuer Zaehler")

    def test_start_fehler_ist_ein_fehler_exit(self):
        sv = tc._ChatterboxServer(sys.executable, self.tmp / "gibtsnicht.py", str(self.tmp), "test")
        self.assertNotEqual(sv.lauf(["--out", "x"]).returncode, 0)


class StillstandTest(unittest.TestCase):
    """Vorfall 04.11.2026 (Weltlage 00:00): der Chatterbox-Dauerprozess blieb bei chunk 3/10 in CUDA haengen, der Client
    wartete blockierend 20'038 s, die Spur hielt die ganze Nacht 18,5 GB VRAM, der Desktop stockte. Der Stillstands-
    Waechter beendet einen Worker ohne Ausgabe nach STILLSTAND_S und meldet den Auftrag als Absturz (Wiederholung)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "worker.py").write_text(FAKE_WORKER, encoding="utf-8")
        self.sv = tc._ChatterboxServer(sys.executable, self.tmp / "worker.py", str(self.tmp), "test", stillstand_s=1.0)

    def tearDown(self):
        self.sv.schliessen()

    @staticmethod
    def _lebt(pid: int) -> bool:
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, int(pid))
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return bool(ok) and code.value == 259          # STILL_ACTIVE

    def test_haengender_worker_wird_beendet_und_als_absturz_gemeldet(self):
        import time
        from tts.veredelung import ist_absturz
        out = self.tmp / "e.txt"
        self.assertEqual(self.sv.lauf(["--out", str(out)]).returncode, 0)
        pid_vorher = int(out.read_text().split(":")[0])
        t0 = time.time()
        r = self.sv.lauf(["--haenger"])
        dauer = time.time() - t0
        self.assertEqual(r.returncode, tc.STILLSTAND_RC)
        self.assertTrue(ist_absturz(r.returncode), "Stillstand muss wie ein Absturz zaehlen (Wiederholung)")
        self.assertLess(dauer, 15, f"Waechter 1 s, aber {dauer:.1f} s gewartet")
        self.assertIn("Stillstand", r.stderr)
        self.assertIsNone(self.sv.p)
        for _ in range(50):
            if not self._lebt(pid_vorher):
                break
            time.sleep(0.1)
        self.assertFalse(self._lebt(pid_vorher), "haengender Worker muss beendet sein (sonst bleibt sein VRAM belegt)")
        self.assertEqual(self.sv.lauf(["--out", str(out)]).returncode, 0)
        pid_nachher, n = out.read_text().split(":")
        self.assertNotEqual(int(pid_nachher), pid_vorher)
        self.assertEqual(n, "1", "neuer Prozess, neuer Zaehler")

    def test_wiederholung_nach_stillstand(self):
        out = self.tmp / "f.txt"
        anlaeufe, logs = [0], []

        def lauf():
            anlaeufe[0] += 1
            return self.sv.lauf(["--haenger"] if anlaeufe[0] == 1 else ["--out", str(out)])
        r = tc.worker_mit_wiederholung(lauf, out, name="chatterbox worker", log=logs.append, pause_s=0)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(anlaeufe[0], 2)
        self.assertTrue(out.exists())
        self.assertTrue(any("hing" in z and "Anlauf 1/2" in z for z in logs), logs)

    def test_standard_waechter_ist_grosszuegig(self):
        sv = tc._ChatterboxServer(sys.executable, self.tmp / "worker.py", str(self.tmp), "x")
        self.assertGreaterEqual(sv.stillstand_s, 600, "mindestens 10 min: langsame Chunks neben Cinema-Renders")
        self.assertLessEqual(sv.stillstand_s, 1800, "hoechstens 30 min: sonst haelt ein haengender Worker die Karte")


class GemeinsamerServerTest(unittest.TestCase):
    def test_aufrufe_der_spuren_laufen_nacheinander(self):
        import time
        aktiv, spitze = [0], [0]

        class Fake:
            def lauf(self, args):
                aktiv[0] += 1
                spitze[0] = max(spitze[0], aktiv[0])
                time.sleep(0.05)
                aktiv[0] -= 1
                return 0

            def schliessen(self):
                pass
        g = tc._GemeinsamerServer(Fake())
        ts = [threading.Thread(target=g.lauf, args=([],)) for _ in range(4)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        self.assertEqual(spitze[0], 1, "Enhance (~9 GB Spitze) darf nie zweimal gleichzeitig laufen")

    def test_ausserhalb_der_sitzung_kein_dauerprozess(self):
        self.assertIsNone(tc.enhance_server())


class PhasenTest(unittest.TestCase):
    def test_veredeln_nie_neben_sprechen_sprechen_parallel(self):
        import time
        ph = gpu_spur._LeserSchreiber()
        zustand = {"leser": 0, "schreiber": 0, "max_leser": 0, "verletzt": False}
        z = threading.Lock()

        def leser():
            with ph.gemeinsam():
                with z:
                    zustand["leser"] += 1
                    zustand["max_leser"] = max(zustand["max_leser"], zustand["leser"])
                    zustand["verletzt"] |= zustand["schreiber"] > 0
                time.sleep(0.05)
                with z:
                    zustand["leser"] -= 1

        def schreiber():
            with ph.exklusiv():
                with z:
                    zustand["schreiber"] += 1
                    zustand["verletzt"] |= zustand["leser"] > 0 or zustand["schreiber"] > 1
                time.sleep(0.05)
                with z:
                    zustand["schreiber"] -= 1
        ts = [threading.Thread(target=f) for f in [leser, leser, schreiber, leser, schreiber, leser, leser, schreiber]]
        for t in ts:
            t.start()
        for t in ts:
            t.join(10)
        self.assertFalse(any(t.is_alive() for t in ts), "Verklemmung")
        self.assertFalse(zustand["verletzt"])
        self.assertGreaterEqual(zustand["max_leser"], 2, "Sprechen mehrerer Spuren muss gleichzeitig moeglich sein")


class SpurenTest(unittest.TestCase):
    def setUp(self):
        import weltlage_tts as wt
        self.wt = wt
        self.buchungen = []

        @contextlib.contextmanager
        def slot(step, **kw):
            self.buchungen.append((step, kw.get("vram_mb")))
            yield None
        self.p = mock.patch.object(gpu_spur.gpu_budget, "slot", slot)
        self.p.start()
        self.addCleanup(self.p.stop)
        self.env = mock.patch.dict(os.environ, {"NEWS_TTS_SPUREN": "2"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.gesprochen, self.threads, self.sperre = [], set(), threading.Lock()

    def _sprich(self, text, out, **kw):
        with self.sperre:
            self.gesprochen.append(text)
            self.threads.add(threading.current_thread().name)
        # in der Spur ist der Platz schon gebucht: kein eigener Platz fuer Sprechen/Veredeln/Whisper
        assert gpu_spur.gebucht()
        assert isinstance(gpu_spur.slot("enhance"), contextlib.nullcontext)
        return {"laenge_s": 1.0, "versuche": 1, "kontrolle": {"quote": 1.0}}

    def _offen(self, n=5):
        return [({"id": f"s{i}", "text": "x" * (10 * (i + 1))}, Path(f"s{i}.wav")) for i in range(n)]

    def test_alle_szenen_laengste_zuerst(self):
        with mock.patch.object(self.wt, "sprich", self._sprich), mock.patch.dict(os.environ, {"NEWS_TTS_SPUREN": "1"}):
            self.wt._sprich_alle(self._offen())
        self.assertEqual([len(t) for t in self.gesprochen], [50, 40, 30, 20, 10])

    def test_zwei_spuren_zwei_threads_jede_szene_einmal(self):
        gleichzeitig, spitze = [0], [0]

        def sprich(text, out, **kw):
            with self.sperre:
                gleichzeitig[0] += 1
                spitze[0] = max(spitze[0], gleichzeitig[0])
            import time
            time.sleep(0.15)
            r = self._sprich(text, out)
            with self.sperre:
                gleichzeitig[0] -= 1
            return r
        with mock.patch.object(self.wt, "sprich", sprich):
            self.wt._sprich_alle(self._offen(6))
        self.assertEqual(sorted(len(t) for t in self.gesprochen), [10, 20, 30, 40, 50, 60])
        self.assertEqual(spitze[0], 2)
        self.assertEqual(len(self.threads), 2)
        self.assertEqual([b[0] for b in self.buchungen], ["tts", "tts"])           # ein Platz je Spur
        self.assertEqual(sorted(b[1] for b in self.buchungen), [self.wt.SPUR_MB, self.wt.SPUR_MB_ERSTE])

    def test_fehler_stoppt_die_uebrigen_szenen_und_wird_geworfen(self):
        def sprich(text, out, **kw):
            if len(text) == 50:
                raise RuntimeError("chatterbox worker failed")
            return self._sprich(text, out)
        with mock.patch.object(self.wt, "sprich", sprich), mock.patch.dict(os.environ, {"NEWS_TTS_SPUREN": "1"}):
            with self.assertRaises(RuntimeError):
                self.wt._sprich_alle(self._offen())
        self.assertEqual(self.gesprochen, [])           # die laengste Szene kommt zuerst dran und bricht ab

    def test_ohne_server_wie_bisher_nacheinander_ohne_spurbuchung(self):
        def sprich(text, out, **kw):
            assert not gpu_spur.gebucht()
            self.gesprochen.append(text)
            return {"laenge_s": 1.0, "versuche": 1, "kontrolle": {"quote": 1.0}}
        with mock.patch.object(self.wt, "sprich", sprich), mock.patch.dict(os.environ, {"NEWS_TTS_SERVER": "0"}):
            self.wt._sprich_alle(self._offen(3))
        self.assertEqual(len(self.gesprochen), 3)
        self.assertEqual(self.buchungen, [])

    def test_zusaetzliche_spur_ohne_platz_gibt_auf_die_erste_macht_weiter(self):
        @contextlib.contextmanager
        def slot(step, **kw):
            if "spur 2" in kw.get("name", ""):
                raise TimeoutError("kein Platz")
            yield None
            return
        with mock.patch.object(gpu_spur.gpu_budget, "slot", slot), mock.patch.object(self.wt, "sprich", self._sprich):
            self.wt._sprich_alle(self._offen(4))
        self.assertEqual(len(self.gesprochen), 4)
        self.assertEqual(len(self.threads), 1)

    def test_spuren_anzahl(self):
        with mock.patch.dict(os.environ, {"NEWS_TTS_SPUREN": "3"}):
            self.assertEqual(self.wt.spuren_anzahl(2), 2)
            self.assertEqual(self.wt.spuren_anzahl(9), 3)
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("NEWS_TTS_SPUREN", None)
            with mock.patch.object(gpu_spur.gpu_budget, "game_running", lambda: "GTA5.exe"):
                self.assertEqual(self.wt.spuren_anzahl(9), 1)        # Spiel laeuft: eine Spur
            with mock.patch.object(gpu_spur.gpu_budget, "game_running", lambda: None):
                self.assertEqual(self.wt.spuren_anzahl(9), self.wt.SPUREN_MAX)
                self.assertEqual(self.wt.spuren_anzahl(1), 1)


if __name__ == "__main__":
    unittest.main()
