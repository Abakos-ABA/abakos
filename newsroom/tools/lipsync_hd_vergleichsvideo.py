"""Vergleichsvideo zu tools/lipsync_hd_vergleich.py (Task 20261023-105317-04c3): Varianten nacheinander, links Studio-
Bild, rechts Mund vergroessert (aus dem Freisteller), oben Beschriftung + Hochrechnung. .venv-lipsync, cwd newsroom."""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from video import freisteller_lipsync as fl  # noqa: E402

WORK = ROOT / "data" / "lipsync_hd_vergleich_20261023"
REPORT = (Path.home() / r"projekte\jarvis\reports\lipsync_hd_vergleich_20261023")
EFF_S = 426.0         # tatsaechlich gelipsyncte Sekunden einer Folge (s5 102/175 Stuecke + Coldopen/Themen/S6)
REAL_A_MIN = 170.0    # gemessener Lipsync-Anteil der Produktion (Variante A, mit GPU-Konkurrenz)
LS_BASE = {5: 63.0, 4: 60.0}   # LatentSync-Zeit ohne GPU-Konkurrenz (B/D/F gemessen), A war durch Konkurrenz auf 83 s aufgeblasen
FONT = r"C\:/Windows/Fonts/arial.ttf"


def norm(v):
    s = v["schritte"]
    ls = LS_BASE[v["steps"]] if v["steps"] in LS_BASE and s["latentsync"] > LS_BASE[v["steps"]] * 1.1 else s["latentsync"]
    return ls + s.get("zoom", 0) + s.get("restore", 0)


def main():
    r = json.loads((WORK / "ergebnis.json").read_text())
    REPORT.mkdir(parents=True, exist_ok=True)
    a = norm(r["A"])
    rows = {}
    faces = np.load(WORK / "A" / "vA_faces.npy")
    cx, cy, sz = faces.mean(0)
    side = int(sz * 0.75) // 2 * 2
    mx, my = int(cx - side / 2), int(cy + 0.36 * sz - side / 2)
    segs = []
    for L, v in r.items():
        g = norm(v)
        rows[L] = dict(titel=v["titel"], gpu_s=round(g, 1), s_pro_s=round(g / v["laenge_s"], 1),
                       folge_idle_min=round(EFF_S * g / v["laenge_s"] / 60), folge_real_min=round(REAL_A_MIN * g / a),
                       gemessen_s=v["gpu_s"])
        t1 = f"{v['titel']}"
        t2 = (f"{rows[L]['s_pro_s']} s Rechenzeit pro s Video  |  Lipsync einer Folge ca. {rows[L]['folge_real_min']} min "
              f"(heute 170 min)  |  Folge gesamt ca. {(264 - 170 + rows[L]['folge_real_min']) / 60:.1f} h (Ziel 3 h)")
        (WORK / f"t1_{L}.txt").write_text(t1, encoding="utf-8")
        (WORK / f"t2_{L}.txt").write_text(t2, encoding="utf-8")
        out = WORK / f"seg_{L}.mp4"
        dt = lambda f, y, sz_: (f"drawtext=fontfile='{FONT}':textfile='{(WORK / f).as_posix().replace(':', chr(92) + ':')}':"
                                f"fontcolor=white:fontsize={sz_}:x=20:y={y}")
        fc = (f"color=c=0x101010:s=1440x720:r=25[bg];"
              f"[0:v]scale=960:540:flags=lanczos[s];"
              f"[1:v]crop={side}:{side}:{mx}:{my},format=rgb24,scale=480:480:flags=lanczos[m];"
              f"[bg][s]overlay=0:120[b1];[b1][m]overlay=960:120,{dt(f't1_{L}.txt', 18, 40)},{dt(f't2_{L}.txt', 72, 24)},"
              f"drawtext=fontfile='{FONT}':text='Mund vergroessert':fontcolor=0xcccccc:fontsize=24:x=965:y=96[v]")
        subprocess.run([fl.FFMPEG, "-y", "-v", "error", "-i", v["studio"], "-i", v["freisteller"], "-i", str(WORK / "clip.wav"),
                        "-filter_complex", fc, "-map", "[v]", "-map", "2:a", "-shortest", "-c:v", "libx264", "-preset", "medium",
                        "-crf", "22", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", str(out)], check=True)
        segs.append(out)
    lst = WORK / "liste.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in segs))
    final = REPORT / "lipsync_hd_vergleich.mp4"
    subprocess.run([fl.FFMPEG, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(final)], check=True)
    (REPORT / "ergebnis.json").write_text(json.dumps(dict(zeilen=rows, roh=r, eff_lipsync_s=EFF_S), indent=1, ensure_ascii=False))
    print(json.dumps(rows, indent=1, ensure_ascii=False), final, final.stat().st_size / 1e6, "MB")


if __name__ == "__main__":
    main()
