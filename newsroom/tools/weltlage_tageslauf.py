"""Weltlage Kompakt - zweimal taeglich vollautomatisch mit Themenwahl und Freigabe (Marlon 02.10.2026 23:03).

Dauerhafte Freigabe von Marlon (02.10.2026 23:03): der Kanal laeuft vollautomatisch inklusive Veroeffentlichung auf
YouTube, wenn Marlon nicht innerhalb einer Stunde reagiert. Ersetzt den frueheren Lauf um 07:00 (Task dffa).

Seit 16.10.2026 (Marlons Ansage per Telegram): KEINE festen Veroeffentlichungs-Slots mehr. Slots (NEWS_WELTLAGE_SLOTS,
Standard 00:00,10:00) sind jetzt PRODUKTIONSSTART-Zeiten - die Themenwahl (Schritt 0) beginnt genau zum Slot, frisch,
nicht Stunden vorher fuer einen spaeteren Termin. Veroeffentlicht wird, sobald die Folge fertig und freigegeben ist,
egal wie spaet - Dauerregel: nie wegen Verspaetung verwerfen. Laeuft beim naechsten Slot noch eine Produktion, startet
die neue trotzdem (die Schritte thema..metadaten laufen parallel, nur der GPU-lastige Rohschnitt wartet nacheinander,
siehe schnitt_vorbereiten/vorrang_fuer) - nie ausfallen lassen.

Gestartet von der resident laufenden Pipeline (Aufgabe AbakosNewsroomPipeline, orchestrator/pipeline.py ruft pro
Tick pruefen_und_starten() auf) - kein eigener Windows-Task; seit 05.10.2026 als Langlauf (Jarvis tools/langlauf.py),
falls erreichbar. Pro Slot startet der Lauf als eigener, losgeloester Prozess (pythonw, kein Fenster) und arbeitet
diese Schritte ab (jeder Schritt wird bei einem Neustart uebersprungen, wenn sein Ergebnis schon da ist):

  0 thema       tools/weltlage_themen.py: Recherche (Rohmeldungen der Pipeline), drei Storylines A/B/C mit Titel als
                Frage + ein Satz Inhalt + gruene Bildquellen, Empfehlung; Themenpool (state/weltlage_themenpool.json)
                wird bevorzugt angeboten. Rueckfrage an Telegram (Knoepfe A/B/C) und Beta-App
                (tools/weltlage_entscheid.py), NEWS_WELTLAGE_THEMENWAHL_MINUTEN warten, sonst Empfehlung. Freitext zur
                Wahl geht als Hinweis ins Skript (vorgabe.txt). Ergebnis: wahl.json, news.json, vorgabe.txt.
                Vorab gewaehlte Storyline (Zustand "vorgabe": {titel, inhalt}) = keine Rueckfrage.
  1 skript      tools/weltlage_skript.py --texte [--news news.json --vorgabe vorgabe.txt] (Analyse-Prompt)
  2 aussprache  tts/aussprache_lexikon.py lerne_aus_folge + tts/aussprache_pruefung.py pruefe_folge
                (Fehler = ohne neuen Eintrag weiter; Meldungen in <ordner>/aussprache_pruefung.json)
  3 bilder      Screenshots der Quellartikel pro Meldung (video/sources.capture) -> bilder.json
  4 stimme      tools/weltlage_tts.py (Chatterbox-Klon laut Profil, GPU-Warteschlange; nur geaenderte Szenen neu)
  5 schnitt     Zuerst tools/weltlage_broll.py --vorbereiten (Stufe 1, seit 19.10.2026 vorgezogen: Einsatzstellen +
                Darstellungsart + Clips, braucht nur texte.json/audio/*.wav), dann tools/weltlage_rohschnitt.py
                (feste Szenen eingefroren, Lipsync Guidance 2.0, GPU-Warteschlange) - der liest den B-Roll-Plan und
                laesst den Mundabgleich fuer Zeitspannen aus, die nachher vollflaechig ueberdeckt werden (Variante
                "voll"). Seit 05.10.2026: keine feste Frist mehr, beendet wird nur bei Stillstand (STILLSTAND_MIN
                ohne neues Log/neue Datei), dann ein zweiter Versuch aus dem LatentSync-Cache; ein noch laufender
                Rohschnitt derselben Folge (abgeloester Vorgaenger-Lauf) wird uebernommen statt doppelt gestartet;
                Rohschnitte verschiedener Folgen laufen nacheinander (die fruehere Folge wird zuerst fertig).
  6 broll       tools/weltlage_broll.py --video (NEWS_WELTLAGE_BROLL=1; gruene Quellen; Fehler -> ohne Clips weiter;
                Stufe 1 liegt meist schon aus Schritt 5 vor, baut hier nur noch die Ebenen auf dem fertigen Master)
  7 abnahme     tools/weltlage_abnahme.py (Fehler = nie automatisch veroeffentlichen, nur melden). Fehler "Folge zu
                kurz" (Mindestlaenge 8:00 Min., Marlons Entscheid 04.10.2026 23:53): einmal automatisch ueber
                tools/weltlage_ueberarbeiten.py verlaengern (mehr Tiefe statt Fuellstoff) und die Schritte
                stimme..metadaten erneut rendern (MAX_LAENGE_RUNDEN); schlaegt das erneut fehl, Abbruch wie jeder
                andere Abnahme-Fehler.
  8 thumbnail   video/weltlage_thumbnail.py (Latara-Foto nach Stimmung aus Marlons Ordner, rechts, textfrei)
  9 metadaten   Titel (staerkste Frage-Variante), Beschreibung, Tags -> metadaten.json
 10 warten      seit 16.10.2026 reiner Durchlaufschritt (kein Slot mehr, auf den gewartet wuerde) - sobald die
                Produktion fertig ist, geht es direkt in die Freigabe, egal wie spaet
 11 freigabe    Video (Telegram-Fassung, Ton kopiert, als Dokument) + Thumbnail + Titel an Telegram, Text + Knoepfe an
                die Beta-App: «Freigeben» = sofort veroeffentlichen, «Stopp» = nicht veroeffentlichen, «Feedback» =
                tools/weltlage_ueberarbeiten.py setzt die Aenderungen um, nur betroffene Szenen werden neu gerendert
                (Schritte stimme..metadaten erneut), das Video kommt neu und das Fenster startet von vorn (hoechstens
                NEWS_WELTLAGE_MAX_FEEDBACK_RUNDEN, danach nur noch Freigeben/Stopp). Keine Reaktion innert
                NEWS_WELTLAGE_FREIGABE_MINUTEN = automatisch veroeffentlichen. Seit 13.10.2026 (Marlons Kritik: Themen
                zu frueh gewaehlt, bei Veroeffentlichung nicht mehr aktuell): th.aktualitaet_pruefen() laeuft schon
                hier, direkt in dieser Nachricht - nicht erst spaeter ueber die separate Nachpruefung der
                Weltlage-Wache (jarvis/tools/weltlage_wache.py). Seit 16.10.2026 (derselbe Rueckfall nochmal: die
                Warnung allein aenderte nichts, wenn Marlon nicht reagierte - der Normalfall war "automatisch
                veroeffentlichen"): findet der Check neue Meldungen, versucht _aktualitaet_aktualisieren() IMMER
                AUTOMATISCH (ohne auf Marlon zu warten, kein Zeitfenster-Vorbehalt mehr - es gibt keinen Slot, den
                das noch gefaehrden koennte) ueber dieselbe Feedback-Maschine (tools/weltlage_ueberarbeiten.py) einen
                kurzen, vorsichtig attribuierten Satz zur neuen Entwicklung zu ergaenzen (nur, wenn das Modell etwas
                Konkretes findet, sonst bleibt alles wie es ist); danach sieht Marlon in der Freigabe-Nachricht
                entweder "automatisch aktualisiert" oder (wenn das Modell nichts Konkretes fand) weiterhin die
                Warnung und kann mit Feedback/Stopp reagieren.
 12 upload      upload/youtube_playwright.upload_datei - direkt in NEWS_WELTLAGE_UPLOAD_VISIBILITY (Standard seit
                16.10.2026: keine festen Slots mehr, also kein Vorab-Privat-Upload); NEWS_WELTLAGE_UPLOAD_VORAB=1
                bleibt als manuelle Ausnahme fuer einen gewollten Punkt-Termin; NEWS_WELTLAGE_TROCKENLAUF=1 bzw.
                --trocken: nie hochladen
 13 veroeffentlichen  nur relevant, wenn NEWS_WELTLAGE_UPLOAD_VORAB=1 manuell gesetzt wurde: bis zum Slot warten,
                dann youtube_playwright.veroeffentlichen() auf NEWS_WELTLAGE_UPLOAD_VISIBILITY (frischer Studio-
                Status, Entwurf/Sichtbarkeit nachziehen); klappt das nicht, Status «unbestaetigt» -> die
                Weltlage-Wache (Jarvis) zieht in ihrer Nachpruefung nach
 14 meldung     Link an Telegram + Beta-App bzw. Fehlermeldung mit Schritt
 15 frage_kommentar  seit 19.10.2026 (Marlon-Auftrag, Task 20261019-115203-a41d): die Kommentarfrage aus
                metadaten.json (schon vom Analyse-Prompt erzeugt, bisher nur in der Beschreibung) wird jetzt
                ZUSAETZLICH als eigener Kommentar gepostet und angeheftet (upload/youtube_kommentar.py) -
                Diskussion soll direkt unter der eigenen Frage beginnen. Nur wenn oeffentlich bestaetigt;
                ein Fehlschlag wird nur geloggt, gefaehrdet die Veroeffentlichung nie.

Vorrang (07.10.2026, Auswertung 01.-07.10.: Zusatz-/Nachhol-Folgen belegten den Rohschnitt bis zu 9 h und liessen die
regulaeren Folgen ausfallen oder Stunden zu spaet erscheinen; seit 16.10.2026 gibt es keine Verwerfen-Frist mehr,
aber den Vortritt-Mechanismus weiterhin): Folgen ausserhalb der regulaeren Slots (Nachhol/Sonder/von Hand) lassen den
regulaeren Folgen beim Rohschnitt den Vortritt (vorrang_fuer). Abnahme-Fehler, die nur den Gesamtpegel betreffen
(True Peak/Lautheit), heilt der Lauf selbst: nur den Master-Ton neu machen (Sekunden).

Der fruehere Schritt "endscreen" (upload/endscreen_playwright.set_endscreen, YouTube-Studio-Endscreen "2 Video +
Abo" per Playwright) ist seit 04.10.2026 entfernt (Marlon: die Video-Felder blieben leer, weil Studios eigene
Automatik ohne genug Kanalhistorie nichts findet) - ersetzt durch die Szene Abschluss im Video selbst
(tools/weltlage_abschluss.py: Latara, Logo, animierter Abo-Hinweis, keine Verweise auf andere Videos).

Zustand: state/weltlage_tageslauf.json, Rueckfragen state/weltlage_entscheid/, Log pro Lauf <folge>/tageslauf.log.
Pause ohne Code-Aenderung: Datei state/weltlage_tageslauf.pause anlegen (loeschen = weiter).

    python tools/weltlage_tageslauf.py status
    python tools/weltlage_tageslauf.py zeitplan                     (Slots, gemessene Produktionsdauer, Startzeiten)
    python tools/weltlage_tageslauf.py lauf --slot 11:00 [--datum 2026-10-03] [--bis metadaten] [--ordner DIR]
                                            [--nur thema,skript] [--trocken] [--themenwahl-min 2] [--freigabe-min 2]
    python tools/weltlage_tageslauf.py metadaten <folgenordner>
    python tools/weltlage_tageslauf.py master-neu <folgenordner> <master.mp4>   (nur Master-Ton neu, Sekunden)
    python tools/weltlage_tageslauf.py sofort 2026-10-10_19:00 [--grund "Marlon per Telegram"]
        (seit 10.10.2026, Task 3ba8: Marlons «sofort veröffentlichen» für EINEN Lauf - Schritt warten überspringt
        Freigabefenster/Slot, freigabe stellt keine Rückfrage, upload geht direkt in NEWS_WELTLAGE_UPLOAD_VISIBILITY
        statt privat vorab. Ein schon laufender Tageslauf liest den Schalter erst beim nächsten Start seines Schritts;
        schläft er bereits im Schritt warten, Langlauf abbrechen und neu starten - fertige Schritte werden übersprungen.)
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
from config.settings import (DATA_DIR, NEWS_WELTLAGE_AKTUALISIERUNG_AUTO,
                             NEWS_WELTLAGE_BROLL, NEWS_WELTLAGE_BROLL_OHNE_KI,
                             NEWS_WELTLAGE_FREIGABE_MINUTEN,  # noqa: E402
                             NEWS_WELTLAGE_MAX_FEEDBACK_RUNDEN,
                             NEWS_WELTLAGE_PRODUKTION_STUNDEN, NEWS_WELTLAGE_SHORTS, NEWS_WELTLAGE_SHORTS_MAX,
                             NEWS_WELTLAGE_SHORTS_VERZUG_MINUTEN, NEWS_WELTLAGE_SLOTS, NEWS_WELTLAGE_TAEGLICH,
                             NEWS_WELTLAGE_THEMENWAHL_MINUTEN, NEWS_WELTLAGE_TITEL_BREAKING,
                             NEWS_WELTLAGE_TITEL_BREAKING_PRAEFIX, NEWS_WELTLAGE_TROCKENLAUF,
                             NEWS_WELTLAGE_UPLOAD_VISIBILITY, NEWS_WELTLAGE_UPLOAD_VORAB, STATE_DIR)

ZUSTAND = STATE_DIR / "weltlage_tageslauf.json"
PAUSE = STATE_DIR / "weltlage_tageslauf.pause"
PY = ROOT / ".venv" / "Scripts" / "python.exe"
PYW = ROOT / ".venv" / "Scripts" / "pythonw.exe"
LS_PY = ROOT / ".venv-lipsync" / "Scripts" / "python.exe"
SCHRITTE = ["thema", "skript", "aussprache", "bilder", "stimme", "schnitt", "broll", "abnahme", "thumbnail",
            "metadaten", "warten", "freigabe", "upload", "veroeffentlichen", "meldung", "frage_kommentar",
            "shorts"]
PRODUKTION = ["stimme", "schnitt", "broll", "abnahme", "thumbnail", "metadaten"]   # nach Feedback erneut
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
KI_HINWEIS = ("Moderatorin Latara und ihre Stimme sind KI-generiert. Fakten und Zitate stammen aus den unten "
              "verlinkten Quellen; Lataras Einschätzungen sind im Video als ihre Meinung gekennzeichnet.")
FESTE_TAGS = ["Weltlage Kompakt", "Nachrichten", "Weltpolitik", "Analyse", "Weltlage", "News Deutsch"]
MAX_NEUSTARTS = 3
MAX_LAENGE_RUNDEN = 1   # hoechstens ein automatischer Verlaengerungsversuch bei "Folge zu kurz" (Abnahme 4i)
# Produktion ohne Rohschnitt (Skript, Bilder, Stimme, B-Roll, Abnahme, Thumbnail), gemessen 02.10.: rund 1 h
NEBENSCHRITTE_STUNDEN = 1.0
PRODUKTION_FALLBACK_STUNDEN = 6.5
# Vorfall 05.10.2026 (0 von 2 Folgen): seit der Mindestlaenge 8:00 (04.10.) spricht Latara ~550 s statt ~350 s; die
# Vertonung brauchte 2,6-2,8 h (Grenze 3 h) und der Rohschnitt mit Lipsync-HD ~8 h (feste Grenze 8 h) - der 11:00-Lauf
# wurde nach 8 h abgeschossen, der Zeitplan rechnete weiter mit 5,9 h, weil er nur FERTIGE (kuerzere) Rohschnitte
# zaehlte. Jetzt: Dauer pro gesprochener Sekunde aus den Tageslauf-Logs (auch abgebrochene Laeufe als Untergrenze),
# hochgerechnet auf die aktuelle Sprechlaenge; Unterprozesse enden nur bei echtem Stillstand.
NEBEN_OHNE_STIMME_STUNDEN = 0.5    # Skript, Bilder, B-Roll, Abnahme, Thumbnail, Metadaten (gemessen ~20-30 min)
MIN_SPRECH_S = 520                 # Sprechdauer einer 8-Min.-Folge (Abnahme 4i) ohne feste Szenen, gemessen 05.10.
PRODUKTION_MAX_STUNDEN = 16.0
STILLSTAND_MIN = 60                # kein neues Log/keine neue Datei so lange = haengt -> Prozessbaum beenden
STIMME_MAX_STUNDEN = 10            # nur Sicherheitsnetz; massgeblich ist der Stillstand
SCHNITT_MAX_STUNDEN = 24
SCHNITT_VERSUCHE = 2               # nach Stillstand einmal neu: fertige LatentSync-Stuecke liegen im Cache


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
_MARKE = re.compile(r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) (\$ \S+|-> Exit|ABBRUCH)")


def schritt_dauern(log_text: str, jetzt: datetime | None = None) -> dict:
    """Dauer (s) des ersten Durchgangs von Vertonung und Rohschnitt aus einem tageslauf.log: von "$ tools/
    weltlage_tts.py" bzw. "$ tools/weltlage_rohschnitt.py" bis zur naechsten "-> Exit"/"ABBRUCH"-Marke; laeuft der
    Schritt noch (kein Ende), zaehlt die bisherige Dauer (Untergrenze). Marken werden auch mitten in der Zeile
    gefunden (Unterprozess-Ausgabe ohne Zeilenende davor). Pure Funktion, offline testbar."""
    jetzt = jetzt or datetime.now()
    out, offen = {}, None
    for m in _MARKE.finditer(log_text):
        t, rest = datetime.fromisoformat(m.group(1)), m.group(2)
        if rest.startswith("$ "):
            name = ("stimme" if "weltlage_tts.py" in rest else "schnitt" if "weltlage_rohschnitt.py" in rest else None)
            offen = (name, t) if name and name not in out else None
        elif offen:
            out[offen[0]] = (t - offen[1]).total_seconds()
            offen = None
    if offen:
        out[offen[0]] = max(0.0, (jetzt - offen[1]).total_seconds())
    return out


def sprech_sekunden(ordner: Path) -> float:
    """Summe der vertonten Sprechdauer einer Folge (audio/*.tts.json, Feld laenge_s)."""
    s = 0.0
    for p in (ordner / "audio").glob("*.tts.json"):
        try:
            s += float(json.loads(p.read_text(encoding="utf-8")).get("laenge_s") or 0)
        except (OSError, ValueError, TypeError):
            pass
    return s


def produktion_aus_logs(data_dir: Path, n: int = 4) -> float | None:
    """Produktion (h) aus den letzten n Folgen mit Vertonung + Rohschnitt im Log: Maximum von (Vertonung + Rohschnitt)
    pro gesprochener Sekunde, mal der laengsten jungen Sprechdauer (mindestens MIN_SPRECH_S), + Nebenschritte.
    Abgebrochene/laufende Rohschnitte zaehlen als Untergrenze mit - sonst sieht der Zeitplan nur die Laeufe, die die
    alte Grenze noch geschafft haben (Vorfall 05.10.2026). None = keine verwertbare Messung."""
    raten, sprech = [], []
    for p in sorted(data_dir.glob("weltlage_*/tageslauf.log"), key=lambda p: p.stat().st_mtime, reverse=True):
        if "test" in p.parent.name or "trocken" in p.parent.name:
            continue
        try:
            # ohne End-Marke (z.B. vom Abbruch ueberschriebene Zeile) endet der Schritt mit der letzten Log-Aenderung
            d = schritt_dauern(p.read_text(encoding="utf-8", errors="replace"), datetime.fromtimestamp(p.stat().st_mtime))
        except OSError:
            continue
        sp = sprech_sekunden(p.parent)
        if "schnitt" not in d or sp < 60:
            continue
        raten.append((d.get("stimme", 0.0) + d["schnitt"]) / sp)
        sprech.append(sp)
        if len(raten) >= n:
            break
    if not raten:
        return None
    return max(raten) * max(MIN_SPRECH_S, *sprech) / 3600 + NEBEN_OHNE_STIMME_STUNDEN


def produktion_stunden(data_dir: Path | None = None) -> float:
    """Dauer Skript bis fertiges Video. NEWS_WELTLAGE_PRODUKTION_STUNDEN als Zahl = fest; "auto" = gemessen aus den
    Tageslauf-Logs (produktion_aus_logs, seit 05.10.2026), sonst Rohschnitt-Dauer der letzten zwei vollen Folgen
    (data/weltlage_*/*_renderzeiten.json, "gesamt" >= 50 min, Maximum der beiden) + NEBENSCHRITTE_STUNDEN."""
    if NEWS_WELTLAGE_PRODUKTION_STUNDEN not in ("", "auto"):
        try:
            return float(NEWS_WELTLAGE_PRODUKTION_STUNDEN)
        except ValueError:
            pass
    gemessen = produktion_aus_logs(data_dir or DATA_DIR)
    if gemessen is not None:
        return round(min(PRODUKTION_MAX_STUNDEN, max(3.0, gemessen)), 2)
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


SCHNITT_FALLBACK_STUNDEN = 9.0
VOR_SCHNITT_STUNDEN = 3.0     # Themenwahl + Skript + Vertonung, bis ein Lauf die Karte fuer den Rohschnitt braucht


def geaenderte_szenen_seit_feedback(ordner: Path) -> list[str] | None:
    """Szenen-IDs, die sich in der letzten Feedback-Runde geaendert haben (Diff aktuelle texte.json gegen die
    juengste texte.vor_feedback_<N>.json, die weltlage_ueberarbeiten.py davor sichert) - None ohne Feedback-Runde
    oder ohne Vergleichsbasis. Wichtig fuer einen von Grund auf neu gestarteten Lauf (Resume/Langlauf/PC-Neustart):
    der bekommt dieselbe Information wie der noch lebende Prozess, der das Feedback entgegengenommen hat (Vorfall
    16.10.2026: ein Resume rechnete trotz nur 2 geaenderter Szenen wieder mit der vollen Rohschnitt-Dauer)."""
    snaps = sorted(ordner.glob("texte.vor_feedback_*.json"),
                   key=lambda p: int(p.stem.rsplit("_", 1)[-1]) if p.stem.rsplit("_", 1)[-1].isdigit() else -1)
    if not snaps or not (ordner / "texte.json").exists():
        return None
    try:
        vorher = json.loads(snaps[-1].read_text(encoding="utf-8"))["szenen"]
        jetzt = json.loads((ordner / "texte.json").read_text(encoding="utf-8"))["szenen"]
    except (OSError, KeyError, json.JSONDecodeError):
        return None
    alt_text = {s["id"]: s.get("text") for s in vorher}
    return [s["id"] for s in jetzt if s.get("text") != alt_text.get(s["id"])]


def schnitt_stunden(ordner: Path, data_dir: Path | None = None, n: int = 4) -> float:
    """Erwartete Rohschnitt-Dauer dieser Folge: Rohschnitt-Zeit pro gesprochener Sekunde der letzten n Folgen
    (Maximum, wie produktion_aus_logs) mal Sprechdauer dieser Folge. Mit NEWS_WELTLAGE_SKIP_SZENEN (fertige
    Sprechszenen, nur Montage) 0,5 h."""
    if os.environ.get("NEWS_WELTLAGE_SKIP_SZENEN", "").strip():
        return 0.5
    raten = []
    for p in sorted((data_dir or DATA_DIR).glob("weltlage_*/tageslauf.log"), key=lambda p: p.stat().st_mtime,
                    reverse=True):
        if "test" in p.parent.name or "trocken" in p.parent.name or p.parent == ordner:
            continue
        try:
            d = schritt_dauern(p.read_text(encoding="utf-8", errors="replace"),
                               datetime.fromtimestamp(p.stat().st_mtime))
        except OSError:
            continue
        sp = sprech_sekunden(p.parent)
        if d.get("schnitt", 0) < 1800 or sp < 60:   # unter 30 min = Montage aus dem Cache, keine Messung
            continue
        raten.append(d["schnitt"] / sp)
        if len(raten) >= n:
            break
    sp = max(sprech_sekunden(ordner), 60.0)
    return round(max(raten) * sp / 3600, 2) if raten else SCHNITT_FALLBACK_STUNDEN


def regulaer(key: str, slots: list[str] | None = None) -> bool:
    """Gehoert der Schluessel zu einem regulaeren Slot (NEWS_WELTLAGE_SLOTS)? Nachhol-, Sonder- und von Hand
    angelegte Folgen haben andere Uhrzeiten."""
    return key.rpartition("_")[2] in (NEWS_WELTLAGE_SLOTS if slots is None else slots)


def vorrang_fuer(key: str, zustand: dict, jetzt: datetime, schnitt_h: float,
                 slots: list[str] | None = None, vor_schnitt_h: float = VOR_SCHNITT_STUNDEN) -> str | None:
    """Fuer eine Folge ausserhalb der regulaeren Slots: Grund, warum ihr Rohschnitt jetzt einer regulaeren Folge den
    Vortritt lassen muss, sonst None. Vortritt hat (a) jede regulaere Folge, die gerade produziert und ihren Master
    noch nicht hat, und (b) der naechste noch nicht gestartete regulaere Lauf (Start = Slot, seit 16.10.2026 keine
    Vorlauf-Rueckrechnung mehr), wenn dieser Rohschnitt bis dahin (Start + vor_schnitt_h) nicht fertig waere.
    Regulaere Folgen warten nie auf so etwas. Pure Funktion."""
    slots = NEWS_WELTLAGE_SLOTS if slots is None else slots
    if regulaer(key, slots):
        return None
    vor_schnitt = ("thema", "skript", "aussprache", "bilder", "stimme", "schnitt")
    for k, e in sorted(zustand.items()):
        if k == key or not isinstance(e, dict) or not regulaer(k, slots) or e.get("trocken"):
            continue
        if e.get("status") == "laeuft" and e.get("schritt") in vor_schnitt:
            return f"reguläre Folge {k} produziert gerade (Schritt {e.get('schritt')})"
    for tag in (jetzt.date(), jetzt.date() + timedelta(days=1)):
        for slot in slots:
            k = f"{tag.isoformat()}_{slot}"
            if (zustand.get(k) or {}).get("status"):
                continue
            start = slot_zeit(tag.isoformat(), slot)
            braucht_karte = start + timedelta(hours=vor_schnitt_h)
            if start > jetzt - timedelta(hours=1) and jetzt + timedelta(hours=schnitt_h) > braucht_karte:
                return (f"reguläre Folge {k} braucht die Karte ab {braucht_karte:%d.%m. %H:%M}, dieser Rohschnitt "
                        f"(~{schnitt_h:g} h) wäre bis dahin nicht fertig")
    return None


PEGEL_FEHLER = re.compile(r"^(True Peak|Lautheit) ")


def nur_pegel_fehler(info: dict) -> bool:
    """Liegen alle Abnahme-Fehler nur am Gesamtpegel des Masters (True Peak / integrierte Lautheit)? Dann reicht es,
    den Master-Ton neu zu machen (weltlage_rohschnitt.master_erneuern) - kein Neuschnitt. Pure Funktion."""
    fehler = info.get("fehler") or []
    return bool(fehler) and all(PEGEL_FEHLER.match(f) for f in fehler)


def master_neu(ordner: Path, master: Path, log=print) -> dict:
    """Master-Ton neu (Sekunden) und alles verwerfen, was aus dem alten Master abgeleitet ist (B-Roll-Fassung,
    Abnahme, Telegram-Fassung), damit B-Roll und Abnahme frisch laufen."""
    from weltlage_rohschnitt import master_erneuern
    res = master_erneuern(ordner / "_schnitt", master)
    for q in (master.with_name(master.stem + "_clips.mp4"), master.with_name(master.stem + "_abnahme.json"),
              ordner / "telegram" / f"{master.stem}_telegram.mp4", ordner / "telegram" / f"{master.stem}_clips_telegram.mp4"):
        q.unlink(missing_ok=True)
    log(f"Master-Ton neu: {res.get('nachher')} (Begrenzer-Versuche {res.get('tp_versuche')})")
    return res


def faellig(jetzt: datetime, zustand: dict) -> list[tuple[str, str]]:
    """[(datum, slot)] deren Produktionsstart faellig ist (jetzt >= Slot) und fuer die noch kein Lauf existiert, der
    Lauf abgestuerzt ist (PID weg, Status nicht final) oder ein angehaltener Lauf zum Fortsetzen markiert ist
    ("auto_fortsetzen": true, z.B. der von Hand vorproduzierte erste Lauf). Seit 16.10.2026 (Marlons Ansage: keine
    festen Veroeffentlichungs-Slots mehr): Slot = Produktionsstart direkt, keine Vorlauf-Rueckrechnung und kein
    Verspaetungs-Limit mehr - eine faellige Folge wird nie aufgegeben; laeuft beim naechsten Slot noch eine andere
    Produktion, startet die neue trotzdem (serialisiert sich beim Rohschnitt selbst, siehe schnitt_vorbereiten/
    vorrang_fuer)."""
    out = []
    for tag in (jetzt.date(), jetzt.date() + timedelta(days=1)):
        for slot in NEWS_WELTLAGE_SLOTS:
            t = slot_zeit(tag.isoformat(), slot)
            if jetzt < t:
                continue
            e = zustand.get(f"{tag.isoformat()}_{slot}")
            if e is None or not e.get("status"):     # ohne Status = nur vorgemerkt (z.B. "vorgabe")
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
        ll = _langlauf()
        if ll is not None:
            # Als Langlauf (Jarvis tools/langlauf.py): eigene Aufsicht ausserhalb des Pipeline-Prozessbaums (ein
            # Neustart der Pipeline-Aufgabe beendet den Lauf nicht mehr), setzt Abstuerze selbst fort, Doppelstart-
            # Schutz ueber Schluessel + Befehlszeile (offener Faden 05.10.2026).
            try:
                e = ll.weltlage_starten(datum, slot, max_versuche=MAX_NEUSTARTS)
                if e.get("schon_aktiv"):
                    continue
                _eintrag(key, status="laeuft", pid=e.get("aufsicht_pid"), langlauf=e.get("id"),
                         gestartet=jetzt.isoformat(timespec="seconds"), neustarts=neustarts)
                log(f"Weltlage-Tageslauf {key} als Langlauf {e.get('id')} gestartet (Neustart {neustarts})")
                gestartet.append(key)
                continue
            except Exception as ex:   # noqa: BLE001 - dann wie bisher direkt
                log(f"Weltlage-Tageslauf {key}: Langlauf ging nicht ({ex}), starte direkt")
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
    slots = []
    for slot in NEWS_WELTLAGE_SLOTS:
        t = slot_zeit(jetzt.date().isoformat(), slot)
        slots.append({"slot": slot, "produktion_ab": slot,
                      "themenwahl_bis_ca": f"{t + timedelta(minutes=NEWS_WELTLAGE_THEMENWAHL_MINUTEN):%H:%M}",
                      "voraussichtlich_fertig_ca": f"{t + timedelta(hours=prod):%H:%M}",
                      "oeffentlich": "sobald fertig und freigegeben (kein fester Slot mehr)"})
    return {"produktion_h": prod, "themenwahl_min": NEWS_WELTLAGE_THEMENWAHL_MINUTEN,
            "freigabe_min": NEWS_WELTLAGE_FREIGABE_MINUTEN, "slots": slots}


# ------------------------------------------------------------------ Schritte
class Abbruch(RuntimeError):
    pass


class Gestoppt(RuntimeError):
    pass


STILLSTAND_RC = -9   # Rueckgabe von _run, wenn der Prozessbaum wegen Stillstand/Obergrenze beendet wurde
POLL_S = 30


def _prozesse(skript: str) -> list[dict]:
    """Laufende Prozesse, deren Befehlszeile `skript` enthaelt: [{pid, ppid, cmd}] (CIM, psutil fehlt in .venv)."""
    ps = ("Get-CimInstance Win32_Process -Filter \"CommandLine like '%" + skript.replace("'", "") + "%'\" | "
          "Select-Object ProcessId,ParentProcessId,CommandLine | ConvertTo-Json -Compress")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True,
                             text=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW, timeout=60).stdout
        d = json.loads(out) if out.strip() else []
    except Exception:   # noqa: BLE001
        return []
    d = d if isinstance(d, list) else [d]
    return [{"pid": int(x["ProcessId"]), "ppid": int(x["ParentProcessId"] or 0), "cmd": x.get("CommandLine") or ""}
            for x in d if x.get("CommandLine")]


