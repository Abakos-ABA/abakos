"""Lipsync-Vergleich alt gegen neu, Studio und Bruessel (Tasks 20261001-161926-e447 / 20261001-184254-d71b).

Marlons Rueckmeldung 01.10. 18:42 zum Probeclip Studio + Bruessel: in Bruessel ist Latara viel zu klein, der Mund
bewegt sich schlecht. Dieser Vergleich zeigt mit demselben Satz (Chatterbox Profil C, ~7 s = ein LatentSync-Stueck):
  alt  = bisheriger Lipsync (Gesichtsfenster mit Lanczos auf 768 px) + alte Bruessel-Platzierung (316 px hoch)
  neu  = Lipsync mit KI-hochskaliertem Gesicht (video/gesicht_hd.py: Real-ESRGAN + GFPGAN rein, GFPGAN auf den Mund
         raus) + neue Platzierung (Latara so gross wie im Studio, 754 px, config/brand/orte/platzierung.json)
Clip 1920x1080: Studio alt, Studio neu, Bruessel alt, Bruessel neu (je mit Mund-Lupe oben rechts), dann
Nahaufnahme alt|neu nebeneinander. Dazu die hochskalierten Standbilder (sitzend, stehend, x2/x4) und Messwerte.
GPU: ein Platz in der GPU-Warteschlange (Prio 3) bis Prozessende, derselbe Name wie video/freisteller_lipsync.

    .venv-lipsync\\Scripts\\python.exe tools\\lipsync_upscale_vergleich.py [stills|videos|clip|alles]
"""
import json
import os
import subprocess
import sys
import time
import wave
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from video import freisteller_lipsync as fl  # noqa: E402
from video import gesicht_hd  # noqa: E402
from video import orte as om  # noqa: E402

WK = Path(r"C:\Users\Marlon\Documents\WK")
STILLS = {"sitz": WK / "latara_front_sitzend.png", "stehend": WK / "latara_front_stehend.png"}
WORK = ROOT / "data" / "lipsync_upscale_20261001"
REPORT = Path(r"C:\Users\Marlon\projekte\jarvis\reports\lipsync_upscale_20261001")
TASK = os.environ.get("JARVIS_TASK_ID", "20261001-184254-d71b")
PROGRESS = Path(r"C:\Users\Marlon\projekte\jarvis\tasks") / f"{TASK}.progress.md"
WAV_SRC = ROOT / "data" / "weltlage_20260930d" / "audio" / "s5_m1_flydubai.wav"   # Chatterbox Profil C
POSE = "stehend"
BRUESSEL_ALT = dict(x=844, y=620, scale=0.2534)      # Platzierung bis 01.10. abends (geschaetzt, 316 px hoch)
TITEL = {"alt": "ALT  (bisher)", "neu": "NEU  (Gesicht KI-hochskaliert)"}


def progress(text: str):
    print(text, flush=True)
    try:
        PROGRESS.write_text(text, encoding="utf-8")
    except OSError:
        pass


def test_wav() -> tuple[Path, float]:
    """Erste ~7 s der Flydubai-Meldung, Schnitt an der leisesten Stelle 6,3-7,2 s (ein LatentSync-Stueck)."""
    out = WORK / "testton_7s.wav"
    with wave.open(str(WAV_SRC)) as w:
        sr, nch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
        a = np.frombuffer(w.readframes(w.getnframes()), np.int16)
    hop = sr // fl.FPS * nch
    lo, hi = int(6.3 * fl.FPS), int(7.2 * fl.FPS)
    rms = [np.sqrt(np.mean(a[i * hop:(i + 1) * hop].astype(np.float32) ** 2)) for i in range(lo, hi)]
    n = lo + int(np.argmin(rms)) + 1
    WORK.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(nch)
        w.setsampwidth(sw)
        w.setframerate(sr)
        w.writeframes(a[:n * hop].tobytes())
    return out, n / fl.FPS


