"""Freisteller-Lipsync fuer die Weltlage-Moderatorin Latara (stehend und sitzend).

FESTE REGEL (Marlon, 29.09.2026), gilt fuer alle Weltlage-Videos:
  1. Lipsync IMMER auf dem Freisteller-Quellvideo der Moderatorin (ohne Studio, volle Quellaufloesung, Gesicht gross),
     nie auf dem fertig komponierten Studiobild (dort ist das Gesicht 40-60 px und der Mund kaum sichtbar).
  2. Matte/Alpha bleibt die des Freistellers (stehend: BiRefNet-Alpha der ProRes-4444-Fassung, sitzend: Differenz-Key
     tools/key_host.key_frame des gruenen Masters); der Lipsync ersetzt nur die untere Gesichtshaelfte innerhalb der Alpha.
  3. Erst danach wird skaliert und in der abgemachten Position ins Studio gesetzt, und zwar direkt in der Endaufloesung
     1920x1080 (kein Composite in 1280x704 mit anschliessendem Hochskalieren, das machte die Sitz-Szene weich).

Ablauf pro Szene (render_scene):
  Freisteller-Bilder lesen -> auf neutralem Grau als LatentSync-Eingang schreiben + Gesicht verfolgen (Haar, geglaettet)
  -> Ton an leisen Stellen in ~7-s-Stuecke teilen -> je Stueck ein enges Gesichtsfenster (2,2x Gesicht) auf 768x768
  hochskalieren und mit LatentSync 1.6 syncen (12 Schritte, guidance config.settings.NEWS_WELTLAGE_LIPSYNC_GUIDANCE,
  Standard 2.0) -> Mundpartie weich in den Freisteller
  zurueck (<name>_freisteller_lipsync_prores4444.mov, mit Alpha) -> Studio-Composite 1920x1080/25 fps (<name>_studio.mp4).
LatentSync-Stuecke werden nach Inhalt (Ton, Bildausschnitt, Einstellungen) in data/_latentsync_cache zwischengespeichert,
gemeinsam fuer alle Laeufe: bei einer neuen Folge wird nur neu gesynct, was sich geaendert hat.

Laeuft mit .venv-lipsync (OpenCV 4 mit Haar-Kaskaden; OpenCV 5 im Basis-Python hat keine mehr):
    .venv-lipsync\\Scripts\\python.exe -m video.freisteller_lipsync stehend|sitz <ton.wav> <start_s> <laenge_s> <arbeitsordner> [name] [--ort bruessel]
Optional --ort: anderer Hintergrund aus config/brand/orte (video/orte.py); ohne = bisheriges Studio, unveraendert.
"""
import hashlib
import json
import os
import subprocess
import sys
import time
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BRAND = ROOT / "config" / "brand"
SZ = BRAND / "szene1_stehend_animation"
STUDIO = BRAND / "studio_bg"
TG = BRAND / "takes_green"
REPO = ROOT / "vendor" / "LatentSync"
LS_PY = ROOT / ".venv-lipsync" / "Scripts" / "python.exe"

_ff = next(iter(Path(os.environ["LOCALAPPDATA"]).glob("Microsoft/WinGet/Packages/Gyan.FFmpeg*/*/bin")), None)
FFMPEG = str(_ff / "ffmpeg.exe") if _ff else "ffmpeg"

OUT_W, OUT_H = 1920, 1080     # Endaufloesung der Weltlage-Videos: Composite direkt hier, nie hochskalieren
FPS = 25                      # LatentSync arbeitet mit 25 fps; der Schnitt setzt danach auf 24 fps
CHUNK = 7.0                   # laengere Stuecke liefen am 29.09. ueber den VRAM
WIN = 2.2                     # Fensterkante in Gesichtsgroessen (eng: Gesicht fuellt den LatentSync-Eingang)
# STEPS/GUIDANCE/ZOOM: zentral in config.settings.NEWS_LIPSYNC_STUFEN (Drosselstufen 1-4, Marlons Entscheid
# 19.10.2026: Stufe 2 ist der neue Standard, Task 20261019-120910-a2ea), nicht mehr hier hartkodiert - frueherer
# Verlauf (12/8 Schritte, Guidance 2,5/2,0/1,5) stand vorher einzeln in dieser Datei, siehe deren Git-Historie.
# Feld "steps"/"guidance" in pipeline_signatur(), damit eingefrorene Szenen eine Aenderung nicht stillschweigend
# ignorieren.
try:
    from config.settings import NEWS_WELTLAGE_LIPSYNC_STEPS as STEPS
except Exception:
    STEPS = 5
try:
    from config.settings import NEWS_WELTLAGE_LIPSYNC_GUIDANCE as GUIDANCE
except Exception:
    GUIDANCE = 1.5
try:
    from config.settings import NEWS_WELTLAGE_LIPSYNC_ZOOM as ZOOM   # Kantenlaenge des hochskalierten Gesichtsfensters
except Exception:
    ZOOM = 768
try:                          # LatentSync-Stuecke einer Szene gebuendelt in EINEM Prozess (Modelle nur einmal laden), Default aus
    from config.settings import NEWS_LIPSYNC_BATCH as LS_BATCH
except Exception:
    LS_BATCH = False
LS_BATCH_MAX = 8              # Stuecke je Prozess/GPU-Platz (Platz wird nicht ueber die ganze Szene gehalten)
GREY = 128
try:                          # Gesichtsfenster KI-hochskaliert statt Lanczos (video/gesicht_hd.py), Default aus
    from config.settings import NEWS_WELTLAGE_LIPSYNC_HD as HD
except Exception:
    HD = False
try:                          # Studio-Compositing mit Schatten/Spiegelung/Licht (video/composite_fx.py), Default an
    from config.settings import NEWS_WELTLAGE_COMPOSITE_FX as COMPOSITE_FX
except Exception:
    COMPOSITE_FX = True
try:                          # Real-ESRGAN/GFPGAN mehrere Bilder gleichzeitig durchs Netz (video/gesicht_hd.py),
    from config.settings import NEWS_WELTLAGE_GESICHT_HD_BATCH as HD_BATCH    # Default 1 = alter Weg, unveraendert
except Exception:
    HD_BATCH = 1
# Grobe VRAM-Schaetzung fuer die Warteschlange bei HD_BATCH > 1 (echte Messung steht noch aus, siehe Bericht Task
# 20261010-081311-ca9f): Aktivierungsspeicher waechst mit der Stapelgroesse, nicht die Gewichte selbst.
_ZOOM_VRAM_MB = 3000 if HD_BATCH <= 1 else min(3000 + 350 * (HD_BATCH - 1), 9000)
_RESTORE_VRAM_MB = 2000 if HD_BATCH <= 1 else min(2000 + 250 * (HD_BATCH - 1), 6000)


def _esrgan_an() -> bool:
    from video import gesicht_hd
    return gesicht_hd.ESRGAN


