"""Lipsync-Qualitaet: Vergleichslauf alt gegen neu, ohne video/freisteller_lipsync.py zu aendern (30.09.2026).

Nutzt render-Schritte aus video/freisteller_lipsync (Freisteller -> LatentSync im Gesichtsfenster -> Mund zurueck ->
Studio 1920x1080), aber mit waehlbaren LatentSync-Einstellungen und tools/latentsync_ref_inference.py (Referenzbild mit
geschlossenem Mund statt Originalbild). Eigener Zwischenspeicher je Einstellung, GPU ueber die Warteschlange wie im
Original (gpu_budget.hold + state/latentsync.lock). Am Ende 24-fps-Clip mit bildgenau angelegtem Ton.

    .venv-lipsync\\Scripts\\python.exe tools\\lipsync_v2_test.py <pose> <ton.wav> <start_s> <laenge_s> <ordner> <name>
        [--ref closed|self] [--steps 20] [--guidance 2.5] [--deepcache] [--ton-start s]
"""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from video import freisteller_lipsync as fl  # noqa: E402

WRAPPER = ROOT / "tools" / "latentsync_ref_inference.py"
_Popen = subprocess.Popen


def patch(ref: str, deepcache: bool):
    class P(_Popen):
        def __init__(self, args, *a, **k):
            if isinstance(args, list) and "scripts.inference" in args:
                i = args.index("-m")
                args = args[:i] + [str(WRAPPER)] + args[i + 2:]
                if not deepcache and "--enable_deepcache" in args:
                    args.remove("--enable_deepcache")
                args += ["--ref_mode", ref]
            k.setdefault("creationflags", 0x08000000)       # CREATE_NO_WINDOW: keine Konsolen-Popups
            super().__init__(args, *a, **k)
    subprocess.Popen = P


def main():
    ap = argparse.ArgumentParser()
    for n in ("pose", "wav", "start", "length", "work", "name"):
        ap.add_argument(n)
    ap.add_argument("--ref", default="closed")
    ap.add_argument("--steps", type=int, default=20)
    ap.add_argument("--guidance", type=float, default=2.5)
    ap.add_argument("--deepcache", action="store_true")
    a = ap.parse_args()
    tag = f"ref{a.ref}_s{a.steps}_g{a.guidance}_{'dc' if a.deepcache else 'nodc'}"
    fl.STEPS, fl.GUIDANCE = a.steps, a.guidance
    fl.SHARED_CACHE = ROOT / "data" / "_latentsync_cache_v2" / tag
    patch(a.ref, a.deepcache)
    work = Path(a.work).resolve()
    a.wav = str(Path(a.wav).resolve())
    fs, n = fl.lipsync_freisteller(a.pose, Path(a.wav), float(a.start), float(a.length), work, a.name,
                                   log=lambda m: print(m, flush=True))
    studio = fl.composite_studio(a.pose, fs, n, work / f"{a.name}_studio.mp4")
    # 25 -> 24 fps wie der Schnitt (fps-Filter, Zeitstempel bleiben), Ton = genau der Lipsync-Eingang, gleiche Laenge
    out = work / f"{a.name}_24fps_mitton.mp4"
    fl.run([fl.FFMPEG, "-y", "-v", "error", "-i", studio, "-i", a.wav, "-vf", "fps=24", "-t", f"{n / fl.FPS:.3f}",
            "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-crf", "16", "-preset", "slow", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", out])
    print(f"fertig ({tag}): {out}", flush=True)


if __name__ == "__main__":
    main()
