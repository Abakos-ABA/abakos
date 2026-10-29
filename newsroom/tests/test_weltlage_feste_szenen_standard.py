"""Feste, eingefrorene Sprechszenen (Begruessung/Verabschiedung/Abschluss) muessen zum heutigen Lipsync-Standard
passen - und der Tageslauf baut sie vor einem neuen Rohschnitt selbst neu, wenn nicht (tools/weltlage_tageslauf.
feste_szenen_veraltet / feste_szenen_aktualisieren, Task 20261020-002406-1486, 20.10.2026).

Vorfall 19.10.2026: rexemres Umstellung auf Drosselstufe 2 (Guidance 2,0 -> 1,5, config.settings.NEWS_LIPSYNC_STUFE)
kam in den Code, ohne dass Begruessung/Abschluss neu eingefroren wurden. Jede Folge waere an der Abnahme
(«eingefroren mit Guidance 2.0 statt Standard 1.5 - neu bauen (build + freeze)») gescheitert, die Weltlage-Wache
kannte keinen Fix. Der letzte Test hier schlaegt deshalb an, sobald jemand den Standard aendert, ohne die
Szenen neu zu bauen - der naechste Tageslauf holt das zwar selbst nach, aber wer den Standard aendert, soll es wissen.

    .venv\\Scripts\\python -m unittest tests.test_weltlage_feste_szenen_standard
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))

import weltlage_tageslauf as tl  # noqa: E402

PIPELINE = {"guidance": 1.5, "hd": True, "composite_fx": True, "steps": 5}


def meta(guidance=1.5, hd=True, pipeline=None, **extra):
    m = {"guidance": guidance, "hd": hd, "pipeline": {**PIPELINE, "guidance": guidance, "hd": hd}, **extra}
    if pipeline is not None:
        m["pipeline"] = pipeline
    return m


class FesteSzenenVeraltet(unittest.TestCase):
    def test_passende_szenen_sind_nicht_veraltet(self):
        metas = {"begruessung": meta(), "abschluss": meta(), "verabschiedung": None}
        self.assertEqual(tl.feste_szenen_veraltet(metas, 1.5, True, PIPELINE), {})

    def test_hoehere_stufe_zaehlt_vor_neuem_render_als_veraltet(self):
        """Die Abnahme toleriert eine staerkere Stufe in einer fertigen Folge - vor einem NEUEN Render soll die
        Szene aber exakt zum Standard passen (Mund in Begruessung und Meldungen gleich stark)."""
        metas = {"begruessung": meta(guidance=2.0), "abschluss": meta()}
        v = tl.feste_szenen_veraltet(metas, 1.5, True, PIPELINE)
        self.assertEqual(list(v), ["begruessung"])
        self.assertTrue(any("2.0" in p for p in v["begruessung"]))

    def test_schwaechere_stufe_und_hd_abweichung(self):
        metas = {"begruessung": meta(guidance=1.2), "abschluss": meta(hd=False)}
        v = tl.feste_szenen_veraltet(metas, 1.5, True, PIPELINE)
        self.assertEqual(sorted(v), ["abschluss", "begruessung"])

    def test_neuer_pipeline_schalter_macht_szene_veraltet(self):
        metas = {"begruessung": meta(pipeline={"guidance": 1.5, "hd": True, "composite_fx": True})}
        v = tl.feste_szenen_veraltet(metas, 1.5, True, {**PIPELINE, "neuer_schalter": True})
        self.assertIn("begruessung", v)
        self.assertTrue(any("neuer_schalter" in p for p in v["begruessung"]))

    def test_nur_rechenzeit_felder_machen_nicht_veraltet(self):
        """steps (NUR_AUFWAND) betrifft nur die Rechenzeit, nicht das Bild - kein Grund fuer einen Neubau."""
        metas = {"begruessung": meta(pipeline={"guidance": 1.5, "hd": True, "composite_fx": True, "steps": 8})}
        self.assertEqual(tl.feste_szenen_veraltet(metas, 1.5, True, PIPELINE), {})

    def test_alte_fassung_ohne_felder_gilt_nicht_als_veraltet(self):
        """Fassungen von vor 02./03.10.2026 ohne guidance/pipeline: wie bisher nur Warnung der Abnahme."""
        metas = {"begruessung": {"landscape": "begruessung_v1.mp4"}}
        self.assertEqual(tl.feste_szenen_veraltet(metas, 1.5, True, PIPELINE), {})

    def test_builder_fuer_jede_feste_szene_vorhanden(self):
        for name, tool in tl.FESTE_SZENEN.items():
            self.assertTrue((ROOT / tool).exists(), f"{name}: {tool} fehlt")


class EingefroreneSzenenPassenZumStandard(unittest.TestCase):
    """Waechter gegen den Vorfall vom 19.10.2026: wer config.settings.NEWS_LIPSYNC_STUFE (oder einen Pipeline-
    Schalter) aendert, muss Begruessung/Abschluss neu einfrieren (build + freeze) - sonst schlaegt dieser Test an."""

    def test_aktive_fassungen_passen(self):
        from video import freisteller_lipsync as fl
        metas = {}
        for name in tl.FESTE_SZENEN:
            cfg = ROOT / "config" / "brand" / name / "aktiv.json"
            if cfg.exists():
                metas[name] = json.loads(cfg.read_text(encoding="utf-8"))
        if not metas:
            self.skipTest("keine eingefrorenen Szenen auf diesem Rechner")
        v = tl.feste_szenen_veraltet(metas, fl.GUIDANCE, fl.HD, fl.pipeline_signatur())
        self.assertEqual(v, {}, "eingefrorene Szenen passen nicht zum Lipsync-Standard - neu bauen: "
                                ".venv-lipsync\\Scripts\\python.exe tools\\weltlage_<szene>.py build, dann freeze "
                                "(der naechste Tageslauf macht das sonst selbst vor dem Rohschnitt)")


if __name__ == "__main__":
    unittest.main()
