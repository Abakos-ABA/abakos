"""VERALTET seit 29.09.2026: ersetzt durch video/freisteller_lipsync.py (Regel: Lipsync auf dem Freisteller,
dann Studio direkt in 1920x1080), eingebaut in tools/weltlage_rohschnitt.py. Nur noch zum Nachvollziehen.

TESTFASSUNG (nicht in der Pipeline): Lipsync fuer die stehende Latara (Szene 1 Cold Open + Szene 4
Ueberblick) eines Weltlage-Rohschnitts, danach neuer Gesamtschnitt als eigene Datei.

Muster wie tools/weltlage_lipsync_sitz.py (LatentSync 1.6, gleiche Einstellungen wie video/lipsync.py,
7-s-Stuecke), aber ohne erneutes Keying, damit die Kanten nicht flimmern:
  1. LatentSync laeuft auf dem ungekeyten Rohvideo stehend_v6_roh.mp4 (gleiche Bilder wie die Alpha-Fassung),
     auf ein eng um das Gesicht zugeschnittenes, hochskaliertes Fenster (Gesicht ist nur ~100 px gross).
  2. Nur eine weiche Ellipse um Mund/Kinn/Wangen (pro Bild per Gesichtserkennung verfolgt, zeitlich geglaettet,
     innerhalb der erodierten Alpha-Maske) wird in die bestehende Alpha-Fassung stehend_v6_alpha_prores4444.mov
     eingesetzt. Alpha, Haare, Koerper, Haende bleiben Bild fuer Bild identisch mit dem Original.
  3. Studio-Composite mit exakt demselben Filter und derselben Platzierung wie
     composite_stehend_v6_neuer_hintergrund.py (host_placement_v6_neuer_hintergrund.json).
  4. Szenen-Clips wie weltlage_rohschnitt.py (1920x1080, 24 fps, Abo-Hinweis in Szene 4); alle anderen Szenen
     und der Ton werden unveraendert aus <test>/_schnitt uebernommen.

Laufen mit .venv-lipsync (OpenCV 4 mit Haar-Kaskaden):
    .venv-lipsync\\Scripts\\python.exe tools\\weltlage_lipsync_stehend.py [testordner]
"""
import json
import re
import subprocess
import sys
import time
import wave
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import gpu_budget                                              # noqa: E402
import composite_stehend_v6_neuer_hintergrund as cs            # noqa: E402
from weltlage_rohschnitt import FFMPEG, VENC, abo_overlay, clip, dur   # noqa: E402

SZ = ROOT / "config" / "brand" / "szene1_stehend_animation"
ROH = SZ / "stehend_v6_roh.mp4"                        # 832x1248, 16 fps, gleiche Bilder wie die Alpha-Fassung
ALPHA = SZ / "stehend_v6_alpha_prores4444.mov"
V6 = SZ / "szene1_stehend_v6_neuer_hintergrund.mp4"    # nur fuer die Zeitberechnung wie im Rohschnitt
REPO = ROOT / "vendor" / "LatentSync"
LS_PY = ROOT / ".venv-lipsync" / "Scripts" / "python.exe"
W0, H0, FPS = 832, 1248, 25
CHUNK = 7.0
ZOOM = 768                                             # Kantenlaenge des hochskalierten Gesichtsfensters
STEPS = 8                                              # wie NEWS_LIPSYNC_STEPS / video/lipsync.py
GUIDANCE = 1.5


def run(cmd):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise RuntimeError(" ".join(map(str, cmd))[:300] + "\n" + r.stderr[-1500:])
    return r


def read_frames(src: Path, vf: str, w: int, h: int, ch: int):
    fmt = {3: "rgb24", 4: "rgba"}[ch]
    p = subprocess.Popen([FFMPEG, "-v", "error", "-i", str(src), "-vf", vf, "-f", "rawvideo", "-pix_fmt", fmt, "-"],
                         stdout=subprocess.PIPE)
    n = w * h * ch
    while True:
        b = p.stdout.read(n)
        if len(b) < n:
            break
        yield np.frombuffer(b, np.uint8).reshape(h, w, ch)
    p.wait()


def scene_vf(f0: int, n: int) -> str:
    return f"fps={FPS},trim=start_frame={f0}:end_frame={f0 + n},setpts=PTS-STARTPTS"


# ---------------------------------------------------------------- Gesicht verfolgen
_DET = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")


