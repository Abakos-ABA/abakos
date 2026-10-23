"""Freie Gesichtsdetektoren fuer LatentSync (kein InsightFace, 22.10.2026)."""
import os
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from video import lipsync_detektoren as D  # noqa: E402


class TestDetektoren(unittest.TestCase):
    def test_korrigiere_null_laesst_punkte(self):
        p = np.array([[100., 100.], [200., 100.], [150., 180.]])
        np.testing.assert_allclose(D.korrigiere(p, np.zeros((3, 2))), p)

    def test_korrigiere_im_gesichtsraster(self):
        p = np.array([[100., 100.], [200., 100.], [150., 180.]])     # Abstand 100, u=(1,0), v=(0,1)
        out = D.korrigiere(p, np.array([[0.1, 0.2], [0, 0], [0, -0.1]]))
        np.testing.assert_allclose(out, [[110, 120], [200, 100], [150, 170]])

    def test_pseudo106_mittel_ergibt_anker(self):
        lmk = D._pseudo106([10, 20], [50, 20], [30, 60], np.tile([30., 80.], (20, 1)))
        self.assertEqual(lmk.shape, (106, 2))
        np.testing.assert_allclose(lmk[D.BROW_L].mean(0), [10, 20])
        np.testing.assert_allclose(lmk[D.BROW_R].mean(0), [50, 20])
        np.testing.assert_allclose(lmk[D.NOSE].mean(0), [30, 60])

    def test_schalter(self):
        os.environ["LIPSYNC_DETEKTOR"] = "YuNet"
        try:
            self.assertEqual(D.gewaehlt(), "yunet")
        finally:
            del os.environ["LIPSYNC_DETEKTOR"]
        with self.assertRaises(ValueError):
            D.erzeuge("gibtsnicht")


if __name__ == "__main__":
    unittest.main()
