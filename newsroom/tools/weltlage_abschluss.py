"""Weltlage Kompakt - Abschluss-Vorlage (fest eingefroren, analog zu tools/weltlage_begruessung.py /
tools/weltlage_verabschiedung.py).

Ersetzt die alte Outro-Grafik (output/outro_v3, reine Musik/Logo-Animation ohne Latara) als letzte Szene der
Folge (rexemre 04.10.2026): ein kurzer, eigenstaendiger Kanal-Abschluss mit Latara (ein zeitloser Ausblick-Satz,
kein Bezug zum Folgeninhalt - die eigentliche Verabschiedung/der "bis morgen" bleibt in der bestehenden Szene
Verabschiedung), dazu das WK-Logo im Studio und der animierte Abo-Hinweis (tools/endscreen_overlay.render_abo_icon,
wird von tools/weltlage_rohschnitt.py per abo_overlay() ueber diese Szene gelegt - nicht hier eingebrannt, damit
beide Bausteine unabhaengig voneinander ausgetauscht werden koennen). Der Text ist in jeder Folge wortgleich,
darum wie Begruessung/Verabschiedung einmal gebaut und seither nur noch eingebunden statt jede Folge neu zu
vertonen und zu lipsyncen.

Startposition im stehenden Freisteller: Taktmitte des Idle-Materials wie die Verabschiedung (start = (Laenge -
Audiolaenge) / 2), damit sich die Bewegung nicht mit Begruessung/Themen/Verabschiedung wiederholt.

Schwere GPU-Schritte (Chatterbox, LatentSync) reihen sich selbst in die GPU-Warteschlange ein
(gpu_budget.slot/hold) - NICHT zusaetzlich in gpu_queue.py run einwickeln (Verklemmung). Nie parallel zu einem
laufenden Folgen-Render starten (gemeinsame GPU-Warteschlange/Sperre reichen das zwar sicher durch, kosten aber
dem laufenden Render Wartezeit):
    .venv-lipsync\\Scripts\\python.exe tools\\weltlage_abschluss.py build
    .venv-lipsync\\Scripts\\python.exe tools\\weltlage_abschluss.py freeze
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

WORK = ROOT / "_work" / "abschluss"
FROZEN = ROOT / "config" / "brand" / "abschluss"

VERSION = "abschluss_v1.mp4"
TEXT = "Weltlage Kompakt: die Welt in wenigen Minuten, jeden Tag neu, hier auf diesem Kanal."
ABO_AT = 0.6   # der Abo-Hinweis blendet kurz nach Szenenbeginn ein (tools/weltlage_rohschnitt.py abo_overlay)

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
    raw = WORK / "abschluss_raw.wav"
    sys.path.insert(0, str(ROOT / "tools"))
    from weltlage_tts import pruefe_stimme
    if pruefe_stimme(raw):          # Chatterbox + Whisper-Kontrolle laufen im Basis-.venv (faster-whisper)
        subprocess.run([str(ROOT / ".venv" / "Scripts" / "python.exe"), str(ROOT / "tools" / "weltlage_tts.py"),
                        "--probe", TEXT, str(raw)], check=True)
    fehler = pruefe_stimme(raw)
    if fehler:
        raise SystemExit(fehler)
    length = dur(raw) + 0.25 + 0.6
    wav = WORK / "abschluss_ton.wav"
    pad_wav(raw, 0.25, length, wav)
    # Taktmitte des stehenden Idle-Materials, wie die Verabschiedung (start6 frueher in weltlage_rohschnitt.py) -
    # einmalig hier berechnet, bleibt danach fest.
    v6_total = dur(fl.POSEN["stehend"]["src"])
    start = max(0.0, (v6_total - length) / 2)
    comp = fl.render_scene("stehend", wav, start, length, WORK, "abschluss", log=lambda m: print(m, flush=True))
    out = WORK / VERSION
    # kein loudnorm hier: Lautheit wird genau einmal im Master gesetzt (tools/weltlage_rohschnitt.master_ton);
    # der Rohschnitt nimmt den Ton ohnehin aus der Stimm-wav, nicht aus diesem Clip
    run([FFMPEG, "-y", "-i", str(comp), "-i", str(wav), "-map", "0:v", "-map", "1:a", "-c:v", "copy",
         "-ar", str(SR), "-ac", "2", "-c:a", "aac", "-b:a", "256k",
         "-movflags", "+faststart", str(out)])
    print("BUILD FERTIG", out, f"{length:.1f}s", f"start={start:.2f}s")
    return out


def _stimme_text() -> str:
    from tts.stimme_profil import profil
    p = profil()
    return (f"Chatterbox Profil {p['profil']} ({Path(p['ref']).name}, exaggeration {p['exaggeration']}, cfg {p['cfg']}, "
            f"tempo {p.get('tempo', 1.0)})")


def freeze():
    """Kopiert den Clip nach FROZEN und schreibt aktiv.json samt "guidance"/"hd"/"pipeline": tools/weltlage_abnahme.py
    vergleicht diese Felder gegen die aktuellen Einstellungen (config.settings.NEWS_WELTLAGE_LIPSYNC_GUIDANCE/_HD,
    video.freisteller_lipsync.pipeline_signatur) und bricht ab, wenn eine Folge mit einer veralteten eingefrorenen
    Fassung landen wuerde - gleiches Muster wie Begruessung/Verabschiedung."""
    src = WORK / VERSION
    if not src.exists():
        raise SystemExit(f"{src} fehlt - zuerst 'build' laufen lassen.")
    FROZEN.mkdir(parents=True, exist_ok=True)
    import shutil
    dst = FROZEN / VERSION
    if dst.exists():   # bisherige Fassung sichern (z.B. andere Lipsync-Stufe), nie stumm ueberschreiben
        shutil.copy2(dst, dst.with_name(f"{dst.stem}_ALT_{time.strftime('%Y%m%d_%H%M')}{dst.suffix}"))
    shutil.copy2(src, dst)
    # Stimm-Datei samt Engine-Nachweis neben den Clip: der Rohschnitt prueft damit Engine/Hash und gleicht den Ton
    # des Clips im fertigen Video gegen genau diese Datei ab (tools/weltlage_stimmpruefung.py).
    stimme = FROZEN / (Path(VERSION).stem + "_stimme.wav")
    for endung in (".wav", ".tts.json"):
        shutil.copy2(WORK / f"abschluss_raw{endung}", stimme.with_suffix(endung))
    laenge = dur(dst)
    (FROZEN / "aktiv.json").write_text(json.dumps({
        "landscape": VERSION,
        "stimme": _stimme_text(),
        "stimme_wav": stimme.name,
        "stimme_vorlauf_s": 0.25,
        "text": TEXT,
        "abo_at": ABO_AT,
        "guidance": fl.GUIDANCE,
        "hd": fl.HD,
        "pipeline": fl.pipeline_signatur(),
        "gebaut": time.strftime("%Y-%m-%d %H:%M"),
        "quelle": "tools/weltlage_abschluss.py",
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