def fremde_laeufe(prozesse: list[dict], skript: str, ordner: Path, eigene: bool) -> list[int]:
    """Oberste PIDs (venv-Starter statt Kind) der Prozesse mit `skript`, die zu diesem Folgenordner gehoeren
    (eigene=True) bzw. zu einem anderen (eigene=False). Pure Funktion, offline testbar."""
    rx = re.compile(re.escape(str(Path(ordner)).lower()) + r"(?![\w])")
    # nur echte Aufrufe "...python.exe tools/<skript> <ordner>", keine Shell/grep/python -c mit dem Text darin
    aufruf = re.compile(r"python[w]?(?:\.exe)?\"?\s+(?:\S*[\\/])?tools[\\/]" + re.escape(skript.lower()) + r"\s")
    passend = [p for p in prozesse if aufruf.search(p["cmd"].lower()) and bool(rx.search(p["cmd"].lower())) == eigene]
    pids = {p["pid"] for p in passend}
    return sorted(p["pid"] for p in passend if p["ppid"] not in pids)


def _baum_beenden(pid: int):
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, creationflags=NO_WINDOW)


def _aktivitaet(log, ordner: Path | None) -> float:
    """Juengste Aenderung (mtime) von Log, Arbeitsordnern (_schnitt, audio) - Lebenszeichen eines Schritts."""
    t = log.datei.stat().st_mtime if log.datei.exists() else 0.0
    for sub in ("_schnitt", "audio") if ordner else ():
        for wurzel, _, dateien in os.walk(ordner / sub):
            for d in dateien:
                try:
                    t = max(t, os.stat(os.path.join(wurzel, d)).st_mtime)
                except OSError:
                    pass
    return t


