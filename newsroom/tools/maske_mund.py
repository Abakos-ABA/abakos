"""Mund der Masken-Moderator-Spur einfrieren und messen (Wurzel-Fix Vorfall 28./29.10.2026).

Wan zeichnet in jedem Frame das ganze Gesicht neu; dabei bewegen sich die Lippen der Maske leicht mit, auch in Clips,
die maske_flf_pruefen.py als «gut» durchlaesst (Mund-SSIM gegen das Standbild ist zu grob). Eine Maske ist starr, also
gehoert der Mund in jedem Frame exakt aus dem Standbild: einfrieren() legt die Mundregion des Referenzbildes, per
ECC-Affin auf die Kopfbewegung des Frames ausgerichtet und mit dem Licht des Frames angeglichen, weich ueber den Frame.

mund_bewegung() misst, ob der Mund schon starr ist: erneutes Einfrieren darf die Lippenform kaum noch aendern. Wache: maske_flf_mix.mix() prueft die fertige Spur und meldet Bewegung als Fehler.

    python tools/maske_mund.py messen video.mp4 [...]
"""
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "config" / "brand" / "maskenmoderator" / "host_7b_720.png"   # Start-/Endbild der FLF-Clips
RW, RH = 1280, 720
MASKE_BOX = (517, 153, 766, 387)       # Maske (x0,y0,x1,y1) im 1280x720-Referenzbild: Ausrichtung
MUND_MITTE, MUND_ACHSEN = (640, 316), (82, 42)   # Lippen + Mundwinkel + Rand, voll deckend ueber der Messbox
MUND_BOX = (595, 298, 687, 334)        # Messbereich Lippen
STRUKTUR_SIGMA = 4.0                   # Messung: nur Lippenform (Hochpass), Licht/Farbe zaehlen nicht
LICHT_SIGMA = 25.0                     # Licht vom Frame aus der Mund-Umgebung uebernehmen, Lippenform bleibt vom Standbild
MUND_REST_GRENZE = 0.95                # mund_rest, Mittel ueber die Proben: eingefroren 0,47-0,82, Wan-Rohclips 1,12-2,05 (29.10.)

EINFRIER_STAND = "v2"                  # bei Aenderung an einfrieren() erhoehen -> Zwischenspeicher wird neu gerechnet

_ref_cache: dict = {}


def referenz(w: int = RW, h: int = RH) -> np.ndarray:
    if (w, h) not in _ref_cache:
        im = cv2.imread(str(REF))
        if im is None:
            raise FileNotFoundError(REF)
        _ref_cache[(w, h)] = cv2.resize(im, (w, h), interpolation=cv2.INTER_AREA) if im.shape[1] != w else im
    return _ref_cache[(w, h)]


def _skal(box, sx, sy):
    return (int(box[0] * sx), int(box[1] * sy), int(box[2] * sx), int(box[3] * sy))


def ausrichtung(ref_g: np.ndarray, f_g: np.ndarray, box, mund=None) -> np.ndarray | None:
    """Affine Abbildung Referenz -> Frame (ECC auf der Maske ohne Mundbereich, damit der bewegte Mund nicht mitzieht)."""
    mask = np.zeros(ref_g.shape, np.uint8)
    mask[box[1]:box[3], box[0]:box[2]] = 255
    if mund is not None:
        mask[mund[1]:mund[3], mund[0]:mund[2]] = 0
    warp = np.eye(2, 3, dtype=np.float32)
    try:
        _, warp = cv2.findTransformECC(ref_g, f_g, warp, cv2.MOTION_AFFINE,
                                       (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 60, 1e-5), mask, 5)
    except cv2.error:
        return None
    return warp


def _alpha(w: int, h: int) -> np.ndarray:
    sx, sy = w / RW, h / RH
    a = np.zeros((h, w), np.float32)
    cv2.ellipse(a, (int(MUND_MITTE[0] * sx), int(MUND_MITTE[1] * sy)),
                (int(MUND_ACHSEN[0] * sx), int(MUND_ACHSEN[1] * sy)), 0, 0, 360, 1, -1)
    return cv2.GaussianBlur(a, (0, 0), 7 * sx)[..., None]


