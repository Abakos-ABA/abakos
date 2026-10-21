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

from config.settings import NEWS_WELTLAGE_SHORTS_SLOTS, NEWS_YOUTUBE_CHANNEL_ID, STATE_DIR  # noqa: E402

QUEUE_PFAD = STATE_DIR / "weltlage_shorts_queue.json"
VERLAUF_PFAD = STATE_DIR / "weltlage_shorts_verlauf.json"
NACHTRAG_PFAD = STATE_DIR / "weltlage_shorts_nachtrag.json"
VIDEO_ID_IN_TEXT = re.compile(r"Upload ([A-Za-z0-9_-]{11}) nach")   # Text von UploadHaltedForReview (upload_datei)
FENSTER_MINUTEN = 110  # Toleranz je Slot (etwas unter 2 h, damit eine ausgefallene Stunden-Runde noch nachholt,
                        # aber niemals zwei Slots verschmelzen - die Wache laeuft stuendlich)
def _thumbnail_bild_bereitstellen(szene_id: str, titel: str | None, ordner, meta: dict | None = None,
                                  log=print) -> Path | None:
    """Liefert das komponierte Thumbnail (tools/weltlage_shorts_thumbnail.fuer_short) passend zum AKTUELLEN
    Titel des Shorts und rendert es bei Bedarf neu (reines Pillow, kein GPU/Netz, ~1 s).

    Befund 19.10.2026 (Task 20261019-193153-93d4, vierter Anlauf "Shorts ohne Thumbnail"), zwei Faelle:
    (a) ZkkmGOjf68w (Short vom 14.10., vor Einfuehrung des komponierten Bilds) hatte kein meta['thumbnail'];
        der Nachtrag fiel sechsmal auf den rohen ffmpeg-Titelkarten-Frame zurueck, lud den "erfolgreich" hoch
        (genau dieses Bild war dann auch live: sardefault.jpg zeigte den Frame mit Titelband) und zaehlte das als
        erschoepfte Versuche - die Wache meldete "haengt", obwohl schlicht das falsche Bild gesetzt wurde.
    (b) Titel koennen sich nach dem Schnitt noch aendern (Titel-Kollisions-Fix 18.10., eigene Nachtrag-Titel,
        Kanal-Manager-Experimente) - das Bild wuerde dann einen anderen Text zeigen als der Titel.
    Darum: Sidecar <szene_id>_thumb.json merkt sich, fuer welchen Titel das Bild gerendert wurde; fehlt das
    Bild, der Sidecar oder weicht der Titel ab, wird neu gerendert. Nie mehr Rueckfall auf einen Videoframe."""
    ordner = Path(ordner) if ordner else None
    titel = (titel or (meta or {}).get("title") or "").strip()
    eigenes = Path(meta["thumbnail"]) if meta and meta.get("thumbnail") else None
    if eigenes is not None and not eigenes.is_absolute():
        eigenes = ROOT / eigenes
    if ordner is not None:
        ziel = ordner / "shorts" / f"{szene_id}_thumb.jpg"
    elif eigenes is not None:
        ziel = eigenes
    else:
        return None
    sidecar = ziel.with_suffix(".json")
    if ziel.exists():
        try:
            if json.loads(sidecar.read_text(encoding="utf-8")).get("titel") == titel:
                return ziel
        except (OSError, ValueError):
            pass
    try:
        from tools.weltlage_shorts_thumbnail import fuer_short
        m = dict(meta or {})
        m["title"] = titel
        fuer_short(m, ziel, ordner=ordner)
        sidecar.write_text(json.dumps({"titel": titel,
                                       "gerendert": datetime.now().astimezone().isoformat(timespec="seconds")},
                                      ensure_ascii=False), encoding="utf-8")
        log(f"Thumbnail: Komposit fuer {szene_id} gerendert ({ziel.name}, Titel: {titel[:60]})")
        return ziel
    except Exception as e:   # noqa: BLE001 - dann wenigstens das vorhandene Bild, aber nie ein Videoframe
        log(f"Thumbnail: Komposit fuer {szene_id} nicht renderbar ({type(e).__name__}: {e})")
        if ziel.exists():
            return ziel
        return eigenes if eigenes is not None and eigenes.exists() else None


