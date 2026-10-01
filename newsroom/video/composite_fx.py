"""Realistischeres Studio-Compositing der stehenden Moderatorin-Pose: Kontaktschatten unter den Schuhen (je Schuh an
seiner eigenen Unterkante), kurzer Schlagschatten nach hinten, Spiegelung im glaenzenden Boden, kuehleres
Studiolicht (Schatten leicht blau, Waerme -3 %, Schwarzwert an den Hintergrund angeglichen), Randlicht/Light-Wrap
von der LED-Wand und leichte Koernung. Probe: Task 20261001-165559-5e26 (reports/weltlage_latara_echtheit_20261001/
proben_code/composite.py), Marlons Wahl und Standard seit Task 20261001-180145-c47f.

Nur die stehende Pose (bei der Sitz-Pose verdeckt das Pult die Fuesse, siehe Bericht 5e26). Aufgerufen von
video/freisteller_lipsync.composite_studio, wenn config.settings.NEWS_WELTLAGE_COMPOSITE_FX an ist (Default an).
Reine Bildfunktionen, numpy/OpenCV, kein eigener Prozess/GPU-Bedarf.
"""
import cv2
import numpy as np

SHADOW_COL = np.array([0.04, 0.03, 0.01], np.float32)     # dunkles Marineblau statt Schwarz
REFL_OPAC, REFL_LEN = 0.5, 320                             # Bodenspiegelung (glaenzender Boden)
CAST_SQUASH, CAST_SHEAR, CAST_OPAC = 0.20, 0.35, 0.55
CONTACT_OPAC = 0.9
RIM_COL = np.array([1.0, 0.62, 0.30], np.float32)          # BGR kaltes Blau-Cyan der LED-Wand
RIM_GAIN, WRAP = 0.30, 0.18
GRAIN = 2.2 / 255


def load_bg(path, W: int, H: int, bg_size: tuple[int, int]) -> np.ndarray:
    """Hintergrund fuellend auf WxH skaliert und mittig beschnitten (wie studio_filter), float BGR 0..1."""
    bw, bh = bg_size
    k = max(W / bw, H / bh)
    sw, sh = round(bw * k / 2) * 2, round(bh * k / 2) * 2
    ox, oy = (sw - W) // 2, (sh - H) // 2
    bg = cv2.imread(str(path), cv2.IMREAD_COLOR)
    bg = cv2.resize(bg, (sw, sh), interpolation=cv2.INTER_LANCZOS4)[oy:oy + H, ox:ox + W]
    return bg.astype(np.float32) / 255


def placement_box(p: dict, src_wh: tuple[int, int], W: int, H: int, bg_size: tuple[int, int]) -> tuple[int, int, int, int]:
    """(mx, my, mw, mh) in Leinwand-Pixeln aus der Platzierung (x, y, scale), wie studio_filter/composite.py."""
    sw, sh = src_wh
    bw, bh = bg_size
    k = max(W / bw, H / bh)
    sw2, sh2 = round(bw * k / 2) * 2, round(bh * k / 2) * 2
    ox, oy = (sw2 - W) // 2, (sh2 - H) // 2
    mw = max(2, round(sw * p["scale"] * k / 2) * 2)
    mh = max(2, round(sh * p["scale"] * k / 2) * 2)
    mx = round(p["x"] * k) - ox
    my = round(p["y"] * k) - oy
    return mx, my, mw, mh


def _place(fg_rgba, mx, my, mw, mh, W, H):
    fg = cv2.resize(fg_rgba, (mw, mh), interpolation=cv2.INTER_LANCZOS4).astype(np.float32) / 255
    rgb = np.zeros((H, W, 3), np.float32)
    a = np.zeros((H, W), np.float32)
    x0, y0 = max(mx, 0), max(my, 0)
    x1, y1 = min(mx + mw, W), min(my + mh, H)
    if x1 > x0 and y1 > y0:
        rgb[y0:y1, x0:x1] = fg[y0 - my:y1 - my, x0 - mx:x1 - mx, :3][..., ::-1]   # RGBA -> BGR
        a[y0:y1, x0:x1] = fg[y0 - my:y1 - my, x0 - mx:x1 - mx, 3]
    return rgb, a


def _feet_line(a, mh, W):
    """Bodenlinie L(x): Unterkante jedes Schuhs (eigene zusammenhaengende Komponente), linear dazwischen."""
    ys, xs = np.nonzero(a > 0.5)
    if len(ys) == 0:
        return np.full(W, float(a.shape[0]), np.float32), []
    bottom = ys.max()
    band = np.zeros_like(a, np.uint8)
    top = int(max(0, bottom - 0.07 * mh))
    band[top:bottom + 1] = (a[top:bottom + 1] > 0.5)
    n, lab, st, _ = cv2.connectedComponentsWithStats(band)
    shoes = []
    for i in range(1, n):
        if st[i, cv2.CC_STAT_AREA] < 40:
            continue
        yy, xx = np.nonzero(lab == i)
        shoes.append((int(xx.min()), int(xx.max()), int(yy.max())))
    shoes.sort()
    x = np.arange(W, dtype=np.float32)
    if not shoes:
        return np.full(W, float(bottom), np.float32), []
    kx = [((s0 + s1) / 2) for s0, s1, _ in shoes]
    ky = [b for _, _, b in shoes]
    L = np.interp(x, kx, ky).astype(np.float32)
    return L, shoes