def _warten_auf_lauf(skript: str, ordner: Path, log, eigene: bool, still_min: float = STILLSTAND_MIN) -> bool:
    """Wartet, solange ein `skript`-Prozess fuer diesen Ordner (eigene=True: z.B. vom abgestuerzten/abgeloesten
    Vorgaenger-Lauf, nie doppelt starten) bzw. fuer einen anderen Ordner (eigene=False: Rohschnitte nacheinander statt
    verzahnt, die fruehere Folge zuerst fertig) laeuft. Eigener Prozess ohne Lebenszeichen seit still_min -> beenden.
    Rueckgabe: True, wenn ueberhaupt gewartet wurde."""
    gewartet, letzte_meldung = False, 0.0
    while True:
        pids = fremde_laeufe(_prozesse(skript), skript, ordner, eigene)
        if not pids:
            return gewartet
        if not gewartet:
            log(f"{skript} läuft schon ({'für diese Folge' if eigene else 'für eine andere Folge'}, PID "
                f"{', '.join(map(str, pids))}) - warte darauf statt {'doppelt zu starten' if eigene else 'gleichzeitig'}")
            gewartet = True
        if eigene and time.time() - _aktivitaet(log, ordner) > still_min * 60:
            log(f"{skript} ohne Lebenszeichen seit {still_min:.0f} min - beende PID {pids}")
            for p in pids:
                _baum_beenden(p)
        elif time.time() - letzte_meldung > 1800:
            letzte_meldung = time.time()
            if not eigene:
                log(f"warte weiter auf {skript} der anderen Folge (PID {', '.join(map(str, pids))})")
        time.sleep(60)