THUMBNAIL_STUDIO_ANLAEUFE = 2        # Studio-Anlaeufe innerhalb EINES Versuchs (Edge-Zombie, Speicher-Request fehlt)
THUMBNAIL_ANLAUF_PAUSE_S = 20.0      # Pause zwischen zwei Anlaeufen


def _thumbnail_api_setzen(video_id: str, bild, log=print) -> dict | None:
    """Klickfreier Weg (seit 21.10.2026, Task 20261021-105909-286b): YouTube Data API thumbnails.set ueber
    upload.youtube_api, sobald die einmalige Einrichtung da ist (secrets/client_secret.json + youtube_token.json,
    `python -m upload.youtube_api --einrichten`). Braucht keinen Browser, kein Studio-Profil, keine Sperre. None =
    nicht eingerichtet oder fehlgeschlagen (dann Rueckfall auf Studio, nie ein Abbruch)."""
    try:
        from upload import youtube_api
        if not youtube_api.verfuegbar():
            return None
        res = youtube_api.thumbnail_setzen(video_id, str(bild))
    except Exception as e:   # noqa: BLE001 - Quota, Token abgelaufen, Netz: Studio bleibt der Rueckfall
        log(f"Thumbnail: {video_id} Data-API fehlgeschlagen ({type(e).__name__}: {str(e)[:160]}) - Rueckfall Studio")
        return None
    return {"versucht": True, "gespeichert": True, "studio_bestaetigt": True, "bild": str(bild), "weg": "api",
            "hinweis": (res or {}).get("hinweis") or "Data API thumbnails.set"}


def _thumbnail_setzen_versucht(video_id: str, mp4: Path, meta: dict | None = None, log=print,
                               titel: str | None = None, ordner=None, szene_id: str | None = None) -> dict:
    """Setzt das komponierte Thumbnail und gibt das Ergebnis als Dict zurueck: versucht (Dienst ueberhaupt
    erreicht), gespeichert (Speichern beantwortet), studio_bestaetigt (nach Neuladen sichtbar; None = nicht
    pruefbar), bild, weg ("api"|"studio"), hinweis. Reihenfolge seit 21.10.2026: (1) YouTube Data API, wenn
    eingerichtet (_thumbnail_api_setzen) - kein Browser; (2) sonst Studio ueber upload.youtube_playwright.
    set_thumbnail (seit 19.10.2026 deterministisch: wartet Upload und Speicher-Request ab, liest nach Neuladen
    zurueck), bei nicht gespeichertem Ergebnis oder einem Fehler, der nicht die belegte Profil-Sperre ist, bis zu
    THUMBNAIL_STUDIO_ANLAEUFE Anlaeufe mit Pause - zaehlt beim Aufrufer trotzdem als EIN Versuch.
    Fehlt das Komposit oder weicht sein Titel vom aktuellen ab, wird es vorher neu gerendert
    (_thumbnail_bild_bereitstellen). Wirft nie - z.B. eine belegte Profil-Sperre darf den Takt nicht scheitern
    lassen."""
    import time as _time
    mp4 = Path(mp4)
    szene_id = szene_id or mp4.stem
    if ordner is None and mp4.parent.name == "shorts":
        ordner = mp4.parents[1]
    bild = _thumbnail_bild_bereitstellen(szene_id, titel, ordner, meta, log)
    if bild is None or not Path(bild).exists():
        return {"versucht": False, "gespeichert": False, "studio_bestaetigt": None, "bild": None,
                "hinweis": "kein komponiertes Thumbnail verfuegbar"}
    api = _thumbnail_api_setzen(video_id, bild, log)
    if api:
        log(f"Thumbnail: {video_id} per Data API gesetzt ({Path(bild).name})")
        return api
    letztes: dict = {"versucht": False, "gespeichert": False, "studio_bestaetigt": None, "bild": str(bild),
                     "weg": "studio", "hinweis": ""}
    for anlauf in range(1, THUMBNAIL_STUDIO_ANLAEUFE + 1):
        try:
            from upload.youtube_playwright import set_thumbnail
            res = set_thumbnail(video_id, str(bild))
        except Exception as e:   # noqa: BLE001 - z.B. Profil-Sperre belegt, nie den Takt scheitern lassen
            log(f"Thumbnail: {video_id} nicht gesetzt ({type(e).__name__}: {e})")
            letztes = {"versucht": False, "gespeichert": False, "studio_bestaetigt": None, "bild": str(bild),
                       "weg": "studio", "hinweis": f"{type(e).__name__}: {str(e)[:200]}"}
            if "belegt" in str(e) or anlauf >= THUMBNAIL_STUDIO_ANLAEUFE:
                return letztes   # Sperre schon bis zur Wartegrenze belegt: nicht noch einmal 30 min warten
            _time.sleep(THUMBNAIL_ANLAUF_PAUSE_S)
            continue
        if not isinstance(res, dict):   # aeltere/fremde set_thumbnail-Fassung ohne Rueckgabe
            res = {"gespeichert": True, "studio_bestaetigt": None, "hinweis": "ohne Rueckkontrolle"}
        letztes = {"versucht": True, "gespeichert": bool(res.get("gespeichert")),
                   "studio_bestaetigt": res.get("studio_bestaetigt"), "bild": str(bild), "weg": "studio",
                   "hinweis": res.get("hinweis") or ""}
        log(f"Thumbnail: {video_id} Studio-Lauf {anlauf}/{THUMBNAIL_STUDIO_ANLAEUFE}: "
            f"gespeichert={letztes['gespeichert']} studio_bestaetigt={letztes['studio_bestaetigt']} "
            f"({Path(bild).name}) {letztes['hinweis']}".rstrip())
        if letztes["gespeichert"] or anlauf >= THUMBNAIL_STUDIO_ANLAEUFE:
            return letztes
        _time.sleep(THUMBNAIL_ANLAUF_PAUSE_S)
    return letztes


