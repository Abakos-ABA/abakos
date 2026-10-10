"""Stimm-Veredelung und Chatterbox-Worker ueberleben einen GPU-Worker-Absturz (Vorfall 04.10. 13:11 und 10.10.2026
05:24: python.exe des Enhance-Workers starb im NVIDIA-Treiber nvcuda64.dll mit 0xC0000409, die ganze Vertonung und der
Tageslauf brachen ab - «stimme: Vertonung fehlgeschlagen»). Komplett offline: kein Unterprozess, keine GPU, kein Audio.

    .venv\\Scripts\\python -m unittest tests.test_veredelung_rueckfall
"""
import contextlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tts import tts_client as tc  # noqa: E402
from tts import veredelung as v  # noqa: E402

ABSTURZ = 0xC0000409          # subprocess meldet den Windows-Ausnahmecode als 3221226505


class FakeRun:
    """Ersatz fuer veredelung._run: die ersten `abstuerze` Enhance-Aufrufe sterben wie der Treiberabsturz, danach
    schreibt der Worker seine Ausgabedatei; ffmpeg schreibt immer seine Ausgabe."""

    def __init__(self, abstuerze: int, code: int = ABSTURZ):
        self.abstuerze, self.code, self.calls = abstuerze, code, []

    def enhance_calls(self):
        return [c for c in self.calls if "_enhance_worker.py" in c[1]]

    def __call__(self, cmd):
        cmd = [str(c) for c in cmd]
        self.calls.append(cmd)
        if "_enhance_worker.py" in cmd[1]:
            if len(self.enhance_calls()) <= self.abstuerze:
                raise v.WorkerFehler(f"{v.exit_text(self.code)}: worker\n  0%|          | 0/4 [00:00<?, ?it/s]", self.code)
            Path(cmd[3]).write_bytes(b"\0" * 200)
            return None
        Path(cmd[-1]).write_bytes(b"\0" * 200)   # ffmpeg: letztes Argument ist die Ausgabe
        return None


