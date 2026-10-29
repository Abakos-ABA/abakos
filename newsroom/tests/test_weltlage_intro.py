"""Unreal-Standard-Intro der Weltlage-Folgen (rexemre 20.10.2026): offline, ohne Unreal/GPU/Netz.

    .venv\Scripts\python -m unittest tests.test_weltlage_intro

Prueft: aktiv.json zeigt auf das Unreal-Standard-Intro (das alte Globus-Intro kommt nirgends zurueck), der Rohschnitt
benutzt genau diese Datei, vorbereiten() baut pro Folge neu / verwendet einen schon gebauten Stand wieder / laesst bei
Fehlschlag die letzte gute Fassung liegen und wirft nie, pruefen() meldet alte Daten/Kurse als Warnung.
"""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))

import weltlage_intro as wi  # noqa: E402


class Standard(unittest.TestCase):
    def test_aktiv_json_zeigt_auf_unreal_standard(self):
        cfg = json.loads(wi.AKTIV.read_text(encoding="utf-8"))
        self.assertEqual(cfg["landscape"], wi.STANDARD_NAME)
        self.assertTrue(cfg.get("unreal_standard"))
        self.assertEqual(wi.aktiv_pruefen(), [])

    def test_rohschnitt_benutzt_den_standard_und_baut_ihn_vor_dem_lipsync(self):
        quelle = (ROOT / "tools" / "weltlage_rohschnitt.py").read_text(encoding="utf-8")
        self.assertIn('INTRO = BRAND / "intro" / "weltlage_intro_unreal_standard.mp4"', quelle)
        self.assertNotIn("weltlage_intro_v8", quelle)
        self.assertIn("weltlage_intro.vorbereiten(", quelle)
        self.assertLess(quelle.index("weltlage_intro.vorbereiten("), quelle.index("    def add(video, audio_src"))

    def test_altes_globus_intro_in_aktiv_json_ist_abnahmefehler(self):
        with tempfile.TemporaryDirectory() as t:
            alt = Path(t) / "aktiv.json"
            alt.write_text(json.dumps({"landscape": "weltlage_intro_v8_ace.mp4"}), encoding="utf-8")
            with mock.patch.object(wi, "AKTIV", alt):
                fehler = wi.aktiv_pruefen()
        self.assertTrue(any("Globus" in f for f in fehler), fehler)


class Vorbereiten(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ziel = self.tmp / wi.STANDARD_NAME
        self.ziel.write_bytes(b"alt")
        self.p = mock.patch.object(wi, "STANDARD", self.ziel)
        self.p.start()

    def tearDown(self):
        self.p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _meta(self, **kw):
        m = {"datum": "2026-10-20", "ok": True, "ticker": "ja", "ton": "ja", "stand": "x", **kw}
        self.ziel.with_name(self.ziel.name + ".json").write_text(json.dumps(m), encoding="utf-8")

    def test_schon_gebautes_datum_wird_wiederverwendet(self):
        self._meta()
        with mock.patch.object(subprocess, "run", side_effect=AssertionError("kein Neubau")):
            m = wi.vorbereiten("2026-10-20", log=lambda *_: None)
        self.assertTrue(m["ok"])

    def test_neues_datum_ruft_den_studio_bau_mit_datum_und_ziel(self):
        self._meta(datum="2026-10-19")
        aufrufe = []

        def fake(cmd, **kw):
            aufrufe.append(cmd)
            self._meta(datum="2026-10-21")
            return subprocess.CompletedProcess(cmd, 0, "ok", "")
        with mock.patch.object(subprocess, "run", fake):
            m = wi.vorbereiten("2026-10-21", log=lambda *_: None)
        cmd = aufrufe[0]
        self.assertEqual(Path(cmd[1]).name, "studio.py")
        self.assertEqual(cmd[2], "intro")
        self.assertEqual(cmd[cmd.index("--datum") + 1], "2026-10-21")
        self.assertEqual(cmd[cmd.index("--ziel") + 1], str(self.ziel))
        self.assertTrue(m["ok"])

    def test_fehlschlag_wirft_nicht_und_laesst_letzte_gute_fassung(self):
        self._meta(datum="2026-10-19")
        meldungen = []
        with mock.patch.object(subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "boom")):
            m = wi.vorbereiten("2026-10-21", log=meldungen.append)
        self.assertFalse(m["ok"])
        self.assertEqual(self.ziel.read_bytes(), b"alt")
        self.assertTrue(any("WARNUNG" in x and "2026-10-19" in x for x in meldungen), meldungen)

    def test_timeout_oder_start_fehler_wirft_nicht(self):
        with mock.patch.object(subprocess, "run", side_effect=OSError("kein python")):
            m = wi.vorbereiten("2026-10-21", log=lambda *_: None)
        self.assertFalse(m["ok"])

    def test_pruefen_warnt_bei_altem_datum_und_alten_kursen(self):
        self._meta(datum="2026-10-19", ticker="alt")
        with mock.patch.object(wi, "aktiv_pruefen", return_value=[]):
            fehler, warn = wi.pruefen("2026-10-21")
        self.assertEqual(fehler, [])
        self.assertTrue(any("2026-10-19" in w for w in warn) and any("letzten guten Kurse" in w for w in warn), warn)


if __name__ == "__main__":
    unittest.main()
