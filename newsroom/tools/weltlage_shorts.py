#!/usr/bin/env python
"""Weltlage Kompakt: vertikale Shorts (9:16, unter 60 s) aus einer fertigen Folge schneiden.

Hintergrund (Analyse 11.10.2026, reports/youtube-kanal/weltlage-analyse-20261011): der Kanal hat trotz
fertiger Shorts-Technik (NEWS_FORMAT=shorts, video/layout.py) noch keine einzige echte Short
veroeffentlicht. Statt einer komplett neu produzierten Shorts-Folge schneidet dieses Modul aus einer
bereits fertigen 16:9-Folge die staerkste Aussage heraus:

- Szenen-Zeiten kommen aus <stamm>_stimmen.json (dieselbe Datei, die die Stimmpruefung am Videoanfang
  nutzt: Label, Start, Laenge, Referenz-WAV je Szene).
- Der Sprechtext je Szene kommt aus texte.json (Szenen-ID = Dateiname des Referenz-WAV ohne Endung).
- Quelle ist die fertige B-Roll-Fassung <stamm>_clips.mp4 (dieselbe Datei, die auch hochgeladen wird).
- Untertitel/Geometrie nutzen dieselben Bausteine wie die bestehende Shorts-Pipeline: video/layout.py
  (9:16-Groessen) und tts/align_captions.py (Whisper-Worttiming -> ASS, Skript-Rechtschreibung).

Aufbau pro Short (rexemre 13.10.2026, Feedback nach dem ersten echten Short: "momentan ist der ganze Clip
nur ein Aufhaenger. Es soll auch Informationen liefern"): vorher war ein Short genau EINE Szene, und wenn
das zufaellig der Cold Open war (der geschriebene Hook der Folge), lieferte die Short gar keine eigene
Information. Jetzt ist jeder Short immer dreiteilig, alle drei Teile aus der bereits fertigen Folge
geschnitten (kein neuer Text, keine neue Stimme/Lipsync - das bliebe der Langfolge vorbehalten):
  1. Hook: der volle Cold Open (meist ~25-30 s), wie bisher mit Titelkarte in den ersten 4 s.
  2. Fakten: die textreichste Meldungs-Szene, an einer Satzgrenze gekuerzt, damit der Gesamt-Short unter
     ZIEL_GESAMT_S bleibt (_satzgrenze - nie mitten im Satz abschneiden, nutzt dieselbe Whisper+Skript-
     Ausrichtung wie die Untertitel). Das liefert die eigentlichen Fakten/Zahlen der Meldung.
  3. Verweis-Karte: 3-4 s Standbild, das auf die ausfuehrliche Folge verweist (zusaetzlich zum Link in der
     Beschreibung).
Mit --max > 1 bekommt jeder weitere Short dieselbe Hook+Verweis-Rahmung, aber eine andere Fakten-Szene
(die naechsttextreichste), nie eine zweite Short nur mit dem Hook allein.

Aufruf: tools/weltlage_shorts.py <ordner> [--max 2] [--test]
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

MIN_TEXT_ZEICHEN = 150
AUSGESCHLOSSENE_SZENEN = {"themen", "s_themen"}   # Themen-Vorschau: keine eigenstaendige Aussage ausserhalb der Folge
AUSGESCHLOSSENE_MUSTER = re.compile(r"outro|verabschied|abschluss", re.I)   # Sign-off, keine eigene Aussage
FIXE_SZENEN_ERSTE = {"s_coldopen", "coldopen"}
ZIEL_GESAMT_S = 55.0     # Zielgesamtlaenge Hook+Fakten+Verweis, Sicherheitsabstand zum 60-s-Limit von Shorts
OUTRO_DAUER_S = 3.5
FAKTEN_MIN_S = 10.0      # auch wenn der Hook schon lang ist: mindestens so viel Fakten-Zeit
FAKTEN_MAX_S = 35.0      # auch wenn der Hook kurz/leer ist: nie zu lang, Short bleibt schnell
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
FONT = r"C:\Windows\Fonts\arialbd.ttf"
OUTRO_TEXT = ["Mehr dazu in der", "ausführlichen Folge:", "Link in der Beschreibung"]
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


def _hook_kandidat(ordner: Path) -> dict | None:
    """Der Cold Open als eigener, voller Hook-Teil (immer zuerst im Short, nie gekuerzt)."""
    texte = _szenen_texte(ordner)
    for s in _szenen_zeiten(ordner):
        sid = Path(s["wav"]).stem
        if sid in FIXE_SZENEN_ERSTE:
            text = texte.get(sid, "")
            if text:
                return {"id": sid, "start": float(s["start"]), "dauer": float(s["laenge"]), "text": text,
                        "label": s["label"]}
    return None


def fakten_kandidaten(ordner: Path, max_anzahl: int = 1) -> list[dict]:
    """Szenen fuer den Fakten-Teil: wie bisher die textreichsten Meldungs-Szenen, ohne den Cold Open (der
    ist der eigene Hook-Teil) und ohne Marken-Clips ohne eigene Aussage. Keine MAX_DAUER_S-Grenze mehr -
    der Fakten-Teil wird ohnehin auf eine Satzgrenze innerhalb des Zeitbudgets gekuerzt (_satzgrenze)."""
    texte = _szenen_texte(ordner)
    liste = []
    for s in _szenen_zeiten(ordner):
        sid = Path(s["wav"]).stem
        text = texte.get(sid, "")
        if (sid in FIXE_SZENEN_ERSTE or sid in AUSGESCHLOSSENE_SZENEN or AUSGESCHLOSSENE_MUSTER.search(sid)
                or len(text) < MIN_TEXT_ZEICHEN):
            continue
        liste.append({"id": sid, "start": float(s["start"]), "dauer": float(s["laenge"]), "text": text,
                      "label": s["label"]})
    liste.sort(key=lambda k: -len(k["text"]))
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


def _woerter_ausgerichtet(wav: Path, text: str, log=print) -> list[dict]:
    """Whisper-Worttiming (CPU, int8 - braucht keine GPU/CUDA, siehe tts/align_captions.run) + Ausrichtung
    auf den Skripttext (_use_script_spelling: Namen/Zahlen/Interpunktion kommen vom Skript, nicht von
    Whisper). Wird fuer die Untertitel UND fuer die Satzgrenzen-Suche des Fakten-Teils gebraucht."""
    from faster_whisper import WhisperModel
    from tts.align_captions import _use_script_spelling

    model = WhisperModel(NEWS_WHISPER_MODEL, device="cpu", compute_type="int8",
                         download_root=str(WHISPER_MODEL_DIR))
    segments, _ = model.transcribe(str(wav), word_timestamps=True, language=NEWS_CONTENT_LANGUAGE)
    words = [{"w": w.word.strip(), "s": round(w.start, 3), "e": round(w.end, 3)}
             for seg in segments for w in (seg.words or []) if w.word.strip()]
    words = _use_script_spelling(words, text)
    log(f"Worttiming: {len(words)} Woerter")
    return words


def _satzgrenze(words: list[dict], text: str, ziel_s: float) -> tuple[float, str]:
    """Letzter vollstaendige Satz, der noch (ungefaehr) ins Zeitbudget ziel_s passt - schneidet nie mitten
    im Satz ab. words muessen in derselben Reihenfolge wie text.split() stehen (siehe
    _woerter_ausgerichtet/_use_script_spelling). Passt kein einziger Satz ins Budget, wird der erste Satz
    trotzdem ganz genommen (lieber etwas laenger als mitten im Satz)."""
    saetze = [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]
    schnitt_s, text_bis, gezaehlt = None, "", 0
    for satz in saetze:
        gezaehlt += len(satz.split())
        idx = min(gezaehlt, len(words)) - 1
        if idx < 0:
            break
        ende = words[idx]["e"]
        if schnitt_s is not None and ende > ziel_s:
            break
        schnitt_s, text_bis = ende, (text_bis + " " + satz).strip()
        if ende >= ziel_s:
            break
    if schnitt_s is None:
        schnitt_s, text_bis = (words[-1]["e"] if words else 0.0), text.strip()
    return schnitt_s, text_bis


def untertitel(words: list[dict], ziel_ass: Path, log=print) -> Path:
    from tts.align_captions import build_ass
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


def _outro_karte(ziel_png: Path):
    """Vollbild-Verweis auf die ausfuehrliche Folge (rexemre 13.10.2026: jeder Short soll am Schluss kurz
    zurueck auf die lange Fassung zeigen, zusaetzlich zum Link in der Beschreibung)."""
    from PIL import Image, ImageDraw, ImageFont
    from video import layout as L

    img = Image.new("RGB", (L.W, L.H), (12, 12, 12))
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT, 72)
    zeilenhoehen = [d.textbbox((0, 0), z, font=font)[3] for z in OUTRO_TEXT]
    gesamt_h = sum(zeilenhoehen) + 24 * (len(OUTRO_TEXT) - 1)
    y = (L.H - gesamt_h) // 2
    for z, h in zip(OUTRO_TEXT, zeilenhoehen):
        breite = d.textlength(z, font=font)
        d.text(((L.W - breite) / 2, y), z, font=font, fill=(255, 209, 0, 255))
        y += h + 24
    img.save(ziel_png)


def _short_rendern(quelle: Path, start: float, dauer: float, ass: Path, ziel: Path,
                   titelkarte: Path | None = None, log=print):
    ass_filter = str(ass).replace("\\", "/").replace(":", "\\:")
    eingaben = ["-ss", f"{start:.3f}", "-t", f"{dauer:.3f}", "-i", quelle]
    filt = ("[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=40[bg];"
            "[0:v]scale=1080:-2[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2[v1];"
            f"[v1]subtitles='{ass_filter}'[v2]")
    video_label = "[v2]"
    if titelkarte is not None:
        eingaben += ["-loop", "1", "-t", f"{dauer:.3f}", "-i", titelkarte]
        filt += ";[1:v]scale=1080:-1[tk];[v2][tk]overlay=0:60:enable='between(t,0,4)'[v]"
        video_label = "[v]"
    _ffmpeg(eingaben + ["-filter_complex", filt, "-map", video_label, "-map", "0:a",
             "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", ziel], log)


def _outro_rendern(dauer: float, titelkarte: Path, ziel: Path, log=print):
    _ffmpeg(["-loop", "1", "-i", titelkarte,
             "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
             "-t", f"{dauer:.3f}",
             "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", ziel], log)


def _concat(teile: list[Path], ziel: Path, log=print):
    """Haengt die fertig gerenderten Teile (Hook/Fakten/Verweis, jeweils schon 1080x1920 h264+aac) zu
    einem Short zusammen. Ueber einen Filtergraph statt dem concat-Demuxer, damit kleine Abweichungen in
    Keyframes/Sample-Format zwischen den Teilen nicht zu einem kaputten Schnitt fuehren."""
    eingaben = []
    for t in teile:
        eingaben += ["-i", str(t)]
    teilgraphen, labels = [], []
    for i in range(len(teile)):
        teilgraphen.append(f"[{i}:v]format=yuv420p,setsar=1[v{i}]")
        teilgraphen.append(f"[{i}:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[a{i}]")
        labels += [f"[v{i}]", f"[a{i}]"]
    teilgraphen.append("".join(labels) + f"concat=n={len(teile)}:v=1:a=1[v][a]")
    _ffmpeg(eingaben + ["-filter_complex", ";".join(teilgraphen), "-map", "[v]", "-map", "[a]",
             "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", ziel], log)


def _baue_einen(ziel_dir: Path, hook: dict | None, fakten: dict | None, meta: dict, video_id: str | None,
                index: int, quelle: Path, ordner: Path, log=print) -> dict:
    titel = titel_frage(ordner, hook or fakten, meta)
    stamm = f"short_{index}_{(hook['id'] + '_') if hook else ''}{fakten['id'] if fakten else 'hook'}"
    teile: list[Path] = []
    hook_dauer = 0.0
    if hook:
        hwav, hass = ziel_dir / f"{stamm}_hook.wav", ziel_dir / f"{stamm}_hook.ass"
        htitelkarte, hmp4 = ziel_dir / f"{stamm}_hook_titel.png", ziel_dir / f"{stamm}_hook.mp4"
        log(f"Short {index}: Hook {hook['label']} ({hook['dauer']:.0f} s)")
        _segment_audio(quelle, hook["start"], hook["dauer"], hwav, log)
        hwords = _woerter_ausgerichtet(hwav, hook["text"], log)
        untertitel(hwords, hass, log)
        _titelkarte(titel, htitelkarte)
        _short_rendern(quelle, hook["start"], hook["dauer"], hass, hmp4, titelkarte=htitelkarte, log=log)
        teile.append(hmp4)
        hook_dauer = hook["dauer"]

    schnitt_s = 0.0
    if fakten:
        ziel_fakten_s = min(FAKTEN_MAX_S, max(FAKTEN_MIN_S, ZIEL_GESAMT_S - hook_dauer - OUTRO_DAUER_S))
        fwav_voll = ziel_dir / f"{stamm}_fakten_voll.wav"
        _segment_audio(quelle, fakten["start"], fakten["dauer"], fwav_voll, log)
        fwords_voll = _woerter_ausgerichtet(fwav_voll, fakten["text"], log)
        schnitt_s, _ = _satzgrenze(fwords_voll, fakten["text"], ziel_fakten_s)
        schnitt_s = min(schnitt_s, fakten["dauer"])
        fwords = [w for w in fwords_voll if w["e"] <= schnitt_s + 0.05]
        fass, fmp4 = ziel_dir / f"{stamm}_fakten.ass", ziel_dir / f"{stamm}_fakten.mp4"
        log(f"Short {index}: Fakten {fakten['label']} (gekuerzt auf {schnitt_s:.0f} von {fakten['dauer']:.0f} s)")
        untertitel(fwords, fass, log)
        _short_rendern(quelle, fakten["start"], schnitt_s, fass, fmp4, titelkarte=None, log=log)
        teile.append(fmp4)

    otitelkarte, omp4 = ziel_dir / f"{stamm}_outro.png", ziel_dir / f"{stamm}_outro.mp4"
    _outro_karte(otitelkarte)
    _outro_rendern(OUTRO_DAUER_S, otitelkarte, omp4, log)
    teile.append(omp4)

    mp4 = ziel_dir / f"{stamm}.mp4"
    _concat(teile, mp4, log)
    dauer_gesamt = hook_dauer + schnitt_s + OUTRO_DAUER_S

    beschreibung = titel + "\n\n"
    if video_id:
        beschreibung += f"Ganze Folge mit allen Quellen: https://youtu.be/{video_id}\n\n"
    beschreibung += KI_HINWEIS + "\n\n#Shorts #WeltlageKompakt #Nachrichten #Weltpolitik"
    meta_short = {"title": titel if len(titel) <= 100 else titel[:97] + "...", "description": beschreibung,
                 "tags": list(dict.fromkeys((meta.get("tags") or []) + ["Shorts"])),
                 "language": meta.get("language", "de"), "dauer_s": dauer_gesamt}
    try:
        from tools.weltlage_shorts_thumbnail import fuer_short
        thumb = fuer_short(meta_short, ziel_dir / f"{stamm}_thumb.jpg", ordner=ordner)
        meta_short["thumbnail"] = str(thumb)
    except Exception as e:   # noqa: BLE001 - eigenes Thumbnail ist Zusatznutzen, darf den Schnitt nie stoppen
        log(f"Short {index}: eigenes Thumbnail nicht gebaut ({type(e).__name__}: {e})")
    (ziel_dir / f"{stamm}.json").write_text(json.dumps(meta_short, ensure_ascii=False, indent=1),
                                            encoding="utf-8")
    return {"mp4": mp4, "meta": meta_short, "dauer": dauer_gesamt, "titel": titel}


def baue(ordner: Path, max_anzahl: int = 1, log=print) -> list[dict]:
    """Baut bis zu max_anzahl Shorts aus der fertigen Folge in <ordner>. Jeder Short ist Hook (Cold Open)
    + Fakten-Ausschnitt + Verweis-Karte (siehe Modul-Docstring); mit max_anzahl > 1 teilen sich alle Shorts
    denselben Hook, bekommen aber je eine andere Fakten-Szene. Legt mp4+json je Short unter
    <ordner>/shorts/ ab. Rueckgabe: [{"mp4", "meta", "dauer", "titel"}, ...]."""
    ordner = Path(ordner)
    quelle = _quelle_video(ordner)
    if not quelle.exists():
        raise FileNotFoundError(f"kein fertiges Video in {ordner}")
    meta = json.loads((ordner / "metadaten.json").read_text(encoding="utf-8"))
    video_id = _video_id(ordner)
    ziel_dir = ordner / "shorts"
    ziel_dir.mkdir(exist_ok=True)
    hook = _hook_kandidat(ordner)
    fakten_liste = fakten_kandidaten(ordner, max_anzahl) or [None]
    if hook is None and fakten_liste == [None]:
        log("Keine Szene gefunden, die sich als Short eignet (kein Cold Open, keine Meldung mit genug Text)")
        return []
    return [_baue_einen(ziel_dir, hook, f, meta, video_id, i, quelle, ordner, log)
            for i, f in enumerate(fakten_liste, start=1)]


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("ordner", type=Path)
    p.add_argument("--max", type=int, default=1)
    p.add_argument("--test", action="store_true", help="nur Kandidaten auflisten, nichts rendern")
    a = p.parse_args()
    if a.test:
        hook = _hook_kandidat(a.ordner)
        if hook:
            print(f"HOOK {hook['id']}: {hook['dauer']:.1f} s")
        for k in fakten_kandidaten(a.ordner, a.max):
            print(f"FAKTEN {k['id']}: {k['dauer']:.1f} s, {len(k['text'])} Zeichen")
        return
    for erg in baue(a.ordner, a.max):
        print(f"{erg['mp4']}  ({erg['dauer']:.0f} s)  {erg['titel']}")


if __name__ == "__main__":
    main()
