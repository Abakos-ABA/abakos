"""Kommerziell freie Gesichtserkennung fuer LatentSync (Ersatz fuer InsightFace buffalo_l, 22.10.2026).

InsightFace-Modelle (buffalo_l) sind nur fuer nicht-kommerzielle Forschung freigegeben -> nicht erlaubt fuer den
Partnerprogramm-Kanal. LatentSync braucht pro Bild nur drei Ankerpunkte (Mitte linke Braue, Mitte rechte Braue, Nasenmitte)
fuer die Ausrichtung aufs 512er-Raster; tools/latentsync_ref_inference.py zusaetzlich Mundpunkte (Mundoeffnung).

Rueckgabe wie vendor/LatentSync/latentsync/utils/face_detector.py: (bbox, lmk) mit lmk = 106x2-Feld im InsightFace-Layout,
aber nur die Indizes gefuellt, die gebraucht werden (Braue 43,48,49,51,50 / 101-105, Nase 74,77,83,86, Mund 52-71).

Varianten (Umgebungsvariable LIPSYNC_DETEKTOR):
  insightface  alt, NICHT kommerziell (nur zum Vergleich)
  mediapipe    MediaPipe Face Mesh (Apache 2.0), Video-Modus mit Verfolgung            <- Standard
  mediapipe_bild  dito, jedes Bild einzeln erkannt (kein Tracking)
  yunet        OpenCV YuNet (MIT), 5 Punkte; Brauen/Nasenmitte per fester Gesichtsgeometrie, keine Mundpunkte
Die festen Versatzwerte (OFFSETS, in Augenabstand-Einheiten) wurden einmalig aus Vergleichsbildern bestimmt
(tools/lipsync_detektor_kalibrieren.py); danach laeuft kein InsightFace mehr.
"""
import json
import os
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parents[1]
MODELS = HERE / "models" / "lipsync_detektoren"
KALIB = MODELS / "kalib.json"

STANDARD = "mediapipe"      # Sieger des Vergleichs 22.10.2026 (Task 767c); Schalter: Umgebungsvariable LIPSYNC_DETEKTOR=insightface fuer alt


def gewaehlt() -> str:
    return os.environ.get("LIPSYNC_DETEKTOR", STANDARD).lower()


BROW_L = [43, 48, 49, 51, 50]
BROW_R = [101, 102, 103, 104, 105]
NOSE = [74, 77, 83, 86]
MOUTH = list(range(52, 72))

# Face-Mesh-Punkte (MediaPipe, 468): Brauen (Person rechts = Bild links), Nasenmitte, aeusserer Lippenring (20)
MP_BROW_L = [70, 63, 105, 66, 107, 46, 53, 52, 65, 55]
MP_BROW_R = [336, 296, 334, 293, 300, 276, 283, 282, 295, 285]
MP_NOSE = [1, 2, 98, 327, 4]
MP_LIPS = [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 185, 40, 39, 37, 0, 267, 269, 270, 409]


def glaette_lmk(lmks: list, sigma: float = 1.6) -> list:
    """Zeitliche Glaettung der Ankerpunkte (Brauen, Nase) einer Bildfolge (Task 20261022-114327-3205).

    Das Zittern der Face-Mesh-Ankerpunkte (bis 20 px bei 160 px Augenabstand, vor allem wenn der Mund auf- und zugeht)
    verschiebt die Ausrichtung aufs 512er-Raster von Bild zu Bild -> unruhiger Mund, kurz schlechtes Lipsync. Hier:
    Ausreisser per Median ueber 5 Bilder weg, dann Gauss; Bilder ohne Treffer (None) bekommen die Werte des naechsten
    Nachbarn statt eines Abbruchs. Mundpunkte bleiben roh (Mundoeffnung fuer die Referenzwahl). Abschalten:
    LIPSYNC_GLAETTEN=0. Eingabe/Ausgabe: Liste von 106x2-Feldern (oder None)."""
    if os.environ.get("LIPSYNC_GLAETTEN", "1") == "0":
        return lmks
    ok = [i for i, l in enumerate(lmks) if l is not None]
    if len(ok) < 3:
        return lmks
    n = len(lmks)
    idx = np.arange(n)
    rows = BROW_L + BROW_R + NOSE
    arr = np.stack([np.asarray(lmks[i], np.float64)[rows] for i in ok]).reshape(len(ok), -1)
    full = np.stack([np.interp(idx, ok, arr[:, j]) for j in range(arr.shape[1])], 1)
    pm = np.pad(full, ((2, 2), (0, 0)), mode="edge")
    med = np.stack([np.median(pm[k:k + 5], axis=0) for k in range(n)])
    w = int(np.ceil(sigma * 3))
    kern = np.exp(-0.5 * (np.arange(-w, w + 1) / sigma) ** 2)
    kern /= kern.sum()
    pg = np.pad(med, ((w, w), (0, 0)), mode="edge")
    sm = np.stack([np.convolve(pg[:, j], kern, mode="valid") for j in range(med.shape[1])], 1).reshape(n, len(rows), 2)
    out = []
    for i in range(n):
        base = lmks[i] if lmks[i] is not None else lmks[min(ok, key=lambda k: abs(k - i))]
        l = np.array(base, np.float32)
        l[rows] = sm[i]
        out.append(l)
    return out


