"""Weltlage Kompakt: Standard-Intro aus dem Unreal-Studio (rexemre 20.10.2026, ersetzt das Globus-Intro vollstaendig).

Jede Folge bekommt ihr Intro frisch: Unreal-Studio-Szene (Globus/Studio, 12 s) + Boersenticker mit den
TAGESAKTUELLEN Kursen (SMI, DAX, S&P, Nasdaq, Dow, Gold, Brent, BTC, EUR/CHF, USD/CHF) + Latara spricht das
Folgendatum + ACE-Musikbett. Gebaut wird in Jarvis (tools/unreal_studio/studio.py, Befehl `intro`); die Unreal-Bilder
sind tagesunabhaengig und gecacht, nur Ticker, Datumsansage und Kodierung laufen pro Folge neu. GPU immer ueber
tools/gpu_queue.py (rendert studio.py selbst, TTS reiht sich selbst ein) - dieses Modul wickelt nichts ein.

Datei: config/brand/intro/weltlage_intro_unreal_standard.mp4 (+ .json mit Datum/Ticker/Ton). Sie wird bei jeder Folge
atomar ERSETZT und ist damit zugleich der Rueckfall «letzte gute Fassung». Rohschnitt (vorbereiten) und Abnahme
(pruefen) benutzen sie; intro/aktiv.json zeigt darauf und traegt "unreal_standard": true. Das alte Globus-Intro
(weltlage_intro_v8_ace.mp4) liegt nur noch als Datei da und wird nirgends mehr verwendet; die Abnahme bricht ab, wenn
aktiv.json wieder darauf zeigt.

Rueckfaelle (Folge nie blockieren, aber laut loggen): keine Kursquelle -> letzte guten Kurse (Zeitstempel im Bild);
Datumsansage scheitert -> nur Musik; Unreal-Render/Kodieren scheitert -> letzte gute Intro-Datei (Warnung der Abnahme,
wenn ihr Datum nicht zur Folge passt).

    .venv\Scripts\python tools\weltlage_intro.py 2026-10-21 [--erzwingen]
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INTRO_DIR = ROOT / "config" / "brand" / "intro"
STANDARD_NAME = "weltlage_intro_unreal_standard.mp4"
STANDARD = INTRO_DIR / STANDARD_NAME
AKTIV = INTRO_DIR / "aktiv.json"
JARVIS = (Path.home() / r"projekte\jarvis")
JARVIS_PY = JARVIS / ".venv" / "Scripts" / "python.exe"
STUDIO = JARVIS / "tools" / "unreal_studio" / "studio.py"
TIMEOUT_S = 4 * 3600                      # Unreal-Neurender (selten) + GPU-Wartezeit; sonst wenige Minuten


def meta_lesen(pfad: Path | None = None) -> dict:
    pfad = pfad or STANDARD
    try:
        return json.loads(pfad.with_name(pfad.name + ".json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def aktiv_pruefen() -> list[str]:
    """Fehler, wenn intro/aktiv.json nicht auf das Unreal-Standard-Intro zeigt (altes Globus-Intro kaeme zurueck)."""
    try:
        cfg = json.loads(AKTIV.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return [f"intro/aktiv.json nicht lesbar: {e}"]
    fehler = []
    if cfg.get("landscape") != STANDARD_NAME:
        fehler.append(f"intro/aktiv.json zeigt auf {cfg.get('landscape')!r} statt auf das Unreal-Standard-Intro "
                      f"{STANDARD_NAME} - das alte Globus-Intro ist abgeloest (rexemre 20.10.2026)")
    if not STANDARD.exists():
        fehler.append(f"{STANDARD_NAME} fehlt - tools/weltlage_intro.py <datum> ausfuehren")
    return fehler


def pruefen(folgendatum: str | None) -> tuple[list[str], list[str]]:
    """(Fehler, Warnungen) fuer die Abnahme: aktiv.json korrekt; Datum/Kurse/Ton des Intros passen zur Folge."""
    fehler, warn = aktiv_pruefen(), []
    meta = meta_lesen()
    if not meta:
        warn.append("Intro: keine Meta-Datei (.json) zum Standard-Intro - unklar, mit welchem Datum es gebaut wurde")
        return fehler, warn
    if folgendatum and meta.get("datum") != folgendatum:
        warn.append(f"Intro: gesprochen/gebaut fuer {meta.get('datum')}, Folge ist vom {folgendatum} "
                    f"(Rueckfall auf die letzte gute Fassung, Unreal-Intro-Bau schlug fehl)")
    if meta.get("ticker") == "alt":
        warn.append("Intro: Boersenticker zeigt die letzten guten Kurse (keine Kursquelle erreichbar)")
    elif meta.get("ticker") == "nein":
        warn.append("Intro: Boersenticker fehlt (keine Kurse, keine fruehere Fassung)")
    return fehler, warn


def vorbereiten(datum: str, erzwingen: bool = False, log=print) -> dict:
    """Baut das Intro fuer `datum` (JJJJ-MM-TT), falls es dafuer nicht schon heute gebaut wurde. Wirft nie;
    gibt die Meta zurueck ({"ok": bool, ...}); bei ok False bleibt die letzte gute Fassung liegen."""
    date.fromisoformat(datum)
    meta = meta_lesen()
    if not erzwingen and meta.get("ok") and meta.get("datum") == datum and STANDARD.exists():
        log(f"Intro: fuer {datum} schon gebaut ({meta.get('stand')}), wiederverwendet")
        return meta
    log(f"Intro: baue Unreal-Standard-Intro fuer {datum} (Kurse live, Datumsansage, GPU ueber die Warteschlange)")
    cmd = [str(JARVIS_PY), str(STUDIO), "intro", "--datum", datum, "--ziel", str(STANDARD)]
    try:
        r = subprocess.run(cmd, cwd=str(JARVIS), capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=TIMEOUT_S)
        for z in (r.stdout or "").strip().splitlines()[-25:]:
            log(f"  intro| {z}")
        if r.returncode != 0 and r.stderr:
            log(f"  intro| stderr: {r.stderr.strip()[-600:]}")
        meta = {**meta_lesen(), "rc": r.returncode} if r.returncode == 0 else {"ok": False, "rc": r.returncode}
    except Exception as e:                                # noqa: BLE001 - Folge nie blockieren
        log(f"Intro: FEHLER beim Bau: {e}")
        meta = {"ok": False, "fehler": str(e)[:300]}
    if not meta.get("ok"):
        alt = meta_lesen()
        log(f"Intro: WARNUNG Bau fehlgeschlagen - letzte gute Fassung ({alt.get('datum', 'unbekannt')}) bleibt im Einsatz")
    return meta


if __name__ == "__main__":
    d = next((a for a in sys.argv[1:] if not a.startswith("--")), date.today().isoformat())
    m = vorbereiten(d, erzwingen="--erzwingen" in sys.argv)
    print(json.dumps(m, ensure_ascii=False))
    sys.exit(0 if m.get("ok") else 1)
