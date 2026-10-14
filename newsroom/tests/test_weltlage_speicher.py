"""Tests fuer tools/weltlage_speicher.py (Vorfall 14.10.2026: C: voll, Rohschnitt brach im s5-Lipsync ab).
Komplett offline in einem Temp-Ordner.

    .venv\\Scripts\\python -m unittest tests.test_weltlage_speicher
"""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import weltlage_speicher as sp  # noqa: E402


def _folge(base: Path, name: str) -> Path:
    o = base / name
    fw = o / "_schnitt" / "_freisteller"
    (fw / "_latentsync").mkdir(parents=True)
    (fw / "s5_freisteller_lipsync_prores4444.mov").write_bytes(b"x" * 1000)
    (fw / "s5_freisteller_grau25.mp4").write_bytes(b"x" * 100)
    (fw / "_latentsync" / "s5_00.wav").write_bytes(b"x" * 10)
    (fw / "s5_studio.mp4").write_bytes(b"x")
    (fw / "s5_fenster.json").write_text("{}")
    (o / f"{name}.mp4").write_bytes(b"x")
    return o


class SpeicherTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.jetzt = datetime.now().astimezone()
        alt = (self.jetzt - timedelta(days=3)).isoformat()
        aelter = (self.jetzt - timedelta(days=5)).isoformat()
        frisch = (self.jetzt - timedelta(hours=2)).isoformat()
        self.o = {n: _folge(self.base, n) for n in ("weltlage_a", "weltlage_b", "weltlage_frisch", "weltlage_lauf",
                                                    "weltlage_fest")}
        self.zustand = {
            "a": {"status": "veroeffentlicht", "ordner": str(self.o["weltlage_a"]), "fertig": alt},
            "b": {"status": "veroeffentlicht", "ordner": str(self.o["weltlage_b"]), "fertig": aelter},
            "frisch": {"status": "veroeffentlicht", "ordner": str(self.o["weltlage_frisch"]), "fertig": frisch},
            "lauf": {"status": "fehler", "ordner": str(self.o["weltlage_lauf"]), "fertig": aelter},
            "fest": {"status": "veroeffentlicht", "ordner": str(self.o["weltlage_fest"]), "fertig": aelter},
        }

    def tearDown(self):
        self.tmp.cleanup()

    def test_kandidaten_nur_veroeffentlicht_alt_ungeschuetzt(self):
        k = sp.kandidaten(self.zustand, jetzt=self.jetzt, schutz={"weltlage_fest"})
        self.assertEqual([p.name for p in k], ["weltlage_b", "weltlage_a"])   # aelteste zuerst

    def test_geschuetzte_ordner_aus_brand(self):
        brand = self.base / "brand" / "begruessung"
        brand.mkdir(parents=True)
        (brand / "aktiv.json").write_text(json.dumps({"video": "C:\\x\\data\\weltlage_20261001_1100\\_schnitt\\s.mp4"}))
        # das Aussprache-Lexikon nennt Folgen nur als Herkunft - kein Schutzgrund
        (self.base / "brand" / "aussprache_lexikon.json").write_text(json.dumps({"folge": "weltlage_20261002_folge"}))
        self.assertEqual(sp.geschuetzte_ordner(self.base / "brand"), {"weltlage_20261001_1100"})

    def test_aufraeumen_loescht_nur_zwischendateien(self):
        orig = sp.geschuetzte_ordner
        sp.geschuetzte_ordner = lambda brand=None: {"weltlage_fest"}
        try:
            gb = sp.aufraeumen(ziel_gb=10 ** 9, zustand=self.zustand, log=lambda m: None, frei=lambda: 0.0)
        finally:
            sp.geschuetzte_ordner = orig
        self.assertGreater(gb, 0)
        for n in ("weltlage_a", "weltlage_b"):
            fw = self.o[n] / "_schnitt" / "_freisteller"
            self.assertFalse((fw / "s5_freisteller_lipsync_prores4444.mov").exists())
            self.assertFalse((fw / "s5_freisteller_grau25.mp4").exists())
            self.assertFalse((fw / "_latentsync").exists())
            self.assertTrue((fw / "s5_studio.mp4").exists())
            self.assertTrue((fw / "s5_fenster.json").exists())     # braucht die Abnahme
            self.assertTrue((self.o[n] / f"{n}.mp4").exists())
        for n in ("weltlage_frisch", "weltlage_lauf", "weltlage_fest"):
            self.assertTrue((self.o[n] / "_schnitt" / "_freisteller" / "s5_freisteller_lipsync_prores4444.mov").exists())

    def test_sichern_genug_platz_tut_nichts(self):
        self.assertEqual(sp.sichern(frei=lambda: 500.0, zustand=self.zustand, log=lambda m: None), 500.0)
        self.assertTrue((self.o["weltlage_a"] / "_schnitt" / "_freisteller" / "_latentsync").exists())

    def test_sichern_zu_wenig_platz_bricht_klar_ab(self):
        with self.assertRaises(sp.SpeicherVoll):
            sp.sichern(frei=lambda: 1.0, zustand={}, log=lambda m: None)


if __name__ == "__main__":
    unittest.main()
