"""Weltlage Kompakt - Rueckfragen an Marlon mit Frist (Themenwahl A/B/C, Freigabe/Feedback/Stopp), Marlon 02.10.2026.

Ein Entscheid pro Lauf (Schluessel "<datum>_<slot>", ID = 12 Hex-Zeichen daraus), Zustand nur in Dateien, damit ein
Neustart nichts verliert: state/weltlage_entscheid/<id>.json, Index der offenen Fragen state/weltlage_entscheid/
offen.json (liest auch Jarvis' Telegram-Dienst, mobil/newsroom.py, um Antworten ohne Reply hierher zu leiten).

Kanaele:
  Telegram  geteilter Bot @WeltlageKompakt_Bot: Nachricht (und bei der Freigabe das Video als Dokument, Ton kopiert)
            mit Inline-Knoepfen, callback_data "wl|<id>|<runde>|<wahl>". Nur Jarvis pollt; Knopfdruecke und Antworten
            landen ueber state/telegram_inbox beim Newsroom-Bot (telegram_bot/handlers.py weltlage_callback /
            feedback_text), der hier antwort()/text_antwort() aufruft. Jeder Text traegt "Job <id>", damit Replies
            als Newsroom-Sache erkannt werden.
  Beta-App  ueber den Beta-Knoten (galadriel.knoten.rueckfrage): Mitteilung im App-Chat + Push (ntfy) mit
            Antwort-Knoepfen; Antworten im App-Chat, die zum Muster passen («A», «Weltlage B, ...», «Freigeben»,
            «Stopp», «Feedback: ...»), schreibt der Knoten als Datei nach state/weltlage_entscheid/antworten/.

Keine Antwort bis zur Frist -> warten() gibt None zurueck, der Lauf nimmt die Voreinstellung (Empfehlung bzw.
Veroeffentlichen). Fehler in einem Kanal brechen nie den Lauf ab (nur Log).
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config.settings import STATE_DIR, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID  # noqa: E402

DIR = STATE_DIR / "weltlage_entscheid"
OFFEN = DIR / "offen.json"
ANTWORTEN = DIR / "antworten"
BETA = Path(r"C:\Users\Marlon\projekte\galadriel")
BETA_PY = BETA / ".venv" / "Scripts" / "python.exe"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
FEEDBACK_NACHFRIST_MIN = 30
OFFEN_STATUS = ("offen", "feedback_erwartet")

THEMA_MUSTER = r"^\s*(weltlage[\s:,.-]*)?[ABC]\b"
FREIGABE_MUSTER = r"^\s*(weltlage[\s:,.-]*)?(freigeben|freigabe|stopp?|feedback)\b"


def _jetzt() -> datetime:
    return datetime.now().astimezone()


def lauf_id(key: str) -> str:
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def _pfad(eid: str) -> Path:
    return DIR / f"{eid}.json"


def laden(eid: str) -> dict | None:
    try:
        return json.loads(_pfad(eid).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _schreiben(p: Path, daten):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(daten, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def speichern(e: dict):
    _schreiben(_pfad(e["id"]), e)
    index_aktualisieren()


def index_aktualisieren():
    offen = []
    for p in DIR.glob("*.json"):
        if p.name == OFFEN.name:
            continue
        try:
            e = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if e.get("status") in OFFEN_STATUS:
            offen.append({"id": e["id"], "key": e.get("key"), "phase": e.get("phase"), "runde": e.get("runde"),
                          "status": e["status"], "bis": e.get("frist"), "optionen": list(e.get("optionen") or {})})
    _schreiben(OFFEN, offen)


def offene() -> list[dict]:
    out = []
    for o in (json.loads(OFFEN.read_text(encoding="utf-8")) if OFFEN.exists() else []):
        e = laden(o["id"])
        if e and e.get("status") in OFFEN_STATUS:
            out.append(e)
    return sorted(out, key=lambda e: e.get("gefragt") or "", reverse=True)


# ------------------------------------------------------------------ Telegram (nur senden, Jarvis pollt)
def _tg(methode: str, daten: dict, dateien: dict | None = None, timeout: float = 60) -> dict:
    import httpx
    r = httpx.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{methode}", data=daten, files=dateien,
                   timeout=timeout)
    j = r.json()
    if not j.get("ok"):
        raise RuntimeError(f"Telegram {methode}: HTTP {r.status_code} {str(j)[:300]}")
    return j["result"]


def _knoepfe(e: dict) -> str:
    reihe = [{"text": label, "callback_data": f"wl|{e['id']}|{e['runde']}|{wahl}"}
             for wahl, label in e["optionen"].items()]
    return json.dumps({"inline_keyboard": [reihe]}, ensure_ascii=False)


def telegram_senden(e: dict, text: str, dokument: Path | None = None, bild: Path | None = None, log=print) -> list[int]:
    ids = []
    kennung = f"\n\nJob {e['id']} (Runde {e['runde']})"
    try:
        if bild and Path(bild).exists():
            with open(bild, "rb") as f:
                ids.append(_tg("sendPhoto", {"chat_id": TELEGRAM_CHAT_ID, "caption": f"Thumbnail{kennung}"[:1000]},
                               {"photo": (Path(bild).name, f, "image/jpeg")}, timeout=120)["message_id"])
        if dokument and Path(dokument).exists():
            with open(dokument, "rb") as f:
                ids.append(_tg("sendDocument", {"chat_id": TELEGRAM_CHAT_ID,
                                                "caption": (text[:900] + kennung)[:1000],
                                                "disable_content_type_detection": "true",
                                                "reply_markup": _knoepfe(e)},
                               {"document": (Path(dokument).name, f, "application/octet-stream")},
                               timeout=900)["message_id"])
            if len(text) > 900:
                ids.append(_tg("sendMessage", {"chat_id": TELEGRAM_CHAT_ID, "text": (text + kennung)[:4000],
                                               "reply_markup": _knoepfe(e)})["message_id"])
        else:
            ids.append(_tg("sendMessage", {"chat_id": TELEGRAM_CHAT_ID, "text": (text + kennung)[:4000],
                                           "reply_markup": _knoepfe(e)})["message_id"])
    except Exception as ex:  # noqa: BLE001 - ein Kanal faellt aus, der Lauf geht weiter
        log(f"Telegram-Rueckfrage fehlgeschlagen: {ex}")
    return ids


def telegram_text(text: str, log=print):
    try:
        _tg("sendMessage", {"chat_id": TELEGRAM_CHAT_ID, "text": text[:4000]})
    except Exception as ex:  # noqa: BLE001
        log(f"Telegram-Meldung fehlgeschlagen: {ex}")


def _knoepfe_weg(e: dict, log=print):
    for mid in (e.get("telegram") or {}).get("message_ids") or []:
        try:
            _tg("editMessageReplyMarkup", {"chat_id": TELEGRAM_CHAT_ID, "message_id": mid,
                                           "reply_markup": json.dumps({"inline_keyboard": []})}, timeout=20)
        except Exception:  # noqa: BLE001 - Foto ohne Knoepfe, schon geaendert, ...
            pass


# ------------------------------------------------------------------ Beta-App (ueber den Beta-Knoten)
def beta(befehl: str, daten: dict, log=print) -> dict | None:
    """galadriel.knoten.rueckfrage <befehl> mit JSON auf stdin (Beta-venv, eigener Prozess, ohne Fenster)."""
    if not BETA_PY.exists():
        log("Beta-App: galadriel-venv fehlt, nur Telegram")
        return None
    try:
        p = subprocess.run([str(BETA_PY), "-m", "galadriel.knoten.rueckfrage", befehl], cwd=str(BETA),
                           input=json.dumps(daten, ensure_ascii=False), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60, creationflags=NO_WINDOW)
        out = (p.stdout or "").strip().splitlines()
        res = json.loads(out[-1]) if out else {}
        if p.returncode != 0 or not res.get("ok"):
            log(f"Beta-App {befehl}: {res.get('fehler') or (p.stderr or '')[-300:]}")
        return res
    except Exception as ex:  # noqa: BLE001
        log(f"Beta-App {befehl} fehlgeschlagen: {ex}")
        return None


def _beta_id(e: dict) -> str:
    return f"weltlage-{e['id']}-{e['runde']}"


# ------------------------------------------------------------------ Fragen / Antworten
def fragen(key: str, phase: str, text: str, optionen: dict[str, str], frist: datetime, *, empfehlung: str | None = None,
           titel: str = "Weltlage Kompakt", dokument: Path | None = None, bild: Path | None = None,
           beta_text: str | None = None, log=print, kanaele=("telegram", "beta")) -> dict:
    """Neue Runde einer Rueckfrage oeffnen und in beide Kanaele schicken. optionen: {wahl: Knopf-Beschriftung}."""
    eid = lauf_id(key)
    alt = laden(eid) or {}
    e = {"id": eid, "key": key, "phase": phase, "runde": int(alt.get("runde") or 0) + 1, "status": "offen",
         "gefragt": _jetzt().isoformat(timespec="seconds"), "frist": frist.isoformat(timespec="seconds"),
         "optionen": optionen, "empfehlung": empfehlung, "antwort": None, "titel": titel,
         "verlauf": (alt.get("verlauf") or []) + ([{"phase": alt.get("phase"), "runde": alt.get("runde"),
                                                    "status": alt.get("status"), "antwort": alt.get("antwort")}]
                                                  if alt else [])}
    speichern(e)
    if "telegram" in kanaele:
        e["telegram"] = {"message_ids": telegram_senden(e, text, dokument, bild, log)}
    if "beta" in kanaele:
        muster = THEMA_MUSTER if phase == "thema" else FREIGABE_MUSTER
        aktionen = [{"label": label, "text": f"Weltlage {wahl if phase == 'thema' else label}"}
                    for wahl, label in optionen.items() if wahl != "feedback"][:3]
        r = beta("stellen", {"id": _beta_id(e), "titel": titel, "text": beta_text or text, "muster": muster,
                             "antwort_ordner": str(ANTWORTEN), "bis": e["frist"], "aktionen": aktionen,
                             "bestaetigung": "Danke, ist an die Weltlage-Redaktion weitergegeben."}, log)
        e["beta"] = {"ok": bool(r and r.get("ok")), "push": (r or {}).get("push")}
    speichern(e)
    log(f"Rueckfrage {phase} Runde {e['runde']} offen bis {frist:%H:%M} (Telegram {len((e.get('telegram') or {}).get('message_ids') or [])} "
        f"Nachrichten, Beta {'ok' if (e.get('beta') or {}).get('ok') else 'nein'})")
    return e


def antwort(eid: str, wahl: str, feedback: str | None = None, quelle: str = "", runde: int | None = None) -> tuple[bool, str]:
    e = laden(eid)
    if not e or e.get("status") not in OFFEN_STATUS:
        return False, "Diese Rückfrage ist schon abgeschlossen."
    if runde is not None and int(runde) != int(e["runde"]):
        return False, "Das war eine ältere Runde, sie gilt nicht mehr."
    if wahl not in e["optionen"]:
        return False, f"Unbekannte Wahl «{wahl}»."
    jetzt = _jetzt()
    if wahl == "feedback" and not (feedback or "").strip():
        e["status"] = "feedback_erwartet"
        e["frist"] = max(datetime.fromisoformat(e["frist"]),
                         jetzt + timedelta(minutes=FEEDBACK_NACHFRIST_MIN)).isoformat(timespec="seconds")
        speichern(e)
        return True, (f"Was soll anders sein? Antworte auf diese Nachricht mit deinen Änderungen (Job {eid}). "
                      f"Ich warte bis {datetime.fromisoformat(e['frist']):%H:%M}.")
    e["antwort"] = {"wahl": wahl, "feedback": (feedback or "").strip() or None, "quelle": quelle,
                    "zeit": jetzt.isoformat(timespec="seconds")}
    e["status"] = "beantwortet"
    speichern(e)
    label = e["optionen"][wahl]
    return True, f"Übernommen: {label}" + (f" mit Hinweis «{feedback.strip()[:200]}»" if feedback else "") + "."


def text_auswerten(text: str, phase: str) -> tuple[str, str | None] | None:
    t = re.sub(r"^\s*weltlage[\s:,.-]*", "", text or "", flags=re.I).strip()
    if phase == "thema":
        m = re.match(r"^([ABC])(?:\b|$)[\s,.:;!)-]*(.*)$", t, re.I | re.S)
        return (m.group(1).upper(), m.group(2).strip() or None) if m else None
    m = re.match(r"^(freigeben|freigabe|ok|passt|go)\b[\s,.:;!-]*(.*)$", t, re.I | re.S)
    if m:
        return "freigeben", None
    if re.match(r"^stopp?\b", t, re.I):
        return "stopp", None
    m = re.match(r"^feedback\b[\s,.:;!-]*(.*)$", t, re.I | re.S)
    if m:
        return "feedback", m.group(1).strip() or None
    return None


def text_antwort(text: str, eid: str | None = None, quelle: str = "", als_antwort: bool = False) -> str | None:
    """Freitext aus Telegram/App einer offenen Rueckfrage zuordnen. eid = aus «Job <id>» der beantworteten Nachricht;
    als_antwort = Text war ein Reply auf unsere Nachricht (dann zaehlt auch Freitext ohne Schluesselwort).
    Rueckgabe: Bestaetigungstext oder None (gehoert nicht hierher)."""
    kandidaten = [laden(eid)] if eid else offene()
    kandidaten = [e for e in kandidaten if e and e.get("status") in OFFEN_STATUS]
    if not kandidaten:
        return None
    e = kandidaten[0]
    t = (text or "").strip()
    if not t:
        return None
    if e["status"] == "feedback_erwartet":
        return antwort(e["id"], "feedback", t, quelle)[1]
    r = text_auswerten(t, e["phase"])
    if r:
        wahl, fb = r
        if wahl == "feedback" and not fb and not als_antwort:
            return antwort(e["id"], "feedback", None, quelle)[1]
        return antwort(e["id"], wahl, fb, quelle)[1]
    if als_antwort or eid:
        if e["phase"] == "thema":
            return antwort(e["id"], e.get("empfehlung") or "A", t, quelle)[1]
        return antwort(e["id"], "feedback", t, quelle)[1]
    return None


def _beta_antworten_einlesen(log=print):
    for f in sorted(ANTWORTEN.glob("*.json")) if ANTWORTEN.exists() else []:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            f.replace(f.with_suffix(".bad"))
            continue
        m = re.match(r"^weltlage-([0-9a-f]{12})-(\d+)$", str(d.get("rueckfrage") or ""))
        f.unlink(missing_ok=True)
        if not m:
            continue
        e = laden(m.group(1))
        if not e or int(m.group(2)) != int(e.get("runde") or 0):
            log(f"Beta-Antwort zu alter Runde ignoriert: {d.get('text')!r}")
            continue
        res = text_antwort(d.get("text") or "", m.group(1), quelle="beta-app", als_antwort=True)
        log(f"Beta-App-Antwort «{str(d.get('text'))[:120]}»: {res}")


def warten(eid: str, log=print, poll_s: float = 5.0, abbruch=None) -> dict | None:
    """Blockiert bis Antwort oder Frist (Frist kann sich durch «Feedback» verlaengern). None = keine Antwort."""
    while True:
        _beta_antworten_einlesen(log)
        e = laden(eid)
        if not e:
            return None
        if e.get("status") == "beantwortet":
            schliessen(e, log)
            return e["antwort"]
        if _jetzt() >= datetime.fromisoformat(e["frist"]):
            e["status"] = "abgelaufen"
            speichern(e)
            schliessen(e, log)
            return None
        if abbruch and abbruch():
            e["status"] = "abgebrochen"
            speichern(e)
            schliessen(e, log)
            return None
        time.sleep(poll_s)


def schliessen(e: dict, log=print):
    _knoepfe_weg(e, log)
    if (e.get("beta") or {}).get("ok"):
        beta("schliessen", {"id": _beta_id(e)}, log)


def mitteilen(titel: str, text: str, log=print, telegram: bool = True, beta_app: bool = True):
    """Reine Meldung ohne Rueckfrage (Wahl bestaetigt, veroeffentlicht, Fehler) an Telegram und Beta-App."""
    if telegram:
        telegram_text(f"{titel}\n{text}" if titel else text, log)
    if beta_app:
        beta("mitteilen", {"titel": titel or "Weltlage Kompakt", "text": text}, log)
