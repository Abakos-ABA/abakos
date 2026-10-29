"""TESTFASSUNG v2 (nicht in der Pipeline): Lipsync der stehenden Latara auf dem FREISTELLER, dann ins Studio.

rexemres Korrektur vom 29.09.2026: Reihenfolge strikt
  1. Freisteller (stehend_v6_alpha_prores4444.mov, 832x1248, volle Aufloesung, ohne Studio) nehmen,
  2. darauf lipsyncen (LatentSync 1.6, Gesicht eng zugeschnitten und hochskaliert, 20 Schritte, staerkere guidance),
  3. Matte/Alpha erhalten (Original-Alpha, der Lipsync ersetzt nur die untere Gesichtshaelfte innerhalb der Alpha),
  4. erst danach skalieren und in der abgemachten Position (host_placement_v6_neuer_hintergrund.json) ins Studio setzen.
Gegenueber v1 (tools/weltlage_lipsync_stehend.py): Eingang ist der Freisteller statt des Rohvideos, engeres
Gesichtsfenster, 20 statt 8 Schritte, guidance per --guidance (Standard 2.0), groessere Einsetz-Maske (ganze
untere Gesichtshaelfte), zusaetzlich ein Freisteller-Zwischenergebnis mit Alpha (ProRes 4444) pro Szene.

    .venv-lipsync\\Scripts\\python.exe tools\\weltlage_lipsync_stehend_v2.py [--probe] [--guidance 2.0] [testordner]
"""
import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import gpu_budget                                              # noqa: E402
import composite_stehend_v6_neuer_hintergrund as cs            # noqa: E402
from weltlage_rohschnitt import FFMPEG, VENC, abo_overlay, clip, dur   # noqa: E402
from weltlage_lipsync_stehend import (ALPHA, V6, REPO, LS_PY, W0, H0, FPS, run, read_frames,  # noqa: E402
                                      scene_vf, track_faces, quiet_cuts)

ZOOM = 768
STEPS = 20
WIN = 2.2                                              # Fensterkante in Gesichtsgroessen (v1: 2,6)
GREY = 128


def freisteller_scene(f0: int, n: int, work: Path, name: str) -> tuple[Path, list[np.ndarray]]:
    """Szenenausschnitt des Freistellers auf neutralem Grau (Eingang fuer LatentSync) + Alpha-Bilder."""
    out = work / f"{name}_freisteller_grau25.mp4"
    alphas, rgb = [], []
    for rgba in read_frames(ALPHA, scene_vf(f0, n), W0, H0, 4):
        a = rgba[..., 3:4].astype(np.float32) / 255
        rgb.append(np.clip(rgba[..., :3] * a + GREY * (1 - a) + 0.5, 0, 255).astype(np.uint8))
        alphas.append(rgba[..., 3].copy())
        if len(rgb) >= n:
            break
    ff = subprocess.Popen([FFMPEG, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W0}x{H0}",
                           "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-crf", "10", "-pix_fmt", "yuv420p", str(out)],
                          stdin=subprocess.PIPE)
    for fr in rgb:
        ff.stdin.write(fr.tobytes())
    ff.stdin.close()
    if ff.wait():
        raise SystemExit("Freisteller-Ausschnitt fehlgeschlagen")
    return out, rgb, alphas


def sync_chunk(tag, wav, src_scene, f0, f1, box, work, guidance):
    x, y, s = box
    n = f1 - f0
    out = work / f"{tag}_synced.mp4"
    if not out.exists():
        seg_wav, seg_vid = work / f"{tag}.wav", work / f"{tag}_zoom.mp4"
        run([FFMPEG, "-y", "-v", "error", "-i", wav, "-ss", f"{f0 / FPS:.3f}", "-to", f"{f1 / FPS:.3f}", "-ar", "16000",
             "-ac", "1", seg_wav])
        run([FFMPEG, "-y", "-v", "error", "-i", src_scene, "-vf",
             f"trim=start_frame={f0}:end_frame={f1 + 5},setpts=PTS-STARTPTS,crop={s}:{s}:{x}:{y},"
             f"scale={ZOOM}:{ZOOM}:flags=lanczos", "-an", "-c:v", "libx264", "-crf", "10", "-pix_fmt", "yuv420p", seg_vid])
        t = time.time()
        with open(work / f"{tag}_latentsync.log", "w") as log:
            r = subprocess.run([str(LS_PY), "-m", "scripts.inference", "--unet_config_path", "configs/unet/stage2_512.yaml",
                                "--inference_ckpt_path", "checkpoints/latentsync_unet.pt", "--inference_steps", str(STEPS),
                                "--guidance_scale", str(guidance), "--enable_deepcache", "--video_path", str(seg_vid),
                                "--audio_path", str(seg_wav), "--video_out_path", str(out),
                                "--temp_dir", str(work / f"{tag}_ls")],
                               cwd=str(REPO), stdout=subprocess.DEVNULL, stderr=log, timeout=1800)
        if r.returncode or not out.exists():
            raise SystemExit(f"LatentSync fehlgeschlagen ({tag}), siehe {tag}_latentsync.log")
        print(f"  {tag}: {n / FPS:.1f} s Ton in {time.time() - t:.0f} s gesynct", flush=True)
    frames = [cv2.resize(fr, (s, s), interpolation=cv2.INTER_AREA)
              for fr in read_frames(out, "null", ZOOM, ZOOM, 3)][:n]
    if len(frames) < n:
        frames += [frames[-1]] * (n - len(frames))
    return frames


