"""Weltlage-Shorts-Thumbnail, fuenfter Anlauf (21.10.2026, Task 20261021-105909-286b): klickfreier Data-API-Weg
zuerst, Studio mit Wiederholung, Alarm nur wenn auch die Reparatur scheitert. Offline, kein Netz, kein Browser.

    .venv\\Scripts\\python -m unittest tests.test_weltlage_shorts_thumbnail_robust
"""
import json
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))

import tools.weltlage_shorts_takt as takt_mod  # noqa: E402

NOW = datetime(2026, 10, 21, 12, 0).astimezone()


class DataApiZuerst(unittest.TestCase):
    """_thumbnail_setzen_versucht nimmt die YouTube Data API (upload.youtube_api.thumbnail_setzen), sobald die
    Einrichtung da ist - ohne Studio/Playwright; faellt sie aus, bleibt Studio der Rueckfall."""

    def _fakes(self, api_verfuegbar, api_wirft=None, studio_folge=None):
        tmp = Path(tempfile.mkdtemp())
        bild = tmp / "short_thumb.jpg"
        bild.write_bytes(b"x")
        self.api_aufrufe, self.studio_aufrufe = [], []
        fake_api = types.ModuleType("upload.youtube_api")
        fake_api.verfuegbar = lambda: api_verfuegbar

        def thumbnail_setzen(vid, pfad):
            self.api_aufrufe.append((vid, pfad))
            if api_wirft:
                raise api_wirft
            return {"gespeichert": True, "studio_bestaetigt": True, "hinweis": "Data API thumbnails.set"}
        fake_api.thumbnail_setzen = thumbnail_setzen
        fake_pw = types.ModuleType("upload.youtube_playwright")
        folge = list(studio_folge or [])

        def set_thumbnail(vid, pfad):
            self.studio_aufrufe.append((vid, pfad))
            e = folge.pop(0) if folge else {"gespeichert": True, "studio_bestaetigt": True, "hinweis": ""}
            if isinstance(e, Exception):
                raise e
            return e
        fake_pw.set_thumbnail = set_thumbnail
        for p in (mock.patch.dict(sys.modules, {"upload.youtube_api": fake_api, "upload.youtube_playwright": fake_pw}),
                  mock.patch.object(takt_mod, "_thumbnail_bild_bereitstellen", lambda *a, **k: bild),
                  mock.patch.object(takt_mod, "THUMBNAIL_ANLAUF_PAUSE_S", 0)):
            p.start()
            self.addCleanup(p.stop)
        return tmp, bild

    def test_api_eingerichtet_kein_studio(self):
        tmp, bild = self._fakes(True)
        res = takt_mod._thumbnail_setzen_versucht("vidA", tmp / "s.mp4", {"title": "T"}, log=lambda m: None)
        self.assertEqual(self.api_aufrufe, [("vidA", str(bild))])
        self.assertEqual(self.studio_aufrufe, [])
        self.assertEqual((res["versucht"], res["gespeichert"], res["studio_bestaetigt"], res["weg"]),
                         (True, True, True, "api"))

    def test_api_nicht_eingerichtet_studio(self):
        tmp, bild = self._fakes(False)
        res = takt_mod._thumbnail_setzen_versucht("vidB", tmp / "s.mp4", {"title": "T"}, log=lambda m: None)
        self.assertEqual(self.api_aufrufe, [])
        self.assertEqual(self.studio_aufrufe, [("vidB", str(bild))])
        self.assertEqual(res["weg"], "studio")
        self.assertTrue(res["gespeichert"])

    def test_api_fehler_faellt_auf_studio_zurueck(self):
        tmp, bild = self._fakes(True, api_wirft=RuntimeError("quotaExceeded"))
        res = takt_mod._thumbnail_setzen_versucht("vidC", tmp / "s.mp4", {"title": "T"}, log=lambda m: None)
        self.assertEqual(len(self.api_aufrufe), 1)
        self.assertEqual(len(self.studio_aufrufe), 1)
        self.assertEqual(res["weg"], "studio")

    def test_studio_nicht_gespeichert_zweiter_anlauf(self):
        """Edge-Zombie/kein Speicher-Request beim ersten Mal: ein zweiter Anlauf im selben Versuch."""
        tmp, bild = self._fakes(False, studio_folge=[
            {"gespeichert": False, "studio_bestaetigt": None, "hinweis": "kein Speicher-Request innerhalb 90s"},
            {"gespeichert": True, "studio_bestaetigt": True, "hinweis": ""}])
        res = takt_mod._thumbnail_setzen_versucht("vidD", tmp / "s.mp4", {"title": "T"}, log=lambda m: None)
        self.assertEqual(len(self.studio_aufrufe), 2)
        self.assertTrue(res["gespeichert"] and res["versucht"])

    def test_studio_fehler_ohne_sperre_wird_wiederholt(self):
        tmp, bild = self._fakes(False, studio_folge=[
            RuntimeError("Connection closed while reading from the driver"),
            {"gespeichert": True, "studio_bestaetigt": True, "hinweis": ""}])
        res = takt_mod._thumbnail_setzen_versucht("vidE", tmp / "s.mp4", {"title": "T"}, log=lambda m: None)
        self.assertEqual(len(self.studio_aufrufe), 2)
        self.assertTrue(res["gespeichert"])

    def test_belegte_sperre_wird_nicht_wiederholt(self):
        """Die Profil-Sperre hat schon bis zur Wartegrenze gewartet - nicht noch einmal 30 min blockieren."""
        tmp, bild = self._fakes(False, studio_folge=[RuntimeError("Studio-Profil seit 30 min von PID 1 belegt")])
        res = takt_mod._thumbnail_setzen_versucht("vidF", tmp / "s.mp4", {"title": "T"}, log=lambda m: None)
        self.assertEqual(len(self.studio_aufrufe), 1)
        self.assertFalse(res["versucht"])

    def test_zwei_anlaeufe_sind_die_grenze(self):
        tmp, bild = self._fakes(False, studio_folge=[
            {"gespeichert": False, "studio_bestaetigt": None, "hinweis": "x"},
            {"gespeichert": False, "studio_bestaetigt": None, "hinweis": "y"},
            {"gespeichert": True, "studio_bestaetigt": True, "hinweis": ""}])
        res = takt_mod._thumbnail_setzen_versucht("vidG", tmp / "s.mp4", {"title": "T"}, log=lambda m: None)
        self.assertEqual(len(self.studio_aufrufe), 2)
        self.assertFalse(res["gespeichert"])
        self.assertTrue(res["versucht"])


