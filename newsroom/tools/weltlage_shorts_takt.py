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
    teilen sich einen key."""
    q = warteschlange()
    bekannt = {(e.get("key"), e["szene_id"]) for e in q}
    verlauf = _lesen(VERLAUF_PFAD, {"hochgeladen": []})
    bekannt |= {(e.get("key"), e["szene_id"]) for e in verlauf.get("hochgeladen") or [] if e.get("szene_id")}
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
    from upload.youtube_playwright import upload_datei
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
        if not m:
            raise
        res = {"video_id": m.group(1), "oeffentlich_bestaetigt": False, "nachzug_fehler": str(e)[:300]}
    q.pop(0)
    _schreiben(QUEUE_PFAD, q)
    # Vorfall 14.10.2026: upload_datei meldete den 08:00-Short nicht bestaetigt (Studio: Entwurf), der Takt meldete
    # trotzdem "veroeffentlicht". Jetzt zaehlt nur Studios Bestaetigung (oeffentlich_bestaetigt).
    bestaetigt = bool(res.get("oeffentlich_bestaetigt"))
    # Befund 16.10.2026 (Task 20261016-103819-3966): das Setzen DIREKT nach dem Upload scheitert bei einem
    # frisch veroeffentlichten Short manchmal lautlos (Studio verarbeitet die Videoqualitaeten noch) - darum
    # zaehlt dieser erste Versuch nicht als letzte Chance, siehe thumbnail_nachtrag() unten, das denselben
    # Aufruf ueber mehrere Wache-Runden hinweg wiederholt, solange "thumbnail" noch nicht True ist.
    thumbnail = (_thumbnail_setzen_versucht(res["video_id"], mp4, eintrag.get("meta"))
                if bestaetigt and res.get("video_id") else False)
    verlauf.setdefault("hochgeladen", []).append({"szene_id": eintrag["szene_id"], "video_id": res.get("video_id"),
                                                  "zeit": now.isoformat(timespec="seconds"), "key": eintrag["key"],
                                                  "titel": eintrag["meta"]["title"],
                                                  "oeffentlich_bestaetigt": bestaetigt,
                                                  "studio_status": res.get("studio_status"),
                                                  "fehler": res.get("nachzug_fehler"),
                                                  "thumbnail": thumbnail, "thumbnail_versuche": 1,
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


THUMBNAIL_VERSUCHE_MAX = 4          # danach aufgeben, nicht endlos jede Stunde gegen Studio laufen
THUMBNAIL_NACHTRAG_WARTE_MIN = 15   # erster Nachtrag-Versuch fruehestens so lange nach dem Erstversuch
THUMBNAIL_NACHTRAG_FENSTER_MIN = 8 * 60   # nach 8 h nicht mehr automatisch nachfassen (sehr alte Shorts)


def thumbnail_nachtrag(now: datetime | None = None) -> dict:
    """Wiederholt das Thumbnail-Setzen fuer kuerzlich hochgeladene Shorts, bei denen es beim ersten Versuch
    (direkt im Anschluss an takt(), siehe oben) nicht gegriffen hat. Befund 16.10.2026 (Task
    20261016-103819-3966, Marlon-Meldung 'die zwei neusten Shorts sehen wieder alt aus'): set_thumbnail() lief
    beim allerersten Versuch (Sekunden nach der Veroeffentlichung) ohne Fehler durch, das komponierte Bild blieb
    aber live nicht sichtbar - derselbe Aufruf Stunden spaeter (manueller Nachtrag) hat zuverlaessig funktioniert.
    Vermutliche Ursache: YouTube verarbeitet die Videoqualitaeten eines frisch veroeffentlichten Shorts noch, ein
    in diesem Fenster gesetztes Vorschaubild wird dabei verworfen. Wird stuendlich von der Weltlage-Wache
    aufgerufen (jarvis/tools/weltlage_wache.py), genau wie takt() selbst - idempotent, darf beliebig oft auf
    denselben Short angewendet werden."""
    now = now or datetime.now().astimezone()
    verlauf = _lesen(VERLAUF_PFAD, {"hochgeladen": [], "erledigte_slots": []})
    ergebnisse = []
    geaendert = False
    for eintrag in verlauf.get("hochgeladen", []):
        if eintrag.get("thumbnail") is True or not eintrag.get("oeffentlich_bestaetigt") or not eintrag.get("video_id"):
            continue
        versuche = eintrag.get("thumbnail_versuche") or 0
        if versuche >= THUMBNAIL_VERSUCHE_MAX:
            continue
        try:
            alter_min = (now - datetime.fromisoformat(eintrag["zeit"])).total_seconds() / 60
        except (KeyError, ValueError):
            continue
        if alter_min < THUMBNAIL_NACHTRAG_WARTE_MIN or alter_min > THUMBNAIL_NACHTRAG_FENSTER_MIN:
            continue
        ordner, mp4 = eintrag.get("ordner"), eintrag.get("mp4")
        if not ordner or not mp4 or not Path(mp4).exists():
            continue
        meta = _lesen(Path(ordner) / "shorts" / f"{eintrag['szene_id']}.json", None)
        ok = _thumbnail_setzen_versucht(eintrag["video_id"], Path(mp4), meta)
        eintrag["thumbnail"] = ok
        eintrag["thumbnail_versuche"] = versuche + 1
        ergebnisse.append({"video_id": eintrag["video_id"], "versuch": versuche + 1, "gesetzt": ok})
        geaendert = True
    if geaendert:
        _schreiben(VERLAUF_PFAD, verlauf)
    return {"versucht": len(ergebnisse), "ergebnisse": ergebnisse}


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
    a = p.parse_args()
    if a.cmd == "status":
        print(status_text())
        return
    if a.cmd == "thumbnail_nachtrag":
        print(json.dumps(thumbnail_nachtrag(), ensure_ascii=False))
        return
    erg = takt(trocken=a.trocken)
    print(json.dumps(erg, ensure_ascii=False))


if __name__ == "__main__":
    main()