def track_faces(frames: list[np.ndarray]) -> np.ndarray:
    """(cx, cy, size) pro Bild. Haar liefert Fehltreffer (Dekollete, Haende) -> nur Kandidaten im oberen Bilddrittel
    mit plausibler Groesse, dem Vorgaenger am naechsten; Luecken interpoliert, danach zeitlich geglaettet."""
    boxes, prev = [], None
    for fr in frames:
        g = cv2.cvtColor(fr, cv2.COLOR_RGB2GRAY)
        c = [f for f in _DET.detectMultiScale(g, 1.08, 4, minSize=(60, 60), maxSize=(160, 160)) if f[1] + f[3] / 2 < H0 * 0.25]
        if c:
            key = (lambda f: abs(f[0] + f[2] / 2 - prev[0]) + abs(f[1] + f[3] / 2 - prev[1])) if prev is not None \
                else (lambda f: -f[2])
            x, y, w, h = min(c, key=key)
            prev = (x + w / 2, y + h / 2, float(w))
            boxes.append(prev)
        else:
            boxes.append(None)
    ok = [i for i, b in enumerate(boxes) if b is not None]
    if len(ok) < len(boxes) * 0.3:
        raise SystemExit(f"Gesicht nur in {len(ok)}/{len(boxes)} Bildern gefunden")
    arr = np.array([boxes[i] for i in ok])
    idx = np.arange(len(boxes))
    out = np.stack([np.interp(idx, ok, arr[:, k]) for k in range(3)], 1)
    # Ausreisser weg (Median 9), dann glaetten (Gauss sigma 2 Bilder) -> Maske zittert nicht
    med = np.stack([np.array([np.median(out[max(0, i - 4):i + 5, k]) for i in idx]) for k in range(3)], 1)
    kern = np.exp(-0.5 * (np.arange(-6, 7) / 2.0) ** 2); kern /= kern.sum()
    pad = np.pad(med, ((6, 6), (0, 0)), mode="edge")
    sm = np.stack([np.convolve(pad[:, k], kern, mode="valid") for k in range(3)], 1)
    sm[:, 2] = np.median(sm[:, 2])                      # Groesse konstant (Kopf steht im Raum, Kamera fix)
    return sm


# ---------------------------------------------------------------- LatentSync pro Stueck
def quiet_cuts(wav: Path, total_frames: int) -> list[int]:
    """Stueckgrenzen (in Bildern) nahe 7 s, jeweils an der leisesten Stelle +-1,2 s (Stoss mitten im Wort vermeiden)."""
    with wave.open(str(wav)) as w:
        sr = w.getframerate()
        a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32)
    hop = sr // FPS
    rms = np.array([np.sqrt(np.mean(a[i * hop:(i + 1) * hop] ** 2) + 1e-9) for i in range(total_frames)])
    cuts, f = [0], 0
    step = int(CHUNK * FPS)
    while total_frames - f > step + FPS:              # Rest > 8 s -> noch ein Schnitt
        lo, hi = f + step - 30, min(f + step + 1, total_frames - FPS)
        f = lo + int(np.argmin(rms[lo:hi])) if hi > lo else f + step
        cuts.append(f)
    cuts.append(total_frames)
    return cuts


def sync_chunk(tag: str, wav: Path, roh_scene: Path, f0: int, f1: int, box, work: Path) -> list[np.ndarray]:
    """LatentSync auf Bilder [f0, f1) im Fenster box=(x, y, s); liefert die gesyncten Fenster in Originalgroesse."""
    x, y, s = box
    n = f1 - f0
    out = work / f"{tag}_synced.mp4"
    if not out.exists():
        seg_wav, seg_vid = work / f"{tag}.wav", work / f"{tag}_zoom.mp4"
        run([FFMPEG, "-y", "-v", "error", "-i", wav, "-ss", f"{f0 / FPS:.3f}", "-to", f"{f1 / FPS:.3f}", "-ar", "16000",
             "-ac", "1", seg_wav])
        # +5 Bilder Reserve wie video/lipsync._cut_master (+0,2 s)
        run([FFMPEG, "-y", "-v", "error", "-i", roh_scene, "-vf",
             f"trim=start_frame={f0}:end_frame={f1 + 5},setpts=PTS-STARTPTS,crop={s}:{s}:{x}:{y},"
             f"scale={ZOOM}:{ZOOM}:flags=lanczos", "-an", "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p", seg_vid])
        t = time.time()
        r = subprocess.run([str(LS_PY), "-m", "scripts.inference", "--unet_config_path", "configs/unet/stage2_512.yaml",
                            "--inference_ckpt_path", "checkpoints/latentsync_unet.pt", "--inference_steps", str(STEPS),
                            "--guidance_scale", str(GUIDANCE), "--enable_deepcache", "--video_path", str(seg_vid),
                            "--audio_path", str(seg_wav), "--video_out_path", str(out), "--temp_dir", str(work / f"{tag}_ls")],
                           cwd=str(REPO), stdout=subprocess.DEVNULL, stderr=open(work / f"{tag}_latentsync.log", "w"),
                           timeout=1800)
        if r.returncode or not out.exists():
            raise SystemExit(f"LatentSync fehlgeschlagen ({tag}), siehe {tag}_latentsync.log")
        print(f"  {tag}: {n / FPS:.1f} s Ton in {time.time() - t:.0f} s gesynct", flush=True)
    frames = [cv2.resize(fr, (s, s), interpolation=cv2.INTER_AREA)
              for fr in read_frames(out, "null", ZOOM, ZOOM, 3)][:n]
    if len(frames) < n:                                   # LatentSync liefert gelegentlich 1-2 Bilder weniger
        frames += [frames[-1]] * (n - len(frames))
    return frames


