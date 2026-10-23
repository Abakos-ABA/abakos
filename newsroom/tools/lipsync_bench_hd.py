"""Zeit der HD-Stufen (Zoom Real-ESRGAN+GFPGAN, Nachzeichnen GFPGAN) pro Clip. Aufruf (.venv-lipsync, cwd newsroom):
    lipsync_bench_hd.py <grau25.mp4> <x> <y> <s> <bilder> <out_dir>"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from video import freisteller_lipsync as fl, gesicht_hd
g, x, y, s, n, out = Path(sys.argv[1]), *map(int, sys.argv[2:6]), Path(sys.argv[6])
out.mkdir(exist_ok=True, parents=True)
t = time.time(); gesicht_hd.zoom_window(fl.FFMPEG, g, 0, n, x, y, s, 768, out / "zoomhd.mp4", 25, batch=4); print("zoom_hd_s", round(time.time() - t, 1), "bilder", n)
fr = list(fl._read_rgb(out / "zoomhd.mp4", 768, 768))[:n]
t = time.time(); gesicht_hd.restore(fr, gesicht_hd.GFP_OUT, batch=4); print("restore_s", round(time.time() - t, 1))
