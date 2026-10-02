"""Weltlage Kompakt - zweimal taeglich vollautomatisch mit Themenwahl und Freigabe (Marlon 02.10.2026 23:03).

Dauerhafte Freigabe von Marlon (02.10.2026 23:03): der Kanal laeuft vollautomatisch inklusive Veroeffentlichung auf
YouTube, wenn Marlon nicht innerhalb einer Stunde reagiert. Ersetzt den frueheren Lauf um 07:00 (Task dffa).

Gestartet von der resident laufenden Pipeline (Aufgabe AbakosNewsroomPipeline, orchestrator/pipeline.py ruft pro
Tick pruefen_und_starten() auf) - kein eigener Windows-Task. Pro Slot (NEWS_WELTLAGE_SLOTS, Standard 11:00,19:00 =
Veroeffentlichungszeit) beginnt der Lauf vorlauf_stunden() vorher (Themenwahl + gemessene Produktionsdauer + Puffer,
siehe produktion_stunden) als eigener, losgeloester Prozess (pythonw, kein Fenster) und arbeitet diese Schritte ab
(jeder Schritt wird bei einem Neustart uebersprungen, wenn sein Ergebnis schon da ist):

  0 thema       tools/weltlage_themen.py: Recherche (Rohmeldungen der Pipeline), drei Storylines A/B/C mit Titel als
                Frage + ein Satz Inhalt + gruene Bildquellen, Empfehlung; Themenpool (state/weltlage_themenpool.json)
                wird bevorzugt angeboten. Rueckfrage an Telegram (Knoepfe A/B/C) und Beta-App
                (tools/weltlage_entscheid.py), NEWS_WELTLAGE_THEMENWAHL_MINUTEN warten, sonst Empfehlung. Freitext zur
                Wahl geht als Hinweis ins Skript (vorgabe.txt). Ergebnis: wahl.json, news.json, vorgabe.txt.
                Vorab gewaehlte Storyline (Zustand "vorgabe": {titel, inhalt}) = keine Rueckfrage.
  1 skript      tools/weltlage_skript.py --texte [--news news.json --vorgabe vorgabe.txt] (Analyse-Prompt)
  2 aussprache  tts/aussprache_lexikon.py lerne_aus_folge (Fehler = ohne neuen Eintrag weiter)
  3 bilder      Screenshots der Quellartikel pro Meldung (video/sources.capture) -> bilder.json
  4 stimme      tools/weltlage_tts.py (Chatterbox-Klon laut Profil, GPU-Warteschlange; nur geaenderte Szenen neu)
  5 schnitt     tools/weltlage_rohschnitt.py (feste Szenen eingefroren, Lipsync Guidance 2.0, GPU-Warteschlange)
  6 broll       tools/weltlage_broll.py --video (NEWS_WELTLAGE_BROLL=1; gruene Quellen; Fehler -> ohne Clips weiter)
  7 abnahme     tools/weltlage_abnahme.py (Fehler = nie automatisch veroeffentlichen, nur melden)
  8 thumbnail   video/weltlage_thumbnail.py (Latara-Foto nach Stimmung aus Marlons Ordner, rechts, textfrei)
  9 metadaten   Titel (staerkste Frage-Variante), Beschreibung, Tags -> metadaten.json
 10 warten      bis zur Slot-Zeit; mehr als NEWS_WELTLAGE_MAX_VERSPAETUNG_STUNDEN zu spaet -> verwerfen + Meldung
 11 freigabe    Video (Telegram-Fassung, Ton kopiert, als Dokument) + Thumbnail + Titel an Telegram, Text + Knoepfe an
                die Beta-App: «Freigeben» = sofort veroeffentlichen, «Stopp» = nicht veroeffentlichen, «Feedback» =
                tools/weltlage_ueberarbeiten.py setzt die Aenderungen um, nur betroffene Szenen werden neu gerendert
                (Schritte stimme..metadaten erneut), das Video kommt neu und das Fenster startet von vorn (hoechstens
                NEWS_WELTLAGE_MAX_FEEDBACK_RUNDEN, danach nur noch Freigeben/Stopp). Keine Reaktion innert
                NEWS_WELTLAGE_FREIGABE_MINUTEN = automatisch veroeffentlichen.
 12 upload      upload/youtube_playwright.upload_datei (oeffentlich); NEWS_WELTLAGE_TROCKENLAUF=1 bzw. --trocken:
                nie hochladen (Test)
 13 endscreen   upload/endscreen_playwright.set_endscreen (Task 595e; Fehler = kein Abbruch)
 14 meldung     Link an Telegram + Beta-App bzw. Fehlermeldung mit Schritt

Zustand: state/weltlage_tageslauf.json, Rueckfragen state/weltlage_entscheid/, Log pro Lauf <folge>/tageslauf.log.
Pause ohne Code-Aenderung: Datei state/weltlage_tageslauf.pause anlegen (loeschen = weiter).

    python tools/weltlage_tageslauf.py status
    python tools/weltlage_tageslauf.py zeitplan                     (Slots, gemessene Produktionsdauer, Startzeiten)
    python tools/weltlage_tageslauf.py lauf --slot 11:00 [--datum 2026-10-03] [--bis metadaten] [--ordner DIR]
                                            [--nur thema,skript] [--trocken] [--themenwahl-min 2] [--freigabe-min 2]
    python tools/weltlage_tageslauf.py metadaten <folgenordner>
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config.settings import (DATA_DIR, NEWS_WELTLAGE_BROLL, NEWS_WELTLAGE_BROLL_OHNE_KI,
                             NEWS_WELTLAGE_FREIGABE_MINUTEN,  # noqa: E402
                             NEWS_WELTLAGE_MAX_FEEDBACK_RUNDEN, NEWS_WELTLAGE_MAX_VERSPAETUNG_STUNDEN,
                             NEWS_WELTLAGE_PRODUKTION_STUNDEN, NEWS_WELTLAGE_SLOTS, NEWS_WELTLAGE_TAEGLICH,
                             NEWS_WELTLAGE_THEMENWAHL_MINUTEN, NEWS_WELTLAGE_TROCKENLAUF,
                             NEWS_WELTLAGE_UPLOAD_VISIBILITY, STATE_DIR)

ZUSTAND = STATE_DIR / "weltlage_tageslauf.json"
PAUSE = STATE_DIR / "weltlage_tageslauf.pause"
PY = ROOT / ".venv" / "Scripts" / "python.exe"
PYW = ROOT / ".venv" / "Scripts" / "pythonw.exe"
LS_PY = ROOT / ".venv-lipsync" / "Scripts" / "python.exe"
SCHRITTE = ["thema", "skript", "aussprache", "bilder", "stimme", "schnitt", "broll", "abnahme", "thumbnail",
            "metadaten", "warten", "freigabe", "upload", "endscreen", "meldung"]
PRODUKTION = ["stimme", "schnitt", "broll", "abnahme", "thumbnail", "metadaten"]   # nach Feedback erneut
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
KI_HINWEIS = ("Moderatorin Latara und ihre Stimme sind KI-generiert. Fakten und Zitate stammen aus den unten "
              "verlinkten Quellen; Lataras Einschätzungen sind im Video als ihre Meinung gekennzeichnet.")
FESTE_TAGS = ["Weltlage Kompakt", "Nachrichten", "Weltpolitik", "Analyse", "Weltlage", "News Deutsch"]
MAX_NEUSTARTS = 3
PUFFER_STUNDEN = 0.5
# Produktion ohne Rohschnitt (Skript, Bilder, Stimme, B-Roll, Abnahme, Thumbnail), gemessen 02.10.: rund 1 h
NEBENSCHRITTE_STUNDEN = 1.0
PRODUKTION_FALLBACK_STUNDEN = 6.5


# ------------------------------------------------------------------ Zustand
def _laden() -> dict:
    try:
        return json.loads(ZUSTAND.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _speichern(z: dict):
    tmp = ZUSTAND.with_suffix(".tmp")
    tmp.write_text(json.dumps(z, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(ZUSTAND)


def _eintrag(key: str, **felder) -> dict:
    z = _laden()
    e = z.setdefault(key, {})
    e.update(felder)
    _speichern(z)
    return e


def _pid_lebt(pid) -> bool:
    if not pid:
        return False
    try:
        out = subprocess.run(["tasklist", "/FI", f"PID eq {int(pid)}", "/NH"], capture_output=True, text=True,
                             errors="replace", creationflags=NO_WINDOW, timeout=30).stdout
        return str(int(pid)) in out
    except Exception:
        return False


def slot_zeit(datum: str, slot: str) -> datetime:
    h, m = (int(x) for x in slot.split(":"))
    return datetime.fromisoformat(datum).replace(hour=h, minute=m, second=0, microsecond=0).astimezone()


# ------------------------------------------------------------------ Zeitplan
def produktion_stunden(data_dir: Path | None = None) -> float:
    """Dauer Skript bis fertiges Video. NEWS_WELTLAGE_PRODUKTION_STUNDEN als Zahl = fest; "auto" = Rohschnitt-Dauer
    der letzten zwei vollen Folgen (data/weltlage_*/*_renderzeiten.json, "gesamt" >= 50 min, Maximum der beiden,
    damit eine schnelle Ausnahme den Zeitplan nicht kippt) + NEBENSCHRITTE_STUNDEN."""
    if NEWS_WELTLAGE_PRODUKTION_STUNDEN not in ("", "auto"):
        try:
            return float(NEWS_WELTLAGE_PRODUKTION_STUNDEN)
        except ValueError:
            pass
    werte = []
    for p in sorted((data_dir or DATA_DIR).glob("weltlage_*/*_renderzeiten.json"), key=lambda p: p.stat().st_mtime,
                    reverse=True):
        if "test" in p.parent.name:
            continue
        try:
            g = float(json.loads(p.read_text(encoding="utf-8")).get("gesamt") or 0)
        except (OSError, ValueError, TypeError):
            continue
        if g >= 3000:
            werte.append(g / 3600)
        if len(werte) >= 2:
            break
    if not werte:
        return PRODUKTION_FALLBACK_STUNDEN
    return round(min(10.0, max(3.0, max(werte) + NEBENSCHRITTE_STUNDEN)), 2)


