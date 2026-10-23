"""Ende-zu-Ende-Vergleich der Gesichtsdetektoren in LatentSync (Task 767c, 22.10.2026).

.venv-lipsync\Scripts\python.exe tools\lipsync_detektor_test.py <ordner mit {sitz,stehend}_zoom.mp4 + _ton16k.wav> [detektoren,...]
Je Clip (erste 6 s) und Detektor ein LatentSync-Lauf (Stufe 2 wie Produktion: 20 Schritte/guidance 2.0 per settings,
DeepCache, Referenz geschlossener Mund) ueber die GPU-Warteschlange (prio 4, Sperre weltlage_lipsync -> Produktion
hat Vorrang). Ergebnis: <ordner>/<clip>_<detektor>.mp4 + lauf.json (Laufzeit reine Rechenzeit).
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config.settings import NEWS_LIPSYNC_STEPS, NEWS_LIPSYNC_GUIDANCE  # noqa: E402
from video import freisteller_lipsync as fl  # noqa: E402

GQ = Path(r"C:\Users\Marlon\projekte\jarvis\tools\gpu_queue.py")
PY = ROOT / ".venv-lipsync" / "Scripts" / "python.exe"
LEN = 6.0


def main():
    d = Path(sys.argv[1]).resolve()
    dets = sys.argv[2].split(",") if len(sys.argv) > 2 else ["insightface", "mediapipe", "yunet"]
    info = json.loads((d / "lauf.json").read_text()) if (d / "lauf.json").exists() else {}
    for clip in ("sitz", "stehend"):
        n = round(LEN * 25)
        vid, wav = d / f"{clip}_in.mp4", d / f"{clip}_in.wav"
        if not vid.exists():
            subprocess.run([fl.FFMPEG, "-y", "-v", "error", "-i", d / f"{clip}_zoom.mp4", "-frames:v", str(n + 5), "-an",
                            "-c:v", "libx264", "-preset", "veryfast", "-crf", "10", "-pix_fmt", "yuv420p", vid], check=True)
            subprocess.run([fl.FFMPEG, "-y", "-v", "error", "-i", d / f"{clip}_ton16k.wav", "-t", str(LEN), wav], check=True)
        for det in dets:
            out = d / f"{clip}_{det}.mp4"
            if out.exists():
                continue
            env = dict(os.environ, LIPSYNC_DETEKTOR=det)
            cmd = [sys.executable, str(GQ), "run", "--name", f"lipsync detektor-test {clip} {det} (767c)", "--prio", "4",
                   "--vram", "11000", "--excl", "weltlage_lipsync", "--",
                   str(PY), str(ROOT / "tools" / "latentsync_ref_inference.py"),
                   "--unet_config_path", "configs/unet/stage2_512.yaml", "--inference_ckpt_path", "checkpoints/latentsync_unet.pt",
                   "--inference_steps", str(NEWS_LIPSYNC_STEPS), "--guidance_scale", str(NEWS_LIPSYNC_GUIDANCE),
                   "--enable_deepcache", "--ref_mode", "closed", "--video_path", str(vid), "--audio_path", str(wav),
                   "--video_out_path", str(out.with_suffix(".tmp.mp4")), "--temp_dir", str(d / f"tmp_{clip}_{det}")]
            t = time.time()
            with open(d / f"{clip}_{det}.log", "w") as lg:
                r = subprocess.run(cmd, cwd=str(fl.REPO), env=env, stdout=lg, stderr=subprocess.STDOUT)
            ok = r.returncode == 0 and out.with_suffix(".tmp.mp4").exists()
            if ok:
                out.with_suffix(".tmp.mp4").replace(out)
            info[f"{clip}_{det}"] = {"ok": ok, "gesamt_s": round(time.time() - t, 1)}
            (d / "lauf.json").write_text(json.dumps(info, indent=1))
            print(clip, det, info[f"{clip}_{det}"], flush=True)


main()