def _run(cmd: list, log, timeout_h: float = 6, python=None, ordner: Path | None = None,
         still_min: float | None = None) -> int:
    """Schritt als Unterprozess ohne Fenster. HuggingFace offline (alle Modelle liegen im Cache): am 02.10. 23:43
    hing tools/weltlage_tts.py 10 min still an einer CDN-Verbindung des Hub-Checks; HF_HUB_OFFLINE=0 in der Umgebung
    hebt das auf.
    still_min: statt einer festen Frist nur bei Stillstand beenden (kein neues Log/keine neue Datei unter ordner seit
    still_min Minuten); timeout_h bleibt als Obergrenze. Beendet wird der ganze Prozessbaum (subprocess.run mit
    timeout traf nur den venv-Starter). Rueckgabe STILLSTAND_RC, wenn beendet wurde."""
    log("$ " + " ".join(str(c) for c in cmd))
    t0 = time.time()
    with open(log.datei, "a", encoding="utf-8") as f:
        p = subprocess.Popen([str(python or PY), *map(str, cmd)], cwd=str(ROOT), stdout=f, stderr=subprocess.STDOUT,
                             stdin=subprocess.DEVNULL, creationflags=NO_WINDOW,
                             env={"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", **os.environ,
                                  "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"})
        while True:
            try:
                rc = p.wait(timeout=POLL_S)
                break
            except subprocess.TimeoutExpired:
                pass
            grund = None
            if time.time() - t0 > timeout_h * 3600:
                grund = f"Obergrenze {timeout_h:g} h erreicht"
            elif still_min and time.time() - max(t0, _aktivitaet(log, ordner)) > still_min * 60:
                grund = f"seit {still_min:.0f} min kein Lebenszeichen (Log/Dateien)"
            if grund:
                log(f"{grund} - beende Prozessbaum {p.pid}")
                _baum_beenden(p.pid)
                p.wait()
                rc = STILLSTAND_RC
                break
    log(f"-> Exit {rc}")
    return rc


def _nur_montage(ordner: Path) -> bool:
    """True, wenn NEWS_WELTLAGE_SKIP_SZENEN wirklich jede Sprechszene der Folge abdeckt (keine Lipsync-Arbeit mehr
    noetig, reine Montage) - nicht schon, wenn nur ein Teil der Szenen eingefroren ist (Vorfall 16.10.2026: ein
    Feedback-Neuschnitt mit 18 von 20 eingefrorenen Szenen haette sonst faelschlich als "reine Montage" gegolten und
    sich weder hinter einem fremden Rohschnitt angestellt noch regulaeren Folgen Vortritt gelassen, obwohl er die
    GPU fuer die 2 geaenderten Szenen noch braucht)."""
    skip = {s.strip() for s in os.environ.get("NEWS_WELTLAGE_SKIP_SZENEN", "").split(",") if s.strip()}
    if not skip:
        return False
    try:
        alle = {s["id"] for s in json.loads((ordner / "texte.json").read_text(encoding="utf-8"))["szenen"]}
    except (OSError, KeyError, json.JSONDecodeError):
        return False
    return alle <= skip


# Feste, eingefrorene Sprechszenen (config/brand/<name>/aktiv.json) und ihr Builder (build + freeze, laeuft im
# Lipsync-venv LS_PY, reiht sich selbst in die GPU-Warteschlange ein). Reihenfolge = Reihenfolge im Video.
FESTE_SZENEN = {"begruessung": "tools/weltlage_begruessung.py", "verabschiedung": "tools/weltlage_verabschiedung.py",
                "abschluss": "tools/weltlage_abschluss.py"}


