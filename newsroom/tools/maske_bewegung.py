"""Masken-Moderator: natuerlichere Bewegung OHNE Lipsync und mit starrem Maskenmund (Task 20261030-021050-1036).

Drei Ansaetze, alle nur CPU (cv2/numpy/ffmpeg), Quelle = Masken-Standbild + Freisteller host_alpha.png
(tools/maske_matte_still.py, BiRefNet-matting MIT):
  atem      Standbild, Kopf als Starrkoerper (nie verformt) + Brust/Schultern atmen. Alles aus der Audio-Huellkurve:
            Nicken bei Betonung, Kopf beruhigt sich in Pausen, Luft holen vor dem Satzanfang, weiches Rauschen statt
            Sinus, kaum merkliches Lichtflackern.
  parallax  wie atem + sehr langsame Kamerafahrt mit zwei Ebenen (Person naeher als Hintergrund, Hintergrund frisch
            aus dem Standbild ergaenzt) -> Tiefenwirkung statt flachem Bild.
  wan       Koerper/Schultern aus dem Wan-Loop (organische Bewegung), der Kopf aber das Standbild, per ECC der
            Kapuzenkontur des Loops nachgefuehrt (starr) -> Wan zeichnet Gesicht/Lippen nie.
  rede      (07.11.2026, Marlon: «Animation schlecht, Loop-Spruenge»): keine Clips, keine Schleife, also auch kein
            Rueckspringen auf ein Ankerbild. Kopf als Starrkoerper an einer gedaempften Feder: je Sprechphrase eine
            neue Kopfhaltung (Blick/Neigung), Nicker an Betonungen mit Nachschwingen, Kopf sinkt am Satzende leicht,
            Oberkoerper folgt verzoegert (Lehnen, Schultern heben sich vor dem Einatmen und bei starken Betonungen),
            langsame Kamera mit Tiefenebenen. Maske und Mund bleiben das Standbild (kein Lipsync).
Schalter in weltlage_maskenformat.host_spur: NEWS_MASKEN_ANIM=atem|parallax|wan|rede (Standard leer = alt).

    python tools/maske_bewegung.py probe --modus atem --ton ton.wav --ende 25 --out probe.mp4
"""
import argparse
import math
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
MASKE = ROOT / "config" / "brand" / "maskenmoderator"
W, H, FPS = 1920, 1080, 25
PIVOT = (965.0, 560.0)            # Halsansatz
KOPF_M = (960, 270)               # Kopf-Ellipse (Kapuze + Gesicht), wie in host_spur
KOPF_R = (300, 290)
MASKE_STARR = ((955, 395), (200, 185))   # Maske samt Kinn im Standbild host_7b (1920x1080)
MIKRO_KOPF = ((1175, 600), 125)   # Mikrofon im Standbild host_7b (1920x1080), gemessen 07.11.2026
MIKRO_LINIEN = [((1175, 600), (1380, 800), 130), ((1360, 680), (1920, 800), 45), ((1245, 720), (1245, 1080), 45)]
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def _ffmpeg():
    sys.path.insert(0, str(ROOT / "tools"))
    import weltlage_maskenformat as m
    return m.FFMPEG, m.ton_huellkurve


def rauschen(n: int, seed: int, freqs=(0.071, 0.113, 0.187, 0.29)) -> np.ndarray:
    """Weiches, nie periodisch wirkendes Rauschen -1..1 (Summe inkommensurabler Sinus-Teile, FPS-Takt)."""
    rng = np.random.RandomState(seed)
    t = np.arange(n) / FPS
    y = sum(math.pow(0.7, k) * np.sin(2 * math.pi * f * t * rng.uniform(0.9, 1.1) + rng.uniform(0, 6.28))
            for k, f in enumerate(freqs))
    return (y / np.abs(y).max()).astype(np.float32)


def _glatt(x: np.ndarray, sek: float) -> np.ndarray:
    k = max(1, int(sek * FPS))
    return np.convolve(np.pad(x, (k, k), mode="edge"), np.ones(k) / k, "same")[k:-k]