def _offsets(name: str) -> np.ndarray:
    """3x2: Korrektur (u, v) fuer Braue links, Braue rechts, Nase, in Einheiten des Abstands der beiden Brauenanker."""
    try:
        d = json.loads(KALIB.read_text())
        return np.array(d[name], dtype=np.float64)
    except Exception:
        return np.zeros((3, 2))


def korrigiere(p: np.ndarray, off: np.ndarray) -> np.ndarray:
    """p = [links, rechts, nase] (3x2); verschiebt jeden Punkt im Gesichtsraster (u entlang der Augenlinie, v quer)."""
    d = p[1] - p[0]
    n = float(np.linalg.norm(d)) or 1.0
    u = d / n
    v = np.array([-u[1], u[0]])
    return p + n * (off[:, :1] * u + off[:, 1:2] * v)


def _pseudo106(left, right, nose, mouth=None) -> np.ndarray:
    lmk = np.zeros((106, 2), np.float32)
    lmk[BROW_L] = left
    lmk[BROW_R] = right
    lmk[NOSE] = nose
    if mouth is not None:
        lmk[MOUTH] = mouth
    else:
        m = np.asarray(nose, np.float32) + (np.asarray(nose, np.float32) - (np.asarray(left) + np.asarray(right)) / 2) * 0.9
        lmk[MOUTH] = m
    return lmk


def _bbox_aus(pts: np.ndarray, shape):
    h, w = shape[:2]
    x1, y1 = pts.min(0)
    x2, y2 = pts.max(0)
    return [int(max(0, x1)), int(max(0, y1)), int(min(w, x2)), int(min(h, y2))]


class MediaPipeDetektor:
    def __init__(self, video: bool = True):
        import mediapipe as mp
        self.name = "mediapipe" if video else "mediapipe_bild"
        self.mesh = mp.solutions.face_mesh.FaceMesh(static_image_mode=not video, max_num_faces=2, refine_landmarks=False,
                                                    min_detection_confidence=0.5, min_tracking_confidence=0.5)
        self.off = _offsets(self.name)

    def __call__(self, frame, threshold=0.5):
        h, w = frame.shape[:2]
        res = self.mesh.process(np.ascontiguousarray(frame[..., :3]))   # Eingang RGB (wie LatentSync-Bilder)
        if not res.multi_face_landmarks:
            return None, None
        best, area = None, -1
        for fl in res.multi_face_landmarks:
            pts = np.array([(p.x * w, p.y * h) for p in fl.landmark], np.float32)
            a = float(np.ptp(pts[:, 0]) * np.ptp(pts[:, 1]))
            if a > area:
                best, area = pts, a
        pts = best
        raw = np.stack([pts[MP_BROW_L].mean(0), pts[MP_BROW_R].mean(0), pts[MP_NOSE].mean(0)])
        l, r, n = korrigiere(raw, self.off)
        lmk = _pseudo106(l, r, n, pts[MP_LIPS])
        return _bbox_aus(pts, frame.shape), lmk


class YuNetDetektor:
    name = "yunet"

    def __init__(self):
        self.det = cv2.FaceDetectorYN.create(str(MODELS / "yunet.onnx"), "", (320, 320), 0.6, 0.3, 5000)
        self.off = _offsets(self.name)

    def __call__(self, frame, threshold=0.5):
        h, w = frame.shape[:2]
        # YuNet findet enge Gesichtsfenster schlecht -> grauen Rand anfuegen (wie gesicht_hd.kps_of)
        pad = max(h, w) // 2
        big = cv2.copyMakeBorder(np.ascontiguousarray(frame[..., ::-1]), pad, pad, pad, pad, cv2.BORDER_CONSTANT,
                                 value=(128, 128, 128))
        self.det.setInputSize((big.shape[1], big.shape[0]))
        _, fs = self.det.detect(big)
        if fs is None or len(fs) == 0:
            return None, None
        f = max(fs, key=lambda f: f[2] * f[3])
        k = f[4:14].reshape(5, 2) - pad             # Augen (Person rechts = Bild links), Nasenspitze, Mundwinkel
        raw = np.stack([k[0], k[1], k[2]])
        l, r, n = korrigiere(raw, self.off)
        mouth = np.tile(((k[3] + k[4]) / 2).astype(np.float32), (20, 1))
        bb = [int(max(0, f[0] - pad)), int(max(0, f[1] - pad)), int(min(w, f[0] + f[2] - pad)), int(min(h, f[1] + f[3] - pad))]
        return bb, _pseudo106(l, r, n, mouth)


def erzeuge(name: str | None = None):
    name = (name or gewaehlt()).lower()
    if name == "mediapipe":
        return MediaPipeDetektor(True)
    if name == "mediapipe_bild":
        return MediaPipeDetektor(False)
    if name == "yunet":
        return YuNetDetektor()
    raise ValueError(f"unbekannter Detektor {name}")
