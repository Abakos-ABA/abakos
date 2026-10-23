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
try:              # Real-ESRGAN im Gesichtsfenster an/aus (Standard aus seit 23.10.2026, Variante C), config/settings.py
    from config.settings import NEWS_WELTLAGE_LIPSYNC_ESRGAN as ESRGAN
except Exception:
    ESRGAN = False
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
    return esrgan_many([rgb], scale, tile, pad, batch=1)[0]


def esrgan_many(frames: list, scale: int, tile: int = 384, pad: int = 16, batch: int = 1) -> list:
    """Wie esrgan(), aber fuer mehrere gleich grosse Bilder: `batch` davon zusammen in einer Stapel-Dimension durchs
    Netz (gleiche Gewichte, gleiche Kachel-Aufteilung, rechnerisch dasselbe wie batch=1 je Bild einzeln - siehe
    tests/test_gesicht_hd_batch.py). batch=1 ist exakt der alte Weg (Liste mit einem Bild pro Aufruf), nur ohne die
    doppelte Funktionsdefinition. Grund fuer das Buendeln (Task 20261010-081311-ca9f): bei einem 768-px-Fenster
    ueberwiegt auf der RTX 4090 der Python-/CUDA-Startaufwand pro Aufruf die eigentliche Rechenzeit."""
    import torch
    dev = _dev()
    m = model(f"RealESRGAN_x{scale}plus")
    dt = torch.float16 if dev == "cuda" else torch.float32
    H, W = frames[0].shape[:2]
    outs = [None] * len(frames)
    step = max(1, batch)
    for i0 in range(0, len(frames), step):
        grp = frames[i0:i0 + step]
        t = torch.stack([torch.from_numpy(np.ascontiguousarray(f)) for f in grp]).to(dev).permute(0, 3, 1, 2).to(dt) / 255
        out = torch.zeros(len(grp), 3, H * scale, W * scale, device=dev, dtype=dt)
        for y in range(0, H, tile):
            for x in range(0, W, tile):
                y0, x0, y1, x1 = max(0, y - pad), max(0, x - pad), min(H, y + tile + pad), min(W, x + tile + pad)
                with torch.inference_mode():
                    o = m(t[:, :, y0:y1, x0:x1])
                h, w = (min(y + tile, H) - y) * scale, (min(x + tile, W) - x) * scale
                oy, ox = (y - y0) * scale, (x - x0) * scale
                out[:, :, y * scale:y * scale + h, x * scale:x * scale + w] = o[:, :, oy:oy + h, ox:ox + w]
        res = (out.float().clamp(0, 1) * 255 + 0.5).byte().permute(0, 2, 3, 1).cpu().numpy()
        for j in range(len(grp)):
            outs[i0 + j] = res[j]
    return outs


_FA = None


def kps_of(rgb: np.ndarray):
    """5 Gesichtspunkte (insightface buffalo_l, CPU) des groessten Gesichts oder None."""
    global _FA
    from video.lipsync_detektoren import gewaehlt
    if gewaehlt() != "insightface":
        return _kps_mediapipe(rgb)           # kommerziell frei (Apache 2.0), siehe video/lipsync_detektoren.py
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


_MP = None
_MP_EYE_L, _MP_EYE_R = [33, 133, 159, 145], [362, 263, 386, 374]


def _kps_mediapipe(rgb: np.ndarray):
    """Wie kps_of(), aber mit MediaPipe Face Mesh statt InsightFace buffalo_l (nur nicht-kommerziell erlaubt)."""
    global _MP
    if _MP is None:
        import mediapipe as mp
        _MP = mp.solutions.face_mesh.FaceMesh(static_image_mode=True, max_num_faces=2, min_detection_confidence=0.5)
    pad = max(rgb.shape[:2]) // 2
    big = cv2.copyMakeBorder(np.ascontiguousarray(rgb), pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=(128, 128, 128))
    h, w = big.shape[:2]
    res = _MP.process(big)
    if not res.multi_face_landmarks:
        return None
    best, area = None, -1
    for fl in res.multi_face_landmarks:
        pts = np.array([(p.x * w, p.y * h) for p in fl.landmark], np.float32)
        a = float(np.ptp(pts[:, 0]) * np.ptp(pts[:, 1]))
        if a > area:
            best, area = pts, a
    k = np.stack([best[_MP_EYE_L].mean(0), best[_MP_EYE_R].mean(0), best[1], best[61], best[291]])
    return k.astype(np.float32) - pad


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
    return gfpgan_many([rgb], [kps], weight, batch=1)[0]


def _gfpgan_align(rgb: np.ndarray, kps: np.ndarray):
    """CPU-Teil von gfpgan(): Ausrichtung aufs 512er FFHQ-Raster. Guenstig genug, um pro Bild einzeln zu bleiben."""
    M = cv2.estimateAffinePartial2D(kps, FFHQ_512, method=cv2.LMEDS)[0]
    crop = cv2.warpAffine(rgb, M, (512, 512), flags=cv2.INTER_AREA if M[0, 0] < 1 else cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_REFLECT)
    return crop, M