def feste_szenen_veraltet(metas: dict, guidance: float, hd: bool, pipeline: dict) -> dict:
    """Welche eingefrorenen Sprechszenen passen nicht mehr EXAKT zum heutigen Lipsync-Standard? metas: {name:
    aktiv.json-Inhalt oder None (nicht eingefroren)}. Rueckgabe {name: [Abweichungen]} nur fuer veraltete Szenen.
    Streng (auch eine staerkere Drosselstufe zaehlt): vor einem NEUEN Render sollen Begruessung/Abschluss mit
    derselben Staerke gebaut sein wie die Meldungen, sonst bewegt sich der Mund in der Begruessung anders als im
    Rest der Folge. Fassungen ohne die Felder (vor 02./03.10.2026) gelten wie bisher nur als Warnung der Abnahme,
    nicht als veraltet. Reine Funktion (Dateien kommen vom Aufrufer), offline testbar.
    Grund (Vorfall 19.10.2026, Task 20261020-002406-1486): Marlons Umstellung auf Drosselstufe 2 (Guidance 2,0 ->
    1,5) kam in den Code, ohne dass jemand Begruessung/Abschluss neu einfror - jede folgende Folge waere an der
    Abnahme («eingefroren mit Guidance 2.0 statt Standard 1.5 - neu bauen») gescheitert, und die Wache kannte dafuer
    keinen Fix. Jetzt baut der Tageslauf sie vor dem Rohschnitt selbst neu (feste_szenen_aktualisieren)."""
    import weltlage_abnahme as abn
    veraltet = {}
    for name, meta in metas.items():
        if not meta:
            continue
        probleme = [p for p in abn.guidance_probleme(meta, guidance, hd, streng=True) if "guidance" in meta]
        probleme += [p for p in abn.pipeline_probleme(meta, pipeline, streng=True) if "pipeline" in meta]
        if probleme:
            veraltet[name] = probleme
    return veraltet


def feste_szenen_aktualisieren(log) -> list[str]:
    """Vor einem neuen Rohschnitt: veraltete eingefrorene Sprechszenen (feste_szenen_veraltet) mit den heutigen
    Einstellungen neu bauen und einfrieren (build + freeze im Lipsync-venv; Ton bleibt gleich, die Builder
    ueberspringen die Vertonung, solange der Stimm-Nachweis zum aktiven Profil passt). Scheitert ein Bau, laeuft
    die Folge trotzdem weiter - die Abnahme meldet die veraltete Szene dann wie bisher. Rueckgabe: neu gebaute
    Szenen."""
    from video import freisteller_lipsync as fl
    metas = {}
    for name in FESTE_SZENEN:
        cfg = ROOT / "config" / "brand" / name / "aktiv.json"
        metas[name] = json.loads(cfg.read_text(encoding="utf-8")) if cfg.exists() else None
    veraltet = feste_szenen_veraltet(metas, fl.GUIDANCE, fl.HD, fl.pipeline_signatur())
    gebaut = []
    for name, probleme in veraltet.items():
        log(f"feste Szene {name} passt nicht mehr zum Lipsync-Standard ({'; '.join(probleme)}) - baue sie neu "
            f"(build + freeze, {FESTE_SZENEN[name]})")
        tool = FESTE_SZENEN[name]
        if _run([tool, "build"], log, timeout_h=3, python=LS_PY) != 0:
            log(f"feste Szene {name}: build fehlgeschlagen - Folge laeuft mit der alten Fassung weiter")
            continue
        if _run([tool, "freeze"], log, timeout_h=0.5, python=LS_PY) != 0:
            log(f"feste Szene {name}: freeze fehlgeschlagen - Folge laeuft mit der alten Fassung weiter")
            continue
        gebaut.append(name)
    return gebaut


def schnitt_vorbereiten(key: str, ordner: Path, log, warte_s: float = 300):
    """Vor jedem Rohschnitt-Versuch: (1) ausserhalb der regulaeren Slots den regulaeren Folgen den Vortritt lassen
    (nicht bei reiner Montage); (2) auf einen laufenden Rohschnitt einer anderen Folge warten (nacheinander statt
    verzahnt) - ausser es wird nur montiert (NEWS_WELTLAGE_SKIP_SZENEN deckt alle Szenen ab, kein Lipsync, braucht
    die Karte nicht; Vorfall 07.10.2026: ein reiner Neuschnitt der 03:00-Folge wartete 8 h hinter einem fremden
    Rohschnitt). Seit 16.10.2026 keine Frist-Pruefung mehr (Dauerregel: nie wegen Verspaetung verwerfen) - der
    Rohschnitt wartet notfalls beliebig lange, der Vortritt schuetzt nur die naechste reguläre Folge."""
    nur_montage = _nur_montage(ordner)
    gemeldet, letzte_meldung = None, 0.0
    while True:
        z = _laden()
        sh = schnitt_stunden(ordner)
        jetzt = datetime.now().astimezone()
        # reine Montage braucht die Karte nicht und laesst auch regulaeren Folgen keinen Vortritt (Vorfall 08.10.2026:
        # die fertig gerenderte 07.10.-19:00-Folge haette sonst ~14 h hinter den Rohschnitten von 11:00/19:00 gewartet)
        grund = None if nur_montage else vorrang_fuer(key, z, jetzt, sh, vor_schnitt_h=VOR_SCHNITT_STUNDEN)
        if not grund and not nur_montage:
            pids = fremde_laeufe(_prozesse("weltlage_rohschnitt.py"), "weltlage_rohschnitt.py", ordner, False)
            grund = f"Rohschnitt einer anderen Folge läuft (PID {', '.join(map(str, pids))})" if pids else None
        if not grund:
            if gemeldet:
                _eintrag(key, wartet_auf=None)
            return
        # Lebenszeichen mindestens alle 30 min ins Log (die Weltlage-Wache haelt einen stillen Lauf sonst fuer haengend)
        if grund != gemeldet or time.time() - letzte_meldung > 1800:
            log(f"Rohschnitt wartet: {grund}")
            gemeldet, letzte_meldung = grund, time.time()
            _eintrag(key, wartet_auf=grund[:200])
        time.sleep(warte_s)


def vorab_upload() -> bool:
    """Privat vorab hochladen und zum Slot oeffentlich stellen? Nur wenn das Ziel nicht ohnehin privat ist."""
    return NEWS_WELTLAGE_UPLOAD_VORAB and NEWS_WELTLAGE_UPLOAD_VISIBILITY != "private"


def sofort_aktiv(key: str) -> bool:
    """Marlon hat fuer diesen Lauf «sofort veroeffentlichen» gegeben (`weltlage_tageslauf.py sofort <key>`, Zustand
    Feld "sofort", 10.10.2026 Task 3ba8): kein Warten auf das Freigabefenster oder den Slot, keine Freigabe-Frage,
    Upload direkt in der Ziel-Sichtbarkeit statt privat vorab. Gilt nur fuer diesen einen Schluessel."""
    return bool((_laden().get(key) or {}).get("sofort"))


def vorab_fuer(key: str) -> bool:
    """Privat vorab hochladen? Nein, wenn Marlon fuer den Lauf «sofort» gegeben hat."""
    return vorab_upload() and not sofort_aktiv(key)


def sofort_setzen(key: str, grund: str = "Marlon") -> dict:
    return _eintrag(key, sofort=True, sofort_seit=datetime.now().astimezone().isoformat(timespec="seconds"),
                    sofort_grund=grund)


def laenge_reparatur_noetig(info: dict, runden: int) -> str | None:
    """Prueft, ob eine durchgefallene Abnahme (abnahme.json-Inhalt) am Fehler "Folge zu kurz" lag (Abnahme 4i,
    Marlons Entscheid 04.10.2026 23:53) und noch ein automatischer Verlaengerungsversuch uebrig ist
    (MAX_LAENGE_RUNDEN). Gibt die passende Fehlermeldung zurueck, sonst None (kein Laengenfehler oder Versuche
    aufgebraucht - dann wie jeder andere Abnahme-Fehler abbrechen). Pure Funktion, offline testbar."""
    if runden >= MAX_LAENGE_RUNDEN:
        return None
    return next((f for f in info.get("fehler") or [] if f.startswith("Folge zu kurz")), None)


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
                                  "url": s["url"], "textzeichen": s.get("textzeichen"),
                                  "schlagzeile": s.get("schlagzeile")})
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
    titel = texte["titel"]
    if NEWS_WELTLAGE_TITEL_BREAKING and not titel.upper().startswith("BREAKING"):
        titel = NEWS_WELTLAGE_TITEL_BREAKING_PRAEFIX + titel
    meta = {"title": titel[:100], "description": beschreibung, "tags": tags, "language": "de",
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


def _langlauf():
    """tools/langlauf.py aus Jarvis (None = nicht erreichbar, dann startet die Pipeline den Lauf wie bisher direkt)."""
    try:
        if str(JARVIS_TOOLS) not in sys.path:
            sys.path.append(str(JARVIS_TOOLS))
        import langlauf
        return langlauf
    except Exception:   # noqa: BLE001
        return None


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
                f"({wahl.get('quelle')}). Produktion läuft, das fertige Video kommt vor {slot} zur Freigabe "
                f"und geht um {slot} online.", log)
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


