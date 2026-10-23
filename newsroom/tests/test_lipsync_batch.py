"""Stapelbetrieb NEWS_LIPSYNC_BATCH (Task c49b): prefetch_chunks() buendelt fehlende LatentSync-Stuecke in einem Prozess
(tools/latentsync_ref_inference.py --jobs), uebernimmt nur als fertig gemeldete Stuecke in den Zwischenspeicher und
laesst sync_chunk() den Rest einzeln rechnen. Offline: der LatentSync-Prozess ist ein Fake-Skript, keine GPU."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from video import freisteller_lipsync as fl  # noqa: E402

FAKE = '''
import json, sys
a = sys.argv
jobs = json.load(open(a[a.index("--jobs") + 1]))
stop = int(__import__("os").environ.get("FAKE_STOP_AFTER", "999"))
for i, j in enumerate(jobs):
    if i >= stop:
        sys.exit(3)
    open(j["out"], "wb").write(b"x")
    print("[job] " + j["out"] + " 1.0 s", file=sys.stderr, flush=True)
'''


class BatchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "fake.py").write_text(FAKE)
        self.old = (fl.LS_PY, fl.SHARED_CACHE, fl._run_with_gpu, fl._zoom_video, fl.REPO, fl.LS_BATCH_MAX, fl.run)
        fl.LS_PY = Path(sys.executable)
        fl.SHARED_CACHE = self.tmp / "shared"
        fl.REPO = self.tmp
        fl._run_with_gpu = lambda step, vram, log, fn: fn()
        fl._zoom_video = lambda tag, g, a, b, box, cache, log: cache / f"{tag}_zoom.mp4"

        def fake_run(cmd):                      # ffmpeg-Tonstueck: leere Datei genuegt fuer den Hash
            Path(cmd[-1]).write_bytes(b"w")
        fl.run = fake_run
        self.cache = self.tmp / "cache"
        self.cache.mkdir()
        # LS_PY ruft latentsync_ref_inference.py auf -> auf das Fake-Skript umbiegen
        self.script = fl.ROOT
        fl.ROOT = self.tmp
        (self.tmp / "tools").mkdir()
        (self.tmp / "tools" / "latentsync_ref_inference.py").write_text(FAKE)

    def tearDown(self):
        fl.LS_PY, fl.SHARED_CACHE, fl._run_with_gpu, fl._zoom_video, fl.REPO, fl.LS_BATCH_MAX, fl.run = self.old
        fl.ROOT = self.script

    def todo(self, n):
        return [(f"t_{k:02d}", k * 100, k * 100 + 100, (0, 0, 10)) for k in range(n)]

    def test_alle_stuecke_in_einem_prozess(self):
        log = []
        n = fl.prefetch_chunks(self.todo(5), "w.wav", "g.mp4", self.cache, "id", log.append)
        self.assertEqual(n, 5)
        self.assertEqual(len(list(fl.SHARED_CACHE.glob("*_synced.mp4"))), 5)
        self.assertEqual(list(fl.SHARED_CACHE.glob("*.tmp.mp4")), [])
        # zweiter Aufruf: alles schon im Zwischenspeicher -> nichts zu tun
        self.assertEqual(fl.prefetch_chunks(self.todo(5), "w.wav", "g.mp4", self.cache, "id", log.append), 0)

    def test_stapelgroesse(self):
        fl.LS_BATCH_MAX = 2
        log = []
        fl.prefetch_chunks(self.todo(5), "w.wav", "g.mp4", self.cache, "id", log.append)
        self.assertEqual(sum("Stapel" in x for x in log), 3)

    def test_abbruch_uebernimmt_nur_fertige(self):
        import os
        os.environ["FAKE_STOP_AFTER"] = "2"
        try:
            n = fl.prefetch_chunks(self.todo(4), "w.wav", "g.mp4", self.cache, "id", lambda m: None)
        finally:
            del os.environ["FAKE_STOP_AFTER"]
        self.assertEqual(n, 2)                   # Rest rechnet sync_chunk() einzeln (Rueckfall)
        self.assertEqual(list(fl.SHARED_CACHE.glob("*.tmp.mp4")), [])


if __name__ == "__main__":
    unittest.main()