def _frage_kommentar_setzen(video_id: str, ordner: str | None, log=print) -> bool:
    """Postet die Kommentarfrage der ZUGEHOERIGEN Folge (metadaten.json["kommentarfrage"] im Folgenordner,
    gleiche Quelle wie fuer die lange Folge selbst) als eigenen, angehefteten Kommentar unter dem Short -
    ein Short zeigt nur einen Ausschnitt derselben Folge, die Frage bleibt also inhaltlich passend. Fehlt
    der Ordner/die Datei/das Feld, wird nichts gepostet (kein Fehler, nur kein Zusatznutzen); ein Fehlschlag
    beim Posten selbst darf den Takt nie gefaehrden (Short ist bereits veroeffentlicht)."""
    if not ordner:
        return False
    try:
        meta = json.loads((Path(ordner) / "metadaten.json").read_text(encoding="utf-8"))
        frage = (meta.get("kommentarfrage") or "").strip()
        if not frage:
            return False
        from upload.youtube_kommentar import frage_kommentar_posten
        ok = frage_kommentar_posten(video_id, frage)
        log(f"Frage-Kommentar Short {video_id}: {'gepostet+angeheftet' if ok else 'FEHLGESCHLAGEN'}")
        return ok
    except Exception as e:   # noqa: BLE001
        log(f"Frage-Kommentar Short {video_id}: FEHLER ({type(e).__name__}: {e})")
        return False


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


VERWAISTER_UPLOAD_MAX_STD = 12


