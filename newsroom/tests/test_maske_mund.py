"""Offline-Test Mund der Masken-Maske starr (Vorfall 28./29.10.2026, rexemre zum 2. Mal: «Der Mund der Maske bewegt sich»).

Ursache: Jede Masken-Sprecher-Spur kam aus Wan (Loop, dann FLF-Kurzclips). Wan zeichnet das Gesicht jedes Frame neu,
die Lippen der Maske veraendern sich mit; die Clip-Pruefung (Mund-SSIM >= 0,72 gegen das Standbild) liess das durch.
Jetzt: maske_flf_mix friert den Mund jedes Clips aus dem Standbild ein (maske_mund.einfrieren) und prueft die fertige
Spur (maske_mund.mund_bewegung); bewegt sich der Mund doch, MundBewegtFehler -> Folge/Short nehmen den CPU-Loop.

    .venv\\Scripts\\python -m unittest tests.test_maske_mund
"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import maske_flf_mix  # noqa: E402
import maske_mund as mm  # noqa: E402

HAT_REF = mm.REF.exists()


def _mund_bewegt(ref: np.ndarray, px: float) -> np.ndarray:
    """Standbild mit «sprechendem» Mund: Unterlippe um px nach unten gezogen (Kiefer oeffnet), wie Wan es tut."""
    h, w = ref.shape[:2]
    x0, y0, x1, y1 = mm.MUND_BOX
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cy = (y0 + y1) / 2
    gew = np.clip(1 - np.abs(xx - (x0 + x1) / 2) / ((x1 - x0) / 2), 0, 1) * np.clip((yy - cy + 4) / 12, 0, 1)
    gew *= (yy >= y0) & (yy < y1) & (xx >= x0) & (xx < x1)      # nur die Lippen bewegen sich, Rest der Maske starr
    return cv2.remap(ref, xx, (yy - float(px) * gew).astype(np.float32), cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def _video(pfad: Path, frames: list[np.ndarray], fps: int = 16):
    vw = cv2.VideoWriter(str(pfad), cv2.VideoWriter_fourcc(*"mp4v"), fps, (frames[0].shape[1], frames[0].shape[0]))
    for f in frames:
        vw.write(f)
    vw.release()


@unittest.skipUnless(HAT_REF, "Masken-Standbild fehlt")
class EinfrierenTest(unittest.TestCase):
    def test_standbild_ist_fixpunkt(self):
        ref = mm.referenz()
        self.assertLess(mm.mund_rest(ref), 0.3)

    def test_bewegter_mund_wird_erkannt_und_eingefroren(self):
        ref = mm.referenz()
        bewegt = _mund_bewegt(ref, 5.0)
        x0, y0, x1, y1 = mm.MUND_BOX
        self.assertGreater(np.abs(bewegt[y0:y1, x0:x1].astype(float) - ref[y0:y1, x0:x1]).mean(), 2.0)   # Mund wirklich anders
        self.assertGreater(mm.mund_rest(bewegt), mm.MUND_REST_GRENZE)
        starr = mm.einfrieren(bewegt)
        self.assertLess(mm.mund_rest(starr), mm.MUND_REST_GRENZE)
        self.assertLess(np.abs(starr[y0:y1, x0:x1].astype(float) - ref[y0:y1, x0:x1]).mean(), 1.0)

    def test_kopfbewegung_wird_mitgefuehrt(self):
        """Kopf leicht verschoben/gedreht: eingefrorener Mund sitzt in der neuen Lage, nicht an der alten Stelle."""
        ref = mm.referenz()
        M = cv2.getRotationMatrix2D((640.0, 330.0), 1.2, 1.0)
        M[:, 2] += (6.0, -4.0)
        def lage(im):
            return cv2.warpAffine(im, M, (mm.RW, mm.RH), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        ziel = lage(ref)
        starr = mm.einfrieren(lage(_mund_bewegt(ref, 5.0)))
        self.assertLess(mm.mund_rest(starr), mm.MUND_REST_GRENZE)
        x0, y0, x1, y1 = mm.MUND_BOX
        b = (x0 + 6, y0 - 4, x1 + 6, y1 - 4)
        def d(im, bx):
            return np.abs(im[bx[1]:bx[3], bx[0]:bx[2]].astype(float) - ziel[bx[1]:bx[3], bx[0]:bx[2]]).mean()
        self.assertLess(d(starr, b), 2.5)
        self.assertLess(d(starr, b), d(lage(_mund_bewegt(ref, 5.0)), b))    # naeher am starren Mund als vorher

    def test_wache_video(self):
        ref = mm.referenz()
        with tempfile.TemporaryDirectory() as td:
            roh, starr = Path(td) / "roh.mp4", Path(td) / "starr.mp4"
            fr = [_mund_bewegt(ref, 4.0 * abs(np.sin(i / 3))) for i in range(16)]
            _video(roh, fr)
            _video(starr, [mm.einfrieren(f) for f in fr])
            self.assertFalse(mm.mund_bewegung(roh, proben=8)["ok"])
            self.assertTrue(mm.mund_bewegung(starr, proben=8)["ok"])


@unittest.skipUnless(HAT_REF, "Masken-Standbild fehlt")
class MixTest(unittest.TestCase):
    def _mix_mit(self, td: Path, mund_ok: bool):
        ref = mm.referenz()
        gut = td / "gut"
        gut.mkdir()
        for k in range(2):
            _video(gut / f"clip_0{k}_s1.mp4", [_mund_bewegt(ref, 4.0 * abs(np.sin((i + k) / 3))) for i in range(10)])
        out = td / "host_spur.mp4"
        wache = dict(ok=mund_ok, mund_rest_max=0.5, mund_rest_mittel=0.5, proben=1)
        with mock.patch.object(maske_flf_mix, "GUT", gut), mock.patch.object(maske_flf_mix, "STARR", td / "starr"), \
                mock.patch.object(mm, "mund_bewegung", return_value=wache):
            erg = maske_flf_mix.mix(1.0, 1, out, "ffmpeg", 640, 360, 16)
        return erg, out, td / "starr"

    def test_mix_nimmt_eingefrorene_clips(self):
        with tempfile.TemporaryDirectory() as td:
            erg, out, starr = self._mix_mit(Path(td), True)
            self.assertTrue(out.exists())
            self.assertEqual(len(list(starr.rglob("clip_*.mp4"))), 2)
            self.assertTrue(erg["mund"]["ok"])
            cap = cv2.VideoCapture(str(next(starr.rglob("clip_00_s1.mp4"))))
            ok, f = cap.read()
            cap.release()
            self.assertTrue(ok)
            self.assertLess(mm.mund_rest(f), mm.MUND_REST_GRENZE)

    def test_mix_wache_schlaegt_an(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(maske_flf_mix.MundBewegtFehler):
                self._mix_mit(Path(td), False)
            self.assertFalse((Path(td) / "host_spur.mp4").exists())   # keine Spur mit bewegtem Mund liegen lassen


class AufruferTest(unittest.TestCase):
    """Folge und Short fangen MundBewegtFehler ab und nehmen den starren CPU-Loop (Selbstheilung statt Abbruch)."""

    def test_aufrufer_fangen_wache_ab(self):
        tools = Path(__file__).resolve().parents[1] / "tools"
        for name in ("weltlage_maskenformat.py", "weltlage_short_eigen.py"):
            src = (tools / name).read_text(encoding="utf-8")
            self.assertIn("maske_flf_mix.mix(", src, name)
            self.assertIn("except maske_flf_mix.MundBewegtFehler", src, name)

    def test_keine_wan_spur_ohne_mixer(self):
        """Nur maske_flf_mix darf FLF-Clips zur Spur machen (dort sitzt das Einfrieren)."""
        tools = Path(__file__).resolve().parents[1] / "tools"
        for p in tools.glob("*.py"):
            if p.name in ("maske_flf_mix.py", "maske_flf_pruefen.py", "maske_flf_clips.py", "maske_flf_alles.py"):
                continue
            src = p.read_text(encoding="utf-8", errors="ignore")
            self.assertNotIn("flf\" / \"gut\"", src, p.name)
            self.assertNotIn("flf/gut/clip", src, p.name)


if __name__ == "__main__":
    unittest.main()
