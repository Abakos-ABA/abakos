"""Bildspur ohne Moderator (tools/weltlage_bildspur.py, 20.11.2026): Satzzeiten, Kartenwahl, Plan lueckenlos,
hoechstens QUELLEN_MAX Screenshots, keine Blitzkarten. Offline (nur Pillow, kein ffmpeg)."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import weltlage_bildspur as bs  # noqa: E402

TEXT = ("Am Donnerstag passiert in Washington etwas Ungewöhnliches. Der Ausschuss stimmt dafür, vertrauliche "
        "Exportdaten zu veröffentlichen, und zwar sämtliche Genehmigungen der letzten sechs Monate, mit allen Namen der "
        "Empfänger und allen Mengen, die bisher nur intern bekannt waren. Genehmigt wurden 879'000 Chips. "
        "Trump schrieb: «Es war eine grossartige und höchst folgenreiche Reise.» Was folgt daraus?")


class BildspurTest(unittest.TestCase):
    def test_satzzeiten_lueckenlos_und_begrenzt(self):
        z = bs.satz_zeiten(TEXT, 40.0)
        self.assertAlmostEqual(z[0][0], 0.0)
        self.assertAlmostEqual(z[-1][1], 40.0)
        for a, b in zip(z, z[1:]):
            self.assertAlmostEqual(a[1], b[0], places=6)
        for t0, t1, s in z:
            self.assertLessEqual(t1 - t0, 12.0 + 1e-6 if "«" in s else bs.KARTE_MAX_S + 1e-6, s)

    def test_zahl_und_zitat(self):
        self.assertEqual(bs.zahl_in("Genehmigt wurden 879'000 Chips.")[0], "879'000")
        self.assertIsNone(bs.zahl_in("Im Jahr 2025 geschah nichts."))
        self.assertIsNone(bs.zahl_in("Am 19. November tagte der Ausschuss."))
        self.assertIn("25 %", bs.zahl_in("Die USA erhalten 25 Prozent vom Umsatz.")[0])
        z = bs.zitat_in("Trump schrieb: «Es war eine grossartige Reise.»",
                        [{"deutsch": "Es war eine grossartige Reise.", "person": "Donald Trump", "funktion": "Präsident"}])
        self.assertEqual(z["person"], "Donald Trump")

    def test_plan(self):
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            bild = work / "m0.png"
            from PIL import Image
            Image.new("RGB", (1280, 2000), (240, 240, 240)).save(bild)
            szenen = []
            for i in range(5):                                 # 5 Meldungen mit demselben Screenshot-Bild je 2er-Paar
                szenen.append({"t0": i * 40.0, "dauer": 40.0, "kicker": f"Meldung {i}", "kapitel": (f"{i + 1} / 5", "Titel"),
                               "saetze": bs.satz_zeiten(TEXT, 40.0), "bild": str(work / f"m{i}.png"),
                               "clips": [{"datei": "clip.mp4", "t": 12.0, "laenge": 6.3}]})
                Image.new("RGB", (1280, 2000), (240, 240, 240)).save(work / f"m{i}.png")
            segs = bs.plan_bauen(szenen, work)
            self.assertAlmostEqual(segs[0]["t0"], 0.0)
            for a, b in zip(segs, segs[1:]):
                self.assertAlmostEqual(a["t0"] + a["dauer"], b["t0"], places=3)
            arten = [s["art"] for s in segs]
            self.assertEqual(arten.count("quelle"), bs.QUELLEN_MAX)
            self.assertEqual(arten.count("kapitel"), 5)
            self.assertEqual(arten.count("voll"), 5)
            self.assertIn("zitat", arten)
            self.assertIn("zahl", arten)
            self.assertTrue(all(s["dauer"] >= 1.2 for s in segs if s["art"] != "kapitel"))
            self.assertNotIn("sprecher", arten)


if __name__ == "__main__":
    unittest.main()