SHADOW_REF = 0.32             # Referenzskala, auf die der Schlagschatten abgestimmt ist (composite_host.py)


def pipeline_signatur() -> dict:
    """Einzige Quelle fuer die Pipeline-Einstellungen, die eine eingefrorene Szene beim Bau mitbekommen hat
    (Lipsync-Staerke/HD-Stufe/Studio-Compositing). Von freeze() aller Vorlagen-Builder (tools/weltlage_begruessung.py,
    tools/weltlage_verabschiedung.py) ins aktiv.json unter "pipeline" geschrieben und von tools/weltlage_abnahme.py
    (pipeline_probleme) gegen die aktuellen Einstellungen geprueft. Grund (03.10.2026): die eingefrorene
    Begruessungs-Szene behielt nach Einfuehrung von composite_fx (Task 20261001-180145-c47f) unbemerkt den alten,
    schattenlosen Rendergang, weil composite_fx kein Feld der damaligen Signatur war - ein neuer Pipeline-Schalter
    wurde nirgends automatisch mitgefuehrt. Kuenftige Schalter gehoeren in dieses eine Dict, nicht einzeln in jeden
    Builder und jede Pruefung verteilt."""
    return {"guidance": GUIDANCE, "hd": HD, "composite_fx": COMPOSITE_FX, "steps": STEPS}

# Pro Pose: Freisteller-Quelle, Keyer, Gesichtssuche (min/max Groesse in Quellpixeln, Gesichtsmitte oberhalb y-Anteil),
# Studio (Hintergrund, Platzierungsdatei samt Standardwerten, optionale Pult-Vordergrundmaske).
POSEN = {
    "stehend": dict(
        src=SZ / "stehend_v6_alpha_prores4444.mov", w=832, h=1248, loop=False, key=False,
        face=(60, 160, 0.25),
        bg=Path(r"C:\Users\Marlon\Documents\WK\latara_in_studio_stehend_neben_pult_breitbild_hintergund.png"),
        bg_still=True, bg_size=(1672, 941),
        placement=SZ / "host_placement_v6_neuer_hintergrund.json", default=dict(x=842, y=386, scale=0.3798),
        desk=None),
    "sitz": dict(
        src=TG / "weltlage_host_sitz_pingpong100_25fps.mp4", w=896, h=1152, loop=True, key=True,
        face=(170, 330, 0.45),
        bg=STUDIO / "logo_probe_A.mp4", bg_still=False, bg_size=(1280, 704),
        placement=STUDIO / "host_placement.json", default=dict(x=489, y=97, scale=0.32),
        desk=STUDIO / "desk_fg_mask_v2.png"),
}
# Sitz-Rohmaster: v3 0-12 s + v4-Tail (gruen, Mund zu), 22 s. Hart geloopt gab das alle 22 s einen sichtbaren Schnitt
# (Testvideo 29.09. bei 1:33, Bilddifferenz 17 statt ~1,3). Darum laeuft die Sitz-Pose seit 29.09. auf einem daraus
# gebauten Ping-Pong-Master (SITZ_PINGPONG): vor und zurueck mit wechselnden Umkehrpunkten, an jedem Umkehrpunkt sanft
# abgebremst (Cosinus-Rampe, Zwischenbilder geblendet), endet auf Bild 0 -> auch der Loop ist nahtlos; ~100 s, damit
# sich die Bewegung selten wiederholt. Beliebig lange Meldungen loopen diesen Master ohne sichtbaren Schnitt.
SITZ_TEILE = (TG / "weltlage_host_v3_master.mp4", TG / "weltlage_host_v4_tail_raw.mp4", 12.0)
SITZ_RAW = TG / "weltlage_host_sitz_raw22_25fps.mp4"
SITZ_PINGPONG = (0, 551, 175, 500, 75, 400, 0)   # Umkehrpunkte (Bilder im Rohmaster), Start = Ende = 0
SITZ_EASE = 15                                   # Bilder Brems-/Anfahrrampe je Umkehrpunkt (0,6 s)


def available() -> bool:
    return LS_PY.exists() and (REPO / "checkpoints" / "latentsync_unet.pt").exists()


def haar_ok() -> bool:
    """Gesichtssuche braucht die Haar-Kaskaden von OpenCV 4 (.venv-lipsync); OpenCV 5 hat sie nicht mehr."""
    try:
        import cv2
        return Path(cv2.data.haarcascades, "haarcascade_frontalface_default.xml").exists()
    except Exception:
        return False


def run(cmd):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise RuntimeError(" ".join(map(str, cmd))[:300] + "\n" + r.stderr[-1500:])
    return r


def pingpong_positions(turns=SITZ_PINGPONG, ease=SITZ_EASE) -> np.ndarray:
    """Quellposition (Bild, gebrochen) pro Ausgabebild: zwischen zwei Umkehrpunkten Tempo 1, an jedem Umkehrpunkt
    Cosinus-Rampe 1 -> 0 -> 1 ueber `ease` Bilder (keine ruckartige Richtungsumkehr). Letzter Punkt exklusiv, damit der
    Loop (Ende = Start) kein Bild doppelt zeigt."""
    pos = []
    for p, q in zip(turns[:-1], turns[1:]):
        dist = abs(q - p)
        n = int(round(dist + ease))                  # zwei halbe Rampen kosten zusammen `ease` Bilder
        t = np.arange(n + 1, dtype=np.float64)
        up = np.clip(t / ease, 0, 1)
        down = np.clip((n - t) / ease, 0, 1)
        v = np.minimum(0.5 - 0.5 * np.cos(np.pi * up), 0.5 - 0.5 * np.cos(np.pi * down))
        s = np.concatenate([[0.0], np.cumsum((v[1:] + v[:-1]) / 2)])
        pos.append(p + np.sign(q - p) * dist * s[:-1] / s[-1])
    return np.concatenate(pos)


def _build_pingpong(raw: Path, out: Path):
    """Ping-Pong-Master aus dem 22-s-Rohmaster (gruen, 25 fps): Bilder nach pingpong_positions, gebrochene Positionen
    linear aus den Nachbarbildern geblendet (gruen + gruen bleibt gruen, der Key laeuft danach wie gewohnt)."""
    P = POSEN["sitz"]
    W, H = P["w"], P["h"]
    frames = [f for f in _read_rgb(raw, W, H)]
    last = len(frames) - 1
    pos = np.clip(pingpong_positions(), 0, last)
    tmp = out.with_suffix(".tmp.mp4")
    ff = subprocess.Popen([FFMPEG, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                           "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-crf", "10", "-pix_fmt", "yuv420p", str(tmp)],
                          stdin=subprocess.PIPE)
    for x in pos:
        i = int(np.floor(x))
        w = x - i
        if w < 1e-3 or i >= last:
            fr = frames[min(i, last)]
        else:
            fr = np.clip(frames[i] * (1 - w) + frames[i + 1].astype(np.float32) * w + 0.5, 0, 255).astype(np.uint8)
        ff.stdin.write(fr.tobytes())
    ff.stdin.close()
    if ff.wait():
        raise RuntimeError("Ping-Pong-Master schreiben fehlgeschlagen")
    tmp.replace(out)