def vorlauf_stunden(themenwahl_min: float | None = None) -> float:
    """Start des Laufs vor dem Slot: Themenwahl-Fenster + Produktion + Puffer."""
    tw = NEWS_WELTLAGE_THEMENWAHL_MINUTEN if themenwahl_min is None else themenwahl_min
    return round(tw / 60 + produktion_stunden() + PUFFER_STUNDEN, 2)


def faellig(jetzt: datetime, zustand: dict, vorlauf: float | None = None,
            produktion: float | None = None) -> list[tuple[str, str]]:
    """[(datum, slot)] deren Fenster offen ist (Start = Slot - Vorlauf, Ende = Slot + max. Verspaetung) und fuer die
    noch kein Lauf existiert, der Lauf abgestuerzt ist (PID weg, Status nicht final) oder ein angehaltener Lauf zum
    Fortsetzen markiert ist ("auto_fortsetzen": true, z.B. der von Hand vorproduzierte erste Lauf).
    Ein NEUER Lauf startet nur, solange er bis Slot + max. Verspaetung noch fertig werden kann (jetzt + Produktion);
    Vorfall 02.10. 23:55: beim Umstellen auf 11:00/19:00 startete sonst der laengst vergangene 19:00-Slot desselben
    Tages und schickte Marlon eine Themenwahl."""
    vorlauf = vorlauf_stunden() if vorlauf is None else vorlauf
    produktion = produktion_stunden() if produktion is None else produktion
    out = []
    for tag in (jetzt.date(), jetzt.date() + timedelta(days=1)):
        for slot in NEWS_WELTLAGE_SLOTS:
            t = slot_zeit(tag.isoformat(), slot)
            if not (t - timedelta(hours=vorlauf) <= jetzt <= t + timedelta(hours=NEWS_WELTLAGE_MAX_VERSPAETUNG_STUNDEN)):
                continue
            e = zustand.get(f"{tag.isoformat()}_{slot}")
            if e is None or not e.get("status"):     # ohne Status = nur vorgemerkt (z.B. "vorgabe")
                if jetzt + timedelta(hours=produktion) <= t + timedelta(hours=NEWS_WELTLAGE_MAX_VERSPAETUNG_STUNDEN):
                    out.append((tag.isoformat(), slot))
            elif e.get("status") in ("laeuft", "angehalten") and not _pid_lebt(e.get("pid")) \
                    and e.get("neustarts", 0) < MAX_NEUSTARTS \
                    and (e.get("status") == "laeuft" or e.get("auto_fortsetzen")):
                out.append((tag.isoformat(), slot))
    return out


