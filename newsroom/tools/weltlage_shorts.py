#!/usr/bin/env python
"""Weltlage Kompakt: 1-3 vertikale Shorts (9:16, unter 60 s) aus einer fertigen Folge schneiden.

Hintergrund (Analyse 11.10.2026, reports/youtube-kanal/weltlage-analyse-20261011): der Kanal hat trotz
fertiger Shorts-Technik (NEWS_FORMAT=shorts, video/layout.py) noch keine einzige echte Short
veroeffentlicht. Statt einer komplett neu produzierten Shorts-Folge schneidet dieses Modul aus einer
bereits fertigen 16:9-Folge die staerkste Aussage/Frage heraus:

- Szenen-Zeiten kommen aus <stamm>_stimmen.json (dieselbe Datei, die die Stimmpruefung am Videoanfang
  nutzt: Label, Start, Laenge, Referenz-WAV je Szene).
- Der Sprechtext je Szene kommt aus texte.json (Szenen-ID = Dateiname des Referenz-WAV ohne Endung).
- Quelle ist die fertige B-Roll-Fassung <stamm>_clips.mp4 (dieselbe Datei, die auch hochgeladen wird).
- Untertitel/Geometrie nutzen dieselben Bausteine wie die bestehende Shorts-Pipeline: video/layout.py
  (9:16-Grossen) und tts/align_captions.py (Whisper-Worttiming -> ASS, Skript-Rechtschreibung).

Kandidaten: der Cold Open (der geschriebene Hook der Folge, meist ~25-30 s) ist immer zuerst dabei, dazu
bis zu zwei weitere Meldungs-Szenen, wenn sie unter MAX_DAUER_S Sekunden liegen (nie mitten im Satz
abschneiden). Der Titel ist wie im Kanal ueblich eine Frage: beim Cold Open der Folgentitel, bei anderen
Szenen die Kommentarfrage, wenn sie wortgleich im Szenentext steckt, sonst ein Fragesatz aus dem
Szenentext, sonst der Folgentitel.

Aufruf: tools/weltlage_shorts.py <ordner> [--max 3] [--test]
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# eigener Prozess: Layout/Captions auf 9:16 stellen, ohne den gleichzeitig laufenden 16:9-Tageslauf zu beeinflussen
os.environ.setdefault("NEWS_FORMAT", "shorts")

from config.settings import NEWS_CONTENT_LANGUAGE, NEWS_WHISPER_MODEL, WHISPER_MODEL_DIR  # noqa: E402

MAX_DAUER_S = 58.0
MIN_TEXT_ZEICHEN = 150
AUSGESCHLOSSENE_SZENEN = {"themen", "s_themen"}   # Themen-Vorschau: keine eigenstaendige Aussage ausserhalb der Folge
AUSGESCHLOSSENE_MUSTER = re.compile(r"outro|verabschied|abschluss", re.I)   # Sign-off, keine eigene Aussage
FIXE_SZENEN_ERSTE = {"s_coldopen", "coldopen"}
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
FONT = r"C:\Windows\Fonts\arialbd.ttf"
KI_HINWEIS = ("Moderatorin Latara und ihre Stimme sind KI-generiert. Diese Short ist ein Ausschnitt aus der "
              "vollen Folge, Quellen und Einordnung dort.")


def _stamm(ordner: Path) -> str:
    return ordner.name


def _quelle_video(ordner: Path) -> Path:
    stamm = _stamm(ordner)
    clips = ordner / f"{stamm}_clips.mp4"
    return clips if clips.exists() else ordner / f"{stamm}.mp4"


def _szenen_zeiten(ordner: Path) -> list[dict]:
    pfad = ordner / f"{_stamm(ordner)}_stimmen.json"
    return json.loads(pfad.read_text(encoding="utf-8"))["szenen"]


def _szenen_texte(ordner: Path) -> dict[str, str]:
    pfad = ordner / "texte.json"
    if not pfad.exists():
        return {}
    texte = json.loads(pfad.read_text(encoding="utf-8"))
    return {s["id"]: s["text"] for s in texte.get("szenen") or [] if s.get("id") and s.get("text")}


def _video_id(ordner: Path) -> str | None:
    pfad = ordner / "upload.log"
    if not pfad.exists():
        return None
    for zeile in reversed(pfad.read_text(encoding="utf-8", errors="replace").splitlines()):
        m = re.search(r"Video-ID:\s*(\S+)", zeile)
        if m:
            return m.group(1)
    return None


def kandidaten(ordner: Path, max_anzahl: int = 3) -> list[dict]:
    """Szenen, die sich als eigenstaendiger Short eignen: unter MAX_DAUER_S Sekunden, mit echtem
    Sprechtext (keine reinen Marken-Clips wie Begruessung/Verabschiedung/Logo-Wisch - die haben keine
    eigene ID in texte.json und fallen damit automatisch raus). Cold Open (der geschriebene Hook) zuerst,
    danach die textreichsten passenden Meldungs-Szenen."""
    texte = _szenen_texte(ordner)
    liste = []
    for s in _szenen_zeiten(ordner):
        sid = Path(s["wav"]).stem
        text = texte.get(sid, "")
        if (sid in AUSGESCHLOSSENE_SZENEN or AUSGESCHLOSSENE_MUSTER.search(sid)
                or len(text) < MIN_TEXT_ZEICHEN or s["laenge"] > MAX_DAUER_S):
            continue
        liste.append({"id": sid, "start": float(s["start"]), "dauer": float(s["laenge"]), "text": text,
                      "label": s["label"]})
    liste.sort(key=lambda k: (k["id"] not in FIXE_SZENEN_ERSTE, -len(k["text"])))
    return liste[:max_anzahl]


def titel_frage(ordner: Path, kandidat: dict, meta: dict | None = None) -> str:
    meta = meta or json.loads((ordner / "metadaten.json").read_text(encoding="utf-8"))
    if kandidat["id"] in FIXE_SZENEN_ERSTE:
        return meta["title"]
    frage = (meta.get("kommentarfrage") or "").strip()
    if frage and frage in kandidat["text"]:
        return frage if frage.endswith("?") else frage + "?"
    saetze = re.split(r"(?<=[.!?])\s+", kandidat["text"].strip())
    letzter = saetze[-1].strip() if saetze else ""
    return letzter if letzter.endswith("?") else meta["title"]


def _ffmpeg(args: list[str], log=print):
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"] + [str(a) for a in args]
    r = subprocess.run(cmd, capture_output=True, text=True, creationflags=NO_WINDOW)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg fehlgeschlagen ({Path(str(args[-1])).name}): {r.stderr[-1500:]}")
    log(f"ffmpeg ok: {Path(str(args[-1])).name}")


def _segment_audio(quelle: Path, start: float, dauer: float, ziel_wav: Path, log=print):
    _ffmpeg(["-ss", f"{start:.3f}", "-t", f"{dauer:.3f}", "-i", quelle, "-vn", "-ac", "1", "-ar", "16000",
             ziel_wav], log)


def untertitel(wav: Path, text: str, ziel_ass: Path, log=print) -> Path:
    """Baut die ASS-Untertitel-Datei fuer einen Short wieder mit tts/align_captions.py: faster-whisper (CPU,
    int8 - braucht keine GPU/CUDA, siehe align_captions.run) fuer das Worttiming, die eigene Skript-
    Rechtschreibung (_use_script_spelling) fuer Namen/Zahlen, build_ass fuer den kinetischen Stil."""
    from faster_whisper import WhisperModel
    from tts.align_captions import _use_script_spelling, build_ass

    model = WhisperModel(NEWS_WHISPER_MODEL, device="cpu", compute_type="int8",
                         download_root=str(WHISPER_MODEL_DIR))
    segments, _ = model.transcribe(str(wav), word_timestamps=True, language=NEWS_CONTENT_LANGUAGE)
    words = [{"w": w.word.strip(), "s": round(w.start, 3), "e": round(w.end, 3)}
             for seg in segments for w in (seg.words or []) if w.word.strip()]
    words = _use_script_spelling(words, text)
    ziel_ass.write_text(build_ass(words), encoding="utf-8")
    log(f"Untertitel: {len(words)} Woerter")
    return ziel_ass


def _titelkarte(text: str, ziel_png: Path):
    """Titel-Band oben, gleiche Farbe wie der Untertitel-Akzent (align_captions.ACCENT, #FFD100)."""
    from PIL import Image, ImageDraw, ImageFont
    from video import layout as L

    hoehe = L.BAND_H + 40
    img = Image.new("RGBA", (L.W, hoehe), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, L.W, L.BAND_H], fill=(0, 0, 0, 190))
    font = ImageFont.truetype(FONT, 58)
    woerter, zeilen, zeile = text.split(), [], ""
    for w in woerter:
        probe = (zeile + " " + w).strip()
        if d.textlength(probe, font=font) > L.W - 80 and zeile:
            zeilen.append(zeile)
            zeile = w
        else:
            zeile = probe
    if zeile:
        zeilen.append(zeile)
    y = 30
    for z in zeilen[:3]:
        d.text((40, y), z, font=font, fill=(255, 209, 0, 255))
        y += 70
    img.save(ziel_png)


