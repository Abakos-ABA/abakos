"""Lipsync-Laufzeit-Vergleich: Rechenschritte 12 (bisheriger Standard) gegen 8, je mit und ohne gebuendeltes
Real-ESRGAN/GFPGAN (config.settings.NEWS_WELTLAGE_GESICHT_HD_BATCH, Task 20261010-081311-ca9f gebaut, nie echt
gemessen). Guidance bleibt in allen Varianten fest bei config.settings.NEWS_WELTLAGE_LIPSYNC_GUIDANCE (2.0,
Marlons feste Vorgabe) - nur STEPS und HD_BATCH aendern sich. Marlons Auftrag 14.10.2026 (Telegram): Weltlage-Folgen
brauchen zu lang (~11 h), Themen sind bei Veroeffentlichung veraltet; Ziel moeglichst nahe an 2 h Gesamtproduktion,
Hauptposten ist die LatentSync-Rechenzeit.

Nutzt denselben 7-s-Testton (test_wav aus lipsync_upscale_vergleich) wie die bisherigen Lipsync-Vergleiche, stehende
Pose, HD-Pfad an (Produktionsstandard). Misst je Variante: reine Rechenzeit (lipsync_freisteller), SyncNet-Versatz/
Konfidenz (tools/lipsync_messung.py) und die Mundbewegungs-Kennzahl (wie Marlons bisherige Lipsync-Vergleiche).
GPU: ein Platz in der zentralen Warteschlange (Prio 3), derselbe Name wie video/freisteller_lipsync.

    .venv-lipsync\\Scripts\\python.exe tools\\lipsync_steps_vergleich.py
"""
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from video import freisteller_lipsync as fl  # noqa: E402
from lipsync_upscale_vergleich import test_wav, mouth_motion, syncnet  # noqa: E402

WORK = ROOT / "data" / "lipsync_steps_20261014"
REPORT = Path(r"C:\Users\Marlon\projekte\jarvis\reports\lipsync_steps_vergleich_20261014")
TASK = os.environ.get("JARVIS_TASK_ID", "20261014-192918-98bb")
PROGRESS = Path(r"C:\Users\Marlon\projekte\jarvis\tasks") / f"{TASK}.progress.md"
POSE = "stehend"
# (Name, Schritte, HD_BATCH)
VARIANTEN = [("steps12_batch1_basis", 12, 1), ("steps8_batch1", 8, 1), ("steps8_batch4", 8, 4),
            ("steps12_batch4", 12, 4)]


def progress(text: str):
    print(text, flush=True)
    try:
        PROGRESS.write_text(text, encoding="utf-8")
    except OSError:
        pass


def render(wav: Path, length: float) -> dict:
    res = {}
    for name, steps, batch in VARIANTEN:
        fl.STEPS = steps
        fl.HD_BATCH = batch
        fl._ZOOM_VRAM_MB = 3000 if batch <= 1 else min(3000 + 350 * (batch - 1), 9000)
        fl._RESTORE_VRAM_MB = 2000 if batch <= 1 else min(2000 + 250 * (batch - 1), 6000)
        work = WORK / name
        tag = f"vgl_{name}"
        progress(f"Lipsync-Vergleich: {name} (Schritte {steps}, HD_BATCH {batch}) laeuft, {length:.0f} s Ton.")
        t = time.time()
        fs, n = fl.lipsync_freisteller(POSE, wav, 0.0, length, work, tag)
        dt = time.time() - t
        fl.composite_studio(POSE, fs, n, work / f"{tag}_studio.mp4")
        faces = np.load(work / f"{tag}_faces.npy")
        res[name] = dict(steps=steps, hd_batch=batch, sekunden_lipsync=round(dt, 1), bilder=n,
                        mund_bewegung=round(mouth_motion(fs, faces, n), 2))
        res[name]["syncnet"] = syncnet(fs, wav, work / f"{tag}_faces.npy")
        progress(f"{name} fertig: {dt:.0f} s, Mund-Bewegung {res[name]['mund_bewegung']}, "
                 f"SyncNet {res[name]['syncnet']}.")
        print(json.dumps(res[name], ensure_ascii=False), flush=True)
    return res


def main():
    # Kein aeusseres gpu_budget.hold() fuer den ganzen Lauf: fl.lipsync_freisteller() reserviert seit dem
    # 02.10.2026-Umbau (_run_with_gpu, Task fe9f) selbst nur noch je einzelne GPU-Operation (Zoom/LatentSync/
    # Nachzeichnung). Ein zusaetzliches hold() hier wuerde doppelt buchen (eigene Anmeldung + die der inneren
    # Operationen gleichzeitig) und sich damit selbst blockieren (beobachtet 14.10., Platz fuer 11 GB gesucht,
    # obwohl nur noch 7,6 von 22 GB Budget frei waren, weil das aeussere hold() schon 14 GB davon hielt).
    WORK.mkdir(parents=True, exist_ok=True)
    REPORT.mkdir(parents=True, exist_ok=True)
    wav, length = test_wav()
    res = {"testton": dict(datei=str(wav), sekunden=length)}
    res["varianten"] = render(wav, length)
    (REPORT / "ergebnis.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    progress("Lipsync-Laufzeit-Vergleich fertig, Ergebnis in ergebnis.json.")
    print(json.dumps(res, indent=1, ensure_ascii=False))
    print("FERTIG", flush=True)


if __name__ == "__main__":
    main()