def pruefen_und_starten(jetzt: datetime | None = None, log=print) -> list[str]:
    """Aufruf aus dem Pipeline-Tick: startet faellige Laeufe als losgeloeste Prozesse ohne Fenster."""
    if not NEWS_WELTLAGE_TAEGLICH or PAUSE.exists():
        return []
    jetzt = jetzt or datetime.now().astimezone()
    gestartet = []
    zustand = _laden()
    for datum, slot in faellig(jetzt, zustand):
        key = f"{datum}_{slot}"
        neustarts = (zustand.get(key) or {}).get("neustarts", -1) + 1 if (zustand.get(key) or {}).get("status") else 0
        logdatei = STATE_DIR / "weltlage_tageslauf.log"
        with open(logdatei, "a", encoding="utf-8") as f:
            p = subprocess.Popen([str(PYW), str(Path(__file__).resolve()), "lauf", "--slot", slot, "--datum", datum],
                                 cwd=str(ROOT), stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                 creationflags=NO_WINDOW | getattr(subprocess, "DETACHED_PROCESS", 0)
                                 | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0), close_fds=True)
        _eintrag(key, status="laeuft", pid=p.pid, gestartet=jetzt.isoformat(timespec="seconds"), neustarts=neustarts)
        log(f"Weltlage-Tageslauf {key} gestartet (PID {p.pid}, Neustart {neustarts})")
        gestartet.append(key)
    return gestartet


def zeitplan(jetzt: datetime | None = None) -> dict:
    jetzt = jetzt or datetime.now().astimezone()
    prod = produktion_stunden()
    vl = vorlauf_stunden()
    slots = []
    for slot in NEWS_WELTLAGE_SLOTS:
        t = slot_zeit(jetzt.date().isoformat(), slot)
        start = t - timedelta(hours=vl)
        slots.append({"slot": slot, "themenwahl_ab": f"{start:%H:%M}",
                      "produktion_ab": f"{start + timedelta(minutes=NEWS_WELTLAGE_THEMENWAHL_MINUTEN):%H:%M}",
                      "freigabe_bis": f"{t + timedelta(minutes=NEWS_WELTLAGE_FREIGABE_MINUTEN):%H:%M}"})
    return {"produktion_h": prod, "vorlauf_h": vl, "themenwahl_min": NEWS_WELTLAGE_THEMENWAHL_MINUTEN,
            "freigabe_min": NEWS_WELTLAGE_FREIGABE_MINUTEN, "slots": slots}


# ------------------------------------------------------------------ Schritte
class Abbruch(RuntimeError):
    pass


class Gestoppt(RuntimeError):
    pass


def _run(cmd: list, log, timeout_h: float = 6, python=None) -> int:
    """Schritt als Unterprozess ohne Fenster. HuggingFace offline (alle Modelle liegen im Cache): am 02.10. 23:43
    hing tools/weltlage_tts.py 10 min still an einer CDN-Verbindung des Hub-Checks; HF_HUB_OFFLINE=0 in der Umgebung
    hebt das auf."""
    log("$ " + " ".join(str(c) for c in cmd))
    with open(log.datei, "a", encoding="utf-8") as f:
        p = subprocess.run([str(python or PY), *map(str, cmd)], cwd=str(ROOT), stdout=f, stderr=subprocess.STDOUT,
                           stdin=subprocess.DEVNULL, timeout=timeout_h * 3600, creationflags=NO_WINDOW,
                           env={"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", **os.environ,
                                "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"})
    log(f"-> Exit {p.returncode}")
    return p.returncode