def gfpgan_many(frames: list, kps_list: list, weight: float, batch: int = 1) -> list:
    """Wie gfpgan(), aber fuer mehrere Bilder: Ausrichtung/Rueckwarpen bleiben pro Bild (CPU, billig), nur der
    GFPGAN-Netzdurchlauf laeuft fuer bis zu `batch` Bilder gleichzeitig (gleiche Gewichte, rechnerisch dasselbe wie
    batch=1 je Bild - siehe tests/test_gesicht_hd_batch.py). Bilder ohne Gesichtspunkte (kps None) bleiben
    unveraendert. batch=1 ist exakt der alte Weg."""
    import torch
    global _MASK
    if _MASK is None:
        _MASK = np.zeros((512, 512), np.float32)
        _MASK[285:-40, 70:-70] = 1                       # Augen (y=240) bleiben Original
        _MASK = cv2.GaussianBlur(_MASK, (0, 0), 14)
    idx = [i for i, k in enumerate(kps_list) if k is not None]
    outs = list(frames)
    if not idx:
        return outs
    aligned = [_gfpgan_align(frames[i], kps_list[i]) for i in idx]
    dev = _dev()
    step = max(1, batch)
    for b0 in range(0, len(aligned), step):
        grp = aligned[b0:b0 + step]
        # contiguous(): die CPU-Umsetzung von GFPGAN (spandrel) verlangt ein zusammenhaengendes Tensor-Layout fuer
        # ihr internes view() bei Stapelgroesse > 1 - auf der GPU (Produktionsweg) war das nie noetig, schadet dort
        # aber auch nicht (no-op, wenn schon zusammenhaengend).
        t = torch.stack([torch.from_numpy(crop) for crop, _ in grp]).to(dev).permute(0, 3, 1, 2).contiguous().float() / 255
        with torch.inference_mode():
            o = model("GFPGANv1.4")(t)
        o = o[0] if isinstance(o, (tuple, list)) else o
        res = (o.clamp(0, 1) * 255 + 0.5).byte().permute(0, 2, 3, 1).cpu().numpy()
        for j, (crop, M) in enumerate(grp):
            i = idx[b0 + j]
            outs[i] = _gfpgan_blend(frames[i], M, res[j], weight)
    return outs


def _gfpgan_blend(rgb: np.ndarray, M: np.ndarray, res: np.ndarray, weight: float) -> np.ndarray:
    H, W = rgb.shape[:2]
    Mi = cv2.invertAffineTransform(M)
    back = cv2.warpAffine(res, Mi, (W, H), flags=cv2.INTER_LANCZOS4)
    mb = cv2.warpAffine(_MASK, Mi, (W, H))[..., None] * weight
    return np.clip(rgb * (1 - mb) + back * mb + 0.5, 0, 255).astype(np.uint8)


def restore(frames: list, weight: float, batch: int = 1) -> list:
    """GFPGAN mit geglaetteten Gesichtspunkten auf einer Bildfolge (Bilder ohne Gesicht bleiben). batch > 1 buendelt
    den Netzdurchlauf (gesicht_hd.gfpgan_many), rechnerisch dasselbe wie batch=1."""
    kp = smooth_kps([kps_of(f) for f in frames])
    return gfpgan_many(frames, kp, weight, batch=batch)


def zoom_window(ffmpeg: str, src: Path, a: int, b: int, x: int, y: int, s: int, size: int, out: Path, fps: int,
                batch: int = 1) -> Path:
    """Bilder [a, b) von src im Fenster (x, y, s): Real-ESRGAN -> size x size, GFPGAN (GFP_IN) -> H.264 crf 10."""
    p = subprocess.run([ffmpeg, "-v", "error", "-i", str(src), "-vf",
                        f"trim=start_frame={a}:end_frame={b},setpts=PTS-STARTPTS,crop={s}:{s}:{x}:{y}",
                        "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True)
    frames = np.frombuffer(p.stdout, np.uint8).reshape(-1, s, s, 3)
    sc = 4 if s * 2 < size else 2
    if ESRGAN:
        grossed = esrgan_many(list(frames), sc, batch=batch)
    else:                                       # Variante C: Lanczos statt Real-ESRGAN, GFPGAN danach wie gehabt
        grossed = [cv2.resize(f, (f.shape[1] * sc, f.shape[0] * sc), interpolation=cv2.INTER_LANCZOS4) for f in frames]
    ups = [cv2.resize(f, (size, size), interpolation=cv2.INTER_AREA) for f in grossed]
    ups = restore(ups, GFP_IN, batch=batch)
    free()
    # preset veryfast statt dem x264-Standard "medium": nur ein Zwischenstueck fuer LatentSync (wird sofort wieder
    # decodiert), crf bleibt gleich -> gleiche Zielqualitaet, nur die Suche nach der effizientesten Kompression ist
    # kuerzer (Task 20261007-150054-1995, Laufzeit-Hebel)
    ff = subprocess.Popen([ffmpeg, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{size}x{size}",
                           "-r", str(fps), "-i", "-", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "10",
                           "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE)
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
