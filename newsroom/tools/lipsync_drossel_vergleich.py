"""Lipsync-Drosselprobe (rexemres Auftrag, Task 20261019-120910-a2ea): 4 Stufen abnehmender Lipsync-Qualitaet/
Rechenaufwand auf einem 5-s-Ausschnitt einer aktuellen Weltlage-Folge, je Rechenzeit pro Sekunde Video gemessen.

Stufe 1 = heutiger Produktionsstandard (video/freisteller_lipsync.py: STEPS=8, GUIDANCE=2.0, ZOOM=768). Die Hebel
fuer die weiteren Stufen (Schritte, Guidance, Fenster/Aufloesung) stammen aus den bisherigen Lipsync-Vergleichen
(docs/lipsync_qualitaet.md, tools/lipsync_steps_vergleich.py, tools/lipsync_guidance_vergleich.py):
  - STEPS: Diffusionsschritte, nahezu linear in der Rechenzeit.
  - GUIDANCE (classifier-free guidance): LatentSync-Pipeline rechnet das UNet bei guidance_scale > 1.0 ZWEIMAL pro
    Schritt (do_classifier_free_guidance, latentsync/pipelines/lipsync_pipeline.py Zeile 355/429); guidance_scale
    = 1.0 schaltet das ab und ist dadurch der staerkste einzelne Hebel (~halbe Rechenzeit), kostet aber Ausdruck/
    Reaktion auf den Ton (Audio-Konditionierung wirkt nur noch ungewichtet).
  - ZOOM (Gesichtsfenster vor dem Hochskalieren auf LatentSync-Eingang): LatentSync selbst arbeitet immer auf
    512 px (configs/unet/stage2_512.yaml, einzige vorhandene Checkpoint-Aufloesung); ein kleineres Fenster spart
    darum kaum GPU-Zeit, macht das Eingangsbild aber unschaerfer (kleinerer Bildausschnitt auf denselben 512 px
    hochskaliert). Nur als "Auflösung"-Hebel in der Probe dabei, nicht als Zeithebel.
  - HD/HD_BATCH (Real-ESRGAN/GFPGAN) bleiben AUS wie im Standard (Produktion laeuft mit HD=False) - kein Hebel
    hier, sonst waere der Vergleich nicht auf denselben Pfad bezogen.
Nichts an video/freisteller_lipsync.py wird geaendert: alle vier Stufen patchen nur die Modulvariablen (STEPS,
GUIDANCE, ZOOM) fuer die Dauer ihres eigenen Laufs, wie tools/lipsync_steps_vergleich.py es tut. GPU ausschliesslich
ueber die zentrale Warteschlange (gpu_queue.slot in freisteller_lipsync._run_with_gpu, Sperre weltlage_lipsync -
dieselbe wie die laufende Produktion, darum reiht sich diese Probe zwischen deren Stuecken ein statt sie zu stoeren).

    .venv-lipsync\\Scripts\\python.exe tools\\lipsync_drossel_vergleich.py
"""
import json
import os
import re
import subprocess
import sys
import time
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from video import freisteller_lipsync as fl  # noqa: E402

WORK = ROOT / "data" / "lipsync_drossel_20261019"
REPORT = (Path.home() / r"projekte\jarvis\reports\lipsync_drossel_vergleich_20261019")
TASK = os.environ.get("JARVIS_TASK_ID", "20261019-120910-a2ea")
PROGRESS = (Path.home() / r"projekte\jarvis\tasks") / f"{TASK}.progress.md"
POSE = "stehend"
# Quelle: aktuelle Folge, 00:00-Lauf vom 19.10.2026 (zu dieser Zeit laengst fertig; der 10:00-Lauf rechnet parallel
# noch, dessen Dateien bleiben unberuehrt).
WAV_SRC = ROOT / "data" / "weltlage_20261019_0000" / "audio" / "s5_a1_ausgangslage.wav"
CLIP_LEN = 5.0

# (Name, Anzeige, Schritte, Guidance, Zoom-Fenster)
VARIANTEN = [
    ("stufe1_standard", "Stufe 1 - Standard (heute)", 8, 2.0, 768),
    ("stufe2_leicht", "Stufe 2 - leicht gedrosselt", 5, 1.5, 768),
    ("stufe3_mehr", "Stufe 3 - mehr gedrosselt", 4, 1.2, 512),
    ("stufe4_stark", "Stufe 4 - stark gedrosselt", 3, 1.0, 384),
]

_ff = fl.FFMPEG


def progress(text: str):
    print(text, flush=True)
    try:
        PROGRESS.write_text(text, encoding="utf-8")
    except OSError:
        pass


def test_clip() -> tuple[Path, float]:
    """5-s-Ausschnitt aus WAV_SRC, Start bei 10 s, Ende an der leisesten Stelle 14,6-15,4 s (kein Schnitt mitten
    im Wort) - derselbe Ansatz wie tools/lipsync_upscale_vergleich.test_wav()."""
    WORK.mkdir(parents=True, exist_ok=True)
    out = WORK / "testclip_5s.wav"
    with wave.open(str(WAV_SRC)) as w:
        sr, nch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
        w.readframes(int(10.0 * sr))  # erste 10 s ueberspringen
        a = np.frombuffer(w.readframes(int(6.0 * sr)), np.int16)
    hop = sr // fl.FPS * nch
    lo, hi = int(4.6 * fl.FPS), int(5.4 * fl.FPS)
    rms = [np.sqrt(np.mean(a[i * hop:(i + 1) * hop].astype(np.float32) ** 2) + 1e-9) for i in range(lo, hi)]
    n = lo + int(np.argmin(rms)) + 1
    with wave.open(str(out), "wb") as w:
        w.setnchannels(nch)
        w.setsampwidth(sw)
        w.setframerate(sr)
        w.writeframes(a[:n * hop].tobytes())
    length = n / fl.FPS
    progress(f"Testclip ({length:.2f} s) aus {WAV_SRC.name} (10-{10 + length:.1f} s) geschnitten.")
    return out, length


