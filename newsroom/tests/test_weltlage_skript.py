"""Titel-Schlagwort-Check (Auftrag 19.10.2026, Task 20261019-223623-e943).

Befund: der Short-Titel "Von 190'000 auf 20'000 geschrumpft: Wie verlässlich ist Trumps Wähler-Zahl?" (Video
5uC-u5K3QFE) bekam nur 20 Aufrufe und 0 % YouTube-Suche, weil das gesuchte Schlagwort "Trump" erst nach dem
Doppelpunkt stand statt vorne. Diese Tests pruefen schlagwoerter_der_folge()/voranstellen_falls_hinten() und die
daraus gebaute Pflicht-Regel in paket_pruefen() (Titel/Titel-Varianten muessen mit dem Schlagwort beginnen).

    .venv\\Scripts\\python -m unittest tests.test_weltlage_skript
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))

import weltlage_skript as sk  # noqa: E402


def _basis_skript(titel: str, titel_varianten: list[str] | None = None) -> dict:
    """Minimal gueltiges Skript-Dict fuer paket_pruefen() - nur die fuer den Titel-Check relevanten Felder
    realistisch befuellt, der Rest so, dass die ANDEREN Pflicht-Regeln nicht gleichzeitig anschlagen."""
    hook = ("Trump kündigt neue Zölle an, zwei Milliarden stehen im Raum. Was bedeutet das für Europa? "
            "Das alles gleich in Weltlage Kompakt.")
    return {
        "hook": hook,
        "hook_themen": [{"meldung": 1, "stichwort": "Zölle"}],
        "abschnitte": [{"rolle": "ausgangslage", "kurz": "Trump kündigt Zölle an", "meldungen": [1],
                        "text": "Trump verhängt neue Zölle gegen Europa. «Das wird hart», sagt Trump."},
                       {"rolle": "schluss", "kurz": "was das für Europa heisst", "meldungen": [1],
                        "text": "Was bedeutet das für Europas Wirtschaft?"}],
        "titel": titel,
        "titel_varianten": titel_varianten or [titel, titel, titel],
        "thumbnail_text": "ZÖLLE SCHOCK",
        "zentrale_these": "Trumps Zölle treffen Europa hart.",
        "analyse": {"akteure": [{"person": "Donald Trump", "funktion": "US-Präsident", "interesse": "Zölle"}]},
        "zitate": [{"person": "Trump"}],
        "handlungen": [{"wer": "Trump"}],
        "thumbnail": {"banderole": "ALARM", "zeile1": "ZÖLLE", "zeile2": "SCHOCK?", "farbe": "wirtschaft"},
        "meinungen": ["Ich halte das für riskant."],
        "kommentarfrage": "Was bedeutet das für Europas Wirtschaft?",
    }


class SchlagwoerterDerFolgeTest(unittest.TestCase):
    def test_findet_personennamen(self):
        s = _basis_skript("Trump verhängt Zölle: Europa in Gefahr?")
        self.assertIn("Trump", sk.schlagwoerter_der_folge(s))

    def test_findet_land_ohne_person(self):
        s = _basis_skript("Egal")
        s["analyse"]["akteure"] = []
        s["zitate"] = []
        s["handlungen"] = []
        s["abschnitte"][0]["text"] = "Die Ukraine meldet neue Angriffe auf Energieanlagen."
        self.assertIn("Ukraine", sk.schlagwoerter_der_folge(s))


class VoranstellenFallsHintenTest(unittest.TestCase):
    def test_schlagwort_schon_vorne_bleibt_unveraendert(self):
        text = "Trump verhängt Zölle: Europa in Gefahr?"
        self.assertEqual(sk.voranstellen_falls_hinten(text, {"Trump"}), text)

    def test_schlagwort_hinten_wird_vorangestellt(self):
        # Genau der reale Befund: Schlagwort "Trump" erst nach dem Doppelpunkt.
        text = "Von 190'000 auf 20'000 geschrumpft: Wie verlässlich ist Trumps Wähler-Zahl?"
        ergebnis = sk.voranstellen_falls_hinten(text, {"Trump"})
        self.assertTrue(ergebnis.startswith("Trump:"))
        self.assertIn(text, ergebnis)

    def test_kein_bekanntes_schlagwort_bleibt_unveraendert(self):
        text = "Ein Satz ohne jedes bekannte Schlagwort."
        self.assertEqual(sk.voranstellen_falls_hinten(text, {"Trump"}), text)

    def test_ohne_schlagwoerter_bleibt_unveraendert(self):
        text = "Trump verhängt Zölle."
        self.assertEqual(sk.voranstellen_falls_hinten(text, set()), text)


class PaketPruefenTitelTest(unittest.TestCase):
    def test_titel_mit_schlagwort_vorne_besteht(self):
        s = _basis_skript("Trump verhängt Zölle: Europa in Gefahr?")
        hart, _ = sk.paket_pruefen(s)
        self.assertFalse([f for f in hart if "Schlagwort" in f or "Namen" in f], hart)

    def test_titel_mit_schlagwort_hinten_wird_hart_abgelehnt(self):
        # Regressionsfall: genau das Muster des Short-Befunds vom 19.10.2026.
        s = _basis_skript("Von 190'000 auf 20'000 geschrumpft: Wie verlässlich ist Trumps Wähler-Zahl?")
        hart, _ = sk.paket_pruefen(s)
        self.assertTrue(any("Schlagwort" in f for f in hart), hart)

    def test_titel_variante_mit_schlagwort_hinten_wird_hart_abgelehnt(self):
        s = _basis_skript("Trump verhängt Zölle: Europa in Gefahr?",
                          titel_varianten=["Trump verhängt Zölle: Europa in Gefahr?",
                                           "Pulverbriefe und Klagen: Was Trump damit zu tun hat?",
                                           "Trump verhängt Zölle: Europa in Gefahr?"])
        hart, _ = sk.paket_pruefen(s)
        self.assertTrue(any("Titel-Variante 2" in f for f in hart), hart)

    def test_titel_ganz_ohne_schlagwort_bleibt_bisherige_meldung(self):
        s = _basis_skript("Zölle in Gefahr: Wer zahlt am Ende?")
        s["analyse"]["akteure"] = []
        s["zitate"] = []
        s["handlungen"] = []
        s["abschnitte"][0]["text"] = "Allgemeine Marktbeobachtung ohne Namen oder Land."
        hart, _ = sk.paket_pruefen(s)
        self.assertTrue(any("Titel nennt keine Person mit Namen" in f for f in hart), hart)


if __name__ == "__main__":
    unittest.main()