def _ensure_source(pose: str) -> Path:
    P = POSEN[pose]
    if pose == "sitz" and not P["src"].exists():
        if not SITZ_RAW.exists():
            a, tail, cut = SITZ_TEILE
            run([FFMPEG, "-y", "-v", "error", "-i", a, "-i", tail, "-filter_complex",
                 f"[0:v]trim=duration={cut},setpts=PTS-STARTPTS[a];[1:v]setpts=PTS-STARTPTS[b];[a][b]concat=n=2:v=1:a=0,"
                 f"fps={FPS}[v]", "-map", "[v]", "-c:v", "libx264", "-crf", "10", "-pix_fmt", "yuv420p", SITZ_RAW])
        _build_pingpong(SITZ_RAW, P["src"])
    return P["src"]


def source_frames(pose: str, f0: int, n: int):
    """RGBA-Bilder f0..f0+n des Freistellers (25 fps, Quellaufloesung, gerade/unpremultiplizierte Alpha)."""
    P = POSEN[pose]
    src = _ensure_source(pose)
    pre = ["-stream_loop", "-1"] if P["loop"] else []
    vf = f"fps={FPS},trim=start_frame={f0}:end_frame={f0 + n},setpts=PTS-STARTPTS"
    ch = 3 if P["key"] else 4
    p = subprocess.Popen([FFMPEG, "-v", "error", *pre, "-i", str(src), "-vf", vf, "-f", "rawvideo", "-pix_fmt",
                          "rgb24" if ch == 3 else "rgba", "-"], stdout=subprocess.PIPE)
    size = P["w"] * P["h"] * ch
    key = None
    if P["key"]:
        sys.path.insert(0, str(ROOT / "tools"))
        from key_host import key_frame as key
    try:
        for _ in range(n):
            b = p.stdout.read(size)
            if len(b) < size:
                break
            fr = np.frombuffer(b, np.uint8).reshape(P["h"], P["w"], ch)
            yield key(fr) if key else fr
    finally:
        p.stdout.close()
        p.wait()


def _read_rgb(src: Path, w: int, h: int):
    p = subprocess.Popen([FFMPEG, "-v", "error", "-i", str(src), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         stdout=subprocess.PIPE)
    while True:
        b = p.stdout.read(w * h * 3)
        if len(b) < w * h * 3:
            break
        yield np.frombuffer(b, np.uint8).reshape(h, w, 3)
    p.wait()


# ---------------------------------------------------------------- Gesicht verfolgen
def smooth_faces(boxes: list, w: int) -> np.ndarray:
    """(cx, cy, size) pro Bild: Luecken interpoliert, Ausreisser weg (Median 9), geglaettet (Gauss sigma 2 Bilder),
    Groesse konstant (Kamera fix)."""
    ok = [i for i, b in enumerate(boxes) if b is not None]
    if len(ok) < len(boxes) * 0.3:
        raise SystemExit(f"Gesicht nur in {len(ok)}/{len(boxes)} Bildern gefunden")
    arr = np.array([boxes[i] for i in ok])
    idx = np.arange(len(boxes))
    out = np.stack([np.interp(idx, ok, arr[:, k]) for k in range(3)], 1)
    med = np.stack([np.array([np.median(out[max(0, i - 4):i + 5, k]) for i in idx]) for k in range(3)], 1)
    kern = np.exp(-0.5 * (np.arange(-6, 7) / 2.0) ** 2); kern /= kern.sum()
    pad = np.pad(med, ((6, 6), (0, 0)), mode="edge")
    sm = np.stack([np.convolve(pad[:, k], kern, mode="valid") for k in range(3)], 1)
    sm[:, 2] = np.median(sm[:, 2])
    return sm


class FaceTracker:
    """Haar liefert Fehltreffer (Dekollete, Haende) -> nur Kandidaten mit plausibler Groesse im oberen Bildteil,
    dem Vorgaenger am naechsten."""

    def __init__(self, pose: str):
        import cv2
        self.cv2 = cv2
        self.det = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        P = POSEN[pose]
        self.lo, self.hi, self.ymax = P["face"][0], P["face"][1], P["face"][2] * P["h"]
        self.prev, self.boxes = None, []

    def add(self, rgb: np.ndarray):
        g = self.cv2.cvtColor(rgb, self.cv2.COLOR_RGB2GRAY)
        c = [f for f in self.det.detectMultiScale(g, 1.08, 4, minSize=(self.lo, self.lo), maxSize=(self.hi, self.hi))
             if f[1] + f[3] / 2 < self.ymax]
        if c:
            prev = self.prev
            key = (lambda f: abs(f[0] + f[2] / 2 - prev[0]) + abs(f[1] + f[3] / 2 - prev[1])) if prev else (lambda f: -f[2])
            x, y, w, h = min(c, key=key)
            self.prev = (x + w / 2, y + h / 2, float(w))
            self.boxes.append(self.prev)
        else:
            self.boxes.append(None)


# ---------------------------------------------------------------- Ton in Stuecke teilen
def quiet_cuts(wav: Path, total_frames: int) -> list[int]:
    """Stueckgrenzen (Bilder) nahe CHUNK s, jeweils an der leisesten Stelle -1,2 s (kein Stoss mitten im Wort)."""
    with wave.open(str(wav)) as w:
        sr, nch = w.getframerate(), w.getnchannels()
        a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32)[::nch]
    hop = sr // FPS
    rms = np.array([np.sqrt(np.mean(a[i * hop:(i + 1) * hop] ** 2) + 1e-9) if i * hop < len(a) else 0.0
                    for i in range(total_frames)])
    cuts, f = [0], 0
    step = int(CHUNK * FPS)
    while total_frames - f > step + FPS:              # Rest > 8 s -> noch ein Schnitt
        lo, hi = f + step - 30, min(f + step + 1, total_frames - FPS)
        f = lo + int(np.argmin(rms[lo:hi])) if hi > lo else f + step
        cuts.append(f)
    cuts.append(total_frames)
    return cuts


CHIN_FULL, CHIN_ZERO = 0.50, 0.62   # Maske voll bis hier, null ab hier (Gesichtsgroessen unter der Gesichtsmitte)
KINN_SIGMA = 0.12                # Weichzeichner der Farbkorrektur in Gesichtsgroessen
KINN_AB, KINN_VOLL = 0.36, 0.48   # Korrektur wirkt unter dem Mund (ab / voll, Gesichtsgroessen unter der Gesichtsmitte)


