"""Offline-Test Master-Ton im Masken-Format (Vorfall 29.10.2026, 10:00-Folge: Abnahme "Lautheit -15.2 LUFS, Ziel
-14.0 +-1", zwei Neuschnitte, gleiches Ergebnis).

Ursache: tools/weltlage_maskenformat.py pegelte mit loudnorm linear=true. Liegt input_tp + Verstaerkung ueber dem
TP-Ziel (Sprache ~-22 LUFS mit einzelnen Spitzen ~-0,8 dBTP), faellt ffmpeg still in den dynamischen Modus und
landet ~1 LU zu leise. Jetzt: weltlage_rohschnitt.master_ton (feste Verstaerkung + True-Peak-Begrenzer); weil auch
der Begrenzer bei so spitzem Ton >1 LU kostet, regelt master_ton die Verstaerkung nach der Messung nach. Dazu fand
die Nur-Pegel-Reparatur des Tageslaufs (master_erneuern) im Masken-Format kein _schnitt - master_quellen nimmt
dann _maskenformat/ton.wav + roh.mp4.

    .venv\\Scripts\\python -m unittest tests.test_weltlage_masken_master
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import weltlage_rohschnitt as r  # noqa: E402


def _sprache_mit_spitzen(path: Path, sekunden: float = 30.0, sr: int = 48000):
    """Sprachaehnliches Signal (~-22 LUFS, moduliertes Rauschen) mit kurzen Spitzen nahe 0 dBFS."""
    import wave
    rng = np.random.default_rng(7)
    n = int(sekunden * sr)
    t = np.arange(n) / sr
    x = rng.standard_normal(n) * 0.035 * (0.6 + 0.4 * np.sin(2 * np.pi * 3.1 * t) ** 2)
    for k in range(1, int(sekunden) // 3):
        i = k * 3 * sr
        x[i:i + 48] = 0.9 * np.hanning(48)
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


class MaskenMaster(unittest.TestCase):
    def test_master_quellen_latara_vor_maske(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            work, mf = d / "_schnitt", d / "_maskenformat"
            work.mkdir()
            mf.mkdir()
            self.assertEqual(r.master_quellen(work), (work / "audio_all.wav", work / "video_all.mp4"))
            (mf / "ton.wav").touch()
            (mf / "roh.mp4").touch()
            self.assertEqual(r.master_quellen(work), (mf / "ton.wav", mf / "roh.mp4"))
            (work / "audio_all.wav").touch()
            (work / "video_all.mp4").touch()
            self.assertEqual(r.master_quellen(work), (work / "audio_all.wav", work / "video_all.mp4"))

    def test_naechste_verstaerkung(self):
        self.assertIsNone(r.naechste_verstaerkung(8.3, r.MASTER_LUFS - 0.2), "in der Toleranz: passt")
        self.assertAlmostEqual(r.naechste_verstaerkung(8.3, -15.4), round(8.3 + (r.MASTER_LUFS + 15.4), 2))
        self.assertAlmostEqual(r.naechste_verstaerkung(8.3, -12.0), round(8.3 + (r.MASTER_LUFS + 12.0), 2), msg="zu laut: senken")
        self.assertEqual(r.naechste_verstaerkung(23.0, -20.0), r.VERSTAERKUNG_MAX_DB, "nie ueber die Hoechstverstaerkung")
        self.assertIsNone(r.naechste_verstaerkung(r.VERSTAERKUNG_MAX_DB, -20.0), "an der Hoechstverstaerkung: nicht weiter")

    def test_master_trifft_ziel_trotz_spitzen(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            mf = d / "_maskenformat"
            mf.mkdir()
            _sprache_mit_spitzen(mf / "ton.wav")
            subprocess.run([r.FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=320x180:r=25:d=30",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(mf / "roh.mp4")], check=True)
            vorher = r._ebur128(mf / "ton.wav")
            self.assertLess(vorher["I"], -18)          # Ausgangslage wie am 29.10.: deutlich leiser als das Ziel
            self.assertGreater(vorher["TP"], -2)       # ... mit Spitzen, die loudnorm linear verhindert haetten
            out = d / "folge.mp4"
            res = r.master_erneuern(d / "_schnitt", out)
            self.assertTrue(out.exists())
            self.assertLessEqual(abs(res["nachher"]["I"] - r.MASTER_LUFS), 0.5, res)
            self.assertLessEqual(res["nachher"]["TP"], r.MASTER_TP + 0.5, res)


if __name__ == "__main__":
    unittest.main()