def shorts_erzeugen_und_einreihen(key: str, slot: str, ordner: Path, log):
    """Schritt shorts (Marlon 11.10.2026, erweitert 13.10.2026 auf dauerhafte Freigabe + festen 6-h-Takt nach dem
    ersten echten Short: ~400 Views/8 Likes/4 Abos in 48 h): aus der gerade veroeffentlichten Folge 1-3 vertikale
    Shorts schneiden (tools/weltlage_shorts.py), SHORTS_VERZUG Minuten warten (zeitversetzt, nicht gleichzeitig
    mit der Folge), dann NICHT mehr einzeln per Telegram freigeben lassen, sondern in die Warteschlange legen
    (tools/weltlage_shorts_takt.py) - der Taktgeber (von der Weltlage-Wache stuendlich aufgerufen) laedt daraus
    automatisch oeffentlich hoch, 4x taeglich zu festen, nicht mit den Folgen-Slots kollidierenden Uhrzeiten."""
    if NEWS_WELTLAGE_SHORTS_VERZUG_MINUTEN > 0:
        log(f"Shorts: warte {NEWS_WELTLAGE_SHORTS_VERZUG_MINUTEN:.0f} min nach der Veröffentlichung (zeitversetzt)")
        time.sleep(NEWS_WELTLAGE_SHORTS_VERZUG_MINUTEN * 60)
    # eigener Unterprozess wie Rohschnitt/TTS (nicht im Tageslauf-Prozess importiert): weltlage_shorts.py braucht
    # NEWS_FORMAT=shorts fuer die 9:16-Geometrie, der Tageslauf selbst laeuft aber mit NEWS_FORMAT=landscape und
    # haette das als bereits geladenes Modul (config.settings/video.layout) nicht mehr umschalten koennen.
    rc = _run(["tools/weltlage_shorts.py", ordner, "--max", str(NEWS_WELTLAGE_SHORTS_MAX)], log, timeout_h=1,
             ordner=ordner)
    if rc != 0:
        log("Shorts-Schnitt fehlgeschlagen (siehe Log)")
        return
    shorts_dir = ordner / "shorts"
    shorts = []
    for meta_pfad in sorted(shorts_dir.glob("short_*.json")):
        meta = json.loads(meta_pfad.read_text(encoding="utf-8"))
        mp4 = meta_pfad.with_suffix(".mp4")
        if mp4.exists():
            shorts.append({"mp4": mp4, "meta": meta})
    if not shorts:
        log("Shorts: keine passende Szene gefunden (keine unter 60 s mit eigenem Sprechtext)")
        return
    import weltlage_shorts_takt as takt
    neu = takt.einreihen(key, slot, ordner, shorts)
    log(f"Shorts: {neu} neue Szene(n) in die Warteschlange gelegt (gesamt {len(takt.warteschlange())})")
    if neu:
        _melden(f"Weltlage {slot}", f"{neu} Short(s) in die Warteschlange gelegt, werden automatisch alle 6 h "
                "öffentlich veröffentlicht (keine Einzelfreigabe mehr nötig).", log)


def _aktualitaet_aktualisieren(key: str, slot: str, ordner: Path, master: Path, log, produktion,
                               aktualitaet: dict) -> str | None:
    """Automatische Aktualisierung (16.10.2026, Marlons Rueckfall-Beschwerde: die Warnung vom 13.10. aenderte nichts,
    wenn niemand reagierte). Nutzt dieselbe Feedback-Maschine wie Marlons manuelles Feedback
    (tools/weltlage_ueberarbeiten.py), aber automatisch ausgeloest: bekommt nur Titel+Quelle+Datum der neuen
    Meldungen (keine erfundenen Fakten moeglich) und die Weisung, NUR bei etwas Konkretem einen kurzen, vorsichtig
    attribuierten Satz zu ergaenzen ("Laut <Quelle>...") und sonst nichts zu aendern. Hoechstens ein Versuch pro
    Folge (Zustand aktualitaet_auto, zusaetzlich zur ohnehin einmaligen aktualitaet_hinweis.json in
    weltlage_themen.aktualitaet_pruefen). Gibt die Zusammenfassung zurueck, sonst None (nichts Konkretes gefunden
    oder schon versucht)."""
    z = _laden().get(key) or {}
    if z.get("aktualitaet_auto"):
        return None
    runde = int(z.get("feedback_runden") or 0) + 1
    zeilen = "\n".join(f"- {a['title']} ({a.get('source')}, {(a.get('published_at') or '')[:16]})"
                       for a in aktualitaet["neue_artikel"][:3])
    feedback = (f"[Automatisch, nicht von Marlon] Seit der Recherche gibt es moeglicherweise neue Meldungen zum "
                f"Hauptthema:\n{zeilen}\n\nFalls das eine konkrete neue Entwicklung ist: ergaenze an der passenden "
                "Stelle einen kurzen, vorsichtig formulierten Satz, der die neue Meldung attributiv nennt (z.B. "
                "\"Laut <Quelle> gibt es inzwischen...\"), ohne bestehende Aussagen zu aendern oder neue Fakten/"
                "Zahlen zu erfinden. Ist unklar, ob es wirklich etwas Neues zur Story ist, oder reicht die knappe "
                "Information dafuer nicht: lass alle Szenen unveraendert (leeres \"szenen\"-Objekt).")
    from weltlage_ueberarbeiten import ueberarbeiten
    _eintrag(key, feedback_runden=runde, aktualitaet_auto="laeuft")
    try:
        res = ueberarbeiten(ordner, feedback, runde, master)
    except Exception as ex:   # noqa: BLE001 - automatische Aktualisierung darf die Freigabe nie blockieren
        log(f"Automatische Aktualisierung fehlgeschlagen ({ex}) - nur Warnung")
        _eintrag(key, aktualitaet_auto="fehlgeschlagen")
        return None
    if not res["neu_rendern"]:
        log("Aktualitaets-Check: Modell hat nichts Konkretes gefunden, keine Aenderung")
        _eintrag(key, aktualitaet_auto="nichts_zu_tun")
        return None
    log(f"Automatische Aktualisierung: Szenen {res['szenen']}, {res['zusammenfassung']}")
    alle = [s["id"] for s in json.loads((ordner / "texte.json").read_text(encoding="utf-8"))["szenen"]]
    eingefroren = [sid for sid in alle if sid not in res["szenen"]]
    alt_skip = os.environ.get("NEWS_WELTLAGE_SKIP_SZENEN")
    os.environ["NEWS_WELTLAGE_SKIP_SZENEN"] = ",".join(eingefroren)
    try:
        produktion(PRODUKTION)
    finally:
        if alt_skip is None:
            os.environ.pop("NEWS_WELTLAGE_SKIP_SZENEN", None)
        else:
            os.environ["NEWS_WELTLAGE_SKIP_SZENEN"] = alt_skip
    _eintrag(key, aktualitaet_auto="umgesetzt")
    _melden(f"Weltlage {slot}", f"Automatisch aktualisiert (neue Meldungen seit der Recherche): "
            f"{res['zusammenfassung']}", log)
    return res["zusammenfassung"]


