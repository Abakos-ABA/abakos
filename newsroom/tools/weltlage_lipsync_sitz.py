"""VERALTET seit 29.09.2026 (verstoesst gegen die Freisteller-Regel: Composite in 1280x704, danach hochskaliert).
Ersetzt durch video/freisteller_lipsync.py, eingebaut in tools/weltlage_rohschnitt.py. Nur noch zum Nachvollziehen.

Lipsync fuer Szene 5 (sitzend) eines Weltlage-Rohschnitts, mit dem bestehenden Weg:
roher Sitz-Master (v3 0-12 s + v4-Tail, gruen, Mund zu) -> LatentSync (video/lipsync.sync_segment, pro Meldung)
-> key_host.key_clip -> composite_host._filter_complex (Platzierung/Studio-Loop/Pultmaske wie v4)
-> <test>/_lipsync/sitz_lip_composite.mp4, danach: python tools/weltlage_rohschnitt.py --lip <datei>

Erwartet einen vorherigen Lauf von weltlage_rohschnitt.py (nutzt dessen _schnitt/a*.wav und zeitmarken.txt).
    python tools/weltlage_lipsync_sitz.py [testordner]
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from video import lipsync                     # noqa: E402
import composite_host as ch                   # noqa: E402
import key_host                               # noqa: E402
import gpu_budget                             # noqa: E402
from weltlage_rohschnitt import FFMPEG, dur   # noqa: E402

TG = ROOT / "config" / "brand" / "takes_green"
CHUNK = 7.0
RAW_A, RAW_TAIL, CUT = TG / "weltlage_host_v3_master.mp4", TG / "weltlage_host_v4_tail_raw.mp4", 12.0


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise RuntimeError(r.stderr[-1500:])


def main():
    test = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "weltlage_test_20260929"
    test = test.resolve()
    work = test / "_lipsync"
    work.mkdir(exist_ok=True)
    marks = [l for l in (test / "zeitmarken.txt").read_text(encoding="utf-8").splitlines() if "Szene" in l]
    s5 = [i for i, l in enumerate(marks) if "Szene 5" in l]
    lens = [float(re.search(r"\(([\d.]+) s\)", marks[i]).group(1)) for i in s5]
    wavs = [test / "_schnitt" / f"a{i + 1:02d}.wav" for i in s5]
    total = sum(lens)
    # Szene-5-Ton am Stueck
    s5wav = work / "s5_audio.wav"
    lst = work / "s5_audio.txt"
    lst.write_text("".join(f"file '{w.as_posix()}'\n" for w in wavs), encoding="utf-8")
    run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(s5wav)])
    # roher Sitz-Master 22 s, hart geloopt auf Szenenlaenge (kein Rueckwaertslauf)
    raw22 = work / "sitz_raw22.mp4"
    run([FFMPEG, "-y", "-i", str(RAW_A), "-i", str(RAW_TAIL), "-filter_complex",
         f"[0:v]trim=duration={CUT},setpts=PTS-STARTPTS[a];[1:v]setpts=PTS-STARTPTS[b];[a][b]concat=n=2:v=1:a=0,fps=25[v]",
         "-map", "[v]", "-c:v", "libx264", "-crf", "14", "-pix_fmt", "yuv420p", str(raw22)])
    raw = work / "sitz_raw_loop.mp4"
    run([FFMPEG, "-y", "-stream_loop", "-1", "-i", str(raw22), "-t", f"{total + 1:.3f}", "-c:v", "libx264", "-crf", "14",
         "-pix_fmt", "yuv420p", str(raw)])
    why = gpu_budget.policy("lipsync")   # Spielregel; VRAM-Schaetzung 18 GB ist konservativ, LatentSync lief bisher bei ~16 GB frei
    if why:
        raise SystemExit(f"GPU belegt: {why}")
    gpu_budget.hold("lipsync", name="lipsync weltlage sitz")   # GPU-Warteschlange bis Prozessende (29.09.)
    # Stuecke <= CHUNK s: eine 33-s-Meldung am Stueck lief am 29.09. ueber den VRAM (22 GB) und brach nach 30 min ab
    outs, t, n = [], 0.0, 0
    while t < total - 0.05:
        L = min(CHUNK, total - t)
        if total - (t + L) < 1.0:          # kein Mini-Rest (<1 s wird von sync_segment verworfen)
            L = total - t
        out = work / f"lip_{n:02d}.mp4"
        if not out.exists():
            print(f"lipsync Stueck {n + 1} ({t:.1f}-{t + L:.1f} s von {total:.1f} s) ...", flush=True)
            if not lipsync.sync_segment(f"wk_s5_{n}", s5wav, t, t + L, raw, out, offset=t):
                raise SystemExit(f"lipsync fehlgeschlagen bei Stueck {n + 1}")
        exact = work / f"lip_{n:02d}_exakt.mp4"      # LatentSync-Video ist 0,08 s laenger als der Ton -> sonst Drift
        run([FFMPEG, "-y", "-i", str(out), "-t", f"{L:.3f}", "-vf", "fps=25", "-c:v", "libx264", "-crf", "14",
             "-pix_fmt", "yuv420p", "-c:a", "aac", str(exact)])
        outs.append(exact)
        t += L
        n += 1
    lip = work / "sitz_lip.mp4"
    lst = work / "lip.txt"
    lst.write_text("".join(f"file '{o.as_posix()}'\n" for o in outs), encoding="utf-8")
    run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-vf", "fps=25", "-c:v", "libx264", "-crf", "14",
         "-pix_fmt", "yuv420p", "-c:a", "aac", str(lip)])
    keyed = work / "sitz_lip_keyed.mov"
    key_host.key_clip(lip, keyed)
    p = ch.load_placement()
    final = work / "sitz_lip_composite.mp4"
    run([FFMPEG, "-y", "-stream_loop", "-1", "-i", str(ch.BG_LOOP), "-i", str(keyed), "-loop", "1", "-i", str(ch.DESK_FG),
         "-filter_complex", ch._filter_complex(p), "-map", "[outv]", "-map", "1:a", "-c:v", "libx264", "-crf", "17",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-shortest", str(final)])
    print("FERTIG", final, f"{dur(final):.1f}s (Szene 5 soll {total:.1f}s)", flush=True)


if __name__ == "__main__":
    main()
