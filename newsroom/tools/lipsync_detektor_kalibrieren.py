"""Kalibrierung + Stabilitaetsmessung der freien Gesichtsdetektoren gegen InsightFace (22.10.2026).

Aufruf mit .venv-lipsync:  python tools/lipsync_detektor_kalibrieren.py <ordner mit *_zoom.mp4> [--schreiben]
Liest je Clip alle Bilder (RGB wie LatentSync), laesst InsightFace (nur als Messlatte, CPU) und die freien Detektoren
laufen, vergleicht die drei Ankerpunkte (Braue links/rechts, Nasenmitte) und misst:
  - Trefferquote, Zeit pro Bild
  - Versatz zu InsightFace (Median im Gesichtsraster, in Einheiten Brauenabstand) -> mit --schreiben nach kalib.json
  - Zittern: Standardabweichung der zweiten Differenz der Anker (Pixel im 512er-Raster) = hochfrequentes Rauschen
"""
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vendor" / "LatentSync"))
from video import lipsync_detektoren as D  # noqa: E402


def frames(p, n=None):
    cap = cv2.VideoCapture(str(p))
    out = []
    while True:
        ok, f = cap.read()
        if not ok or (n and len(out) >= n):
            break
        out.append(cv2.cvtColor(f, cv2.COLOR_BGR2RGB))
    return out


def anker(lmk):
    return np.stack([lmk[D.BROW_L].mean(0), lmk[D.BROW_R].mean(0), lmk[D.NOSE].mean(0)])


def lauf(det, fr):
    res, t = [], time.time()
    for f in fr:
        b, l = det(f)
        res.append(None if b is None else anker(l))
    return res, (time.time() - t) / len(fr)


def zittern(a):
    """a: Liste 3x2 oder None -> std der 2. Differenz, normiert auf 512er-Raster (Brauenabstand = ~190 px im Raster)."""
    ok = [x for x in a if x is not None]
    if len(ok) < 5:
        return float("nan")
    arr = np.stack(ok)
    scale = 190.0 / np.median(np.linalg.norm(arr[:, 1] - arr[:, 0], axis=1))
    d2 = (arr[2:] - 2 * arr[1:-1] + arr[:-2]) * scale
    return float(np.sqrt((d2 ** 2).sum(-1).mean()))


def main():
    d = Path(sys.argv[1])
    schreiben = "--schreiben" in sys.argv
    from insightface.app import FaceAnalysis
    app = FaceAnalysis(allowed_modules=["detection", "landmark_2d_106"], root=str(ROOT / "vendor/LatentSync/checkpoints/auxiliary"),
                       providers=["CPUExecutionProvider"])
    app.prepare(ctx_id=-1, det_size=(512, 512))

    class IF:
        def __call__(self, f):
            fs = app.get(f)
            if not fs:
                return None, None
            x = max(fs, key=lambda x: (x.bbox[2] - x.bbox[0]) * (x.bbox[3] - x.bbox[1]))
            return [0, 0, 1, 1], np.round(x.landmark_2d_106)
    dets = {"insightface": IF(), "mediapipe": D.MediaPipeDetektor(True), "mediapipe_bild": D.MediaPipeDetektor(False),
            "yunet": D.YuNetDetektor()}
    clips = sorted(d.glob("*_zoom.mp4"))
    alle = {}
    for c in clips:
        fr = frames(c, 150)
        alle[c.stem] = {n: lauf(dt, fr) for n, dt in dets.items()}
        print(c.stem, len(fr), "Bilder")
    # Rohversatz bestimmen: ohne Korrektur messen
    for name in ("mediapipe", "mediapipe_bild", "yunet"):
        dets[name].off = np.zeros((3, 2))
    roh = {}
    for c in clips:
        fr = frames(c, 150)
        roh[c.stem] = {n: lauf(dets[n], fr)[0] for n in ("mediapipe", "mediapipe_bild", "yunet")}
    kalib = {}
    for name in ("mediapipe", "mediapipe_bild", "yunet"):
        res = []
        for c in clips:
            ref = alle[c.stem]["insightface"][0]
            for r, i in zip(roh[c.stem][name], ref):
                if r is None or i is None:
                    continue
                dd = r[1] - r[0]
                n = np.linalg.norm(dd)
                u = dd / n
                v = np.array([-u[1], u[0]])
                diff = (i - r) / n
                res.append(np.stack([diff @ u, diff @ v], 1))
        kalib[name] = np.median(np.stack(res), 0).round(4).tolist()
    print("Kalibrierung", json.dumps(kalib))
    if schreiben:
        D.KALIB.write_text(json.dumps(kalib, indent=1))
        for n in kalib:
            dets[n].off = np.array(kalib[n])
    print("\nclip / detektor: Trefferquote, ms/Bild, Zittern(px@512), Abweichung zu InsightFace (px@512)")
    for c in clips:
        fr = frames(c, 150)
        ref = alle[c.stem]["insightface"][0]
        for n, dt in dets.items():
            a, t = lauf(dt, fr) if n != "insightface" else alle[c.stem][n]
            hit = sum(x is not None for x in a) / len(a)
            dev = []
            for x, i in zip(a, ref):
                if x is None or i is None:
                    continue
                s = 190.0 / np.linalg.norm(i[1] - i[0])
                dev.append(np.linalg.norm((x - i) * s, axis=1).mean())
            print(f"{c.stem:14s} {n:15s} hit {hit:5.1%}  {t * 1000:6.1f} ms  zittern {zittern(a):5.2f}  abw {np.mean(dev) if dev else float('nan'):5.2f}")


main()
