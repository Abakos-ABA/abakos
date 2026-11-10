"""Weltlage-Meldungen gehen durch Jarvis' Telegram-Filter (Marlon 10.11.2026 «weniger Weltlage Kompakt»).

    .venv\Scripts\python -m pytest tests/test_weltlage_telegram_filter.py -q

Ohne Netz und ohne Jarvis: telegram_filter wird durch eine Attrappe ersetzt, _tg zeichnet nur auf.
"""
import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import weltlage_entscheid as ent  # noqa: E402


class FilterTest(unittest.TestCase):
    def setUp(self):
        self.gefragt, self.gesendet = [], []
        self.durchlassen = {"entscheidung", "fehler", "antwort"}
        attrappe = types.ModuleType("telegram_filter")
        attrappe.gate = lambda text, art=None, quelle=None, titel=None, **kw: (
            self.gefragt.append((art, quelle, titel)) or art in self.durchlassen)
        self._alt = sys.modules.get("telegram_filter")
        sys.modules["telegram_filter"] = attrappe
        self._tg = ent._tg
        ent._tg = lambda methode, daten, dateien=None, timeout=60: (
            self.gesendet.append((methode, daten.get("text") or daten.get("caption"))) or {"message_id": 1})

    def tearDown(self):
        ent._tg = self._tg
        if self._alt is None:
            sys.modules.pop("telegram_filter", None)
        else:
            sys.modules["telegram_filter"] = self._alt

    def test_routine_bleibt_weg(self):
        ent.mitteilen("Weltlage 10:00", "Veröffentlicht: Titel", log=lambda *_: None, beta_app=False)
        self.assertEqual(self.gesendet, [])
        self.assertEqual(self.gefragt, [("routine", "newsroom_weltlage", "Weltlage 10:00")])

    def test_fehler_und_antwort_gehen_raus(self):
        ent.mitteilen("Short 18:00", "Status unklar, bitte in Studio pruefen", log=lambda *_: None, beta_app=False,
                      art="fehler")
        ent.mitteilen("Weltlage 10:00", "Gestoppt", log=lambda *_: None, beta_app=False, art="antwort")
        self.assertEqual([m for m, _ in self.gesendet], ["sendMessage", "sendMessage"])

    def test_rueckfrage_ist_entscheidung(self):
        e = {"id": "abc123abc123", "runde": 1, "titel": "Weltlage 10:00: Thema", "optionen": {"A": "A"}}
        ids = ent.telegram_senden(e, "Welches Thema?", log=lambda *_: None)
        self.assertEqual(ids, [1])
        self.assertEqual(self.gefragt[0][0], "entscheidung")
        self.durchlassen = set()
        self.assertEqual(ent.telegram_senden(e, "Welches Thema?", log=lambda *_: None), [])

    def test_ohne_filter_nur_routine_weg(self):
        sys.modules["telegram_filter"] = types.ModuleType("telegram_filter")   # ohne gate -> Fehler
        self.assertFalse(ent.telegram_erlaubt("x", "routine", log=lambda *_: None))
        self.assertTrue(ent.telegram_erlaubt("x", "fehler", log=lambda *_: None))


if __name__ == "__main__":
    unittest.main()