def _verwaister_upload(log_pfad: Path, bekannte_ids: set[str], now: datetime) -> dict | None:
    """Befund 21.10.2026 (Task 20261021-065618-c914): wird der Takt-Prozess mitten im Upload beendet (Worker-
    Timeout), steht das Video schon bei YouTube (Video-ID im Upload-Log), aber weder Warteschlange noch Verlauf
    wissen davon - der naechste Slot lud dieselbe Datei ein zweites Mal hoch (Duplikat ECzVpvXEpoY/MnePPAJE0Ug).
    Liest darum das Upload-Log der Szene: eine juengere Video-ID (< VERWAISTER_UPLOAD_MAX_STD h), die noch nicht im
    Verlauf steht, wird uebernommen statt neu hochgeladen. Rueckgabe wie upload_datei (video_id,
    oeffentlich_bestaetigt, studio_status), sonst None."""
    try:
        zeilen = Path(log_pfad).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    vid, zeit = None, None
    for i, z in enumerate(zeilen):
        m = re.match(r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) Video-ID: ([A-Za-z0-9_-]{11})(?![A-Za-z0-9_-])", z)
        if m:
            vid, zeit, start = m.group(2), m.group(1), i
    if not vid or vid in bekannte_ids:
        return None
    try:
        alter_h = (now.replace(tzinfo=None) - datetime.strptime(zeit, "%Y-%m-%d %H:%M:%S")).total_seconds() / 3600
    except ValueError:
        return None
    if alter_h > VERWAISTER_UPLOAD_MAX_STD:
        return None
    public = any(f"Studio-Status {vid}: PUBLIC" in z for z in zeilen[start:])
    return {"video_id": vid, "oeffentlich_bestaetigt": public, "studio_status": "PUBLIC" if public else None,
            "nachzug_fehler": None if public else "verwaister Upload uebernommen, Studio-Bestaetigung unklar"}


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
    log_pfad = Path(eintrag["ordner"]) / "shorts" / f"{eintrag['szene_id']}_upload.log"
    bekannte = {e.get("video_id") for e in verlauf.get("hochgeladen", [])}
    try:
        res = _verwaister_upload(log_pfad, bekannte, now)
        if res is None:
            res = upload_datei(mp4, eintrag["meta"], None, visibility="public", log_path=log_pfad)
        else:
            print(f"Verwaister Upload {res['video_id']} im Log gefunden - uebernommen, kein zweiter Upload")
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
    # Befund 21.10.2026 (Task 20261021-065618-c914): der Verlaufseintrag wurde erst NACH Thumbnail-Setzen und
    # Frage-Kommentar (zusammen Minuten) geschrieben. Wurde der Takt-Prozess in dieser Zeit beendet (Worker-
    # Timeout, Neustart), war der Short live, aber nicht im Verlauf - thumbnail_nachtrag() kennt nur Verlaufs-
    # eintraege und hat ihn nie geprueft (Pentagon-Short 02OUSEsRRK4 blieb ohne Thumbnail). Darum zuerst den
    # Eintrag sichern, dann die langsamen Schritte.
    eintrag_neu = {"szene_id": eintrag["szene_id"], "video_id": res.get("video_id"),
                   "zeit": now.isoformat(timespec="seconds"), "key": eintrag["key"],
                   "titel": eintrag["meta"]["title"],
                   "oeffentlich_bestaetigt": bestaetigt,
                   "studio_status": res.get("studio_status"),
                   "fehler": res.get("nachzug_fehler"),
                   "thumbnail": False, "thumbnail_versuche": 0, "thumbnail_letzter_versuch": None,
                   "frage_kommentar_ok": None,
                   "ordner": eintrag.get("ordner"), "mp4": str(mp4)}
    verlauf.setdefault("hochgeladen", []).append(eintrag_neu)
    verlauf["hochgeladen"] = verlauf["hochgeladen"][-200:]
    verlauf.setdefault("erledigte_slots", []).append(schluessel)
    verlauf["erledigte_slots"] = verlauf["erledigte_slots"][-60:]
    _schreiben(VERLAUF_PFAD, verlauf)
    if thumbnail_versucht:
        _thumbnail_setzen_versucht(res["video_id"], mp4, eintrag.get("meta"), titel=eintrag["meta"].get("title"),
                                   ordner=eintrag.get("ordner"), szene_id=eintrag["szene_id"])
        eintrag_neu["thumbnail_versuche"] = 1
        eintrag_neu["thumbnail_letzter_versuch"] = now.isoformat(timespec="seconds")
        _schreiben(VERLAUF_PFAD, verlauf)
    if bestaetigt and res.get("video_id"):
        eintrag_neu["frage_kommentar_ok"] = _frage_kommentar_setzen(res["video_id"], eintrag.get("ordner"))
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
        _thumbnail_setzen_versucht(res["video_id"], mp4, eintrag.get("meta"), titel=eintrag["meta"].get("title"),
                                   ordner=eintrag.get("ordner"), szene_id=eintrag["szene_id"])
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


