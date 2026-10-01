"""KI-Hochskalierung fuers Lipsync-Gesicht der Moderatorin (Real-ESRGAN + GFPGAN, Task 20261001-184254-d71b).

Problem (Messung 01.10.): Im stehenden Freisteller (832x1248) ist das Gesicht nur ~100 px gross; das enge
Gesichtsfenster (2,2x Gesicht, ~220 px) wurde bisher mit Lanczos auf 768 px hochgezogen, LatentSync bekam also ein
weiches Gesicht und lieferte einen weichen, wenig gezeichneten Mund.

Ablauf bei NEWS_WELTLAGE_LIPSYNC_HD (video/freisteller_lipsync.sync_chunk):
  vor LatentSync:  Fenster Bild fuer Bild mit Real-ESRGAN x4plus (x2plus bei grossem Fenster) auf 768 px, danach die
                   untere Gesichtshaelfte mit GFPGAN 1.4 (Anteil GFP_IN) nachgezeichnet
  nach LatentSync: Mundpartie der LatentSync-Ausgabe nochmals mit GFPGAN (Anteil GFP_OUT) -> klare Lippen/Zaehne
GFPGAN nur auf der unteren Gesichtshaelfte: auf dem ganzen Gesicht aenderte es Augenfarbe und Person (Probe 01.10.).
Gesichtspunkte (insightface buffalo_l, wie LatentSync) werden zeitlich geglaettet, sonst flackert GFPGAN.
Modelle: models/upscale/RealESRGAN_x2plus.pth, RealESRGAN_x4plus.pth (BSD-3), GFPGANv1.4.pth (Apache-2.0), via spandrel.
Laeuft in .venv-lipsync (torch cuda) im Prozess, der den GPU-Platz der Warteschlange haelt; free() vor jedem
LatentSync-Stueck gibt den VRAM wieder frei.
"""
import os
import subprocess
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models" / "upscale"
DET_ROOT = ROOT / "vendor" / "LatentSync" / "checkpoints" / "auxiliary"
GFP_IN = 0.6      # GFPGAN-Anteil am LatentSync-Eingang (mehr veraendert die Person)
GFP_OUT = 0.7     # GFPGAN-Anteil auf der LatentSync-Ausgabe
# FFHQ-Ausrichtung 512 (facexlib): Auge l/r, Nase, Mundwinkel l/r
FFHQ_512 = np.array([[192.98138, 239.94708], [318.90277, 240.1936], [256.63416, 314.01935],
                     [201.26117, 371.41043], [313.08905, 371.15118]], np.float32)


def available() -> bool:
    return all((MODELS / f).exists() for f in ("RealESRGAN_x2plus.pth", "RealESRGAN_x4plus.pth", "GFPGANv1.4.pth"))


def _dev() -> str:
    import torch
    return os.environ.get("GESICHT_HD_DEVICE") or ("cuda" if torch.cuda.is_available() else "cpu")


_M = {}


def model(name):
    if name not in _M:
        import spandrel
        import torch
        m = spandrel.ModelLoader().load_from_file(str(MODELS / f"{name}.pth")).to(_dev()).eval()
        if _dev() == "cuda" and name.startswith("RealESRGAN"):
            m = m.to(torch.float16)
        _M[name] = m
    return _M[name]


def free():
    _M.clear()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