def _kinn_angleichen(win: np.ndarray, alpha: np.ndarray, fr: np.ndarray, dy: np.ndarray, size: float) -> np.ndarray:
    """Kinn/Wange unter dem Mund: Helligkeit und Farbton (nur die groben Anteile) des LatentSync-Ergebnisses ans Original
    angleichen. LatentSync liefert dort einen dunklen Schatten-Halbmond am Kinn und leicht dunklere Haut; die Mundpartie
    selbst bleibt unberuehrt (Korrektur erst unter dem Mund, weich eingeblendet). Referenz = Freisteller ueber Grau
    (transparente Pixel haben keine verlaessliche Farbe). Abschalten: NEWS_LIPSYNC_KINN=0 (Umgebungsvariable)."""
    if os.environ.get("NEWS_LIPSYNC_KINN", "1") == "0":
        return fr
    import cv2
    a = (alpha.astype(np.float32) / 255)[..., None]
    ref = win * a + GREY * (1 - a)
    sg = max(3.0, KINN_SIGMA * size)
    fr = fr.astype(np.float32)
    h, w0 = fr.shape[:2]
    k = 4                                          # Korrektur ist grob (sigma gross) -> auf 1/4 rechnen, spart ~15x Zeit
    sm = (w0 // k, h // k)
    korr = (cv2.GaussianBlur(cv2.resize(ref, sm, interpolation=cv2.INTER_AREA), (0, 0), sg / k)
            - cv2.GaussianBlur(cv2.resize(fr, sm, interpolation=cv2.INTER_AREA), (0, 0), sg / k))
    korr = cv2.resize(korr, (w0, h), interpolation=cv2.INTER_LINEAR)
    w = np.clip((dy - KINN_AB) / (KINN_VOLL - KINN_AB), 0, 1)
    w = (w * w * (3 - 2 * w))[..., None]
    return np.clip(fr + korr * w + 0.5, 0, 255)


MIN_CHUNK = round(1.0 * FPS)      # kein LatentSync-Stueck kuerzer als 1 s


def _mit_skip_grenzen(cuts: list[int], skip_frames: list[tuple[int, int]], n: int) -> list[int]:
    """Fuegt an jeder Vollbild-Spannen-Grenze einen zusaetzlichen Schnittpunkt ein: eine geplante Vollbild-Stelle
    (hoechstens VOLL_MAX=4 s) ist immer kuerzer als CHUNK=7 s - ohne eigene Grenze laege dort nie ein GANZES
    LatentSync-Stueck vollstaendig in der Spanne, das Ueberspringen in lipsync_freisteller() griffe also praktisch
    nie. Eine Grenze zu dicht an einem vorhandenen Schnittpunkt (< MIN_CHUNK) wird ausgelassen (kein Mini-Stueck);
    dann bleibt der nahe vorhandene Punkt die wirksame Kante - im Zweifel also ein Stueck mehr normal gerechnet statt
    ein zu kurzes LatentSync-Stueck erzwungen (Marlon 19.10.2026)."""
    pts = set(cuts)
    for a, b in skip_frames:
        for p in (a, b):
            if 0 < p < n and all(abs(p - c) >= MIN_CHUNK for c in pts):
                pts.add(p)
    return sorted(pts)


def windows_for(faces: np.ndarray, cuts: list[int], w: int, h: int) -> list[tuple[int, int, int]]:
    """Quadratisches Gesichtsfenster (x, y, s) pro Stueck: 2,2x Gesicht, gross genug fuer die Kopfbewegung im Stueck."""
    wins = []
    for k in range(len(cuts) - 1):
        fc = faces[cuts[k]:cuts[k + 1]]
        size = float(fc[0, 2])
        cx = (fc[:, 0].min() + fc[:, 0].max()) / 2
        cy = (fc[:, 1].min() + fc[:, 1].max()) / 2 + size * 0.1
        s = int(min(max(size * WIN, np.ptp(fc[:, 0]) + size * 1.9, np.ptp(fc[:, 1]) + size * 1.9), w, h) // 2 * 2)
        x = int(min(max(cx - s / 2, 0), w - s)) // 2 * 2
        y = int(min(max(cy - s / 2, 0), h - s)) // 2 * 2
        wins.append((x, y, s))
    return wins


# ---------------------------------------------------------------- LatentSync pro Stueck
# 02.10.2026 (Task 20261002-125229-cafd, -131755-44f2): LS_FREE_MB war der Schwellwert einer eigenen
# "ist genug VRAM frei?"-Pollschleife (_wait_gpu) ZUSAETZLICH zum Platz in der zentralen Warteschlange - genau das
# Muster, das die Warteschlange ersetzen sollte (siehe gpu_queue.py-Kopf). Diese zweite Schleife erfuellte ihren
# eigenen Schwellwert auf dieser Maschine nie zuverlaessig (freier VRAM schwankt +-1 GB durch Jarvis/Beta) und wartete
# darum bei praktisch jedem Stueck die volle 3-min-Soft-Frist aus, bevor sie trotzdem losliefen - bei ~30-50 Stuecken
# je Folge ein bis zweieinhalb Stunden toter Wartezeit obendrauf, dazu hielt der alte `hold()` den Platz ueber die
# GANZE Folge (alle Szenen, auch CPU-Arbeit dazwischen) und blockierte damit andere Jobs wie HiDream stundenlang
# (Task 20261002-154329-1b6a wartete so ueber 80 min). Task 20261002-170551-fe9f (02.10. abends): eigene Pollschleife
# entfernt, Platz wird nur noch pro tatsaechlicher GPU-Operation gehalten (_run_with_gpu: Zoom-Fenster, LatentSync,
# GFPGAN-Nachzeichnung je einzeln, sonst frei fuer andere Jobs), die zentrale Warteschlange entscheidet allein, wie
# schon in video/lipsync.py. LS_FREE_MB bleibt nur noch die VRAM-Schaetzung, die der LatentSync-Schritt anmeldet.
LS_FREE_MB = 11000   # LatentSync mit VAE-Slicing braucht ~8,5 GB (ohne ~17 GB)


# gemeinsamer Zwischenspeicher aller Laeufe (Dateiname = Inhalts-Hash): jede Folge/Testfassung nutzt fertige Stuecke
SHARED_CACHE = ROOT / "data" / "_latentsync_cache"
LS_TIMEOUT = 900     # normal ~110 s pro 7-s-Stueck; laenger = VRAM laeuft ueber

# Sperrname in der zentralen GPU-Warteschlange (jarvis/tools/gpu_queue.py, excl=): nie zwei Weltlage-Lipsync-Laeufe
# gleichzeitig, egal was die VRAM-Rechnung hergeben wuerde. War bis 04.10.2026 eine eigene Datei-Sperre (PID in
# state/latentsync.lock, psutil.pid_exists): nach einem Absturz/Neustart konnte eine fremde, spaeter gestartete PID
# dieselbe Nummer bekommen und die Sperre faelschlich als belegt zeigen (Windows vergibt PIDs wieder); die zentrale
# Warteschlange prueft stattdessen PID+Startzeit (gpu_queue._alive) und raeumt tote Eintraege bei jedem Zugriff weg.
LS_EXCL = "weltlage_lipsync"


_GB = None


def _gpu_budget():
    """gpu_budget-Modul, einmal importiert (gemeinsamer Zustand mit video/lipsync.py und dem Rest der Pipeline)."""
    global _GB
    if _GB is None:
        sys.path.insert(0, str(ROOT))
        import gpu_budget
        _GB = gpu_budget
    return _GB


def _run_with_gpu(step_name: str, vram_mb: int, log, fn):
    """Fuehrt `fn()` aus und haelt dafuer einen Platz in der zentralen GPU-Warteschlange NUR fuer diese eine
    Operation (Zoom-Fenster, LatentSync-Aufruf oder GFPGAN-Nachzeichnung je einzeln) statt fuer die ganze Folge:
    zwischen den Stuecken und waehrend der CPU-Arbeit (Gesichtsverfolgung, ffmpeg, Compositing) ist die Karte fuer
    andere Jobs (HiDream, TTS, Beta-Orb) frei. Die Warteschlange (gpu_budget.slot, wie video/lipsync.py) entscheidet
    allein ueber den Start, keine eigene VRAM-Pollschleife mehr (Task 20261002-170551-fe9f); excl=LS_EXCL sorgt
    zusaetzlich dafuer, dass nie zwei Weltlage-Lipsync-Laeufe gleichzeitig eine Operation fahren (Task
    20261004-003744-17ef, siehe LS_EXCL)."""
    gb = _gpu_budget()
    with gb.slot("lipsync", name=f"lipsync freisteller {step_name} ({Path(sys.argv[0]).stem})", vram_mb=vram_mb,
                progress=lambda w, m: log(f"  GPU-Warteschlange ({m:.0f} min): {w}"), excl=LS_EXCL):
        return fn()


def _chunk_key(tag, wav, a, b, box, cache: Path, ident: str):
    """(Ton-Stueck, Zwischenspeicher-Datei) eines LatentSync-Stuecks; gleiche Berechnung wie bisher in sync_chunk."""
    seg_wav = cache / f"{tag}.wav"
    run([FFMPEG, "-y", "-v", "error", "-i", wav, "-ss", f"{a / FPS:.3f}", "-to", f"{b / FPS:.3f}", "-ar", "16000",
         "-ac", "1", seg_wav])
    h = hashlib.sha1(seg_wav.read_bytes())
    h.update(json.dumps([ident, a, b, box, ZOOM, STEPS, GUIDANCE, "refclosed"] + (["hd1"] if HD else []) + (["noesr"] if HD and not _esrgan_an() else [])).encode())
    return seg_wav, SHARED_CACHE / f"{tag}_{h.hexdigest()[:10]}_synced.mp4"


def _zoom_video(tag, grey_scene, a, b, box, cache: Path, log) -> Path:
    """Gesichtsfenster-Video (ZOOM x ZOOM) fuer Bilder [a, b) (+5 Reserve), HD oder Lanczos wie bisher in sync_chunk."""
    x, y, s = box
    seg_vid = cache / f"{tag}_zoom.mp4"
    if HD:                                                 # Real-ESRGAN + GFPGAN statt Lanczos (braucht die GPU)
        from video import gesicht_hd
        t = time.time()
        _run_with_gpu("zoom", _ZOOM_VRAM_MB, log,
                      lambda: gesicht_hd.zoom_window(FFMPEG, Path(grey_scene), a, b + 5, x, y, s, ZOOM, seg_vid,
                                                     FPS, batch=HD_BATCH))
        log(f"  {tag}: Gesichtsfenster {s} px KI-hochskaliert auf {ZOOM} in {time.time() - t:.0f} s")
    else:
        run([FFMPEG, "-y", "-v", "error", "-i", grey_scene, "-vf",
             f"trim=start_frame={a}:end_frame={b + 5},setpts=PTS-STARTPTS,crop={s}:{s}:{x}:{y},"
             f"scale={ZOOM}:{ZOOM}:flags=lanczos", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "10",
             "-pix_fmt", "yuv420p", seg_vid])
    return seg_vid


def prefetch_chunks(todo: list, wav, grey_scene, cache: Path, ident: str, log) -> int:
    """Schalter NEWS_LIPSYNC_BATCH: rechnet die noch fehlenden LatentSync-Stuecke (todo = [(tag, a, b, box)]) in wenigen
    Prozessen (je bis LS_BATCH_MAX Stuecke, tools/latentsync_ref_inference.py --jobs) statt je Stueck einen eigenen
    Prozess mit Modell-Ladezeit; gleiche Einstellungen, gleicher Seed je Stueck -> gleiches Ergebnis. Ergebnisse landen im
    gemeinsamen Zwischenspeicher, sync_chunk() findet sie danach dort. Was nicht klappt, rechnet sync_chunk wie bisher
    einzeln (Rueckfall). Liefert die Zahl der fertigen Stuecke."""
    SHARED_CACHE.mkdir(parents=True, exist_ok=True)
    missing = []
    for tag, a, b, box in todo:
        seg_wav, out = _chunk_key(tag, wav, a, b, box, cache, ident)
        if not out.exists():
            missing.append((tag, a, b, box, seg_wav, out))
    done = 0
    for i in range(0, len(missing), LS_BATCH_MAX):
        part = missing[i:i + LS_BATCH_MAX]
        jobs = []
        for tag, a, b, box, seg_wav, out in part:
            seg_vid = _zoom_video(tag, grey_scene, a, b, box, cache, log)
            jobs.append(dict(video=str(seg_vid), audio=str(seg_wav), out=str(out.with_suffix(".tmp.mp4")),
                             temp=str(cache / f"{tag}_ls")))
        jf = cache / f"batch_{part[0][0]}.json"
        jf.write_text(json.dumps(jobs), encoding="utf-8")
        lgp = cache / f"batch_{part[0][0]}.log"
        t = time.time()

        def _once():
            with open(lgp, "w") as lg:
                pr = subprocess.Popen([str(LS_PY), str(ROOT / "tools" / "latentsync_ref_inference.py"),
                                       "--unet_config_path", "configs/unet/stage2_512.yaml",
                                       "--inference_ckpt_path", "checkpoints/latentsync_unet.pt",
                                       "--inference_steps", str(STEPS), "--guidance_scale", str(GUIDANCE),
                                       "--enable_deepcache", "--ref_mode", "closed", "--jobs", str(jf)],
                                      cwd=str(REPO), stdout=subprocess.DEVNULL, stderr=lg)
                try:
                    pr.wait(timeout=LS_TIMEOUT * len(jobs))
                except subprocess.TimeoutExpired:
                    subprocess.run(["taskkill", "/PID", str(pr.pid), "/T", "/F"], capture_output=True)
                    pr.wait()

        _run_with_gpu("latentsync batch", LS_FREE_MB, log, _once)
        n_ok = lgp.read_text(errors="replace").count("[job] ") if lgp.exists() else 0
        for (tag, a, b, box, seg_wav, out), j in list(zip(part, jobs))[:n_ok]:   # nur Stuecke, die der Prozess als fertig meldete
            tmp = Path(j["out"])
            if tmp.exists() and not out.exists():
                SHARED_CACHE.mkdir(parents=True, exist_ok=True)
                tmp.replace(out)
                done += 1
        for j in jobs:
            Path(j["out"]).unlink(missing_ok=True)
        log(f"  Stapel {i // LS_BATCH_MAX + 1}: {n_ok}/{len(part)} Stuecke in {time.time() - t:.0f} s gerechnet")
    return done


def sync_chunk(tag, wav, grey_scene, a, b, box, cache: Path, ident: str, log) -> list[np.ndarray]:
    """LatentSync auf Bilder [a, b) des Grau-Freistellers im Fenster box; liefert die Fenster in Originalgroesse."""
    import cv2
    x, y, s = box
    n = b - a
    seg_wav, out = _chunk_key(tag, wav, a, b, box, cache, ident)
    SHARED_CACHE.mkdir(parents=True, exist_ok=True)
    if not out.exists():
        # +5 Bilder Reserve wie video/lipsync._cut_master (+0,2 s); LatentSync liefert gelegentlich 1-2 Bilder weniger
        seg_vid = _zoom_video(tag, grey_scene, a, b, box, cache, log)
        tmp = out.with_suffix(".tmp.mp4")
        # bis zu 3 Versuche: am 29.09. lief ein Stueck ueber den VRAM, als Jarvis mittendrin seine Stimme neu in die GPU
        # lud (60 s pro Schritt statt 0,5 s) -> nach 15 min abbrechen, wieder auf freie GPU warten, neu versuchen
        for attempt in range(1, 4):
            with open(cache / f"{tag}_latentsync.log", "w") as lg:
                if out.exists():                               # waehrend des Wartens von einem anderen Lauf gerechnet
                    break
                t = time.time()                                # reine Rechenzeit, ohne Warten auf die GPU

                def _once():
                    pr = subprocess.Popen([str(LS_PY), str(ROOT / "tools" / "latentsync_ref_inference.py"),
                                           "--unet_config_path", "configs/unet/stage2_512.yaml",
                                           "--inference_ckpt_path", "checkpoints/latentsync_unet.pt",
                                           "--inference_steps", str(STEPS), "--guidance_scale", str(GUIDANCE),
                                           "--enable_deepcache", "--ref_mode", "closed", "--video_path", str(seg_vid),
                                           "--audio_path", str(seg_wav), "--video_out_path", str(tmp), "--temp_dir",
                                           str(cache / f"{tag}_ls")],
                                          cwd=str(REPO), stdout=subprocess.DEVNULL, stderr=lg)
                    try:
                        return pr.wait(timeout=LS_TIMEOUT) == 0 and tmp.exists()
                    except subprocess.TimeoutExpired:      # ganzer Baum: der venv-Starter hat ein Kind-Python auf der GPU
                        subprocess.run(["taskkill", "/PID", str(pr.pid), "/T", "/F"], capture_output=True)
                        pr.wait()
                        return False

                ok = _run_with_gpu("latentsync", LS_FREE_MB, log, _once)
            if ok or out.exists():
                break
            log(f"  {tag}: Versuch {attempt} fehlgeschlagen oder zu langsam, siehe {tag}_latentsync.log")
        else:
            raise SystemExit(f"LatentSync fehlgeschlagen ({tag}), siehe {cache / (tag + '_latentsync.log')}")
        if not out.exists():
            tmp.replace(out)
            log(f"  {tag}: {n / FPS:.1f} s Ton in {time.time() - t:.0f} s gesynct")
        else:
            log(f"  {tag}: von einem anderen Lauf gerechnet")
    else:
        log(f"  {tag}: aus dem Zwischenspeicher")
    frames = list(_read_rgb(out, ZOOM, ZOOM))[:n]
    if HD and frames:                                      # Mundpartie der Ausgabe nachzeichnen (GFPGAN)
        from video import gesicht_hd
        t = time.time()
        frames = _run_with_gpu("restore", _RESTORE_VRAM_MB, log,
                              lambda: gesicht_hd.restore(frames, gesicht_hd.GFP_OUT, batch=HD_BATCH))
        gesicht_hd.free()
        log(f"  {tag}: Mund nachgezeichnet (GFPGAN) in {time.time() - t:.0f} s")
    frames = [cv2.resize(fr, (s, s), interpolation=cv2.INTER_AREA) for fr in frames]
    if not frames:
        raise SystemExit(f"LatentSync-Ausgabe leer ({out})")
    frames += [frames[-1]] * (n - len(frames))
    return frames


# ---------------------------------------------------------------- Szene
def lipsync_freisteller(pose: str, wav: Path, start: float, length: float, work: Path, name: str, log=print,
                        skip_spans: list | None = None) -> tuple[Path, int]:
    """Schritt 1+2 der Regel: Lipsync auf dem Freisteller, Alpha erhalten -> ProRes 4444 mit Alpha. Liefert (Datei, Bilder).
    skip_spans: [(start_s, ende_s), ...] relativ zu DIESEM Aufruf (0 = Szenenanfang, wie `length`) - dort setzt
    tools/weltlage_broll.py nachher einen Vollbild-Clip ein, der Freisteller wird gleich wieder ganz verdeckt. Ein
    LatentSync-Stueck (quiet_cuts()) wird dort ausgelassen (teuerster Schritt der Pipeline), nur wenn es VOLLSTAENDIG
    in einer Spanne liegt - sonst normal gerechnet (Marlon 19.10.2026, Task 20261019-182613-44c1)."""
    import cv2
    P = POSEN[pose]
    W0, H0 = P["w"], P["h"]
    work.mkdir(parents=True, exist_ok=True)
    cache = work / "_latentsync"
    cache.mkdir(exist_ok=True)
    f0, n = round(start * FPS), round(length * FPS)
    skip_frames = [(max(0, round(a * FPS)), min(n, round(b * FPS))) for a, b in (skip_spans or []) if b > a]
    log(f"{name} ({pose}): Freisteller-Bilder {f0}-{f0 + n} ({length:.2f} s), {W0}x{H0}, guidance {GUIDANCE}, {STEPS} Schritte")
    # 1) Freisteller auf neutralem Grau (LatentSync-Eingang), Gesicht verfolgen
    grey = work / f"{name}_freisteller_grau25.mp4"
    tr = FaceTracker(pose)
    # preset veryfast: reines Zwischenstueck fuer LatentSync, sofort wieder decodiert; crf bleibt gleich (gleiche
    # Zielqualitaet), nur schneller codiert (Task 20261007-150054-1995, Laufzeit-Hebel)
    ff = subprocess.Popen([FFMPEG, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W0}x{H0}",
                           "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "10",
                           "-pix_fmt", "yuv420p", str(grey)], stdin=subprocess.PIPE)
    got = 0
    for rgba in source_frames(pose, f0, n + 5):
        a = rgba[..., 3:4].astype(np.float32) / 255
        rgb = np.clip(rgba[..., :3] * a + GREY * (1 - a) + 0.5, 0, 255).astype(np.uint8)
        ff.stdin.write(rgb.tobytes())
        if got < n:
            tr.add(rgb)
        got += 1
    ff.stdin.close()
    if ff.wait() or got < n:
        raise SystemExit(f"Freisteller-Ausschnitt fehlgeschlagen ({got}/{n} Bilder)")
    faces = smooth_faces(tr.boxes, W0)
    np.save(work / f"{name}_faces.npy", faces)
    # 2) LatentSync pro Stueck im engen Gesichtsfenster
    cuts = quiet_cuts(wav, n)
    if skip_frames:
        cuts = _mit_skip_grenzen(cuts, skip_frames, n)
    wins = windows_for(faces, cuts, W0, H0)
    ident = f"{pose}:{P['src'].name}:{int(P['src'].stat().st_mtime)}:{f0}"
    # Vollbild-Spannen (skip_frames): ein Stueck nur auslassen, wenn es GANZ in einer Spanne liegt (sonst normal
    # rechnen - lieber ein paar Sekunden unnoetig gesynct als ein sichtbar unsynchronisiertes Stueck am Rand).
    skip_chunks = {k for k in range(len(cuts) - 1)
                   if any(sa <= cuts[k] and cuts[k + 1] <= sb for sa, sb in skip_frames)}
    if skip_chunks:
        log(f"{name}: {len(skip_chunks)}/{len(cuts) - 1} Lipsync-Stuecke uebersprungen (Vollbild-Clip ueberdeckt sie)")
    if LS_BATCH:                               # Schalter NEWS_LIPSYNC_BATCH: fehlende Stuecke gebuendelt vorrechnen
        prefetch_chunks([(f"{name}_{k:02d}", cuts[k], cuts[k + 1], wins[k]) for k in range(len(cuts) - 1)
                         if k not in skip_chunks], wav, grey, cache, ident, log)
    # 3) Mundpartie in den Freisteller zurueck; Alpha = Original
    fs_out = work / f"{name}_freisteller_lipsync_prores4444.mov"
    pf = subprocess.Popen([FFMPEG, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W0}x{H0}",
                           "-r", str(FPS), "-i", "-", "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt",
                           "yuva444p10le", "-alpha_bits", "16", str(fs_out)], stdin=subprocess.PIPE)
    check, k, chunk = [], -1, None
    kernel = np.ones((5, 5), np.uint8)
    for i, rgba in enumerate(source_frames(pose, f0, n)):
        if k + 1 < len(cuts) - 1 and i >= cuts[k + 1]:
            k += 1
            chunk = None if k in skip_chunks else sync_chunk(f"{name}_{k:02d}", wav, grey, cuts[k], cuts[k + 1],
                                                             wins[k], cache, ident, log)
        if chunk is None:                      # vollflaechig ueberdeckt - Freisteller unveraendert durchreichen
            pf.stdin.write(rgba.tobytes())
            continue
        cx, cy, size = faces[i]
        x, y, s = wins[k]
        fr = chunk[i - cuts[k]]
        # untere Gesichtshaelfte (unter den Augen bis unters Kinn, Wange zu Wange), weicher Rand, nur im Fenster;
        # Augen und Stirn bleiben Original (LatentSync gibt dort nur eine leicht weichere Kopie zurueck)
        yy, xx = np.mgrid[y:y + s, x:x + s].astype(np.float32)
        d = np.sqrt(((xx - cx) / (size * 0.46)) ** 2 + ((yy - (cy + size * 0.36)) / (size * 0.40)) ** 2)
        m = np.clip((1.15 - d) / 0.35, 0, 1)
        m = m * m * (3 - 2 * m)
        # Kinn-Grenze (Task 20261022-114327-3205): Kinn liegt bei ~0.56 (max 0.62) Gesichtsgroessen unter der Haar-Mitte;
        # darunter (Hals) gibt LatentSync einen dunklen Schatten-Halbmond aus -> dort blendet die Maske zum Original aus
        v = np.clip((CHIN_ZERO - (yy - cy) / size) / (CHIN_ZERO - CHIN_FULL), 0, 1)
        m = m * (v * v * (3 - 2 * v))
        al = cv2.erode(np.ascontiguousarray(rgba[y:y + s, x:x + s, 3]), kernel)
        m = (m * (cv2.GaussianBlur(al, (0, 0), 1.5).astype(np.float32) / 255))[..., None]
        out = rgba.copy()
        win = out[y:y + s, x:x + s, :3].astype(np.float32)
        fr = _kinn_angleichen(win, rgba[y:y + s, x:x + s, 3], fr, (yy - cy) / size, size)
        out[y:y + s, x:x + s, :3] = np.clip(win * (1 - m) + fr.astype(np.float32) * m + 0.5, 0, 255).astype(np.uint8)
        pf.stdin.write(out.tobytes())
        if i in (n // 4, n // 2, 3 * n // 4):
            r0, c0, e = max(0, int(cy - size)), max(0, int(cx - size)), int(2 * size)
            check.append(np.concatenate([rgba[r0:r0 + e, c0:c0 + e, :3], out[r0:r0 + e, c0:c0 + e, :3]], 1))
    pf.stdin.close()
    if pf.wait():
        raise SystemExit("Freisteller-Lipsync schreiben fehlgeschlagen")
    if check and len({c.shape for c in check}) == 1:
        cv2.imwrite(str(work / f"{name}_vergleich_gesicht.png"), cv2.cvtColor(np.concatenate(check, 0), cv2.COLOR_RGB2BGR))
    (work / f"{name}_fenster.json").write_text(json.dumps({"pose": pose, "f0": f0, "cuts": cuts, "windows": wins,
                                                           "steps": STEPS, "guidance": GUIDANCE, "hd": HD,
                                                           "zoom": ZOOM}), encoding="utf-8")
    return fs_out, n


def load_placement(pose: str) -> dict:
    P = POSEN[pose]
    p = dict(P["default"], desk_mask=P["desk"] is not None)
    if P["placement"].exists():
        p.update(json.loads(P["placement"].read_text(encoding="utf-8")))
    return p


def studio_filter(pose: str, p: dict, W: int = OUT_W, H: int = OUT_H) -> str:
    """Platzierung wie tools/composite_host.py bzw. composite_stehend_v6_neuer_hintergrund.py (x/y/scale beziehen
    sich auf die Hintergrund-Leinwand), aber alles direkt auf W x H: Hintergrund fuellend skaliert und mittig
    beschnitten (wie der Schnitt es bisher nachtraeglich tat), Moderatorin aus der vollen Freisteller-Aufloesung."""
    P = POSEN[pose]
    bw, bh = P["bg_size"]
    k = max(W / bw, H / bh)
    sw, sh = round(bw * k / 2) * 2, round(bh * k / 2) * 2
    ox, oy = (sw - W) // 2, (sh - H) // 2
    bgf = f"scale={sw}:{sh}:flags=lanczos,crop={W}:{H}:{ox}:{oy},setsar=1"
    mw, mh = max(2, round(P["w"] * p["scale"] * k / 2) * 2), max(2, round(P["h"] * p["scale"] * k / 2) * 2)
    mx, my = round(p["x"] * k) - ox, round(p["y"] * k) - oy
    sf = p["scale"] / SHADOW_REF
    dx, dy = max(1, round(6 * sf * k)), max(1, round(10 * sf * k))
    sigma = max(1.0, 6 * sf) * k
    f = (f"[0:v]fps={FPS},{bgf}[bg0];"
         f"[1:v]format=gbrap,scale={mw}:{mh}:flags=lanczos,colorbalance=rs=-0.02:bs=0.05,format=yuva444p[mod];"
         f"[mod]split=2[modA][modB];"
         f"[modB]colorchannelmixer=rr=0:gg=0:bb=0:aa=0.45,gblur=sigma={sigma:.2f}[shadow];"
         f"[bg0][shadow]overlay={mx + dx}:{my + dy}:shortest=1[bg1];"
         f"[bg1][modA]overlay={mx}:{my}:shortest=1:format=auto[bg2];")
    if P["desk"] is not None and p.get("desk_mask", True):
        f += f"[2:v]format=rgba,{bgf}[desk];[bg2][desk]overlay=0:0:shortest=1[outv]"
    else:
        f += "[bg2]null[outv]"
    return f


def _composite_studio_fx(pose: str, freisteller: Path, n: int, out: Path) -> Path:
    """Wie composite_studio, aber mit dem realistischeren Pro-Bild-Compositing (video/composite_fx.py): eigener
    Kontaktschatten je Schuh, Schlagschatten, Bodenspiegelung, kuehleres Studiolicht, Randlicht/Light-Wrap, Koernung
    (Probe Task 20261001-165559-5e26, Standard seit Task 20261001-180145-c47f). Nur die stehende Pose."""
    from video import composite_fx as fx
    P = POSEN[pose]
    p = load_placement(pose)
    bg = fx.load_bg(P["bg"], OUT_W, OUT_H, P["bg_size"])
    mx, my, mw, mh = fx.placement_box(p, (P["w"], P["h"]), OUT_W, OUT_H, P["bg_size"])
    box = fx.crop_box(mx, my, mw, mh, OUT_W, OUT_H)   # einmal pro Szene, nicht pro Bild (siehe composite_fx.compose)
    size = P["w"] * P["h"] * 4
    rd = subprocess.Popen([FFMPEG, "-v", "error", "-i", str(freisteller), "-frames:v", str(n), "-f", "rawvideo",
                           "-pix_fmt", "rgba", "-"], stdout=subprocess.PIPE)
    # preset veryfast: Szenen-Zwischendatei, der Rohschnitt setzt/encodiert sie ohnehin neu zusammen; crf bleibt
    # gleich (Task 20261007-150054-1995, Laufzeit-Hebel)
    wr = subprocess.Popen([FFMPEG, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s",
                           f"{OUT_W}x{OUT_H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast",
                           "-crf", "15", "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE)
    got = 0
    for i in range(n):
        b = rd.stdout.read(size)
        if len(b) < size:
            break
        fg = np.frombuffer(b, np.uint8).reshape(P["h"], P["w"], 4)
        wr.stdin.write(fx.compose(fg, bg, mx, my, mw, mh, seed=i, box=box).tobytes())
        got += 1
    rd.stdout.close()
    rd.wait()
    wr.stdin.close()
    if wr.wait() or got < n:
        raise SystemExit(f"Studio-Compositing (Bild-FX) fehlgeschlagen ({got}/{n} Bilder)")
    return out


def composite_studio(pose: str, freisteller: Path, n: int, out: Path, ort: str | None = None,
                     avatar: str = "latara") -> Path:
    """Schritt 3 der Regel: skalieren, platzieren, ins Studio setzen (1920x1080, 25 fps, ohne Ton).
    ort: optionaler Ort aus config/brand/orte/orte.json (z.B. "bruessel"); None/"studio" = bisheriges Studio,
    unveraendert. Andere Orte setzt video/orte.py mit den im Tool gespeicherten Werten (Grösse, Position, Schatten).
    Stehende Pose: mit config.settings.NEWS_WELTLAGE_COMPOSITE_FX (Default an) per video/composite_fx.py, sonst
    (und immer bei der Sitz-Pose, dort verdeckt das Pult die Fuesse) der bisherige ffmpeg-Overlay-Weg."""
    from video import orte as orte_mod
    if not orte_mod.ist_standard(ort):
        return orte_mod.composite(avatar, ort, freisteller, n, out)
    if pose == "stehend" and COMPOSITE_FX:
        return _composite_studio_fx(pose, freisteller, n, out)
    P = POSEN[pose]
    p = load_placement(pose)
    bg = ["-loop", "1", "-i", str(P["bg"])] if P["bg_still"] else ["-stream_loop", "-1", "-i", str(P["bg"])]
    desk = ["-loop", "1", "-i", str(P["desk"])] if P["desk"] is not None and p.get("desk_mask", True) else []
    run([FFMPEG, "-y", "-v", "error", *bg, "-i", freisteller, *desk, "-filter_complex", studio_filter(pose, p),
         "-map", "[outv]", "-frames:v", str(n), "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "15",
         "-pix_fmt", "yuv420p", out])
    return out


def render_scene(pose: str, wav: Path, start: float, length: float, work: Path, name: str, log=print,
                 ort: str | None = None, skip_spans: list | None = None) -> Path:
    """Ganze Regel fuer eine Sprechszene: Freisteller lipsyncen -> Alpha behalten -> Studio 1920x1080. -> <name>_studio.mp4
    ort: optional anderer Hintergrund (config/brand/orte), Standard None = bisheriges Studio.
    skip_spans: siehe lipsync_freisteller()."""
    t = time.time()
    fs, n = lipsync_freisteller(pose, Path(wav), start, length, Path(work), name, log, skip_spans=skip_spans)
    comp = composite_studio(pose, fs, n, Path(work) / f"{name}_studio.mp4", ort=ort)
    log(f"{name}: fertig in {time.time() - t:.0f} s -> {comp}")
    return comp


if __name__ == "__main__":
    ort_arg = None
    if "--ort" in sys.argv:                          # optional: --ort bruessel (config/brand/orte/orte.json)
        i = sys.argv.index("--ort")
        ort_arg = sys.argv[i + 1]
        del sys.argv[i:i + 2]
    if len(sys.argv) < 6 or sys.argv[1] not in POSEN:
        raise SystemExit(__doc__)
    render_scene(sys.argv[1], Path(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]), Path(sys.argv[5]),
                 sys.argv[6] if len(sys.argv) > 6 else sys.argv[1], ort=ort_arg)
