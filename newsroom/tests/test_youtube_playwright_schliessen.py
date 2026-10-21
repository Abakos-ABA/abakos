"""Studio-Browser robust starten und schliessen (upload/youtube_playwright._launch, 21.10.2026): Lockfile-Wartezeit,
Neustart bei ProcessSingleton-Fehler, Watchdog beim Schliessen (Edge-155-Zombies). Offline: Fake-Playwright, kein
Browser, kein Netz.

    .venv\\Scripts\\python -m unittest tests.test_youtube_playwright_schliessen
"""
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import upload.youtube_playwright as yp  # noqa: E402


class CloseWatchdog(unittest.TestCase):
    def test_schnelles_schliessen_ohne_eingriff(self):
        calls = []
        st = yp._close_mit_watchdog(lambda: None, beenden_browser=lambda: calls.append("b"),
                                    beenden_treiber=lambda: calls.append("t"), warte_s=0.3, treiber_s=0.6,
                                    log=lambda m: None)
        self.assertEqual(calls, [])
        self.assertFalse(st["browser_beendet"] or st["treiber_beendet"])
        self.assertIsNone(st["fehler"])

    def test_blockierendes_schliessen_browser_dann_treiber(self):
        """context.close() haengt (Edge-Zombie): nach warte_s eigene Browser-Prozesse, nach treiber_s der Treiber;
        der folgende Verbindungsabbruch ist kein Fehler, der Aufrufer kommt zurueck."""
        ev = threading.Event()
        calls = []

        def block():
            ev.wait(10)
            raise RuntimeError("Connection closed while reading from the driver")
        st = yp._close_mit_watchdog(block, beenden_browser=lambda: calls.append("b"),
                                    beenden_treiber=lambda: (calls.append("t"), ev.set()),
                                    warte_s=0.2, treiber_s=0.5, log=lambda m: None)
        self.assertEqual(calls, ["b", "t"])
        self.assertTrue(st["browser_beendet"] and st["treiber_beendet"])
        self.assertIsNone(st["fehler"])
        self.assertLess(st["dauer_s"], 5)

    def test_browser_kill_reicht(self):
        """Reichen die Browser-Kills (close kommt danach zurueck), wird der Treiber nicht angefasst."""
        ev = threading.Event()
        calls = []

        def block():
            ev.wait(10)
        st = yp._close_mit_watchdog(block, beenden_browser=lambda: (calls.append("b"), ev.set()),
                                    beenden_treiber=lambda: calls.append("t"), warte_s=0.2, treiber_s=2.0,
                                    log=lambda m: None)
        self.assertEqual(calls, ["b"])
        self.assertTrue(st["browser_beendet"] and not st["treiber_beendet"])

    def test_echter_fehler_ohne_eingriff_wird_gemeldet(self):
        st = yp._close_mit_watchdog(lambda: (_ for _ in ()).throw(RuntimeError("kaputt")),
                                    beenden_browser=lambda: None, beenden_treiber=lambda: None,
                                    warte_s=0.5, treiber_s=1.0, log=lambda m: None)
        self.assertIn("kaputt", st["fehler"] or "")


class LockfileUndNeustart(unittest.TestCase):
    def test_lockfile_frei_abwarten(self):
        stand = {"n": 0}

        def frei():
            stand["n"] += 1
            return stand["n"] >= 3
        schlaf = []
        self.assertTrue(yp._lockfile_frei_abwarten(max_s=60, schritt_s=5, frei=frei, schlafen=schlaf.append,
                                                   log=lambda m: None))
        self.assertEqual(schlaf, [5, 5])

    def test_lockfile_dauerhaft_belegt_startet_trotzdem(self):
        self.assertFalse(yp._lockfile_frei_abwarten(max_s=0, schritt_s=5, frei=lambda: False, schlafen=lambda s: None,
                                                    log=lambda m: None))

    def test_lockfile_frei_ohne_datei_und_mit_datei(self):
        tmp = Path(tempfile.mkdtemp())
        self.assertTrue(yp._lockfile_frei(tmp))
        (tmp / "lockfile").write_bytes(b"")
        self.assertTrue(yp._lockfile_frei(tmp))

    def test_process_singleton_fehler_erkannt(self):
        self.assertTrue(yp._ist_process_singleton_fehler(RuntimeError(
            "BrowserType.launch_persistent_context: Failed to create a ProcessSingleton for your profile directory.")))
        self.assertTrue(yp._ist_process_singleton_fehler(RuntimeError("Lock file can not be created! Error code: 32")))
        self.assertFalse(yp._ist_process_singleton_fehler(RuntimeError("Timeout 30000ms exceeded")))

    def test_nachkommen(self):
        prozesse = [(1, 0, "python.exe"), (2, 1, "node.exe"), (3, 2, "msedge.exe"), (4, 3, "msedge.exe"),
                    (5, 0, "msedge.exe"), (6, 5, "msedge.exe")]
        self.assertEqual([p[0] for p in yp._nachkommen(2, prozesse)], [3, 4])
        self.assertEqual([p[0] for p in yp._nachkommen(1, prozesse)], [2, 3, 4])
        with mock.patch.object(yp, "_prozessliste", lambda: prozesse):
            self.assertEqual(yp._eigene_browser_pids(1), ([2], [3, 4]))    # 5/6 (fremder Browser) nie dabei

    def test_launch_startet_bei_process_singleton_neu(self):
        tmp = Path(tempfile.mkdtemp())
        versuche = []

        class FakeContext:
            pages = []

            def close(self):
                versuche.append("close")

        class FakeChromium:
            def launch_persistent_context(self, *a, **k):
                versuche.append("launch")
                if len([v for v in versuche if v == "launch"]) == 1:
                    raise RuntimeError("Failed to create a ProcessSingleton for your profile directory.")
                return FakeContext()

        class FakeP:
            chromium = FakeChromium()
        warte = []
        with mock.patch.object(yp, "SPERRE", tmp / "profile.lock"), \
                mock.patch.object(yp, "_lockfile_frei_abwarten", lambda *a, **k: warte.append(1) or True), \
                mock.patch.object(yp.time, "sleep", lambda s: None):
            ctx = yp._launch(FakeP(), headless=True)
            self.assertTrue((tmp / "profile.lock").exists())
            ctx.close()
            self.assertFalse((tmp / "profile.lock").exists())
        self.assertEqual(versuche, ["launch", "launch", "close"])
        self.assertEqual(len(warte), 2)

    def test_launch_anderer_fehler_kein_neustart_sperre_frei(self):
        tmp = Path(tempfile.mkdtemp())

        class FakeChromium:
            def launch_persistent_context(self, *a, **k):
                raise RuntimeError("Timeout 30000ms exceeded")

        class FakeP:
            chromium = FakeChromium()
        with mock.patch.object(yp, "SPERRE", tmp / "profile.lock"), \
                mock.patch.object(yp, "_lockfile_frei_abwarten", lambda *a, **k: True):
            with self.assertRaises(RuntimeError):
                yp._launch(FakeP(), headless=True)
            self.assertFalse((tmp / "profile.lock").exists())


if __name__ == "__main__":
    unittest.main()
