#!/usr/bin/env python
"""Weltlage Kompakt: fester 6-Stunden-Takt fuer Shorts-Uploads (Marlon 13.10.2026, Telegram-Auftrag nach dem
ersten echten Short: ~400 Views/8 Likes/4 Abos in 48 h, deutlich besser als frueherer Inhalt).

Vorher (seit 11.10.) schnitt der Tageslauf Shorts direkt nach jeder Folge und fragte JEDE Short einzeln per
Telegram frei (shorts_erzeugen_und_freigeben in weltlage_tageslauf.py) - das kam unregelmaessig (an die
Folgen-Slots gekoppelt) und brauchte eine Reaktion. Marlons neuer Auftrag: taeglich GENAU 4 Shorts, alle 6
Stunden, vollautomatisch OEFFENTLICH, keine Einzelfreigabe mehr (dauerhafte Freigabe).

Architektur (erweitert statt neu gebaut): das Schneiden bleibt dort, wo es ist (tools/weltlage_shorts.py,
direkt nach der Veroeffentlichung einer Folge, CPU-only - faster-whisper auf CPU, ffmpeg - verdraengt also
nie die GPU-Produktion der naechsten Folge). Statt die fertigen Shorts sofort hochzuladen, legt
weltlage_tageslauf.py sie jetzt in eine Warteschlange (QUEUE_PFAD). Dieses Modul ist der Taktgeber: einmal
pro Stunde ruft die Weltlage-Wache (jarvis\\tools\\weltlage_wache.py) `python -m tools.weltlage_shorts_takt takt`
auf (wie sie auch andere Newsroom-Schritte per Unterprozess im Newsroom-venv ausloest); ist eine der festen
Uhrzeiten (SLOTS) faellig UND fuer diesen Slot heute noch nichts hochgeladen UND die Warteschlange nicht leer,
nimmt es das AELTESTE Element (FIFO = die am laengsten liegende, noch nicht gezeigte Szene) und laedt es direkt
OEFFENTLICH hoch (keine Rueckfrage, kein Freigabe-Timer). Themen-Wiederholung ist bereits durch die vorgelagerte
Themenwahl ausgeschlossen (weltlage_themen.py vergleicht 14 Tage rueckwirkend) und dadurch, dass jede Szene nur
EIN einziges Mal in die Warteschlange kommt (eigene Szene-ID je Short).

Aufruf:
    python -m tools.weltlage_shorts_takt takt [--trocken]   ein Taktschlag (von der Wache, stuendlich)
    python -m tools.weltlage_shorts_takt status             Warteschlange + letzte Uploads ansehen
Gibt bei "takt" zuletzt eine einzelne JSON-Zeile aus (wie andere Newsroom-CLI-Werkzeuge), die die Wache parst.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config.settings import NEWS_WELTLAGE_SHORTS_SLOTS, STATE_DIR  # noqa: E402

QUEUE_PFAD = STATE_DIR / "weltlage_shorts_queue.json"
VERLAUF_PFAD = STATE_DIR / "weltlage_shorts_verlauf.json"
NACHTRAG_PFAD = STATE_DIR / "weltlage_shorts_nachtrag.json"
VIDEO_ID_IN_TEXT = re.compile(r"Upload ([A-Za-z0-9_-]{11}) nach")   # Text von UploadHaltedForReview (upload_datei)
FENSTER_MINUTEN = 110  # Toleranz je Slot (etwas unter 2 h, damit eine ausgefallene Stunden-Runde noch nachholt,
                        # aber niemals zwei Slots verschmelzen - die Wache laeuft stuendlich)
THUMB_ZEIT_S = 1.5   # liegt im eingeblendeten Titelband (0-4 s, tools.weltlage_shorts._titelkarte)


def _thumbnail_aus_titelkarte(mp4: Path, log=print) -> Path | None:
    """Standbild aus der Titelkarten-Phase des fertigen Shorts (t=THUMB_ZEIT_S) - bisher lud upload_datei() Shorts
    IMMER mit thumb_path=None hoch (Studio waehlte selbst einen Zufalls-Frame), obwohl Studio bei Shorts ein
    eigenes Thumbnail-Upload-Feld erlaubt (Live-Check 15.10.2026, Task t-20261015-092430-e232 von Beta: zuvor nur
    unverifizierte Annahme 'nein' im Bericht). Gibt None zurueck, wenn ffmpeg fehlschlaegt - ein Thumbnail ist
    Zusatznutzen, kein Pflichtschritt."""
    from tools.weltlage_shorts import _ffmpeg
    ziel = mp4.with_name(mp4.stem + "_thumb.jpg")
    try:
        _ffmpeg(["-ss", str(THUMB_ZEIT_S), "-i", str(mp4), "-frames:v", "1", "-q:v", "2", str(ziel)], log)
    except Exception as e:   # noqa: BLE001
        log(f"Thumbnail: Standbild aus {mp4.name} fehlgeschlagen ({type(e).__name__}: {e})")
        return None
    return ziel if ziel.exists() else None


def _thumbnail_setzen_versucht(video_id: str, mp4: Path, meta: dict | None = None, log=print) -> bool:
    """Bevorzugt das eigene, komponierte Thumbnail (Text+Branding in der Safe-Zone, von
    weltlage_shorts_thumbnail.fuer_short() beim Schneiden des Shorts gebaut und in meta['thumbnail']
    hinterlegt, Marlons Auftrag 15.10.2026 - Problem vorher: kein eigenes Vorschaubild, Studio/ffmpeg-Grab
    zeigte nur einen rohen Videoframe, die Kachelansicht schnitt oben/unten je rund ein Viertel ab). Fehlt
    das Komposit (altes meta ohne 'thumbnail'-Feld, oder Bild zwischenzeitlich geloescht), faellt es auf den
    alten ffmpeg-Standbild-Grab zurueck, statt ganz ohne Thumbnail hochzuladen."""
    eigenes = Path(meta["thumbnail"]) if meta and meta.get("thumbnail") else None
    aufgeraeumt = False
    if eigenes and eigenes.exists():
        bild = eigenes
    else:
        bild = _thumbnail_aus_titelkarte(mp4, log)
        aufgeraeumt = True
    if bild is None:
        return False
    try:
        from upload.youtube_playwright import set_thumbnail
        set_thumbnail(video_id, str(bild))
        log(f"Thumbnail: {video_id} gesetzt ({bild.name})")
        return True
    except Exception as e:   # noqa: BLE001 - z.B. Profil-Sperre belegt, nie den Takt scheitern lassen
        log(f"Thumbnail: {video_id} nicht gesetzt ({type(e).__name__}: {e})")
        return False
    finally:
        if aufgeraeumt:
            bild.unlink(missing_ok=True)


def _lesen(pfad: Path, default):
    try:
        return json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _schreiben(pfad: Path, daten) -> None:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    tmp = pfad.with_suffix(pfad.suffix + ".tmp")
    tmp.write_text(json.dumps(daten, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(pfad)


def warteschlange() -> list[dict]:
    return _lesen(QUEUE_PFAD, [])


def einreihen(key: str, slot: str, ordner: Path, shorts: list[dict]) -> int:
    """Haengt frisch geschnittene Shorts (aus weltlage_tageslauf.shorts_erzeugen_und_einreihen) ans Ende der
    Warteschlange. shorts: [{"mp4": Path, "meta": dict}, ...] wie weltlage_shorts.baue() liefert. Jede Szene hat
    eine eigene ID (Dateiname short_<i>_<szene>), damit nichts doppelt eingereiht wird.

    Fehlerfund 16.10.2026 (Task 20261016-103819-3966): die Dedup-Pruefung verglich nur die nackte szene_id
    (z.B. 'short_2_s_coldopen_s5_a5_gegenargument'). Diese ID kommt aus der abstrakten Analyse-Skriptstruktur
    (Abschnitt/Argument-Nummer) und wiederholt sich darum zwischen VERSCHIEDENEN Folgen mit voellig anderem
    Thema - ein am 14.10. hochgeladener 'gegenargument'-Short einer Iran-fernen Folge blockierte am 15.10. den
    tatsaechlich neuen 'gegenargument'-Short der Iran-Folge; die fertig geschnittene, 55 s lange Datei wurde
    stillschweigend NIE eingereiht und ging verloren (nur per Zufallsfund in den Dateien bemerkt). Der
    Eindeutigkeits-Schluessel ist jetzt (key, szene_id) statt nur szene_id - key ist die Folge, nie zwei Folgen
    teilen sich einen key.

    Fehlerfund 18.10.2026 (Task 20261018-161538-e742, Marlons Meldung: fuenf zu Unrecht als "Duplikat" geloeschte
    Shorts sollten mit eigenem Titel neu hochgeladen werden): "bekannt" zaehlte bisher JEDEN Verlaufseintrag, auch
    bereits geloeschte - ein absichtlich (ob zu Recht oder faelschlich) geloeschter Short liess sich dadurch nie
    wieder hochladen, die Sperre liess sich nur durch Umbenennen der szene_id aushebeln. Ein geloeschter Short ist
    auf dem Kanal nicht mehr vorhanden, kann also auch kein echtes Duplikat mehr sein; die Sperre bleibt fuer alles
    wirklich noch LIVE Vorhandene unveraendert scharf."""
    q = warteschlange()
    bekannt = {(e.get("key"), e["szene_id"]) for e in q}
    verlauf = _lesen(VERLAUF_PFAD, {"hochgeladen": []})
    bekannt |= {(e.get("key"), e["szene_id"]) for e in verlauf.get("hochgeladen") or []
                if e.get("szene_id") and not e.get("geloescht")}
    neu = 0
    for s in shorts:
        mp4 = Path(s["mp4"])
        szene_id = mp4.stem
        if (key, szene_id) in bekannt:
            continue
        q.append({"szene_id": szene_id, "mp4": str(mp4), "meta": s["meta"], "key": key, "slot": slot,
                  "ordner": str(ordner), "eingereiht_am": datetime.now().astimezone().isoformat(timespec="seconds")})
        bekannt.add((key, szene_id))
        neu += 1
    if neu:
        _schreiben(QUEUE_PFAD, q)
    return neu


def slots() -> list[str]:
    return [s.strip() for s in NEWS_WELTLAGE_SHORTS_SLOTS.split(",") if s.strip()]


def _slot_heute(now: datetime, hhmm: str) -> datetime | None:
    try:
        h, m = (int(x) for x in hhmm.split(":"))
    except ValueError:
        return None
    return now.replace(hour=h, minute=m, second=0, microsecond=0)


def faelliger_slot(now: datetime, verlauf: dict) -> str | None:
    """Gibt "<Datum> <HH:MM>" zurueck, wenn genau jetzt ein Slot im Fenster faellig und noch nicht erledigt ist."""
    erledigt = set(verlauf.get("erledigte_slots") or [])
    for hhmm in slots():
        t = _slot_heute(now, hhmm)
        if t is None or t > now:
            continue
        schluessel = f"{now.date().isoformat()} {hhmm}"
        if schluessel in erledigt:
            continue
        if now - t <= timedelta(minutes=FENSTER_MINUTEN):
            return schluessel
    return None


def takt(now: datetime | None = None, trocken: bool = False) -> dict:
    now = now or datetime.now().astimezone()
    verlauf = _lesen(VERLAUF_PFAD, {"hochgeladen": [], "erledigte_slots": []})
    schluessel = faelliger_slot(now, verlauf)
    if not schluessel:
        return {"faellig": False}
    q = warteschlange()
    if not q:
        if not trocken:
            verlauf.setdefault("erledigte_slots", []).append(schluessel)
            verlauf["erledigte_slots"] = verlauf["erledigte_slots"][-60:]
            _schreiben(VERLAUF_PFAD, verlauf)
        return {"faellig": True, "slot": schluessel, "hochgeladen": False, "grund": "Warteschlange leer"}
    eintrag = q[0]
    if trocken:
        return {"faellig": True, "slot": schluessel, "hochgeladen": False,
                "grund": f"WUERDE hochladen: {eintrag['meta']['title']}"}
    from upload.youtube_playwright import UploadHaltedForReview, upload_datei
    mp4 = Path(eintrag["mp4"])
    if not mp4.exists():
        q.pop(0)
        _schreiben(QUEUE_PFAD, q)
        return {"faellig": True, "slot": schluessel, "hochgeladen": False,
                "grund": f"Datei fehlt, verworfen: {mp4}"}
    try:
        res = upload_datei(mp4, eintrag["meta"], None, visibility="public",
                           log_path=Path(eintrag["ordner"]) / "shorts" / f"{eintrag['szene_id']}_upload.log")
    except Exception as e:   # noqa: BLE001
        # Datei ist schon bei YouTube (Video-ID bekannt): NIE neu hochladen (Duplikat), sondern als nicht bestaetigt
        # vermerken - die stuendliche Haenger-Nachpruefung (jarvis tools/youtube_haenger.py) zieht ihn nach.
        m = VIDEO_ID_IN_TEXT.search(str(e))
        if m:
            res = {"video_id": m.group(1), "oeffentlich_bestaetigt": False, "nachzug_fehler": str(e)[:300]}
        elif isinstance(e, UploadHaltedForReview):
            # Fehlerfund 18.10.2026 (Task 20261018-152136-0684): die Datei wurde an Studio uebergeben, aber wir
            # haben keine Video-ID - ohne die harte Sperre haette die naechste Stunde dieselbe Datei blind erneut
            # hochgeladen (echter Doppel-Upload, siehe youtube_playwright._wizard). Statt zu wiederholen: aus der
            # Warteschlange nehmen, in "zur_pruefung" vermerken, Marlon/Jarvis per weltlage_entscheid informieren.
            q.pop(0)
            _schreiben(QUEUE_PFAD, q)
            verlauf.setdefault("zur_pruefung", []).append({
                "szene_id": eintrag["szene_id"], "key": eintrag["key"], "titel": eintrag["meta"]["title"],
                "mp4": str(mp4), "zeit": now.isoformat(timespec="seconds"), "fehler": str(e)[:500]})
            verlauf["zur_pruefung"] = verlauf["zur_pruefung"][-50:]
            _schreiben(VERLAUF_PFAD, verlauf)
            try:
                import weltlage_entscheid as ent
                ent.mitteilen(f"Short {eintrag['slot']}",
                              f"Status nach Upload-Versuch unklar, NICHT automatisch wiederholt (Duplikat-Gefahr): "
                              f"{eintrag['meta']['title']}\n{str(e)[:300]}\nBitte in YouTube Studio pruefen.", print)
            except Exception:   # noqa: BLE001 - Meldung darf den Takt nie gefaehrden
                pass
            return {"faellig": True, "slot": schluessel, "hochgeladen": False,
                    "grund": "Status nach Upload-Versuch unklar, zur Pruefung vorgemerkt (nicht wiederholt)"}
        else:
            raise
    q.pop(0)
    _schreiben(QUEUE_PFAD, q)
    # Vorfall 14.10.2026: upload_datei meldete den 08:00-Short nicht bestaetigt (Studio: Entwurf), der Takt meldete
    # trotzdem "veroeffentlicht". Jetzt zaehlt nur Studios Bestaetigung (oeffentlich_bestaetigt).
    bestaetigt = bool(res.get("oeffentlich_bestaetigt"))
    # Befund 16.10.2026 (Task 20261016-103819-3966, verschaerft im selben Task am 16.10. nachmittags): das
    # Setzen DIREKT nach dem Upload scheitert bei einem frisch veroeffentlichten Short manchmal lautlos (Studio
    # verarbeitet die Videoqualitaeten noch) UND Studios fehlerfreier Speichern-Klick ist generell kein Beweis,
    # dass das Bild live sichtbar wird (siehe _thumbnail_live_sichtbar-Docstring) - "thumbnail" im Verlauf ist
    # darum NIE mehr der rohe Playwright-Rueckgabewert, sondern bleibt False, bis thumbnail_nachtrag() es unten
    # objektiv am CDN bestaetigt hat.
    thumbnail_versucht = bool(bestaetigt and res.get("video_id"))
    if thumbnail_versucht:
        _thumbnail_setzen_versucht(res["video_id"], mp4, eintrag.get("meta"))
    verlauf.setdefault("hochgeladen", []).append({"szene_id": eintrag["szene_id"], "video_id": res.get("video_id"),
                                                  "zeit": now.isoformat(timespec="seconds"), "key": eintrag["key"],
                                                  "titel": eintrag["meta"]["title"],
                                                  "oeffentlich_bestaetigt": bestaetigt,
                                                  "studio_status": res.get("studio_status"),
                                                  "fehler": res.get("nachzug_fehler"),
                                                  "thumbnail": False, "thumbnail_versuche": 1 if thumbnail_versucht else 0,
                                                  "thumbnail_letzter_versuch":
                                                      now.isoformat(timespec="seconds") if thumbnail_versucht else None,
                                                  "ordner": eintrag.get("ordner"), "mp4": str(mp4)})
    verlauf["hochgeladen"] = verlauf["hochgeladen"][-200:]
    verlauf.setdefault("erledigte_slots", []).append(schluessel)
    verlauf["erledigte_slots"] = verlauf["erledigte_slots"][-60:]
    _schreiben(VERLAUF_PFAD, verlauf)
    try:
        import weltlage_entscheid as ent
        wie = ("Short veröffentlicht" if bestaetigt else
               f"Short hochgeladen, aber NICHT bestätigt öffentlich (Studio: {res.get('studio_status') or 'unbekannt'})"
               " - die Nachprüfung versucht es stündlich weiter")
        ent.mitteilen(f"Short {eintrag['slot']}",
                      f"{wie}: {eintrag['meta']['title']}\nhttps://youtu.be/{res.get('video_id')}",
                      print)
    except Exception:   # noqa: BLE001 - Meldung darf den Takt nie gefaehrden
        pass
    return {"faellig": True, "slot": schluessel, "hochgeladen": True, "video_id": res.get("video_id"),
           "titel": eintrag["meta"]["title"], "rest_warteschlange": len(q), "oeffentlich_bestaetigt": bestaetigt,
           "studio_status": res.get("studio_status")}


def nachtrag_liste() -> list[dict]:
    """Frei geplante Einzel-Nachtraege (Marlon 18.10.2026, Task 20261018-161538-e742: fuenf zu Unrecht als
    'Duplikat' geloeschte, in Wahrheit eigenstaendige Shorts sollten mit eigenem Titel neu hochgeladen werden,
    im Abstand von vier Stunden statt an den vier festen SLOTS). Anders als die normale Warteschlange (q, nur
    FIFO an feste Tageszeiten) hat jeder Eintrag hier eine eigene faellig_ab-Zeit - fuer kuenftige Einzelfaelle
    wiederverwendbar (verpasste/nachzuholende Shorts mit eigenem Zeitplan), nicht an diese fuenf Videos gebunden.
    Eintrag: {"szene_id", "key", "mp4", "meta", "ordner", "faellig_ab" (ISO), "eingereiht_am"}."""
    return _lesen(NACHTRAG_PFAD, [])


def nachtrag_einreihen(eintraege: list[dict]) -> int:
    """Haengt Eintraege an die Nachtrag-Liste an, ueberspringt bereits bekannte (key, szene_id) - wie
    einreihen() oben, nur ohne Bindung an die festen SLOTS. 'bekannt' zaehlt dabei nur noch wirklich LIVE
    vorhandene Uploads (nicht geloeschte), sonst liesse sich eine faelschliche Loeschung nie reparieren."""
    liste = nachtrag_liste()
    verlauf = _lesen(VERLAUF_PFAD, {"hochgeladen": []})
    bekannt = {(e.get("key"), e["szene_id"]) for e in liste}
    bekannt |= {(e.get("key"), e["szene_id"]) for e in verlauf.get("hochgeladen") or []
                if e.get("szene_id") and not e.get("geloescht")}
    neu = 0
    for e in eintraege:
        schluessel = (e.get("key"), e["szene_id"])
        if schluessel in bekannt:
            continue
        liste.append(e)
        bekannt.add(schluessel)
        neu += 1
    if neu:
        _schreiben(NACHTRAG_PFAD, liste)
    return neu


def nachtrag_takt(now: datetime | None = None, trocken: bool = False) -> dict:
    """Stuendlicher Nachtrag-Taktgeber, analog takt() oben, aber faellig_ab je Eintrag statt feste SLOTS - laedt
    hoechstens EINEN faelligen Eintrag pro Aufruf oeffentlich hoch (nie mehrere pro Stunde, dasselbe
    Playwright-Browserprofil wie der normale Takt, siehe Memory playwright-profil-sperre). Von der Weltlage-
    Wache stuendlich aufgerufen, genau wie takt()/thumbnail_nachtrag()."""
    now = now or datetime.now().astimezone()
    liste = nachtrag_liste()
    faellige = sorted((e for e in liste if e.get("faellig_ab", "") <= now.isoformat()),
                      key=lambda e: e["faellig_ab"])
    if not faellige:
        return {"faellig": False, "rest": len(liste)}
    eintrag = faellige[0]
    if trocken:
        return {"faellig": True, "hochgeladen": False, "grund": f"WUERDE hochladen: {eintrag['meta']['title']}"}
    from upload.youtube_playwright import UploadHaltedForReview, upload_datei
    mp4 = Path(eintrag["mp4"])
    verlauf = _lesen(VERLAUF_PFAD, {"hochgeladen": []})
    if not mp4.exists():
        liste = [e for e in liste if e is not eintrag]
        _schreiben(NACHTRAG_PFAD, liste)
        return {"faellig": True, "hochgeladen": False, "grund": f"Datei fehlt, verworfen: {mp4}"}
    try:
        res = upload_datei(mp4, eintrag["meta"], None, visibility="public",
                           log_path=Path(eintrag["ordner"]) / "shorts" / f"{eintrag['szene_id']}_nachtrag_upload.log")
    except Exception as e:   # noqa: BLE001
        m = VIDEO_ID_IN_TEXT.search(str(e))
        if m:
            res = {"video_id": m.group(1), "oeffentlich_bestaetigt": False, "nachzug_fehler": str(e)[:300]}
        elif isinstance(e, UploadHaltedForReview):
            liste = [x for x in liste if x is not eintrag]
            _schreiben(NACHTRAG_PFAD, liste)
            verlauf.setdefault("zur_pruefung", []).append({
                "szene_id": eintrag["szene_id"], "key": eintrag.get("key"), "titel": eintrag["meta"]["title"],
                "mp4": str(mp4), "zeit": now.isoformat(timespec="seconds"), "fehler": str(e)[:500]})
            verlauf["zur_pruefung"] = verlauf["zur_pruefung"][-50:]
            _schreiben(VERLAUF_PFAD, verlauf)
            try:
                import weltlage_entscheid as ent
                ent.mitteilen("Short-Nachtrag",
                              f"Status nach Upload-Versuch unklar, NICHT automatisch wiederholt (Duplikat-Gefahr): "
                              f"{eintrag['meta']['title']}\n{str(e)[:300]}\nBitte in YouTube Studio pruefen.", print)
            except Exception:   # noqa: BLE001 - Meldung darf den Nachtrag nie gefaehrden
                pass
            return {"faellig": True, "hochgeladen": False,
                    "grund": "Status nach Upload-Versuch unklar, zur Pruefung vorgemerkt (nicht wiederholt)"}
        else:
            raise
    liste = [x for x in liste if x is not eintrag]
    _schreiben(NACHTRAG_PFAD, liste)
    bestaetigt = bool(res.get("oeffentlich_bestaetigt"))
    thumbnail_versucht = bool(bestaetigt and res.get("video_id"))
    if thumbnail_versucht:
        _thumbnail_setzen_versucht(res["video_id"], mp4, eintrag.get("meta"))
    verlauf.setdefault("hochgeladen", []).append({
        "szene_id": eintrag["szene_id"], "video_id": res.get("video_id"),
        "zeit": now.isoformat(timespec="seconds"), "key": eintrag.get("key"),
        "titel": eintrag["meta"]["title"], "oeffentlich_bestaetigt": bestaetigt,
        "studio_status": res.get("studio_status"), "fehler": res.get("nachzug_fehler"),
        "thumbnail": False, "thumbnail_versuche": 1 if thumbnail_versucht else 0,
        "thumbnail_letzter_versuch": now.isoformat(timespec="seconds") if thumbnail_versucht else None,
        "ordner": eintrag.get("ordner"), "mp4": str(mp4)})
    verlauf["hochgeladen"] = verlauf["hochgeladen"][-200:]
    _schreiben(VERLAUF_PFAD, verlauf)
    try:
        import weltlage_entscheid as ent
        wie = ("Short-Nachtrag veröffentlicht" if bestaetigt else
               f"Short-Nachtrag hochgeladen, aber NICHT bestätigt öffentlich "
               f"(Studio: {res.get('studio_status') or 'unbekannt'})")
        ent.mitteilen("Short-Nachtrag",
                      f"{wie}: {eintrag['meta']['title']}\nhttps://youtu.be/{res.get('video_id')}", print)
    except Exception:   # noqa: BLE001
        pass
    return {"faellig": True, "hochgeladen": True, "video_id": res.get("video_id"),
           "titel": eintrag["meta"]["title"], "rest": len(liste), "oeffentlich_bestaetigt": bestaetigt,
           "studio_status": res.get("studio_status")}


THUMBNAIL_VERSUCHE_MAX = 6          # Studio-Upload-Versuche, danach nicht mehr neu hochladen (nur noch live pruefen)
THUMBNAIL_NACHTRAG_WARTE_MIN = 15   # erster Nachtrag-Versuch fruehestens so lange nach dem Erstversuch
THUMBNAIL_STUDIO_WIEDERHOLEN_MIN = 60   # Mindestabstand zwischen zwei Studio-Upload-Versuchen desselben Shorts
# Keine Obergrenze fuers Alter mehr (Befund 16.10.2026, zweite Haelfte desselben Tasks): die alte 8h-Grenze liess
# echte Shorts fuer immer unbestaetigt, weil Live-Propagation beobachtbar laenger als 8h dauern kann (ein zuvor
# korrekt gesetztes Thumbnail zeigte sich bei zwei baugleichen Shorts erst nach >24h bzw. gar nicht - siehe
# _thumbnail_live_sichtbar-Docstring). Die billige CDN-Pruefung kostet pro Short nur einen HTTP-Get und darf
# darum unbegrenzt oft laufen; nur die TEUREN Studio-Upload-Versuche bleiben ueber THUMBNAIL_VERSUCHE_MAX
# begrenzt, unabhaengig vom Alter.


BANDEROLE_MIN_LAUF = 20   # Mindestbreite (Pixel im hqdefault-Bild) eines zusammenhaengenden Banderole-Treffers


def _thumbnail_live_sichtbar(video_id: str, log=print) -> bool | None:
    """Objektive Pruefung OHNE Playwright/Studio, ob das komponierte Thumbnail (Banderole + Headline + Latara-
    Foto, siehe tools/weltlage_shorts_thumbnail.render) auf YouTube wirklich sichtbar ist. Befund 16.10.2026
    (dieser Task, Marlon-Meldung 'nur die zwei neusten Shorts mit neuem Bild haben viele Aufrufe'): Studios
    Speichern-Button meldet bei set_thumbnail() praktisch IMMER Erfolg (kein Playwright-Fehler) - Stichprobe per
    oEmbed/hqdefault.jpg zeigte aber bei 4 von 6 schon veroeffentlichten Shorts Stunden spaeter immer noch den
    alten, zufaelligen Studio-Frame, bei zwei baugleichen Shorts AUS DEMSELBEN Upload-Lauf (g-JkGWZ5dJ4 vs.
    zBFgmh-fSF0) sogar mit genau demselben Ergebniscode (True) aber unterschiedlichem Live-Ausgang - der
    Playwright-Erfolg allein ist also kein verlaesslicher Beweis, nur eine echte Nachpruefung am CDN ist es.

    Befund 18.10.2026 (Marlons Meldung: beim neusten Short fehlt wieder das eigene Thumbnail, wiederkehrender
    Fehler): die erste Fassung tastete nur EINEN festen Punkt ab (cy = 18 % der Bildhoehe) - das nahm an, die
    Banderole sitze bei jedem Short an derselben Stelle. Stimmt nicht: render() in weltlage_shorts_thumbnail.py
    zentriert den ganzen Block (Banderole+Headline+Foto+Markenbalken) vertikal in der Safe-Zone, die Banderole-
    Position haengt also von der Headline-Laenge (1-4 Zeilen) ab und verschiebt sich pro Short um bis zu einigen
    Dutzend Pixeln. Stichprobe an sieben zuletzt hochgeladenen Shorts (3 davon seit Tagen faelschlich als "nicht
    sichtbar" markiert, bis zu 6 nutzlose Studio-Neuversuche je Short): bei allen dreien sass die Banderole ausserhalb
    des alten Abtastpunkts, war aber klar im Bild vorhanden. Jetzt wird die GANZE Bildhoehe zeilenweise abgetastet
    und der laengste zusammenhaengende Lauf an Banderole-Pixeln in der horizontalen Mitte gesucht (die Banderole ist
    ein durchgezogener farbiger Balken, darum ein breiter Lauf). Echte Treffer lagen in derselben Stichprobe
    durchgehend bei 34-55 Pixeln Laufweite; falsche Treffer durch farbige Untertitel-Woerter im rohen Videoframe
    (z.B. gelb hervorgehobene Begriffe) kamen nie ueber 7 Pixel - BANDEROLE_MIN_LAUF = 20 liegt mit viel Abstand
    dazwischen. hqdefault.jpg ist das oeffentliche, unauthentifizierte Vorschaubild-CDN-Bild zu jeder Video-ID
    (kein API-Key noetig). Gibt None zurueck, wenn das Bild gerade nicht abrufbar ist (kein Fehlschlag, einfach
    beim naechsten Taktschlag erneut pruefen)."""
    import io
    import urllib.error
    import urllib.request

    from PIL import Image

    url = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            daten = r.read()
    except (urllib.error.URLError, OSError) as e:
        log(f"Thumbnail-Live-Pruefung {video_id}: hqdefault.jpg nicht abrufbar ({e})")
        return None
    try:
        bild = Image.open(io.BytesIO(daten)).convert("RGB")
    except Exception as e:   # noqa: BLE001 - defektes/leeres Bild zaehlt als "jetzt nicht pruefbar"
        log(f"Thumbnail-Live-Pruefung {video_id}: Bild nicht lesbar ({e})")
        return None
    bester_lauf, beste_y = _laengster_banderole_lauf(bild)
    sichtbar = bester_lauf >= BANDEROLE_MIN_LAUF
    log(f"Thumbnail-Live-Pruefung {video_id}: "
        f"{'komponiertes Bild erkannt' if sichtbar else 'noch alter Frame/unbekannt'} "
        f"(laengster Banderole-Lauf {bester_lauf}px bei y={beste_y})")
    return sichtbar


def _laengster_banderole_lauf(bild) -> tuple[int, int | None]:
    """Sucht ueber das GANZE Bild (nicht nur einen Punkt) zeilenweise den laengsten zusammenhaengenden Lauf an
    Pixeln in Banderole-Farbe (hell, deutlich mehr Rot als Blau) - weil die Banderole-Zeile je nach Headline-
    Laenge unterschiedlich hoch sitzt (siehe _thumbnail_live_sichtbar). Eine Mindestlaufweite statt eines
    Einzelpixels unterscheidet die durchgezogene Banderole zuverlaessig von einzelnen farbigen Untertitel-
    Buchstaben im rohen Videoframe, die nie einen so breiten zusammenhaengenden Lauf ergeben."""
    w, h = bild.size
    bester, beste_y = 0, None
    for y in range(h):
        lauf = 0
        for x in range(w):
            r, g, b = bild.getpixel((x, y))
            if r > 150 and r - b > 60:
                lauf += 1
                if lauf > bester:
                    bester, beste_y = lauf, y
            else:
                lauf = 0
    return bester, beste_y


def thumbnail_nachtrag(now: datetime | None = None) -> dict:
    """Pflegt das Thumbnail-Setzen fuer alle Shorts nach, bei denen es (noch) nicht live bestaetigt ist. Zwei
    getrennte Schritte pro Short: (1) billige, objektive Live-Pruefung direkt am CDN (_thumbnail_live_sichtbar) -
    bestaetigt sie das komponierte Bild, ist der Short erledigt, ohne dass ueberhaupt ein Studio/Playwright-
    Aufruf noetig war; (2) ist es noch nicht sichtbar, wird hoechstens alle THUMBNAIL_STUDIO_WIEDERHOLEN_MIN
    erneut bei Studio hochgeladen (nie oefter als THUMBNAIL_VERSUCHE_MAX). Wird stuendlich von der Weltlage-
    Wache aufgerufen (jarvis/tools/weltlage_wache.py), genau wie takt() selbst - idempotent, darf beliebig oft
    auf denselben Short angewendet werden.

    Befund 16.10.2026 (Task 20261016-103819-3966 hatte das Feld 'thumbnail' fälschlich schon nach dem ersten
    fehlerfreien Playwright-Aufruf auf True gesetzt, siehe _thumbnail_live_sichtbar-Docstring): 'thumbnail' ist
    jetzt ausschliesslich die LIVE-bestaetigte Wahrheit, nie mehr nur "Studio hat ohne Fehler gespeichert".

    Befund 18.10.2026 (Marlons Meldung ueber den wiederkehrenden Fehler): bis hierhin blieb ein Short, der
    THUMBNAIL_VERSUCHE_MAX erreicht hatte und trotzdem nie live bestaetigt wurde, STILL stecken - die Funktion
    pruefte ihn zwar stuendlich weiter (billige Live-Pruefung), meldete das aber nirgends, darum fiel der
    eigentliche Fehlerfall (Studio meldet Erfolg, das Bild aendert sich aber nie) erst auf, als Marlon es von
    Hand bemerkte. 'haengt' listet jetzt genau diese erschoepften, weiterhin nicht sichtbaren Videos - die
    Weltlage-Wache (jarvis/tools/weltlage_wache.py) meldet sie als Warnung, bis ein Mensch nachschaut."""
    now = now or datetime.now().astimezone()
    verlauf = _lesen(VERLAUF_PFAD, {"hochgeladen": [], "erledigte_slots": []})
    ergebnisse = []
    haengt = []
    geaendert = False
    for eintrag in verlauf.get("hochgeladen", []):
        if (eintrag.get("thumbnail") is True or eintrag.get("geloescht") or not eintrag.get("oeffentlich_bestaetigt")
                or not eintrag.get("video_id")):
            continue
        try:
            alter_min = (now - datetime.fromisoformat(eintrag["zeit"])).total_seconds() / 60
        except (KeyError, ValueError):
            continue
        if alter_min < THUMBNAIL_NACHTRAG_WARTE_MIN:
            continue
        live = _thumbnail_live_sichtbar(eintrag["video_id"])
        if live:
            eintrag["thumbnail"] = True
            ergebnisse.append({"video_id": eintrag["video_id"], "live_bestaetigt": True})
            geaendert = True
            continue
        versuche = eintrag.get("thumbnail_versuche") or 0
        if versuche >= THUMBNAIL_VERSUCHE_MAX:
            haengt.append({"video_id": eintrag["video_id"], "titel": eintrag.get("titel"), "versuche": versuche})
            continue
        letzter = eintrag.get("thumbnail_letzter_versuch")
        zu_frueh = False
        if letzter:
            try:
                zu_frueh = ((now - datetime.fromisoformat(letzter)).total_seconds() / 60
                            < THUMBNAIL_STUDIO_WIEDERHOLEN_MIN)
            except ValueError:
                zu_frueh = False
        if zu_frueh:
            continue
        ordner, mp4 = eintrag.get("ordner"), eintrag.get("mp4")
        if not ordner or not mp4 or not Path(mp4).exists():
            continue
        meta = _lesen(Path(ordner) / "shorts" / f"{eintrag['szene_id']}.json", None)
        ok = _thumbnail_setzen_versucht(eintrag["video_id"], Path(mp4), meta)
        eintrag["thumbnail_versuche"] = versuche + 1
        eintrag["thumbnail_letzter_versuch"] = now.isoformat(timespec="seconds")
        ergebnisse.append({"video_id": eintrag["video_id"], "versuch": versuche + 1, "studio_gesetzt": ok,
                           "live_bestaetigt": False})
        geaendert = True
    if geaendert:
        _schreiben(VERLAUF_PFAD, verlauf)
    return {"versucht": len(ergebnisse), "ergebnisse": ergebnisse, "haengt": haengt}


def status_text() -> str:
    q = warteschlange()
    verlauf = _lesen(VERLAUF_PFAD, {"hochgeladen": [], "erledigte_slots": []})
    zeilen = [f"Slots: {', '.join(slots())}", f"Warteschlange: {len(q)} Short(s)"]
    for e in q[:8]:
        zeilen.append(f"  - {e['szene_id']}: {e['meta']['title']}")
    letzte = (verlauf.get("hochgeladen") or [])[-5:]
    if letzte:
        zeilen.append("Zuletzt hochgeladen:")
        for e in letzte:
            zeilen.append(f"  - {e['zeit']}: {e['titel']} -> https://youtu.be/{e['video_id']}")
    return "\n".join(zeilen)


def main():
    import argparse
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("takt")
    t.add_argument("--trocken", action="store_true")
    sub.add_parser("status")
    sub.add_parser("thumbnail_nachtrag")
    n = sub.add_parser("nachtrag_takt")
    n.add_argument("--trocken", action="store_true")
    a = p.parse_args()
    if a.cmd == "status":
        print(status_text())
        return
    if a.cmd == "thumbnail_nachtrag":
        print(json.dumps(thumbnail_nachtrag(), ensure_ascii=False))
        return
    if a.cmd == "nachtrag_takt":
        print(json.dumps(nachtrag_takt(trocken=a.trocken), ensure_ascii=False))
        return
    erg = takt(trocken=a.trocken)
    print(json.dumps(erg, ensure_ascii=False))


if __name__ == "__main__":
    main()
