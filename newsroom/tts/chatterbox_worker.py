"""Runs inside the separate .venv-tts (torch + chatterbox-tts, MIT). Called by tts_client.py:

    .venv-tts/Scripts/python.exe tts/chatterbox_worker.py --text-file in.txt --out out.wav --lang de [--ref voice.wav]

Chatterbox Multilingual (Resemble AI, MIT, 23 languages) with optional zero-shot voice cloning
from a reference wav - the channel's host voice is a fixed reference file so every video sounds
like the same person. Long texts are synthesised sentence by sentence and concatenated (the model
is happiest with < ~300 characters at a time).

--veredeln (Stimm-Veredelung Variante A, rexemres Wahl 01.10.2026, Task 20261001-165559-5e26/180145-c47f):
erzwingt echte Satz-fuer-Satz-Erzeugung (ignoriert --max-chars) und ersetzt die feste 0,25-s-Stille zwischen den
Saetzen durch eine leicht zufaellige Pause (0,30-0,42 s) mit einem leisen synthetischen Einatmer. Das holt die
Hoehen noch nicht zurueck - das macht tts/veredelung.py danach mit Resemble Enhance in .venv-enhance.

--prosodie (18.10.2026, rexemre: Stimme "zu monoton und unecht", Task ad90): Satzmelodie-Plan je Satz statt fester
Parameter. prosodie_plan() gibt jedem Satz nach Satzart eigene exaggeration/Tempo/Pause (Frage: mehr Ausdruck,
etwas langsamer, laengere Pause; kurzer Schlusssatz/Ausruf: mehr Ausdruck; lange Saetze: etwas zuegiger), mit
kleiner Streuung, damit nie zwei Saetze gleich klingen. Das relative Tempo je Satz kommt per ffmpeg atempo
(tonhoehenneutral) dazu; das Grundtempo des Profils (1.15) wendet tts_client._tempo danach wie bisher an.
"""
import argparse
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np
import torch
import torchaudio


def _atem(sr: int, dauer: float, pegel_db: float, rng: np.random.Generator) -> np.ndarray:
    """Leiser Einatmer: baendlimitiertes Rauschen (~1,6 kHz) mit weicher Huellkurve (synthetisch, keine Aufnahme)."""
    n = int(dauer * sr)
    w = rng.normal(0, 1, n)
    spec = np.fft.rfft(w)
    f = np.fft.rfftfreq(n, 1 / sr)
    spec = spec * np.exp(-((np.log(f + 1) - np.log(1600)) ** 2) / (2 * 0.55 ** 2))
    w = np.fft.irfft(spec, n)
    env = np.sin(np.linspace(0, np.pi, n)) ** 1.5 * np.linspace(0.6, 1, n)
    w = w * env
    return (w / (np.abs(w).max() + 1e-9) * 10 ** (pegel_db / 20)).astype(np.float32)


def pause_mit_atmer(sr: int, peak: float, rng: np.random.Generator, dauer: float | None = None) -> torch.Tensor:
    """Natuerliche Pause (0,30-0,42 s oder `dauer`) zwischen zwei Saetzen, mit leisem Atmer kurz vor dem naechsten Satz."""
    dauer = float(rng.uniform(0.30, 0.42)) if dauer is None else max(0.12, float(dauer))
    n = int(dauer * sr)
    gap = np.zeros(n, dtype=np.float32)
    b = _atem(sr, min(dauer, 0.32), -34.0, rng) * peak
    start = max(0, n - len(b) - int(0.05 * sr))
    ende = min(n, start + len(b))
    gap[start:ende] += b[: ende - start]
    return torch.from_numpy(gap)[None]


def prosodie_plan(saetze: list[str], ex_basis: float, rng: np.random.Generator) -> list[dict]:
    """Je Satz {ex, tempo, pause_s}. ex_basis = exaggeration des Profils; Tempo relativ (1.0 = Profiltempo)."""
    plan = []
    for i, s in enumerate(saetze):
        woerter = len(s.split())
        ex, tempo, pause = ex_basis, 1.0, float(rng.uniform(0.30, 0.42))
        if s.rstrip().endswith("?"):
            ex, tempo, pause = ex_basis + 0.15, 0.96, float(rng.uniform(0.45, 0.58))
        elif s.rstrip().endswith("!"):
            ex, pause = ex_basis + 0.2, float(rng.uniform(0.40, 0.50))
        elif woerter <= 6:
            ex, tempo, pause = ex_basis + 0.12, 0.97, float(rng.uniform(0.38, 0.50))
        elif woerter >= 18:
            tempo = 1.03
        if ":" in s:
            ex += 0.05
        if i == len(saetze) - 1:
            pause = 0.0
        plan.append({"ex": round(min(0.9, ex + float(rng.uniform(-0.04, 0.04))), 3),
                     "tempo": round(tempo * float(rng.uniform(0.985, 1.015)), 3), "pause_s": round(pause, 3)})
    return plan


