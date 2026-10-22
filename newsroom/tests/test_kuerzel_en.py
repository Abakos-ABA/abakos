"""Englische Medien-/Organisationskuerzel (22.10.2026): CNBC -> "Si En Bi Si", EU/CDU/AfD bleiben deutsch,
vor KUERZEL_EN_AB vertonte Szenen behalten den Altstand, automatisches Lernen. Aufruf:
    .venv\\Scripts\\python.exe tests\\test_kuerzel_en.py
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tts import aussprache_lexikon as lex  # noqa: E402
from tts import kuerzel_lernen as kl  # noqa: E402
from tts import normalize_de as nd  # noqa: E402


class EnglischTest(unittest.TestCase):
    def test_cnbc_und_medien_englisch(self):
        n = nd.normalize_for_tts
        self.assertEqual(n("CNBC"), "Si En Bi Si")
        self.assertEqual(n("Die BBC"), "Die Bi Bi Si")
        self.assertEqual(n("CNN"), "Si En En")
        self.assertEqual(n("NBC, ABC und CBS"), "En Bi Si, Ei Bi Si und Si Bi Es")
        self.assertEqual(n("NPR"), "En Pi Ahr")
        self.assertEqual(n("NYT"), "En Wai Ti")
        self.assertEqual(n("WSJ"), "Dabbeljuh Es Dschej")
        self.assertEqual(n("AP"), "Ei Pi")
        self.assertEqual(n("FBI"), "Eff Bi Ai")

    def test_deutsche_kuerzel_bleiben(self):
        n = nd.normalize_for_tts
        self.assertEqual(n("EU"), "Eh Uh")
        self.assertEqual(n("CDU"), "Zeh Deh Uh")
        self.assertEqual(n("AfD"), "Ah Eff Deh")
        self.assertEqual(n("USA"), "Uh Ess Ah")
        self.assertEqual(n("NATO"), "NATO")
        self.assertEqual(n("UNO"), "UNO")

    def test_plural_und_kompositum(self):
        self.assertEqual(nd.normalize_for_tts("CNNs"), "Si En Ens")
        self.assertEqual(nd.normalize_for_tts("CNN-Bericht"), "Si-En-En-Bericht")

    def test_alte_szene_behaelt_altstand(self):
        with lex.ohne_gelernt_ab("2026-10-22 10:00:00"):
            self.assertEqual(nd.normalize_for_tts("CNBC"), "Zeh Enn Beh Zeh")
            self.assertEqual(nd.normalize_for_tts("FBI"), "Eff Bi Ai")
            self.assertIn("Zeh Beh Ess Njuhs", nd.normalize_for_tts("CBS News"))
        with lex.ohne_gelernt_ab("2026-10-23 10:00:00"):
            self.assertEqual(nd.normalize_for_tts("CNBC"), "Si En Bi Si")
            self.assertIn("Si Bi Es Njuhs", nd.normalize_for_tts("CBS News"))

    def test_neue_lexikon_namen_nicht_in_alten_szenen(self):
        self.assertIn("Blumbörg", nd.normalize_for_tts("Bloomberg"))
        with lex.ohne_gelernt_ab("2026-10-22 10:00:00"):
            self.assertEqual(nd.normalize_for_tts("Bloomberg"), "Bloomberg")


class LernenTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.alt = (kl.PFAD, kl.PROTOKOLL)
        kl.PFAD, kl.PROTOKOLL = self.tmp / "kuerzel_en.json", self.tmp / "protokoll.jsonl"
        self.en_vorher, self.zeit_vorher = set(nd.SPELL_OUT_EN), dict(nd._GELERNT_ZEIT)

    def tearDown(self):
        kl.PFAD, kl.PROTOKOLL = self.alt
        nd.SPELL_OUT_EN.clear()
        nd.SPELL_OUT_EN.update(self.en_vorher)
        nd._GELERNT_ZEIT.clear()
        nd._GELERNT_ZEIT.update(self.zeit_vorher)

    def folge(self, skript: str, artikel: list[str]) -> Path:
        d = self.tmp / "folge"
        d.mkdir(exist_ok=True)
        (d / "texte.json").write_text(json.dumps({"szenen": [{"id": "s1", "text": skript}]}), encoding="utf-8")
        (d / "news.json").write_text(json.dumps([{"articles": [{"title": t} for t in artikel]}]), encoding="utf-8")
        return d

    def test_lernt_mit_zwei_belegen_und_laesst_deutsches(self):
        d = self.folge("Die XYZ meldet, die QRS auch, und die EU.", ["XYZ says so", "Reuters: XYZ confirms", "QRS only once"])
        r = kl.lerne_aus_folge(d, log=lambda *_: None)
        self.assertEqual(r["gelernt"], ["XYZ"])
        self.assertEqual(r["offen"], {"QRS": 1})
        self.assertIn("XYZ", json.loads(kl.PFAD.read_text(encoding="utf-8"))["eintraege"])
        self.assertEqual(nd.normalize_for_tts("XYZ"), "Eks Wai Sed")
        self.assertEqual(nd.normalize_for_tts("EU"), "Eh Uh")

    def test_sperre_haelt_deutsch(self):
        d = self.folge("Die XYZ meldet.", ["XYZ a", "XYZ b"])
        kl.sperre("XYZ")
        self.assertEqual(kl.lerne_aus_folge(d, log=lambda *_: None)["gelernt"], [])


if __name__ == "__main__":
    unittest.main()
