#!/usr/bin/env python
"""Weltlage Kompakt: eigenstaendige Shorts (Marlon 29.10.2026, Telegram): Shorts sind NICHT mehr Ausschnitte der
Folgen (tools/weltlage_shorts.py bleibt als Altbestand, NEWS_WELTLAGE_SHORTS=0 schaltet den Schnitt im Tageslauf
ab), sondern eigene Themen, eigenes Skript, eigene Produktion, 3 bis 5 pro Tag (Soll: jarvis/tools/kanal_takt.py).

Ablauf je Short (CPU + eine kurze TTS-Strecke, keine Lipsync-Arbeit):
  1. Thema: frische Meldungsgruppe (weltlage_skript.aktuelle_gruppen), die weder einer Folge der letzten Tage noch
     einem frueheren eigenen Short aehnelt (weltlage_themen.aehnlichkeit, Verlauf state/weltlage_short_eigen.json).
  2. Skript: ein Modell-Aufruf (weltlage_skript.frage_modell), ~120 Woerter Sprechtext, Titel, Hashtags.
  3. Stimme: weltlage_tts.sprich (aktives Profil = maennliche Stimme, volle Aussprache-Kette inkl. Rueckhoeren).
  4. Bild: Masken-Moderator (maske_flf_mix bzw. Loop + host_spur wie die Folgen), Untertitel, Titelkarte, 9:16.
  5. Einreihen in die Shorts-Warteschlange (weltlage_shorts_takt.einreihen); der Taktgeber laedt zu den Slots hoch.

    python tools/weltlage_short_eigen.py auffuellen [--ziel N]   Warteschlange auf N eigene Shorts auffuellen
    python tools/weltlage_short_eigen.py baue --text "..." --titel "..." [--ordner DIR]   Probe ohne News/Upload
    python tools/weltlage_short_eigen.py status
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["NEWS_FORMAT"] = "shorts"      # 9:16-Geometrie fuer Titelkarte/Untertitel (video/layout.py), wie weltlage_shorts.py
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from config.settings import DATA_DIR, STATE_DIR  # noqa: E402

VERLAUF = STATE_DIR / "weltlage_short_eigen.json"
KEY_PREFIX = "short-eigen"
ZIEL_WARTESCHLANGE = 2           # so viele fertige eigene Shorts sollen in der Warteschlange liegen
MAX_PRO_LAUF = 2                 # hoechstens so viele Shorts pro Aufruf (Laufzeit)
THEMA_SCHWELLE = 0.5             # Aehnlichkeit (weltlage_themen.aehnlichkeit) ab der ein Thema als Wiederholung gilt
WOERTER_MIN, WOERTER_MAX = 80, 118      # ~2,5 Woerter/s bei Tempo 1.15 -> 33 bis 48 s (Limit 59 s inkl. Rueckhoer-Pausen)
KI_HINWEIS = ("Moderator und Stimme sind KI-generiert. Fakten stammen aus den unten genannten Quellen.")
HASHTAGS = "#Shorts #WeltlageKompakt #Nachrichten #Weltpolitik"

PROMPT = """Du schreibst den Sprechtext fuer einen eigenstaendigen YouTube-Short (Hochformat, 40 bis 55 Sekunden) des
deutschsprachigen Nachrichtenkanals «Weltlage Kompakt». Heute ist {heute}.

Thema (nur aus dem folgenden Material, nichts erfinden):
{material}

Regeln:
- Genau {lo} bis {hi} Woerter Sprechtext. Erster Satz = Hook mit der staerksten Tatsache, kein «Hallo», kein Kanalname.
- Dann 3 bis 5 kurze Saetze: was ist passiert, warum ist es wichtig, was heisst das. Letzter Satz: eine offene Frage
  an die Zuschauer.
- Nur Tatsachen aus dem Material; Zahlen nur wenn sie im Material stehen. Keine woertlichen Zitate.
- Schweizer Schreibweise (ss statt ß). Keine Aufzaehlungen, keine Klammern, keine Emojis, keine Hashtags im Text.
- Jahreszahlen und Abkuerzungen normal schreiben (FBI, CDU, 1980), die Vertonung spricht sie selbst richtig aus.
- Titel: Frage oder klare Aussage, 45 bis 80 Zeichen, ohne Clickbait-Luege.

