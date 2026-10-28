"""Weltlage Kompakt - Begruessungs-Vorlage (Struktur vom 30.09.2026, rexemre): Latara steht am Pult und
begruesst das Publikum ganz allgemein, ohne Datum und ohne die heutigen Themen zu nennen, damit der Clip
zeitlos ist und in jeder Folge unveraendert wiederverwendet werden kann (analog zur eingefrorenen Szene 3
"Auftritt", siehe tools/szene3_auftritt.py und docs/weltlage_szenenplan.md).

Ablauf (einmalig - danach wird nur noch aus config/brand/begruessung/ eingebunden, nie neu gerendert):
  1. TTS mit Lataras Stimme (Chatterbox-Klon Ramona via tools/weltlage_tts.py --probe im Basis-.venv, mit
     Engine-Nachweis begruessung_raw.tts.json) auf den festen Begruessungstext. Seit 30.09.2026 Chatterbox statt
     Piper (rexemres Entscheid, Piper-Umstellung vom 29.09. zurueckgenommen) -> begruessung_v2.mp4.
  2. Freisteller-Lipsync + Studio-Composite auf der stehenden Pose (video/freisteller_lipsync.render_scene),
     Start bei V6-Position 0 - derselbe Frame, auf dem Szene 3 "Reinlaufen" endet.
  3. Ton draufmuxen, nach config/brand/begruessung/<VERSION> kopieren, aktiv.json schreiben.

Schwere GPU-Schritte (Chatterbox, LatentSync) reihen sich selbst in die GPU-Warteschlange ein
(gpu_budget.slot/hold) - NICHT zusaetzlich in gpu_queue.py run einwickeln (Verklemmung):
    .venv-lipsync\\Scripts\\python.exe tools\\weltlage_begruessung.py build
    .venv-lipsync\\Scripts\\python.exe tools\\weltlage_begruessung.py freeze
"""
import json
import os
import subprocess
import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from video import freisteller_lipsync as fl

WORK = ROOT / "_work" / "begruessung"
FROZEN = ROOT / "config" / "brand" / "begruessung"

# Sinngemaess rexemres Vorgabe (29./30.09.2026): kurz, zeitlos, kein Datum, keine Themen.
VERSION = "begruessung_v3.mp4"   # v3 (30.09. spaet) = Kerstin CC0 Profil C, Tempo 1.15; v2 = Ramona-Chatterbox; v1 (30.09. 11:16) = Piper-Stimme, bleibt nur als Backup liegen
TEXT = "Willkommen bei Weltlage Kompakt, ich bin Latara. Heute kommen die folgenden Themen."

_ff = next(iter(Path(os.environ["LOCALAPPDATA"]).glob("Microsoft/WinGet/Packages/Gyan.FFmpeg*/*/bin")), None)
FFMPEG = str(_ff / "ffmpeg.exe") if _ff else "ffmpeg"
FFPROBE = str(_ff / "ffprobe.exe") if _ff else "ffprobe"
SR = 48000


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise RuntimeError(" ".join(map(str, cmd))[:400] + "\n" + r.stderr[-2000:])


def dur(path: Path) -> float:
    if path.suffix == ".wav":
        with wave.open(str(path)) as w:
            return w.getnframes() / w.getframerate()
    out = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                          capture_output=True, text=True).stdout
    return float(out.strip())


def pad_wav(src: Path, pre: float, total: float, out: Path):
    run([FFMPEG, "-y", "-i", str(src), "-af", f"aresample={SR},adelay={int(pre * 1000)},apad",
         "-ac", "1", "-t", f"{total:.3f}", str(out)])


