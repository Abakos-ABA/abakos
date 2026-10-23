"""Testclips fuer den Lipsync-Verfahrensvergleich (Task c49b, 22.10.2026): erzeugt je Pose ein Gesichtsfenster (768,
Grau-Freisteller, wie sync_chunk) + Ton 16 kHz + faces.npy. Keine GPU. Aufruf mit .venv-lipsync:
    python tools/lipsync_bench_prep.py <stehend|sitz> <wav> <start_s> <laenge_s> <ausgabeordner>
"""
import subprocess, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from video import freisteller_lipsync as fl

pose, wav, start, length, out = sys.argv[1], Path(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]), Path(sys.argv[5])
out.mkdir(parents=True, exist_ok=True)
P = fl.POSEN[pose]; W0, H0 = P["w"], P["h"]
f0, n = round(start * fl.FPS), round(length * fl.FPS)
grey = out / f"{pose}_grau25.mp4"
tr = fl.FaceTracker(pose)
ff = subprocess.Popen([fl.FFMPEG, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W0}x{H0}", "-r", "25",
                       "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "10", "-pix_fmt", "yuv420p", str(grey)],
                      stdin=subprocess.PIPE)
for i, rgba in enumerate(fl.source_frames(pose, f0, n + 5)):
    a = rgba[..., 3:4].astype(np.float32) / 255
    rgb = np.clip(rgba[..., :3] * a + fl.GREY * (1 - a) + 0.5, 0, 255).astype(np.uint8)
    ff.stdin.write(rgb.tobytes())
    if i < n:
        tr.add(rgb)
ff.stdin.close(); ff.wait()
faces = fl.smooth_faces(tr.boxes, W0)
np.save(out / f"{pose}_faces.npy", faces)
x, y, s = fl.windows_for(faces, [0, n], W0, H0)[0]
zoom = out / f"{pose}_zoom.mp4"
subprocess.run([fl.FFMPEG, "-y", "-v", "error", "-i", str(grey), "-vf",
                f"trim=start_frame=0:end_frame={n + 5},setpts=PTS-STARTPTS,crop={s}:{s}:{x}:{y},scale=768:768:flags=lanczos",
                "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "10", "-pix_fmt", "yuv420p", str(zoom)], check=True)
subprocess.run([fl.FFMPEG, "-y", "-v", "error", "-i", str(wav), "-ss", f"{start:.3f}", "-t", f"{length:.3f}", "-ar", "16000", "-ac", "1",
                str(out / f"{pose}_ton16k.wav")], check=True)
print(pose, "fenster", (x, y, s), "bilder", n, "gesicht", faces[0])