_LOG_RE = re.compile(r"\bin (\d+) s\b")   # erfasst alle drei Schritte: Zoom-Hochskalierung, LatentSync, GFPGAN-Nachzeichnung


def render(wav: Path, length: float) -> dict:
    res = {}
    for name, titel, steps, guidance, zoom in VARIANTEN:
        fl.STEPS, fl.GUIDANCE, fl.ZOOM = steps, guidance, zoom
        schritte_s = []
        def log(msg, _l=schritte_s):
            print(msg, flush=True)
            _l.extend(float(x) for x in _LOG_RE.findall(msg))
        work = WORK / name
        tag = f"drossel_{name}"
        progress(f"Lipsync-Drosselprobe: {titel} laeuft (Schritte {steps}, Guidance {guidance}, Fenster {zoom} px).")
        t0 = time.time()
        fs, n = fl.lipsync_freisteller(POSE, wav, 0.0, length, work, tag, log)
        wand_s = time.time() - t0
        fl.composite_studio(POSE, fs, n, work / f"{tag}_studio.mp4")
        rechen_s = sum(schritte_s) if schritte_s else wand_s   # reine GPU-Rechenzeit (Zoom+LatentSync+GFPGAN), ohne Warteschlangen-Wartezeit
        res[name] = dict(titel=titel, steps=steps, guidance=guidance, zoom=zoom,
                         rechenzeit_s=round(rechen_s, 1), wandzeit_s=round(wand_s, 1),
                         rechenzeit_pro_s_video=round(rechen_s / length, 2),
                         studio=str(work / f"{tag}_studio.mp4"))
        progress(f"{titel} fertig: {rechen_s:.0f} s Rechenzeit fuer {length:.1f} s Video "
                 f"({rechen_s / length:.1f} s/s).")
    return res


def _label(path: Path) -> str:
    return path.name.replace(":", "").replace("'", "")


def vergleichsvideo(res: dict, wav: Path, length: float, out: Path) -> Path:
    """Vier Stufen nacheinander, 960x540 (Groesse/unter 50 MB), Beschriftung oben eingebrannt, Originalton auf
    allen vier Abschnitten (gleicher Testclip, nur die Lipsync-Qualitaet unterscheidet sich)."""
    W, H = 960, 540
    labeled = []
    for name, titel, steps, guidance, zoom in VARIANTEN:
        info = res[name]
        text = (f"{titel}  Schritte {steps}, Guidance {guidance}, Fenster {zoom}px, "
                f"{info['rechenzeit_pro_s_video']:.0f} s Rechenzeit pro s Video").encode("ascii", "ignore").decode()
        src = Path(info["studio"])
        dst = WORK / f"label_{name}.mp4"
        font = r"C:\Windows\Fonts\arial.ttf".replace("\\", "/").replace(":", "\\:")
        fl.run([_ff, "-y", "-v", "error", "-i", str(src), "-vf",
                f"scale={W}:{H}:flags=lanczos,drawtext=fontfile='{font}':text='{text}':fontcolor=white:"
                f"fontsize=22:box=1:boxcolor=black@0.55:boxborderw=8:x=(w-text_w)/2:y=24", "-an", "-r", str(fl.FPS),
                "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-pix_fmt", "yuv420p", str(dst)])
        labeled.append(dst)
    ins = sum([["-i", str(p)] for p in labeled], []) + ["-stream_loop", "3", "-i", str(wav)]
    concat = "".join(f"[{i}:v]" for i in range(len(labeled))) + f"concat=n={len(labeled)}:v=1:a=0[v]"
    out.parent.mkdir(parents=True, exist_ok=True)
    fl.run([_ff, "-y", "-v", "error", *ins, "-filter_complex", concat, "-map", "[v]", "-map",
            f"{len(labeled)}:a", "-t", str(length * len(labeled)), "-c:v", "libx264", "-preset", "medium",
            "-crf", "23", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", str(out)])
    return out


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    REPORT.mkdir(parents=True, exist_ok=True)
    wav, length = test_clip()
    res = {"testclip": dict(quelle=str(WAV_SRC), start_s=10.0, laenge_s=length)}
    res["stufen"] = render(wav, length)
    out = vergleichsvideo(res["stufen"], wav, length, REPORT / "lipsync_drossel_vergleich.mp4")
    res["vergleichsvideo"] = str(out)
    res["vergleichsvideo_mb"] = round(out.stat().st_size / 1_000_000, 1)
    (REPORT / "ergebnis.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    progress(f"Lipsync-Drosselprobe fertig. Vergleichsvideo {res['vergleichsvideo_mb']} MB: {out}")
    print(json.dumps(res, indent=1, ensure_ascii=False))
    print("FERTIG", flush=True)


if __name__ == "__main__":
    main()
