"""Laeuft in .venv-enhance (torch 2.1 + resemble-enhance, MIT; seit 01.10. torch 2.1.1+cu121, Task 98b7). Holt die
Hoehen zurueck, die Chatterbox nicht liefert (Task 20261001-165559-5e26: Referenzstimme -56 dB ueber 8 kHz,
Chatterbox-Ausgabe -70,6 dB). Geht auf die GPU (RTX 4090), deutlich schneller als CPU; faellt auf CPU zurueck, wenn
kein CUDA da ist oder ENHANCE_DEVICE=cpu erzwungen wird - aufgerufen von tts/veredelung.py ueber jarvis/tools/gpu_queue.py.

    .venv-enhance/Scripts/python.exe tts/_enhance_worker.py <in.wav> <out.wav> enhance|denoise [lambd] [device]
    device: cuda|cpu, Default cuda wenn verfuegbar (auch per Umgebungsvariable ENHANCE_DEVICE erzwingbar)
"""
import os
import pathlib
pathlib.PosixPath = pathlib.WindowsPath   # Windows-Pfade in den mitgelieferten Checkpoints
import sys
import torch
import torchaudio
from resemble_enhance.enhancer.inference import enhance, denoise

src, dst, mode = sys.argv[1], sys.argv[2], sys.argv[3]
lambd = float(sys.argv[4]) if len(sys.argv) > 4 and sys.argv[4] else 0.5
device = (sys.argv[5] if len(sys.argv) > 5 and sys.argv[5] else os.environ.get("ENHANCE_DEVICE")) or \
    ("cuda" if torch.cuda.is_available() else "cpu")
wav, sr = torchaudio.load(src)
wav = wav.mean(0)
if mode == "denoise":
    out, osr = denoise(wav, sr, device)
else:
    out, osr = enhance(wav, sr, device, nfe=32, solver="midpoint", lambd=lambd, tau=0.5)
torchaudio.save(dst, out[None].clamp(-1, 1), osr, encoding="PCM_S", bits_per_sample=16)
peak_mb = torch.cuda.max_memory_allocated() / 1024**2 if device == "cuda" else 0.0
print(dst, osr, device, f"{peak_mb:.0f}MB")
