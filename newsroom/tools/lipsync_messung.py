"""Lipsync messen (SyncNet aus vendor/LatentSync/eval, CPU, keine GPU-Warteschlange noetig).

Liefert pro Clip den Bild-Ton-Versatz (in Bildern bei 25 fps und in ms) und die SyncNet-Sicherheit (conf; hoeher = Mund
passt besser zum Ton, LatentSync-Demos liegen bei ~8-9, gutes echtes Video bei ~7-9, unter ~4 sieht man es deutlich).

Gesicht wird nicht gesucht, sondern als fester Ausschnitt angegeben (Moderatorin steht/sitzt an bekannter Stelle):
    .venv-lipsync\\Scripts\\python.exe tools\\lipsync_messung.py <video> [--audio ton.wav] [--ss s] [--t s]
        --box x,y,w,h            fester Gesichtsausschnitt im Video (Pixel)
        --faces faces.npy        oder Gesichtsspur aus video/freisteller_lipsync (cx, cy, size pro 25-fps-Bild)
        --shift ms               Ton kuenstlich verschieben (Eichung: +ms = Ton spaeter)
Vorzeichen: offset_ms > 0 heisst: der Mund kommt NACH dem Ton (Bild hinkt hinterher).
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT / "vendor" / "LatentSync"
_ff = next(iter(Path(os.environ["LOCALAPPDATA"]).glob("Microsoft/WinGet/Packages/Gyan.FFmpeg*/*/bin")), None)
FFMPEG = str(_ff / "ffmpeg.exe") if _ff else "ffmpeg"


def measure(video, audio=None, ss=0.0, t=None, box=None, faces=None, shift_ms=0.0, vshift=15):
    import cv2
    import torch
    sys.path.insert(0, str(REPO))
    from scipy.io import wavfile
    import python_speech_features
    from eval.syncnet import SyncNetEval

    tmp = Path(tempfile.mkdtemp(prefix="lipmess_", dir=str(ROOT / "state")))
    cut = ["-ss", f"{ss:.3f}"] + (["-t", f"{t:.3f}"] if t else [])
    # Bild: 25 fps, Gesichtsausschnitt 224x224
    p = subprocess.run([FFMPEG, "-v", "error", *cut, "-i", str(video), "-vf", "fps=25", "-f", "rawvideo",
                        "-pix_fmt", "bgr24", "-"], capture_output=True)
    probe = subprocess.run([FFMPEG, "-hide_banner", "-i", str(video)], capture_output=True, text=True).stderr
    import re
    m = re.search(r", (\d{2,5})x(\d{2,5})", probe)
    W, H = int(m.group(1)), int(m.group(2))
    raw = np.frombuffer(p.stdout, np.uint8)
    n = len(raw) // (W * H * 3)
    frames = raw[: n * W * H * 3].reshape(n, H, W, 3)
    crops = []
    f0 = int(round(ss * 25))
    for i, fr in enumerate(frames):
        if faces is not None:
            cx, cy, s = faces[min(f0 + i, len(faces) - 1)]
            s = s * 1.25
            x, y, w, h = int(cx - s / 2), int(cy - s / 2 + 0.08 * s), int(s), int(s)
        else:
            x, y, w, h = box
        x, y = max(0, x), max(0, y)
        crops.append(cv2.resize(np.ascontiguousarray(fr[y:y + h, x:x + w]), (224, 224), interpolation=cv2.INTER_CUBIC))
    # Ton 16 kHz mono
    wav = tmp / "a.wav"
    src = audio or video
    acut = ["-ss", f"{ss:.3f}"] + (["-t", f"{t:.3f}"] if t else [])
    af = f"adelay={int(shift_ms)}" if shift_ms > 0 else (f"atrim=start={-shift_ms / 1000:.3f}" if shift_ms < 0 else "anull")
    subprocess.run([FFMPEG, "-v", "error", "-y", *acut, "-i", str(src), "-vn", "-ac", "1", "-ar", "16000", "-af", af,
                    "-acodec", "pcm_s16le", str(wav)], check=True)
    sr, a = wavfile.read(str(wav))
    mfcc = np.stack([np.array(i) for i in zip(*python_speech_features.mfcc(a, sr))])
    cct = torch.from_numpy(mfcc[None, None].astype(float)).float()
    im = np.stack(crops, 3)[None].transpose(0, 3, 4, 1, 2)
    imtv = torch.from_numpy(im.astype(float)).float()

    net = SyncNetEval(device="cpu")
    net.loadParameters(str(ROOT / "models" / "latentsync_eval" / "auxiliary" / "syncnet_v2.model"))
    net.__S__.eval()
    L = min(len(crops), len(a) // 640) - 5
    imf, ccf = [], []
    with torch.no_grad():
        for i in range(0, L, 20):
            j = range(i, min(L, i + 20))
            imf.append(net.__S__.forward_lip(torch.cat([imtv[:, :, v:v + 5] for v in j], 0)))
            ccf.append(net.__S__.forward_aud(torch.cat([cct[:, :, :, v * 4:v * 4 + 20] for v in j], 0)))
    imf, ccf = torch.cat(imf), torch.cat(ccf)
    # wie syncnet_python calc_pdist: fuer jedes Bild Abstand zu Ton -vshift..+vshift
    pad = torch.nn.functional.pad(ccf, (0, 0, vshift, vshift))
    d = torch.stack([torch.nn.functional.pairwise_distance(imf[i:i + 1].repeat(2 * vshift + 1, 1), pad[i:i + 2 * vshift + 1])
                     for i in range(len(imf))])            # (frames, shifts)
    md = d.mean(0)
    k = int(torch.argmin(md))
    offset = vshift - k
    conf = float(torch.median(md) - md[k])
    # lokale Sicherheit je 2-s-Fenster bei optimalem Versatz (zeigt flaue Stellen)
    fd = d[:, k].numpy()
    fconf = (torch.median(d, 1).values - d[:, k]).numpy()
    win = [round(float(fconf[i:i + 50].mean()), 2) for i in range(0, len(fconf), 50)]
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    # syncnet: offset>0 -> Ton muesste spaeter kommen, d.h. Bild hinkt hinterher? Eichung ueber --shift
    return {"offset_frames": offset, "offset_ms": offset * 40, "conf": round(conf, 2), "lse_d": round(float(md[k]), 2), "conf_2s": win, "frames": len(crops)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--audio")
    ap.add_argument("--ss", type=float, default=0.0)
    ap.add_argument("--t", type=float)
    ap.add_argument("--box")
    ap.add_argument("--faces")
    ap.add_argument("--shift", type=float, default=0.0)
    a = ap.parse_args()
    box = tuple(int(v) for v in a.box.split(",")) if a.box else None
    faces = np.load(a.faces) if a.faces else None
    print(json.dumps(measure(a.video, a.audio, a.ss, a.t, box, faces, a.shift)))