def freigabe_einholen(key: str, slot: str, ordner: Path, master: Path, log, minuten: float, trocken: bool,
                      produktion) -> str:
    """Schritt freigabe. Rueckgabe "freigegeben" | "automatisch"; Stopp -> Gestoppt; Feedback -> Ueberarbeitung +
    produktion() (Schritte stimme..metadaten) + neue Runde."""
    import weltlage_entscheid as ent
    import weltlage_themen as th
    while True:
        z = _laden().get(key) or {}
        runden = int(z.get("feedback_runden") or 0)
        e = _offene_frage(key, "freigabe")
        if e is None:
            try:
                aktualitaet = th.aktualitaet_pruefen(ordner)
            except Exception:   # noqa: BLE001 - Aktualitaets-Check darf die Freigabe nie verhindern
                aktualitaet = None
            auto_hinweis = None
            # seit 16.10.2026 kein Zeitfenster-Vorbehalt mehr (kein Slot mehr, der dadurch gefaehrdet werden koennte)
            if aktualitaet and NEWS_WELTLAGE_AKTUALISIERUNG_AUTO and not trocken:
                auto_hinweis = _aktualitaet_aktualisieren(key, slot, ordner, master, log, produktion, aktualitaet)
            clips = master.with_name(master.stem + "_clips.mp4")
            datei = clips if clips.exists() else master
            meta = json.loads((ordner / "metadaten.json").read_text(encoding="utf-8"))
            frist = datetime.now().astimezone() + timedelta(minutes=minuten)
            optionen = {"freigeben": "Freigeben", "feedback": "Feedback", "stopp": "Stopp"}
            if runden >= NEWS_WELTLAGE_MAX_FEEDBACK_RUNDEN:
                optionen.pop("feedback")
            text = (f"Weltlage Kompakt {slot}{' (TROCKENLAUF, kein Upload)' if trocken else ''}: Video fertig"
                    f"{f' (Fassung {runden + 1})' if runden else ''}.\nTitel: {meta['title']}\n\n"
                    + (f"Ohne Antwort bis {frist:%H:%M} lade ich es hoch und stelle es um {slot} öffentlich auf "
                       f"YouTube (ist {slot} schon vorbei: sofort). Freigeben = um {slot} veröffentlichen, "
                       if vorab_upload() else
                       f"Ohne Antwort bis {frist:%H:%M} veröffentliche ich es automatisch öffentlich auf YouTube. "
                       "Freigeben = sofort, ")
                    + "Stopp = nicht veröffentlichen"
                    + (", Feedback = Änderungen (nur betroffene Szenen werden neu gerendert)." if "feedback" in optionen
                       else ". Die Feedback-Runden sind aufgebraucht."))
            if auto_hinweis:
                text += (f"\n\nHinweis: Seit der Recherche gab es neue Meldungen zum Thema - ich habe automatisch "
                         f"einen aktuellen Satz ergänzt ({auto_hinweis}). Bei Bedarf trotzdem Feedback oder Stopp.")
            elif aktualitaet:
                neue = "\n".join(f"- {a['title']} ({a.get('source')})" for a in aktualitaet["neue_artikel"][:3])
                text += (f"\n\nAchtung, Thema evtl. überholt: seit der Recherche gibt es neue Meldungen dazu:\n{neue}\n"
                         "Bei Bedarf Feedback (Titel/Beschreibung anpassen) oder Stopp statt automatisch veröffentlichen.")
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
        if res["neu_rendern"]:
            # Nur die vom Feedback geaenderten Szenen muessen neu gerendert werden (weltlage_ueberarbeiten.py:
            # die uebrigen liegen schon per Content-Hash im LatentSync-Cache) - das muss auch schnitt_stunden()
            # wissen, sonst schaetzt die Frist-Pruefung mit der vollen Rohschnitt-Dauer der Folge und bricht
            # faelschlich "zu spaet" ab (Vorfall 16.10.2026: 2 von ~20 Szenen geaendert, veranschlagt wie eine
            # komplette Neuproduktion mit ~6,5 h statt Minuten).
            alle = [s["id"] for s in json.loads((ordner / "texte.json").read_text(encoding="utf-8"))["szenen"]]
            eingefroren = [sid for sid in alle if sid not in res["szenen"]]
            alt_skip = os.environ.get("NEWS_WELTLAGE_SKIP_SZENEN")
            os.environ["NEWS_WELTLAGE_SKIP_SZENEN"] = ",".join(eingefroren)
            try:
                produktion(PRODUKTION)
            finally:
                if alt_skip is None:
                    os.environ.pop("NEWS_WELTLAGE_SKIP_SZENEN", None)
                else:
                    os.environ["NEWS_WELTLAGE_SKIP_SZENEN"] = alt_skip
        else:
            produktion(["thumbnail", "metadaten"])


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
    veroeffentlichen = slot_zeit(datum, slot)   # Produktionsstart dieses Slots, kein Veroeffentlichungstermin mehr
    log(f"Tageslauf {key} in {ordner} (Produktionsstart {veroeffentlichen:%d.%m. %H:%M}, veroeffentlicht sobald "
        f"fertig und freigegeben, bis {bis or 'Ende'}{', TROCKENLAUF' if trocken else ''})")

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
            try:                     # Pruefschritt (18.10.2026): meldet, was danach noch heikel klingt
                from tts.aussprache_pruefung import pruefe_folge
                pruefe_folge(ordner, log=log)
            except Exception as ex:  # noqa: BLE001
                log(f"Aussprache-Prüfung uebersprungen: {ex}")
        elif schritt == "bilder" and not (ordner / "bilder.json").exists():
            bilder_holen(ordner, log)
        elif schritt == "stimme":
            if fremde_laeufe(_prozesse("weltlage_rohschnitt.py"), "weltlage_rohschnitt.py", ordner, True):
                # Lauf wurde abgeloest/neu gestartet, waehrend sein Rohschnitt weiterrechnet: der schneidet die
                # vorhandene Vertonung - jetzt neu vertonen (z.B. nach Lexikon-Pflege) passte nicht mehr zum Video
                log("Rohschnitt dieser Folge läuft noch - Vertonung bleibt wie sie ist")
                return
            _warten_auf_lauf("weltlage_tts.py", ordner, log, eigene=True)
            if _run(["tools/weltlage_tts.py", ordner], log, timeout_h=STIMME_MAX_STUNDEN, ordner=ordner,
                    still_min=STILLSTAND_MIN) != 0:
                raise Abbruch("Vertonung fehlgeschlagen")
        elif schritt == "schnitt":
            _warten_auf_lauf("weltlage_rohschnitt.py", ordner, log, eigene=True)
            # Eingefrorene Sprechszenen zuerst an den heutigen Lipsync-Standard anpassen (nur vor einem neuen
            # Render; ein fertiger Master behaelt seine Fassung, die Abnahme toleriert dort eine staerkere Stufe)
            if not master.exists():
                feste_szenen_aktualisieren(log)
            # B-Roll-Planung vorgezogen (Marlon 19.10.2026, Task 20261019-182613-44c1): Stufe 1 von
            # weltlage_broll.py (Einsatzstellen, Darstellungsart, Clips - braucht nur texte.json + audio/*.wav) lief
            # bisher erst im Schritt "broll" NACH dem Rohschnitt; der Lipsync dort rechnete darum auch fuer
            # Zeitspannen, die broll hinterher ohnehin vollflaechig ueberdeckt (Variante "voll"). Jetzt schon hier,
            # VOR dem Rohschnitt-Schritt, damit der sein Ergebnis lesen und dort den teuren Mundabgleich auslassen
            # kann (tools/weltlage_rohschnitt.py, video/freisteller_lipsync.py). Scheitert/fehlt sie, holt der
            # Schritt "broll" sie wie bisher nach - nie ein Abbruchgrund fuer die Folge.
            if NEWS_WELTLAGE_BROLL and not (ordner / "broll" / "plan.json").exists():
                cmd = ["tools/weltlage_broll.py", ordner, "--vorbereiten"] + (["--ohne-ki"] if NEWS_WELTLAGE_BROLL_OHNE_KI
                                                                              else [])
                if _run(cmd, log, timeout_h=1) != 0:
                    log("B-Roll-Planung vorab fehlgeschlagen - der Schritt \"broll\" versucht es nachher erneut")
            # Nach einer Feedback-Runde muessen nur die geaenderten Szenen neu gerendert werden (die uebrigen
            # liegen schon im Lipsync-Cache dieses Ordners) - das gilt auch fuer einen von Grund auf neu
            # gestarteten Lauf (Resume/Langlauf/PC-Neustart), nicht nur den noch lebenden Prozess, der das
            # Feedback entgegengenommen hat (Vorfall 16.10.2026, s. geaenderte_szenen_seit_feedback()).
            geaendert = None if master.exists() else geaenderte_szenen_seit_feedback(ordner)
            alt_skip = os.environ.get("NEWS_WELTLAGE_SKIP_SZENEN")
            if geaendert is not None:
                alle = [s["id"] for s in json.loads((ordner / "texte.json").read_text(encoding="utf-8"))["szenen"]]
                os.environ["NEWS_WELTLAGE_SKIP_SZENEN"] = ",".join(sid for sid in alle if sid not in geaendert)
            try:
                for versuch in range(1, SCHNITT_VERSUCHE + 1):
                    if master.exists():
                        break
                    # Vorfall 14.10.2026: C: voll, ffmpeg brach mitten im s5-Lipsync ab (tools/weltlage_speicher.py)
                    import weltlage_speicher
                    try:
                        weltlage_speicher.sichern(ordner, log)
                    except weltlage_speicher.SpeicherVoll as ex:
                        raise Abbruch(str(ex)) from ex
                    schnitt_vorbereiten(key, ordner, log)
                    rc = _run(["tools/weltlage_rohschnitt.py", ordner, "--out", master], log,
                              timeout_h=SCHNITT_MAX_STUNDEN, python=LS_PY, ordner=ordner, still_min=STILLSTAND_MIN)
                    if rc != STILLSTAND_RC:
                        break
                    log(f"Rohschnitt Versuch {versuch} hing - neu mit den fertigen Stücken aus dem Cache")
            finally:
                if alt_skip is None:
                    os.environ.pop("NEWS_WELTLAGE_SKIP_SZENEN", None)
                else:
                    os.environ["NEWS_WELTLAGE_SKIP_SZENEN"] = alt_skip
            if not master.exists():
                raise Abbruch("Rohschnitt/Lipsync fehlgeschlagen oder Stimmen-Endprüfung durchgefallen")
        elif schritt == "broll" and NEWS_WELTLAGE_BROLL:
            clips = master.with_name(master.stem + "_clips.mp4")
            cmd = ["tools/weltlage_broll.py", ordner, "--video", master] + (["--ohne-ki"] if NEWS_WELTLAGE_BROLL_OHNE_KI
                                                                           else [])
            if not clips.exists() and _run(cmd, log, timeout_h=3) != 0:
                log("B-Roll fehlgeschlagen - Folge geht ohne Symbolclips raus")
        elif schritt == "abnahme":
            if _run(["tools/weltlage_abnahme.py", ordner, master], log, timeout_h=1) != 0:
                abn_pfad = master.with_name(master.stem + "_abnahme.json")
                info = json.loads(abn_pfad.read_text(encoding="utf-8")) if abn_pfad.exists() else {}
                pegel_runden = int((_laden().get(key) or {}).get("master_neu_runden") or 0)
                if nur_pegel_fehler(info) and pegel_runden < 1:
                    # Vorfall 07.10.2026: True Peak -0,9 statt -1,5 dBTP -> 10 h Neuschnitt, Slot verloren. Nur der
                    # Master-Ton ist falsch: neu mastern (Sekunden), B-Roll-Fassung + Abnahme frisch.
                    _eintrag(key, master_neu_runden=pegel_runden + 1)
                    log(f"Abnahme: nur Gesamtpegel ({'; '.join(info.get('fehler') or [])}) - mache den Master-Ton neu")
                    master_neu(ordner, master, log)
                    for s in ("broll", "abnahme"):
                        schritt_ausfuehren(s)
                    return
                runden = int((_laden().get(key) or {}).get("laenge_runden") or 0)
                zu_kurz = laenge_reparatur_noetig(info, runden)
                if zu_kurz:
                    _eintrag(key, laenge_runden=runden + 1)
                    log(f"Abnahme: {zu_kurz} - verlängere das Skript automatisch und rendere betroffene Szenen neu")
                    from weltlage_ueberarbeiten import ueberarbeiten
                    from weltlage_abnahme import MIN_DAUER_S
                    # Wachstum nach tatsaechlichem Fehlbetrag statt fixer 20 % (Vorfall 04./05.10.2026: 20 % reichten
                    # bei 321 s nie fuer 480 s - mathematisch unmoeglich; jetzt Fehlbetrag + 15 % Sicherheitsspanne).
                    dauer_jetzt = float(info.get("dauer_s") or 0) or 1.0
                    wachstum = max(20, round((MIN_DAUER_S * 1.15 / dauer_jetzt - 1) * 100))
                    feedback = ("Die Folge ist zu kurz für YouTube-Mid-Roll-Werbung (Mindestlänge 8:00 Minuten). "
                                f"Sie dauert jetzt nur {dauer_jetzt:.0f} s, noetig sind mindestens {MIN_DAUER_S:.0f} s. "
                                "Verlängere JEDE Szene um echten zusätzlichen Inhalt bis an die erlaubte Obergrenze "
                                "(mehr Hintergrund und Fakten aus dem Material, Gegenargumente, Einordnung, weitere "
                                "Zitate) - keine Wiederholungen oder Füllsätze.")
                    try:
                        res = ueberarbeiten(ordner, feedback, 100 + runden, master, max_wachstum_prozent=wachstum)
                    except Exception as ex:  # noqa: BLE001
                        raise Abbruch(f"Abnahme-Prüfung durchgefallen ({zu_kurz}), automatische Verlängerung ging "
                                      f"nicht ({str(ex)[:300]}) - nicht veröffentlicht")
                    log(f"Verlängerung Szenen {res['szenen'] or '-'}: {res['zusammenfassung']}")
                    if res["neu_rendern"]:
                        for s in PRODUKTION:
                            schritt_ausfuehren(s)
                        return
                raise Abbruch("Abnahme-Prüfung durchgefallen (Stimme/Lautheit/Ton/Zitate/Länge), siehe "
                              f"{master.stem}_abnahme.json - nicht veröffentlicht")
        elif schritt == "thumbnail":
            from video.weltlage_thumbnail import fuer_folge
            log(f"Thumbnail: {fuer_folge(ordner)}")
        elif schritt == "metadaten":
            m = metadaten(ordner)
            log(f"Titel: {m['title']} | {len(m['description'])} Zeichen Beschreibung | {len(m['tags'])} Tags")
        elif schritt == "warten":
            # Seit 16.10.2026 reiner Durchlaufschritt (kein fester Slot mehr, auf den gewartet wuerde, kein
            # Abbruch wegen Verspaetung) - sobald die Produktion fertig ist, geht es direkt in die Freigabe.
            jetzt = datetime.now().astimezone()
            verspaetung_min = (jetzt - veroeffentlichen).total_seconds() / 60
            if verspaetung_min > 0:
                log(f"fertig um {jetzt:%H:%M}, {verspaetung_min:.0f} min nach Produktionsstart {slot} - geht "
                    "direkt in die Freigabe (keine festen Slots mehr)")
            else:
                log(f"fertig um {jetzt:%H:%M} - geht direkt in die Freigabe")
        elif schritt == "freigabe":
            e = _laden().get(key) or {}
            if e.get("freigabe") or e.get("video_id"):
                log(f"Freigabe schon erledigt ({e.get('freigabe')})")
                return
            if sofort_aktiv(key):
                log(f"Freigabe: Marlon hat «sofort» gegeben ({e.get('sofort_grund') or 'Marlon'}) - keine Rückfrage")
                _eintrag(key, freigabe="sofort (Marlon)")
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
            vorab = vorab_fuer(key)
            res = upload_datei(datei, meta, ordner / "thumbnails" / "thumbnail.jpg",
                               visibility="private" if vorab else NEWS_WELTLAGE_UPLOAD_VISIBILITY,
                               log_path=ordner / "upload.log", debug_dir=ordner / "upload_shots")
            if vorab:
                res["vorab_privat"] = True
                res["oeffentlich_bestaetigt"] = False
            _eintrag(key, video_id=res["video_id"], upload=res)
            log(f"Upload{' (privat vorab, öffentlich um ' + slot + ')' if vorab else ''}: {res}")
        elif schritt == "veroeffentlichen":
            e = _laden().get(key) or {}
            res = dict(e.get("upload") or {})
            if trocken or not res.get("vorab_privat") or res.get("oeffentlich_bestaetigt"):
                return
            if PAUSE.exists():
                raise Abbruch("Pause-Datei gesetzt - privat hochgeladen, nicht veröffentlicht")
            if datetime.now().astimezone() < veroeffentlichen:
                log(f"privat hochgeladen ({res.get('video_id')}), stelle um {veroeffentlichen:%H:%M} öffentlich")
                _eintrag(key, wartet_bis=veroeffentlichen.isoformat(timespec="minutes"))
                while datetime.now().astimezone() < veroeffentlichen:
                    time.sleep(min(30, max(1, (veroeffentlichen - datetime.now().astimezone()).total_seconds())))
            from upload.youtube_playwright import veroeffentlichen as studio_veroeffentlichen
            v = studio_veroeffentlichen(res["video_id"], NEWS_WELTLAGE_UPLOAD_VISIBILITY, log,
                                        ordner / "upload_shots")
            res.update(oeffentlich_bestaetigt=bool(v["ok"]), studio_status=v["status"],
                       veroeffentlichen_verlauf=v["verlauf"], veroeffentlicht_um=datetime.now().astimezone()
                       .isoformat(timespec="seconds"))
            if not v["ok"]:
                res["nachzug_fehler"] = (v.get("fehler") or f"Studio-Status {v['status']}")[:500]
            _eintrag(key, upload=res)
            log(f"Veröffentlichen: {'ok' if v['ok'] else 'NICHT bestätigt'} ({v['status']})")
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
            nachzug = (" (über Sichtbarkeit-Nachzug selbst öffentlich gestellt)" if ok and res.get("nachgezogen")
                       else " (Nachzug-Versuch fehlgeschlagen, bitte in Studio prüfen)" if res.get("nachzug_fehler")
                       else "")
            _melden(f"Weltlage {slot}", f"{'Veröffentlicht' if ok else 'Hochgeladen, aber noch NICHT öffentlich bestätigt'}"
                    f"{nachzug} ({NEWS_WELTLAGE_UPLOAD_VISIBILITY}, {e.get('freigabe')}): {meta['title']}\n"
                    f"https://youtu.be/{res.get('video_id')}\nThumbnail: {res.get('thumbnail')}", log)
            _eintrag(key, status="veroeffentlicht" if ok else "unbestaetigt",
                     fertig=datetime.now().astimezone().isoformat(timespec="seconds"))
        elif schritt == "frage_kommentar":
            if trocken:
                return
            e = _laden().get(key) or {}
            if e.get("frage_kommentar_erledigt"):
                log("Frage-Kommentar schon erledigt")
                return
            res = e.get("upload") or {}
            if not res.get("oeffentlich_bestaetigt") or not res.get("video_id"):
                log("Frage-Kommentar uebersprungen: Video noch nicht oeffentlich bestaetigt")
                return
            meta = json.loads((ordner / "metadaten.json").read_text(encoding="utf-8"))
            frage = (meta.get("kommentarfrage") or "").strip()
            if not frage:
                log("Frage-Kommentar uebersprungen: keine kommentarfrage in metadaten.json")
                _eintrag(key, frage_kommentar_erledigt=True)
                return
            from upload.youtube_kommentar import frage_kommentar_posten
            ok_fk = frage_kommentar_posten(res["video_id"], frage)
            log(f"Frage-Kommentar {'gepostet+angeheftet' if ok_fk else 'FEHLGESCHLAGEN'}: {frage}")
            _eintrag(key, frage_kommentar_erledigt=True, frage_kommentar_ok=ok_fk)
        elif schritt == "shorts":
            if trocken or not NEWS_WELTLAGE_SHORTS:
                return
            e = _laden().get(key) or {}
            if e.get("shorts_erledigt"):
                log("Shorts bereits erledigt")
                return
            res = e.get("upload") or {}
            if not res.get("video_id"):
                log("Shorts: Folge hat keine Video-ID - uebersprungen")
                return
            try:
                shorts_erzeugen_und_einreihen(key, slot, ordner, log)
            except Exception as ex:  # noqa: BLE001 - Shorts sind ein Zusatznutzen, duerfen die Folge nie gefaehrden
                log(f"Shorts fehlgeschlagen: {ex}")
            _eintrag(key, shorts_erledigt=True)

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
            # Vorfall 06.10.2026: ein per --nur upload,meldung nachgeholter Upload setzte «unbestaetigt» -> «probe»
            # zurueck, die Weltlage-Wache sah das Entwurfs-Video danach nicht mehr. Upload-Ergebnis bleibt stehen.
            st = (_laden().get(key) or {}).get("status")
            _eintrag(key, schritte=nur, **({} if st in ("veroeffentlicht", "unbestaetigt") else {"status": "probe"}))
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


