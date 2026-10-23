"""Lipsync-HD-Vergleich (Task 20261023-105317-04c3): ein Sprechausschnitt der Folge 23.10. 00:00 in Varianten
A voll (Stufe 2 + HD), B ohne GFPGAN-Nachzeichnen, C ohne Real-ESRGAN, D ohne beide HD-Stufen, E Stufe 3 (+HD),
F Stufe 3 ohne HD. Nur Modulvariablen/Funktionen im eigenen Prozess gepatcht, Produktion unveraendert. GPU ueber
gpu_budget.slot mit Prio 4 und derselben excl-Sperre wie die Produktion. Aufruf (.venv-lipsync, cwd newsroom):
    python tools\lipsync_hd_vergleich.py [A B ...]
"""
import contextlib
import json
import os
import sys
import time
import wave
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from video import freisteller_lipsync as fl  # noqa: E402
from video import gesicht_hd  # noqa: E402

WORK = ROOT / "data" / "lipsync_hd_vergleich_20261023"
REPORT = Path(r"C:\Users\Marlon\projekte\jarvis\reports\lipsync_hd_vergleich_20261023")
PROGRESS = Path(r"C:\Users\Marlon\projekte\jarvis\tasks\20261023-105317-04c3.progress.md")
WAV_SRC = ROOT / "data" / "weltlage_20261023_0000" / "_schnitt" / "_freisteller" / "s5_ton.wav"
POSE = "sitz"
START, END = 13.12, 21.0     # Schnittpunkte 328/525 (leise Stellen der Produktion), ~7,9 s Moderation

# (Buchstabe, Titel, steps, guidance, zoom, hd, esrgan, gfp_out)
VAR = {
    "A": ("A  heute: Stufe 2 + volle HD", 5, 1.5, 768, True, True, True),
    "B": ("B  ohne GFPGAN-Mund-Nachzeichnen", 5, 1.5, 768, True, True, False),
    "C": ("C  ohne Real-ESRGAN-Hochskalierung", 5, 1.5, 768, True, False, True),
    "D": ("D  ohne beide HD-Stufen", 5, 1.5, 768, False, False, False),
    "E": ("E  Stufe 3 (4 Schritte) + volle HD", 4, 1.2, 512, True, True, True),
    "F": ("F  Stufe 3 + ohne HD", 4, 1.2, 512, False, False, False),
}

_orig_esrgan_many = gesicht_hd.esrgan_many
_orig_restore = gesicht_hd.restore
_state = {"esrgan": True, "gfp_out": True, "t": {}}


def progress(t):
    print(t, flush=True)
    try:
        PROGRESS.write_text(t, encoding="utf-8")
    except OSError:
        pass


def _esrgan_many(frames, scale, tile=384, pad=16, batch=1):
    if _state["esrgan"]:
        return _orig_esrgan_many(frames, scale, tile, pad, batch)
    return [cv2.resize(f, (f.shape[1] * scale, f.shape[0] * scale), interpolation=cv2.INTER_LANCZOS4) for f in frames]


def _restore(frames, weight, batch=1):
    if weight == gesicht_hd.GFP_OUT and not _state["gfp_out"]:
        return frames
    return _orig_restore(frames, weight, batch=batch)


def _run_with_gpu(step_name, vram_mb, log, fn):
    gb = fl._gpu_budget()
    t0 = time.time()
    with gb.slot("lipsync", name=f"lipsync HD-Vergleich {step_name} (Task 04c3)", prio=4, vram_mb=vram_mb,
                 progress=lambda w, m: log(f"  GPU-Warteschlange ({m:.0f} min): {w}"), excl=fl.LS_EXCL):
        t1 = time.time()
        r = fn()
        d = _state["t"]
        d[step_name] = d.get(step_name, 0) + time.time() - t1
        d["warten"] = d.get("warten", 0) + t1 - t0
        return r


def clip():
    WORK.mkdir(parents=True, exist_ok=True)
    out = WORK / "clip.wav"
    with wave.open(str(WAV_SRC)) as w:
        sr, nch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
        w.setpos(int(START * sr))
        data = w.readframes(int((END - START) * sr))
    with wave.open(str(out), "wb") as w:
        w.setnchannels(nch); w.setsampwidth(sw); w.setframerate(sr); w.writeframes(data)
    return out, END - START


def main():
    letters = [a for a in sys.argv[1:] if a in VAR] or list(VAR)
    wav, length = clip()
    gesicht_hd.esrgan_many = _esrgan_many
    gesicht_hd.restore = _restore
    fl._run_with_gpu = _run_with_gpu
    resf = WORK / "ergebnis.json"
    res = json.loads(resf.read_text()) if resf.exists() else {}
    for L in letters:
        titel, steps, guid, zoom, hd, esr, gout = VAR[L]
        fl.STEPS, fl.GUIDANCE, fl.ZOOM, fl.HD = steps, guid, zoom, hd
        _state.update(esrgan=esr, gfp_out=gout, t={})
        fl.SHARED_CACHE = WORK / f"cache_{L}"
        work = WORK / L
        progress(f"HD-Vergleich: Variante {L} laeuft ({titel}).")
        t0 = time.time()
        fs, n = fl.lipsync_freisteller(POSE, wav, START, length, work, f"v{L}", print)
        gpu_s = sum(v for k, v in _state["t"].items() if k != "warten")
        studio = work / f"v{L}_studio.mp4"
        fl.composite_studio(POSE, fs, n, studio)
        res[L] = dict(titel=titel, steps=steps, guidance=guid, zoom=zoom, hd=hd, esrgan=esr, gfp_out=gout,
                      laenge_s=round(length, 2), gpu_s=round(gpu_s, 1), wartezeit_s=round(_state["t"].get("warten", 0), 1),
                      wand_s=round(time.time() - t0, 1), schritte={k: round(v, 1) for k, v in _state["t"].items()},
                      s_pro_s_video=round(gpu_s / length, 2), studio=str(studio), freisteller=str(fs))
        resf.write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
        progress(f"Variante {L} fertig: {gpu_s:.0f} s GPU-Rechenzeit fuer {length:.1f} s Video ({gpu_s / length:.1f} s/s).")
    print("FERTIG", flush=True)


if __name__ == "__main__":
    main()