BANDEROLE_MIN_LAUF = 20   # Mindestbreite (Pixel) eines zusammenhaengenden Banderole-Treffers (Rueckfall-Heuristik)
VERGLEICH_SEITE = 48      # Kantenlaenge fuer den direkten Bildvergleich (graustufig, klein skaliert)
# Schwelle fuer den direkten Vergleich, kalibriert 19.10.2026 an echten sardefault.jpg-Bildern: dasselbe
# Komposit nach YouTubes Neukodierung lag bei mittlerer Pixeldifferenz < 1.5, ein anderer Text im selben Layout
# oder ein roher Videoframe bei > 8 - 4.0 trennt beides mit Abstand nach beiden Seiten.
VERGLEICH_SCHWELLE = 4.0
THUMBNAIL_REGAL_WARN_MIN = 120   # ein Short, der so lange nach Upload im Regal noch ohne eigenes Bild ist, wird gemeldet
THUMBNAIL_CDN_NACHWARTEN_S = 15  # nach bestaetigtem Studio-Speichern kurz warten, bis das CDN das Bild hat (gemessen <60 s)
THUMBNAIL_STUDIO_MAX_PRO_LAUF = 4   # Studio-Laeufe je Nachtrag-Aufruf (je ~2-3 min; die Wache kappt den Unterprozess
                                    # nach 20 min, Vorfall 19.10.2026: fuenf Shorts am Stueck liefen in den Timeout)


def _bilder_stimmen_ueberein(live, lokal) -> bool:
    """Reiner Bildvergleich ohne Netz (offline testbar): beide Bilder graustufig auf VERGLEICH_SEITE skaliert,
    mittlere Pixeldifferenz gegen VERGLEICH_SCHWELLE. live/lokal: PIL-Bilder."""
    a = live.convert("L").resize((VERGLEICH_SEITE, VERGLEICH_SEITE))
    b = lokal.convert("L").resize((VERGLEICH_SEITE, VERGLEICH_SEITE))
    diff = sum(abs(x - y) for x, y in zip(a.getdata(), b.getdata())) / (VERGLEICH_SEITE ** 2)
    return diff < VERGLEICH_SCHWELLE


def _thumbnail_live_sichtbar(video_id: str, lokal=None, log=print, url: str | None = None) -> bool | None:
    """Objektive Pruefung OHNE Playwright/Studio, ob das komponierte Thumbnail auf YouTube wirklich sichtbar ist.

    Befund 19.10.2026 (Task 20261019-193153-93d4): das Shorts-Regal der Kanalseite (youtube.com/channel/<id>/
    shorts, ytInitialData) zeigt pro Short entweder `sardefault.jpg` (= das eigene, in Studio gesetzte Bild,
    1080x1920) oder - wenn keins gesetzt ist - einen der automatisch gewaehlten Videoframes `oar1|oar2|oar3.jpg`.
    Das bisher geprueft hqdefault.jpg (16:9) ist nur eine Ableitung davon; sardefault.jpg ist die Datei, die
    Marlon im Regal sieht, und fehlt (HTTP 404), solange gar kein eigenes Bild gesetzt ist. CDN-Cache: max-age
    7200 s, d.h. ein neu gesetztes Bild ist spaetestens nach 2 h hier sichtbar (gemessen: unter einer Minute).

    Ist das erwartete lokale Bild (lokal) bekannt, zaehlt nur ein direkter Bildvergleich - so faellt auch ein
    veraltetes Komposit mit altem Titel auf (Fall SAzJwxfnLwE). Ohne lokales Bild bleibt die aeltere Heuristik
    (durchgezogene Banderole ueber die ganze Bildhoehe, _laengster_banderole_lauf). Rueckgabe None nur, wenn das
    CDN gerade nicht erreichbar ist (kein Urteil); 404 heisst eindeutig "kein eigenes Bild" -> False.

    url: optional die versionierte Bild-URL aus dem Shorts-Regal (sardefault.jpg?sqp=…, siehe shorts_regal_lesen).
    Wird ein schon vorhandenes eigenes Bild ERSETZT, liefert die nackte CDN-URL bis zu 2 h das alte Bild aus dem
    Edge-Cache (Befund ZkkmGOjf68w 19.10.2026: Age 1996 s, altes Bild), waehrend das Regal die neue, versionierte
    URL verlinkt - die zaehlt dann."""
    import io
    import urllib.error
    import urllib.request

    from PIL import Image

    url = url or f"https://i.ytimg.com/vi/{video_id}/sardefault.jpg"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            daten = r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            log(f"Thumbnail-Live-Pruefung {video_id}: kein eigenes Bild gesetzt (sardefault.jpg 404)")
            return False
        log(f"Thumbnail-Live-Pruefung {video_id}: sardefault.jpg nicht abrufbar (HTTP {e.code})")
        return None
    except (urllib.error.URLError, OSError) as e:
        log(f"Thumbnail-Live-Pruefung {video_id}: sardefault.jpg nicht abrufbar ({e})")
        return None
    try:
        bild = Image.open(io.BytesIO(daten)).convert("RGB")
    except Exception as e:   # noqa: BLE001 - defektes/leeres Bild zaehlt als "jetzt nicht pruefbar"
        log(f"Thumbnail-Live-Pruefung {video_id}: Bild nicht lesbar ({e})")
        return None
    if bild.width < 300:   # YouTubes 120x90-Platzhalter = kein eigenes Bild
        log(f"Thumbnail-Live-Pruefung {video_id}: nur Platzhalter {bild.size}, kein eigenes Bild")
        return False
    if lokal is not None and Path(lokal).exists():
        try:
            gleich = _bilder_stimmen_ueberein(bild, Image.open(lokal))
        except Exception as e:   # noqa: BLE001
            log(f"Thumbnail-Live-Pruefung {video_id}: lokales Bild nicht lesbar ({e})")
            gleich = None
        if gleich is not None:
            log(f"Thumbnail-Live-Pruefung {video_id}: "
                f"{'komponiertes Bild live (Bildvergleich)' if gleich else 'live ein ANDERES Bild als erwartet'}")
            return gleich
    bester_lauf, beste_y = _laengster_banderole_lauf(bild)
    sichtbar = bester_lauf >= BANDEROLE_MIN_LAUF
    log(f"Thumbnail-Live-Pruefung {video_id}: "
        f"{'komponiertes Bild erkannt' if sichtbar else 'noch alter Frame/unbekannt'} "
        f"(laengster Banderole-Lauf {bester_lauf}px bei y={beste_y})")
    return sichtbar