def _grade(rgb, a, bg, mx, my, mw, mh, W, H):
    """Figur an das Studiolicht angleichen: kuehle Schatten, etwas weniger Waerme, Schwarzwert an den Hintergrund."""
    m = a > 0.9
    lum = rgb @ np.array([0.114, 0.587, 0.299], np.float32)
    sh = np.clip(1 - lum / 0.55, 0, 1)[..., None]
    rgb = rgb + sh * np.array([0.018, 0.006, -0.008], np.float32)
    rgb = rgb * np.array([1.03, 1.0, 0.97], np.float32)
    g = (rgb @ np.array([0.114, 0.587, 0.299], np.float32))[..., None]
    rgb = g + (rgb - g) * 0.94
    x0, y0 = max(mx, 0), max(my, 0)
    x1, y1 = min(mx + mw, W), min(my + mh, H)
    if x1 > x0 and y1 > y0 and m.any():
        bg_dark = np.percentile(bg[y0:y1, x0:x1], 2, axis=(0, 1))
        fg_dark = np.percentile(rgb[m], 2, axis=0)
        lift = np.clip(bg_dark - fg_dark, 0, 0.05) * 0.25
        rgb = rgb + lift * (1 - np.clip(rgb, 0, 1))
    return np.clip(rgb, 0, 1)


def _soft_alpha(a):
    a = cv2.erode(a, np.ones((2, 2), np.uint8))
    return cv2.GaussianBlur(a, (0, 0), 0.8)


def _rim_and_wrap(rgb, a, bg, my, mh, H):
    """Randlicht von der LED-Wand + Light-Wrap (Hintergrund blutet leicht in die Kante)."""
    inner = cv2.erode(a, np.ones((9, 9), np.uint8))
    edge = np.clip(a - inner, 0, 1)
    edge = cv2.GaussianBlur(edge, (0, 0), 3) * a
    yy = (np.arange(H, dtype=np.float32)[:, None] - my) / max(mh, 1)
    upper = np.clip(1.15 - yy * 1.1, 0, 1)
    rgb = rgb + (edge * upper * RIM_GAIN)[..., None] * RIM_COL
    bgb = cv2.GaussianBlur(bg, (0, 0), 14)
    wrap = (edge * WRAP)[..., None]
    rgb = rgb * (1 - wrap) + bgb * wrap
    return np.clip(rgb, 0, 1)


def _remap(img, mx, my):
    return cv2.remap(img, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)


def _ground_fx(out, rgb, a, L, feet, W, H):
    xs = np.arange(W, dtype=np.float32)[None, :].repeat(H, 0)
    ys = np.arange(H, dtype=np.float32)[:, None].repeat(W, 1)
    Lm = L[None, :].repeat(H, 0)
    d = Lm - ys
    below = ys > Lm
    sy = np.where(below, 2 * Lm - ys, -1).astype(np.float32)
    ra = _remap(a, xs, sy)
    rr = _remap(rgb, xs, sy)
    fade = np.clip(1 - (ys - Lm) / REFL_LEN, 0, 1) ** 1.6 * below
    ra = cv2.blur(ra * fade, (3, 9))
    rr = cv2.blur(rr, (3, 9))
    floor = cv2.GaussianBlur(out, (0, 0), 6)
    refl = rr * 0.75 + floor * 0.25
    o = (ra * REFL_OPAC)[..., None]
    out = out * (1 - o) + refl * o
    above = d > 0
    sy2 = np.where(above, Lm - d / CAST_SQUASH, -1).astype(np.float32)
    sx2 = (xs - CAST_SHEAR * d).astype(np.float32)
    ca = _remap(a, sx2, sy2) * above
    dist = np.clip(d / 70, 0, 1)
    c1 = cv2.GaussianBlur(ca, (0, 0), 2.5)
    c2 = cv2.GaussianBlur(ca, (0, 0), 12)
    cast = (c1 * (1 - dist) + c2 * dist) * (1 - dist * 0.75) * CAST_OPAC
    cont = np.zeros((H, W), np.float32)
    for x0, x1, bottom in feet:
        cv2.ellipse(cont, (int((x0 + x1) / 2), int(bottom) - 2), (int((x1 - x0) * 0.6) + 4, 7), 0, 0, 360, 1.0, -1)
    cont = cv2.GaussianBlur(cont, (0, 0), 6) * 0.85
    sy3 = np.where(np.abs(d) < 14, Lm - d / 0.08, -1).astype(np.float32)
    shoe = cv2.GaussianBlur(_remap(a, xs, sy3) * (np.abs(d) < 14), (0, 0), 3.5)
    contact = np.clip(cont + shoe * 0.8, 0, 1) * CONTACT_OPAC
    sh = np.clip(np.maximum(cast, contact), 0, 0.9)[..., None]
    return out, sh


def compose(fg_rgba: np.ndarray, bg: np.ndarray, mx: int, my: int, mw: int, mh: int, seed: int = 0) -> np.ndarray:
    """Ein Bild: Freisteller (RGBA) auf den Hintergrund (float BGR, 0..1) compositen. Liefert uint8 BGR."""
    H, W = bg.shape[:2]
    rgb, a = _place(fg_rgba, mx, my, mw, mh, W, H)
    L, feet = _feet_line(a, mh, W)
    rgb = _grade(rgb, a, bg, mx, my, mw, mh, W, H)
    a2 = _soft_alpha(a)
    rgb = _rim_and_wrap(rgb, a2, bg, my, mh, H)
    out, sh = _ground_fx(bg.copy(), rgb, a, L, feet, W, H)
    out = out * (1 - sh) + SHADOW_COL * sh
    out = rgb * a2[..., None] + out * (1 - a2[..., None])
    rng = np.random.default_rng(seed)
    n = rng.normal(0, GRAIN, (H, W, 1)).astype(np.float32)
    n = cv2.GaussianBlur(n, (0, 0), 0.6)[..., None] * 1.6
    out = np.clip(out + n, 0, 1)
    return (out * 255 + 0.5).astype(np.uint8)
