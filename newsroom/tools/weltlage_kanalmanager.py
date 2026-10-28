"""Weltlage Kompakt - taeglicher Kanal-Manager (rexemre 13.10.2026, Task 20261013-164355-df82).

Anders als die stuendliche Produktions-Wache (jarvis/tools/weltlage_wache.py, heilt abgebrochene Laeufe) kuemmert
sich dieses Modul einmal pro Tag um den KANAL selbst, nie um laufende Produktion:

  1. uploads_pruefen(): welche Folgen/Shorts sind in den letzten 24 h tatsaechlich hochgeladen worden (aus
     state/weltlage_tageslauf.json + state/weltlage_shorts_verlauf.json), welche erwarteten Slots fehlen. Reiner
     Befund - kein Eingriff, keine doppelte Heilung (das macht schon die Wache).
  2. analytics_abrufen(): liest YouTube Studio Analytics ueber dieselbe signierte Playwright-Sitzung wie der
     Uploader (upload.youtube_playwright._launch, gleiche Profil-Sperre). Kein OAuth/Data-API fuer diesen Kanal
     verfuegbar (client_secret.json fehlt, siehe newsroom/README.md) - darum Studio-Text per sprachunabhaengiger
     Regex wie beim Uploader (zwischendialog_art & Co.). Fehlt eine einzelne Zahl, bleibt sie None statt den Lauf
     abzubrechen; nur ein kompletter Fehlschlag (Seite/Kanal nicht erreichbar) wirft.
  3. strategie_ableiten(): reine, offline testbare Regel-Logik. Risikoarme Befunde (Titel/Beschreibung/Tags/
     Zeitpunkt/Thumbnail) werden von risikoarm_anwenden() SOFORT umgesetzt (set_metadata/set_thumbnail ueber
     upload.youtube_playwright) - aber nur, wenn eine Regel wirklich etwas Konkretes gefunden hat, nie geraten.
     Groessere Ideen (Aufbau, Stil, Stimme, Studio, Schnitt) werden NIE direkt uebernommen: hoechstens EIN
     Experiment gleichzeitig (experiment_vorschlagen/experiment_stand/experiment_antwort), rexemre antwortet per
     Telegram/Chat mit ja/nein - die Antwort kommt ueber jarvis/tools/weltlage_kanalmanager.py hierher
     (experiment-antwort), nie automatisch uebernommen ohne sein ja. Jede wirklich gesetzte Aenderung
     (risikoarm_anwenden) landet automatisch im Kanal-Aenderungsprotokoll des jarvis-Repos (tools/
     kanal_protokoll.py, Cross-Repo-Import gegen den LIVE-Jarvis-Ordner) - Vorher-Kennzahlen + 7-/28-Tage-
     Nachvergleich, damit sich spaeter erklaeren laesst, warum sich Zahlen veraendert haben.
  4. run() liefert ein JSON-Ergebnis; der Jarvis-Tagesauftrag baut daraus den kurzen Bericht fuer rexemre. run()
     holt dabei auch faellige 7-/28-Tage-Auswertungen aus dem Kanal-Aenderungsprotokoll nach (Feld
     "kanal_protokoll_auswertungen") - der Tagesauftrag nennt ein faelliges Ergebnis kurz im Bericht.

CLI:
    .venv\\Scripts\\python -m tools.weltlage_kanalmanager run [--trocken]
    .venv\\Scripts\\python -m tools.weltlage_kanalmanager experiment-antwort ja|nein
    .venv\\Scripts\\python -m tools.weltlage_kanalmanager status
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config.settings import (  # noqa: E402
    NEWS_WELTLAGE_SHORTS_SLOTS, NEWS_WELTLAGE_SLOTS, NEWS_YOUTUBE_CHANNEL_ID, STATE_DIR,
)

KANAL_DIR = STATE_DIR / "weltlage_kanalmanager"
VERLAUF_PFAD = KANAL_DIR / "analytics_verlauf.json"
EXPERIMENT_PFAD = KANAL_DIR / "experiment.json"
TAGESLAUF_PFAD = STATE_DIR / "weltlage_tageslauf.json"
SHORTS_VERLAUF_PFAD = STATE_DIR / "weltlage_shorts_verlauf.json"
MIN_MESSPUNKTE_FUER_MUSTER = 5     # unter dieser Anzahl taeglicher Snapshots keine automatische Anpassung

# Kanal-Aenderungsprotokoll (rexemre 15.10.2026, jarvis-Repo tools/kanal_protokoll.py): Cross-Repo-Import wie
# jarvis/tools/jarvis_kanal_broll.py es umgekehrt tut - immer gegen den LIVE-Jarvis-Ordner, nie ein Worktree.
# Fehlt das Modul (vor der ersten Uebernahme des jarvis-Zweigs, der es anlegt), bleibt das hier folgenlos.
_JARVIS_TOOLS = Path(r"C:\Users\USER\projekte\jarvis\tools")


def _kanal_protokoll():
    if str(_JARVIS_TOOLS) not in sys.path:
        sys.path.insert(0, str(_JARVIS_TOOLS))
    import kanal_protokoll
    return kanal_protokoll


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


def jetzt() -> datetime:
    return datetime.now().astimezone()


def _iso_parse(text: str | None):
    if not text:
        return None
    try:
        return datetime.fromisoformat(str(text))
    except ValueError:
        return None


# ------------------------------------------------------------------------ 1) Uploads der letzten 24 h (nur Befund)
def folgen_24h(laeufe: dict, now: datetime, fenster_h: float = 24) -> dict:
    """Veroeffentlichte Folgen seit `fenster_h`, erwartete Slots im selben Fenster aus NEWS_WELTLAGE_SLOTS."""
    seit = now - timedelta(hours=fenster_h)
    hochgeladen = []
    for key, e in (laeufe or {}).items():
        zeit = _iso_parse((e.get("upload") or {}).get("veroeffentlicht_um"))
        if zeit and seit <= zeit <= now:
            hochgeladen.append({"key": key, "video_id": e.get("video_id"), "zeit": zeit.isoformat(timespec="seconds")})
    erwartete_slots = []
    for tag_offset in (1, 0):
        tag = (now - timedelta(days=tag_offset)).date()
        for slot in NEWS_WELTLAGE_SLOTS:
            h, m = (int(x) for x in slot.split(":"))
            t = datetime(tag.year, tag.month, tag.day, h, m, tzinfo=now.tzinfo)
            if seit <= t <= now:
                erwartete_slots.append(f"{tag.isoformat()}_{slot}")
    gefundene = {h["key"] for h in hochgeladen}
    fehlend = [s for s in erwartete_slots if s not in gefundene]
    return {"erwartet": len(erwartete_slots), "hochgeladen": hochgeladen, "fehlend": fehlend}


def shorts_24h(verlauf: dict, now: datetime, fenster_h: float = 24) -> dict:
    """Hochgeladene Shorts seit `fenster_h` aus state/weltlage_shorts_verlauf.json (hochgeladen-Liste)."""
    seit = now - timedelta(hours=fenster_h)
    hochgeladen = []
    for e in (verlauf or {}).get("hochgeladen") or []:
        zeit = _iso_parse(e.get("zeit"))
        if zeit and seit <= zeit <= now:
            hochgeladen.append(e)
    slots = [s.strip() for s in (NEWS_WELTLAGE_SHORTS_SLOTS or "").split(",") if s.strip()]
    erwartet = round(fenster_h / 24 * len(slots)) if slots else 0
    return {"erwartet": erwartet, "hochgeladen": hochgeladen}


def uploads_pruefen(now: datetime | None = None) -> dict:
    now = now or jetzt()
    laeufe = _lesen(TAGESLAUF_PFAD, {})
    sv = _lesen(SHORTS_VERLAUF_PFAD, {"hochgeladen": []})
    return {"folgen": folgen_24h(laeufe, now), "shorts": shorts_24h(sv, now)}


# ------------------------------------------------------------------------ 2) YouTube Studio Analytics (Playwright)
def _zahl(text: str, muster: str) -> float | None:
    """Erste Zahl nach einem Kennzahl-Label. Studio mischt Formate (13.10.2026 live gegen den echten Kanal
    verifiziert): Zaehler wie Aufrufe/Abonnenten nutzen deutschen Tausenderpunkt (1.234) und Dezimalkomma
    (4,2 %), die Wiedergabezeit-Kachel aber einen Dezimalpunkt (2.4 = 2,4 Stunden, keine drei Nachkommastellen
    einer Tausendergruppe) - nur ein Punkt gefolgt von genau drei Ziffern gilt als Tausendertrenner."""
    m = re.search(muster, text, re.I)
    if not m:
        return None
    z = m.group(1).strip().replace(" ", "").replace(" ", "")
    vorzeichen = ""
    if z and z[0] in "+-":
        vorzeichen, z = z[0], z[1:]
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", z):
        z = z.replace(".", "")
    elif "," in z:
        z = z.replace(".", "").replace(",", ".")
    try:
        return float(vorzeichen + z)
    except ValueError:
        return None


# Studio folgt der Sprache des Google-Kontos (deutsch) - Muster und URL gegen eine echte Sitzung verifiziert
# (13.10.2026, Kanal Weltlage Kompakt): .../analytics/tab-overview/period-default zeigt "Aufrufe" (28-Tage-Summe),
# "Wiedergabezeit (Stunden)" (Zahl direkt danach, keine Einheit im Fliesstext) und "Abonnenten" mit der
# Veraenderung (+4) direkt danach - der aktuelle Gesamtstand steht hier nicht, darum eigenes Feldlabel.
# Impressionen/Klickrate stehen auf der Zuschauer-/Reichweite-Unterseite, noch nicht gelesen (siehe Modul-Doku).
_KENNZAHL_MUSTER = {
    "aufrufe": r"(?:Aufrufe|Views)\D{0,40}?([\d.,]+)",
    "wiedergabezeit_std": r"(?:Wiedergabezeit|Watch time)\D{0,40}?([\d.,]+)",
    "abonnenten_aenderung_28_tage": r"(?:Abonnenten|Subscribers)\D{0,20}?([+-][\d.,]+)",
}


def kennzahlen_aus_text(text: str) -> dict:
    """Reine Funktion (testbar ohne Browser): Kennzahlen aus dem sichtbaren Text der Studio-Analytics-Uebersicht."""
    return {name: _zahl(text, muster) for name, muster in _KENNZAHL_MUSTER.items()}


_INHALT_ZEILE = re.compile(r"^(\d{1,2})\n(.+)\n(?:.+\n){2,4}?(\d+)$", re.M)


def inhalte_tabelle(text: str) -> list[dict]:
    """Reine Funktion: die Tabelle 'Deine erfolgreichsten Inhalte in diesem Zeitraum' der Analytics-Uebersicht
    (schon nach Aufrufen absteigend sortiert - Studio tut das selbst) als Liste {rang, titel, aufrufe}. Best
    effort: findet Studio die Tabelle nicht (umgebaute Seite), liefert sie eine leere Liste statt abzustuerzen."""
    start = text.find("Durchschnittliche Wiedergabedauer")
    ende = text.find("Echtzeit", start) if start != -1 else -1
    if start == -1 or ende == -1:
        return []
    block = text[start:ende].split("Mehr anzeigen")[0]
    out = []
    for m in _INHALT_ZEILE.finditer(block):
        out.append({"rang": int(m.group(1)), "titel": m.group(2).strip(), "aufrufe": int(m.group(3))})
    return out


def analytics_abrufen(debug_dir: str | None = None) -> dict:
    """Kanal-Kennzahlen + Inhalte-Tabelle (Studio-Standardzeitraum, i.d.R. letzte 28 Tage) von der Analytics-
    Uebersicht. Nutzt die gleiche Profil-Sperre wie Uploads (upload.youtube_playwright._launch) - wartet notfalls,
    kollidiert nie mit einem laufenden Upload."""
    from playwright.sync_api import sync_playwright
    from config.settings import NEWS_PLAYWRIGHT_HEADLESS
    from upload.youtube_playwright import _launch, _switch_channel

    if not NEWS_YOUTUBE_CHANNEL_ID:
        raise RuntimeError("NEWS_YOUTUBE_CHANNEL_ID ist nicht gesetzt")
    shots = Path(debug_dir) if debug_dir else None
    url = (f"https://studio.youtube.com/channel/{NEWS_YOUTUBE_CHANNEL_ID}"
          f"/analytics/tab-overview/period-default?hl=en")
    letzter_fehler = None
    with sync_playwright() as p:
        for versuch in (1, 2):
            context = _launch(p, headless=NEWS_PLAYWRIGHT_HEADLESS)
            page = context.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_timeout(8000)
                if shots:
                    shots.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(shots / f"analytics_overview_{versuch}.png"), full_page=True)
                text = page.inner_text("body")
                if re.search(r"nicht berechtigt|don.t have permission", text, re.I):
                    # Profil zeigt ein anderes Kanal-Konto des Google-Kontos (wie beim Uploader, Vorfall
                    # 23.09.2026 Doku-Kanal) - einmal umschalten und frisch versuchen, bevor aufgegeben wird.
                    if versuch == 1:
                        _switch_channel(page)
                        continue
                    letzter_fehler = RuntimeError("Studio zeigt 'nicht berechtigt' auch nach Kanalwechsel")
                    continue
                kennzahlen = kennzahlen_aus_text(text)
                kennzahlen["inhalte"] = inhalte_tabelle(text)
                kennzahlen["abgerufen_um"] = jetzt().isoformat(timespec="seconds")
                return kennzahlen
            except Exception as e:   # noqa: BLE001 - zweiter Versuch mit frischem Browser (Playwright/Edge-Flattern)
                letzter_fehler = e
            finally:
                context.close()
    raise letzter_fehler or RuntimeError("Analytics-Abruf ohne erkennbaren Fehler fehlgeschlagen")


# ------------------------------------------------------------------------ 3) Strategie (reine Logik, testbar)
def strategie_ableiten(uploads: dict, analytics: dict, verlauf: list[dict]) -> dict:
    """Reine Funktion: baut aus Upload-Befund + aktuellen Kennzahlen + Verlauf Erkenntnisse und (sehr zurueckhaltend)
    risikoarme Vorschlaege. Erfindet nie ein Experiment - das bleibt expliziten, belastbaren Befunden vorbehalten."""
    erkenntnisse = []
    folgen, shorts = uploads.get("folgen", {}), uploads.get("shorts", {})
    if folgen.get("fehlend"):
        erkenntnisse.append(f"Fehlende Folgen-Slots der letzten 24 h: {', '.join(folgen['fehlend'])}")
    else:
        erkenntnisse.append(f"{len(folgen.get('hochgeladen', []))} von {folgen.get('erwartet', 0)} "
                            f"Folgen-Slots der letzten 24 h veroeffentlicht")
    erkenntnisse.append(f"{len(shorts.get('hochgeladen', []))} von {shorts.get('erwartet', 0)} "
                        f"Shorts-Slots der letzten 24 h hochgeladen")
    if analytics.get("fehler"):
        erkenntnisse.append(f"YouTube Analytics heute nicht lesbar: {analytics['fehler']}")
    else:
        if analytics.get("aufrufe") is not None:
            erkenntnisse.append(f"{int(analytics['aufrufe'])} Aufrufe (Studio-Standardzeitraum, i.d.R. 28 Tage)")
        if analytics.get("wiedergabezeit_std") is not None:
            erkenntnisse.append(f"{analytics['wiedergabezeit_std']:.1f} Stunden Wiedergabezeit im selben Zeitraum")
        if analytics.get("abonnenten_aenderung_28_tage") is not None:
            vz = analytics["abonnenten_aenderung_28_tage"]
            erkenntnisse.append(f"Abonnenten-Veraenderung im selben Zeitraum: {vz:+.0f}")
        inhalte = analytics.get("inhalte") or []
        if inhalte:
            bestes, schlechtestes = inhalte[0], inhalte[-1]
            if bestes["titel"] != schlechtestes["titel"]:
                erkenntnisse.append(f"Bestes Video im Zeitraum: «{bestes['titel']}» mit {bestes['aufrufe']} "
                                    f"Aufrufen, schwaechstes: «{schlechtestes['titel']}» mit "
                                    f"{schlechtestes['aufrufe']}")
        fehlende_zahlen = [k for k, v in analytics.items()
                          if k not in ("abgerufen_um", "inhalte") and v is None]
        if fehlende_zahlen:
            erkenntnisse.append(f"Von Studio nicht gelesen: {', '.join(fehlende_zahlen)}")
    risikoarm_vorschlaege: list[dict] = []
    if len(verlauf) < MIN_MESSPUNKTE_FUER_MUSTER:
        erkenntnisse.append(f"Erst {len(verlauf)} taegliche Messpunkte - fuer belastbare Muster braucht es "
                            f"mindestens {MIN_MESSPUNKTE_FUER_MUSTER}, heute keine automatische Anpassung")
    return {"erkenntnisse": erkenntnisse, "risikoarm_vorschlaege": risikoarm_vorschlaege, "experiment_vorschlag": None}


def risikoarm_anwenden(vorschlaege: list[dict]) -> list[dict]:
    """Setzt risikoarme Vorschlaege (Titel/Beschreibung/Tags/Thumbnail) direkt um, ueber
    upload.youtube_playwright.set_metadata/set_thumbnail. Noch ungenutzt: strategie_ableiten liefert erst dann
    etwas, wenn eine Regel einen konkreten, begruendeten Befund hat - nie geraten."""
    angewendet = []
    if not vorschlaege:
        return angewendet
    from upload.youtube_playwright import set_metadata, set_thumbnail
    for v in vorschlaege:
        try:
            if v.get("art") == "titel":
                set_metadata(v["video_id"], title=v["neu"])
            elif v.get("art") == "beschreibung":
                set_metadata(v["video_id"], description=v["neu"])
            elif v.get("art") == "thumbnail":
                set_thumbnail(v["video_id"], v["neu"])
            else:
                continue
            angewendet.append(v)
            try:
                _kanal_protokoll().eintrag(
                    kanal="weltlage", art=v["art"], alt=v.get("alt"), neu=v["neu"], video_ids=[v["video_id"]],
                    video_titel=v.get("video_titel"), grund=v.get("grund", ""),
                    ausloeser="weltlage_kanalmanager.risikoarm_anwenden")
            except Exception:   # noqa: BLE001 - Protokoll darf eine echte Kanal-Aenderung nie gefaehrden
                pass
        except Exception as e:   # noqa: BLE001 - ein fehlgeschlagener Vorschlag haelt den Lauf nicht an
            v["fehler"] = str(e)[:300]
    return angewendet


# ------------------------------------------------------------------------ Experiment (hoechstens eins gleichzeitig)
def experiment_stand() -> dict:
    return _lesen(EXPERIMENT_PFAD, {"status": "keins"})


def experiment_vorschlagen(idee: str, clip_pfad: str | None = None) -> dict:
    """Schlaegt EIN Experiment vor (Vorher/Nachher-Clip, rexemre antwortet ja/nein) - liegt schon eins offen, wird
    kein zweites angelegt (Regel: hoechstens ein Experiment aufs Mal)."""
    stand = experiment_stand()
    if stand.get("status") in ("vorgeschlagen", "wartet_antwort"):
        return stand
    stand = {"status": "vorgeschlagen", "idee": idee, "clip": clip_pfad,
             "vorgeschlagen_am": jetzt().isoformat(timespec="seconds")}
    _schreiben(EXPERIMENT_PFAD, stand)
    return stand


def experiment_antwort(ja: bool) -> dict:
    """rexemres Antwort auf die eine offene Frage - kommt ueber jarvis/tools/weltlage_kanalmanager.py hierher."""
    stand = experiment_stand()
    stand["status"] = "angenommen" if ja else "abgelehnt"
    stand["beantwortet_am"] = jetzt().isoformat(timespec="seconds")
    _schreiben(EXPERIMENT_PFAD, stand)
    return stand


# ------------------------------------------------------------------------ 4) Tageslauf
def run(trocken: bool = False, debug_dir: str | None = None) -> dict:
    now = jetzt()
    uploads = uploads_pruefen(now)
    try:
        analytics = analytics_abrufen(debug_dir)
    except Exception as e:   # noqa: BLE001 - ein Analytics-Fehlschlag haelt den Bericht nicht an
        analytics = {"fehler": str(e)[:400]}
    verlauf = _lesen(VERLAUF_PFAD, [])
    if not trocken and "fehler" not in analytics:
        verlauf = verlauf + [analytics]
        verlauf = verlauf[-90:]
        _schreiben(VERLAUF_PFAD, verlauf)
    strategie = strategie_ableiten(uploads, analytics, verlauf)
    angewendet = [] if trocken else risikoarm_anwenden(strategie.get("risikoarm_vorschlaege") or [])
    faellige_auswertungen = []
    if not trocken:
        try:
            faellige_auswertungen = _kanal_protokoll().auswerten_alle_faelligen()
        except Exception:   # noqa: BLE001 - die 7-/28-Tage-Auswertung darf den Tageslauf nie zum Absturz bringen
            pass
    return {"zeit": now.isoformat(timespec="seconds"), "uploads": uploads, "analytics": analytics,
            "erkenntnisse": strategie.get("erkenntnisse") or [], "angewendet": angewendet,
            "experiment": experiment_stand(), "kanal_protokoll_auswertungen": faellige_auswertungen}


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("run")
    r.add_argument("--trocken", action="store_true")
    r.add_argument("--debug-dir")
    sub.add_parser("status")
    ea = sub.add_parser("experiment-antwort")
    ea.add_argument("antwort", choices=["ja", "nein"])
    args = ap.parse_args()

    if args.cmd == "experiment-antwort":
        print(json.dumps(experiment_antwort(args.antwort == "ja"), ensure_ascii=False))
    elif args.cmd == "status":
        print(json.dumps({"experiment": experiment_stand(), "letzter_verlauf_eintrag":
                          (_lesen(VERLAUF_PFAD, []) or [None])[-1]}, ensure_ascii=False, default=str))
    else:
        ergebnis = run(trocken=getattr(args, "trocken", False), debug_dir=getattr(args, "debug_dir", None))
        print(json.dumps(ergebnis, ensure_ascii=False, default=str))
