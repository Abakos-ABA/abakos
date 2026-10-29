"""Zusammensetzer fuer die Masken-FLF-Clips: mischt gepruefte Kurzclips (flf/gut) zu einer Sprecher-Spur beliebiger Laenge.

Alle Clips beginnen und enden am selben Masken-Standbild -> Schnitt ohne Ueberblendung ist nahtlos. Reihenfolge je Folge per
Seed gemischt (Beutel-Verfahren), nie derselbe Clip zweimal direkt hintereinander. Schalter im Masken-Format: NEWS_MASKEN_FLF=1
(Standard 0, CPU-Loop bleibt Rueckfall wenn weniger als FLF_MIN_CLIPS gute Clips da sind).

    python tools/maske_flf_mix.py probe --dauer 30 [--seed 1] [--out datei.mp4]
"""
import argparse
import random
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parents[1]
GUT = ROOT / "config" / "brand" / "maskenmoderator" / "flf" / "gut"
STARR = GUT.parent / "gut_mund_starr"     # Zwischenspeicher: gute Clips mit eingefrorenem Mund (maske_mund.einfrieren)
FLF_MIN_CLIPS = 5


class MundBewegtFehler(RuntimeError):
    """Wache: in der fertigen Spur bewegt sich der Mund der Maske (maske_mund.mund_bewegung)."""


def gute_clips() -> list[Path]:
    return sorted(GUT.glob("clip_*.mp4")) if GUT.exists() else []


def verfuegbar() -> bool:
    return len(gute_clips()) >= FLF_MIN_CLIPS


def _lade(p: Path, w: int, h: int) -> tuple[list[np.ndarray], float]:
    cap = cv2.VideoCapture(str(p))
    fps = cap.get(cv2.CAP_PROP_FPS) or 16.0
    fr = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        fr.append(cv2.resize(f, (w, h), interpolation=cv2.INTER_LANCZOS4))
    cap.release()
    return fr, fps


def starrer_clip(p: Path, ffmpeg: str = "ffmpeg") -> Path:
    """Clip mit Mund aus dem Standbild (Wan zeichnet die Lippen sonst jedes Frame leicht neu). Einmal je Clip gerechnet."""
    import maske_mund
    out = STARR / maske_mund.EINFRIER_STAND / p.name
    if out.exists() and out.stat().st_mtime >= max(p.stat().st_mtime, maske_mund.REF.stat().st_mtime):
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(p))
    fps = cap.get(cv2.CAP_PROP_FPS) or 16.0
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    tmp = out.with_suffix(".tmp.mp4")
    pr = subprocess.Popen([ffmpeg, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}", "-r", f"{fps:g}", "-i", "-",
                           "-c:v", "libx264", "-crf", "10", "-preset", "veryfast", "-pix_fmt", "yuv420p", str(tmp)],
                          stdin=subprocess.PIPE, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
    while True:
        ok, f = cap.read()
        if not ok:
            break
        pr.stdin.write(maske_mund.einfrieren(f).tobytes())
    cap.release()
    pr.stdin.close()
    if pr.wait() != 0:
        raise RuntimeError(f"ffmpeg: starrer Clip {p.name} fehlgeschlagen")
    tmp.replace(out)
    return out


def reihenfolge(n_clips: int, anzahl: int, rng: random.Random) -> list[int]:
    out: list[int] = []
    while len(out) < anzahl:
        beutel = list(range(n_clips))
        rng.shuffle(beutel)
        if out and n_clips > 1 and beutel[0] == out[-1]:
            beutel[0], beutel[-1] = beutel[-1], beutel[0]
        out += beutel
    return out[:anzahl]


def mix(dauer: float, seed: int, out: Path, ffmpeg: str = "ffmpeg", w: int = 1920, h: int = 1080, fps: int = 25, extra_s: float = 1.0,
        mund_starr: bool = True) -> dict:
    """mund_starr: Mund je Clip aus dem Standbild einfrieren und die fertige Spur pruefen (MundBewegtFehler -> Aufrufer nimmt CPU-Loop)."""
    clips = gute_clips()
    if not clips:
        raise RuntimeError("keine geprueften FLF-Clips in flf/gut")
    rng = random.Random(seed)
    geladen = {}
    n_ziel = int((dauer + extra_s) * fps)
    folge, n = [], 0
    ids = reihenfolge(len(clips), 4 + int((dauer + extra_s) / 0.8), rng)   # genug Clips, Ueberschuss wird abgeschnitten
    p = subprocess.Popen([ffmpeg, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
                          "-c:v", "libx264", "-crf", "14", "-preset", "veryfast", "-g", str(fps), "-pix_fmt", "yuv420p", str(out)],
                         stdin=subprocess.PIPE, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
    for i in ids:
        if n >= n_ziel:
            break
        if i not in geladen:
            geladen[i] = _lade(starrer_clip(clips[i], ffmpeg) if mund_starr else clips[i], w, h)
        fr, cfps = geladen[i]
        dur = len(fr) / cfps
        k = max(1, int(round(dur * fps)))
        for j in range(k):                                  # Zeitumrechnung cfps -> fps mit Bildmischung
            pos = j * (len(fr) - 1) / max(1, k - 1) if k > 1 else 0
            a = int(pos)
            b = min(a + 1, len(fr) - 1)
            t = pos - a
            f = fr[a] if t < 0.02 else cv2.addWeighted(fr[a], 1 - t, fr[b], t, 0)
            p.stdin.write(f.tobytes())
            n += 1
            if n >= n_ziel:
                break
        folge.append(i)
    p.stdin.close()
    p.wait()
    erg = dict(clips=[clips[i].name for i in folge], frames=n, dauer=n / fps)
    if mund_starr:
        import maske_mund
        erg["mund"] = maske_mund.mund_bewegung(out)
        if not erg["mund"]["ok"]:
            out.unlink(missing_ok=True)
            raise MundBewegtFehler(f"Mund der Maske bewegt sich in der Sprecher-Spur: {erg['mund']}")
    return erg


def main():
    a = argparse.ArgumentParser()
    a.add_argument("cmd", choices=["probe"])
    a.add_argument("--dauer", type=float, default=30.0)
    a.add_argument("--seed", type=int, default=1)
    a.add_argument("--out", default=str(ROOT / "output" / "maske_flf_probemix.mp4"))
    n = a.parse_args()
    import weltlage_maskenformat as mf
    Path(n.out).parent.mkdir(parents=True, exist_ok=True)
    r = mix(n.dauer, n.seed, Path(n.out), mf.FFMPEG, mf.W, mf.H, mf.FPS)
    print(r)


if __name__ == "__main__":
    main()
