"""Stimm-Veredelung Variante A, Schritt 2 (rexemres Wahl 01.10.2026, Task 20261001-165559-5e26/180145-c47f):
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

Wiederholung (Vorfall 04.10. 13:11 und 10.10.2026 05:24, Task 20261010-081203-3ba8): der Enhance-Worker starb beide
Male ohne Python-Traceback im NVIDIA-Treiber (python.exe in nvcuda64.dll, Ausnahmecode 0xC0000409, Windows-
Ereignisprotokoll), waehrend parallel der LatentSync-Rohschnitt einer anderen Folge auf derselben Karte rechnete.
Ein einzelner Anlauf liess die ganze Vertonung und damit den Tageslauf abbrechen («stimme: Vertonung
fehlgeschlagen»), obwohl der naechste Anlauf problemlos lief. Jetzt: bis zu VERSUCHE_GPU Anlaeufe auf der GPU
(kurze Pause dazwischen), danach ein Anlauf auf der CPU (langsam, aber unabhaengig vom Treiber); erst wenn auch der
scheitert, bricht die Vertonung ab - mit Exit-Code (hex) und Geraet je Anlauf im Fehlertext, damit Wache und Log die
Ursache sehen. Test: tests/test_veredelung_rueckfall.py (offline, ohne GPU).
"""
import contextlib
import os
import subprocess
import sys
import time
from pathlib import Path

from config.settings import BASE_DIR, ENHANCE_PYTHON

sys.path.insert(0, str(BASE_DIR))
import gpu_budget  # noqa: E402

ROOM_IR = BASE_DIR / "config" / "brand" / "stimme" / "veredelung_room_ir.wav"
SR = 24000

# Windows-Ausnahmecodes als Exit-Code eines abgestuerzten Prozesses: 0xC0000409 (Fail-Fast, z.B. nvcuda64.dll),
# 0xC0000005 (Zugriffsverletzung), 0xC000001D ... - alles ab 0xC0000000 ist ein Absturz, kein regulaerer Fehler.
ABSTURZ_CODE_AB = 0xC0000000
VERSUCHE_GPU = 2        # Anlaeufe auf der GPU, danach einmal CPU
PAUSE_S = 20            # Pause zwischen zwei Anlaeufen (Treiber erholt sich, anderer Job gibt Speicher frei)

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


class WorkerFehler(RuntimeError):
    """Unterprozess mit Exit-Code != 0; .returncode fuer die Absturz-Erkennung."""

    def __init__(self, msg: str, returncode: int | None):
        super().__init__(msg)
        self.returncode = returncode


def ist_absturz(returncode) -> bool:
    """Exit-Code eines abgestuerzten Prozesses (Windows-Ausnahmecode >= 0xC0000000, von subprocess auch als
    negative Zahl gemeldet) - im Unterschied zu einem regulaeren Fehler-Exit (1, 2, ...)."""
    if returncode is None:
        return False
    rc = int(returncode)
    return rc < 0 or rc >= ABSTURZ_CODE_AB


def exit_text(returncode) -> str:
    rc = int(returncode or 0)
    return f"Exit {rc} (0x{rc & 0xFFFFFFFF:08X})"


def _run(cmd):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise WorkerFehler(f"{exit_text(r.returncode)}: " + " ".join(map(str, cmd))[:300] + "\n" + r.stderr[-1500:],
                           r.returncode)
    return r


def _enhance(wav_path: Path, enhanced: Path, log=print, versuche_gpu: int = VERSUCHE_GPU, cpu_rueckfall: bool = True,
             pause_s: float | None = None) -> str:
    """Resemble Enhance mit Wiederholung: versuche_gpu Anlaeufe auf der GPU (ueber die zentrale Warteschlange), dann
    ein Anlauf auf der CPU. Rueckgabe: Geraet des erfolgreichen Anlaufs ("cuda"/"cpu"). Wirft RuntimeError mit allen
    Anlaeufen (Exit-Code, Geraet), wenn keiner eine Ausgabedatei liefert."""
    pause_s = PAUSE_S if pause_s is None else pause_s
    plan = ["cuda"] * max(0, int(versuche_gpu)) + (["cpu"] if cpu_rueckfall else [])
    if not plan:
        raise ValueError("kein Anlauf geplant (versuche_gpu=0 und kein CPU-Rueckfall)")
    fehler = []
    for i, device in enumerate(plan, 1):
        enhanced.unlink(missing_ok=True)
        try:
            ctx = (gpu_budget.slot("enhance", name=f"Stimm-Veredelung {wav_path.stem}") if device == "cuda"
                   else contextlib.nullcontext())
            with ctx:
                _run([ENHANCE_PYTHON, BASE_DIR / "tts" / "_enhance_worker.py", wav_path, enhanced, "enhance", "0.5",
                      device])
            if enhanced.exists() and enhanced.stat().st_size > 44:
                if i > 1:
                    log(f"  {wav_path.name}: Veredelung Anlauf {i} ({device}) erfolgreich")
                return device
            fehler.append(f"Anlauf {i} ({device}): Worker ohne Fehler, aber keine Ausgabedatei")
        except WorkerFehler as ex:
            art = ("Absturz (Windows-Ausnahmecode, typisch NVIDIA-Treiber nvcuda64.dll)" if ist_absturz(ex.returncode)
                   else "Fehler")
            fehler.append(f"Anlauf {i} ({device}): {art} {ex}")
        log(f"  {wav_path.name}: Veredelung {fehler[-1].splitlines()[0][:200]}")
        if i < len(plan) and pause_s > 0:
            time.sleep(pause_s)
    raise RuntimeError(f"Stimm-Veredelung {wav_path.name} endgueltig fehlgeschlagen ({len(plan)} Anlaeufe):\n"
                       + "\n".join(fehler))


def veredeln(wav_path: Path, log=print) -> str:
    """Veredelt wav_path in place (Enhance -> Klangkette + 10 % Raum -> zurueck auf 24 kHz mono 16 bit).
    Rueckgabe: Geraet des Enhance-Anlaufs ("cuda"/"cpu")."""
    wav_path = Path(wav_path)
    if not ENHANCE_PYTHON.exists():
        raise FileNotFoundError(f"{ENHANCE_PYTHON} fehlt - .venv-enhance nicht eingerichtet")
    enhanced = wav_path.with_name(wav_path.stem + "_enh.wav")
    t = time.time()
    device = _enhance(wav_path, enhanced, log=log)
    out = wav_path.with_name(wav_path.stem + "_ver.wav")
    f = (f"[0:a]{AUDIO_CHAIN}[dry];[dry]asplit=2[dry1][dry2];"
         f"[dry2][1:a]afir=dry=0:wet=10[wet];"
         f"[dry1][wet]amix=inputs=2:weights=1.0 0.11:normalize=0[mix]")
    _run([FFMPEG, "-y", "-v", "error", "-i", enhanced, "-i", ROOM_IR, "-filter_complex", f, "-map", "[mix]",
          "-ar", str(SR), "-ac", "1", "-c:a", "pcm_s16le", out])
    out.replace(wav_path)
    enhanced.unlink(missing_ok=True)
    log(f"  {wav_path.name}: veredelt in {time.time() - t:.0f} s ({device})")
    return device


if __name__ == "__main__":
    veredeln(Path(sys.argv[1]))