def esrgan(rgb: np.ndarray, scale: int, tile: int = 384, pad: int = 16) -> np.ndarray:
    """Real-ESRGAN x2/x4plus gekachelt (uint8 HxWx3 -> uint8)."""
    import torch
    dev = _dev()
    m = model(f"RealESRGAN_x{scale}plus")
    dt = torch.float16 if dev == "cuda" else torch.float32
    t = torch.from_numpy(np.ascontiguousarray(rgb)).to(dev).permute(2, 0, 1)[None].to(dt) / 255
    H, W = rgb.shape[:2]
    out = torch.zeros(1, 3, H * scale, W * scale, device=dev, dtype=dt)
    for y in range(0, H, tile):
        for x in range(0, W, tile):
            y0, x0, y1, x1 = max(0, y - pad), max(0, x - pad), min(H, y + tile + pad), min(W, x + tile + pad)
            with torch.inference_mode():
                o = m(t[:, :, y0:y1, x0:x1])
            h, w = (min(y + tile, H) - y) * scale, (min(x + tile, W) - x) * scale
            oy, ox = (y - y0) * scale, (x - x0) * scale
            out[:, :, y * scale:y * scale + h, x * scale:x * scale + w] = o[:, :, oy:oy + h, ox:ox + w]
    return (out[0].float().clamp(0, 1) * 255 + 0.5).byte().permute(1, 2, 0).cpu().numpy()


_FA = None


