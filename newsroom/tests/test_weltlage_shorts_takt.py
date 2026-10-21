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
from upload.youtube_playwright import UploadHaltedForReview  # noqa: E402

NOW = datetime(2026, 10, 14, 8, 17).astimezone()


class ThumbnailLiveSichtbarTest(unittest.TestCase):
    """_thumbnail_live_sichtbar prueft OHNE Playwright/Studio direkt am oeffentlichen CDN-Bild (seit 19.10.2026
    sardefault.jpg = das Bild des Shorts-Regals, vorher hqdefault.jpg; Rueckfall-Heuristik ohne lokales Bild),
    ob das komponierte Thumbnail (durchgezogene Banderole, Erkennung ueber die ganze Bildhoehe) wirklich sichtbar
    ist - der eigentliche Beweis-Schritt, der am 16.10.2026 fehlte (ein fehlerfreier Studio-Speichern-Klick allein
    war keiner, siehe Docstring der Funktion).

    Regressionstest fuer den Befund vom 18.10.2026 (Marlons Meldung ueber den wiederkehrenden Fehler): die erste
    Fassung tastete nur EINEN festen Punkt (18 % der Bildhoehe) ab und nahm an, die Banderole sitze bei jedem
    Short an derselben Stelle - stimmt nicht, render() zentriert den Block je nach Headline-Laenge unterschiedlich
    hoch. test_banderole_ausserhalb_des_alten_fixpunkts_wird_erkannt baut genau diesen Fall nach (Banderole bei
    y=180 statt dem alten Fixpunkt 65) und waere mit der alten Fassung als 'nicht sichtbar' durchgefallen."""

    def _bild_bytes(self, farbe_oben, y_bereich=range(55, 76), x_bereich=range(220, 261), hintergrund=(20, 40, 70)):
        import io
        from PIL import Image
        img = Image.new("RGB", (480, 360), hintergrund)
        for y in y_bereich:
            for x in x_bereich:
                img.putpixel((x, y), farbe_oben)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        return buf.getvalue()

    def _mock_urlopen(self, daten, wirft=None):
        cm = mock.MagicMock()
        cm.__enter__.return_value.read.return_value = daten
        cm.__exit__.return_value = False
        if wirft:
            return mock.patch("urllib.request.urlopen", side_effect=wirft)
        return mock.patch("urllib.request.urlopen", return_value=cm)

    def test_rote_banderole_wird_als_komponiert_erkannt(self):
        daten = self._bild_bytes((225, 20, 45))   # Markenrot, wie weltlage_shorts_thumbnail._banderole
        with self._mock_urlopen(daten):
            self.assertTrue(takt_mod._thumbnail_live_sichtbar("v1", log=lambda *a: None))

    def test_banderole_ausserhalb_des_alten_fixpunkts_wird_erkannt(self):
        """Kurzer Titel -> Block sitzt tiefer in der Safe-Zone, Banderole bei y~180 statt dem alten Fixpunkt 65."""
        daten = self._bild_bytes((225, 20, 45), y_bereich=range(175, 196))
        with self._mock_urlopen(daten):
            self.assertTrue(takt_mod._thumbnail_live_sichtbar("v1", log=lambda *a: None))

    def test_dunkelblauer_studio_frame_wird_nicht_erkannt(self):
        daten = self._bild_bytes((20, 40, 70))   # kein Banderole-Akzent, nur Studio-Hintergrund ueberall
        with self._mock_urlopen(daten):
            self.assertFalse(takt_mod._thumbnail_live_sichtbar("v1", log=lambda *a: None))

    def test_schmale_untertitel_faerbung_wird_nicht_als_banderole_verwechselt(self):
        """Realer Fehlerfund (18.10.2026): ein gelb/orange hervorgehobenes Untertitel-Wort im rohen Videoframe
        traf denselben Rot-Schwellenwert, war aber nur wenige Pixel breit - deutlich unter BANDEROLE_MIN_LAUF."""
        daten = self._bild_bytes((225, 20, 45), y_bereich=range(295, 300), x_bereich=range(230, 236))
        with self._mock_urlopen(daten):
            self.assertFalse(takt_mod._thumbnail_live_sichtbar("v1", log=lambda *a: None))

    def test_netzwerkfehler_gibt_none_statt_fehlzuschlagen(self):
        import urllib.error
        with self._mock_urlopen(None, wirft=urllib.error.URLError("offline")):
            self.assertIsNone(takt_mod._thumbnail_live_sichtbar("v1", log=lambda *a: None))


