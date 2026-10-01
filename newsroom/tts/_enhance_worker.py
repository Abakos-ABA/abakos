"""Laeuft in .venv-enhance (torch 2.1 CPU + resemble-enhance, MIT). Holt die Hoehen zurueck, die Chatterbox nicht
liefert (Task 20261001-165559-5e26: Referenzstimme -56 dB ueber 8 kHz, Chatterbox-Ausgabe -70,6 dB). CPU-only,
~2 Min je 14 s Ton (keine CUDA-Version von torch in diesem venv) - aufgerufen von tts/veredelung.py.

    .venv-enhance/Scripts/python.exe tts/_enhance_worker.py <in.wav> <out.wav> enhance|denoise [lambd]
"""
import pathlib
pathlib.PosixPath = pathlib.WindowsPath   # Windows-Pfade in den mitgelieferten Checkpoints
import sys
import torch
import torchaudio
from resemble_enhance.enhancer.inference import enhance, denoise

src, dst, mode = sys.argv[1], sys.argv[2], sys.argv[3]
wav, sr = torchaudio.load(src)
wav = wav.mean(0)
if mode == "denoise":
    out, osr = denoise(wav, sr, "cpu")
else:
    lambd = float(sys.argv[4]) if len(sys.argv) > 4 else 0.5
    out, osr = enhance(wav, sr, "cpu", nfe=32, solver="midpoint", lambd=lambd, tau=0.5)
torchaudio.save(dst, out[None].clamp(-1, 1), osr, encoding="PCM_S", bits_per_sample=16)
print(dst, osr)
