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
    def _setup(self, upload, thumbnail=None):
        tmp = Path(tempfile.mkdtemp())
        self.gemeldet = []
        self.thumbnail_aufrufe = []
        fake_up = types.ModuleType("upload.youtube_playwright")
        fake_up.upload_datei = upload
        fake_ent = types.ModuleType("weltlage_entscheid")
        fake_ent.mitteilen = lambda titel, text, log=None: self.gemeldet.append(text)

        def _thumb(video_id, mp4, meta=None, log=print):
            self.thumbnail_aufrufe.append((video_id, mp4, meta))
            return thumbnail if thumbnail is not None else False

        for p in (mock.patch.object(takt_mod, "QUEUE_PFAD", tmp / "q.json"),
                  mock.patch.object(takt_mod, "VERLAUF_PFAD", tmp / "v.json"),
                  mock.patch.object(takt_mod, "slots", lambda: ["08:00"]),
                  mock.patch.object(takt_mod, "_thumbnail_setzen_versucht", _thumb),
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

    def test_bestaetigt_versucht_thumbnail_zu_setzen(self):
        """15.10.2026 (Task t-20261015-092430-e232, Beta): upload_datei() lud Shorts bisher IMMER mit
        thumb_path=None hoch, Studio waehlte selbst einen Zufalls-Frame. Nach bestaetigter Veroeffentlichung
        soll ein Standbild aus der Titelkarte gesetzt werden, das Ergebnis landet im Verlauf."""
        self._setup(lambda *a, **k: {"video_id": "abcdefghijk", "oeffentlich_bestaetigt": True}, thumbnail=True)
        takt_mod.takt(NOW)
        self.assertEqual([vid for vid, _, _ in self.thumbnail_aufrufe], ["abcdefghijk"])
        self.assertEqual(self.thumbnail_aufrufe[0][2], {"title": "T"})   # meta wird durchgereicht
        v = json.loads(takt_mod.VERLAUF_PFAD.read_text(encoding="utf-8"))
        self.assertIs(v["hochgeladen"][-1]["thumbnail"], True)

    def test_nicht_bestaetigt_versucht_kein_thumbnail(self):
        """Bleibt die Veroeffentlichung unbestaetigt (Entwurf), waere ein Thumbnail-Versuch unnoetige Studio-Last -
        die stuendliche Nachpruefung zieht das Video ohnehin nach."""
        self._setup(lambda *a, **k: {"video_id": "ZkkmGOjf68w", "oeffentlich_bestaetigt": False,
                                     "studio_status": "ENTWURF"})
        takt_mod.takt(NOW)
        self.assertEqual(self.thumbnail_aufrufe, [])

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


class EinreihenDedupTest(unittest.TestCase):
    """Fehlerfund 16.10.2026 (Task 20261016-103819-3966): szene_id allein (z.B. 'short_2_..._gegenargument')
    wiederholt sich zwischen VERSCHIEDENEN Folgen (abstrakte Skriptstruktur-Label), darum darf der Dedup-
    Schluessel nicht nur die szene_id sein, sonst wird ein neuer Short einer anderen Folge faelschlich als
    schon bekannt verworfen und geht komplett verloren."""

    def _tmp(self):
        tmp = Path(tempfile.mkdtemp())
        for p in (mock.patch.object(takt_mod, "QUEUE_PFAD", tmp / "q.json"),
                  mock.patch.object(takt_mod, "VERLAUF_PFAD", tmp / "v.json")):
            p.start()
            self.addCleanup(p.stop)
        return tmp

    def test_gleiche_szene_id_anderer_folge_wird_nicht_verworfen(self):
        tmp = self._tmp()
        takt_mod._schreiben(takt_mod.VERLAUF_PFAD, {"hochgeladen": [
            {"szene_id": "short_2_s5_a5_gegenargument", "key": "2026-10-14_11:00", "video_id": "alt1234567"}]})
        mp4 = tmp / "short_2_s5_a5_gegenargument.mp4"
        mp4.write_bytes(b"x")
        neu = takt_mod.einreihen("2026-10-15_19:00", "20:00", tmp,
                                 [{"mp4": mp4, "meta": {"title": "Andere Folge, gleiches Szenen-Label"}}])
        self.assertEqual(neu, 1)
        q = json.loads(takt_mod.QUEUE_PFAD.read_text(encoding="utf-8"))
        self.assertEqual(len(q), 1)

    def test_gleiche_szene_id_gleicher_folge_bleibt_dedupliziert(self):
        tmp = self._tmp()
        takt_mod._schreiben(takt_mod.VERLAUF_PFAD, {"hochgeladen": [
            {"szene_id": "short_2_s5_a5_gegenargument", "key": "2026-10-15_19:00", "video_id": "alt1234567"}]})
        mp4 = tmp / "short_2_s5_a5_gegenargument.mp4"
        mp4.write_bytes(b"x")
        neu = takt_mod.einreihen("2026-10-15_19:00", "20:00", tmp,
                                 [{"mp4": mp4, "meta": {"title": "Schon hochgeladen"}}])
        self.assertEqual(neu, 0)


class ThumbnailNachtragTest(unittest.TestCase):
    """16.10.2026: Nachtrag wiederholt das Thumbnail-Setzen fuer kuerzlich hochgeladene, noch nicht bestaetigte
    Shorts - der Erstversuch direkt nach der Veroeffentlichung greift manchmal nicht (Studio verarbeitet die
    Videoqualitaeten vermutlich noch)."""

    def _setup(self, eintraege, ergebnis_folge=None):
        tmp = Path(tempfile.mkdtemp())
        self.versuche = []

        def _thumb(video_id, mp4, meta=None, log=print):
            self.versuche.append(video_id)
            if ergebnis_folge is None:
                return True
            return ergebnis_folge.pop(0)

        for p in (mock.patch.object(takt_mod, "VERLAUF_PFAD", tmp / "v.json"),
                  mock.patch.object(takt_mod, "_thumbnail_setzen_versucht", _thumb)):
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
        return tmp

    def test_zu_jung_wird_noch_nicht_wiederholt(self):
        now = NOW
        self._setup([{"video_id": "v1", "oeffentlich_bestaetigt": True, "thumbnail": False,
                      "thumbnail_versuche": 1, "zeit": now.isoformat(timespec="seconds")}])
        erg = takt_mod.thumbnail_nachtrag(now)
        self.assertEqual(erg["versucht"], 0)
        self.assertEqual(self.versuche, [])

    def test_alt_genug_und_nicht_bestaetigt_wird_wiederholt(self):
        from datetime import timedelta
        now = NOW
        alt = (now - timedelta(minutes=30)).isoformat(timespec="seconds")
        self._setup([{"video_id": "v1", "oeffentlich_bestaetigt": True, "thumbnail": False,
                      "thumbnail_versuche": 1, "zeit": alt}])
        erg = takt_mod.thumbnail_nachtrag(now)
        self.assertEqual(erg["versucht"], 1)
        self.assertEqual(self.versuche, ["v1"])
        v = json.loads(takt_mod.VERLAUF_PFAD.read_text(encoding="utf-8"))
        self.assertIs(v["hochgeladen"][0]["thumbnail"], True)
        self.assertEqual(v["hochgeladen"][0]["thumbnail_versuche"], 2)

    def test_bereits_gesetzt_wird_uebersprungen(self):
        from datetime import timedelta
        now = NOW
        alt = (now - timedelta(minutes=30)).isoformat(timespec="seconds")
        self._setup([{"video_id": "v1", "oeffentlich_bestaetigt": True, "thumbnail": True,
                      "thumbnail_versuche": 1, "zeit": alt}])
        erg = takt_mod.thumbnail_nachtrag(now)
        self.assertEqual(erg["versucht"], 0)

    def test_maximale_versuche_erreicht_wird_aufgegeben(self):
        from datetime import timedelta
        now = NOW
        alt = (now - timedelta(minutes=30)).isoformat(timespec="seconds")
        self._setup([{"video_id": "v1", "oeffentlich_bestaetigt": True, "thumbnail": False,
                      "thumbnail_versuche": takt_mod.THUMBNAIL_VERSUCHE_MAX, "zeit": alt}])
        erg = takt_mod.thumbnail_nachtrag(now)
        self.assertEqual(erg["versucht"], 0)


class ThumbnailSetzenVersucht(unittest.TestCase):
    """15.10.2026 (Marlons Auftrag, analog zum Jarvis-KI-Kanal-Fund): das eigene, komponierte Thumbnail aus
    meta['thumbnail'] hat Vorrang vor dem alten ffmpeg-Standbild-Grab."""

    def _mit_set_thumbnail(self, fake_set):
        tmp = Path(tempfile.mkdtemp())
        fake_up = types.ModuleType("upload.youtube_playwright")
        fake_up.set_thumbnail = fake_set
        p = mock.patch.dict(sys.modules, {"upload.youtube_playwright": fake_up})
        p.start()
        self.addCleanup(p.stop)
        return tmp

    def test_bevorzugt_eigenes_komponiertes_thumbnail(self):
        tmp = self._mit_set_thumbnail(lambda vid, pfad: self.gesetzt.append((vid, pfad)))
        self.gesetzt = []
        eigenes = tmp / "eigenes_thumb.jpg"
        eigenes.write_bytes(b"x")
        mp4 = tmp / "short.mp4"
        mp4.write_bytes(b"x")
        with mock.patch.object(takt_mod, "_thumbnail_aus_titelkarte") as grab:
            ok = takt_mod._thumbnail_setzen_versucht("vid1", mp4, {"thumbnail": str(eigenes)})
        self.assertTrue(ok)
        grab.assert_not_called()   # kein ffmpeg-Grab noetig, eigenes Bild war schon da
        self.assertEqual(self.gesetzt, [("vid1", str(eigenes))])
        self.assertTrue(eigenes.exists())   # eigenes Thumbnail wird NICHT geloescht (gehoert zum Short-Ordner)

    def test_faellt_auf_ffmpeg_grab_zurueck_wenn_kein_eigenes_thumbnail(self):
        tmp = self._mit_set_thumbnail(lambda vid, pfad: self.gesetzt.append((vid, pfad)))
        self.gesetzt = []
        mp4 = tmp / "short.mp4"
        mp4.write_bytes(b"x")
        grab_bild = tmp / "short_thumb.jpg"
        grab_bild.write_bytes(b"x")
        with mock.patch.object(takt_mod, "_thumbnail_aus_titelkarte", return_value=grab_bild) as grab:
            ok = takt_mod._thumbnail_setzen_versucht("vid2", mp4, {"title": "ohne Thumbnail-Feld"})
        self.assertTrue(ok)
        grab.assert_called_once()
        self.assertFalse(grab_bild.exists())   # Rueckfall-Standbild ist nur ein Zwischending, wird aufgeraeumt


if __name__ == "__main__":
    unittest.main()