Antworte nur mit einem JSON-Objekt: {{"titel": "...", "text": "...", "tags": ["...", "..."]}}"""


def _lesen() -> dict:
    try:
        return json.loads(VERLAUF.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"shorts": []}


def _schreiben(d: dict) -> None:
    VERLAUF.parent.mkdir(parents=True, exist_ok=True)
    VERLAUF.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def _eigene_in_warteschlange() -> int:
    import weltlage_shorts_takt as takt
    return sum(1 for e in takt.warteschlange() if str(e.get("key", "")).startswith(KEY_PREFIX))


def _bekannte_titel() -> list[str]:
    """Titel der letzten Folgen + eigener Shorts, gegen die ein neues Thema geprueft wird."""
    titel = [s.get("titel", "") for s in _lesen().get("shorts", [])[-40:]]
    try:
        import weltlage_themen as th
        titel += [f.get("titel") or f.get("title") or "" for f in th.vergangene_folgen(4)]
    except Exception as e:   # noqa: BLE001 - ohne Folgen-Abgleich lieber nur den eigenen Verlauf nutzen
        print(f"Folgen-Abgleich nicht moeglich ({type(e).__name__}: {e})", flush=True)
    return [t for t in titel if t]


def thema_waehlen(gruppen: list[dict]) -> dict | None:
    import weltlage_themen as th
    bekannt = _bekannte_titel()
    for g in gruppen:
        kopf = " ".join((a.get("title") or "") for a in g["articles"][:3])
        if all(th.aehnlichkeit(kopf, b) < THEMA_SCHWELLE for b in bekannt):
            return g
    return None


def skript_schreiben(gruppe: dict) -> dict:
    import weltlage_skript as sk
    jetzt = datetime.now().astimezone()
    heute = f"{sk.WOCHENTAGE[jetzt.weekday()]}, {jetzt.day}. {sk.MONATE[jetzt.month - 1]} {jetzt.year}"
    material = sk.material_aus_news([gruppe], volltext=True)
    prompt = PROMPT.format(heute=heute, material=material, lo=WOERTER_MIN, hi=WOERTER_MAX)
    for versuch in (1, 2):
        s = sk._ss(sk.frage_modell(prompt))
        text = re.sub(r"\s+", " ", str(s.get("text") or "")).strip()
        n = len(text.split())
        if s.get("titel") and WOERTER_MIN * 0.85 <= n <= WOERTER_MAX * 1.15:
            return {"titel": str(s["titel"]).strip().rstrip("."), "text": text,
                    "tags": [str(t) for t in s.get("tags") or []][:8], "woerter": n}
        prompt += f"\n\nDein letzter Entwurf hatte {n} Woerter oder keinen Titel - halte {WOERTER_MIN}-{WOERTER_MAX} ein."
    raise RuntimeError("Short-Skript: Laenge/Titel nach 2 Versuchen nicht in Ordnung")


def _host_video(ordner: Path, ton: Path, ende: float, seed: int) -> Path:
    """Masken-Moderator-Spur in 1920x1080 (wie die Folgen): Wan-Clips (NEWS_MASKEN_FLF) sonst CPU-Loop + Sprechbewegung."""
    import weltlage_maskenformat as mf
    work = ordner / "_maske"
    work.mkdir(exist_ok=True)
    host = None
    if os.environ.get("NEWS_MASKEN_FLF", "0") == "1":
        import maske_flf_mix
        if maske_flf_mix.verfuegbar():
            host = work / "host_spur.mp4"
            if not host.exists():
                try:
                    maske_flf_mix.mix(ende, seed, host, mf.FFMPEG, mf.W, mf.H, mf.FPS)
                except maske_flf_mix.MundBewegtFehler as e:
                    print(f"{e} -> CPU-Loop (starre Maske)", flush=True)
                    host = None
    if host is None:
        loop = mf.host_quelle(None, work)
        host = work / "host_spur.mp4"
        if not host.exists():
            mf.host_spur(loop, ton, ende, host, versatz_s=(seed % 1000) / 100.0)
    return host


def _tor(titel: str, text: str, meta_tts: dict) -> None:
    """Qualitaets- und Datenschutzpruefung vor dem Rendern/Einreihen (bleibt Pflicht, Marlon 29.10.2026): Stimm-Nachweis
    (aktives Profil), Whisper-Kontrolle der Vertonung und Text-Datenschutz (IBAN, Adresse, Mail, Telefon, Keys,
    Sperrliste) ueber jarvis/tools/datenschutz_pruefung.py. Ist das Pruefmodul nicht erreichbar, wird nicht veroeffentlicht."""
    import weltlage_tts
    fehler = []
    if not (meta_tts.get("kontrolle") or {}).get("ok"):
        fehler.append(f"Vertonung nicht in Ordnung (Kontrolle {(meta_tts.get('kontrolle') or {}).get('quote')})")
    if meta_tts.get("ref_sha256") != weltlage_tts.REF_SHA256:
        fehler.append("Vertonung nicht mit dem aktiven Stimmprofil")
    jarvis_tools = Path(r"C:\Users\Marlon\projekte\jarvis\tools")
    try:
        sys.path.append(str(jarvis_tools))   # hinten: Newsroom-Module haben Vorrang
        import datenschutz_pruefung as dsp
        fehler += [f"Datenschutz {t}" for t in dsp.pruefe_text({"titel": titel, "text": text})]
    except Exception as e:   # noqa: BLE001
        fehler.append(f"Datenschutz-Pruefung nicht ausfuehrbar ({type(e).__name__}: {e})")
    if fehler:
        raise RuntimeError("Qualitaets-/Datenschutz-Tor: " + "; ".join(fehler))


def baue(ordner: Path, titel: str, text: str, tags: list[str] | None = None, log=print) -> dict:
    """Vertont und rendert einen Short in <ordner>; gibt {"mp4", "meta"} im Format von weltlage_shorts_takt.einreihen."""
    import weltlage_shorts as ws
    import weltlage_tts
    ordner.mkdir(parents=True, exist_ok=True)
    wav = ordner / "short.wav"
    meta_tts = weltlage_tts.sprich(text, wav)
    ende = float(meta_tts["laenge_s"])
    if ende > 59.0:
        raise RuntimeError(f"Short zu lang ({ende:.1f} s, Limit 59 s) - Text kuerzen")
    _tor(titel, text, meta_tts)
    seed = int(hashlib.sha256(f"{ordner.name}{titel}".encode()).hexdigest()[:8], 16)
    host = _host_video(ordner, wav, ende, seed)
    words = ws._woerter_ausgerichtet(wav, text, log)
    ass = ws.untertitel(words, ordner / "short.ass", log)
    karte = ordner / "short_titel.png"
    ws._titelkarte(titel, karte)
    rohmp4 = ordner / "short_roh.mp4"
    mit_ton = ordner / "host_mit_ton.mp4"      # _short_rendern mappt 0:a, die Host-Spur hat keinen Ton
    ws._ffmpeg(["-i", host, "-i", wav, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-shortest",
                mit_ton], log)
    ws._short_rendern(mit_ton, 0.0, ende, ass, rohmp4, titelkarte=karte, log=log)
    # Ton: Stimme (mit Lautheit der Folgen) statt der Spur aus dem Host-Video, das hat keinen Ton
    mp4 = ordner / f"short_eigen_{ordner.name}.mp4"
    ws._ffmpeg(["-i", rohmp4, "-i", wav, "-map", "0:v", "-map", "1:a", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-shortest",
                "-movflags", "+faststart", mp4], log)
    beschr = f"{titel}\n\n{KI_HINWEIS}\n\n{HASHTAGS}"
    meta = {"title": titel if len(titel) <= 100 else titel[:97] + "...", "description": beschr,
            "tags": list(dict.fromkeys((tags or []) + ["Weltlage Kompakt", "Nachrichten", "Shorts"])),
            "language": "de", "dauer_s": ende}
    try:
        from tools.weltlage_shorts_thumbnail import fuer_short
        meta["thumbnail"] = str(fuer_short(meta, ordner / f"{mp4.stem}_thumb.jpg", ordner=None))
    except Exception as e:   # noqa: BLE001 - Thumbnail ist Zusatz; der Takt-Nachtrag baut es sonst neu
        log(f"Thumbnail nicht gebaut ({type(e).__name__}: {e})")
    (ordner / f"{mp4.stem}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"mp4": mp4, "meta": meta, "dauer": ende}


def produziere_einen(log=print) -> dict | None:
    import weltlage_shorts_takt as takt
    import weltlage_skript as sk
    gruppen = sk.aktuelle_gruppen(12)
    gruppe = thema_waehlen(gruppen)
    if gruppe is None:
        log("Eigener Short: kein frisches Thema, das nicht schon vorkam")
        return None
    s = skript_schreiben(gruppe)
    ordner = DATA_DIR / f"weltlage_short_{datetime.now():%Y%m%d_%H%M%S}"
    log(f"Eigener Short: «{s['titel']}» ({s['woerter']} Woerter) -> {ordner.name}")
    (ordner).mkdir(parents=True, exist_ok=True)
    (ordner / "skript.json").write_text(json.dumps({"skript": s, "material": gruppe}, ensure_ascii=False, indent=1,
                                                   default=str), encoding="utf-8")
    erg = baue(ordner, s["titel"], s["text"], s["tags"], log)
    key = f"{KEY_PREFIX}-{ordner.name}"
    takt.einreihen(key, "eigen", ordner, [erg])
    v = _lesen()
    v["shorts"].append({"titel": s["titel"], "ordner": str(ordner), "zeit": datetime.now().astimezone().isoformat(
        timespec="seconds"), "dauer_s": erg["dauer"]})
    v["shorts"] = v["shorts"][-200:]
    _schreiben(v)
    return erg


LOCK = STATE_DIR / "weltlage_short_eigen.lock"
LOCK_MAX_S = 3 * 3600


def _lock_nehmen() -> bool:
    """Nur ein Auffuell-Lauf gleichzeitig (die Wache startet ihn stuendlich losggeloest); ein Lock aelter als 3 h
    gilt als verwaist."""
    try:
        if LOCK.exists() and time.time() - LOCK.stat().st_mtime < LOCK_MAX_S:
            return False
        LOCK.parent.mkdir(parents=True, exist_ok=True)
        LOCK.write_text(str(os.getpid()), encoding="utf-8")
        return True
    except OSError:
        return False


def auffuellen(ziel: int = ZIEL_WARTESCHLANGE, log=print) -> dict:
    if not _lock_nehmen():
        return {"gebaut": 0, "grund": "anderer Auffuell-Lauf aktiv"}
    gebaut, fehler = 0, []
    t0 = time.time()
    try:
        while _eigene_in_warteschlange() < ziel and gebaut < MAX_PRO_LAUF:
            try:
                if produziere_einen(log) is None:
                    break
                gebaut += 1
            except Exception as e:   # noqa: BLE001 - ein Fehlschlag stoppt den Lauf, der naechste Takt versucht es neu
                fehler.append(f"{type(e).__name__}: {str(e)[:300]}")
                break
    finally:
        LOCK.unlink(missing_ok=True)
    return {"gebaut": gebaut, "in_warteschlange": _eigene_in_warteschlange(), "fehler": fehler,
            "dauer_s": round(time.time() - t0)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("auffuellen")
    a.add_argument("--ziel", type=int, default=ZIEL_WARTESCHLANGE)
    b = sub.add_parser("baue")
    b.add_argument("--text", required=True)
    b.add_argument("--titel", required=True)
    b.add_argument("--ordner", type=Path)
    sub.add_parser("status")
    args = ap.parse_args()
    if args.cmd == "auffuellen":
        print(json.dumps(auffuellen(args.ziel), ensure_ascii=False))
    elif args.cmd == "baue":
        ordner = args.ordner or DATA_DIR / f"weltlage_short_probe_{datetime.now():%Y%m%d_%H%M%S}"
        erg = baue(ordner, args.titel, args.text)
        print(json.dumps({"mp4": str(erg["mp4"]), "dauer": erg["dauer"], "titel": erg["meta"]["title"]},
                         ensure_ascii=False))
    else:
        v = _lesen()
        print(json.dumps({"eigene_in_warteschlange": _eigene_in_warteschlange(), "gebaut_gesamt": len(v["shorts"]),
                          "letzte": v["shorts"][-3:]}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