# ---------------------------------------------------------------- Szene bauen
def build_scene(name: str, wav: Path, start: float, L: float, work: Path) -> Path:
    f0 = round(start * FPS)
    n = round(L * FPS)
    print(f"{name}: Bilder {f0}-{f0 + n} ({L:.2f} s)", flush=True)
    roh_scene = work / f"{name}_roh25.mp4"
    run([FFMPEG, "-y", "-v", "error", "-i", ROH, "-vf", scene_vf(f0, n), "-an", "-c:v", "libx264", "-crf", "10",
         "-pix_fmt", "yuv420p", roh_scene])
    roh = list(read_frames(roh_scene, "null", W0, H0, 3))[:n]
    faces = track_faces(roh)
    np.save(work / f"{name}_faces.npy", faces)
    del roh
    cuts = quiet_cuts(wav, n)
    lip = [None] * n
    windows = []
    for k in range(len(cuts) - 1):
        a, b = cuts[k], cuts[k + 1]
        fc = faces[a:b]
        size = float(fc[0, 2])
        s = int(round(size * 2.6 / 2) * 2)                # Fenster ~2,6x Gesicht: genug Kontext fuer den Detektor
        cx = (fc[:, 0].min() + fc[:, 0].max()) / 2
        cy = (fc[:, 1].min() + fc[:, 1].max()) / 2 + size * 0.1
        s = int(min(max(s, fc[:, 0].ptp() + size * 2.2, fc[:, 1].ptp() + size * 2.2), W0) // 2 * 2)
        x = int(min(max(cx - s / 2, 0), W0 - s)) // 2 * 2
        y = int(min(max(cy - s / 2, 0), H0 - s)) // 2 * 2
        windows.append((x, y, s))
        for i, fr in enumerate(sync_chunk(f"{name}_{k:02d}", wav, roh_scene, a, b, (x, y, s), work)):
            lip[a + i] = (fr, (x, y, s))
    # Zusammensetzen: Alpha-Fassung unveraendert, nur Mund-Ellipse aus dem Lipsync
    yy, xx = np.mgrid[0:H0, 0:W0].astype(np.float32)
    comp = work / f"{name}_studio.mp4"
    p = cs.load_placement()
    ff = subprocess.Popen([FFMPEG, "-v", "error", "-y", "-loop", "1", "-i", str(cs.BG_STILL), "-f", "rawvideo",
                           "-pix_fmt", "rgba", "-s", f"{W0}x{H0}", "-r", str(FPS), "-i", "-",
                           "-filter_complex", cs._filter_complex(p), "-map", "[outv]", "-frames:v", str(n),
                           "-c:v", "libx264", "-crf", "15", "-pix_fmt", "yuv420p", str(comp)], stdin=subprocess.PIPE)
    check = []
    for i, rgba in enumerate(read_frames(ALPHA, scene_vf(f0, n), W0, H0, 4)):
        if i >= n:
            break
        cx, cy, size = faces[i]
        fr, (x, y, s) = lip[i]
        # Ellipse: Nase bis unter das Kinn, Wange zu Wange; weicher Rand ueber ~0,18 Gesichtsbreiten
        ex, ey = cx, cy + size * 0.30
        rx, ry = size * 0.42, size * 0.42
        d = np.sqrt(((xx - ex) / rx) ** 2 + ((yy - ey) / ry) ** 2)
        m = np.clip((1.25 - d) / 0.45, 0, 1)
        m = m * m * (3 - 2 * m)
        al = cv2.erode(rgba[..., 3], np.ones((7, 7), np.uint8))
        al = cv2.GaussianBlur(al, (0, 0), 2).astype(np.float32) / 255
        m = m * al
        out = rgba.copy()
        full = out[..., :3].astype(np.float32)
        mm = m[y:y + s, x:x + s, None]
        full[y:y + s, x:x + s] = full[y:y + s, x:x + s] * (1 - mm) + fr.astype(np.float32) * mm
        out[..., :3] = np.clip(full + 0.5, 0, 255).astype(np.uint8)
        ff.stdin.write(out.tobytes())
        if i in (n // 4, n // 2, 3 * n // 4):
            r0, c0, e = int(cy - size), int(cx - size), int(2 * size)
            check.append(np.concatenate([rgba[r0:r0 + e, c0:c0 + e, :3], out[r0:r0 + e, c0:c0 + e, :3]], 1))
    ff.stdin.close()
    if ff.wait():
        raise SystemExit("Composite fehlgeschlagen")
    if check:
        cv2.imwrite(str(work / f"{name}_vergleich_gesicht.png"),
                    cv2.cvtColor(np.concatenate(check, 0), cv2.COLOR_RGB2BGR))
    (work / f"{name}_fenster.json").write_text(json.dumps({"cuts": cuts, "windows": windows}), encoding="utf-8")
    return comp


def main():
    t_all = time.time()
    test = (Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "weltlage_test_20260929").resolve()
    sch = test / "_schnitt"
    work = test / "_lipsync_stehend"
    work.mkdir(exist_ok=True)
    marks = [l for l in (test / "zeitmarken.txt").read_text(encoding="utf-8").splitlines() if "Szene" in l or "Bumper" in l]
    lens = {i + 1: float(re.search(r"\(([\d.]+) s\)", l).group(1)) for i, l in enumerate(marks)}
    labels = {i + 1: l for i, l in enumerate(marks)}
    assert "Szene 1" in labels[1] and "Szene 4" in labels[5], labels
    texte = json.loads((test / "texte.json").read_text(encoding="utf-8"))["szenen"]
    abo4 = next(t.get("abo_at", 0) for t in texte if t["id"] == "s4_ueberblick")
    # exakt dieselben Laengen/Startpunkte wie weltlage_rohschnitt.py (Ton a01/a05 ist dort schon auf Szenenlaenge gepolstert)
    L1 = dur(sch / "a01.wav")
    L4 = dur(sch / "a05.wav")
    start4 = max(0.0, dur(V6) - L4 - 0.1)
    print(f"Szene 1: {L1:.2f} s ab 0 | Szene 4: {L4:.2f} s ab {start4:.2f} (Zeitmarken {lens[1]} / {lens[5]})", flush=True)
    why = gpu_budget.policy("lipsync")
    if why:
        raise SystemExit(f"GPU belegt: {why}")
    gpu_budget.hold("lipsync", name=f"lipsync {Path(__file__).stem}")   # GPU-Warteschlange bis Prozessende (29.09.)
    zeiten = {}
    t = time.time(); c1 = build_scene("s1", sch / "a01.wav", 0.0, L1, work); zeiten["Szene 1"] = time.time() - t
    t = time.time(); c4 = build_scene("s4", sch / "a05.wav", start4, L4, work); zeiten["Szene 4"] = time.time() - t
    # Szenen-Clips wie im Rohschnitt (clip(): Skalierung auf 1920x1080 + 24 fps)
    s1 = work / "s1.mp4"; clip(c1, 0, L1, s1)
    clip(c4, 0, L4, work / "s4_ohne_abo.mp4"); s4 = work / "s4.mp4"
    abo_overlay(work / "s4_ohne_abo.mp4", abo4 + 0.25, s4)
    # Gesamtschnitt: Liste aus _schnitt, nur s1/s4 ersetzt; Ton unveraendert
    lines = (sch / "video.txt").read_text(encoding="utf-8").splitlines()
    rep = {"s1.mp4": s1, "s4.mp4": s4}
    new = []
    for l in lines:
        name = l.split("/")[-1].rstrip("'")
        new.append(f"file '{rep[name].as_posix()}'" if name in rep else l)
    assert sum(1 for a, b in zip(lines, new) if a != b) == 2, new
    vl = work / "video.txt"; vl.write_text("\n".join(new) + "\n", encoding="utf-8")
    t = time.time()
    vid = work / "video_all.mp4"
    run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", vl, "-vf", f"fps=24", *VENC, vid])
    out = test / "weltlage_rohschnitt_20260929_lipsync_stehend_TEST.mp4"
    run([FFMPEG, "-y", "-i", vid, "-i", sch / "audio_all.wav", "-map", "0:v", "-map", "1:a", "-c:v", "copy",
         "-af", "loudnorm=I=-14:TP=-2:LRA=11", "-ar", "48000", "-ac", "2", "-c:a", "aac", "-b:a", "192k",
         "-shortest", "-movflags", "+faststart", out])
    zeiten["Zusammenschnitt"] = time.time() - t
    zeiten["gesamt"] = time.time() - t_all
    (work / "renderzeiten.json").write_text(json.dumps({k: round(v, 1) for k, v in zeiten.items()}, indent=2), encoding="utf-8")
    print("ZEITEN", {k: round(v) for k, v in zeiten.items()}, flush=True)
    print("FERTIG", out, f"{dur(out):.1f}s", flush=True)


if __name__ == "__main__":
    main()