class Basis(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.wav = self.tmp / "s5_a4_verbindung.wav"
        self.wav.write_bytes(b"RIFF" + b"\0" * 300)
        self.enh = self.wav.with_name(self.wav.stem + "_enh.wav")
        self.log = []
        self._alt = {n: getattr(v, n) for n in ("_run", "ENHANCE_PYTHON", "PAUSE_S")}
        self._slot = v.gpu_budget.slot
        v.gpu_budget.slot = lambda *a, **k: contextlib.nullcontext()
        v.PAUSE_S = 0
        fake_py = self.tmp / "python.exe"
        fake_py.write_bytes(b"")
        v.ENHANCE_PYTHON = fake_py

    def tearDown(self):
        for n, val in self._alt.items():
            setattr(v, n, val)
        v.gpu_budget.slot = self._slot

    def _enhance(self, abstuerze: int, **kw):
        fake = FakeRun(abstuerze)
        v._run = fake
        device = v._enhance(self.wav, self.enh, log=self.log.append, pause_s=0, **kw)
        return fake, device


class Absturzerkennung(unittest.TestCase):
    def test_ist_absturz(self):
        self.assertFalse(v.ist_absturz(0))
        self.assertFalse(v.ist_absturz(1))
        self.assertFalse(v.ist_absturz(None))
        self.assertTrue(v.ist_absturz(ABSTURZ))          # nvcuda64.dll Fail-Fast, so kam es 04.10. und 10.10.
        self.assertTrue(v.ist_absturz(0xC0000005))       # Zugriffsverletzung
        self.assertTrue(v.ist_absturz(-1073740791))      # dasselbe als vorzeichenbehaftete Zahl

    def test_exit_text_hex(self):
        self.assertEqual(v.exit_text(ABSTURZ), "Exit 3221226505 (0xC0000409)")
        self.assertEqual(v.exit_text(1), "Exit 1 (0x00000001)")


class EnhanceWiederholung(Basis):
    def test_ohne_absturz_ein_anlauf_auf_der_gpu(self):
        fake, device = self._enhance(0)
        self.assertEqual(device, "cuda")
        self.assertEqual(len(fake.enhance_calls()), 1)
        self.assertEqual(fake.enhance_calls()[0][-1], "cuda")

    def test_ein_absturz_zweiter_anlauf_gpu(self):
        fake, device = self._enhance(1)
        self.assertEqual(device, "cuda")
        self.assertEqual(len(fake.enhance_calls()), 2)
        self.assertTrue(any("0xC0000409" in z and "Absturz" in z for z in self.log), self.log)
        self.assertTrue(any("Anlauf 2 (cuda) erfolgreich" in z for z in self.log), self.log)

    def test_zwei_abstuerze_dann_cpu(self):
        fake, device = self._enhance(2)
        self.assertEqual(device, "cpu")
        self.assertEqual([c[-1] for c in fake.enhance_calls()], ["cuda", "cuda", "cpu"])
        self.assertTrue(self.enh.exists())

    def test_alle_anlaeufe_tot_fehler_mit_exitcode(self):
        with self.assertRaises(RuntimeError) as cm:
            self._enhance(3)
        text = str(cm.exception)
        self.assertIn("0xC0000409", text)
        self.assertIn("Anlauf 3 (cpu)", text)
        self.assertIn("3 Anlaeufe", text)

    def test_ohne_cpu_rueckfall_nur_gpu(self):
        with self.assertRaises(RuntimeError):
            self._enhance(2, cpu_rueckfall=False)
        v._run = fake = FakeRun(1)
        self.assertEqual(v._enhance(self.wav, self.enh, log=self.log.append, pause_s=0, cpu_rueckfall=False), "cuda")
        self.assertEqual(len(fake.enhance_calls()), 2)

    def test_halbfertige_ausgabe_wird_vor_jedem_anlauf_entfernt(self):
        self.enh.write_bytes(b"\0" * 10)      # Rest eines frueheren Absturzes
        fake = FakeRun(0)

        def pruefend(cmd):
            if "_enhance_worker.py" in str(cmd[1]):
                self.assertFalse(self.enh.exists(), "alte _enh.wav muss vor dem Worker weg sein")
            return fake(cmd)
        v._run = pruefend
        self.assertEqual(v._enhance(self.wav, self.enh, log=self.log.append, pause_s=0), "cuda")

    def test_veredeln_komplett_mit_absturz(self):
        v._run = fake = FakeRun(1)
        device = v.veredeln(self.wav, log=self.log.append)
        self.assertEqual(device, "cuda")
        self.assertTrue(self.wav.exists())
        self.assertFalse(self.enh.exists(), "_enh.wav wird aufgeraeumt")
        self.assertFalse(self.wav.with_name(self.wav.stem + "_ver.wav").exists(), "_ver.wav ersetzt die Quelle")
        ffmpeg = [c for c in fake.calls if "_enhance_worker.py" not in c[1]]
        self.assertEqual(len(ffmpeg), 1, "Klangkette laeuft genau einmal, nach dem erfolgreichen Anlauf")
        self.assertTrue(any("veredelt in" in z and "(cuda)" in z for z in self.log), self.log)


class ChatterboxWorkerWiederholung(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.out = self.tmp / "s.wav"
        self.log = []

    def _lauf(self, codes):
        folge = list(codes)

        def lauf():
            rc = folge.pop(0)
            if rc == 0:
                self.out.write_bytes(b"RIFF" + b"\0" * 100)
            return subprocess.CompletedProcess(["worker"], rc, "", "stderr")
        return lauf

    def test_absturz_wird_wiederholt(self):
        r = tc.worker_mit_wiederholung(self._lauf([ABSTURZ, 0]), self.out, name="chatterbox worker",
                                       log=self.log.append, pause_s=0)
        self.assertEqual(r.returncode, 0)
        self.assertTrue(self.out.exists())
        self.assertEqual(len(self.log), 1)
        self.assertIn("0xC0000409", self.log[0])

    def test_regulaerer_fehler_nicht_wiederholt(self):
        laeufe = []
        lauf = self._lauf([1, 0])

        def zaehlend():
            laeufe.append(1)
            return lauf()
        r = tc.worker_mit_wiederholung(zaehlend, self.out, log=self.log.append, pause_s=0)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(len(laeufe), 1, "zweiter Anlauf darf nicht laufen")
        self.assertEqual(self.log, [])

    def test_zweimal_absturz_gibt_letztes_ergebnis(self):
        r = tc.worker_mit_wiederholung(self._lauf([ABSTURZ, ABSTURZ, 0]), self.out, log=self.log.append, pause_s=0,
                                       anlaeufe=2)
        self.assertEqual(r.returncode, ABSTURZ)
        self.assertFalse(self.out.exists())
        self.assertEqual(len(self.log), 2)


if __name__ == "__main__":
    unittest.main()
