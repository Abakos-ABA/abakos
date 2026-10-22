"""Abnahme Ton (tools/weltlage_abnahme.ton_ok): 256k-Master mit inhaltsabhaengig niedriger Messrate besteht,
Neu-Codierungen (128k Standard, 160k Shorts, 180k Telegram) und falsches Format fallen durch. Vorfall 22.10.2026:
Folge 00:00 mit 217 kbit (korrekt 256k codiert, Encoder gesaettigt) faelschlich durchgefallen.

    .venv\Scripts\python -m unittest tests.test_weltlage_abnahme_ton
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import weltlage_abnahme as a  # noqa: E402


def _t(kbps, codec="aac", sr=48000, ch=2):
    return {"codec": codec, "sr": sr, "ch": ch, "kbps": kbps}


class TonOk(unittest.TestCase):
    def test_256k_master_mit_niedriger_messrate_besteht(self):
        for kbps in (217, 219, 226, 229, 246):
            self.assertTrue(a.ton_ok(_t(kbps)), kbps)

    def test_neu_codierung_faellt_durch(self):
        for kbps in (96, 128, 160, 180):
            self.assertFalse(a.ton_ok(_t(kbps)), kbps)

    def test_falsches_format_faellt_durch(self):
        self.assertFalse(a.ton_ok(_t(246, codec="mp3")))
        self.assertFalse(a.ton_ok(_t(246, sr=44100)))
        self.assertFalse(a.ton_ok(_t(246, ch=1)))


if __name__ == "__main__":
    unittest.main()