def build() -> Path:
    if not fl.haar_ok():   # muss mit .venv-lipsync laufen (OpenCV 4, Haar-Kaskaden), siehe Docstring
        raise SystemExit("Bitte mit .venv-lipsync\\Scripts\\python.exe starten (siehe Docstring).")
    WORK.mkdir(parents=True, exist_ok=True)
    raw = WORK / "begruessung_raw.wav"
    sys.path.insert(0, str(ROOT / "tools"))
    from weltlage_tts import pruefe_stimme
    if pruefe_stimme(raw):          # Chatterbox + Whisper-Kontrolle laufen im Basis-.venv (faster-whisper)
        subprocess.run([str(ROOT / ".venv" / "Scripts" / "python.exe"), str(ROOT / "tools" / "weltlage_tts.py"),
                        "--probe", TEXT, str(raw)], check=True)
    fehler = pruefe_stimme(raw)
    if fehler:
        raise SystemExit(fehler)
    length = dur(raw) + 0.25 + 0.6
    wav = WORK / "begruessung_ton.wav"
    pad_wav(raw, 0.25, length, wav)
    comp = fl.render_scene("stehend", wav, 0.0, length, WORK, "begruessung", log=lambda m: print(m, flush=True))
    out = WORK / VERSION
    # kein loudnorm hier: Lautheit wird genau einmal im Master gesetzt (tools/weltlage_rohschnitt.master_ton, Task
    # 20260930-210208-ed2c); der Rohschnitt nimmt den Ton ohnehin aus der Stimm-wav, nicht aus diesem Clip
    run([FFMPEG, "-y", "-i", str(comp), "-i", str(wav), "-map", "0:v", "-map", "1:a", "-c:v", "copy",
         "-ar", str(SR), "-ac", "2", "-c:a", "aac", "-b:a", "256k",
         "-movflags", "+faststart", str(out)])
    print("BUILD FERTIG", out, f"{length:.1f}s")
    return out


def _stimme_text() -> str:
    from tts.stimme_profil import profil
    p = profil()
    return (f"Chatterbox Profil {p['profil']} ({Path(p['ref']).name}, exaggeration {p['exaggeration']}, cfg {p['cfg']}, "
            f"tempo {p.get('tempo', 1.0)})")


def freeze():
    """Kopiert den Clip nach FROZEN und schreibt aktiv.json samt "guidance"/"hd" (Task 20261002-163146-afaf,
    02.10.2026): ohne diese Felder liess sich nicht pruefen, ob eine eingefrorene Fassung noch zur aktuellen
    Lipsync-Staerke passt - tools/weltlage_abnahme.py vergleicht sie gegen config.settings.
    NEWS_WELTLAGE_LIPSYNC_GUIDANCE/_HD und bricht bei Abweichung ab. Fassungen von vor diesem Datum (z.B.
    begruessung_v3.mp4) haben die Felder nicht; Abnahme gibt dafuer nur eine Warnung, keinen Abbruch.
    Seit 03.10.2026 zusaetzlich "pipeline": fl.pipeline_signatur() - die eine, gemeinsame Signatur aller
    Pipeline-Schalter (siehe video/freisteller_lipsync.pipeline_signatur). tools/weltlage_abnahme.py prueft dieses
    Feld vollstaendig und generisch; fehlt es (Fassungen von vor diesem Datum), wieder nur eine Warnung."""
    src = WORK / VERSION
    if not src.exists():
        raise SystemExit(f"{src} fehlt - zuerst 'build' laufen lassen.")
    FROZEN.mkdir(parents=True, exist_ok=True)
    import shutil
    dst = FROZEN / VERSION
    shutil.copy2(src, dst)
    # Stimm-Datei samt Engine-Nachweis neben den Clip: der Rohschnitt prueft damit Engine/Hash und gleicht den Ton
    # des Clips im fertigen Video gegen genau diese Datei ab (tools/weltlage_stimmpruefung.py).
    stimme = FROZEN / (Path(VERSION).stem + "_stimme.wav")
    for endung in (".wav", ".tts.json"):
        shutil.copy2(WORK / f"begruessung_raw{endung}", stimme.with_suffix(endung))
    laenge = dur(dst)
    (FROZEN / "aktiv.json").write_text(json.dumps({
        "landscape": VERSION,
        "stimme": _stimme_text(),
        "stimme_wav": stimme.name,
        "stimme_vorlauf_s": 0.25,
        "text": TEXT,
        "guidance": fl.GUIDANCE,
        "hd": fl.HD,
        "pipeline": fl.pipeline_signatur(),
        "gebaut": time.strftime("%Y-%m-%d %H:%M"),
        "quelle": "tools/weltlage_begruessung.py",
        "laenge_s": round(laenge, 3),
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print("eingefroren", dst, f"{laenge:.2f}s")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "build":
        build()
    elif cmd == "freeze":
        freeze()
    else:
        raise SystemExit(__doc__)
