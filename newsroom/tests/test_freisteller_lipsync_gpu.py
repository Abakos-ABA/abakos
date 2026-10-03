"""Offline-Test fuer video/freisteller_lipsync._run_with_gpu (Task 20261002-170551-fe9f, 02.10.2026;
Sperre excl=LS_EXCL seit Task 20261004-003744-17ef).

Jede GPU-Operation (Zoom-Fenster, LatentSync-Aufruf, GFPGAN-Nachzeichnung) haelt ihren Platz in der zentralen
GPU-Warteschlange (jarvis/tools/gpu_queue.py, ueber gpu_budget.slot) nur fuer sich selbst, nie fuer die ganze
Folge -- die Warteschlange entscheidet allein ueber den Start. Zusaetzlich meldet jede Operation excl=LS_EXCL an:
nie zwei Weltlage-Lipsync-Laeufe gleichzeitig, selbst wenn die VRAM-Schaetzung beide zuliesse (zwei Folgen teilten
sich sonst die GPU und liefen beide nur halb so schnell). Bis 04.10.2026 war das eine eigene Datei-Sperre
(PID in state/latentsync.lock) mit Zombie-Risiko bei PID-Wiederverwendung nach einem Absturz; die zentrale
Warteschlange prueft PID+Startzeit und ist darum sicherer.

    .venv\\Scripts\\python -m unittest tests.test_freisteller_lipsync_gpu
"""
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from video import freisteller_lipsync as fl  # noqa: E402


def _silent_log(*_a, **_kw):
    pass


class FakeGpuBudget:
    """Steht fuer das echte gpu_budget-Modul: hat bewusst kein `hold`, damit ein Rueckfall auf die alte
    Ganz-Prozess-Sperre (AttributeError) den Test sofort sichtbar scheitern liesse."""

    def __init__(self):
        self.calls = []

    @contextmanager
    def slot(self, step, name=None, prio=None, progress=None, vram_mb=None, excl=None):
        self.calls.append(dict(step=step, name=name, vram_mb=vram_mb, progress=progress, excl=excl))
        yield object()


class RunWithGpu(unittest.TestCase):
    def setUp(self):
        self.gb = FakeGpuBudget()
        self._patch = mock.patch.object(fl, "_gpu_budget", return_value=self.gb)
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def test_haelt_platz_nur_fuer_die_operation(self):
        result = fl._run_with_gpu("zoom", 3000, _silent_log, lambda: "fertig")
        self.assertEqual(result, "fertig")
        self.assertEqual(len(self.gb.calls), 1)
        call = self.gb.calls[0]
        self.assertEqual(call["step"], "lipsync")
        self.assertIn("zoom", call["name"])
        self.assertEqual(call["vram_mb"], 3000)
        self.assertTrue(callable(call["progress"]))
        self.assertEqual(call["excl"], fl.LS_EXCL)

    def test_mehrere_operationen_sind_eigene_platzanfragen(self):
        fl._run_with_gpu("zoom", 3000, _silent_log, lambda: None)
        fl._run_with_gpu("latentsync", fl.LS_FREE_MB, _silent_log, lambda: None)
        fl._run_with_gpu("restore", 2000, _silent_log, lambda: None)
        vram = [c["vram_mb"] for c in self.gb.calls]
        self.assertEqual(vram, [3000, fl.LS_FREE_MB, 2000])
        self.assertTrue(all(c["excl"] == fl.LS_EXCL for c in self.gb.calls))

    def test_fehler_in_der_operation_wird_weitergereicht(self):
        def boom():
            raise RuntimeError("latentsync kaputt")
        with self.assertRaises(RuntimeError):
            fl._run_with_gpu("latentsync", fl.LS_FREE_MB, _silent_log, boom)
        self.assertEqual(len(self.gb.calls), 1)   # Platz wurde trotzdem anfordert (und ueber den with-Block freigegeben)


if __name__ == "__main__":
    unittest.main()