def einfrieren(f: np.ndarray) -> np.ndarray:
    """Frame (BGR, beliebige Groesse im 16:9-Format) mit dem Mund aus dem Standbild zurueckgeben."""
    h, w = f.shape[:2]
    ref = referenz(w, h)
    sx, sy = w / RW, h / RH
    warp = ausrichtung(cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY), cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), _skal(MASKE_BOX, sx, sy), _skal(MUND_BOX, sx, sy))
    if warp is None:
        warp = np.eye(2, 3, dtype=np.float32)
    # warp bildet Referenz- auf Frame-Koordinaten ab -> Referenz und Mund-Alpha in die Frame-Lage bringen
    r = cv2.warpAffine(ref, warp, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    a = cv2.warpAffine(_alpha(w, h), warp, (w, h), flags=cv2.INTER_LINEAR)[..., None]
    f32, r32 = f.astype(np.float32), r.astype(np.float32)
    # Licht nur aus der Umgebung des Mundes (normierte Faltung): sonst schlaegt der bewegte Wan-Mund ueber das Licht durch
    s = LICHT_SIGMA * sx
    umg = (a[..., 0] < 0.02).astype(np.float32)
    n = cv2.GaussianBlur(umg, (0, 0), s)[..., None] + 1e-4
    umg = umg[..., None]
    licht = (cv2.GaussianBlur(f32 * umg, (0, 0), s) / n + 4) / (cv2.GaussianBlur(r32 * umg, (0, 0), s) / n + 4)
    r32 = r32 * np.clip(licht, 0.5, 2.0)
    return np.clip(f32 * (1 - a) + r32 * a, 0, 255).astype(np.uint8)


def mund_rest(f: np.ndarray) -> float:
    """Wie stark wuerde erneutes Einfrieren die Lippenform aendern (Grauwerte, nur feine Struktur, Referenzgroesse)?
    Starrer Mund = Fixpunkt (~0,5, nur Kompression/Interpolation); von Wan neu gezeichnete Lippen 1,1-2,1.
    Fixpunkt statt Vergleich mit dem Standbild: Wan-Unschaerfe und 3D-Drehung verwischen den direkten Vergleich."""
    if f.shape[1] != RW:
        f = cv2.resize(f, (RW, RH), interpolation=cv2.INTER_AREA)
    x0, y0, x1, y1 = MUND_BOX
    a = _struktur(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY))
    b = _struktur(cv2.cvtColor(einfrieren(f), cv2.COLOR_BGR2GRAY))
    return float(np.abs(a - b)[y0:y1, x0:x1].mean())


def _struktur(g: np.ndarray) -> np.ndarray:
    g = g.astype(np.float32)
    return cv2.GaussianBlur(g - cv2.GaussianBlur(g, (0, 0), STRUKTUR_SIGMA), (0, 0), 1.2)


def mund_bewegung(pfad: Path, proben: int = 24) -> dict:
    """Wache: Mund-Rest ueber ein Video (gleichmaessig verteilte Proben). ok = Mund starr."""
    cap = cv2.VideoCapture(str(pfad))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    werte = []
    for i in np.linspace(0, n - 1, min(proben, n)).astype(int):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(i))
        ok, f = cap.read()
        if ok:
            werte.append(mund_rest(f))
    cap.release()
    mx = max(werte) if werte else 255.0
    # Mittel statt Maximum: auch eingefrorene Frames haben einzelne Ausreisser (Ausrichtung, Kompression)
    return dict(mund_rest_max=round(mx, 2), mund_rest_mittel=round(float(np.mean(werte)) if werte else 255.0, 2),
                proben=len(werte), ok=bool(werte) and float(np.mean(werte)) <= MUND_REST_GRENZE)


def main():
    if len(sys.argv) < 3 or sys.argv[1] != "messen":
        print(__doc__)
        return 2
    schlecht = 0
    for p in sys.argv[2:]:
        r = mund_bewegung(Path(p))
        schlecht += not r["ok"]
        print(Path(p).name, r, flush=True)
    return 1 if schlecht else 0


if __name__ == "__main__":
    sys.exit(main())