def mouth_motion(frames, faces, offs=(0, 0)):
    """Mittlere Bild-zu-Bild-Aenderung im Mundkasten (Mass fuer sichtbare Mundbewegung, Skala 0-255)."""
    v = []
    for i in range(1, len(frames)):
        cx, cy, size = faces[i]
        x0, y0 = int(cx - size * 0.22) - offs[0], int(cy + size * 0.18) - offs[1]
        a = frames[i][y0:y0 + int(size * 0.3), x0:x0 + int(size * 0.44)].astype(np.float32)
        b = frames[i - 1][y0:y0 + int(size * 0.3), x0:x0 + int(size * 0.44)].astype(np.float32)
        v.append(np.abs(a - b).mean())
    return float(np.mean(v))


def windows_for(faces, cuts):
    wins = []
    for k in range(len(cuts) - 1):
        fc = faces[cuts[k]:cuts[k + 1]]
        size = float(fc[0, 2])
        cx = (fc[:, 0].min() + fc[:, 0].max()) / 2
        cy = (fc[:, 1].min() + fc[:, 1].max()) / 2 + size * 0.1
        s = int(min(max(size * WIN, np.ptp(fc[:, 0]) + size * 1.9, np.ptp(fc[:, 1]) + size * 1.9), W0) // 2 * 2)
        x = int(min(max(cx - s / 2, 0), W0 - s)) // 2 * 2
        y = int(min(max(cy - s / 2, 0), H0 - s)) // 2 * 2
        wins.append((x, y, s))
    return wins


def build_scene(name, wav, start, L, work, guidance, probe=False):
    f0, n = round(start * FPS), round(L * FPS)
    print(f"{name}: Bilder {f0}-{f0 + n} ({L:.2f} s), guidance {guidance}", flush=True)
    src, rgb, alphas = freisteller_scene(f0, n, work, name)
    faces = track_faces(rgb)
    np.save(work / f"{name}_faces.npy", faces)
    cuts = quiet_cuts(wav, n)
    if probe:
        cuts = cuts[:2]
    wins = windows_for(faces, cuts)
    lip = [None] * n
    for k, (a, b) in enumerate(zip(cuts[:-1], cuts[1:])):
        for i, fr in enumerate(sync_chunk(f"{name}_{k:02d}", wav, src, a, b, wins[k], work, guidance)):
            lip[a + i] = (fr, wins[k])
    if probe:
        a, b = cuts[0], cuts[1]
        x, y, s = wins[0]
        m = mouth_motion([lip[i][0] for i in range(a, b)], faces[a:b], (x, y))
        return m, faces[a:b]
    # Freisteller mit Lipsync zusammensetzen (Alpha = Original), als ProRes 4444 sichern und direkt ins Studio
    yy, xx = np.mgrid[0:H0, 0:W0].astype(np.float32)
    fs_out = work / f"{name}_freisteller_lipsync_prores4444.mov"
    comp = work / f"{name}_studio.mp4"
    pf = subprocess.Popen([FFMPEG, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W0}x{H0}",
                           "-r", str(FPS), "-i", "-", "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt",
                           "yuva444p10le", str(fs_out)], stdin=subprocess.PIPE)
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
        # ganze untere Gesichtshaelfte (Nasenspitze bis unters Kinn, Wange zu Wange), weicher Rand
        d = np.sqrt(((xx - cx) / (size * 0.50)) ** 2 + ((yy - (cy + size * 0.30)) / (size * 0.48)) ** 2)
        m = np.clip((1.2 - d) / 0.35, 0, 1)
        m = m * m * (3 - 2 * m)
        al = cv2.erode(alphas[i], np.ones((5, 5), np.uint8))
        m = m * (cv2.GaussianBlur(al, (0, 0), 1.5).astype(np.float32) / 255)
        out = rgba.copy()
        full = out[..., :3].astype(np.float32)
        mm = m[y:y + s, x:x + s, None]
        full[y:y + s, x:x + s] = full[y:y + s, x:x + s] * (1 - mm) + fr.astype(np.float32) * mm
        out[..., :3] = np.clip(full + 0.5, 0, 255).astype(np.uint8)
        pf.stdin.write(out.tobytes())
        ff.stdin.write(out.tobytes())
        if i in (n // 4, n // 2, 3 * n // 4):
            r0, c0, e = int(cy - size), int(cx - size), int(2 * size)
            check.append(np.concatenate([rgba[r0:r0 + e, c0:c0 + e, :3], out[r0:r0 + e, c0:c0 + e, :3]], 1))
    for proc in (pf, ff):
        proc.stdin.close()
        if proc.wait():
            raise SystemExit("Composite fehlgeschlagen")
    cv2.imwrite(str(work / f"{name}_vergleich_gesicht.png"), cv2.cvtColor(np.concatenate(check, 0), cv2.COLOR_RGB2BGR))
    (work / f"{name}_fenster.json").write_text(json.dumps({"cuts": cuts, "windows": wins}), encoding="utf-8")
    return comp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("test", nargs="?", default=str(ROOT / "data" / "weltlage_test_20260929"))
    ap.add_argument("--guidance", type=float, default=2.0)
    ap.add_argument("--probe", action="store_true", help="nur erstes Stueck Szene 1, Mundbewegung messen")
    a = ap.parse_args()
    t_all = time.time()
    test = Path(a.test).resolve()
    sch = test / "_schnitt"
    work = test / ("_lipsync_stehend_v2_probe_g%s" % a.guidance if a.probe else "_lipsync_stehend_v2")
    work.mkdir(exist_ok=True)
    texte = json.loads((test / "texte.json").read_text(encoding="utf-8"))["szenen"]
    abo4 = next(t.get("abo_at", 0) for t in texte if t["id"] == "s4_ueberblick")
    L1, L4 = dur(sch / "a01.wav"), dur(sch / "a05.wav")
    start4 = max(0.0, dur(V6) - L4 - 0.1)
    why = gpu_budget.policy("lipsync")
    if why:
        raise SystemExit(f"GPU belegt: {why}")
    gpu_budget.hold("lipsync", name=f"lipsync {Path(__file__).stem}")   # GPU-Warteschlange bis Prozessende (29.09.)
    if a.probe:
        m, faces = build_scene("s1", sch / "a01.wav", 0.0, L1, work, a.guidance, probe=True)
        v1 = test / "_lipsync_stehend"
        w1 = json.loads((v1 / "s1_fenster.json").read_text())["windows"][0]
        f1 = np.load(v1 / "s1_faces.npy")
        c1 = json.loads((v1 / "s1_fenster.json").read_text())["cuts"]
        fr1 = [cv2.resize(f, (w1[2], w1[2]), interpolation=cv2.INTER_AREA)
               for f in read_frames(v1 / "s1_00_synced.mp4", "null", ZOOM, ZOOM, 3)][:c1[1]]
        m1 = mouth_motion(fr1, f1[:len(fr1)], (w1[0], w1[1]))
        print(f"MUNDBEWEGUNG v1={m1:.2f}  neu(g{a.guidance})={m:.2f}", flush=True)
        return
    zeiten = {}
    t = time.time(); c1 = build_scene("s1", sch / "a01.wav", 0.0, L1, work, a.guidance); zeiten["Szene 1"] = time.time() - t
    t = time.time(); c4 = build_scene("s4", sch / "a05.wav", start4, L4, work, a.guidance); zeiten["Szene 4"] = time.time() - t
    s1 = work / "s1.mp4"; clip(c1, 0, L1, s1)
    clip(c4, 0, L4, work / "s4_ohne_abo.mp4"); s4 = work / "s4.mp4"
    abo_overlay(work / "s4_ohne_abo.mp4", abo4 + 0.25, s4)
    lines = (sch / "video.txt").read_text(encoding="utf-8").splitlines()
    rep = {"s1.mp4": s1, "s4.mp4": s4}
    new = []
    for l in lines:
        name = l.split("/")[-1].rstrip("'")
        new.append(f"file '{rep[name].as_posix()}'" if name in rep else l)
    assert sum(1 for x, y in zip(lines, new) if x != y) == 2, new
    vl = work / "video.txt"; vl.write_text("\n".join(new) + "\n", encoding="utf-8")
    t = time.time()
    vid = work / "video_all.mp4"
    run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", vl, "-vf", "fps=24", *VENC, vid])
    out = test / "weltlage_rohschnitt_20260929_lipsync_stehend_v2_TEST.mp4"
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