# ---------------------------------------------------------------- 1) Standbilder
def stills() -> dict:
    res = {}
    REPORT.mkdir(parents=True, exist_ok=True)
    for pose, src in STILLS.items():
        t = time.time()
        info = gesicht_hd.still(src, WORK / "stills")
        info["sekunden"] = round(time.time() - t, 1)
        # Gesichtsausschnitt zum Ansehen: Original (Lanczos x4) | Real-ESRGAN x4 + GFPGAN
        im = cv2.imread(str(src), cv2.IMREAD_UNCHANGED)
        hd = cv2.imread(info["x4"]["datei"], cv2.IMREAD_UNCHANGED)
        rgb = np.ascontiguousarray(im[..., :3])
        k = gesicht_hd.kps_of(np.ascontiguousarray(rgb[..., ::-1]))
        if k is not None:
            c, r = k.mean(0) * 4, int(np.linalg.norm(k[1] - k[0]) * 4 * 1.6)
            y0, x0 = max(0, int(c[1] - r)), max(0, int(c[0] - r))
            lz = cv2.resize(rgb, (rgb.shape[1] * 4, rgb.shape[0] * 4), interpolation=cv2.INTER_LANCZOS4)
            pair = [cv2.resize(x[y0:y0 + 2 * r, x0:x0 + 2 * r, :3], (640, 640), interpolation=cv2.INTER_AREA)
                    for x in (lz, hd)]
            cv2.imwrite(str(REPORT / f"standbild_{pose}_gesicht_alt_links_hochskaliert_rechts.png"),
                        np.concatenate(pair, 1))
        res[pose] = info
        progress(f"Standbild {pose} hochskaliert, zweifach und vierfach mit Gesichts-Restaurierung.")
    return res