def _laengster_banderole_lauf(bild) -> tuple[int, int | None]:
    """Rueckfall-Heuristik ohne lokales Vergleichsbild: sucht ueber das GANZE Bild zeilenweise den laengsten
    zusammenhaengenden Lauf an Pixeln in Banderole-Farbe (hell, deutlich mehr Rot als Blau) - die Banderole-Zeile
    sitzt je nach Headline-Laenge unterschiedlich hoch (Befund 18.10.2026). Grosse Bilder werden vorher auf 480 px
    Breite verkleinert (sardefault.jpg ist 1080x1920, die Pixelschleife waere sonst langsam)."""
    if bild.width > 480:
        bild = bild.resize((480, round(bild.height * 480 / bild.width)))
    w, h = bild.size
    bester, beste_y = 0, None
    px = bild.load()
    for y in range(h):
        lauf = 0
        for x in range(w):
            r, g, b = px[x, y][:3]
            if r > 150 and r - b > 60:
                lauf += 1
                if lauf > bester:
                    bester, beste_y = lauf, y
            else:
                lauf = 0
    return bester, beste_y


REGAL_BILD = re.compile(r"i\.ytimg\.com/vi/([A-Za-z0-9_-]{11})/(sardefault|oardefault|oar\d)\.jpg")
REGAL_BILD_URL = re.compile(r"https://i\.ytimg\.com/vi/([A-Za-z0-9_-]{11})/sardefault\.jpg\?sqp=[^\"\\s]+")


def shorts_regal_auswerten(html: str, urls: dict | None = None) -> dict[str, str]:
    """Liest aus dem HTML der Kanal-Shorts-Seite (ytInitialData), welches Bild das Shorts-Regal je Video zeigt:
    'sardefault' = eigenes gesetztes Bild, 'oar1'/'oar2'/'oar3'/'oardefault' = automatisch gewaehlter Videoframe.
    frame0.jpg (Poster des Players, immer der erste Videoframe) zaehlt bewusst nicht. urls (optional, wird
    gefuellt): je Video die versionierte sardefault-URL (…?sqp=…) des Regals - umgeht den CDN-Edge-Cache der
    nackten URL, siehe _thumbnail_live_sichtbar."""
    regal: dict[str, str] = {}
    for vid, art in REGAL_BILD.findall(html or ""):
        if art == "sardefault" or vid not in regal:
            regal[vid] = art
    if urls is not None:
        for m in REGAL_BILD_URL.finditer(html or ""):
            urls.setdefault(m.group(1), m.group(0).replace("\u0026", "&"))
    return regal