class AlarmNurWennReparaturScheitert(unittest.TestCase):
    """thumbnail_nachtrag: ein Short, der im Regal ohne eigenes Bild stand und in DIESEM Lauf gesetzt + live
    bestaetigt wurde, ist 'repariert' (Tagesbericht) und verschwindet aus regal_ohne_bild (kein Alarm). Bleibt er
    nach dem Versuch ohne Bild, bleibt der Alarm."""

    def _setup(self, eintraege, regal, setzen_ergebnis, live_folge):
        tmp = Path(tempfile.mkdtemp())
        self.versuche, self.live = [], []

        def _thumb(video_id, mp4, meta=None, log=print, **kw):
            self.versuche.append(video_id)
            return dict(setzen_ergebnis)

        def _live(video_id, lokal=None, log=print, url=None):
            self.live.append(video_id)
            return live_folge.pop(0) if live_folge else False
        for p in (mock.patch.object(takt_mod, "VERLAUF_PFAD", tmp / "v.json"),
                  mock.patch.object(takt_mod, "_thumbnail_setzen_versucht", _thumb),
                  mock.patch.object(takt_mod, "_thumbnail_live_sichtbar", _live),
                  mock.patch.object(takt_mod, "_thumbnail_bild_bereitstellen", lambda *a, **k: None),
                  mock.patch.object(takt_mod, "shorts_regal_lesen", lambda *a, **k: regal),
                  mock.patch.object(takt_mod, "THUMBNAIL_CDN_NACHWARTEN_S", 0)):
            p.start()
            self.addCleanup(p.stop)
        ordner = tmp / "folge"
        (ordner / "shorts").mkdir(parents=True)
        mp4 = ordner / "shorts" / "short_1_a.mp4"
        mp4.write_bytes(b"x")
        (ordner / "shorts" / "short_1_a.json").write_text("{}", encoding="utf-8")
        for e in eintraege:
            e.setdefault("ordner", str(ordner))
            e.setdefault("mp4", str(mp4))
            e.setdefault("szene_id", "short_1_a")
        takt_mod._schreiben(takt_mod.VERLAUF_PFAD, {"hochgeladen": eintraege, "erledigte_slots": []})

    def test_reparatur_gelungen_kein_alarm(self):
        alt = (NOW - timedelta(hours=4)).isoformat(timespec="seconds")
        self._setup([{"video_id": "v1", "oeffentlich_bestaetigt": True, "thumbnail": False, "thumbnail_versuche": 0,
                      "thumbnail_letzter_versuch": None, "zeit": alt}], {"v1": "oar2"},
                    {"versucht": True, "gespeichert": True, "studio_bestaetigt": True, "bild": None, "weg": "api"},
                    live_folge=[False, True])   # erst CDN-Pruefung (noch nicht), nach dem Setzen live
        erg = takt_mod.thumbnail_nachtrag(NOW)
        self.assertEqual(self.versuche, ["v1"])
        self.assertEqual(erg["regal_ohne_bild"], [])
        self.assertEqual(erg["repariert"], [{"video_id": "v1", "weg": "api"}])
        v = json.loads(takt_mod.VERLAUF_PFAD.read_text(encoding="utf-8"))
        self.assertIs(v["hochgeladen"][0]["thumbnail"], True)

    def test_reparatur_gescheitert_alarm_bleibt(self):
        alt = (NOW - timedelta(hours=4)).isoformat(timespec="seconds")
        self._setup([{"video_id": "v2", "oeffentlich_bestaetigt": True, "thumbnail": False, "thumbnail_versuche": 1,
                      "thumbnail_letzter_versuch": None, "zeit": alt}], {"v2": "oar1"},
                    {"versucht": True, "gespeichert": False, "studio_bestaetigt": None, "bild": None, "weg": "studio",
                     "hinweis": "kein Speicher-Request"},
                    live_folge=[False])
        erg = takt_mod.thumbnail_nachtrag(NOW)
        self.assertEqual([h["video_id"] for h in erg["regal_ohne_bild"]], ["v2"])
        self.assertEqual(erg["repariert"], [])

    def test_nur_live_bestaetigt_ohne_setzen_ist_keine_reparatur(self):
        alt = (NOW - timedelta(hours=4)).isoformat(timespec="seconds")
        self._setup([{"video_id": "v3", "oeffentlich_bestaetigt": True, "thumbnail": False, "thumbnail_versuche": 1,
                      "thumbnail_letzter_versuch": None, "zeit": alt}], {"v3": "sardefault"},
                    {"versucht": True, "gespeichert": True, "studio_bestaetigt": True, "bild": None},
                    live_folge=[True])
        erg = takt_mod.thumbnail_nachtrag(NOW)
        self.assertEqual(self.versuche, [])
        self.assertEqual(erg["repariert"], [])
        self.assertEqual(erg["regal_ohne_bild"], [])


if __name__ == "__main__":
    unittest.main()
