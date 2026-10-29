"""Weltlage Kompakt - Masken-Format (rexemre 27.10.2026). Spezifikation: docs/weltlage_maskenformat.md.

Neues Videoformat NEBEN dem Latara-Format (tools/weltlage_rohschnitt.py bleibt unveraendert). Schalter
NEWS_MASKENFORMAT=1 (config/settings.py, Standard 0): tools/weltlage_tageslauf.py ruft dann im Schritt "schnitt"
dieses Skript statt Rohschnitt/Lipsync, der Schritt "broll" entfaellt (B-Roll ist Teil des Formats).

Bausteine
  * Sprecher (Schalter NEWS_MASKEN_FLF=1, Standard 0): Mix aus kurzen Wan-Clips mit gleichem Erst-/Letztbild, tools/maske_flf_mix.py.
  * Sprecher: maskierter Moderator gross im Bild, animierter 5-s-Loop (kein Lipsync). Loop-Quelle:
    config/brand/maskenmoderator/loop.mp4 (Task ea56, Wan), sonst CPU-Loop aus dem Standbild
    config/brand/maskenmoderator/host.png (Kopf/Kapuze/Oberkoerper/Licht, periodisch -> nahtlos).
  * Uhr: Cyber-Noir-Uhr oben mittig, laeuft ab dem Stand der Folge (Slot HH:MM) mit der Folgenzeit weiter.
  * Layouts pro Szenenwechsel: sprecher | pip | voll | quelle | split, Reihenfolge, Laengen, Kamerafahrten,
    Clip-/Bildwahl pro Folge per Seed aus Datum+Slot (nie gleiche Abfolge zweimal).
  * B-Roll: nur Clips aus <folge>/broll (Lizenzliste broll_lizenzen.json, Attribution broll_attribution.txt, nie
    Sender/Agenturen), Schlagzeilen-Screenshots aus <folge>/bilder.json. Jeder Clip/jedes Bild hoechstens einmal.
  * Ton: Stimmen-Dateien (audio/*.wav) in Szenenreihenfolge, unveraendert; Master wie Latara-Format
    (weltlage_rohschnitt.master_ton: linear auf -14 LUFS, Begrenzer -1,5 dBTP). Nur-Pegel-Reparatur: master_erneuern.

    python tools/weltlage_maskenformat.py <folgenordner> [--out datei.mp4] [--max-s 55] [--host loop.mp4|bild.png]
        [--nur-plan] [--seed N]
Nur CPU (ffmpeg libx264), keine GPU-Warteschlange noetig.
"""
import argparse
import hashlib
import json
import math
import os
import random
import re
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
BRAND = ROOT / "config" / "brand"
MASKE = BRAND / "maskenmoderator"
FPS = 25
W, H = 1920, 1080
CYAN, ROT = (0, 229, 255), (255, 42, 61)
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
_ff = next(iter(Path(os.environ.get("LOCALAPPDATA", "")).glob("Microsoft/WinGet/Packages/Gyan.FFmpeg*/*/bin")), None)
FFMPEG = str(_ff / "ffmpeg.exe") if _ff else "ffmpeg"
FONT_B, FONT_R = "C:/Windows/Fonts/consolab.ttf", "C:/Windows/Fonts/consola.ttf"
TAGE = ["MO", "DI", "MI", "DO", "FR", "SA", "SO"]

# Regeln je Layout: Mindest-/Hoechstdauer (s), Gewicht, braucht Medium ("clip"/"bild"/None)
LAYOUTS = {
    "sprecher": dict(min=5.0, max=10.0, gew=3.0, med=None),
    "pip": dict(min=6.0, max=12.0, gew=3.0, med="clip"),
    "voll": dict(min=3.5, max=6.0, gew=2.5, med="clip"),
    "quelle": dict(min=4.0, max=7.0, gew=2.5, med="bild"),
    "split": dict(min=5.0, max=9.0, gew=2.0, med="clip"),
}
KAMERA = {  # Zoom, Mittelpunkt (relativ), Drift (relativ je Segment)
    "weit": (1.00, (0.50, 0.50), (0.0, 0.0)),
    "push": (1.12, (0.50, 0.45), (0.0, 0.0)),
    "links": (1.18, (0.44, 0.45), (0.03, 0.0)),
    "rechts": (1.18, (0.56, 0.45), (-0.03, 0.0)),
    "nah": (1.38, (0.50, 0.38), (0.0, 0.015)),
}


