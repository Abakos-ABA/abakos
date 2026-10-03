"""Weltlage Kompakt - Verabschiedungs-Vorlage (fest eingefroren, analog zu tools/weltlage_begruessung.py).

Der Abschiedstext ist in jeder Folge wortgleich (tools/weltlage_skript.py OUTRO["text"], dort als "s6_outro fest"
unveraendert in jede texte.json geschrieben). Bis 02.10.2026 wurde die Szene trotzdem jede Folge neu vertont und
neu gelipsynct (gleicher Text, aber neue TTS-Aufnahme + rund zwei LatentSync-Stuecke a ~7 min GPU-Zeit) - genau
das Muster, das die Begruessung seit dem 30.09.2026 schon vermeidet. Darum jetzt derselbe Weg: einmal TTS +
Freisteller-Lipsync + Studio-Composite, danach nur noch eingebunden (tools/weltlage_rohschnitt.py, Abschnitt
"Verabschiedung" - faellt automatisch auf den alten Pro-Folge-Weg zurueck, solange hier noch nicht gebaut wurde).

Startposition im stehenden Freisteller: anders als die Begruessung (Position 0) startet die Verabschiedung an der
Taktmitte des Idle-Materials, wie es frueher weltlage_rohschnitt.py pro Folge live berechnete (start6 = (Laenge -
Audiolaenge) / 2) - damit wiederholt sich die Bewegung nicht mit Begruessung/Themen. Bei einer fest eingefrorenen
Fassung bleibt dieser Abstand in jeder Folge gleich (vorher zufaellig je nach Audiolaenge der Folge).

Schwere GPU-Schritte (Chatterbox, LatentSync) reihen sich selbst in die GPU-Warteschlange ein
(gpu_budget.slot/hold) - NICHT zusaetzlich in gpu_queue.py run einwickeln (Verklemmung). Nie parallel zu einem
laufenden Folgen-Render starten (gemeinsame GPU-Warteschlange/Sperre reichen das zwar sicher durch, kosten aber
dem laufenden Render Wartezeit):
    .venv-lipsync\\Scripts\\python.exe tools\\weltlage_verabschiedung.py build
    .venv-lipsync\\Scripts\\python.exe tools\\weltlage_verabschiedung.py freeze
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

WORK = ROOT / "_work" / "verabschiedung"
FROZEN = ROOT / "config" / "brand" / "verabschiedung"

# Wortgleich mit tools/weltlage_skript.py OUTRO["text"]/["abo_at"] ("s6_outro fest") - bei einer Aenderung dort
# auch hier nachziehen und neu bauen (build + freeze).
VERSION = "verabschiedung_v1.mp4"
TEXT = ("Das war Weltlage Kompakt für heute. Morgen bin ich wieder hier mit der Weltlage. Wenn du nichts "
        "verpassen willst, abonniere den Kanal. Danke fürs Zuschauen, bis morgen.")
ABO_AT = 4.6

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
    raw = WORK / "verabschiedung_raw.wav"
    sys.path.insert(0, str(ROOT / "tools"))
    from weltlage_tts import pruefe_stimme
    if pruefe_stimme(raw):          # Chatterbox + Whisper-Kontrolle laufen im Basis-.venv (faster-whisper)
        subprocess.run([str(ROOT / ".venv" / "Scripts" / "python.exe"), str(ROOT / "tools" / "weltlage_tts.py"),
                        "--probe", TEXT, str(raw)], check=True)
    fehler = pruefe_stimme(raw)
    if fehler:
        raise SystemExit(fehler)
    length = dur(raw) + 0.25 + 0.6
    wav = WORK / "verabschiedung_ton.wav"
    pad_wav(raw, 0.25, length, wav)
    # Taktmitte des stehenden Idle-Materials, wie fruehen weltlage_rohschnitt.py (start6) es pro Folge live
    # berechnete - einmalig hier berechnet, bleibt danach fest.
    v6_total = dur(fl.POSEN["stehend"]["src"])
    start = max(0.0, (v6_total - length) / 2)
    comp = fl.render_scene("stehend", wav, start, length, WORK, "verabschiedung", log=lambda m: print(m, flush=True))
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
    """Kopiert den Clip nach FROZEN und schreibt aktiv.json samt "guidance"/"hd": tools/weltlage_abnahme.py
    vergleicht diese Felder gegen die aktuellen Einstellungen (config.settings.NEWS_WELTLAGE_LIPSYNC_GUIDANCE/_HD)
    und bricht ab, wenn eine Folge mit einer veralteten eingefrorenen Fassung (z.B. andere Lipsync-Staerke) landen
    wuerde - gleiches Muster wie tools/weltlage_begruessung.py. Seit 03.10.2026 zusaetzlich "pipeline":
    fl.pipeline_signatur() (ein Dict fuer alle Pipeline-Schalter, siehe dort)."""
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
        shutil.copy2(WORK / f"verabschiedung_raw{endung}", stimme.with_suffix(endung))
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
        "quelle": "tools/weltlage_verabschiedung.py",
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
