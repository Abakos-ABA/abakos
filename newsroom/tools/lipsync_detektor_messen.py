"""Messung + Vergleichsclip zum Detektor-Test (Task 767c, 22.10.2026). Nach tools/lipsync_detektor_test.py.

.venv-lipsync\Scripts\python.exe tools\lipsync_detektor_messen.py <ordner> [detektoren,...]
Je Clip/Detektor: SyncNet LSE-C (conf) / LSE-D / Versatz, Flackern im Oberkopf (mittlere Bilddifferenz Stirn/Augen, Ausgabe
gegen Eingang: Differenz = vom Detektor/Ausrichtung eingefuehrtes Zittern), Mundschaerfe (Laplace-Varianz), Rechenzeit.
Schreibt <ordner>/messung.json + messung.md und <ordner>/vergleich.mp4 (Raster: Zeile = Clip, Spalte = Detektor).
"""
import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from video import freisteller_lipsync as fl  # noqa: E402
from video import lipsync_detektoren as D  # noqa: E402
import lipsync_messung as LM  # noqa: E402


def frames(p):
    cap = cv2.VideoCapture(str(p))
    out = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        out.append(f)
    return out


def main():
    d = Path(sys.argv[1]).resolve()
    dets = sys.argv[2].split(",") if len(sys.argv) > 2 else ["insightface", "mediapipe", "yunet"]
    lauf = json.loads((d / "lauf.json").read_text())
    res = {}
    mp = D.MediaPipeDetektor(False)
    for clip in ("sitz", "stehend"):
        inp = frames(d / f"{clip}_in.mp4")
        rgb0 = cv2.cvtColor(inp[0], cv2.COLOR_BGR2RGB)
        bb, _ = mp(rgb0)
        cx, cy, s = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2, 1.25 * (bb[2] - bb[0])      # wie lipsync_messung --faces
        box = (int(cx - s / 2), int(cy - s / 2 + 0.08 * s), int(s), int(s))
        top = (slice(int(box[1]), int(box[1] + box[3] * 0.4)), slice(box[0], box[0] + box[2]))
        low = (slice(int(box[1] + box[3] * 0.55), int(box[1] + box[3] * 0.9)), slice(box[0] + box[2] // 5, box[0] + box[2] * 4 // 5))
        for det in dets:
            v = d / f"{clip}_{det}.mp4"
            if not v.exists():
                continue
            m = LM.measure(str(v), str(d / f"{clip}_in.wav"), 0.0, None, box, None, 0.0)
            fr = frames(v)
            n = min(len(fr), len(inp))
            g = lambda f, r: cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)[r].astype(np.float32)
            flick = np.mean([np.abs(g(fr[i + 1], top) - g(fr[i], top)).mean() for i in range(n - 1)])
            flick_in = np.mean([np.abs(g(inp[i + 1], top) - g(inp[i], top)).mean() for i in range(n - 1)])
            sharp = np.mean([cv2.Laplacian(g(f, low), cv2.CV_32F).var() for f in fr[:n]])
            res[f"{clip}_{det}"] = dict(lse_c=m["conf"], lse_d=m["lse_d"], versatz_ms=m["offset_ms"],
                                        flackern_oben=round(float(flick), 3), flackern_oben_eingang=round(float(flick_in), 3),
                                        mundschaerfe=round(float(sharp), 1), **{k: lauf[f"{clip}_{det}"][k] for k in ("gesamt_s",)})
            print(clip, det, res[f"{clip}_{det}"], flush=True)
    (d / "messung.json").write_text(json.dumps(res, indent=1))
    names = {"insightface": "ALT InsightFace (nicht kommerziell)", "mediapipe": "MediaPipe (Apache 2.0)",
             "mediapipe_bild": "MediaPipe je Bild", "yunet": "YuNet (MIT)"}
    ins, filt, rows = [], [], []
    font = "C\:/Windows/Fonts/arial.ttf"
    i = 0
    for r, clip in enumerate(("sitz", "stehend")):
        for c, det in enumerate(dets):
            ins += ["-i", str(d / f"{clip}_{det}.mp4")]
            filt.append(f"[{i}:v]crop=iw:iw,scale=384:384,drawtext=fontfile='{font}':text='{clip} - {names.get(det, det)}':"
                        f"x=8:y=8:fontsize=16:fontcolor=white:box=1:boxcolor=black@0.6[v{i}]")
            i += 1
    cols = len(dets)
    layout = "|".join(f"{(k % cols) * 384}_{(k // cols) * 384}" for k in range(i))
    fc = ";".join(filt) + f";{''.join(f'[v{k}]' for k in range(i))}xstack=inputs={i}:layout={layout}[o]"
    out = d / "vergleich.mp4"
    subprocess.run([fl.FFMPEG, "-y", "-v", "error", *ins, "-i", str(d / "sitz_in.wav"), "-filter_complex", fc, "-map", "[o]",
                    "-map", f"{i}:a", "-t", "6", "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                    str(out)], check=True)
    print("Vergleichsclip", out)


main()
