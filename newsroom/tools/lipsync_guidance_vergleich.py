"""Lipsync-Vergleich: alte Mundbewegungs-Staerke (guidance 2,5, Task 1fa2 29.09.) gegen die neue, gesenkte
(config.settings.NEWS_WELTLAGE_LIPSYNC_GUIDANCE, Standard 2,0, Task 20261001-202910-0180).

Marlons Rueckmeldung 01.10. abends zum Testclip aus Task 98b7: Lipsync wirkt uebertrieben, Mundbewegungen zu stark.
Dieser Vergleich zeigt mit demselben Satz (Chatterbox Profil C, ein LatentSync-Stueck), stehend im Studio, HD-Pfad
(Real-ESRGAN/GFPGAN) in beiden Varianten unveraendert: alt = guidance 2,5, neu = die aktuell aktive Einstellung.
Clip 1920x1080: Studio alt | Studio neu untereinander, dazu Nahaufnahme Mund alt|neu nebeneinander. Mund-Bewegungs-
Kennzahl (mittlere Bild-zu-Bild-Aenderung im Mundbereich) fuer beide Varianten.
GPU: ein Platz in der GPU-Warteschlange (Prio 3), derselbe Name wie video/freisteller_lipsync.

    .venv-lipsync\\Scripts\\python.exe tools\\lipsync_guidance_vergleich.py
"""
import json
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from video import freisteller_lipsync as fl  # noqa: E402
from lipsync_upscale_vergleich import test_wav, mouth_motion, _reader, label  # noqa: E402
from config.settings import NEWS_WELTLAGE_LIPSYNC_GUIDANCE  # noqa: E402

WORK = ROOT / "data" / "lipsync_guidance_20261001"
REPORT = Path(r"C:\Users\Marlon\projekte\jarvis\reports\lipsync_guidance_vergleich_20261001")
PROGRESS = Path(r"C:\Users\Marlon\projekte\jarvis\tasks\20261001-202910-0180.progress.md")
POSE = "stehend"
VARIANTEN = [("alt_2_5", 2.5, "ALT  (guidance 2,5)"), ("neu", NEWS_WELTLAGE_LIPSYNC_GUIDANCE,
             f"NEU  (guidance {NEWS_WELTLAGE_LIPSYNC_GUIDANCE:g}, aktueller Standard)")]


def progress(text: str):
    print(text, flush=True)
    try:
        PROGRESS.write_text(text, encoding="utf-8")
    except OSError:
        pass


def render(wav: Path, length: float) -> dict:
    res = {}
    for var, guidance, _ in VARIANTEN:
        fl.GUIDANCE = guidance
        work = WORK / var
        name = f"vgl_{var}"
        progress(f"Lipsync-Vergleich: Variante {var} (guidance {guidance:g}) laeuft, {length:.0f} Sekunden.")
        t = time.time()
        fs, n = fl.lipsync_freisteller(POSE, wav, 0.0, length, work, name)
        dt = time.time() - t
        fl.composite_studio(POSE, fs, n, work / f"{name}_studio.mp4")
        faces = np.load(work / f"{name}_faces.npy")
        res[var] = dict(guidance=guidance, freisteller=str(fs), sekunden_lipsync=round(dt), bilder=n,
                        mund_bewegung=round(mouth_motion(fs, faces, n), 2))
        progress(f"Variante {var} fertig: Mund-Bewegungs-Kennzahl {res[var]['mund_bewegung']}.")
    return res