class ShortsTaktTest(unittest.TestCase):
    def _setup(self, upload, thumbnail=None):
        tmp = Path(tempfile.mkdtemp())
        self.gemeldet = []
        self.thumbnail_aufrufe = []
        fake_up = types.ModuleType("upload.youtube_playwright")
        fake_up.upload_datei = upload
        fake_up.UploadHaltedForReview = UploadHaltedForReview
        fake_ent = types.ModuleType("weltlage_entscheid")
        fake_ent.mitteilen = lambda titel, text, log=None: self.gemeldet.append(text)

        def _thumb(video_id, mp4, meta=None, log=print, **kw):
            self.thumbnail_aufrufe.append((video_id, mp4, meta))
            return {"versucht": True, "gespeichert": bool(thumbnail), "studio_bestaetigt": None}

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
        soll ein Standbild aus der Titelkarte gesetzt werden.

        Befund 16.10.2026 (Task 20261016-103819-3966, verschaerft): ein fehlerfreier Playwright-Aufruf ist
        KEIN Beweis, dass das Bild live sichtbar wird (siehe _thumbnail_live_sichtbar) - "thumbnail" im Verlauf
        bleibt darum nach dem Erstversuch immer False, auch wenn Studio Erfolg meldet. Erst
        thumbnail_nachtrag() darf es nach einer echten CDN-Pruefung auf True setzen."""
        self._setup(lambda *a, **k: {"video_id": "abcdefghijk", "oeffentlich_bestaetigt": True}, thumbnail=True)
        takt_mod.takt(NOW)
        self.assertEqual([vid for vid, _, _ in self.thumbnail_aufrufe], ["abcdefghijk"])
        self.assertEqual(self.thumbnail_aufrufe[0][2], {"title": "T"})   # meta wird durchgereicht
        v = json.loads(takt_mod.VERLAUF_PFAD.read_text(encoding="utf-8"))
        self.assertIs(v["hochgeladen"][-1]["thumbnail"], False)
        self.assertEqual(v["hochgeladen"][-1]["thumbnail_versuche"], 1)
        self.assertIsNotNone(v["hochgeladen"][-1]["thumbnail_letzter_versuch"])

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

    def test_status_unklar_wird_nicht_wiederholt(self):
        """Fehlerfund 18.10.2026 (Task 20261018-152136-0684): Datei wurde an Studio uebergeben, aber keine
        Video-ID lesbar (UploadHaltedForReview ohne eingebettete ID). Ohne die harte Sperre haette die
        naechste Stunde dieselbe Datei blind erneut hochgeladen - echter Doppel-Upload."""
        def upload(*a, **k):
            raise UploadHaltedForReview("Datei x wurde an Studio übergeben, keine Video-ID lesbar (Timeout)")
        self._setup(upload)
        res = takt_mod.takt(NOW)
        self.assertFalse(res["hochgeladen"])
        self.assertEqual(json.loads(takt_mod.QUEUE_PFAD.read_text(encoding="utf-8")), [])
        v = json.loads(takt_mod.VERLAUF_PFAD.read_text(encoding="utf-8"))
        self.assertEqual(len(v["zur_pruefung"]), 1)
        self.assertEqual(v["zur_pruefung"][0]["szene_id"], "short_1_a")
        self.assertIn("unklar", self.gemeldet[0])


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

    def test_geloeschter_eintrag_darf_neu_eingereiht_werden(self):
        """Fehlerfund 18.10.2026 (Task 20261018-161538-e742): die Sperre zaehlte bisher auch bereits geloeschte
        Verlaufseintraege als 'bekannt' - ein (zu Recht oder faelschlich) geloeschter Short liess sich dadurch
        nie wieder hochladen. Ein geloeschter Short ist auf dem Kanal nicht mehr vorhanden, also kein Duplikat."""
        tmp = self._tmp()
        takt_mod._schreiben(takt_mod.VERLAUF_PFAD, {"hochgeladen": [
            {"szene_id": "short_1_s5_a4_verbindung", "key": "2026-10-14_11:00", "video_id": "g-JkGWZ5dJ4",
             "geloescht": True, "geloescht_grund": "Titel-Duplikat"}]})
        mp4 = tmp / "short_1_s5_a4_verbindung.mp4"
        mp4.write_bytes(b"x")
        neu = takt_mod.einreihen("2026-10-14_11:00", "14:00", tmp,
                                 [{"mp4": mp4, "meta": {"title": "Eigener neuer Titel"}}])
        self.assertEqual(neu, 1)


class NachtragTaktTest(unittest.TestCase):
    """nachtrag_takt(): freier Zeitplan (faellig_ab je Eintrag) statt der vier festen SLOTS - fuer Einzelfaelle
    wie das Nachreichen zu Unrecht geloeschter Shorts mit eigenem Zeitplan (Task 20261018-161538-e742)."""

    def _setup(self, upload, thumbnail=None):
        tmp = Path(tempfile.mkdtemp())
        self.gemeldet = []
        self.thumbnail_aufrufe = []
        fake_up = types.ModuleType("upload.youtube_playwright")
        fake_up.upload_datei = upload
        fake_up.UploadHaltedForReview = UploadHaltedForReview
        fake_ent = types.ModuleType("weltlage_entscheid")
        fake_ent.mitteilen = lambda titel, text, log=None: self.gemeldet.append(text)

        def _thumb(video_id, mp4, meta=None, log=print, **kw):
            self.thumbnail_aufrufe.append((video_id, mp4, meta))
            return {"versucht": True, "gespeichert": bool(thumbnail), "studio_bestaetigt": None}

        for p in (mock.patch.object(takt_mod, "NACHTRAG_PFAD", tmp / "n.json"),
                  mock.patch.object(takt_mod, "VERLAUF_PFAD", tmp / "v.json"),
                  mock.patch.object(takt_mod, "_thumbnail_setzen_versucht", _thumb),
                  mock.patch.dict(sys.modules, {"upload.youtube_playwright": fake_up, "weltlage_entscheid": fake_ent})):
            p.start()
            self.addCleanup(p.stop)
        mp4 = tmp / "short_1_a.mp4"
        mp4.write_bytes(b"x")
        return tmp, mp4

    def test_noch_nicht_faelliger_eintrag_wird_nicht_hochgeladen(self):
        tmp, mp4 = self._setup(lambda *a, **k: self.fail("haette nicht hochladen sollen"))
        spaeter = (NOW + __import__("datetime").timedelta(hours=1)).isoformat()
        takt_mod._schreiben(takt_mod.NACHTRAG_PFAD, [{"szene_id": "short_1_a", "mp4": str(mp4),
                                                       "meta": {"title": "T"}, "key": "k", "ordner": str(tmp),
                                                       "faellig_ab": spaeter}])
        res = takt_mod.nachtrag_takt(NOW)
        self.assertFalse(res["faellig"])
        self.assertEqual(len(takt_mod.nachtrag_liste()), 1)

    def test_faelliger_eintrag_wird_hochgeladen_und_entfernt(self):
        tmp, mp4 = self._setup(lambda *a, **k: {"video_id": "abcdefghijk", "oeffentlich_bestaetigt": True})
        takt_mod._schreiben(takt_mod.NACHTRAG_PFAD, [{"szene_id": "short_1_a", "mp4": str(mp4),
                                                       "meta": {"title": "T"}, "key": "k", "ordner": str(tmp),
                                                       "faellig_ab": NOW.isoformat()}])
        res = takt_mod.nachtrag_takt(NOW)
        self.assertTrue(res["hochgeladen"])
        self.assertEqual(res["video_id"], "abcdefghijk")
        self.assertEqual(takt_mod.nachtrag_liste(), [])
        v = json.loads(takt_mod.VERLAUF_PFAD.read_text(encoding="utf-8"))
        self.assertEqual(v["hochgeladen"][-1]["video_id"], "abcdefghijk")

    def test_aeltester_faelliger_eintrag_zuerst(self):
        tmp, mp4 = self._setup(lambda *a, **k: {"video_id": "abcdefghijk", "oeffentlich_bestaetigt": True})
        frueher = (NOW - __import__("datetime").timedelta(hours=4)).isoformat()
        takt_mod._schreiben(takt_mod.NACHTRAG_PFAD, [
            {"szene_id": "short_2_b", "mp4": str(mp4), "meta": {"title": "Zweiter"}, "key": "k2",
             "ordner": str(tmp), "faellig_ab": NOW.isoformat()},
            {"szene_id": "short_1_a", "mp4": str(mp4), "meta": {"title": "Erster"}, "key": "k1",
             "ordner": str(tmp), "faellig_ab": frueher}])
        res = takt_mod.nachtrag_takt(NOW)
        self.assertEqual(res["titel"], "Erster")
        rest = takt_mod.nachtrag_liste()
        self.assertEqual(len(rest), 1)
        self.assertEqual(rest[0]["szene_id"], "short_2_b")

    def test_status_unklar_wird_nicht_wiederholt(self):
        def upload(*a, **k):
            raise UploadHaltedForReview("Datei x wurde an Studio übergeben, keine Video-ID lesbar (Timeout)")
        tmp, mp4 = self._setup(upload)
        takt_mod._schreiben(takt_mod.NACHTRAG_PFAD, [{"szene_id": "short_1_a", "mp4": str(mp4),
                                                       "meta": {"title": "T"}, "key": "k", "ordner": str(tmp),
                                                       "faellig_ab": NOW.isoformat()}])
        res = takt_mod.nachtrag_takt(NOW)
        self.assertFalse(res["hochgeladen"])
        self.assertEqual(takt_mod.nachtrag_liste(), [])
        v = json.loads(takt_mod.VERLAUF_PFAD.read_text(encoding="utf-8"))
        self.assertEqual(len(v["zur_pruefung"]), 1)


class NachtragEinreihenTest(unittest.TestCase):
    def _tmp(self):
        tmp = Path(tempfile.mkdtemp())
        for p in (mock.patch.object(takt_mod, "NACHTRAG_PFAD", tmp / "n.json"),
                  mock.patch.object(takt_mod, "VERLAUF_PFAD", tmp / "v.json")):
            p.start()
            self.addCleanup(p.stop)
        return tmp

    def test_geloeschter_eintrag_darf_als_nachtrag_neu_eingereiht_werden(self):
        self._tmp()
        takt_mod._schreiben(takt_mod.VERLAUF_PFAD, {"hochgeladen": [
            {"szene_id": "short_1_a", "key": "k", "video_id": "alt1234567", "geloescht": True}]})
        neu = takt_mod.nachtrag_einreihen([{"szene_id": "short_1_a", "key": "k", "mp4": "x.mp4",
                                            "meta": {"title": "Neu"}, "ordner": "o", "faellig_ab": NOW.isoformat()}])
        self.assertEqual(neu, 1)

    def test_live_vorhandener_eintrag_wird_nicht_doppelt_eingereiht(self):
        self._tmp()
        takt_mod._schreiben(takt_mod.VERLAUF_PFAD, {"hochgeladen": [
            {"szene_id": "short_1_a", "key": "k", "video_id": "alt1234567"}]})
        neu = takt_mod.nachtrag_einreihen([{"szene_id": "short_1_a", "key": "k", "mp4": "x.mp4",
                                            "meta": {"title": "Neu"}, "ordner": "o", "faellig_ab": NOW.isoformat()}])
        self.assertEqual(neu, 0)


class ThumbnailNachtragTest(unittest.TestCase):
    """16.10.2026: Nachtrag prueft fuer kuerzlich hochgeladene, noch nicht LIVE bestaetigte Shorts zuerst
    objektiv am CDN (_thumbnail_live_sichtbar) und laedt nur bei Bedarf gedrosselt erneut bei Studio hoch -
    der Erstversuch direkt nach der Veroeffentlichung greift manchmal nicht (Studio verarbeitet die
    Videoqualitaeten vermutlich noch), und selbst ein fehlerfreier Studio-Speichern-Klick ist kein Beweis
    fuer Live-Sichtbarkeit (Befund 16.10.2026, zweite Haelfte desselben Tasks)."""

    def _setup(self, eintraege, ergebnis_folge=None, live_folge=None, regal=None):
        tmp = Path(tempfile.mkdtemp())
        self.versuche = []
        self.live_pruefungen = []

        def _thumb(video_id, mp4, meta=None, log=print, **kw):
            self.versuche.append(video_id)
            if ergebnis_folge is None:
                return True
            return ergebnis_folge.pop(0)

        def _live(video_id, lokal=None, log=print, url=None):
            self.live_pruefungen.append(video_id)
            if live_folge is None:
                return False
            return live_folge.pop(0)

        self.regal = regal if regal is not None else {}
        for p in (mock.patch.object(takt_mod, "VERLAUF_PFAD", tmp / "v.json"),
                  mock.patch.object(takt_mod, "_thumbnail_setzen_versucht", _thumb),
                  mock.patch.object(takt_mod, "_thumbnail_live_sichtbar", _live),
                  mock.patch.object(takt_mod, "_thumbnail_bild_bereitstellen", lambda *a, **k: None),
                  mock.patch.object(takt_mod, "shorts_regal_lesen", lambda *a, **k: self.regal),
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
        return tmp

    def test_zu_jung_wird_noch_nicht_wiederholt(self):
        now = NOW
        self._setup([{"video_id": "v1", "oeffentlich_bestaetigt": True, "thumbnail": False,
                      "thumbnail_versuche": 1, "zeit": now.isoformat(timespec="seconds")}])
        erg = takt_mod.thumbnail_nachtrag(now)
        self.assertEqual(erg["versucht"], 0)
        self.assertEqual(self.versuche, [])
        self.assertEqual(self.live_pruefungen, [])

    def test_live_sichtbar_bestaetigt_ohne_neuen_studio_aufruf(self):
        """Haupt-Fix dieses Tasks: ist das Bild schon live sichtbar, braucht es keinen weiteren
        Studio/Playwright-Aufruf - die billige CDN-Pruefung allein bestaetigt den Short."""
        from datetime import timedelta
        now = NOW
        alt = (now - timedelta(minutes=30)).isoformat(timespec="seconds")
        self._setup([{"video_id": "v1", "oeffentlich_bestaetigt": True, "thumbnail": False,
                      "thumbnail_versuche": 1, "zeit": alt}], live_folge=[True])
        erg = takt_mod.thumbnail_nachtrag(now)
        self.assertEqual(erg["versucht"], 1)
        self.assertEqual(self.live_pruefungen, ["v1"])
        self.assertEqual(self.versuche, [])   # kein erneuter Studio-Upload noetig
        v = json.loads(takt_mod.VERLAUF_PFAD.read_text(encoding="utf-8"))
        self.assertIs(v["hochgeladen"][0]["thumbnail"], True)

    def test_noch_nicht_live_wird_bei_studio_erneut_versucht(self):
        from datetime import timedelta
        now = NOW
        alt = (now - timedelta(minutes=30)).isoformat(timespec="seconds")
        self._setup([{"video_id": "v1", "oeffentlich_bestaetigt": True, "thumbnail": False,
                      "thumbnail_versuche": 1, "zeit": alt}], live_folge=[False])
        erg = takt_mod.thumbnail_nachtrag(now)
        self.assertEqual(erg["versucht"], 1)
        self.assertEqual(self.versuche, ["v1"])
        v = json.loads(takt_mod.VERLAUF_PFAD.read_text(encoding="utf-8"))
        # Playwright-Erfolg (fehlerfrei) ist allein kein Beweis - "thumbnail" bleibt False, bis die
        # naechste Live-Pruefung es bestaetigt.
        self.assertIs(v["hochgeladen"][0]["thumbnail"], False)
        self.assertEqual(v["hochgeladen"][0]["thumbnail_versuche"], 2)
        self.assertIsNotNone(v["hochgeladen"][0]["thumbnail_letzter_versuch"])

    def test_kuerzlicher_studio_versuch_wird_nicht_sofort_wiederholt(self):
        """Drosselung: ein frischer Studio-Upload-Versuch darf nicht jede Stunde erneut passieren, solange die
        Live-Pruefung noch nichts bestaetigt - nur die billige CDN-Pruefung laeuft trotzdem jedes Mal."""
        now = NOW
        self._setup([{"video_id": "v1", "oeffentlich_bestaetigt": True, "thumbnail": False,
                      "thumbnail_versuche": 1, "zeit": (now - takt_mod.timedelta(hours=3)).isoformat(timespec="seconds"),
                      "thumbnail_letzter_versuch": (now - takt_mod.timedelta(minutes=10)).isoformat(timespec="seconds")}],
                    live_folge=[False])
        erg = takt_mod.thumbnail_nachtrag(now)
        self.assertEqual(self.live_pruefungen, ["v1"])
        self.assertEqual(self.versuche, [])   # zu frueh fuer einen weiteren Studio-Upload
        self.assertEqual(erg["versucht"], 0)

    def test_sehr_alter_eintrag_wird_weiterhin_live_geprueft(self):
        """Regressionstest fuer den zweiten Befund vom 16.10.2026: eine feste Alters-Obergrenze (vorher 8h,
        dann 48h) liess echte, erfolgreich hochgeladene Shorts fuer immer unbestaetigt, weil Live-Propagation
        beobachtbar laenger dauern kann. Die billige CDN-Pruefung hat darum KEINE Alters-Obergrenze mehr -
        nur die teuren Studio-Upload-Versuche bleiben ueber THUMBNAIL_VERSUCHE_MAX begrenzt."""
        from datetime import timedelta
        now = NOW
        uralt = (now - timedelta(days=10)).isoformat(timespec="seconds")
        self._setup([{"video_id": "v1", "oeffentlich_bestaetigt": True, "thumbnail": False,
                      "thumbnail_versuche": 1, "zeit": uralt}], live_folge=[True])
        erg = takt_mod.thumbnail_nachtrag(now)
        self.assertEqual(self.live_pruefungen, ["v1"])
        self.assertEqual(erg["versucht"], 1)
        v = json.loads(takt_mod.VERLAUF_PFAD.read_text(encoding="utf-8"))
        self.assertIs(v["hochgeladen"][0]["thumbnail"], True)

    def test_bereits_gesetzt_wird_uebersprungen(self):
        from datetime import timedelta
        now = NOW
        alt = (now - timedelta(minutes=30)).isoformat(timespec="seconds")
        self._setup([{"video_id": "v1", "oeffentlich_bestaetigt": True, "thumbnail": True,
                      "thumbnail_versuche": 1, "zeit": alt}])
        erg = takt_mod.thumbnail_nachtrag(now)
        self.assertEqual(erg["versucht"], 0)
        self.assertEqual(self.live_pruefungen, [])

    def test_maximale_versuche_erreicht_prueft_trotzdem_nur_noch_live(self):
        from datetime import timedelta
        now = NOW
        alt = (now - timedelta(minutes=30)).isoformat(timespec="seconds")
        self._setup([{"video_id": "v1", "oeffentlich_bestaetigt": True, "thumbnail": False,
                      "thumbnail_versuche": takt_mod.THUMBNAIL_VERSUCHE_MAX, "zeit": alt}], live_folge=[False])
        erg = takt_mod.thumbnail_nachtrag(now)
        self.assertEqual(self.live_pruefungen, ["v1"])   # Live-Pruefung laeuft trotzdem weiter
        self.assertEqual(self.versuche, [])              # aber kein weiterer Studio-Upload mehr
        self.assertEqual(erg["versucht"], 0)

    def test_erschoepfter_short_wird_als_haengend_gemeldet(self):
        """Befund 18.10.2026 (Marlons Meldung): bisher blieb ein erschoepfter, weiterhin nicht live sichtbarer
        Short nur im stillen Log stecken. 'haengt' gibt der Weltlage-Wache jetzt, was sie als Warnung an Marlon
        melden kann, statt dass der Fehler tagelang unbemerkt bleibt."""
        from datetime import timedelta
        now = NOW
        alt = (now - timedelta(minutes=30)).isoformat(timespec="seconds")
        self._setup([{"video_id": "v1", "titel": "Haengender Short", "oeffentlich_bestaetigt": True,
                      "thumbnail": False, "thumbnail_versuche": takt_mod.THUMBNAIL_VERSUCHE_MAX, "zeit": alt}],
                    live_folge=[False])
        erg = takt_mod.thumbnail_nachtrag(now)
        self.assertEqual(erg["haengt"], [{"video_id": "v1", "titel": "Haengender Short",
                                          "versuche": takt_mod.THUMBNAIL_VERSUCHE_MAX}])

    def test_noch_nicht_erschoepfter_short_gilt_nicht_als_haengend(self):
        from datetime import timedelta
        now = NOW
        alt = (now - timedelta(minutes=30)).isoformat(timespec="seconds")
        self._setup([{"video_id": "v1", "oeffentlich_bestaetigt": True, "thumbnail": False,
                      "thumbnail_versuche": 1, "zeit": alt}], live_folge=[False])
        erg = takt_mod.thumbnail_nachtrag(now)
        self.assertEqual(erg["haengt"], [])

    # ---- seit 19.10.2026 (Task 20261019-193153-93d4): echte Studio-Laeufe zaehlen, Sofort-Nachpruefung, Regal
    def test_nicht_erreichter_studio_lauf_zaehlt_nicht_als_versuch(self):
        """Eine belegte Profil-Sperre o.ae. (versucht=False) darf das Versuchs-Budget nicht aufbrauchen - genau so
        liefen frueher Shorts in 'haengt', ohne dass Studio je erreicht wurde."""
        from datetime import timedelta
        now = NOW
        alt = (now - timedelta(minutes=30)).isoformat(timespec="seconds")
        self._setup([{"video_id": "v1", "oeffentlich_bestaetigt": True, "thumbnail": False,
                      "thumbnail_versuche": 2, "zeit": alt}], live_folge=[False],
                    ergebnis_folge=[{"versucht": False, "gespeichert": False, "studio_bestaetigt": None,
                                     "hinweis": "Studio-Profil belegt"}])
        erg = takt_mod.thumbnail_nachtrag(now)
        v = json.loads(takt_mod.VERLAUF_PFAD.read_text(encoding="utf-8"))
        self.assertEqual(v["hochgeladen"][0]["thumbnail_versuche"], 2)
        self.assertIsNone(v["hochgeladen"][0].get("thumbnail_letzter_versuch"))
        self.assertEqual(erg["ergebnisse"][0]["hinweis"], "Studio-Profil belegt")

    def test_studio_bestaetigt_wird_sofort_live_nachgeprueft(self):
        """Befund 19.10.2026: nach einem von Studio bestaetigten Speichern ist das Bild in unter einer Minute am
        CDN - der Nachtrag prueft darum gleich nach statt eine Stunde zu warten."""
        from datetime import timedelta
        now = NOW
        alt = (now - timedelta(minutes=30)).isoformat(timespec="seconds")
        self._setup([{"video_id": "v1", "oeffentlich_bestaetigt": True, "thumbnail": False,
                      "thumbnail_versuche": 0, "zeit": alt}], live_folge=[False, True],
                    ergebnis_folge=[{"versucht": True, "gespeichert": True, "studio_bestaetigt": True,
                                     "bild": "x.jpg"}])
        erg = takt_mod.thumbnail_nachtrag(now)
        self.assertEqual(self.live_pruefungen, ["v1", "v1"])
        v = json.loads(takt_mod.VERLAUF_PFAD.read_text(encoding="utf-8"))
        self.assertIs(v["hochgeladen"][0]["thumbnail"], True)
        self.assertEqual(v["hochgeladen"][0]["thumbnail_versuche"], 1)
        self.assertTrue(erg["ergebnisse"][0]["live_bestaetigt"])

    def test_studio_gespeichert_aber_nicht_bestaetigt_bleibt_offen(self):
        from datetime import timedelta
        now = NOW
        alt = (now - timedelta(minutes=30)).isoformat(timespec="seconds")
        self._setup([{"video_id": "v1", "oeffentlich_bestaetigt": True, "thumbnail": False,
                      "thumbnail_versuche": 0, "zeit": alt}], live_folge=[False],
                    ergebnis_folge=[{"versucht": True, "gespeichert": True, "studio_bestaetigt": False}])
        takt_mod.thumbnail_nachtrag(now)
        self.assertEqual(self.live_pruefungen, ["v1"])   # keine Sofort-Nachpruefung ohne Studio-Bestaetigung
        v = json.loads(takt_mod.VERLAUF_PFAD.read_text(encoding="utf-8"))
        self.assertIs(v["hochgeladen"][0]["thumbnail"], False)
        self.assertEqual(v["hochgeladen"][0]["thumbnail_versuche"], 1)

    def test_studio_laeufe_pro_aufruf_begrenzt(self):
        """Vorfall 19.10.2026: fuenf Studio-Laeufe am Stueck (je 2-3 min) liefen in den 20-min-Timeout der Wache -
        der Rest wird auf den naechsten Stundenlauf verschoben statt alles zu verlieren."""
        from datetime import timedelta
        now = NOW
        alt = (now - timedelta(minutes=30)).isoformat(timespec="seconds")
        eintraege = [{"video_id": f"v{i}", "oeffentlich_bestaetigt": True, "thumbnail": False,
                      "thumbnail_versuche": 0, "zeit": alt} for i in range(6)]
        self._setup(eintraege, live_folge=[False] * 6)
        erg = takt_mod.thumbnail_nachtrag(now)
        self.assertEqual(self.versuche, [f"v{i}" for i in range(takt_mod.THUMBNAIL_STUDIO_MAX_PRO_LAUF)])
        verschoben = [e for e in erg["ergebnisse"] if e.get("verschoben")]
        self.assertEqual(len(verschoben), 6 - takt_mod.THUMBNAIL_STUDIO_MAX_PRO_LAUF)

    def test_regal_ohne_eigenes_bild_wird_gemeldet(self):
        """Das echte Shorts-Regal der Kanalseite (das, was Marlon sieht) zeigt oar1/oar2/oar3 = automatischer
        Videoframe statt sardefault = eigenes Bild -> nach THUMBNAIL_REGAL_WARN_MIN eine Meldung."""
        from datetime import timedelta
        now = NOW
        alt = (now - timedelta(hours=3)).isoformat(timespec="seconds")
        self._setup([{"video_id": "v1", "titel": "Ohne Bild", "oeffentlich_bestaetigt": True, "thumbnail": False,
                      "thumbnail_versuche": 1, "zeit": alt,
                      "thumbnail_letzter_versuch": (now - timedelta(minutes=10)).isoformat(timespec="seconds")}],
                    live_folge=[False], regal={"v1": "oar2"})
        erg = takt_mod.thumbnail_nachtrag(now)
        self.assertTrue(erg["regal_gelesen"])
        self.assertEqual(erg["regal_ohne_bild"], [{"video_id": "v1", "titel": "Ohne Bild", "regal": "oar2",
                                                   "versuche": 1}])

    def test_regal_frisch_hochgeladen_noch_keine_meldung(self):
        from datetime import timedelta
        now = NOW
        alt = (now - timedelta(minutes=30)).isoformat(timespec="seconds")
        self._setup([{"video_id": "v1", "oeffentlich_bestaetigt": True, "thumbnail": False,
                      "thumbnail_versuche": 1, "zeit": alt,
                      "thumbnail_letzter_versuch": (now - timedelta(minutes=10)).isoformat(timespec="seconds")}],
                    live_folge=[False], regal={"v1": "oar1"})
        erg = takt_mod.thumbnail_nachtrag(now)
        self.assertEqual(erg["regal_ohne_bild"], [])

    def test_regal_rueckfall_setzt_bestaetigten_short_zurueck(self):
        """Ein frueher bestaetigter Short, der im Regal wieder ohne eigenes Bild steht, wird auf unbestaetigt
        zurueckgesetzt und im selben Lauf neu gesetzt - statt still fuer immer 'thumbnail: true' zu bleiben."""
        from datetime import timedelta
        now = NOW
        alt = (now - timedelta(hours=5)).isoformat(timespec="seconds")
        self._setup([{"video_id": "v1", "titel": "Rueckfall", "oeffentlich_bestaetigt": True, "thumbnail": True,
                      "thumbnail_versuche": 6, "zeit": alt}], live_folge=[False], regal={"v1": "oar3"})
        erg = takt_mod.thumbnail_nachtrag(now)
        v = json.loads(takt_mod.VERLAUF_PFAD.read_text(encoding="utf-8"))
        self.assertIs(v["hochgeladen"][0]["thumbnail"], False)
        self.assertEqual(self.versuche, ["v1"])   # Budget zurueckgesetzt, gleich neu gesetzt
        self.assertEqual(v["hochgeladen"][0]["thumbnail_versuche"], 1)
        self.assertIn({"video_id": "v1", "regal_rueckfall": "oar3"}, erg["ergebnisse"])
        self.assertEqual(erg["regal_ohne_bild"][0]["video_id"], "v1")

    def test_regal_mit_eigenem_bild_aendert_nichts(self):
        from datetime import timedelta
        now = NOW
        alt = (now - timedelta(hours=5)).isoformat(timespec="seconds")
        self._setup([{"video_id": "v1", "oeffentlich_bestaetigt": True, "thumbnail": True,
                      "thumbnail_versuche": 1, "zeit": alt}], regal={"v1": "sardefault"})
        erg = takt_mod.thumbnail_nachtrag(now)
        self.assertEqual(erg["versucht"], 0)
        self.assertEqual(erg["regal_ohne_bild"], [])

    def test_regal_nicht_abrufbar_ist_kein_fehler(self):
        from datetime import timedelta
        now = NOW
        alt = (now - timedelta(hours=5)).isoformat(timespec="seconds")
        self._setup([{"video_id": "v1", "oeffentlich_bestaetigt": True, "thumbnail": True,
                      "thumbnail_versuche": 1, "zeit": alt}])
        self.regal = None
        erg = takt_mod.thumbnail_nachtrag(now)
        self.assertFalse(erg["regal_gelesen"])
        self.assertEqual(erg["regal_ohne_bild"], [])


class ThumbnailSetzenVersucht(unittest.TestCase):
    """15.10.2026: das eigene, komponierte Thumbnail. Seit 19.10.2026 (Task 20261019-193153-93d4): nie mehr
    Rueckfall auf einen rohen Videoframe (so wurden bei ZkkmGOjf68w sechs Versuche mit dem falschen Bild
    verbraucht), Rueckgabe ist ein Dict mit dem echten Studio-Ergebnis (versucht/gespeichert/studio_bestaetigt)."""

    def _mit_set_thumbnail(self, fake_set, bild=None):
        tmp = Path(tempfile.mkdtemp())
        fake_up = types.ModuleType("upload.youtube_playwright")
        fake_up.set_thumbnail = fake_set
        for p in (mock.patch.dict(sys.modules, {"upload.youtube_playwright": fake_up}),
                  mock.patch.object(takt_mod, "_thumbnail_bild_bereitstellen", lambda *a, **k: bild)):
            p.start()
            self.addCleanup(p.stop)
        return tmp

    def test_setzt_komponiertes_bild_und_gibt_studio_ergebnis_zurueck(self):
        self.gesetzt = []
        tmp = Path(tempfile.mkdtemp())
        bild = tmp / "short_thumb.jpg"
        bild.write_bytes(b"x")
        self._mit_set_thumbnail(lambda vid, pfad: (self.gesetzt.append((vid, pfad)) or
                                                   {"gespeichert": True, "studio_bestaetigt": True, "hinweis": ""}),
                                bild=bild)
        res = takt_mod._thumbnail_setzen_versucht("vid1", tmp / "short.mp4", {"title": "T"}, titel="T")
        self.assertEqual(self.gesetzt, [("vid1", str(bild))])
        self.assertEqual((res["versucht"], res["gespeichert"], res["studio_bestaetigt"]), (True, True, True))
        self.assertTrue(bild.exists())   # eigenes Thumbnail wird NICHT geloescht (gehoert zum Short-Ordner)

    def test_ohne_komponiertes_bild_kein_studio_aufruf(self):
        """Kein Videoframe-Rueckfall mehr: ohne Komposit wird Studio gar nicht erst bemueht."""
        self.gesetzt = []
        self._mit_set_thumbnail(lambda vid, pfad: self.gesetzt.append((vid, pfad)), bild=None)
        res = takt_mod._thumbnail_setzen_versucht("vid2", Path("x.mp4"), {"title": "ohne"})
        self.assertFalse(res["versucht"])
        self.assertEqual(self.gesetzt, [])

    def test_studio_fehler_zaehlt_nicht_als_versuch(self):
        tmp = Path(tempfile.mkdtemp())
        bild = tmp / "short_thumb.jpg"
        bild.write_bytes(b"x")

        def _wirft(vid, pfad):
            raise RuntimeError("Studio-Profil seit 30 min von PID 1 belegt")
        self._mit_set_thumbnail(_wirft, bild=bild)
        res = takt_mod._thumbnail_setzen_versucht("vid3", tmp / "short.mp4", {"title": "T"})
        self.assertFalse(res["versucht"])
        self.assertIn("belegt", res["hinweis"])

    def test_alte_set_thumbnail_fassung_ohne_rueckgabe(self):
        tmp = Path(tempfile.mkdtemp())
        bild = tmp / "short_thumb.jpg"
        bild.write_bytes(b"x")
        self._mit_set_thumbnail(lambda vid, pfad: None, bild=bild)
        res = takt_mod._thumbnail_setzen_versucht("vid4", tmp / "short.mp4", {"title": "T"})
        self.assertEqual((res["versucht"], res["gespeichert"], res["studio_bestaetigt"]), (True, True, None))


class ThumbnailBildBereitstellenTest(unittest.TestCase):
    """_thumbnail_bild_bereitstellen rendert das Komposit passend zum AKTUELLEN Titel (Sidecar merkt sich den
    Titel) - Befund 19.10.2026: ZkkmGOjf68w hatte gar kein Komposit (Short von vor dem 15.10.), der Nachtrag
    lud darum sechsmal einen rohen Videoframe hoch."""

    def _mit_fuer_short(self):
        self.gerendert = []
        fake = types.ModuleType("tools.weltlage_shorts_thumbnail")

        def fuer_short(meta, out, ordner=None, merken=True):
            self.gerendert.append((meta.get("title"), Path(out)))
            Path(out).parent.mkdir(parents=True, exist_ok=True)
            Path(out).write_bytes(b"jpg")
            return Path(out)
        fake.fuer_short = fuer_short
        p = mock.patch.dict(sys.modules, {"tools.weltlage_shorts_thumbnail": fake})
        p.start()
        self.addCleanup(p.stop)
        tmp = Path(tempfile.mkdtemp())
        (tmp / "shorts").mkdir()
        return tmp

    def test_fehlendes_bild_wird_gerendert_und_sidecar_geschrieben(self):
        ordner = self._mit_fuer_short()
        bild = takt_mod._thumbnail_bild_bereitstellen("short_1_a", "Titel A", ordner, {"title": "alt"},
                                                      log=lambda *a: None)
        self.assertEqual(bild, ordner / "shorts" / "short_1_a_thumb.jpg")
        self.assertEqual(self.gerendert, [("Titel A", bild)])
        sidecar = json.loads((ordner / "shorts" / "short_1_a_thumb.json").read_text(encoding="utf-8"))
        self.assertEqual(sidecar["titel"], "Titel A")

    def test_passender_sidecar_rendert_nicht_erneut(self):
        ordner = self._mit_fuer_short()
        takt_mod._thumbnail_bild_bereitstellen("short_1_a", "Titel A", ordner, None, log=lambda *a: None)
        takt_mod._thumbnail_bild_bereitstellen("short_1_a", "Titel A", ordner, None, log=lambda *a: None)
        self.assertEqual(len(self.gerendert), 1)

    def test_geaenderter_titel_rendert_neu(self):
        ordner = self._mit_fuer_short()
        takt_mod._thumbnail_bild_bereitstellen("short_1_a", "Titel A", ordner, None, log=lambda *a: None)
        takt_mod._thumbnail_bild_bereitstellen("short_1_a", "Titel B (neu)", ordner, None, log=lambda *a: None)
        self.assertEqual([t for t, _ in self.gerendert], ["Titel A", "Titel B (neu)"])

    def test_vorhandenes_bild_ohne_sidecar_wird_einmal_neu_gerendert(self):
        """Bilder aus dem Schnitt vor dem 19.10. haben keinen Sidecar - einmal neu rendern (billig), danach stabil."""
        ordner = self._mit_fuer_short()
        (ordner / "shorts" / "short_1_a_thumb.jpg").write_bytes(b"alt")
        takt_mod._thumbnail_bild_bereitstellen("short_1_a", "Titel A", ordner, {"thumbnail": "irgendwo.jpg"},
                                               log=lambda *a: None)
        self.assertEqual(len(self.gerendert), 1)

    def test_render_fehler_liefert_vorhandenes_bild_nie_videoframe(self):
        ordner = self._mit_fuer_short()
        alt = ordner / "shorts" / "short_1_a_thumb.jpg"
        alt.write_bytes(b"alt")
        fake = sys.modules["tools.weltlage_shorts_thumbnail"]

        def kaputt(*a, **k):
            raise RuntimeError("Font fehlt")
        fake.fuer_short = kaputt
        bild = takt_mod._thumbnail_bild_bereitstellen("short_1_a", "Titel A", ordner, None, log=lambda *a: None)
        self.assertEqual(bild, alt)


class ThumbnailLiveVergleichTest(unittest.TestCase):
    """Seit 19.10.2026 prueft _thumbnail_live_sichtbar sardefault.jpg (das Bild des Shorts-Regals) und vergleicht
    direkt mit dem erwarteten lokalen Komposit; 404 heisst eindeutig 'kein eigenes Bild'."""

    def _jpg(self, farbe, groesse=(1080, 1920)):
        import io
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", groesse, farbe).save(buf, format="JPEG", quality=90)
        return buf.getvalue()

    def _mock_urlopen(self, daten=None, wirft=None):
        cm = mock.MagicMock()
        cm.__enter__.return_value.read.return_value = daten
        cm.__exit__.return_value = False
        if wirft:
            return mock.patch("urllib.request.urlopen", side_effect=wirft)
        return mock.patch("urllib.request.urlopen", return_value=cm)

    def test_404_heisst_kein_eigenes_bild(self):
        import urllib.error
        fehler = urllib.error.HTTPError("u", 404, "Not Found", {}, None)
        with self._mock_urlopen(wirft=fehler):
            self.assertIs(takt_mod._thumbnail_live_sichtbar("v1", log=lambda *a: None), False)

    def test_anderer_http_fehler_ist_kein_urteil(self):
        import urllib.error
        fehler = urllib.error.HTTPError("u", 503, "busy", {}, None)
        with self._mock_urlopen(wirft=fehler):
            self.assertIsNone(takt_mod._thumbnail_live_sichtbar("v1", log=lambda *a: None))

    def test_gleiches_lokales_bild_wird_bestaetigt(self):
        tmp = Path(tempfile.mkdtemp())
        lokal = tmp / "thumb.jpg"
        lokal.write_bytes(self._jpg((120, 20, 30)))
        with self._mock_urlopen(self._jpg((121, 21, 31))):   # YouTube-Neukodierung: minimal anders
            self.assertIs(takt_mod._thumbnail_live_sichtbar("v1", lokal=lokal, log=lambda *a: None), True)

    def test_anderes_lokales_bild_wird_abgelehnt(self):
        tmp = Path(tempfile.mkdtemp())
        lokal = tmp / "thumb.jpg"
        lokal.write_bytes(self._jpg((120, 20, 30)))
        with self._mock_urlopen(self._jpg((20, 40, 70))):
            self.assertIs(takt_mod._thumbnail_live_sichtbar("v1", lokal=lokal, log=lambda *a: None), False)

    def test_platzhalter_zaehlt_nicht(self):
        with self._mock_urlopen(self._jpg((200, 200, 200), groesse=(120, 90))):
            self.assertIs(takt_mod._thumbnail_live_sichtbar("v1", log=lambda *a: None), False)

    def test_versionierte_regal_url_hat_vorrang(self):
        """Befund ZkkmGOjf68w 19.10.2026: die nackte CDN-URL lieferte 33 min nach dem Ersetzen noch das alte Bild
        (Edge-Cache, max-age 7200), das Regal verlinkte schon die neue versionierte URL (?sqp=…)."""
        gesehen = []

        def fake(req, timeout=0):
            gesehen.append(req.full_url)
            raise OSError("offline")
        with mock.patch("urllib.request.urlopen", side_effect=fake):
            takt_mod._thumbnail_live_sichtbar("abcdefghijk", log=lambda *a: None,
                                              url="https://i.ytimg.com/vi/abcdefghijk/sardefault.jpg?sqp=XYZ")
        self.assertEqual(gesehen, ["https://i.ytimg.com/vi/abcdefghijk/sardefault.jpg?sqp=XYZ"])

    def test_url_ist_sardefault(self):
        gesehen = []

        def fake(req, timeout=0):
            gesehen.append(req.full_url)
            raise OSError("offline")
        with mock.patch("urllib.request.urlopen", side_effect=fake):
            takt_mod._thumbnail_live_sichtbar("abcdefghijk", log=lambda *a: None)
        self.assertEqual(gesehen, ["https://i.ytimg.com/vi/abcdefghijk/sardefault.jpg"])


class ShortsRegalAuswertenTest(unittest.TestCase):
    """shorts_regal_auswerten liest aus der echten Kanal-Shorts-Seite, welches Bild das Regal je Short zeigt."""

    HTML = ('{"url":"https://i.ytimg.com/vi/AAAAAAAAAAA/frame0.jpg"} '
            '{"url":"https://i.ytimg.com/vi/AAAAAAAAAAA/sardefault.jpg?sqp=x"} '
            '{"url":"https://i.ytimg.com/vi/BBBBBBBBBBB/frame0.jpg"} '
            '{"url":"https://i.ytimg.com/vi/BBBBBBBBBBB/oar2.jpg?sqp=y"} '
            '{"url":"https://i.ytimg.com/vi/BBBBBBBBBBB/oar2.jpg?sqp=z"} '
            '{"url":"https://i.ytimg.com/vi/CCCCCCCCCCC/frame0.jpg"}')

    def test_eigenes_bild_vs_automatischer_frame(self):
        regal = takt_mod.shorts_regal_auswerten(self.HTML)
        self.assertEqual(regal, {"AAAAAAAAAAA": "sardefault", "BBBBBBBBBBB": "oar2"})

    def test_versionierte_urls_werden_mitgeliefert(self):
        urls = {}
        takt_mod.shorts_regal_auswerten(self.HTML, urls)
        self.assertEqual(urls, {"AAAAAAAAAAA": "https://i.ytimg.com/vi/AAAAAAAAAAA/sardefault.jpg?sqp=x"})

    def test_leer(self):
        self.assertEqual(takt_mod.shorts_regal_auswerten(""), {})
        self.assertEqual(takt_mod.shorts_regal_auswerten(None), {})


if __name__ == "__main__":
    unittest.main()


class VerwaisterUploadTest(unittest.TestCase):
    """Befund 21.10.2026: Takt-Prozess mitten im Upload beendet -> Video bei YouTube, nicht im Verlauf, naechster
    Slot lud dasselbe Short nochmal hoch. _verwaister_upload uebernimmt die Video-ID aus dem Upload-Log."""

    def _log(self, text):
        d = tempfile.mkdtemp()
        p = Path(d) / "x_upload.log"
        p.write_text(text, encoding="utf-8")
        return p

    def test_juengere_unbekannte_id_wird_uebernommen(self):
        p = self._log("2026-10-21 06:56:11 Video-ID: ECzVpvXEpoY\n2026-10-21 06:59:18 Studio-Status ECzVpvXEpoY: PUBLIC (Ziel PUBLIC)\n")
        now = datetime(2026, 10, 21, 8, 5).astimezone()
        res = takt_mod._verwaister_upload(p, set(), now)
        self.assertEqual(res["video_id"], "ECzVpvXEpoY")
        self.assertTrue(res["oeffentlich_bestaetigt"])

    def test_ohne_studio_status_unbestaetigt(self):
        p = self._log("2026-10-21 06:56:11 Video-ID: ECzVpvXEpoY\n")
        res = takt_mod._verwaister_upload(p, set(), datetime(2026, 10, 21, 8, 5).astimezone())
        self.assertFalse(res["oeffentlich_bestaetigt"])

    def test_bekannte_oder_alte_id_wird_ignoriert(self):
        p = self._log("2026-10-21 06:56:11 Video-ID: ECzVpvXEpoY\n")
        now = datetime(2026, 10, 21, 8, 5).astimezone()
        self.assertIsNone(takt_mod._verwaister_upload(p, {"ECzVpvXEpoY"}, now))
        self.assertIsNone(takt_mod._verwaister_upload(p, set(), datetime(2026, 10, 22, 8, 5).astimezone()))
        self.assertIsNone(takt_mod._verwaister_upload(Path("fehlt.log"), set(), now))