def fremder_interpreter() -> bool:
    """Laeuft dieser Prozess nicht mit dem Newsroom-venv? (Vorfaelle 03./04./06.10.2026: von Hand oder von Workern
    mit einem anderen Python gestartete Laeufe brachen erst im Upload/Telegram mit «No module named 'httpx'» ab.)"""
    try:
        eigen = {PY.resolve(), PYW.resolve()}
        return PY.exists() and Path(sys.executable).resolve() not in eigen
    except OSError:
        return False


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "lauf" and fremder_interpreter() and not os.environ.get("WELTLAGE_VENV_OK"):
        # mit dem richtigen Interpreter neu starten; dieser Prozess wartet (eine Langlauf-Aufsicht sieht ihn weiter)
        r = subprocess.run([str(PY), str(Path(__file__).resolve()), *sys.argv[1:]], cwd=str(ROOT),
                           env={**os.environ, "WELTLAGE_VENV_OK": "1"}, creationflags=NO_WINDOW)
        sys.exit(r.returncode)
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
    mn = sub.add_parser("master-neu", help="nur den Master-Ton neu (Pegel-Fehler der Abnahme), B-Roll/Abnahme verwerfen")
    mn.add_argument("ordner", type=Path)
    mn.add_argument("master", type=Path)
    so = sub.add_parser("sofort", help="Marlons Freigabe «sofort veröffentlichen» für einen Lauf: kein Warten auf "
                                       "Freigabefenster/Slot, keine Rückfrage, Upload direkt öffentlich")
    so.add_argument("key", help="z.B. 2026-10-10_19:00")
    so.add_argument("--grund", default="Marlon")
    a = ap.parse_args()
    if a.cmd == "sofort":
        print(json.dumps(sofort_setzen(a.key, a.grund), indent=1, ensure_ascii=False, default=str))
        return
    if a.cmd == "lauf":
        sys.exit(lauf(a.datum, a.slot, a.ordner, a.bis, a.nur.split(",") if a.nur else None,
                      True if a.trocken else None, a.themenwahl_min, a.freigabe_min))
    if a.cmd == "metadaten":
        print(json.dumps(metadaten(a.ordner), indent=1, ensure_ascii=False))
    if a.cmd == "master-neu":
        print(json.dumps(master_neu(a.ordner, a.master), ensure_ascii=False))
    if a.cmd == "zeitplan":
        print(json.dumps(zeitplan(), indent=1, ensure_ascii=False))
    if a.cmd == "status":
        print(json.dumps({"aktiv": NEWS_WELTLAGE_TAEGLICH, "pause": PAUSE.exists(), "slots": NEWS_WELTLAGE_SLOTS,
                          "trockenlauf": NEWS_WELTLAGE_TROCKENLAUF, **zeitplan(),
                          "sichtbarkeit": NEWS_WELTLAGE_UPLOAD_VISIBILITY, "laeufe": _laden()}, indent=1,
                         ensure_ascii=False))


if __name__ == "__main__":
    main()
