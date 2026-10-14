"""Shorts-Takt: nur Studios Bestaetigung zaehlt als veroeffentlicht, ein Upload mit bekannter Video-ID wird nie
wiederholt (Vorfall 14.10.2026: 08:00-Short blieb Entwurf, Takt meldete trotzdem "veroeffentlicht"). Offline.

    .venv\Scripts\python -m unittest tests.test_weltlage_shorts_takt
"""
import json
import sys
import tempfile
import types
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))

import tools.weltlage_shorts_takt as takt_mod  # noqa: E402

NOW = datetime(2026, 10, 14, 8, 17).astimezone()


class ShortsTaktTest(unittest.TestCase):
    def _setup(self, upload):
        tmp = Path(tempfile.mkdtemp())
        self.gemeldet = []
        fake_up = types.ModuleType("upload.youtube_playwright")
        fake_up.upload_datei = upload
        fake_ent = types.ModuleType("weltlage_entscheid")
        fake_ent.mitteilen = lambda titel, text, log=None: self.gemeldet.append(text)
        for p in (mock.patch.object(takt_mod, "QUEUE_PFAD", tmp / "q.json"),
                  mock.patch.object(takt_mod, "VERLAUF_PFAD", tmp / "v.json"),
                  mock.patch.object(takt_mod, "slots", lambda: ["08:00"]),
                  mock.patch.dict(sys.modules, {"upload.youtube_playwright": fake_up, "weltlage_entscheid": fake_ent})):
            p.start()
            self.addCleanup(p.stop)
        mp4 = tmp / "short_1_a.mp4"
        mp4.write_bytes(b"x")
        takt_mod._schreiben(takt_mod.QUEUE_PFAD, [{"szene_id": "short_1_a", "mp4": str(mp4), "meta": {"title": "T"},
                                                   "key": "k", "slot": "11:00", "ordner": str(tmp)}])

    def test_nicht_bestaetigt_wird_nicht_als_veroeffentlicht_gemeldet(self):
        self._setup(lambda *a, **k: {"video_id": "ZkkmGOjf68w", "oeffentlich_bestaetigt": False,
                                     "studio_status": "ENTWURF"})
        res = takt_mod.takt(NOW)
        self.assertTrue(res["hochgeladen"])
        self.assertIs(res["oeffentlich_bestaetigt"], False)
        v = json.loads(takt_mod.VERLAUF_PFAD.read_text(encoding="utf-8"))
        self.assertIs(v["hochgeladen"][-1]["oeffentlich_bestaetigt"], False)
        self.assertIn("NICHT", self.gemeldet[0])

    def test_bestaetigt(self):
        self._setup(lambda *a, **k: {"video_id": "abcdefghijk", "oeffentlich_bestaetigt": True})
        res = takt_mod.takt(NOW)
        self.assertIs(res["oeffentlich_bestaetigt"], True)
        self.assertTrue(self.gemeldet[0].startswith("Short veröffentlicht"))

    def test_abbruch_nach_dateiuebergabe_wird_vermerkt_statt_wiederholt(self):
        def upload(*a, **k):
            raise RuntimeError("Upload ZkkmGOjf68w nach Dateiübergabe fehlgeschlagen - in Studio prüfen")
        self._setup(upload)
        res = takt_mod.takt(NOW)
        self.assertEqual(res["video_id"], "ZkkmGOjf68w")
        self.assertIs(res["oeffentlich_bestaetigt"], False)
        self.assertEqual(json.loads(takt_mod.QUEUE_PFAD.read_text(encoding="utf-8")), [])

    def test_abbruch_ohne_video_id_bleibt_in_der_warteschlange(self):
        def upload(*a, **k):
            raise RuntimeError("Login weg")
        self._setup(upload)
        with self.assertRaises(RuntimeError):
            takt_mod.takt(NOW)
        self.assertEqual(len(json.loads(takt_mod.QUEUE_PFAD.read_text(encoding="utf-8"))), 1)


if __name__ == "__main__":
    unittest.main()
