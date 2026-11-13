"""Ersatz-KI im Weltlage-Skript (Vorfall 25.10.2026, Task 20261025-072414-13df).

Befund: das Claude-Abo war vom 24.10. 17:55 bis 25.10. 16:51 serverseitig gesperrt («Your organization has disabled
Claude subscription access for Claude Code»). tools/weltlage_skript.py hatte Claude als einzigen Weg, drei Laeufe
(00:00, 09:10 Nachhol, 10:00) scheiterten im Schritt skript mit der irrefuehrenden Meldung «besteht die automatische
Pruefung nicht». Diese Tests pruefen die Einordnung der CLI-Fehler (_claude), die Ersatz-Kette (_ersatz/frage_modell)
und dass die benutzte KI festgehalten wird (LLM_BENUTZT). Keine echten Aufrufe, kein Netz.

    .venv\\Scripts\\python -m unittest tests.test_weltlage_skript_ersatz
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))

import weltlage_skript as sk  # noqa: E402

ABO_GESPERRT = ("Claude-CLI Fehler: Your organization has disabled Claude subscription access for Claude Code · "
                "Use an Anthropic API key instead, or ask your admin to enable access")


class ClaudeEinordnungTest(unittest.TestCase):
    def test_zugangsfehler_sofort_ersatz(self):
        aufrufe = []

        def einmal(p):
            aufrufe.append(p)
            raise RuntimeError(ABO_GESPERRT)

        with self.assertRaises(sk.KiZugangFehler):
            sk._claude("x", einmal=einmal, schlafen=lambda s: None)
        self.assertEqual(len(aufrufe), 1, "Abo-Sperre wird nicht wiederholt")

    def test_login_und_limit_sind_zugangsfehler(self):
        for text in ("Claude-CLI Fehler: Not logged in · Please run /login", "Claude-CLI Fehler: You've hit your limit",
                     "Claude-CLI Fehler: You've hit your weekly limit · resets 2am (Europe/Zurich)",
                     "Claude-CLI Fehler: You've hit your session limit · resets 12:10am (Europe/Zurich)",
                     "Claude-CLI Fehler: API Error: 429 rate_limit_error", "Claude-CLI Fehler: 403 oauth_not_allowed_for_organization"):
            with self.subTest(text=text):
                self.assertTrue(sk.ZUGANG_RE.search(text))

    def test_serverfehler_wiederholen(self):
        n = {"i": 0}
        schlaf = []

        def einmal(p):
            n["i"] += 1
            if n["i"] < 3:
                raise RuntimeError("Claude-CLI Fehler: API Error: 529 overloaded_error")
            return '{"ok": 1}'

        self.assertEqual(sk._claude("x", einmal=einmal, schlafen=schlaf.append), '{"ok": 1}')
        self.assertEqual(n["i"], 3)
        self.assertEqual(schlaf, [sk.CLAUDE_WARTE_S, sk.CLAUDE_WARTE_S])

    def test_serverfehler_dauerhaft_wird_zugangsfehler(self):
        def einmal(p):
            raise RuntimeError("Claude-CLI Fehler: 503 service unavailable")

        with self.assertRaises(sk.KiZugangFehler) as cm:
            sk._claude("x", einmal=einmal, schlafen=lambda s: None)
        self.assertIn(f"nach {sk.CLAUDE_WIEDERHOLUNGEN} Versuchen", str(cm.exception))

    def test_anderer_fehler_bleibt_runtime(self):
        def einmal(p):
            raise RuntimeError("Claude-CLI ohne lesbare Antwort: kaputt")

        with self.assertRaises(RuntimeError) as cm:
            sk._claude("x", einmal=einmal, schlafen=lambda s: None)
        self.assertNotIsInstance(cm.exception, sk.KiZugangFehler)


class FrageModellErsatzTest(unittest.TestCase):
    def setUp(self):
        self._alt = (sk._claude, sk._ersatz, sk.LLM_BENUTZT["name"])
        sk.LLM_BENUTZT["name"] = ""

    def tearDown(self):
        sk._claude, sk._ersatz = self._alt[:2]
        sk.LLM_BENUTZT["name"] = self._alt[2]

    def test_claude_weg_ersatz_antwortet(self):
        def claude(p, **k):
            raise sk.KiZugangFehler(ABO_GESPERRT)

        def ersatz(p, grund, frage=None):
            self.assertIn("subscription access", grund)
            sk.LLM_BENUTZT["name"] = "ersatz/codex"
            return 'Hier das Skript: {"titel": "T"}'

        sk._claude, sk._ersatz = claude, ersatz
        self.assertEqual(sk.frage_modell("prompt"), {"titel": "T"})
        self.assertEqual(sk.LLM_BENUTZT["name"], "ersatz/codex")

    def test_ersatz_nachfrage_nur_json_bleibt_in_der_kette(self):
        antworten = iter(["kein JSON hier", '{"titel": "zweiter Anlauf"}'])
        prompts = []

        def claude(p, **k):
            raise sk.KiZugangFehler(ABO_GESPERRT)

        def ersatz(p, grund, frage=None):
            prompts.append(p)
            return next(antworten)

        sk._claude, sk._ersatz = claude, ersatz
        self.assertEqual(sk.frage_modell("prompt"), {"titel": "zweiter Anlauf"})
        self.assertEqual(len(prompts), 2)
        self.assertIn("nur mit dem JSON-Objekt", prompts[1])

    def test_claude_antwortet_normal(self):
        sk._claude = lambda p, **k: '{"titel": "A"}'
        sk._ersatz = lambda *a, **k: self.fail("Ersatz darf nicht laufen, wenn Claude antwortet")
        self.assertEqual(sk.frage_modell("p"), {"titel": "A"})
        self.assertTrue(sk.LLM_BENUTZT["name"].startswith("claude-cli/"), sk.LLM_BENUTZT["name"])

    def test_ersatz_kette_direkt(self):
        text = sk._ersatz("p", "grund", frage=lambda p: ('{"a": 1}', "lokal"))
        self.assertEqual(text, '{"a": 1}')
        self.assertEqual(sk.LLM_BENUTZT["name"], "ersatz/lokal")

        def kaputt(p):
            raise RuntimeError("keine Ersatz-KI antwortet (codex: nicht frei; lokal: Ollama aus)")

        with self.assertRaises(sk.KiZugangFehler) as cm:
            sk._ersatz("p", "grund", frage=kaputt)
        self.assertIn("Ersatz-Kette", str(cm.exception))
        self.assertIn("Ollama aus", str(cm.exception))

    def test_ersatz_ohne_jarvis_ordner(self):
        alt = sk.JARVIS_DIR
        sk.JARVIS_DIR = Path("C:/gibt/es/nicht")
        try:
            with self.assertRaises(sk.KiZugangFehler) as cm:
                sk._ersatz("p", "grund")
            self.assertIn("ki_oneshot.py fehlt", str(cm.exception))
        finally:
            sk.JARVIS_DIR = alt

    def test_jarvis_kette_ist_erreichbar(self):
        """Der Standardpfad zeigt auf einen Jarvis-Ordner mit ki_oneshot.ask(lang=...) - sonst gibt es keine Ersatz-KI."""
        if not (Path.home() / "projekte" / "jarvis").exists():
            self.skipTest("kein Jarvis-Ordner auf diesem Rechner")
        self.assertTrue((sk.JARVIS_DIR / "ki_oneshot.py").exists(), f"Standardpfad ohne ki_oneshot.py: {sk.JARVIS_DIR}")
        quelle = (sk.JARVIS_DIR / "ki_oneshot.py").read_text(encoding="utf-8")
        self.assertIn("lang: bool", quelle)
        self.assertIn("LETZTE", quelle)


if __name__ == "__main__":
    unittest.main()
