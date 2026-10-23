"""Lip-sync of a narration segment onto a "master" host clip with LatentSync 1.6 (Apache-2.0),
running in its own environment (.venv-lipsync, torch 2.5.1/cu121) from vendor/LatentSync.

Pattern the owner asked for: ONE long, lively "presenting" master clip per pose (mouth closed,
gestures, natural head/face motion - config/brand/clips_wide/master_*.mp4, rendered once with Wan),
and per video only the spoken segment is synced onto a cut of that master and trimmed to the
audio. LatentSync only repaints the mouth region, so the master's motion, hair, hands and the
studio stay untouched.

Weltlage Kompakt (Latara, Langformat) nutzt dieses Modul NICHT mehr: dort gilt seit 29.09.2026 die feste Regel
"Lipsync immer auf dem Freisteller in voller Aufloesung, erst danach ins Studio" -> video/freisteller_lipsync.py.
Dieses Modul bleibt fuer die aelteren Master-Clips von video/assemble.py.

GPU rule: never run this while ComfyUI renders - measured 60 s for 7.7 s of speech alone vs. 8-11 min
when Wan shared the card. The pipeline calls it in the assemble stage, after the b-roll stage stopped
ComfyUI.
"""
import logging
import subprocess
from pathlib import Path

from config.settings import BASE_DIR, CONFIG_DIR, NEWS_LIPSYNC, NEWS_LIPSYNC_STEPS, NEWS_LIPSYNC_GUIDANCE
from video import layout as L

logger = logging.getLogger(__name__)

VENV_PY = BASE_DIR / ".venv-lipsync" / "Scripts" / "python.exe"
REPO = BASE_DIR / "vendor" / "LatentSync"
MASTERS_DIR = CONFIG_DIR / "brand" / L.CLIPS_DIR_NAME
FPS = 25            # LatentSync works at 25 fps; assemble re-times to its own fps


def available() -> bool:
    return NEWS_LIPSYNC and VENV_PY.exists() and (REPO / "scripts" / "inference.py").exists() \
        and (REPO / "checkpoints" / "latentsync_unet.pt").exists()


def masters() -> list[Path]:
    return sorted(p for p in MASTERS_DIR.glob("master_*.mp4") if ".take" not in p.name)


def _duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def _cut_audio(audio: Path, start: float, end: float, out: Path):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(audio), "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
                    "-ar", "16000", "-ac", "1", str(out)], check=True)


def _cut_master(master: Path, seconds: float, offset: float, out: Path):
    """A `seconds` long piece of the master starting at `offset` (wraps by ping-pong if the master is
    shorter), 25 fps, no audio."""
    total = _duration(master)
    if offset + seconds <= total:
        vf = f"trim=start={offset:.3f}:duration={seconds:.3f},setpts=PTS-STARTPTS,fps={FPS}"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(master), "-vf", vf, "-an", "-c:v", "libx264", "-crf", "16",
                        "-pix_fmt", "yuv420p", str(out)], check=True)
    else:
        fc = (f"[0:v]split[a][b];[b]reverse[r];[a][r]concat=n=2:v=1:a=0,loop=loop=-1:size=32767,"
              f"trim=duration={seconds:.3f},setpts=PTS-STARTPTS,fps={FPS}[v]")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(master), "-filter_complex", fc, "-map", "[v]", "-an",
                        "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", str(out)], check=True)


def _face_window(video: Path) -> tuple[int, int, int, int] | None:
    """Face-centred crop (multiple of 16) of the first frame via mediapipe-free heuristics: OpenCV's
    built-in Haar detector is enough to locate the anchor once; None if the face is already large."""
    import cv2
    cap = cv2.VideoCapture(str(video)); ok, frame = cap.read(); cap.release()
    if not ok:
        return None
    H, W = frame.shape[:2]
    faces = []
    try:                                                    # OpenCV 5 dropped the Haar cascades
        det = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        faces = det.detectMultiScale(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), 1.1, 4, minSize=(24, 24))
    except Exception:
        faces = []
    if len(faces) == 0:
        cx, cy, fh = W * 0.49, H * 0.40, H * 0.14           # layout default: anchor at the desk
    else:
        fx, fy, fw, fh = max(faces, key=lambda f: f[2] * f[3]); cx, cy = fx + fw / 2, fy + fh / 2
    if fh >= H * 0.28:
        return None                                        # already big enough for the detector
    w = int(min(W, max(fh * 6.5, W * 0.4))); h = int(w * 704 / 1280)
    if h > H:
        h = H; w = int(h * 1280 / 704)
    x = int(min(max(cx - w / 2, 0), W - w)); y = int(min(max(cy - h * 0.42, 0), H - h))
    return (x // 2 * 2, y // 2 * 2, w // 2 * 2, h // 2 * 2)


def sync_segment(job_id: str, audio: Path, start: float, end: float, master: Path, out: Path, offset: float = 0.0) -> Path | None:
    """Lip-syncs narration [start, end) onto the master and writes `out` (video with that audio).
    Returns None on any failure so the caller falls back to the plain (mouth-closed) clip."""
    if not available():
        return None
    seconds = end - start
    if seconds < 0.8:
        return None
    tmp = out.parent / f"{out.stem}.tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    wav, vid = tmp / "seg.wav", tmp / "seg.mp4"
    try:
        _cut_audio(audio, start, end, wav)
        _cut_master(master, seconds + 0.2, offset, vid)
        # The anchor's face is small in a wide studio shot (preview masters are 960x528): sync a
        # face-centred window, enlarged to what the detector expects, then paste it back.
        zoom_box = _face_window(vid)
        work_in, synced = vid, tmp / "synced.mp4"
        if zoom_box:
            x, y, w, h = zoom_box
            work_in = tmp / "zoom.mp4"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(vid), "-vf", f"crop={w}:{h}:{x}:{y},scale=1280:704:flags=lanczos",
                            "-c:v", "libx264", "-crf", "14", "-pix_fmt", "yuv420p", str(work_in)], check=True)
        cmd = [str(VENV_PY), "-m", "scripts.inference", "--unet_config_path", "configs/unet/stage2_512.yaml",
               "--inference_ckpt_path", "checkpoints/latentsync_unet.pt", "--inference_steps", str(NEWS_LIPSYNC_STEPS),
               "--guidance_scale", str(NEWS_LIPSYNC_GUIDANCE), "--enable_deepcache", "--video_path", str(work_in),
               "--audio_path", str(wav),
               "--video_out_path", str(synced), "--temp_dir", str(tmp / "ls")]
        import gpu_budget                                  # zentrale GPU-Warteschlange (29.09.), Fallback ohne
        with gpu_budget.slot("lipsync", name=f"lipsync {job_id}"):
            result = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True, timeout=1800)
        if result.returncode != 0 or not synced.exists():
            logger.warning("lipsync failed for %s (%.1fs): %s", job_id, seconds, result.stderr[-600:])
            return None
        if zoom_box:
            x, y, w, h = zoom_box
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(vid), "-i", str(synced),
                            "-filter_complex", f"[1:v]scale={w}:{h}:flags=lanczos[z];[0:v][z]overlay={x}:{y}:shortest=1[v]",
                            "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", "-c:a", "aac", str(out)], check=True)
        else:
            synced.replace(out)
        logger.info("lipsync done for %s: %.1fs segment -> %s", job_id, seconds, out.name)
        return out
    except Exception as e:
        logger.warning("lipsync error for %s: %s", job_id, e)
        return None