def _short_rendern(quelle: Path, start: float, dauer: float, ass: Path, titelkarte: Path, ziel: Path,
                   log=print):
    ass_filter = str(ass).replace("\\", "/").replace(":", "\\:")
    filt = ("[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=40[bg];"
            "[0:v]scale=1080:-2[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2[v1];"
            f"[v1]subtitles='{ass_filter}'[v2];"
            "[1:v]scale=1080:-1[tk];"
            "[v2][tk]overlay=0:60:enable='between(t,0,4)'[v]")
    _ffmpeg(["-ss", f"{start:.3f}", "-t", f"{dauer:.3f}", "-i", quelle,
             "-loop", "1", "-t", f"{dauer:.3f}", "-i", titelkarte,
             "-filter_complex", filt, "-map", "[v]", "-map", "0:a",
             "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", ziel], log)


def baue(ordner: Path, max_anzahl: int = 3, log=print) -> list[dict]:
    """Baut bis zu max_anzahl Shorts aus der fertigen Folge in <ordner>, legt mp4+json je Short unter
    <ordner>/shorts/ ab. Rueckgabe: [{"mp4", "meta", "dauer", "titel"}, ...]."""
    ordner = Path(ordner)
    quelle = _quelle_video(ordner)
    if not quelle.exists():
        raise FileNotFoundError(f"kein fertiges Video in {ordner}")
    meta = json.loads((ordner / "metadaten.json").read_text(encoding="utf-8"))
    video_id = _video_id(ordner)
    ziel_dir = ordner / "shorts"
    ziel_dir.mkdir(exist_ok=True)
    gefunden = kandidaten(ordner, max_anzahl)
    ergebnisse = []
    for i, k in enumerate(gefunden, start=1):
        titel = titel_frage(ordner, k, meta)
        stamm = f"short_{i}_{k['id']}"
        wav, ass = ziel_dir / f"{stamm}.wav", ziel_dir / f"{stamm}.ass"
        titelkarte, mp4 = ziel_dir / f"{stamm}_titel.png", ziel_dir / f"{stamm}.mp4"
        log(f"Short {i}/{len(gefunden)}: {k['label']} ({k['dauer']:.0f} s) - Titel: {titel}")
        _segment_audio(quelle, k["start"], k["dauer"], wav, log)
        untertitel(wav, k["text"], ass, log)
        _titelkarte(titel, titelkarte)
        _short_rendern(quelle, k["start"], k["dauer"], ass, titelkarte, mp4, log)
        beschreibung = titel + "\n\n"
        if video_id:
            beschreibung += f"Ganze Folge: https://youtu.be/{video_id}\n\n"
        beschreibung += KI_HINWEIS + "\n\n#Shorts #WeltlageKompakt #Nachrichten #Weltpolitik"
        meta_short = {"title": titel if len(titel) <= 100 else titel[:97] + "...", "description": beschreibung,
                     "tags": list(dict.fromkeys((meta.get("tags") or []) + ["Shorts"])),
                     "language": meta.get("language", "de"), "dauer_s": k["dauer"]}
        (ziel_dir / f"{stamm}.json").write_text(json.dumps(meta_short, ensure_ascii=False, indent=1),
                                                encoding="utf-8")
        ergebnisse.append({"mp4": mp4, "meta": meta_short, "dauer": k["dauer"], "titel": titel})
    return ergebnisse


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("ordner", type=Path)
    p.add_argument("--max", type=int, default=3)
    p.add_argument("--test", action="store_true", help="nur Kandidaten auflisten, nichts rendern")
    a = p.parse_args()
    if a.test:
        for k in kandidaten(a.ordner, a.max):
            print(f"{k['id']}: {k['dauer']:.1f} s - {titel_frage(a.ordner, k)}")
        return
    for erg in baue(a.ordner, a.max):
        print(f"{erg['mp4']}  ({erg['dauer']:.0f} s)  {erg['titel']}")


if __name__ == "__main__":
    main()
