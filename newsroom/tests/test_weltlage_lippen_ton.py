"""Lippen-Video und Ton bleiben zusammen (Vorfall 08.10.2026: die Aussprache-Pflege liess eine Meldung nach dem
Lippen-Rendern neu sprechen, der wiederverwendete Sitz-Clip hatte danach versetzte Lippen). Offline, ohne GPU.

    .venv\Scripts\python -m unittest tests.test_weltlage_lippen_ton
"""
import hashlib
import json
import sys
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))

import weltlage_rohschnitt as rs  # noqa: E402
import weltlage_tts as tts  # noqa: E402


def _wav(pfad: Path, sek: float, seed: int):
    x = np.random.default_rng(seed).normal(0, 3000, int(sek * 24000)).clip(-32000, 32000).astype(np.int16)
    with wave.open(str(pfad), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(24000)
        w.writeframes(x.tobytes())


class TonAbweichung(unittest.TestCase):
    def test_gleicher_ton_ok_neue_aufnahme_faellt_auf(self):
        with tempfile.TemporaryDirectory() as td:
            fw = Path(td)
            a, b = fw / "a.wav", fw / "b.wav"
            _wav(a, 3.0, 1)
            _wav(b, 3.0, 2)
            rs.pad_wav(a, 0.25, 3.7, fw / "s5_ton_00.wav", ch=1)
            self.assertIsNone(rs.ton_abweichung([(a, 3.7)], 0, fw, "s5"))
            self.assertIn("anderer Ton", rs.ton_abweichung([(b, 3.7)], 0, fw, "s5"))
            self.assertIn("Laenge", rs.ton_abweichung([(a, 3.9)], 0, fw, "s5"))
            rs.pad_wav(a, 0.25, 3.5, fw / "coldopen_ton.wav", ch=1)
            self.assertIsNone(rs.ton_abweichung(a, 3.5, fw, "coldopen"))
            self.assertIsNone(rs.ton_abweichung(b, 3.5, fw, "themen"), "ohne alte Tondatei keine Pruefung")
            self.assertFalse(list(fw.glob("_*_tonvergleich.wav")), "Vergleichsdatei aufgeraeumt")


class LexikonNachLippen(unittest.TestCase):
    def _folge(self, td: str, text: str) -> tuple[Path, Path]:
        o = Path(td)
        (o / "audio").mkdir()
        (o / "_schnitt" / "_freisteller").mkdir(parents=True)
        w = o / "audio" / "s5_a1.wav"
        _wav(w, 1.0, 3)
        w.with_suffix(".tts.json").write_text(json.dumps(
            {"text_sha256": "alt", "text_roh_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}),
            encoding="utf-8")
        return o, w

    def test_lippen_video_zuordnung(self):
        with tempfile.TemporaryDirectory() as td:
            o, _ = self._folge(td, "x")
            fw = o / "_schnitt" / "_freisteller"
            self.assertIsNone(tts.lippen_video(o, "s5_a1"))
            (fw / "s5_studio.mp4").write_bytes(b"")
            (fw / "coldopen_studio.mp4").write_bytes(b"")
            self.assertEqual(tts.lippen_video(o, "s5_a1").name, "s5_studio.mp4")
            self.assertEqual(tts.lippen_video(o, "s_coldopen").name, "coldopen_studio.mp4")
            self.assertIsNone(tts.lippen_video(o, "s6_outro"))

    def test_nur_lexikon_vs_neuer_text(self):
        with tempfile.TemporaryDirectory() as td:
            _, w = self._folge(td, "Reuters meldet.")
            self.assertTrue(tts.lexikon_nur_geaendert("Reuters meldet.", w))
            self.assertFalse(tts.lexikon_nur_geaendert("Reuters meldet etwas anderes.", w))
            w.with_suffix(".tts.json").write_text(json.dumps({"text_sha256": "alt"}), encoding="utf-8")
            self.assertTrue(tts.lexikon_nur_geaendert("egal", w), "alte Dateien ohne Rohtext-Hash")


if __name__ == "__main__":
    unittest.main()