def clip(wav: Path, length: float) -> Path:
    n = int(round(length * fl.FPS))
    W, H = fl.OUT_W, fl.OUT_H
    P = fl.POSEN[POSE]
    tmp = WORK / "vergleich_video.mp4"
    ff = subprocess.Popen([fl.FFMPEG, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                           "-r", str(fl.FPS), "-i", "-", "-c:v", "libx264", "-crf", "16", "-preset", "slow",
                           "-pix_fmt", "yuv420p", str(tmp)], stdin=subprocess.PIPE)
    # Studio-Ansicht je Variante, untereinander im selben 1920x1080-Bild (oben/unten je halbe Hoehe)
    half = H // 2
    labs = [label(TITEL, W, 48, 30) for _, _, TITEL in VARIANTEN]
    readers = [_reader(WORK / var / f"vgl_{var}_studio.mp4", W, H) for var, _, _ in VARIANTEN]
    for _ in range(n):
        c = np.zeros((H, W, 3), np.uint8)
        for j, r in enumerate(readers):
            fr = next(r, None)
            if fr is None:
                continue
            top = j * half
            c[top:top + half] = cv2.resize(fr, (W, half), interpolation=cv2.INTER_AREA)
            c[top:top + 48] = labs[j]
        ff.stdin.write(c.tobytes())
    # Nahaufnahme aus den Freistellern (volle Quellaufloesung): alt links, neu rechts
    faces = np.load(WORK / VARIANTEN[0][0] / f"vgl_{VARIANTEN[0][0]}_faces.npy")
    cx, cy, sz = np.median(faces, 0)
    s = int(sz * 1.6)
    x0, y0 = int(cx - s / 2), int(cy - s / 2 + sz * 0.15)
    labs2 = [label(t, 900, 64, 30) for _, _, t in VARIANTEN]
    rd = [_reader(WORK / var / f"vgl_{var}_freisteller_lipsync_prores4444.mov", P["w"], P["h"], "rgba")
          for var, _, _ in VARIANTEN]
    head = label("Nahaufnahme Mund (Freisteller, vor dem Einsetzen)", W, 70, 34)
    for _ in range(n):
        c = np.full((H, W, 3), 18, np.uint8)
        c[:70] = head
        for j, r in enumerate(rd):
            fr = next(r, None)
            if fr is None:
                continue
            a = fr[..., 3:4].astype(np.float32) / 255
            rgb = (fr[..., :3] * a + 40 * (1 - a)).astype(np.uint8)
            x = 40 + j * 940
            c[100:164, x:x + 900] = labs2[j]
            c[170:170 + 900, x:x + 900] = cv2.resize(rgb[y0:y0 + s, x0:x0 + s], (900, 900),
                                                     interpolation=cv2.INTER_LANCZOS4)
        ff.stdin.write(c.tobytes())
    ff.stdin.close()
    if ff.wait():
        raise RuntimeError("Vergleichsclip schreiben fehlgeschlagen")
    REPORT.mkdir(parents=True, exist_ok=True)
    out = REPORT / "lipsync_vergleich_guidance_alt_neu_20261001.mp4"
    k = len(VARIANTEN) + 1
    ins = sum([["-i", str(wav)] for _ in range(k)], [])
    pads = ";".join(f"[{i + 1}:a]apad=whole_dur={length:.3f},atrim=0:{length:.3f}[a{i}]" for i in range(k))
    fl.run([fl.FFMPEG, "-y", "-v", "error", "-i", tmp, *ins, "-filter_complex",
            pads + ";" + "".join(f"[a{i}]" for i in range(k)) + f"concat=n={k}:v=0:a=1,aresample=48000,"
            "pan=stereo|c0=c0|c1=c0[a]", "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "256k",
            "-shortest", "-movflags", "+faststart", out])
    return out


def main():
    import gpu_budget
    WORK.mkdir(parents=True, exist_ok=True)
    wav, length = test_wav()
    t = time.time()
    progress("Lipsync-Vergleich (Mundbewegung alt/neu): warte in der GPU-Warteschlange.")
    gpu_budget.hold("lipsync", name=f"lipsync freisteller ({Path(sys.argv[0]).stem})", prio=3, vram_mb=14000,
                    progress=lambda w, m: progress(f"Warte seit {m:.0f} Minuten in der GPU-Warteschlange: {w}"))
    res = {"testton": dict(datei=str(wav), sekunden=length), "gpu_wartezeit_s": round(time.time() - t)}
    res["varianten"] = render(wav, length)
    progress("Beide Varianten gerechnet, baue den Vergleichsclip.")
    res["clip"] = str(clip(wav, length))
    REPORT.mkdir(parents=True, exist_ok=True)
    (REPORT / "ergebnis.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    progress("Lipsync-Vergleich fertig.")
    print(json.dumps(res, indent=1, ensure_ascii=False))
    print("FERTIG", flush=True)


if __name__ == "__main__":
    main()