def bilder_holen(ordner: Path, log) -> dict:
    """Screenshots der Quellartikel pro verwendeter Meldung (wie data/<folge>/bilder_holen.py, jetzt allgemein)."""
    from video.sources import capture
    news = json.loads((ordner / "news.json").read_text(encoding="utf-8"))
    texte = json.loads((ordner / "texte.json").read_text(encoding="utf-8"))
    byurl = {a["url"].split("?")[0]: a for g in news for a in g["articles"] if a.get("url")}
    benutzt = {int(s["bild"]) for s in texte["szenen"] if s.get("bild") is not None}
    (ordner / "bilder").mkdir(exist_ok=True)
    praefix = "wl" + re.sub(r"\D", "", ordner.name)[-12:]
    res = {}
    for b in texte["bilder"]:
        if b["idx"] not in benutzt:
            continue
        arts = [a for u in b["urls"] for a in [byurl.get(u.split("?")[0])
                                               or next((v for k, v in byurl.items() if k.startswith(u)), None)] if a]
        shots = capture(f"{praefix}_{b['idx']}", arts)
        res[b["idx"]] = []
        for s in shots:
            dst = ordner / "bilder" / f"m{b['idx']}_{s['index']}.png"
            shutil.copy(s["png"], dst)
            res[b["idx"]].append({"png": str(dst), "source": s["source"], "domain": s["domain"], "title": s["title"],
                                  "url": s["url"]})
        shutil.rmtree(DATA_DIR / "broll" / f"{praefix}_{b['idx']}", ignore_errors=True)
        log(f"Bilder Meldung {b['idx']}: {len(shots)} ({', '.join(s['source'] for s in shots)})")
    if not any(res.values()):
        raise Abbruch("keine einzige Quellen-Aufnahme - ohne Schnittbilder wird nicht veröffentlicht")
    (ordner / "bilder.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    return res


def _quellen(ordner: Path, texte: dict) -> list[str]:
    news = json.loads((ordner / "news.json").read_text(encoding="utf-8"))
    benutzt = sorted({m for s in texte["szenen"] for m in s.get("meldungen") or []})
    zeilen, gesehen = [], set()
    for nr in benutzt:
        if not 1 <= nr <= len(news):
            continue
        for a in news[nr - 1]["articles"][:3]:
            url = a.get("url")
            if url and url not in gesehen:
                gesehen.add(url)
                zeilen.append(f"[{len(zeilen) + 1}] {a.get('source')} ({str(a.get('published_at') or '')[:10]}): {url}")
    for z in texte.get("zitate") or []:
        url = z.get("url")
        if url and url not in gesehen:
            gesehen.add(url)
            zeilen.append(f"[{len(zeilen) + 1}] Zitat {z.get('person')} ({z.get('kanal')}, {z.get('datum')}): {url}")
    return zeilen


def _hashtags(namen: list[str]) -> str:
    tags = ["#WeltlageKompakt", "#Nachrichten", "#Weltpolitik"]
    for n in namen:
        t = "#" + re.sub(r"[^A-Za-z0-9ÄÖÜäöü]", "", n)
        if len(t) > 3 and t not in tags:
            tags.append(t)
        if len(tags) >= 6:
            break
    return " ".join(tags)


def metadaten(ordner: Path) -> dict:
    """Titel, Beschreibung, Tags aus texte.json. Hook = erster Absatz (Cold Open), dann These, Kommentarfrage,
    Quellen, KI-Hinweis, Clip-Lizenzen, Hashtags. Titel-Varianten bleiben in metadaten.json dokumentiert."""
    texte = json.loads((ordner / "texte.json").read_text(encoding="utf-8"))
    hook = texte.get("hook") or next((s["text"] for s in texte["szenen"] if s["id"] == "s_coldopen"), "")
    hook = hook.replace("Das alles gleich in Weltlage Kompakt.", "").strip()
    namen = [h.get("stichwort") for h in texte.get("hook_themen") or [] if h.get("stichwort")]
    teile = [hook, texte.get("zentrale_these") or ""]
    if texte.get("kommentarfrage"):
        teile.append(f"Meine Frage an dich: {texte['kommentarfrage']} Schreib es in die Kommentare.")
    quellen = _quellen(ordner, texte)
    if quellen:
        teile.append("Quellen:\n" + "\n".join(quellen))
    teile.append(KI_HINWEIS)
    attribution = ordner / "broll_attribution.txt"
    if attribution.exists() and attribution.read_text(encoding="utf-8").strip():
        teile.append(attribution.read_text(encoding="utf-8").strip())
    teile.append(_hashtags(namen))
    beschreibung = "\n\n".join(t for t in teile if t.strip())[:4900]
    tags, laenge = [], 0
    for t in [*namen, *FESTE_TAGS]:
        t = t.strip()[:60]
        if t and t.lower() not in {x.lower() for x in tags} and laenge + len(t) + 2 < 480:
            tags.append(t)
            laenge += len(t) + 2
    meta = {"title": texte["titel"][:100], "description": beschreibung, "tags": tags, "language": "de",
            "titel_varianten": texte.get("titel_varianten"), "thumbnail": texte.get("thumbnail"),
            "kommentarfrage": texte.get("kommentarfrage")}
    (ordner / "metadaten.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")
    return meta


JARVIS_TOOLS = Path(r"C:\Users\Marlon\projekte\jarvis\tools")   # gleiches Muster wie gpu_budget.py: in-process, Fallback bei Fehler
_ergebnis_mod = None


def _ergebnis_zeigen():
    """tools/ergebnis_zeigen.py aus Jarvis (Marlon-Regel 01.10.: am PC öffnen statt immer Telegram); None = nicht
    erreichbar, dann bleibt es beim alten direkten Telegram-Versand."""
    global _ergebnis_mod
    if _ergebnis_mod is None:
        try:
            if str(JARVIS_TOOLS) not in sys.path:
                sys.path.append(str(JARVIS_TOOLS))
            import ergebnis_zeigen
            _ergebnis_mod = ergebnis_zeigen
        except Exception as e:   # noqa: BLE001
            print(f"WARNUNG weltlage_tageslauf: ergebnis_zeigen nicht erreichbar ({e}), sende direkt per Telegram",
                  file=sys.stderr)
            _ergebnis_mod = False
    return _ergebnis_mod or None


def _melden(titel: str, text: str, log=print):
    """Reine Meldung an Telegram + Beta-App (ohne Rueckfrage)."""
    try:
        import weltlage_entscheid as ent
        ent.mitteilen(titel, text, log)
    except Exception as e:   # noqa: BLE001
        log(f"Meldung fehlgeschlagen: {e}")


class _Log:
    def __init__(self, datei: Path):
        self.datei = datei

    def __call__(self, msg: str):
        zeile = f"{datetime.now().astimezone():%Y-%m-%d %H:%M:%S} {msg}"
        print(zeile, flush=True)
        with open(self.datei, "a", encoding="utf-8") as f:
            f.write(zeile + "\n")


# ------------------------------------------------------------------ Themenwahl
FERTIG_STATUS = ("beantwortet", "abgelaufen", "abgebrochen")


def _offene_frage(key: str, phase: str) -> dict | None:
    """Laufende (oder beantwortete, aber noch nicht verarbeitete) Rueckfrage dieses Laufs nach einem Neustart."""
    import weltlage_entscheid as ent
    e = ent.laden(ent.lauf_id(key))
    if not e or e.get("phase") != phase:
        return None
    if e.get("status") in ent.OFFEN_STATUS or (e.get("status") in FERTIG_STATUS and not e.get("verarbeitet")):
        return e
    return None


def _als_verarbeitet(e: dict):
    import weltlage_entscheid as ent
    x = ent.laden(e["id"]) or e
    x["verarbeitet"] = True
    ent._schreiben(ent._pfad(x["id"]), x)


def thema_waehlen(key: str, slot: str, ordner: Path, log, minuten: float, trocken: bool = False) -> dict:
    """Schritt thema. Ergebnis wahl.json; news.json + vorgabe.txt fuer das Skript."""
    import weltlage_entscheid as ent
    import weltlage_themen as th
    vorab = (_laden().get(key) or {}).get("vorgabe")
    sl = ordner / "storylines.json"
    d = json.loads(sl.read_text(encoding="utf-8")) if sl.exists() else th.vorschlagen(ordner, feste=vorab)
    emp = d.get("empfehlung") or "A"
    if vorab:
        wahl = {"wahl": "A", "feedback": None, "quelle": "vorab gewählt"}
    else:
        e = _offene_frage(key, "thema")
        if e is None:
            frist = datetime.now().astimezone() + timedelta(minutes=minuten)
            kopf = f"{'TEST (Trockenlauf, wird nicht veröffentlicht): ' if trocken else ''}Weltlage Kompakt, Folge um {slot}: welche Storyline?"
            e = ent.fragen(key, "thema", th.bericht(d, f"{frist:%H:%M}", kopf=kopf),
                           {s["buchstabe"]: s["buchstabe"] + (" (Empfehlung)" if s["buchstabe"] == emp else "")
                            for s in d["storylines"]}, frist, empfehlung=emp,
                           titel=f"Weltlage {slot}: Thema wählen", log=log)
        ant = e.get("antwort") if e.get("status") in FERTIG_STATUS else ent.warten(e["id"], log)
        _als_verarbeitet(e)
        wahl = ant or {"wahl": emp, "feedback": None, "quelle": "automatisch (keine Antwort, Empfehlung)"}
    s = th.storyline(d, wahl["wahl"])
    news = th.news_fuer(d, wahl["wahl"])
    if news:
        (ordner / "news.json").write_text(json.dumps(news, indent=1, ensure_ascii=False), encoding="utf-8")
    (ordner / "vorgabe.txt").write_text(th.vorgabe_text(s, wahl.get("feedback")), encoding="utf-8")
    wahl = {**wahl, "titel": s["titel"], "zeit": wahl.get("zeit") or datetime.now().astimezone().isoformat(timespec="seconds")}
    (ordner / "wahl.json").write_text(json.dumps(wahl, indent=1, ensure_ascii=False), encoding="utf-8")
    th.pool_entfernen(s.get("pool_id"))
    log(f"Thema {wahl['wahl']}: {s['titel']} ({wahl.get('quelle')})" + (f", Hinweis: {wahl['feedback']}"
                                                                         if wahl.get("feedback") else ""))
    if not vorab:
        _melden(f"Weltlage {slot}{' (Trockenlauf)' if trocken else ''}", f"Thema {wahl['wahl']}: {s['titel']} "
                f"({wahl.get('quelle')}). Produktion läuft, das fertige Video kommt um {slot} zur Freigabe.", log)
    return wahl


# ------------------------------------------------------------------ Freigabe
def telegram_fassung(datei: Path, ordner: Path, log) -> Path | None:
    out = ordner / "telegram" / f"{datei.stem}_telegram.mp4"
    if out.exists() and out.stat().st_mtime >= datei.stat().st_mtime:
        return out
    out.parent.mkdir(exist_ok=True)
    try:
        import telegram_fassung as tf
        return tf.fassung(datei, out)
    except BaseException as e:   # fassung() bricht mit SystemExit ab, wenn der Master-Ton falsch ist
        log(f"Telegram-Fassung fehlgeschlagen: {e}")
        return None


def freigabe_einholen(key: str, slot: str, ordner: Path, master: Path, log, minuten: float, trocken: bool,
                      produktion) -> str:
    """Schritt freigabe. Rueckgabe "freigegeben" | "automatisch"; Stopp -> Gestoppt; Feedback -> Ueberarbeitung +
    produktion() (Schritte stimme..metadaten) + neue Runde."""
    import weltlage_entscheid as ent
    while True:
        z = _laden().get(key) or {}
        runden = int(z.get("feedback_runden") or 0)
        e = _offene_frage(key, "freigabe")
        if e is None:
            clips = master.with_name(master.stem + "_clips.mp4")
            datei = clips if clips.exists() else master
            meta = json.loads((ordner / "metadaten.json").read_text(encoding="utf-8"))
            frist = datetime.now().astimezone() + timedelta(minutes=minuten)
            optionen = {"freigeben": "Freigeben", "feedback": "Feedback", "stopp": "Stopp"}
            if runden >= NEWS_WELTLAGE_MAX_FEEDBACK_RUNDEN:
                optionen.pop("feedback")
            text = (f"Weltlage Kompakt {slot}{' (TROCKENLAUF, kein Upload)' if trocken else ''}: Video fertig"
                    f"{f' (Fassung {runden + 1})' if runden else ''}.\nTitel: {meta['title']}\n\n"
                    f"Ohne Antwort bis {frist:%H:%M} veröffentliche ich es automatisch öffentlich auf YouTube. "
                    "Freigeben = sofort, Stopp = nicht veröffentlichen"
                    + (", Feedback = Änderungen (nur betroffene Szenen werden neu gerendert)." if "feedback" in optionen
                       else ". Die Feedback-Runden sind aufgebraucht."))
            beta_text = text + "\nVideo und Thumbnail liegen in Telegram."
            e = ent.fragen(key, "freigabe", text, optionen, frist, titel=f"Weltlage {slot}: Freigabe",
                           dokument=telegram_fassung(datei, ordner, log),
                           bild=ordner / "thumbnails" / "thumbnail.jpg", beta_text=beta_text, log=log)
            _eintrag(key, freigabe_frage=e["id"], freigabe_runde=e["runde"])
        ant = e.get("antwort") if e.get("status") in FERTIG_STATUS else ent.warten(e["id"], log)
        _als_verarbeitet(e)
        if ant is None:
            log("Freigabe: keine Reaktion im Fenster - automatisch veröffentlichen")
            return "automatisch"
        log(f"Freigabe-Antwort: {ant}")
        if ant["wahl"] == "freigeben":
            return "freigegeben"
        if ant["wahl"] == "stopp":
            raise Gestoppt(f"Marlon hat «Stopp» gedrückt ({ant.get('quelle')})")
        runde = runden + 1
        _eintrag(key, feedback_runden=runde)
        from weltlage_ueberarbeiten import ueberarbeiten
        try:
            res = ueberarbeiten(ordner, ant.get("feedback") or "", runde, master)
        except Exception as ex:   # noqa: BLE001
            _melden(f"Weltlage {slot}", f"Feedback konnte ich nicht umsetzen ({str(ex)[:300]}). Das Video bleibt "
                    "wie es ist und kommt gleich nochmal zur Freigabe.", log)
            continue
        log(f"Feedback Runde {runde}: Szenen {res['szenen'] or '-'}, Titel {res['titel']}, Thumbnail {res['thumbnail']}")
        _melden(f"Weltlage {slot}", f"Feedback wird umgesetzt: {res['zusammenfassung']} "
                + (f"Neu gerendert werden {len(res['szenen'])} Szene(n), das dauert etwas."
                   if res["neu_rendern"] else "Nur Titel/Thumbnail, kein neues Rendern."), log)
        produktion(PRODUKTION if res["neu_rendern"] else ["thumbnail", "metadaten"])


# ------------------------------------------------------------------ Lauf
def lauf(datum: str, slot: str, ordner: Path | None = None, bis: str | None = None,
         nur: list[str] | None = None, trocken: bool | None = None, themenwahl_min: float | None = None,
         freigabe_min: float | None = None) -> int:
    key = f"{datum}_{slot}"
    trocken = NEWS_WELTLAGE_TROCKENLAUF if trocken is None else trocken
    themenwahl_min = NEWS_WELTLAGE_THEMENWAHL_MINUTEN if themenwahl_min is None else themenwahl_min
    freigabe_min = NEWS_WELTLAGE_FREIGABE_MINUTEN if freigabe_min is None else freigabe_min
    ordner = ordner or DATA_DIR / f"weltlage_{datum.replace('-', '')}_{slot.replace(':', '')}"
    ordner.mkdir(parents=True, exist_ok=True)
    log = _Log(ordner / "tageslauf.log")
    _eintrag(key, status="laeuft", pid=os.getpid(), ordner=str(ordner), trocken=trocken)
    master = ordner / f"weltlage_{datum.replace('-', '')}_{slot.replace(':', '')}.mp4"
    veroeffentlichen = slot_zeit(datum, slot)
    log(f"Tageslauf {key} in {ordner} (Veröffentlichung {veroeffentlichen:%d.%m. %H:%M}, bis {bis or 'Ende'}"
        f"{', TROCKENLAUF' if trocken else ''})")

    def schritt_ausfuehren(schritt: str):
        if schritt == "thema" and not (ordner / "wahl.json").exists() and not (ordner / "texte.json").exists():
            try:
                thema_waehlen(key, slot, ordner, log, themenwahl_min, trocken)
            except Exception as ex:  # noqa: BLE001 - ohne Themenwahl waehlt das Skript selbst aus den Meldungen
                log(f"Themenwahl fehlgeschlagen ({ex}) - Skript wählt das Thema selbst")
                _melden(f"Weltlage {slot}", f"Themenwahl ging nicht ({str(ex)[:200]}), ich nehme die "
                        "wichtigsten aktuellen Meldungen.", log)
        elif schritt == "skript" and not (ordner / "texte.json").exists():
            cmd = ["tools/weltlage_skript.py", "--ordner", ordner, "--texte"]
            if (ordner / "wahl.json").exists() and (ordner / "news.json").exists():
                cmd += ["--news", ordner / "news.json"]
            if (ordner / "vorgabe.txt").exists():
                cmd += ["--vorgabe", ordner / "vorgabe.txt"]
            rc = _run(cmd, log, timeout_h=1)
            if rc != 0 or not (ordner / "texte.json").exists():
                log("Skript mit Problemen - zweiter Versuch")
                rc = _run(cmd, log, timeout_h=1)
            if rc != 0 or not (ordner / "texte.json").exists():
                raise Abbruch("Skript besteht die automatische Prüfung nicht (siehe skript.md)")
        elif schritt == "aussprache":
            try:
                from tts.aussprache_lexikon import lerne_aus_folge
                lerne_aus_folge(ordner, log=log)
            except Exception as ex:  # noqa: BLE001 - Zusatznutzen, nie ein Abbruchgrund fuer die Folge
                log(f"Aussprache-Pflege uebersprungen: {ex}")
        elif schritt == "bilder" and not (ordner / "bilder.json").exists():
            bilder_holen(ordner, log)
        elif schritt == "stimme":
            if _run(["tools/weltlage_tts.py", ordner], log, timeout_h=3) != 0:
                raise Abbruch("Vertonung fehlgeschlagen")
        elif schritt == "schnitt" and not master.exists():
            if _run(["tools/weltlage_rohschnitt.py", ordner, "--out", master], log, timeout_h=8,
                    python=LS_PY) != 0 or not master.exists():
                raise Abbruch("Rohschnitt/Lipsync fehlgeschlagen oder Stimmen-Endprüfung durchgefallen")
        elif schritt == "broll" and NEWS_WELTLAGE_BROLL:
            clips = master.with_name(master.stem + "_clips.mp4")
            cmd = ["tools/weltlage_broll.py", ordner, "--video", master] + (["--ohne-ki"] if NEWS_WELTLAGE_BROLL_OHNE_KI
                                                                           else [])
            if not clips.exists() and _run(cmd, log, timeout_h=3) != 0:
                log("B-Roll fehlgeschlagen - Folge geht ohne Symbolclips raus")
        elif schritt == "abnahme":
            if _run(["tools/weltlage_abnahme.py", ordner, master], log, timeout_h=1) != 0:
                raise Abbruch("Abnahme-Prüfung durchgefallen (Stimme/Lautheit/Ton/Zitate), siehe "
                              f"{master.stem}_abnahme.json - nicht veröffentlicht")
        elif schritt == "thumbnail":
            from video.weltlage_thumbnail import fuer_folge
            log(f"Thumbnail: {fuer_folge(ordner)}")
        elif schritt == "metadaten":
            m = metadaten(ordner)
            log(f"Titel: {m['title']} | {len(m['description'])} Zeichen Beschreibung | {len(m['tags'])} Tags")
        elif schritt == "warten":
            jetzt = datetime.now().astimezone()
            if jetzt > veroeffentlichen + timedelta(hours=NEWS_WELTLAGE_MAX_VERSPAETUNG_STUNDEN):
                raise Abbruch(f"zu spät fertig ({jetzt:%H:%M}), Folge wäre veraltet - nicht veröffentlicht")
            if jetzt < veroeffentlichen:
                log(f"fertig um {jetzt:%H:%M}, warte bis {veroeffentlichen:%H:%M}")
                _eintrag(key, status="laeuft", wartet_bis=veroeffentlichen.isoformat(timespec="minutes"))
                while datetime.now().astimezone() < veroeffentlichen:
                    time.sleep(min(60, max(1, (veroeffentlichen - datetime.now().astimezone()).total_seconds())))
        elif schritt == "freigabe":
            e = _laden().get(key) or {}
            if e.get("freigabe") or e.get("video_id"):
                log(f"Freigabe schon erledigt ({e.get('freigabe')})")
                return
            ergebnis = freigabe_einholen(key, slot, ordner, master, log, freigabe_min, trocken,
                                         lambda schritte: [schritt_ausfuehren(s) for s in schritte])
            _eintrag(key, freigabe=ergebnis)
        elif schritt == "upload":
            e = _laden().get(key) or {}
            if e.get("video_id"):
                log(f"bereits hochgeladen ({e['video_id']}) - kein zweiter Upload")
                return
            if PAUSE.exists():
                raise Abbruch("Pause-Datei gesetzt - nicht hochgeladen")
            meta = json.loads((ordner / "metadaten.json").read_text(encoding="utf-8"))
            clips = master.with_name(master.stem + "_clips.mp4")
            datei = clips if clips.exists() else master
            if trocken:
                log(f"TROCKENLAUF: würde jetzt {datei.name} öffentlich hochladen (Titel «{meta['title']}») - "
                    "kein Upload")
                _eintrag(key, upload={"trocken": True, "datei": str(datei)})
                return
            from upload.youtube_playwright import upload_datei
            res = upload_datei(datei, meta, ordner / "thumbnails" / "thumbnail.jpg",
                               visibility=NEWS_WELTLAGE_UPLOAD_VISIBILITY, log_path=ordner / "upload.log",
                               debug_dir=ordner / "upload_shots")
            _eintrag(key, video_id=res["video_id"], upload=res)
            log(f"Upload: {res}")
        elif schritt == "endscreen":
            video_id = (_laden().get(key) or {}).get("video_id")
            if not video_id:
                log("kein video_id - Endscreen übersprungen")
                return
            from upload.endscreen_playwright import EndscreenHaltedForReview, set_endscreen
            try:
                res = set_endscreen(video_id, log_path=ordner / "upload.log", debug_dir=ordner / "upload_shots",
                                    save=True)
                log(f"Endscreen: {res}")
            except EndscreenHaltedForReview as ex:
                log(f"Endscreen übersprungen: {ex}")
            except Exception as ex:   # noqa: BLE001
                log(f"Endscreen fehlgeschlagen (Folge bleibt veröffentlicht): {ex}")
        elif schritt == "meldung":
            e = _laden().get(key) or {}
            res = e.get("upload") or {}
            meta = json.loads((ordner / "metadaten.json").read_text(encoding="utf-8"))
            if trocken:
                _melden(f"Weltlage {slot} (Trockenlauf)", f"Freigabe: {e.get('freigabe')}. Kein Upload im "
                        f"Trockenlauf.\n{meta['title']}", log)
                _eintrag(key, status="trocken", fertig=datetime.now().astimezone().isoformat(timespec="seconds"))
                return
            ok = res.get("oeffentlich_bestaetigt") or NEWS_WELTLAGE_UPLOAD_VISIBILITY == "private"
            _melden(f"Weltlage {slot}", f"{'Veröffentlicht' if ok else 'Hochgeladen, aber noch NICHT öffentlich bestätigt'}"
                    f" ({NEWS_WELTLAGE_UPLOAD_VISIBILITY}, {e.get('freigabe')}): {meta['title']}\n"
                    f"https://youtu.be/{res.get('video_id')}\nThumbnail: {res.get('thumbnail')}", log)
            _eintrag(key, status="veroeffentlicht" if ok else "unbestaetigt",
                     fertig=datetime.now().astimezone().isoformat(timespec="seconds"))

    schritt = "start"
    try:
        for schritt in SCHRITTE:
            if nur and schritt not in nur:
                continue
            _eintrag(key, schritt=schritt)
            schritt_ausfuehren(schritt)
            if bis and schritt == bis:
                _eintrag(key, status="angehalten", schritt=schritt)
                log(f"angehalten nach Schritt {schritt} (--bis)")
                return 0
        if nur:
            _eintrag(key, status="probe", schritte=nur)
        log("Tageslauf fertig")
        return 0
    except Gestoppt as e:
        log(f"GESTOPPT: {e}")
        _eintrag(key, status="gestoppt", fertig=datetime.now().astimezone().isoformat(timespec="seconds"))
        _melden(f"Weltlage {slot}", f"Gestoppt, wird nicht veröffentlicht. Ordner: {ordner}", log)
        return 0
    except Exception as e:
        log(f"ABBRUCH in Schritt {schritt}: {e}")
        _eintrag(key, status="fehler", fehler=f"{schritt}: {str(e)[:500]}",
                 fertig=datetime.now().astimezone().isoformat(timespec="seconds"))
        _melden(f"Weltlage {slot}", f"NICHT veröffentlicht. Schritt «{schritt}»: {str(e)[:600]}\nOrdner: {ordner}",
                log)
        return 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    l = sub.add_parser("lauf")
    l.add_argument("--slot", required=True)
    l.add_argument("--datum", default=datetime.now().date().isoformat())
    l.add_argument("--ordner", type=Path)
    l.add_argument("--bis", choices=SCHRITTE)
    l.add_argument("--nur", help="nur diese Schritte, Komma-Liste (z.B. thema,skript,thumbnail,metadaten)")
    l.add_argument("--trocken", action="store_true", help="nie auf YouTube hochladen (Test)")
    l.add_argument("--themenwahl-min", type=float)
    l.add_argument("--freigabe-min", type=float)
    m = sub.add_parser("metadaten")
    m.add_argument("ordner", type=Path)
    sub.add_parser("status")
    sub.add_parser("zeitplan")
    a = ap.parse_args()
    if a.cmd == "lauf":
        sys.exit(lauf(a.datum, a.slot, a.ordner, a.bis, a.nur.split(",") if a.nur else None,
                      True if a.trocken else None, a.themenwahl_min, a.freigabe_min))
    if a.cmd == "metadaten":
        print(json.dumps(metadaten(a.ordner), indent=1, ensure_ascii=False))
    if a.cmd == "zeitplan":
        print(json.dumps(zeitplan(), indent=1, ensure_ascii=False))
    if a.cmd == "status":
        print(json.dumps({"aktiv": NEWS_WELTLAGE_TAEGLICH, "pause": PAUSE.exists(), "slots": NEWS_WELTLAGE_SLOTS,
                          "trockenlauf": NEWS_WELTLAGE_TROCKENLAUF, **zeitplan(),
                          "sichtbarkeit": NEWS_WELTLAGE_UPLOAD_VISIBILITY, "laeufe": _laden()}, indent=1,
                         ensure_ascii=False))


if __name__ == "__main__":
    main()
