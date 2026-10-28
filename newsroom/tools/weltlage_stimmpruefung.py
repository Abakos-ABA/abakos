"""Weltlage Kompakt - Stimmen-Nachweis im FERTIGEN Video (rexemre 30.09.2026, nach zwei Folgen, die angeblich
umgestellt waren und doch «die alte Stimme» hatten).

Die Eingangspruefung (tools/weltlage_tts.pruefe_stimme) belegt nur, dass die audio/<id>.wav vom Chatterbox-Klon
stammen. Diese Pruefung belegt zusaetzlich, dass genau diese Dateien im fertigen Video an der richtigen Stelle zu
hoeren sind - also keine alte Tonspur, kein Cache, keine eingefrorene Szene mit anderer Stimme dazwischengerutscht:
pro Sprechszene wird der Ton aus dem Video geschnitten und mit der nachgewiesenen Quelldatei kreuzkorreliert
(Folge 30.09. b: 0,938-0,983; fremde Aufnahme derselben Stimme: < 0,3). Ergebnis pro Szene samt Engine, Referenz-
Hash und wav-Hash steht in <video>_stimmen.json. Faellt eine Szene durch, benennt weltlage_rohschnitt.py das Video in
<name>_UNGUELTIG.mp4 um und bricht ab - es darf dann nicht verschickt werden.

    python tools/weltlage_stimmpruefung.py <video.mp4>     # Nachpruefung anhand <video>_stimmen.json
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from weltlage_tts import REF_SHA256, pruefe_stimme, sha256

SR = 16000
MIN_KORRELATION = 0.8
SUCHFENSTER_S = 0.5

_ff = next(iter(Path(os.environ["LOCALAPPDATA"]).glob("Microsoft/WinGet/Packages/Gyan.FFmpeg*/*/bin")), None)
FFMPEG = str(_ff / "ffmpeg.exe") if _ff else "ffmpeg"


def _lade(pfad: Path) -> np.ndarray:
    roh = subprocess.run([FFMPEG, "-v", "error", "-i", str(pfad), "-vn", "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(roh, dtype=np.int16).astype(np.float64)


def korrelation(video_ton: np.ndarray, start: float, laenge: float, quelle: np.ndarray, pre: float) -> float:
    """Normierte Kreuzkorrelation der Quelle mit dem Videoausschnitt, bestes Versatz im Fenster um `pre`."""
    a = int(max(0.0, start - SUCHFENSTER_S) * SR)
    seg = video_ton[a:int((start + laenge + SUCHFENSTER_S) * SR)]
    soll = int((start + pre) * SR) - a
    # Quelle nur so lang, dass das ganze Suchfenster um `soll` Platz hat. Frueher q = quelle[:len(seg)-1]: bei einer
    # Szene ab 0 s (Cold Open, vorne kein Suchfenster) mit Quelle laenger als die Szene blieb nur Versatz 0..1 Sample
    # statt `pre` -> Korrelation ~0 trotz richtigem Ton (Vorfall 08.10.2026, Folge 07.10. 19:00).
    q = quelle[:max(0, len(seg) - soll - int(SUCHFENSTER_S * SR))]
    if len(q) < SR // 2 or not q.any() or not seg.any():
        return 0.0
    n = 1 << int(np.ceil(np.log2(len(seg) + len(q))))
    c = np.fft.irfft(np.fft.rfft(seg, n) * np.conj(np.fft.rfft(q, n)), n)
    lo, hi = max(0, soll - int(SUCHFENSTER_S * SR)), min(len(seg) - len(q), soll + int(SUCHFENSTER_S * SR))
    if hi < lo:
        return 0.0
    k = lo + int(np.argmax(c[lo:hi + 1]))
    fenster = seg[k:k + len(q)]
    return float(c[k] / (np.linalg.norm(fenster) * np.linalg.norm(q) + 1e-9))


def pruefe_video(video: Path, szenen: list[dict]) -> dict:
    """szenen: [{label, start, laenge, wav, pre}] - wav = die mit Nachweis erzeugte Chatterbox-Datei der Szene."""
    ton = _lade(video)
    ergebnis = []
    for s in szenen:
        wav = Path(s["wav"])
        eintrag = {**s, "wav": str(wav)}
        fehler = pruefe_stimme(wav)
        if fehler:
            eintrag.update(ok=False, fehler=fehler)
        else:
            meta = json.loads(wav.with_suffix(".tts.json").read_text(encoding="utf-8"))
            k = korrelation(ton, s["start"], s["laenge"], _lade(wav), s["pre"])
            eintrag.update(engine=meta["engine"], ref_sha256=meta["ref_sha256"], wav_sha256=meta["wav_sha256"],
                           korrelation=round(k, 3), ok=k >= MIN_KORRELATION)
            if not eintrag["ok"]:
                eintrag["fehler"] = f"Ton im Video passt nicht zur Chatterbox-Datei (Korrelation {k:.3f})"
        ergebnis.append(eintrag)
    bericht = {"video": str(video), "video_sha256": sha256(video), "stimme_ref_sha256": REF_SHA256,
               "min_korrelation": MIN_KORRELATION, "ok": bool(ergebnis) and all(e["ok"] for e in ergebnis),
               "szenen": ergebnis}
    video.with_name(video.stem + "_stimmen.json").write_text(json.dumps(bericht, indent=1, ensure_ascii=False),
                                                            encoding="utf-8")
    return bericht


def zusammenfassung(bericht: dict) -> str:
    zeilen = [f"  {'ok ' if e['ok'] else 'FEHLER'} {e['label']}: " +
              (f"{e['engine']}, Korrelation {e['korrelation']}" if "korrelation" in e else "") +
              (f" - {e['fehler']}" if e.get("fehler") else "") for e in bericht["szenen"]]
    kopf = "STIMMEN OK: alle Sprechszenen nachweislich Chatterbox-Klon" if bericht["ok"] else "STIMMEN FEHLER"
    return kopf + "\n" + "\n".join(zeilen)


if __name__ == "__main__":
    v = Path(sys.argv[1])
    alt = json.loads(v.with_name(v.stem + "_stimmen.json").read_text(encoding="utf-8"))
    b = pruefe_video(v, [{k: e[k] for k in ("label", "start", "laenge", "wav", "pre")} for e in alt["szenen"]])
    print(zusammenfassung(b))
    sys.exit(0 if b["ok"] else 1)