def steuerung(hk: np.ndarray, n: int, seed: int) -> dict:
    """Aus Huellkurve (env, acc) und Rauschen die Bewegungskurven je Bild."""
    env, acc = hk[:n, 0], hk[:n, 1]
    sprech = _glatt(env, 0.35)
    sprech = np.clip(sprech / 0.45, 0, 1)                          # ~1 beim Sprechen, 0 in Pausen
    # Luft holen: kurz vor dem Wiedereinsatz nach einer Pause > 0.45 s
    atem_ev = np.zeros(n, np.float32)
    still = sprech < 0.12
    i = 0
    while i < n:
        if still[i]:
            j = i
            while j < n and still[j]:
                j += 1
            if j - i > int(0.45 * FPS) and j < n:
                c = j - int(0.2 * FPS)
                x = np.arange(n)
                atem_ev += np.exp(-0.5 * ((x - c) / (0.22 * FPS)) ** 2)
            i = j
        else:
            i += 1
    atem_ev = np.clip(atem_ev, 0, 1)
    ruhig = 0.55 + 0.45 * sprech                                   # in Pausen ruhiger, aber nie eingefroren
    t = np.arange(n) / FPS
    atem = 0.5 + 0.5 * np.sin(2 * math.pi * 0.26 * t + 0.4 * rauschen(n, seed + 9, (0.05, 0.09)))
    # Satzphrasen: Kopf-Grundlage wechselt langsam (Blickrichtung / Neigung), weich
    return dict(
        nick=acc,                                                  # Betonung -> Kopf nickt nach unten
        roll=(0.38 * rauschen(n, seed + 1) * ruhig + 0.35 * acc * rauschen(n, seed + 2, (0.9, 1.3))),   # Grad
        dx=(3.2 * rauschen(n, seed + 3) + 1.5 * acc * rauschen(n, seed + 4, (0.6, 0.9))) * ruhig,
        dy=(1.6 * rauschen(n, seed + 5)) * ruhig + 5.0 * acc - 2.5 * atem_ev,
        atem=np.clip(0.55 * atem + 0.45 * _glatt(env, 0.5) + 0.9 * atem_ev, 0, 1.6),
        licht=0.03 * rauschen(n, seed + 6, (0.05, 0.13, 0.31)),
        cam=np.stack([4.5 * rauschen(n, seed + 7, (0.04, 0.083)), 2.5 * rauschen(n, seed + 8, (0.05, 0.097)),
                      0.011 * rauschen(n, seed + 10, (0.025, 0.06))], 1),
    )


class Ebenen:
    """Standbild, Alpha, Hintergrund ohne Person (Vorberechnung), Gitter, Gewichtskarten."""

    def __init__(self):
        still = ROOT / "_work" / "maske_anim" / "still_1080.png"
        if not still.exists() and (MASKE / "host_7b_3344.png").exists():   # wie tools/maske_matte_still.py, ohne GPU
            still.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(still), cv2.resize(cv2.imread(str(MASKE / "host_7b_3344.png")), (W, H),
                                               interpolation=cv2.INTER_AREA))
        img = cv2.imread(str(still))
        if img is None:
            raise RuntimeError("still_1080.png fehlt: tools/maske_matte_still.py ueber gpu_queue ausfuehren")
        a = cv2.imread(str(MASKE / "host_alpha.png"), -1).astype(np.float32) / 65535
        self.img = img.astype(np.float32)
        self.a = a
        sm = cv2.resize(img, (480, 270), interpolation=cv2.INTER_AREA)
        loch = cv2.dilate((cv2.resize(a, (480, 270)) > 0.04).astype(np.uint8) * 255, np.ones((7, 7), np.uint8))
        bg = cv2.inpaint(sm, loch, 9, cv2.INPAINT_TELEA)
        bgb = cv2.resize(bg, (W, H), interpolation=cv2.INTER_CUBIC).astype(np.float32)
        hart = cv2.GaussianBlur(cv2.dilate((a > 0.04).astype(np.uint8), np.ones((9, 9), np.uint8)).astype(np.float32), (0, 0), 3)[..., None]
        self.bg = self.img * (1 - hart) + bgb * hart            # ausserhalb der Person Originalpixel
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        self.xx, self.yy = xx, yy
        k = np.zeros((H, W), np.float32)
        cv2.ellipse(k, KOPF_M, KOPF_R, 0, 0, 360, 1, -1)
        self.wkopf = cv2.GaussianBlur(k, (0, 0), 45)
        self.wbrust = np.clip((1000 - yy) / 440, 0, 1) ** 1.3    # Brust hebt sich, Tischkante unten bleibt
        self.wbrust *= np.clip((a > 0.5).astype(np.float32), 0, 1)
        self.wbrust = cv2.GaussianBlur(self.wbrust, (0, 0), 25)
        lk = np.clip(1 - xx / 900, 0, 1) * np.clip(1 - np.abs(yy - 450) / 450, 0, 1)
        self.licht_w = lk[..., None]
        mic = np.zeros((H, W), np.uint8)
        for a_, b_, d_ in MIKRO_LINIEN:
            cv2.line(mic, a_, b_, 255, d_)
        cv2.circle(mic, MIKRO_KOPF[0], MIKRO_KOPF[1], 255, -1)
        self.starr = 1 - cv2.GaussianBlur(mic.astype(np.float32) / 255, (0, 0), 6)
        # Modus rede: die ganze Maske bis unters Kinn voll starr (Gewicht 1), sonst schert der Uebergang zur Brust den
        # Mund (Wache maske_mund 07.11.2026: mund_rest 1,9 bei Gewicht 0,97 am Mund / 0,79 am Kinn); Mikrofon steht.
        starr_m = np.zeros((H, W), np.float32)
        cv2.ellipse(starr_m, MASKE_STARR[0], MASKE_STARR[1], 0, 0, 360, 1, -1)
        self.wkopf_r = np.maximum(self.wkopf, cv2.GaussianBlur(starr_m, (0, 0), 10)) * self.starr
        self.wbrust_r = self.wbrust * self.starr