def run(cmd, **kw):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, creationflags=NOWIN, **kw)
    if r.returncode:
        raise RuntimeError(f"{cmd[0]} Exit {r.returncode}: {r.stderr[-800:]}")
    return r.stderr


# ------------------------------------------------------------------ Ton
def szenen_wavs(folge: Path) -> list[Path]:
    def schl(p: Path):
        n = p.stem
        return (0, 0, n) if n == "s_coldopen" else (1, 0, n) if n == "s_themen" else \
            (3, 0, n) if n.startswith("s6") else (2, 0, n)
    return sorted((p for p in (folge / "audio").glob("*.wav")), key=schl)


def wav_dauer(p: Path) -> float:
    import wave
    with wave.open(str(p)) as w:
        return w.getnframes() / w.getframerate()


def pausen(wav: Path, min_s=0.28, db=-34) -> list[float]:
    log = run([FFMPEG, "-i", wav, "-af", f"silencedetect=n={db}dB:d={min_s}", "-f", "null", "-"])
    s, mids = None, []
    for l in log.splitlines():
        if "silence_start" in l:
            s = float(l.split("silence_start:")[1])
        if "silence_end" in l and s is not None:
            mids.append((s + float(l.split("silence_end:")[1].split("|")[0])) / 2)
            s = None
    return mids


def ton_bauen(wavs: list[Path], out: Path, bis: float | None):
    cmd = [FFMPEG, "-v", "error", "-y"]
    for w in wavs:
        cmd += ["-i", w]
    fc = "".join(f"[{i}:a]aresample=48000,aformat=channel_layouts=mono[a{i}];" for i in range(len(wavs)))
    fc += "".join(f"[a{i}]" for i in range(len(wavs))) + f"concat=n={len(wavs)}:v=0:a=1[c]"
    cmd += ["-filter_complex", fc, "-map", "[c]"] + (["-t", f"{bis:.3f}"] if bis else []) + ["-c:a", "pcm_s16le", out]
    run(cmd)


