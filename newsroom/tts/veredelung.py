"""Stimm-Veredelung Variante A, Schritt 2 (Marlons Wahl 01.10.2026, Task 20261001-165559-5e26/180145-c47f):
Resemble Enhance (MIT, .venv-enhance, tts/_enhance_worker.py) holt die Hoehen zurueck, die Chatterbox nicht liefert,
danach eine leichte Klangkette (Mulm raus, Praesenz, Zischlaute daempfen, sanft komprimieren, 10 % Raum).
Schritt 1 (satzweise Pausen + Atmer) passiert in tts/chatterbox_worker.py selbst (--veredeln).

Aufgerufen von tts/tts_client.py nach _tempo(); Ausgabe bleibt wie vorher 24 kHz mono 16 bit (STIMME_SR in
tools/weltlage_tts.py), deshalb bleiben Stimmpruefung und Abnahme unveraendert. Lautheit wird hier nicht
normalisiert - das macht weiterhin tools/weltlage_rohschnitt.py im Master (loudnorm nur linear).

Schalter: config/settings.NEWS_WELTLAGE_STIMME_VEREDELN (Default an).
Seit 01.10.2026 (Task 98b7) auf der GPU ueber gpu_budget.slot("enhance") (zentrale Warteschlange, ~4,2 GB VRAM,
gemessen auf der RTX 4090) statt CPU: rund 1-2 s Rechenzeit je Sekunde Ton statt vorher ~8 s/s auf der CPU. A/B-Probe
desselben Satzes CPU vs. GPU: Pegel (RMS/Peak) innerhalb 0.2 dB, Hochton-Anteil >8 kHz innerhalb 0.3 dB - die
Unterschiede liegen im selben Rahmen wie zwei CPU-Laeufe desselben Satzes (das Modell samplet stochastisch), die GPU
veraendert die Klangqualitaet also nicht. Faellt automatisch auf CPU zurueck, wenn .venv-enhance kein CUDA hat.
"""
import os
import subprocess
import sys
from pathlib import Path

from config.settings import BASE_DIR, ENHANCE_PYTHON

sys.path.insert(0, str(BASE_DIR))
import gpu_budget  # noqa: E402

ROOM_IR = BASE_DIR / "config" / "brand" / "stimme" / "veredelung_room_ir.wav"
SR = 24000

_ff = next(iter(Path(os.environ.get("LOCALAPPDATA", "")).glob("Microsoft/WinGet/Packages/Gyan.FFmpeg*/*/bin")), None)
FFMPEG = str(_ff / "ffmpeg.exe") if _ff else "ffmpeg"

# gleiche Klangkette wie die Probe (Task 5e26 proben_code/post.py:veredeln): Tiefen entmulmen, Praesenz anheben,
# Zischlaute daempfen, sanft komprimieren
AUDIO_CHAIN = (
    "highpass=f=75,"
    "equalizer=f=280:t=q:w=1.0:g=-2.5,"
    "equalizer=f=3200:t=q:w=1.2:g=2.0,"
    "equalizer=f=9500:t=h:w=0.7:g=0.5,"
    "deesser=i=0.35:m=0.5:f=0.5:s=o,"
    "acompressor=threshold=-20dB:ratio=2.2:attack=8:release=140:makeup=2"
)


def _run(cmd):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise RuntimeError(" ".join(map(str, cmd))[:300] + "\n" + r.stderr[-1500:])
    return r


def veredeln(wav_path: Path, log=print) -> None:
    """Veredelt wav_path in place (Enhance -> Klangkette + 10 % Raum -> zurueck auf 24 kHz mono 16 bit)."""
    wav_path = Path(wav_path)
    if not ENHANCE_PYTHON.exists():
        raise FileNotFoundError(f"{ENHANCE_PYTHON} fehlt - .venv-enhance nicht eingerichtet")
    enhanced = wav_path.with_name(wav_path.stem + "_enh.wav")
    t = __import__("time").time()
    with gpu_budget.slot("enhance", name=f"Stimm-Veredelung {wav_path.stem}"):
        _run([ENHANCE_PYTHON, BASE_DIR / "tts" / "_enhance_worker.py", wav_path, enhanced, "enhance", "0.5"])
    out = wav_path.with_name(wav_path.stem + "_ver.wav")
    f = (f"[0:a]{AUDIO_CHAIN}[dry];[dry]asplit=2[dry1][dry2];"
         f"[dry2][1:a]afir=dry=0:wet=10[wet];"
         f"[dry1][wet]amix=inputs=2:weights=1.0 0.11:normalize=0[mix]")
    _run([FFMPEG, "-y", "-v", "error", "-i", enhanced, "-i", ROOM_IR, "-filter_complex", f, "-map", "[mix]",
          "-ar", str(SR), "-ac", "1", "-c:a", "pcm_s16le", out])
    out.replace(wav_path)
    enhanced.unlink(missing_ok=True)
    log(f"  {wav_path.name}: veredelt in {__import__('time').time() - t:.0f} s")


if __name__ == "__main__":
    import sys
    veredeln(Path(sys.argv[1]))