def shorts_regal_lesen(kanal_id: str | None = None, log=print, urls: dict | None = None) -> dict[str, str] | None:
    """Holt das echte Shorts-Regal der Kanalseite (das, was Marlon sieht) und gibt {video_id: Bildart} zurueck,
    siehe shorts_regal_auswerten. None, wenn die Seite nicht abrufbar ist. Nur die vordersten Shorts stehen im
    ersten Seitenabruf (rund 20-30, reicht fuer die Nachkontrolle der letzten Tage)."""
    import urllib.error
    import urllib.request

    kanal_id = kanal_id or NEWS_YOUTUBE_CHANNEL_ID
    if not kanal_id:
        return None
    url = f"https://www.youtube.com/channel/{kanal_id}/shorts"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "de-CH,de;q=0.9",
                                               "Cookie": "CONSENT=YES+1; SOCS=CAI"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            html = r.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError) as e:
        log(f"Shorts-Regal nicht abrufbar ({e})")
        return None
    return shorts_regal_auswerten(html, urls)


def thumbnail_nachtrag(now: datetime | None = None, regal: dict[str, str] | None = None) -> dict:
    """Pflegt das Thumbnail-Setzen fuer alle Shorts nach, bei denen es (noch) nicht live bestaetigt ist. Pro
    Short: (1) billige, objektive Live-Pruefung am CDN-Bild sardefault.jpg per Bildvergleich mit dem erwarteten
    Komposit (_thumbnail_live_sichtbar) - stimmt es, ist der Short erledigt, ohne Studio/Playwright; (2) sonst
    hoechstens alle THUMBNAIL_STUDIO_WIEDERHOLEN_MIN erneut bei Studio setzen (nie mehr als
    THUMBNAIL_VERSUCHE_MAX echte Studio-Laeufe). Stuendlich von der Weltlage-Wache aufgerufen, idempotent.

    'thumbnail' im Verlauf ist ausschliesslich die LIVE-bestaetigte Wahrheit (Befund 16.10.2026). 'haengt'
    listet erschoepfte, weiterhin nicht sichtbare Videos (Befund 18.10.2026).

    Seit 19.10.2026 (Task 20261019-193153-93d4): (a) gezaehlt werden nur echte Studio-Laeufe (versucht=True),
    nicht z.B. eine belegte Profil-Sperre; (b) nach einem von Studio bestaetigten Speichern wird das CDN gleich
    nachgeprueft (gemessen: Bild in unter einer Minute da), statt eine Stunde zu warten; (c) zusaetzlich wird das
    echte Shorts-Regal der Kanalseite gelesen ('regal'): zeigt es fuer einen Short aelter als
    THUMBNAIL_REGAL_WARN_MIN noch einen automatischen Videoframe (oarN) statt des eigenen Bilds, landet er in
    'regal_ohne_bild' (Wache meldet) - und ein frueher bestaetigter Short, der dort wieder ohne eigenes Bild
    steht, wird auf unbestaetigt zurueckgesetzt und automatisch neu gesetzt."""
    import time as _time
    now = now or datetime.now().astimezone()
    verlauf = _lesen(VERLAUF_PFAD, {"hochgeladen": [], "erledigte_slots": []})
    ergebnisse = []
    haengt = []
    regal_ohne_bild = []
    geaendert = False
    studio_laeufe = 0
    regal_urls: dict[str, str] = {}
    if regal is None:
        regal = shorts_regal_lesen(urls=regal_urls)
    for eintrag in verlauf.get("hochgeladen", []):
        if eintrag.get("geloescht") or not eintrag.get("oeffentlich_bestaetigt") or not eintrag.get("video_id"):
            continue
        try:
            alter_min = (now - datetime.fromisoformat(eintrag["zeit"])).total_seconds() / 60
        except (KeyError, ValueError):
            continue
        vid = eintrag["video_id"]
        im_regal = (regal or {}).get(vid)
        if im_regal and im_regal != "sardefault":
            if alter_min >= THUMBNAIL_REGAL_WARN_MIN:
                regal_ohne_bild.append({"video_id": vid, "titel": eintrag.get("titel"), "regal": im_regal,
                                        "versuche": eintrag.get("thumbnail_versuche") or 0})
            if eintrag.get("thumbnail") is True:
                # frueher bestaetigt, jetzt im Regal ohne eigenes Bild -> Selbstheilung statt stiller Rueckfall
                eintrag["thumbnail"] = False
                eintrag["thumbnail_versuche"] = 0
                eintrag["thumbnail_letzter_versuch"] = None
                eintrag["thumbnail_rueckfall"] = now.isoformat(timespec="seconds")
                geaendert = True
                ergebnisse.append({"video_id": vid, "regal_rueckfall": im_regal})
        if eintrag.get("thumbnail") is True:
            continue
        if alter_min < THUMBNAIL_NACHTRAG_WARTE_MIN:
            continue
        ordner, mp4 = eintrag.get("ordner"), eintrag.get("mp4")
        meta = _lesen(Path(ordner) / "shorts" / f"{eintrag['szene_id']}.json", None) if ordner else None
        erwartet = (_thumbnail_bild_bereitstellen(eintrag["szene_id"], eintrag.get("titel"), ordner, meta)
                    if ordner else None)
        live = _thumbnail_live_sichtbar(vid, lokal=erwartet, url=regal_urls.get(vid))
        if live:
            eintrag["thumbnail"] = True
            ergebnisse.append({"video_id": vid, "live_bestaetigt": True})
            geaendert = True
            continue
        versuche = eintrag.get("thumbnail_versuche") or 0
        if versuche >= THUMBNAIL_VERSUCHE_MAX:
            haengt.append({"video_id": vid, "titel": eintrag.get("titel"), "versuche": versuche})
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
        if not ordner or not mp4 or not Path(mp4).exists():
            continue
        if studio_laeufe >= THUMBNAIL_STUDIO_MAX_PRO_LAUF:
            ergebnisse.append({"video_id": vid, "verschoben": "Studio-Budget dieses Laufs erschoepft"})
            continue
        studio_laeufe += 1
        res = _thumbnail_setzen_versucht(vid, Path(mp4), meta, titel=eintrag.get("titel"), ordner=ordner,
                                         szene_id=eintrag["szene_id"])
        if not isinstance(res, dict):   # aeltere Test-Doubles liefern bool
            res = {"versucht": True, "gespeichert": bool(res), "studio_bestaetigt": None}
        erg = {"video_id": vid, "versuch": versuche + (1 if res.get("versucht") else 0),
               "studio_gesetzt": bool(res.get("gespeichert")), "studio_bestaetigt": res.get("studio_bestaetigt"),
               "live_bestaetigt": False, "weg": res.get("weg")}
        if res.get("hinweis"):
            erg["hinweis"] = res["hinweis"]
        if res.get("versucht"):
            eintrag["thumbnail_versuche"] = versuche + 1
            eintrag["thumbnail_letzter_versuch"] = now.isoformat(timespec="seconds")
            geaendert = True
            if res.get("gespeichert") and res.get("studio_bestaetigt"):
                _time.sleep(THUMBNAIL_CDN_NACHWARTEN_S)
                if _thumbnail_live_sichtbar(vid, lokal=res.get("bild")):
                    eintrag["thumbnail"] = True
                    erg["live_bestaetigt"] = True
        ergebnisse.append(erg)
    if geaendert:
        _schreiben(VERLAUF_PFAD, verlauf)
    # Seit 21.10.2026 (Task 20261021-105909-286b): Alarm nur, wenn auch die Reparatur scheitert - ein Short, dessen
    # Bild in diesem Lauf gesetzt und live bestaetigt wurde, verschwindet aus regal_ohne_bild; 'repariert' nennt
    # die Wache nur im Tagesbericht.
    jetzt_live = {e["video_id"] for e in ergebnisse if e.get("live_bestaetigt")}
    regal_ohne_bild = [h for h in regal_ohne_bild if h["video_id"] not in jetzt_live]
    repariert = [{"video_id": e["video_id"], "weg": e.get("weg")} for e in ergebnisse
                 if e.get("live_bestaetigt") and e.get("versuch")]
    return {"versucht": len(ergebnisse), "ergebnisse": ergebnisse, "haengt": haengt,
            "regal_gelesen": regal is not None, "regal_ohne_bild": regal_ohne_bild, "repariert": repariert}


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