# ------------------------------------------------------------------ Moderator-Loop (CPU-Fallback)
def host_loop_cpu(still: Path, out: Path, sek: float = 5.0):
    """Nahtloser Loop aus einem Standbild: Kopf/Kapuze (weich maskiert) nickt/rollt dezent, Oberkoerper wippt,
    Licht pulsiert links (rotes Licht) und am Fenster. Alle Bewegungen haben ganze Perioden in `sek` -> Anfang = Ende.
    Maske selbst: nur starre Mitbewegung mit dem Kopf, keine Verformung."""
    img = cv2.imread(str(still))
    img = cv2.resize(img, (W, H), interpolation=cv2.INTER_LANCZOS4).astype(np.float32)
    pivot = (965.0, 560.0)
    m = np.zeros((H, W), np.float32)
    cv2.ellipse(m, (960, 300), (330, 300), 0, 0, 360, 1, -1)
    m = cv2.GaussianBlur(m, (0, 0), 40)[..., None]
    xs = np.linspace(0, 1, W, dtype=np.float32)[None, :, None]
    ys = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]
    rotlicht = np.clip(1.2 - xs * 3.0, 0, 1) * (1 - 0.6 * ys)       # links oben
    fenster = np.clip((xs - 0.78) * 4.5, 0, 1)                      # rechts
    n = int(sek * FPS)
    p = subprocess.Popen([FFMPEG, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-crf", "16", "-preset", "fast",
                          "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE, creationflags=NOWIN)
    for i in range(n):
        ph = 2 * math.pi * i / n
        rot = 0.55 * math.sin(ph) + 0.25 * math.sin(2 * ph + 1.0)
        dy = 3.0 * math.sin(2 * ph + 0.4) + 1.5 * math.sin(3 * ph)
        dx = 2.5 * math.sin(ph + 0.8)
        M = cv2.getRotationMatrix2D(pivot, rot, 1.0)
        M[0, 2] += dx
        M[1, 2] += dy
        kopf = cv2.warpAffine(img, M, (W, H), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REFLECT)
        f = img * (1 - m) + kopf * m
        # Oberkoerper wippt (Atem) um die Mitte
        z = 1.0 + 0.004 * math.sin(2 * ph)
        Z = cv2.getRotationMatrix2D((W / 2, H), 0, z)
        f = cv2.warpAffine(f, Z, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        # Licht
        g = 1 + rotlicht * (0.10 * math.sin(ph + 0.3) + 0.04 * math.sin(3 * ph)) + fenster * 0.04 * math.sin(2 * ph + 2)
        f = f * g
        p.stdin.write(np.clip(f, 0, 255).astype(np.uint8).tobytes())
    p.stdin.close()
    p.wait()


def ton_huellkurve(wav: Path, ende: float) -> np.ndarray:
    """Pro Bild (FPS) zwei Werte 0..1: Lautheit (env) und Betonung (acc = schneller Anstieg ueber dem langsamen Mittel)."""
    import wave
    with wave.open(str(wav)) as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32)
        if w.getnchannels() > 1:
            x = x.reshape(-1, w.getnchannels()).mean(1)
    n = int(math.ceil(ende * FPS)) + FPS
    hop = sr // FPS
    x = np.concatenate([x, np.zeros(max(0, (n + 1) * hop - len(x)), np.float32)])   # Ende mit Stille auffuellen
    rms = np.array([math.sqrt(float(np.mean(x[i * hop:(i + 1) * hop] ** 2)) + 1e-9) for i in range(n)], np.float32)
    rms = rms / max(float(np.percentile(rms, 95)), 1.0)
    rms = np.clip(rms, 0, 1.2)
    env = np.zeros(n, np.float32)
    langsam = np.zeros(n, np.float32)
    for i in range(1, n):
        a = 0.55 if rms[i] > env[i - 1] else 0.12          # schnell hoch, langsam runter
        env[i] = env[i - 1] + a * (rms[i] - env[i - 1])
        langsam[i] = langsam[i - 1] + 0.04 * (env[i] - langsam[i - 1])
    acc = np.clip((env - langsam) * 3.0, 0, 1)
    for i in range(1, n):                                  # Betonung weich ausklingen lassen
        acc[i] = max(acc[i], acc[i - 1] * 0.82)
    return np.stack([np.clip(env, 0, 1), acc], 1)


def host_spur(loop: Path, ton: Path, ende: float, out: Path, versatz_s: float = 0.0, bewegung: bool = True):
    """Durchgehende Sprecher-Spur ueber die ganze Folge: Wan-Loop (24 fps, nahtlos) fortlaufend, Startversatz je Folge,
    darauf sprechsynchrone Zusatzbewegung (Kopf nickt/neigt sich dezent an Betonungen, Schultern atmen mit der
    Lautheit). Maske/Mund bleiben starr (nur Starrkoerper-Bewegung des Kopfbereichs, keine Verformung)."""
    cap = cv2.VideoCapture(str(loop))
    fr = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        fr.append(cv2.resize(f, (W, H)) if f.shape[1] != W else f)
    cap.release()
    fps_l = 24.0
    hk = ton_huellkurve(ton, ende) if bewegung else None
    m = np.zeros((H, W), np.float32)
    cv2.ellipse(m, (960, 270), (300, 290), 0, 0, 360, 1, -1)
    m = cv2.GaussianBlur(m, (0, 0), 45)[..., None]
    pivot = (965.0, 560.0)
    n = int(math.ceil(ende * FPS)) + FPS
    p = subprocess.Popen([FFMPEG, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-crf", "14", "-preset", "veryfast",
                          "-g", str(FPS), "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE, creationflags=NOWIN)
    for i in range(n):
        f = fr[int((i / FPS + versatz_s) * fps_l) % len(fr)]
        if hk is not None:
            env, acc = float(hk[i, 0]), float(hk[i, 1])
            sway = math.sin(i / FPS * 0.9)
            f32 = f.astype(np.float32)
            M = cv2.getRotationMatrix2D(pivot, 0.45 * acc * sway + 0.15 * env * math.sin(i / FPS * 1.7), 1.0)
            M[1, 2] += 4.5 * acc
            M[0, 2] += 1.2 * sway * env
            kopf = cv2.warpAffine(f32, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            g = f32 * (1 - m) + kopf * m
            z = 1.0 + 0.0035 * env + 0.002 * acc               # Atem/Schultern an Lautheit
            Z = cv2.getRotationMatrix2D((W / 2, H), 0, z)
            g = cv2.warpAffine(g, Z, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            f = np.clip(g, 0, 255).astype(np.uint8)
        p.stdin.write(f.tobytes())
    p.stdin.close()
    p.wait()


def host_quelle(arg: str | None, work: Path) -> Path:
    c = Path(arg) if arg else None
    if c is None:
        # Wan-Loop nur auf ausdruecklichen Wunsch: er laesst die Maske zu Haut werden und bewegt den Mund (Befund 28.10.)
        for n in (("loop.mp4", "loop_1080.mp4") if os.environ.get("NEWS_MASKEN_WAN_LOOP", "0") == "1" else ()):
            if (MASKE / n).exists():
                return MASKE / n
        c = MASKE / "host.png"
    if c.suffix.lower() in (".mp4", ".mov", ".webm"):
        return c
    out = work / "host_loop_cpu.mp4"
    if not out.exists():
        host_loop_cpu(c, out)
    return out


# ------------------------------------------------------------------ Overlays (PNG, PIL)
def _font(pfad, gr):
    return ImageFont.truetype(pfad, gr)


def uhr_png(hhmm: str, datum: str, out: Path):
    """Cyber-Noir-Uhr: dunkle Glasflaeche, cyan Rahmen mit Eckklammern, rote Live-Marke. ca. 330x118 px."""
    w, h = 330, 118
    im = Image.new("RGBA", (w + 40, h + 40), (0, 0, 0, 0))
    glow = Image.new("RGBA", im.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.rectangle((20, 20, w + 20, h + 20), outline=CYAN + (255,), width=4)
    from PIL import ImageFilter
    glow = glow.filter(ImageFilter.GaussianBlur(7))
    d = ImageDraw.Draw(im)
    d.rectangle((20, 20, w + 20, h + 20), fill=(6, 10, 16, 205))
    im = Image.alpha_composite(im, glow)
    d = ImageDraw.Draw(im)
    d.rectangle((20, 20, w + 20, h + 20), outline=CYAN + (150,), width=1)
    for (x, y, sx, sy) in ((20, 20, 1, 1), (w + 20, 20, -1, 1), (20, h + 20, 1, -1), (w + 20, h + 20, -1, -1)):
        d.line((x, y, x + 26 * sx, y), fill=CYAN + (255,), width=3)
        d.line((x, y, x, y + 26 * sy), fill=CYAN + (255,), width=3)
    d.ellipse((38, 36, 48, 46), fill=ROT + (255,))
    d.text((58, 30), "LIVE-STAND", font=_font(FONT_B, 18), fill=(200, 215, 225, 255))
    d.text((w - 12, 30), datum, font=_font(FONT_R, 18), fill=(150, 170, 185, 255), anchor="ra")
    f = _font(FONT_B, 66)
    for off, col in (((0, 0), CYAN + (70,)),):
        d.text((w // 2 + 20 + off[0], 92), hhmm, font=f, fill=col, anchor="mm", stroke_width=6)
    d.text((w // 2 + 20, 92), hhmm, font=f, fill=(235, 252, 255, 255), anchor="mm")
    d.text((w - 12, h + 4), "MEZ", font=_font(FONT_B, 15), fill=CYAN + (255,), anchor="ra")
    im.save(out)


def binde_png(zeile1: str, zeile2: str, out: Path, breite=1100):
    im = Image.new("RGBA", (breite, 96), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, breite - 1, 95), fill=(6, 10, 16, 215))
    d.rectangle((0, 0, 8, 95), fill=ROT + (255,))
    d.line((8, 0, breite - 1, 0), fill=CYAN + (220,), width=2)
    d.text((28, 12), zeile1, font=_font(FONT_B, 26), fill=CYAN + (255,))
    d.text((28, 52), (zeile2[:78] + "…") if len(zeile2) > 79 else zeile2, font=_font(FONT_R, 26), fill=(235, 240, 245, 255))
    im.save(out)


def logo_png(out: Path):
    lg = BRAND / "logo.png"
    if lg.exists():
        im = Image.open(lg).convert("RGBA")
        im.thumbnail((200, 90))
        im.save(out)
        return True
    return False


# ------------------------------------------------------------------ Planung
def folgen_seed(folge: Path, extra: int | None) -> int:
    return int(hashlib.sha1((folge.name + str(extra or "")).encode()).hexdigest()[:8], 16)


def stand_aus_ordner(folge: Path) -> tuple[str, str, int]:
    """Datum/Slot aus weltlage_JJJJMMTT_HHMM -> (HH:MM, 'MO 26.10.2026', Sekunden seit Mitternacht)."""
    m = re.search(r"(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})", folge.name)
    import datetime as dt
    if not m:
        j = dt.datetime.now()
    else:
        j = dt.datetime(*(int(x) for x in m.groups()))
    return j.strftime("%H:%M"), f"{TAGE[j.weekday()]} {j:%d.%m.%Y}", j.hour * 3600 + j.minute * 60


def medien(folge: Path) -> tuple[list[dict], list[dict]]:
    """(clips, bilder) der Folge. clips: Datei, nr, meldung, urheber, quelle, lizenz, attribution."""
    liz = {}
    lf = folge / "broll_lizenzen.json"
    if lf.exists():
        for k in json.loads(lf.read_text(encoding="utf-8")).get("clips", []):
            liz[int(k["nr"])] = k
    clips = []
    for p in sorted((folge / "broll").glob("clip??_*.mp4")):
        if "_ersatz" in p.stem:
            continue
        nr = int(p.stem[4:6])
        k = liz.get(nr)
        if not k:            # ohne Lizenzeintrag nie einsetzen
            continue
        clips.append(dict(datei=str(p), nr=nr, meldung=k.get("meldung", ""), urheber=k.get("urheber", ""),
                          quelle=k.get("quelle", ""), lizenz=k.get("lizenz", ""), attribution=k.get("attribution", ""),
                          titel=k.get("titel", "")))
    bilder = []
    bf = folge / "bilder.json"
    if bf.exists():
        for lst in json.loads(bf.read_text(encoding="utf-8")).values():
            for b in lst:
                if Path(b.get("png", "")).exists():
                    bilder.append(dict(datei=b["png"], quelle=b.get("source", ""), domain=b.get("domain", ""),
                                       schlagzeile=b.get("schlagzeile") or b.get("title", "")))
    return clips, bilder


def planen(pa: list[float], ende: float, szenen: list[tuple[str, float, float]], clips, bilder, rng: random.Random):
    """Segmentplan nach den Regeln in docs/weltlage_maskenformat.md (Abschnitt 4)."""
    clips, bilder = clips[:], bilder[:]
    rng.shuffle(bilder)
    plan, t, letzte, ohne_med = [], 0.0, [], 0
    kam_letzte = None
    while ende - t > 0.4:
        rest = ende - t
        opts = {}
        for k, v in LAYOUTS.items():
            if letzte and k == letzte[-1]:
                continue
            if v["med"] == "clip" and not clips:
                continue
            if v["med"] == "bild" and not bilder:
                continue
            if not plan and k != "sprecher":
                continue                       # Start immer Sprecher
            if rest < 14 and k != "sprecher":
                continue                       # Schluss immer Sprecher
            g = v["gew"]
            if v["med"] is None and ohne_med >= 1:
                g *= 0.3                       # Sprecher allein nie zweimal bald hintereinander
            if v["med"] and ohne_med == 0 and plan:
                g *= 1.2
            if k == "voll" and letzte[-2:].count("voll"):
                g = 0
            opts[k] = g
        if not opts:
            opts = {"sprecher": 1.0}
        k = rng.choices(list(opts), list(opts.values()))[0] if sum(opts.values()) else "sprecher"
        v = LAYOUTS[k]
        # Schnittpunkt: zufaellige Satzpause im Fenster, sonst Hoechstdauer
        fen = [p for p in pa if t + v["min"] <= p <= t + v["max"]]
        e = rng.choice(fen) if fen else min(t + v["max"], ende)
        if ende - e < 3.0:
            e = ende
        d = round((e - t) * FPS) / FPS
        seg = dict(layout=k, t0=round(t, 3), dauer=d)
        # Szene am Segmentanfang
        sz = next((s[0] for s in szenen if s[1] <= t < s[2]), szenen[-1][0])
        if v["med"] == "clip":
            bev = [c for c in clips if c["meldung"] == sz] or clips
            c = rng.choice(bev)
            clips.remove(c)
            seg["medium"] = c
        elif v["med"] == "bild":
            seg["medium"] = bilder.pop(0)
        # Kamera (Moderator), nie zweimal gleich hintereinander
        kam = rng.choice([x for x in KAMERA if x != kam_letzte])
        kam_letzte = kam
        seg["kamera"] = kam
        seg["pip_seite"] = rng.choice(["links", "rechts"])
        plan.append(seg)
        letzte.append(k)
        ohne_med = ohne_med + 1 if v["med"] is None else 0
        t = e if e > t else t + v["max"]
        if e == ende:
            break
    return plan


# ------------------------------------------------------------------ Segment-Render
def _kamera(kam: str, d: float) -> str:
    z, (cx, cy), (dx, dy) = KAMERA[kam]
    cw, ch = f"iw/{z}", f"ih/{z}"
    x0 = f"(iw*{cx}-iw/{z}/2)"
    y0 = f"(ih*{cy}-ih/{z}/2)"
    return (f"crop=w={cw}:h={ch}:x='max(0,min(iw-iw/{z},{x0}+iw*{dx}*t/{d:.3f}))':"
            f"y='max(0,min(ih-ih/{z},{y0}+ih*{dy}*t/{d:.3f}))',scale={W}:{H}:flags=lanczos,setsar=1")


def segment_rendern(seg: dict, host: Path, work: Path, n: int, clock: dict, logo: Path | None) -> Path:
    """clock: {minute_index: png}. Uhr wechselt mitten im Segment an der Minutengrenze (nur ein Wechsel moeglich)."""
    d, k = seg["dauer"], seg["layout"]
    out = work / f"seg{n:03d}.mp4"
    inp = [FFMPEG, "-v", "error", "-y"] + (["-ss", f"{seg['host_ss']:.3f}", "-i", host] if seg.get("host_ss") is not None else ["-stream_loop", "-1", "-i", host])
    m = seg.get("medium")
    if k in ("pip", "voll", "split"):
        inp += ["-stream_loop", "-1", "-ss", "0", "-i", m["datei"]]
    elif k == "quelle":
        inp += ["-loop", "1", "-framerate", str(FPS), "-i", m["datei"]]
    if k == "quelle":
        b = work / f"binde{n:03d}.png"
        binde_png(f"QUELLE · {m['quelle']}  {m['domain']}", m["schlagzeile"], b)
        inp += ["-loop", "1", "-framerate", str(FPS), "-i", b]
    elif k == "voll":
        b = work / f"binde{n:03d}.png"
        binde_png("SYMBOLBILD", f"{m['urheber'] or m['quelle']} · {m['quelle'].capitalize()} · {m['lizenz']}", b, 900)
        inp += ["-loop", "1", "-framerate", str(FPS), "-i", b]
    # Eingabe-Indizes ermitteln
    n_in = sum(1 for x in inp if x == "-i")  # Eingaben bisher
    ci = n_in          # Uhr-PNGs
    uhren = clock["pngs"]
    for u in uhren:
        inp += ["-i", u]
    li = None
    if logo:
        li = n_in + len(uhren)
        inp += ["-i", logo]
    bi = 2 if k in ("quelle", "voll") else None
    fade = f"format=yuva420p,fade=t=in:st=0:d=0.4:alpha=1,fade=t=out:st={d - 0.4:.2f}:d=0.4:alpha=1"
    fc = []
    if k == "sprecher":
        fc.append(f"[0:v]{_kamera(seg['kamera'], d)}[b]")
    elif k == "pip":
        fc.append(f"[0:v]{_kamera(seg['kamera'], d)}[h]")
        fc.append(f"[1:v]scale=624:351:force_original_aspect_ratio=increase,crop=624:351,fps={FPS},"
                  f"pad=632:359:4:4:color=0x00e5ff,{fade}[p]")
        x = 24 if seg["pip_seite"] == "links" else W - 632 - 24
        fc.append(f"[h][p]overlay={x}:300:eof_action=pass[b]")
    elif k == "voll":
        fc.append(f"[1:v]scale=2112:1188:force_original_aspect_ratio=increase,crop=2112:1188,fps={FPS},"
                  f"zoompan=z='1.0+0.06*on/{int(d * FPS)}':d=1:s={W}x{H}:fps={FPS},{fade}[v]")
        fc.append(f"[0:v]{_kamera('weit', d)}[h]")
        fc.append("[h][v]overlay=0:0:eof_action=pass[bv]")
        fc.append(f"[{bi}:v]{fade}[bd]")
        fc.append("[bv][bd]overlay=60:H-h-70[b]")
    elif k == "quelle":
        fc.append(f"[0:v]{_kamera(seg['kamera'], d)},gblur=sigma=5,eq=brightness=-0.28[h]")
        fc.append(f"[1:v]scale=1120:-2,crop=1120:630:0:0,pad=1128:638:4:4:color=0x00e5ff,{fade}[s]")
        fc.append("[h][s]overlay=(W-w)/2:200:eof_action=pass[bs]")
        fc.append(f"[{bi}:v]{fade}[bd]")
        fc.append("[bs][bd]overlay=(W-w)/2:870[b]")
    elif k == "split":
        fc.append(f"[0:v]crop=960:1080:484:0[l]")
        fc.append(f"[1:v]scale=960:1080:force_original_aspect_ratio=increase,crop=960:1080,fps={FPS}[r]")
        fc.append("[l][r]hstack=inputs=2[hs]")
        fc.append(f"[hs]drawbox=x=958:y=0:w=4:h=1080:color=0x00e5ff@0.9:t=fill[b]")
    # Uhr (ggf. Wechsel an Minutengrenze) und Logo
    cur = "b"
    grenze = clock.get("wechsel")
    for j, _ in enumerate(uhren):
        en = ""
        if len(uhren) == 2:
            en = f":enable='lt(t,{grenze:.3f})'" if j == 0 else f":enable='gte(t,{grenze:.3f})'"
        fc.append(f"[{cur}][{ci + j}:v]overlay=(W-w)/2:14{en}[c{j}]")
        cur = f"c{j}"
    if li is not None:
        fc.append(f"[{cur}][{li}:v]overlay=W-w-36:30[o]")
        cur = "o"
    fc.append(f"[{cur}]format=yuv420p[out]")
    cmd = inp + ["-filter_complex", ";".join(fc), "-map", "[out]", "-t", f"{d:.3f}", "-r", str(FPS),
                 "-c:v", "libx264", "-crf", "18", "-preset", "fast", "-an", out]
    run(cmd)
    return out


def bauen(folge: Path, out: Path, max_s: float | None = None, host_arg: str | None = None, nur_plan: bool = False,
          seed: int | None = None, work: Path | None = None) -> dict:
    work = work or (folge / "_maskenformat")
    work.mkdir(parents=True, exist_ok=True)
    wavs = szenen_wavs(folge)
    if not wavs:
        raise RuntimeError(f"keine Sprechdateien in {folge / 'audio'}")
    szenen, t = [], 0.0
    for w in wavs:
        dd = wav_dauer(w)
        szenen.append((w.stem, t, t + dd))
        t += dd
    voll = work / "ton.wav"
    ton_bauen(wavs, voll, max_s)
    ende = min(t, max_s) if max_s else t
    pa = [p for p in pausen(voll) if p > 3] + [s[1] for s in szenen[1:] if s[1] < ende]
    if max_s:  # Probe: bis zur letzten Satzpause vor max_s schneiden
        c = [p for p in pa if max_s * 0.8 < p <= max_s]
        if c:
            ende = c[-1]
            ton_bauen(wavs, voll, ende)
    pa = sorted(set(round(p, 2) for p in pa))
    clips, bilder = medien(folge)
    rng = random.Random(folgen_seed(folge, seed))
    plan = planen(pa, ende, szenen, clips, bilder, rng)
    erg = dict(folge=str(folge), dauer=ende, segmente=plan, out=str(out))
    anteil = sum(s["dauer"] for s in plan if s["layout"] != "sprecher") / ende
    erg["fremdanteil"] = round(anteil, 2)
    (work / "plan.json").write_text(json.dumps(erg, ensure_ascii=False, indent=1), encoding="utf-8")
    if nur_plan:
        return erg
    host = None
    if host_arg is None and os.environ.get("NEWS_MASKEN_FLF", "0") == "1":
        # Kurze Wan-Clips mit gleichem Erst-/Letztbild (tools/maske_flf_mix.py); zu wenige gute Clips -> CPU-Loop (Rueckfall)
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import maske_flf_mix
        if maske_flf_mix.verfuegbar():
            host = work / "host_spur.mp4"
            if not host.exists():
                try:
                    maske_flf_mix.mix(ende, folgen_seed(folge, seed), host, FFMPEG, W, H, FPS)
                except maske_flf_mix.MundBewegtFehler as e:
                    print(f"{e} -> CPU-Loop (starre Maske)", flush=True)
                    host = None
        else:
            print("NEWS_MASKEN_FLF=1, aber zu wenige geprueften Clips -> CPU-Loop", flush=True)
    if host is None:
        host = host_quelle(host_arg, work)
    if host.name != "host_spur.mp4" and host.suffix.lower() == ".mp4" and os.environ.get("NEWS_MASKEN_SPUR", "1") == "1":
        spur = work / "host_spur.mp4"
        if not spur.exists():
            host_spur(host, voll, ende, spur, versatz_s=(folgen_seed(folge, seed) % 1000) / 100.0,
                      bewegung=os.environ.get("NEWS_MASKEN_SPRECHBEWEGUNG", "1") == "1")
        host = spur
    hhmm, datum, start_s = stand_aus_ordner(folge)
    logo = work / "logo.png"
    logo = logo if logo_png(logo) else None
    teile, pos = [], 0.0
    for n, seg in enumerate(plan):
        a, b = start_s + pos, start_s + pos + seg["dauer"]
        m0, m1 = int(a // 60), int(b // 60)
        pngs = []
        for mm in sorted({m0, m1}):
            p = work / f"uhr_{mm}.png"
            if not p.exists():
                uhr_png(f"{(mm // 60) % 24:02d}:{mm % 60:02d}", datum, p)
            pngs.append(p)
        clock = dict(pngs=pngs, wechsel=(m1 * 60 - a) if m1 != m0 else None)
        if host.name == "host_spur.mp4":
            seg["host_ss"] = pos
        teile.append(segment_rendern(seg, host, work, n, clock, logo))
        pos += seg["dauer"]
        print(f"Segment {n + 1}/{len(plan)} {seg['layout']} {seg['dauer']:.1f}s", flush=True)
    lst = work / "liste.txt"
    lst.write_text("\n".join(f"file '{p.as_posix()}'" for p in teile), encoding="utf-8")
    roh = work / "roh.mp4"
    run([FFMPEG, "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", roh])
    # Pegel wie im Latara-Format: feste Verstaerkung auf MASTER_LUFS + True-Peak-Begrenzer, AAC 256k ohne PNS/IS.
    # Frueher loudnorm linear=true: liegt input_tp + Verstaerkung ueber dem TP-Ziel (Sprache ~-22 LUFS mit Spitzen
    # ~-0,8 dBTP), faellt ffmpeg still in den dynamischen Modus und landet bei ~-15,2 LUFS (Vorfall 29.10.2026, 10:00).
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from weltlage_rohschnitt import master_ton
    erg["ton_master"] = master_ton(voll, roh, out)
    # Attribution der verwendeten Clips
    att = [s["medium"]["attribution"] for s in plan if s["layout"] in ("pip", "voll", "split")]
    (out.with_suffix(".attribution.txt")).write_text("\n".join(a for a in att if a), encoding="utf-8")
    return erg


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folge")
    ap.add_argument("--out")
    ap.add_argument("--max-s", type=float)
    ap.add_argument("--host")
    ap.add_argument("--nur-plan", action="store_true")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--work")
    a = ap.parse_args()
    folge = Path(a.folge)
    out = Path(a.out) if a.out else folge / f"{folge.name}.mp4"
    erg = bauen(folge, out, a.max_s, a.host, a.nur_plan, a.seed, Path(a.work) if a.work else None)
    print(json.dumps({k: v for k, v in erg.items() if k != "segmente"}, ensure_ascii=False))
    print(" ".join(f"{s['layout']}:{s['dauer']:.0f}" for s in erg["segmente"]))


if __name__ == "__main__":
    main()