# ---------------------------------------------------------------- 2) Lipsync + Compositing
def mouth_sharpness(mov: Path, faces: np.ndarray, n: int) -> float:
    """Mittlere Laplace-Varianz im Mundbereich des Freistellers (hoeher = schaerfer gezeichnet)."""
    P = fl.POSEN[POSE]
    W, H = P["w"], P["h"]
    vals = []
    p = subprocess.Popen([fl.FFMPEG, "-v", "error", "-i", str(mov), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         stdout=subprocess.PIPE)
    for i in range(n):
        b = p.stdout.read(W * H * 3)
        if len(b) < W * H * 3:
            break
        fr = np.frombuffer(b, np.uint8).reshape(H, W, 3)
        cx, cy, sz = faces[i]
        g = cv2.cvtColor(fr[int(cy + sz * 0.2):int(cy + sz * 0.5), int(cx - sz * 0.3):int(cx + sz * 0.3)],
                         cv2.COLOR_RGB2GRAY)
        vals.append(cv2.Laplacian(g, cv2.CV_64F).var())
    p.stdout.close()
    p.wait()
    return float(np.mean(vals)) if vals else 0.0


def mouth_motion(mov: Path, faces: np.ndarray, n: int) -> float:
    """Mittlere Bild-zu-Bild-Aenderung im Mundbereich (Grauwerte) = wie stark sich der Mund bewegt."""
    P = fl.POSEN[POSE]
    W, H = P["w"], P["h"]
    prev, vals = None, []
    p = subprocess.Popen([fl.FFMPEG, "-v", "error", "-i", str(mov), "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                         stdout=subprocess.PIPE)
    cx, cy, sz = np.median(faces, 0)
    for i in range(n):
        b = p.stdout.read(W * H)
        if len(b) < W * H:
            break
        g = np.frombuffer(b, np.uint8).reshape(H, W)[int(cy + sz * 0.2):int(cy + sz * 0.55),
                                                     int(cx - sz * 0.3):int(cx + sz * 0.3)].astype(np.float32)
        if prev is not None:
            vals.append(float(np.abs(g - prev).mean()))
        prev = g
    p.stdout.close()
    p.wait()
    return float(np.mean(vals)) if vals else 0.0


def syncnet(mov: Path, wav: Path, faces: Path) -> dict:
    r = subprocess.run([str(fl.LS_PY), str(ROOT / "tools" / "lipsync_messung.py"), str(mov), "--audio", str(wav),
                        "--faces", str(faces)], capture_output=True, text=True, cwd=str(ROOT))
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        return {"fehler": (r.stderr or r.stdout)[-300:]}


def composite_ort(fs: Path, n: int, out: Path, p: dict) -> Path:
    """Wie video/orte.composite, aber mit vorgegebener Platzierung (fuer die alte Bruessel-Groesse)."""
    av, o = om.avatar("latara"), om.ort("bruessel")
    p = dict(p, schatten=om.schatten_standard(o))
    kont = om.kontakt_png(av, o, p, out.with_name(out.stem + "_kontakt.png"))
    fl.run([om.FFMPEG, "-y", "-v", "error", "-loop", "1", "-i", str(o["bild_pfad"]), "-i", str(fs), "-loop", "1",
            "-i", str(kont), "-filter_complex", om.video_filter(av, o, p), "-map", "[outv]", "-frames:v", str(n),
            "-r", str(om.FPS), "-c:v", "libx264", "-crf", "15", "-pix_fmt", "yuv420p", str(out)])
    return out


def videos(wav: Path, length: float) -> dict:
    res = {}
    for var in ("alt", "neu"):
        fl.HD = var == "neu"
        work = WORK / var
        name = f"vgl_{var}"
        progress(f"Lipsync Variante {var} laeuft (stehend, {length:.0f} Sekunden).")
        t = time.time()
        fs, n = fl.lipsync_freisteller(POSE, wav, 0.0, length, work, name)
        dt = time.time() - t
        progress(f"Lipsync {var} fertig, setze ins Studio und nach Bruessel.")
        fl.composite_studio(POSE, fs, n, work / f"{name}_studio.mp4")
        if var == "alt":
            composite_ort(fs, n, work / f"{name}_bruessel.mp4", BRUESSEL_ALT)
        else:
            fl.composite_studio(POSE, fs, n, work / f"{name}_bruessel.mp4", ort="bruessel")
        faces = np.load(work / f"{name}_faces.npy")
        res[var] = dict(freisteller=str(fs), sekunden_lipsync=round(dt), bilder=n,
                        gesicht_px=round(float(faces[0, 2])),
                        fenster=json.loads((work / f"{name}_fenster.json").read_text())["windows"],
                        mund_schaerfe=round(mouth_sharpness(fs, faces, n), 1),
                        mund_bewegung=round(mouth_motion(fs, faces, n), 2))
        print(json.dumps(res[var]), flush=True)
    fl.HD = False
    progress("Beide Lipsync-Varianten fertig, messe die Lippensynchronitaet auf der CPU.")
    for var in ("alt", "neu"):
        w = WORK / var
        res[var]["syncnet"] = syncnet(w / f"vgl_{var}_freisteller_lipsync_prores4444.mov", wav, w / f"vgl_{var}_faces.npy")
        print(var, res[var]["syncnet"], flush=True)
    return res


# ---------------------------------------------------------------- 3) Vergleichsclip
def label(text: str, w: int, h: int, size: int = 34) -> np.ndarray:
    from PIL import Image, ImageDraw, ImageFont
    im = Image.new("RGB", (w, h), (18, 18, 22))
    dr = ImageDraw.Draw(im)
    f = ImageFont.truetype(r"C:\Windows\Fonts\arialbd.ttf", size)
    dr.text((18, (h - size) / 2 - 3), text, font=f, fill=(255, 255, 255))
    return np.asarray(im)


def face_box_out(ort: str | None, var: str, faces: np.ndarray) -> tuple[float, float, float]:
    """Gesichtsmitte/-groesse im 1920x1080-Endbild."""
    P = fl.POSEN[POSE]
    if ort is None:
        from video import composite_fx as fx
        mx, my, mw, mh = fx.placement_box(fl.load_placement(POSE), (P["w"], P["h"]), fl.OUT_W, fl.OUT_H, P["bg_size"])
    else:
        av, o = om.avatar("latara"), om.ort(ort)
        p = dict(BRUESSEL_ALT) if var == "alt" else om.platzierung("latara", ort)
        p.setdefault("schatten", om.schatten_standard(o))
        g = om.ausgabe(av, o, p)
        mx, my, mw, mh = g["x"], g["y"], g["w"], g["h"]
    cx, cy, sz = np.median(faces, 0)
    return mx + cx * mw / P["w"], my + cy * mh / P["h"], sz * mw / P["w"]


def _reader(path: Path, w: int, h: int, fmt: str = "rgb24"):
    p = subprocess.Popen([fl.FFMPEG, "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", fmt, "-"],
                         stdout=subprocess.PIPE)
    ch = 4 if fmt == "rgba" else 3
    try:
        while True:
            b = p.stdout.read(w * h * ch)
            if len(b) < w * h * ch:
                break
            yield np.frombuffer(b, np.uint8).reshape(h, w, ch)
    finally:
        p.stdout.close()
        p.wait()


def clip(wav: Path, length: float) -> Path:
    n = int(round(length * fl.FPS))
    W, H = fl.OUT_W, fl.OUT_H
    LUPE = 420
    tmp = WORK / "vergleich_video.mp4"
    ff = subprocess.Popen([fl.FFMPEG, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                           "-r", str(fl.FPS), "-i", "-", "-c:v", "libx264", "-crf", "16", "-preset", "slow",
                           "-pix_fmt", "yuv420p", str(tmp)], stdin=subprocess.PIPE)
    segs = [("studio", None, "alt"), ("studio", None, "neu"), ("bruessel", "bruessel", "alt"),
            ("bruessel", "bruessel", "neu")]
    for ort_name, ort, var in segs:
        faces = np.load(WORK / var / f"vgl_{var}_faces.npy")
        fx_, fy_, fs_ = face_box_out(ort, var, faces)
        z = max(16, int(fs_ * 1.8) // 2 * 2)                 # Lupe: 1,8x Gesicht
        zx = int(np.clip(fx_ - z / 2, 0, W - z))
        zy = int(np.clip(fy_ - z / 2 + fs_ * 0.15, 0, H - z))
        lab = label(f"{'Studio' if ort is None else 'Brüssel'}  -  {TITEL[var]}", 900, 64)
        llab = label("Lupe Gesicht", LUPE, 40, 24)
        for i, fr in enumerate(_reader(WORK / var / f"vgl_{var}_{ort_name}.mp4", W, H)):
            if i >= n:
                break
            c = fr.copy()
            c[24:88, 24:924] = lab
            lupe = cv2.resize(fr[zy:zy + z, zx:zx + z], (LUPE, LUPE), interpolation=cv2.INTER_LANCZOS4)
            c[24:64, W - LUPE - 24:W - 24] = llab
            c[64:64 + LUPE, W - LUPE - 24:W - 24] = lupe
            ff.stdin.write(c.tobytes())
    # Nahaufnahme aus den Freistellern (volle Quellaufloesung): alt links, neu rechts
    P = fl.POSEN[POSE]
    faces = np.load(WORK / "alt" / "vgl_alt_faces.npy")
    cx, cy, sz = np.median(faces, 0)
    s = int(sz * 1.6)
    x0, y0 = int(cx - s / 2), int(cy - s / 2 + sz * 0.15)
    labs = [label(TITEL[v], 900, 64, 30) for v in ("alt", "neu")]
    rd = [_reader(WORK / v / f"vgl_{v}_freisteller_lipsync_prores4444.mov", P["w"], P["h"], "rgba") for v in ("alt", "neu")]
    head = label("Nahaufnahme Mund (Freisteller, vor dem Einsetzen)", W, 70, 34)
    for i in range(n):
        c = np.full((H, W, 3), 18, np.uint8)
        c[:70] = head
        for j, r in enumerate(rd):
            fr = next(r, None)
            if fr is None:
                continue
            a = fr[..., 3:4].astype(np.float32) / 255
            rgb = (fr[..., :3] * a + 40 * (1 - a)).astype(np.uint8)
            x = 40 + j * 940
            c[100:164, x:x + 900] = labs[j]
            c[170:170 + 900, x:x + 900] = cv2.resize(rgb[y0:y0 + s, x0:x0 + s], (900, 900),
                                                     interpolation=cv2.INTER_LANCZOS4)
        ff.stdin.write(c.tobytes())
    ff.stdin.close()
    if ff.wait():
        raise RuntimeError("Vergleichsclip schreiben fehlgeschlagen")
    REPORT.mkdir(parents=True, exist_ok=True)
    out = REPORT / "lipsync_vergleich_alt_neu_studio_bruessel_20261001.mp4"
    k = len(segs) + 1
    ins = sum([["-i", str(wav)] for _ in range(k)], [])
    pads = ";".join(f"[{i + 1}:a]apad=whole_dur={length:.3f},atrim=0:{length:.3f}[a{i}]" for i in range(k))
    fl.run([fl.FFMPEG, "-y", "-v", "error", "-i", tmp, *ins, "-filter_complex",
            pads + ";" + "".join(f"[a{i}]" for i in range(k)) + f"concat=n={k}:v=0:a=1,aresample=48000,"
            "pan=stereo|c0=c0|c1=c0[a]", "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "256k",
            "-shortest", "-movflags", "+faststart", out])
    return out


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "alles"
    import gpu_budget
    WORK.mkdir(parents=True, exist_ok=True)
    resf = WORK / "ergebnis.json"
    res = json.loads(resf.read_text(encoding="utf-8")) if resf.exists() else {}
    wav, length = test_wav()
    res["testton"] = dict(datei=str(wav), sekunden=length, quelle=str(WAV_SRC))
    if what in ("stills", "videos", "alles"):
        t = time.time()
        progress("Warte in der GPU-Warteschlange auf einen Platz, Prioritaet Render.")
        gpu_budget.hold("lipsync", name=f"lipsync freisteller ({Path(sys.argv[0]).stem})", prio=3, vram_mb=14000,
                        progress=lambda w, m: progress(f"Warte seit {m:.0f} Minuten in der GPU-Warteschlange: {w}"))
        res["gpu_wartezeit_s"] = round(time.time() - t)
    if what in ("stills", "alles"):
        res["stills"] = stills()
        resf.write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    if what in ("videos", "alles"):
        res["videos"] = videos(wav, length)
        resf.write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    if what in ("clip", "videos", "alles"):
        progress("Baue den Vergleichsclip.")
        res["clip"] = str(clip(wav, length))
        resf.write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    progress("Vergleich fertig gerechnet, Bericht folgt.")
    print("FERTIG", flush=True)


if __name__ == "__main__":
    main()
