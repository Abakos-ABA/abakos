#!/usr/bin/env python
"""Einmal-Werkzeug: setzt das neue komponierte Shorts-Thumbnail (tools/weltlage_shorts_thumbnail.py) auf
bereits veroeffentlichte Weltlage-Shorts nachtraeglich (rexemres Auftrag 15.10.2026, analog zum Fund beim
Jarvis-KI-Kanal: kein eigenes Vorschaubild, YouTube/ffmpeg zeigte nur einen rohen Videoframe, die Kachelansicht
schnitt oben/unten je rund ein Viertel ab).

Quelle der Videoliste: state/weltlage_shorts_verlauf.json - die einzige Aufzeichnung aller bisher von dieser
Pipeline hochgeladenen Shorts. Vor dem Setzen wird jeder Eintrag per oEmbed frisch gegen den echten YouTube-
Stand geprueft (eigener Treffer statt sich blind auf den - unter Umstaenden veralteten - lokalen Verlauf zu
verlassen), damit kein geloeschtes/privates Video getroffen wird; das oEmbed-Ergebnis liefert gleich auch die
bisherige Thumbnail-URL fuer den Vorher-Vergleich.

    python -m tools.weltlage_shorts_thumbnail_backfill [--trocken]
"""
from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config.settings import DATA_DIR, STATE_DIR  # noqa: E402

VERLAUF_PFAD = STATE_DIR / "weltlage_shorts_verlauf.json"

# Kanal-Aenderungsprotokoll (jarvis-Repo tools/kanal_protokoll.py): Cross-Repo-Import gegen den LIVE-Jarvis-
# Ordner wie tools/weltlage_kanalmanager.py es bereits tut - fehlt das Modul, bleibt der Eintrag folgenlos.
_JARVIS_TOOLS = Path(r"C:\Users\USER\projekte\jarvis\tools")


def _kanal_protokoll():
    if str(_JARVIS_TOOLS) not in sys.path:
        sys.path.insert(0, str(_JARVIS_TOOLS))
    import kanal_protokoll
    return kanal_protokoll


def _ordner_aus_key(key: str) -> Path | None:
    """key steht in zwei Formaten im Verlauf (aelterer Befund, nicht Teil dieser Aufgabe): entweder schon
    'weltlage_20261013_1100' oder '2026-10-14_11:00' - beide zeigen auf denselben Folgenordner
    data/weltlage_<JJJJMMTT>_<HHMM>. Nur fuer das Thema-Schlagwort (Banderole) der Folge gebraucht, nicht
    zwingend fuer den themenbezogenen Text selbst (der ist schon der Short-Titel aus dem Verlauf)."""
    if re.match(r"^weltlage_\d{8}_\d{4}$", key or ""):
        ordner = DATA_DIR / key
        return ordner if ordner.is_dir() else None
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})_(\d{2}):(\d{2})$", key or "")
    if m:
        j, mo, t, hh, mm = m.groups()
        ordner = DATA_DIR / f"weltlage_{j}{mo}{t}_{hh}{mm}"
        return ordner if ordner.is_dir() else None
    return None


def _oembed(video_id: str) -> dict | None:
    url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except (urllib.error.HTTPError, urllib.error.URLError, ValueError):
        return None


def kandidaten() -> list[dict]:
    verlauf = json.loads(VERLAUF_PFAD.read_text(encoding="utf-8"))
    return [e for e in (verlauf.get("hochgeladen") or []) if e.get("video_id")]


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--trocken", action="store_true", help="nur bauen und oEmbed pruefen, nicht auf YouTube setzen")
    a = p.parse_args()

    from tools.weltlage_shorts_thumbnail import fuer_short
    from upload.youtube_playwright import set_thumbnail

    ziel_dir = STATE_DIR / "tmp" / "shorts_thumbnail_backfill"
    ziel_dir.mkdir(parents=True, exist_ok=True)
    ergebnisse = []
    for e in kandidaten():
        vid, titel = e["video_id"], e.get("titel") or ""
        print(f"=== {vid}: {titel}")
        info = _oembed(vid)
        if info is None:
            print(f"  uebersprungen: {vid} ist gerade nicht oeffentlich per oEmbed abrufbar "
                  f"(geloescht/privat/noch nicht bestaetigt?)")
            continue
        print(f"  oEmbed bestaetigt: {info.get('title', '')[:80]!r}")
        vorher_jpg = ziel_dir / f"{vid}_vorher.jpg"
        vorher_url = info.get("thumbnail_url")
        if vorher_url:
            try:
                urllib.request.urlretrieve(vorher_url, vorher_jpg)
            except OSError as ex:
                print(f"  Vorher-Bild nicht geladen: {ex}")
                vorher_jpg = None
        else:
            vorher_jpg = None
        ordner = _ordner_aus_key(e.get("key") or "")
        nachher_jpg = fuer_short({"title": titel}, ziel_dir / f"{vid}_nachher.jpg", ordner=ordner)
        print(f"  neues Thumbnail gebaut: {nachher_jpg}")
        gesetzt, fehler = False, None
        if not a.trocken:
            try:
                set_thumbnail(vid, str(nachher_jpg), debug_dir=str(ziel_dir))
                gesetzt = True
                print(f"  gesetzt auf https://youtu.be/{vid}")
            except Exception as ex:  # noqa: BLE001 - ein instabiles Studio bei einem Video darf die
                # anderen Videos der Stapelverarbeitung nicht verhindern (analog jarvis_kanal_cta_nachtrag.py)
                fehler = f"{type(ex).__name__}: {ex}"
                print(f"  FEHLER beim Setzen (uebersprungen, weiter mit dem naechsten Video): {fehler}")
        ergebnisse.append({"video_id": vid, "titel": titel, "vorher": str(vorher_jpg) if vorher_jpg else None,
                           "nachher": str(nachher_jpg), "gesetzt": gesetzt, "fehler": fehler})
    (ziel_dir / "ergebnis.json").write_text(json.dumps(ergebnisse, ensure_ascii=False, indent=1),
                                            encoding="utf-8")
    gesetzt_n = sum(1 for r in ergebnisse if r["gesetzt"])
    print(f"\n{gesetzt_n} von {len(ergebnisse)} gesetzt. Ergebnis: {ziel_dir / 'ergebnis.json'}")
    if not a.trocken and gesetzt_n:
        try:
            _kanal_protokoll().eintrag(
                kanal="weltlage", art="thumbnail",
                alt="zufaelliger/abgeschnittener Videoframe als Shorts-Vorschaubild",
                neu=f"komponiertes eigenes Shorts-Vorschaubild (Text + Latara-Bild) nachgetragen "
                    f"({gesetzt_n}/{len(ergebnisse)} Shorts erfolgreich)",
                video_ids=[r["video_id"] for r in ergebnisse if r["gesetzt"]],
                grund="Nachtrag des neuen Shorts-Thumbnails (tools/weltlage_shorts_thumbnail.py) bei schon "
                      "veroeffentlichten Shorts, analog zum fa92-Nachtrag beim Kanal Jarvis KI",
                ausloeser="weltlage_shorts_thumbnail_backfill.main")
        except Exception:  # noqa: BLE001 - Protokoll darf den Nachtrag selbst nie gefaehrden
            pass


if __name__ == "__main__":
    main()
