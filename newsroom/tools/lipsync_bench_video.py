"""Vergleichsvideo Lipsync-Verfahren (Task c49b): Original | LatentSync Stufe 2 (heute) | LatentSync 3 Schritte | MuseTalk 1.5.
Segmente: Sitz Nahaufnahme, Stehend Nahaufnahme, Stehend Totale (Fenster in den Freisteller zurueck, verkleinert wie im Studio).
Aufruf (.venv-lipsync): lipsync_bench_video.py <lsbench-ordner> <out.mp4>"""
import subprocess, sys, os
from pathlib import Path
import cv2, numpy as np
W = Path(sys.argv[1]).resolve(); OUT = Path(sys.argv[2]).resolve()
_ff = next(iter(Path(os.environ["LOCALAPPDATA"]).glob("Microsoft/WinGet/Packages/Gyan.FFmpeg*/*/bin")), None)
FF = str(_ff / "ffmpeg.exe") if _ff else "ffmpeg"
LAB = ["Original (Quelle)", "LatentSync Stufe 2 (heute)", "LatentSync 3 Schritte (schneller)", "MuseTalk 1.5 (Echtzeit)"]
def frames(p, n):
    c = cv2.VideoCapture(str(p)); o = []
    while len(o) < n:
        ok, f = c.read()
        if not ok: break
        o.append(f)
    return o
def label(img, txt):
    cv2.rectangle(img, (0, 0), (img.shape[1], 34), (0, 0, 0), -1)
    cv2.putText(img, txt, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (255, 255, 255), 1, cv2.LINE_AA); return img
def seg(files, n, crop, size, title):
    fr = [frames(f, n) for f in files]; m = min(len(x) for x in fr)
    for i in range(m):
        tiles = []
        for k, x in enumerate(fr):
            im = crop(x[i], i, k); im = cv2.resize(im, size, interpolation=cv2.INTER_AREA); tiles.append(label(im.copy(), LAB[k]))
        row = np.hstack(tiles); bar = np.zeros((36, row.shape[1], 3), np.uint8); cv2.putText(bar, title, (8, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (80, 220, 255), 2, cv2.LINE_AA)
        yield np.vstack([bar, row])
def close(f, i, k): return f[150:590, 170:610]
sitz = [W / "sub0.mp4", W / "sub0_p.mp4", W / "sub0_s3g1.0.mp4", W / "sitz_musetalk_closed.mp4"]
steh = [W / "sub0.mp4", W / "sub0_p.mp4", W / "sub0_s3g1.0.mp4", W / "sitz_musetalk_closed.mp4"]
# Totale: Fenster (294,12,230) im Freisteller 832x1248 ersetzen (untere Gesichtshaelfte, weiche Ellipse), auf Studiogroesse verkleinern
fa = np.load(W / "sitz_faces.npy"); grey = frames(W / "sitz_grau25.mp4", 125)
X, Y, S = 170, 76, 532
def totale_tiles():
    wins = [frames(f, 125) for f in steh]; m = min(len(w) for w in wins + [grey])
    for i in range(m):
        cx, cy, sz = fa[i]; tiles = []
        for k, w in enumerate(wins):
            im = grey[i].copy()
            if k:
                win = cv2.resize(w[i], (S, S), interpolation=cv2.INTER_AREA)
                yy, xx = np.mgrid[Y:Y + S, X:X + S].astype(np.float32)
                d = np.sqrt(((xx - cx) / (sz * 0.46)) ** 2 + ((yy - (cy + sz * 0.36)) / (sz * 0.40)) ** 2)
                mk = np.clip((1.15 - d) / 0.35, 0, 1); mk = (mk * mk * (3 - 2 * mk))[..., None]
                im[Y:Y + S, X:X + S] = (im[Y:Y + S, X:X + S] * (1 - mk) + win * mk).astype(np.uint8)
            im = im[0:900, 100:850]; im = cv2.resize(im, (int(750 * 0.25 * 2), int(900 * 0.25 * 2)), interpolation=cv2.INTER_AREA)   # Studio-Massstab 0,25 (Sitz), Anzeige x2
            tiles.append(label(im, LAB[k]))
        row = np.hstack(tiles); bar = np.zeros((36, row.shape[1], 3), np.uint8)
        cv2.putText(bar, "Sitzend Totale (Gesicht ~60 px wie im Studiobild, x2 vergroessert)", (8, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (80, 220, 255), 2, cv2.LINE_AA)
        yield np.vstack([bar, row])
gens = [seg(sitz, 125, close, (400, 400), "Sitzend Nahaufnahme (Gesichtsfenster)"), totale_tiles()]
first = next(gens[0]); H, Wd = first.shape[:2]
p = subprocess.Popen([FF, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{Wd}x{H}", "-r", "25", "-i", "-", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", str(OUT) + ".stumm.mp4"], stdin=subprocess.PIPE)
def put(f):
    if f.shape[:2] != (H, Wd):
        c = np.zeros((H, Wd, 3), np.uint8); h2, w2 = min(H, f.shape[0]), min(Wd, f.shape[1]); c[:h2, :w2] = f[:h2, :w2]; f = c
    p.stdin.write(f.tobytes())
put(first)
for g in gens:
    for f in g: put(f)
p.stdin.close(); p.wait()
lst = W / "audio_liste.txt"; lst.write_text("".join(f"file '{(W / n).as_posix()}'\n" for n in ["sub0.wav", "sub0.wav"]))
subprocess.run([FF, "-v", "error", "-y", "-i", str(OUT) + ".stumm.mp4", "-f", "concat", "-safe", "0", "-i", str(lst), "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-shortest", str(OUT)], check=True)
os.remove(str(OUT) + ".stumm.mp4"); print("fertig", OUT)