def _atempo(wav: torch.Tensor, sr: int, tempo: float) -> torch.Tensor:
    """Relatives Satztempo per ffmpeg atempo (WSOLA, tonhoehenneutral); ohne ffmpeg unveraendert."""
    if abs(tempo - 1.0) < 0.004:
        return wav
    d = Path(tempfile.mkdtemp())
    src, dst = d / "a.wav", d / "b.wav"
    torchaudio.save(str(src), wav, sr, encoding="PCM_S", bits_per_sample=16)
    ff = next(iter(Path(os.environ.get("LOCALAPPDATA", "")).glob("Microsoft/WinGet/Packages/Gyan.FFmpeg*/*/bin")), None)
    r = subprocess.run([str(ff / "ffmpeg.exe") if ff else "ffmpeg", "-y", "-v", "error", "-i", str(src), "-af",
                        f"atempo={tempo}", "-c:a", "pcm_s16le", str(dst)], capture_output=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode or not dst.exists():
        return wav
    out, _ = torchaudio.load(str(dst))
    for f in (src, dst):
        f.unlink(missing_ok=True)
    d.rmdir()
    return out


def split_sentences(text: str, max_chars: int = 280) -> list[str]:
    parts = [p.strip() for p in re.split(r"(?<=[.!?…])\s+", text.strip()) if p.strip()]
    out, cur = [], ""
    for p in parts:
        if cur and len(cur) + len(p) + 1 > max_chars:
            out.append(cur)
            cur = p
        else:
            cur = f"{cur} {p}".strip()
    if cur:
        out.append(cur)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text-file", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--lang", default="de")
    ap.add_argument("--ref", default=None)
    ap.add_argument("--exaggeration", type=float, default=0.4)
    ap.add_argument("--cfg", type=float, default=0.5)
    ap.add_argument("--temperature", type=float, default=0.8)       # Chatterbox-Standard
    ap.add_argument("--max-chars", type=int, default=280)          # Textlaenge pro Aufruf (120 = satzweise)
    ap.add_argument("--seed", type=int, default=None)              # fester Seed = reproduzierbar
    ap.add_argument("--veredeln", action="store_true")             # Variante A: Satz fuer Satz, Pause+Atmer statt fixer Stille
    ap.add_argument("--prosodie", action="store_true")             # Satzmelodie-Plan je Satz (18.10.2026)
    args = ap.parse_args()

    from chatterbox.mtl_tts import ChatterboxMultilingualTTS

    device = "cuda" if torch.cuda.is_available() else "cpu"
    t0 = time.time()
    model = ChatterboxMultilingualTTS.from_pretrained(device=device)
    print(f"model loaded on {device} in {time.time() - t0:.0f}s", flush=True)

    text = open(args.text_file, encoding="utf-8").read()
    chunks = split_sentences(text, 1 if (args.veredeln or args.prosodie) else args.max_chars)
    if args.seed is not None:
        torch.manual_seed(args.seed)
    rng = np.random.default_rng(args.seed if args.seed is not None else 7)
    plan = prosodie_plan(chunks, args.exaggeration, np.random.default_rng(rng.integers(1 << 30))) if args.prosodie else None
    pieces = []
    for i, chunk in enumerate(chunks):
        t = time.time()
        kwargs = {"language_id": args.lang, "exaggeration": plan[i]["ex"] if plan else args.exaggeration,
                  "cfg_weight": args.cfg, "temperature": args.temperature}
        if args.ref:
            kwargs["audio_prompt_path"] = args.ref
        wav = model.generate(chunk, **kwargs).cpu()
        if plan:
            wav = _atempo(wav, model.sr, plan[i]["tempo"])
        pieces.append(wav)
        if i < len(chunks) - 1:
            if plan:
                pieces.append(pause_mit_atmer(model.sr, float(wav.abs().max()), rng, plan[i]["pause_s"]))
            elif args.veredeln:
                pieces.append(pause_mit_atmer(model.sr, float(wav.abs().max()), rng))
            else:
                pieces.append(torch.zeros(1, int(model.sr * 0.25)))
        print(f"chunk {i + 1}/{len(chunks)}: {wav.shape[-1] / model.sr:.1f}s audio in {time.time() - t:.1f}s", flush=True)
    audio = torch.cat(pieces, dim=-1).clamp(-1.0, 1.0)
    # 16-bit PCM on purpose: 32-bit float wavs trip up the stdlib wave module used downstream
    torchaudio.save(args.out, audio, model.sr, encoding="PCM_S", bits_per_sample=16)
    print(f"wrote {args.out}: {audio.shape[-1] / model.sr:.1f}s", flush=True)


if __name__ == "__main__":
    main()