def kps_of(rgb: np.ndarray):
    """5 Gesichtspunkte (insightface buffalo_l, CPU) des groessten Gesichts oder None."""
    global _FA
    if _FA is None:
        from insightface.app import FaceAnalysis
        _FA = FaceAnalysis(allowed_modules=["detection"], root=str(DET_ROOT), providers=["CPUExecutionProvider"])
        _FA.prepare(ctx_id=-1, det_size=(640, 640))
    # enge Gesichtsfenster (Gesicht fuellt das Bild) findet der Detektor nicht -> grauen Rand anfuegen
    pad = max(rgb.shape[:2]) // 2
    big = cv2.copyMakeBorder(np.ascontiguousarray(rgb[..., ::-1]), pad, pad, pad, pad, cv2.BORDER_CONSTANT,
                             value=(128, 128, 128))
    fs = _FA.get(big)
    if not fs:
        return None
    f = max(fs, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
    return f.kps.astype(np.float32) - pad


def smooth_kps(seq: list) -> list:
    """Luecken interpolieren, zeitlich glaetten (Gauss sigma 2 Bilder) -> kein GFPGAN-Flackern durch Punktzittern."""
    ok = [i for i, k in enumerate(seq) if k is not None]
    if not ok:
        return seq
    arr = np.stack([seq[i] for i in ok]).reshape(len(ok), -1)
    idx = np.arange(len(seq))
    full = np.stack([np.interp(idx, ok, arr[:, j]) for j in range(arr.shape[1])], 1)
    kern = np.exp(-0.5 * (np.arange(-6, 7) / 2.0) ** 2)
    kern /= kern.sum()
    pad = np.pad(full, ((6, 6), (0, 0)), mode="edge")
    sm = np.stack([np.convolve(pad[:, j], kern, mode="valid") for j in range(full.shape[1])], 1)
    return [s.reshape(5, 2).astype(np.float32) for s in sm]


_MASK = None


def gfpgan(rgb: np.ndarray, kps: np.ndarray, weight: float) -> np.ndarray:
    """GFPGAN 1.4 auf dem nach FFHQ ausgerichteten 512er-Gesicht, nur untere Gesichtshaelfte, Anteil `weight`."""
    import torch
    global _MASK
    M = cv2.estimateAffinePartial2D(kps, FFHQ_512, method=cv2.LMEDS)[0]
    crop = cv2.warpAffine(rgb, M, (512, 512), flags=cv2.INTER_AREA if M[0, 0] < 1 else cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_REFLECT)
    t = torch.from_numpy(crop).to(_dev()).permute(2, 0, 1)[None].float() / 255
    with torch.inference_mode():
        o = model("GFPGANv1.4")(t)
    o = o[0] if isinstance(o, (tuple, list)) else o
    res = (o[0].clamp(0, 1) * 255 + 0.5).byte().permute(1, 2, 0).cpu().numpy()
    if _MASK is None:
        _MASK = np.zeros((512, 512), np.float32)
        _MASK[285:-40, 70:-70] = 1                       # Augen (y=240) bleiben Original
        _MASK = cv2.GaussianBlur(_MASK, (0, 0), 14)
    H, W = rgb.shape[:2]
    Mi = cv2.invertAffineTransform(M)
    back = cv2.warpAffine(res, Mi, (W, H), flags=cv2.INTER_LANCZOS4)
    mb = cv2.warpAffine(_MASK, Mi, (W, H))[..., None] * weight
    return np.clip(rgb * (1 - mb) + back * mb + 0.5, 0, 255).astype(np.uint8)


def restore(frames: list, weight: float) -> list:
    """GFPGAN mit geglaetteten Gesichtspunkten auf einer Bildfolge (Bilder ohne Gesicht bleiben)."""
    kp = smooth_kps([kps_of(f) for f in frames])
    return [gfpgan(f, k, weight) if k is not None else f for f, k in zip(frames, kp)]


def zoom_window(ffmpeg: str, src: Path, a: int, b: int, x: int, y: int, s: int, size: int, out: Path, fps: int) -> Path:
    """Bilder [a, b) von src im Fenster (x, y, s): Real-ESRGAN -> size x size, GFPGAN (GFP_IN) -> H.264 crf 10."""
    p = subprocess.run([ffmpeg, "-v", "error", "-i", str(src), "-vf",
                        f"trim=start_frame={a}:end_frame={b},setpts=PTS-STARTPTS,crop={s}:{s}:{x}:{y}",
                        "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True)
    frames = np.frombuffer(p.stdout, np.uint8).reshape(-1, s, s, 3)
    sc = 4 if s * 2 < size else 2
    ups = [cv2.resize(esrgan(f, sc), (size, size), interpolation=cv2.INTER_AREA) for f in frames]
    ups = restore(ups, GFP_IN)
    free()
    ff = subprocess.Popen([ffmpeg, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{size}x{size}",
                           "-r", str(fps), "-i", "-", "-an", "-c:v", "libx264", "-crf", "10", "-pix_fmt", "yuv420p",
                           str(out)], stdin=subprocess.PIPE)
    for u in ups:
        ff.stdin.write(u.tobytes())
    ff.stdin.close()
    if ff.wait():
        raise RuntimeError(f"Gesichtsfenster schreiben fehlgeschlagen ({out})")
    return out


def still(src: Path, out_dir: Path, scales=(2, 4)) -> dict:
    """Freisteller-Standbild (RGBA-PNG) hochskalieren: Farbe Real-ESRGAN + GFPGAN (untere Gesichtshaelfte), Alpha
    separat mit Real-ESRGAN (Kanten bleiben). Liefert Auflösungen, Augenabstand/Mundbreite in Pixeln, Dateien."""
    im = cv2.imread(str(src), cv2.IMREAD_UNCHANGED)
    rgb, a = np.ascontiguousarray(im[..., 2::-1]), im[..., 3]
    af = a[..., None] / 255
    k0 = kps_of(np.clip(rgb * af + 128 * (1 - af), 0, 255).astype(np.uint8))
    info = dict(quelle=str(src), w=im.shape[1], h=im.shape[0],
                augenabstand_px=round(float(np.linalg.norm(k0[1] - k0[0])), 1) if k0 is not None else None,
                mundbreite_px=round(float(np.linalg.norm(k0[4] - k0[3])), 1) if k0 is not None else None)
    out_dir.mkdir(parents=True, exist_ok=True)
    for s in scales:
        up = esrgan(rgb, s)
        aup = esrgan(np.repeat(a[..., None], 3, 2), s).mean(2).round().astype(np.uint8)
        fin = gfpgan(up, k0 * s, GFP_IN) if k0 is not None else up
        p = out_dir / f"{src.stem}_x{s}_esrgan_gfpgan.png"
        cv2.imwrite(str(p), np.dstack([fin[..., ::-1], aup]))
        info[f"x{s}"] = dict(datei=str(p), w=fin.shape[1], h=fin.shape[0])
    free()
    return info