def _kopf_matrix(roll_deg, dx, dy, scale=1.0):
    M = cv2.getRotationMatrix2D(PIVOT, roll_deg, scale)
    M[0, 2] += dx
    M[1, 2] += dy
    return M


def _remap(img, mx, my):
    return cv2.remap(img, mx.astype(np.float32), my.astype(np.float32), cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def bild_atem(E: Ebenen, s: dict, i: int, parallax: bool) -> np.ndarray:
    """Ein Bild der Modi atem/parallax."""
    M = _kopf_matrix(s["roll"][i], s["dx"][i], s["dy"][i], 1.0)
    Mi = cv2.invertAffineTransform(M)                              # Ziel -> Quelle
    sx = Mi[0, 0] * E.xx + Mi[0, 1] * E.yy + Mi[0, 2]
    sy = Mi[1, 0] * E.xx + Mi[1, 1] * E.yy + Mi[1, 2]
    wk = E.wkopf
    b = float(s["atem"][i])
    # Rueckwaerts-Abbildung: Kopf starr (wk), Brust hebt sich und weitet sich leicht
    mx = E.xx + wk * (sx - E.xx) + b * 1.4 * (E.xx - PIVOT[0]) / 420 * E.wbrust
    my = E.yy + wk * (sy - E.yy) + b * 3.0 * E.wbrust
    cam = s["cam"][i] if parallax else np.zeros(3)
    P = _remap(E.img, mx, my)
    A = _remap(E.a, mx, my)
    B = E.bg
    if parallax:
        # Kamerafahrt: Person (nah) bewegt sich staerker als der Hintergrund (fern); Zoom um den Bildmittelpunkt
        def ebene(img, f):
            z = 1.0 + cam[2] * f
            Mc = np.array([[z, 0, (1 - z) * W / 2 + cam[0] * f], [0, z, (1 - z) * H / 2 + cam[1] * f]], np.float32)
            return cv2.warpAffine(img, Mc, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        P, A, B = ebene(P, 1.0), ebene(A, 1.0), ebene(B, 0.35)
    out = P * A[..., None] + B * (1 - A[..., None])
    out[..., 2] *= 1 + float(s["licht"][i]) * E.licht_w[..., 0] * 1.0   # Rot-Randlicht flackert kaum merklich
    return np.clip(out, 0, 255).astype(np.uint8)


# ---------------------------------------------------------------- Modus rede
def _feder(ziel: np.ndarray, w: float, stoss: np.ndarray | None = None, d: float = 1.0) -> np.ndarray:
    """Gedaempfte Feder (d=1 kritisch): folgt `ziel` weich, `stoss` = Geschwindigkeitsimpuls je Bild."""
    x, v, dt = float(ziel[0]), 0.0, 1.0 / FPS
    out = np.empty(len(ziel), np.float32)
    for i in range(len(ziel)):
        if stoss is not None:
            v += float(stoss[i])
        v += (w * w * (float(ziel[i]) - x) - 2 * d * w * v) * dt
        x += v * dt
        out[i] = x
    return out


def phrasen(sprech: np.ndarray, pause_s: float = 0.22) -> list[tuple[int, int]]:
    """(Start, Ende) je Sprechphrase in Bildern; Pausen kuerzer als pause_s gehoeren zur Phrase."""
    an = sprech > 0.18
    out, i, n = [], 0, len(an)
    while i < n:
        if not an[i]:
            i += 1
            continue
        j = i
        while j < n:
            if an[j]:
                j += 1
                continue
            k = j
            while k < n and not an[k]:
                k += 1
            if k - j >= int(pause_s * FPS) or k >= n:
                break
            j = k
        out.append((i, j))
        i = j
    return out


def betonungen(acc: np.ndarray, schwelle: float = 0.3, abstand_s: float = 0.32) -> list[tuple[int, float]]:
    """Lokale Spitzen der Betonungskurve (Bild, Staerke 0..1), mindestens abstand_s auseinander."""
    out, letzte = [], -10 ** 6
    for i in range(1, len(acc) - 1):
        if acc[i] >= schwelle and acc[i] >= acc[i - 1] and acc[i] > acc[i + 1] and i - letzte >= abstand_s * FPS:
            out.append((i, float(min(1.0, acc[i]))))
            letzte = i
    return out


def steuerung_rede(hk: np.ndarray, n: int, seed: int) -> dict:
    """Bewegungskurven des Modus rede (siehe Modul-Doku)."""
    env, acc = hk[:n, 0], hk[:n, 1]
    rng = np.random.RandomState(seed)
    sprech = np.clip(_glatt(env, 0.3) / 0.4, 0, 1)
    ph = phrasen(sprech)
    # Ziel-Haltung je Phrase (bleibt bis zur naechsten Phrase): Blick links/rechts, Neigung, Hoehe, Vorlehnen
    z_dx, z_roll, z_dy, z_lehn = (np.zeros(n, np.float32) for _ in range(4))
    seite = rng.choice([-1, 1])
    for k, (a, b) in enumerate(ph):
        e = ph[k + 1][0] if k + 1 < len(ph) else n
        seite = -seite if rng.rand() < 0.7 else seite                # meist abwechselnd, nie mechanisch
        z_dx[a:e] = seite * rng.uniform(2.5, 7.5)
        z_roll[a:e] = -seite * rng.uniform(0.3, 1.1) + rng.uniform(-0.25, 0.25)
        z_dy[a:e] = rng.uniform(-2.5, 1.5)
        z_lehn[a:e] = rng.uniform(0.3, 1.0) if acc[a:b].mean() > 0.12 else rng.uniform(0.0, 0.5)
        # Satzende: Kopf sinkt etwas und kehrt halb zur Mitte zurueck (bis die naechste Phrase beginnt)
        z_dy[b:e] += 3.0
        z_dx[b:e] *= 0.45
        z_roll[b:e] *= 0.5
        z_lehn[b:e] *= 0.4
    if ph:
        z_dx[:ph[0][0]] = z_dx[ph[0][0]]
    # Nicker: Impuls an jeder Betonung (nach unten), die Feder schwingt natuerlich nach
    st_dy, st_roll, st_sch = (np.zeros(n, np.float32) for _ in range(3))
    for i, staerke in betonungen(acc):
        st_dy[i] += 70.0 * staerke
        st_roll[i] += rng.uniform(-6.0, 6.0) * staerke
        if staerke > 0.6:
            st_sch[i] -= 9.0 * staerke                                # starke Betonung: Schultern heben sich kurz
    weich = np.array([0.1, 0.2, 0.25, 0.25, 0.2], np.float32)      # Impuls ueber 5 Bilder: Nicken setzt weich ein
    st_dy, st_roll, st_sch = (np.convolve(x_, weich)[:n] for x_ in (st_dy, st_roll, st_sch))
    # Einatmen vor jeder Phrase nach laengerer Pause: Kopf hebt sich, Brust weitet sich
    einatmen = np.zeros(n, np.float32)
    x = np.arange(n)
    for k, (a, b) in enumerate(ph):
        if a - (ph[k - 1][1] if k else 0) > 0.4 * FPS:
            einatmen += np.exp(-0.5 * ((x - (a - 0.25 * FPS)) / (0.2 * FPS)) ** 2).astype(np.float32)
    einatmen = np.clip(einatmen, 0, 1)
    dx = _feder(z_dx, 3.2) + 0.9 * rauschen(n, seed + 1, (0.21, 0.37, 0.61)) * (0.4 + 0.6 * sprech)
    dy = _feder(z_dy - 2.0 * einatmen, 4.0, st_dy, d=0.55) + 0.6 * rauschen(n, seed + 2, (0.21, 0.37, 0.61))
    roll = _feder(z_roll, 3.0, st_roll, d=0.7) + 0.12 * rauschen(n, seed + 3, (0.21, 0.37, 0.61))
    lehn = _feder(z_lehn, 1.6)
    t = np.arange(n) / FPS
    atem = 0.5 + 0.5 * np.sin(2 * math.pi * 0.24 * t + 0.5 * rauschen(n, seed + 9, (0.05, 0.09)))
    return dict(
        dx=dx, dy=dy, roll=roll,
        skala=1.0 + 0.010 * lehn,                                    # Vorlehnen: Kopf minimal groesser
        k_dx=_feder(dx * 0.38, 2.2),                                 # Oberkoerper folgt dem Kopf verzoegert
        k_dy=_feder(np.zeros(n, np.float32), 5.0, st_sch, d=0.8) - 1.5 * lehn,
        atem=np.clip(0.45 * atem + 0.35 * _glatt(env, 0.5) + 1.0 * einatmen, 0, 1.6),
        licht=0.025 * rauschen(n, seed + 6, (0.05, 0.13, 0.31)),
        cam=np.stack([5.0 * rauschen(n, seed + 7, (0.03, 0.061)), 2.8 * rauschen(n, seed + 8, (0.04, 0.083)),
                      0.005 + 0.005 * rauschen(n, seed + 10, (0.017, 0.041))], 1),
        phrasen=ph,
    )


def bild_rede(E: Ebenen, s: dict, i: int) -> np.ndarray:
    """Kopf starr (Rotation/Verschiebung/gleichmaessige Skala um den Hals), Oberkoerper verschoben + Atem, Mikrofon
    steht, Person vor dem freigestellten Hintergrund, langsame Kamera mit Tiefe (Person 1.0, Hintergrund 0.35).
    Kamera und Koerper in EINER Rueckwaertsabbildung (Gewichtskarten ohne Kamera, Fehler < 1 px)."""
    cam = s["cam"][i]
    z = 1.0 + float(cam[2])
    xc = (E.xx - (1 - z) * W / 2 - float(cam[0])) / z            # Zielbild -> Standbild-Koordinaten ohne Kamera
    yc = (E.yy - (1 - z) * H / 2 - float(cam[1])) / z
    Mi = cv2.invertAffineTransform(_kopf_matrix(float(s["roll"][i]), float(s["dx"][i]), float(s["dy"][i]),
                                                float(s["skala"][i])))
    wk, wb = E.wkopf_r, E.wbrust_r
    b = float(s["atem"][i])
    kdx, kdy = float(s["k_dx"][i]), float(s["k_dy"][i])
    rest = (1 - wk) * wb
    mx = xc + wk * (Mi[0, 0] * xc + Mi[0, 1] * yc + Mi[0, 2] - xc) + rest * (-kdx + b * 1.4 * (xc - PIVOT[0]) / 420)
    my = yc + wk * (Mi[1, 0] * xc + Mi[1, 1] * yc + Mi[1, 2] - yc) + rest * (-kdy + b * 3.0)
    mx, my = mx.astype(np.float32), my.astype(np.float32)
    P = cv2.remap(E.img8, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    A = cv2.remap(E.a, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    zb = 1.0 + float(cam[2]) * 0.35
    Mb = np.array([[zb, 0, (1 - zb) * W / 2 + cam[0] * 0.35], [0, zb, (1 - zb) * H / 2 + cam[1] * 0.35]], np.float32)
    B = cv2.warpAffine(E.bg8, Mb, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    out = cv2.blendLinear(P, B, A, 1 - A)
    lw = 1 + float(s["licht"][i]) * E.licht_w[..., 0]
    out[..., 2] = np.clip(out[..., 2] * lw, 0, 255).astype(np.uint8)
    return out


_E = None
_S = None


def _rede_init(ton, ende, seed):
    global _E, _S
    _, huellkurve = _ffmpeg()
    n = int(math.ceil(ende * FPS))
    _S = steuerung_rede(huellkurve(Path(ton), ende), n + FPS, seed)
    _E = Ebenen()
    _E.img8 = np.clip(_E.img, 0, 255).astype(np.uint8)
    _E.bg8 = np.clip(_E.bg, 0, 255).astype(np.uint8)


def _rede_block(ab):
    a, b = ab
    return b"".join(bild_rede(_E, _S, i).tobytes() for i in range(a, b))


def rede_kerne() -> int:
    """Rechenprozesse fuer den Modus rede: 8 Kerne bleiben frei (CPU-Waechter-Regel), hoechstens 8."""
    import os
    return max(1, min(8, (os.cpu_count() or 4) - 8, int(os.environ.get("NEWS_MASKEN_REDE_KERNE", "8"))))


# ---------------------------------------------------------------- Modus wan
def wan_kopfbahn(loop: Path, E: Ebenen, start_f: int = 0, anzahl: int = 100000):
    """Loop-Bilder auf das Standbild stabilisieren (ECC affin ueber das ganze Bild: der Wan-Loop schwankt mit der Kamera)
    und danach je Bild die starre Kopfbahn (ECC Euklid, Kopfmaske). Gibt (Bahn, stabilisierte Bilder) zurueck."""
    g0 = cv2.cvtColor(E.img.astype(np.uint8), cv2.COLOR_BGR2GRAY)
    s = 0.5
    g0s = cv2.GaussianBlur(cv2.resize(g0, None, fx=s, fy=s), (0, 0), 1.5)
    kopf = np.zeros((H, W), np.uint8)
    cv2.ellipse(kopf, (960, 235), (300, 250), 0, 0, 360, 255, -1)
    ms = cv2.resize(kopf, None, fx=s, fy=s, interpolation=cv2.INTER_NEAREST)
    E.wkopf_wan = cv2.GaussianBlur((kopf > 0).astype(np.float32), (0, 0), 40)
    krit = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 80, 1e-6)
    cap = cv2.VideoCapture(str(loop))
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_f)
    bahn, frames = [], []
    wg = np.eye(2, 3, dtype=np.float32)
    wk = np.eye(2, 3, dtype=np.float32)
    while len(frames) < anzahl:
        ok, f = cap.read()
        if not ok:
            break
        if f.shape[1] != W:
            f = cv2.resize(f, (W, H))
        g = cv2.GaussianBlur(cv2.resize(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), None, fx=s, fy=s), (0, 0), 1.5)
        try:   # Stufe 1: ganzes Bild (Hintergrund dominiert) -> stabilisiert; warp: Loop -> Standbild
            _, wg = cv2.findTransformECC(g0s, g, wg, cv2.MOTION_AFFINE, krit, None, 5)
        except cv2.error:
            pass
        w = wg.copy()
        w[:, 2] /= s
        fs = cv2.warpAffine(f, w, (W, H), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP, borderMode=cv2.BORDER_REFLECT)
        frames.append(fs)
        gs = cv2.GaussianBlur(cv2.resize(cv2.cvtColor(fs, cv2.COLOR_BGR2GRAY), None, fx=s, fy=s), (0, 0), 1.5)
        try:   # Stufe 2: Kopf im stabilisierten Bild relativ zum Standbild (starr)
            _, wk = cv2.findTransformECC(g0s, gs, wk, cv2.MOTION_EUCLIDEAN, krit, ms, 5)
        except cv2.error:
            pass
        w2 = wk.copy()
        w2[:, 2] /= s
        bahn.append(w2)
    cap.release()
    B = np.array(bahn, np.float32)                                   # Spruenge (Clip-Naehte) tiefpassen: Kopfbahn weich
    k = np.exp(-0.5 * (np.arange(-12, 13) / 5.0) ** 2); k /= k.sum()
    for a in range(2):
        for b in range(3):
            B[:, a, b] = np.convolve(np.pad(B[:, a, b], (12, 12), mode="edge"), k, "valid")
    return list(B), frames


def bild_wan(E: Ebenen, loop_frames, bahn, s: dict, i: int, versatz_s: float, loop_fps: float = 24.0) -> np.ndarray:
    n = len(loop_frames)
    t = (i / FPS + versatz_s) * loop_fps
    k0 = int(t) % n
    k1 = (k0 + 1) % n
    fr = t - int(t)
    body = loop_frames[k0].astype(np.float32) * (1 - fr) + loop_frames[k1].astype(np.float32) * fr
    # Kopfbahn: Loop-Koordinaten -> Standbild-Koordinaten (warp); wir brauchen Standbild -> Loop-Bild = Inverse
    w = bahn[k0] * (1 - fr) + bahn[k1] * fr                        # stabilisiertes Bild -> Standbild
    Mi = cv2.invertAffineTransform(w.astype(np.float32))           # Standbild-Punkt -> stabilisiertes Bild
    # leichte Betonungs-Nicker oben drauf (halbe Staerke, Loop bringt schon Eigenbewegung)
    Mn = _kopf_matrix(0.5 * s["roll"][i], 0.5 * s["dx"][i], 0.6 * s["dy"][i])
    A3 = np.vstack([Mi, [0, 0, 1]])
    N3 = np.vstack([Mn, [0, 0, 1]])
    T = (N3 @ A3)[:2].astype(np.float32)
    kopf = cv2.warpAffine(E.img, T, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    m = E.wkopf_wan[..., None]
    out = body * (1 - m) + kopf * m
    return np.clip(out, 0, 255).astype(np.uint8)


# ---------------------------------------------------------------- Treiber
def render(ton: Path, ende: float, out: Path, modus: str = "atem", versatz_s: float = 0.0, seed: int = 7,
           loop: Path | None = None, mit_ton: bool = False, loop_fps: float = 24.0, loop_start_s: float = 0.0):
    FF, huellkurve = _ffmpeg()
    n = int(math.ceil(ende * FPS))
    hk = huellkurve(ton, ende)
    s = steuerung_rede(hk, n + FPS, seed) if modus == "rede" else steuerung(hk, n + FPS, seed)
    E = Ebenen()
    wan = None
    if modus == "wan":
        wan = wan_kopfbahn(loop or (MASKE / "loop.mp4"), E, int(loop_start_s * loop_fps), int(ende * loop_fps) + 2)
    cmd = [FF, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-"]
    if mit_ton:
        cmd += ["-i", str(ton)]
    cmd += ["-c:v", "libx264", "-crf", "15", "-preset", "veryfast", "-g", str(FPS), "-pix_fmt", "yuv420p"]
    if mit_ton:
        cmd += ["-c:a", "aac", "-b:a", "192k", "-shortest"]
    cmd += [str(out)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, creationflags=NOWIN)
    if modus == "rede":
        import multiprocessing as mp
        bloecke = [(a, min(n, a + FPS)) for a in range(0, n, FPS)]
        k = rede_kerne()
        if k > 1:
            with mp.get_context("spawn").Pool(k, _rede_init, (str(ton), ende, seed)) as pool:
                for daten in pool.imap(_rede_block, bloecke, chunksize=1):
                    p.stdin.write(daten)
        else:
            _rede_init(str(ton), ende, seed)
            for bl in bloecke:
                p.stdin.write(_rede_block(bl))
        p.stdin.close()
        p.wait()
        return
    for i in range(n):
        if modus == "wan":
            f = bild_wan(E, wan[1], wan[0], s, i, 0.0, loop_fps)
        elif modus == "rede":
            f = bild_rede(E, s, i)
        else:
            f = bild_atem(E, s, i + int(versatz_s * FPS), modus == "parallax")
        p.stdin.write(f.tobytes())
    p.stdin.close()
    p.wait()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["probe"])
    ap.add_argument("--modus", default="atem", choices=["atem", "parallax", "wan", "rede"])
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--ton", required=True)
    ap.add_argument("--ende", type=float, default=25)
    ap.add_argument("--out", required=True)
    ap.add_argument("--mit-ton", action="store_true")
    ap.add_argument("--loop")
    ap.add_argument("--loop-fps", type=float, default=24.0)
    ap.add_argument("--loop-start", type=float, default=0.0)
    a = ap.parse_args()
    render(Path(a.ton), a.ende, Path(a.out), a.modus, seed=a.seed, mit_ton=a.mit_ton, loop=Path(a.loop) if a.loop else None,
           loop_fps=a.loop_fps, loop_start_s=a.loop_start)


if __name__ == "__main__":
    main()
