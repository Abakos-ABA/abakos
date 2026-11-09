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


DECKEL_MB = 10500             # wie gpu_budget.STEP_MB["enhance"]: gemessen ~8,8 GB Spitze (30-s-Fenster)


def vram_deckeln(device) -> None:
    """Haelt den PyTorch-Cache unter der Anmeldung: ohne Deckel wuchs er auf einer freien Karte auf ~13 GB (Messung 04.11.,
    Vorfall 09.11.2026: 13177 MB belegt, Karte voll). Am Deckel gibt der Allokator zuerst seinen Cache zurueck."""
    if device != "cuda" or not torch.cuda.is_available():
        return
    torch.cuda.set_per_process_memory_fraction(min(1.0, DECKEL_MB * 1024**2 / torch.cuda.get_device_properties(0).total_memory))


def lauf(src, dst, mode, lambd, device):
    vram_deckeln(device)
    wav, sr = torchaudio.load(src)
    wav = wav.mean(0)
    if mode == "denoise":
        out, osr = denoise(wav, sr, device)
    else:
        out, osr = enhance(wav, sr, device, nfe=32, solver="midpoint", lambd=lambd, tau=0.5)
    torchaudio.save(dst, out[None].clamp(-1, 1), osr, encoding="PCM_S", bits_per_sample=16)
    peak_mb = torch.cuda.max_memory_allocated() / 1024**2 if device == "cuda" else 0.0
    print(dst, osr, device, f"{peak_mb:.0f}MB", flush=True)


def vram_cache_freigeben() -> None:
    """Zwischen zwei Auftraegen den PyTorch-Zwischenspeicher zurueckgeben (wie tts/chatterbox_worker.py): der Enhance-
    Dauerprozess hielt sonst ~13 GB VRAM, obwohl ein Auftrag nur ~8,8 GB Spitze braucht und er die meiste Zeit wartet
    (Messung 04.11.2026). Das Modell bleibt geladen."""
    try:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:  # noqa: BLE001
        pass


def server():
    """Dauerbetrieb (tts/veredelung.py, wie tts/chatterbox_worker.py --server): Modell bleibt geladen, je Auftrag eine
    JSON-Zeile [src, dst, mode, lambd, device] auf stdin, Antwort "@@FERTIG <rc>"."""
    import json
    import traceback
    print("@@FERTIG bereit", flush=True)
    for zeile in sys.stdin:
        zeile = zeile.strip()
        if zeile == "quit":
            break
        if not zeile:
            continue
        rc = 0
        try:
            src, dst, mode, lambd, device = json.loads(zeile)
            lauf(src, dst, mode, float(lambd or 0.5), device or ("cuda" if torch.cuda.is_available() else "cpu"))
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            rc = 1
        finally:
            vram_cache_freigeben()
        print(f"@@FERTIG {rc}", flush=True)


if __name__ == "__main__":
    if sys.argv[1:2] == ["--server"]:
        server()
    else:
        src, dst, mode = sys.argv[1], sys.argv[2], sys.argv[3]
        lambd = float(sys.argv[4]) if len(sys.argv) > 4 and sys.argv[4] else 0.5
        device = (sys.argv[5] if len(sys.argv) > 5 and sys.argv[5] else os.environ.get("ENHANCE_DEVICE")) or             ("cuda" if torch.cuda.is_available() else "cpu")
        lauf(src, dst, mode, lambd, device)
