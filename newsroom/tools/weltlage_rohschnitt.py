"""Weltlage Kompakt - Rohschnitt Langformat nach docs/weltlage_szenenplan.md (Struktur vom 30.09.2026, rexemre).

Liest aus einem Folgenordner (Default data/weltlage_test_20260929):
  texte.json   Sprechtexte pro Szene/Meldung (id, szene, bild, bei Meldungen "kurz" fuer die Themen-Szene;
               "s_coldopen" = Cold Open, fehlt er, erzeugt tools/weltlage_update_themen.py ihn; optional "ort" =
               Hintergrund aus config/brand/orte/orte.json, z.B. "bruessel": Latara steht dann dort (video/orte.py,
               Werte aus tools/orte_platzieren.py); ohne "ort" oder "studio" bleibt alles wie bisher)
  audio/<id>.wav  Lataras Stimme = Chatterbox-Klon Ramona pro Eintrag (tools/weltlage_tts.py, rexemres Entscheid
                  30.09.2026; s_themen zuvor mit tools/weltlage_update_themen.py aus den "kurz"-Feldern generieren).
                  Der Rohschnitt bricht ab, wenn eine gesprochene Datei nicht nachweislich Chatterbox ist
                  (24 kHz mono + Engine-Nachweis audio/<id>.tts.json mit passendem Hash; Piper = 16 kHz).
  bilder.json  Screenshots pro Meldung (bilder_holen.py, video/sources.capture)
und baut 1920x1080 / 24 fps / H.264 + AAC in dieser Reihenfolge:
  Cold Open (v6 stehend, pro Folge neu: Anriss der Top-Meldungen, rexemre 30.09.2026 abends wieder als ERSTE Szene,
  weiche Ueberblendung in den Bumper) - Welt-Bumper (bumper/aktiv.json) - Intro (intro/aktiv.json) - Reinlaufen/Auftritt (fester Clip
  szene3_auftritt/aktiv.json, unveraendert) - Begruessung (fest eingefroren, begruessung/aktiv.json,
  tools/weltlage_begruessung.py, in jeder Folge identisch) - Logo-Wisch (kurzer Marken-Uebergang,
  uebergang/aktiv.json, tools/weltlage_uebergang.py, ersetzt den harten Schnitt) - Themen (v6 stehend,
  pro Folge neu, Text automatisch aus den Meldungs-Schlagzeilen) - Logo-Wisch (zweite Einblendung derselben
  Vorlage, rexemre 04.10.2026: ersetzt den harten Schnitt beim Wechsel von der stehenden Themen-Szene in die
  sitzende Meldungen-Szene) - Meldungen sitzend mit Schnittbildern - Verabschiedung (v6 stehend, seit 02.10.2026
  ebenfalls fest eingefroren, verabschiedung/aktiv.json, tools/weltlage_verabschiedung.py - gleicher Text in
  jeder Folge) - Abschluss (v6 stehend, fest eingefroren, abschluss/aktiv.json, tools/weltlage_abschluss.py,
  rexemre 04.10.2026: kurzer Kanal-Abschluss mit Latara, WK-Logo und animiertem Abo-Hinweis, ersetzt die alte
  Outro-Grafik ohne Latara).
Die alte Szene "Themenüberblick" entfaellt seit 30.09.2026 (ersetzt durch Begruessung + Themen). Der Cold Open war
am 30.09. mittags ebenfalls gestrichen und ist seit dem Abend auf rexemres Wunsch wieder die erste Szene.

Stimmen-Nachweis (rexemre 30.09.2026): vor dem Schnitt muss jede gesprochene Datei (Cold Open, Begruessung, Themen,
Meldungen, Verabschiedung) nachweislich der Chatterbox-Klon sein (tools/weltlage_tts.pruefe_stimme), sonst Abbruch.
Nach dem Schnitt gleicht tools/weltlage_stimmpruefung.py jede Sprechszene im fertigen Video gegen genau diese Datei
ab (<video>_stimmen.json); faellt eine durch, wird das Video in *_UNGUELTIG.mp4 umbenannt und der Lauf bricht ab.

Lipsync (Standard, sobald LatentSync da ist) nach der festen Regel vom 29.09.2026 (video/freisteller_lipsync.py):
alle Sprechszenen (Begruessung, Themen, Meldungen) werden auf dem FREISTELLER der Moderatorin in voller
Quellaufloesung gelipsynct, Alpha bleibt erhalten, erst danach wird sie in der abgemachten Platzierung direkt in
1920x1080 ins Studio gesetzt. Nie Lipsync auf dem fertigen Studiobild. LatentSync-Stuecke liegen zwischengespeichert
in <work>/_freisteller.

    .venv-lipsync\\Scripts\\python.exe tools/weltlage_rohschnitt.py [folgenordner] [--out datei.mp4] [--work ordner]
        [--ohne-lipsync]      alter Stand: stehend ohne Lipsync, sitzend = composite_host_v4_full.mp4
        [--lip <mp4>]         alte fertige Sitz-Spur fuer die Meldungen (stehend dann ohne Lipsync)
        [--kurztest]          nur Reinlaufen + Begruessung + Logo-Wisch + Themen + Anfang der Sitz-Szene
                               (eine Meldung), kein Bumper/Intro/Verabschiedung/Abschluss - kurzer Clip zum
                               Gegenpruefen der Struktur
"""
import json
import os
import re
import statistics
import subprocess
import sys
import time
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from av_sync import align_parts

ROOT = Path(__file__).resolve().parents[1]
BRAND = ROOT / "config" / "brand"
V6 = BRAND / "szene1_stehend_animation" / "szene1_stehend_v6_neuer_hintergrund.mp4"
SITZ = BRAND / "studio_bg" / "composite_host_v4_full.mp4"
# Intro: seit 20.10.2026 IMMER das Unreal-Standard-Intro (tools/weltlage_intro.py baut es pro Folge mit Tageskursen +
# Datumsansage); das alte Globus-Intro ist abgeloest, aktiv.json zeigt darauf (Abnahme prueft das).
INTRO = BRAND / "intro" / "weltlage_intro_unreal_standard.mp4"
LOGO = BRAND / "logo.png"
_BUMPER_CFG = BRAND / "bumper" / "aktiv.json"
_bumper = json.loads(_BUMPER_CFG.read_text(encoding="utf-8")).get("landscape") if _BUMPER_CFG.exists() else None
BUMPER = BRAND / "bumper" / _bumper if _bumper else None   # Welt-Bumper A2 eroeffnet die Folge (Struktur 30.09.: kein Cold Open mehr davor)
# Szene «Reinlaufen/Auftritt»: Latara laeuft von links ins Studio, letzter Frame = erster Frame der stehenden
# v6-Pose (Frame 0 im Studio). In jeder Folge identisch, einmal gebaut und eingefroren (tools/szene3_auftritt.py,
# 29.09.2026); kein Text, kein Sprechton. rexemre 30.09.2026: "ist gut so, unveraendert lassen".
_S3_CFG = BRAND / "szene3_auftritt" / "aktiv.json"
_s3 = json.loads(_S3_CFG.read_text(encoding="utf-8")).get("landscape") if _S3_CFG.exists() else None
SZENE3 = BRAND / "szene3_auftritt" / _s3 if _s3 else None
# Begruessungs-Vorlage (Struktur 30.09.2026, rexemre): Latara begruesst das Publikum allgemein, ohne Datum/Themen -
# in jeder Folge identisch, einmal gebaut und eingefroren (tools/weltlage_begruessung.py), nie neu gerendert.
_BEGR_CFG = BRAND / "begruessung" / "aktiv.json"
_begr_meta = json.loads(_BEGR_CFG.read_text(encoding="utf-8")) if _BEGR_CFG.exists() else {}
BEGRUESSUNG = BRAND / "begruessung" / _begr_meta["landscape"] if _begr_meta.get("landscape") else None
# Stimm-Datei der Begruessung samt Engine-Nachweis (weltlage_begruessung.freeze legt sie neben den Clip)
BEGRUESSUNG_STIMME = BRAND / "begruessung" / _begr_meta["stimme_wav"] if _begr_meta.get("stimme_wav") else None
# Verabschiedungs-Vorlage (analog, 02.10.2026, tools/weltlage_verabschiedung.py): der Text ist in jeder Folge
# wortgleich ("s6_outro fest" in texte.json, siehe tools/weltlage_skript.py OUTRO), darum ebenfalls einmal gebaut
# und eingefroren statt jede Folge neu vertont und gelipsynct. Fehlt config/brand/verabschiedung/aktiv.json noch
# (vor dem ersten Bau), bleibt der alte Pro-Folge-Weg unten unveraendert - rueckwaertskompatibel.
_VERAB_CFG = BRAND / "verabschiedung" / "aktiv.json"
_verab_meta = json.loads(_VERAB_CFG.read_text(encoding="utf-8")) if _VERAB_CFG.exists() else {}
VERABSCHIEDUNG = BRAND / "verabschiedung" / _verab_meta["landscape"] if _verab_meta.get("landscape") else None
VERABSCHIEDUNG_STIMME = BRAND / "verabschiedung" / _verab_meta["stimme_wav"] if _verab_meta.get("stimme_wav") else None
# Abschluss-Vorlage (fest eingefroren, rexemre 04.10.2026, tools/weltlage_abschluss.py): kurzer, eigenstaendiger
# Kanal-Abschluss mit Latara (zeitloser Ausblick-Satz, kein Folgeninhalt) + WK-Logo + animiertem Abo-Hinweis -
# ersetzt die alte Outro-Grafik (output/outro_v3, nur Musik/Logo, keine Latara, kein Abo-Hinweis-Text) als letzte
# Szene der Folge. Analoges Muster zu Begruessung/Verabschiedung.
_ABSCHL_CFG = BRAND / "abschluss" / "aktiv.json"
_abschl_meta = json.loads(_ABSCHL_CFG.read_text(encoding="utf-8")) if _ABSCHL_CFG.exists() else {}
ABSCHLUSS = BRAND / "abschluss" / _abschl_meta["landscape"] if _abschl_meta.get("landscape") else None
ABSCHLUSS_STIMME = BRAND / "abschluss" / _abschl_meta["stimme_wav"] if _abschl_meta.get("stimme_wav") else None
# Logo-Wisch (Variante A, rexemre 30.09.2026): kurzer Marken-Uebergang zwischen Begruessung und Themen,
# ersetzt den harten Schnitt - eigenstaendige Vorlage wie Bumper/Intro, unabhaengig vom Folgeninhalt,
# kein bildgenaues Standbild-Scharnier (tools/weltlage_uebergang.py).
_UEB_CFG = BRAND / "uebergang" / "aktiv.json"
_ueb_meta = json.loads(_UEB_CFG.read_text(encoding="utf-8")) if _UEB_CFG.exists() else {}
UEBERGANG = BRAND / "uebergang" / _ueb_meta["landscape"] if _ueb_meta.get("landscape") else None
# V6-Zeitposition, an der die eingefrorene Begruessung endet (aus tools/weltlage_begruessung.py freeze()).
# Bildgenauer Anschluss (rexemre 30.09.2026): die Themen-Szene startet exakt hier im selben V6-Material, letzter
# Frame Begruessung = erster Frame Themen - keine neue Bewegung, direkte Fortsetzung derselben Performance.
BEGRUESSUNG_ENDE = _begr_meta.get("laenge_s")
# v6-Bilder (16 fps), die praktisch dem Frame 0 entsprechen (Segmentgrenzen der First-Last-Frame-Segmente, mittlere
# Abweichung <= 1,7/255): Rueckfallposition fuer die Themen-Szene, falls keine Begruessung eingefroren ist.
V6_RUHEPUNKTE = (0.0, 157 / 16, 234 / 16, 311 / 16, 388 / 16)
ABO_ICON = BRAND / "endscreen" / "abo_hinweis_icon.mov"   # animierter Abo-Hinweis mit Text (seit 04.10.2026 nur noch
                                                           # einmal, in der Szene Abschluss), Alpha, tools/endscreen_overlay.py

_ff = next(iter(Path(os.environ["LOCALAPPDATA"]).glob("Microsoft/WinGet/Packages/Gyan.FFmpeg*/*/bin")), None)
FFMPEG = str(_ff / "ffmpeg.exe") if _ff else "ffmpeg"
FFPROBE = str(_ff / "ffprobe.exe") if _ff else "ffprobe"

W, H, FPS, SR = 1920, 1080, 24, 48000
CH = 2                # Programmton Stereo bis zum Ende (Stimme mono -> beide Kanaele gleich, Musik bleibt Stereo)
MASTER_LUFS, MASTER_TP, MASTER_KBPS = -14.0, -1.5, "256k"   # einmal, linear, im Master (master_ton)
MARKE_UEBER_SPRACHE_DB = 1.5   # Bumper/Intro/Outro-Musik hoechstens so viel lauter als die Stimme (marke_angleichen)
VENC = ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(FPS)]
GAP = 0.45            # Pause zwischen Meldungen
HOST_LEAD = 4.0       # Latara sichtbar am Anfang jeder Meldung
CUT_LEN = 5.5         # Dauer eines Schnittbilds
HOST_BACK = 3.0       # Latara zwischen zwei Schnittbildern
FONT_B = "C:/Windows/Fonts/arialbd.ttf"
FONT_R = "C:/Windows/Fonts/arial.ttf"


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise RuntimeError(" ".join(map(str, cmd))[:400] + "\n" + r.stderr[-2000:])


def dur(path: Path) -> float:
    if path.suffix == ".wav":
        with wave.open(str(path)) as w:
            return w.getnframes() / w.getframerate()
    out = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True).stdout
    return float(out.strip())


def scale_crop():
    return f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={FPS}"


def clip(src: Path, start: float, length: float, out: Path, loop=False):
    pre = ["-stream_loop", "-1"] if loop else []
    run([FFMPEG, "-y", *pre, "-ss", f"{start:.3f}", "-i", str(src), "-t", f"{length:.3f}", "-an",
         "-vf", scale_crop(), *VENC, str(out)])


def still_clip(png: Path, length: float, out: Path, zoom=True):
    frames = max(1, round(length * FPS))
    vf = (f"scale={W*2}:{H*2},zoompan=z='1+0.06*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
          f":d={frames}:s={W}x{H}:fps={FPS},setsar=1") if zoom else f"scale={W}:{H},setsar=1,fps={FPS}"
    run([FFMPEG, "-y", "-loop", "1", "-i", str(png), "-t", f"{length:.3f}", "-vf", vf, *VENC, str(out)])


def abo_overlay(video: Path, at: float, out: Path):
    """Legt das Abo-Symbol (Alpha) ab Sekunde `at` ueber `video`."""
    if not ABO_ICON.exists():
        video.replace(out)
        return
    run([FFMPEG, "-y", "-i", str(video), "-itsoffset", f"{at:.3f}", "-i", str(ABO_ICON), "-filter_complex",
         f"[1:v]fps={FPS},format=yuva444p[i];[0:v][i]overlay=0:0:eof_action=pass:format=auto[v]", "-map", "[v]",
         *VENC, str(out)])


def frame_at(src: Path, t: float, out: Path):
    run([FFMPEG, "-y", "-ss", f"{t:.3f}", "-i", str(src), "-frames:v", "1", "-vf", f"scale={W}:{H}", str(out)])


def font(size, bold=True):
    return ImageFont.truetype(FONT_B if bold else FONT_R, size)


def placeholder_plate(bg_png: Path, title: str, sub: str, out: Path):
    im = Image.open(bg_png).convert("RGB").resize((W, H))
    im = ImageEnhance.Brightness(im).enhance(0.55)
    d = ImageDraw.Draw(im, "RGBA")
    d.rectangle([0, H - 230, W, H - 60], fill=(8, 20, 45, 215))
    d.rectangle([0, H - 230, 14, H - 60], fill=(200, 30, 40, 255))
    d.text((60, H - 210), "PLATZHALTER", font=font(34), fill=(255, 200, 60))
    d.text((60, H - 165), title, font=font(52), fill="white")
    d.text((60, H - 100), sub, font=font(30, False), fill=(210, 220, 235))
    im.save(out)


def _in_box_einpassen(img: Image.Image, max_w: int, max_h: int) -> Image.Image:
    """Echtes 'fit' (contain), nie 'fill'/Crop und nie Reinzoomen in einen Teilbereich: skaliert so, dass das
    GANZE Bild in max_w x max_h passt - je nachdem, welche Seite der Engpass ist. Vorher wurde immer auf eine
    feste Hoehe skaliert (die Breite blieb unbegruenzt); bei einem besonders hohen Screenshot lief dessen Breite
    dadurch ueber den Rahmen hinaus und PIL.paste schnitt den Ueberstand kommentarlos ab - im Ergebnis wieder ein
    Ausschnitt statt des ganzen Bilds. rexemre 08.10.2026: eine gemeinsame Regel fuer jeden Screenshot in der
    Szene, nicht nur den ersten. Pure Funktion."""
    scale = min(max_w / img.width, max_h / img.height, 1.0)
    neu = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
    return img.resize(neu, Image.LANCZOS)


def source_plate(shot: dict, out: Path):
    """Screenshot vollstaendig und unverzerrt (fit, kein Crop/Zoom) eingepasst, darunter Quellenzeile;
    Hintergrund = unscharfe Version des Screenshots."""
    src = Image.open(shot["png"]).convert("RGB")
    bg = src.resize((W, H)).filter(ImageFilter.GaussianBlur(28))
    bg = ImageEnhance.Brightness(bg).enhance(0.35)
    box_w, box_h = 1500, 860
    s = _in_box_einpassen(src, box_w, box_h)
    x = (W - s.width) // 2
    y = 60 + (box_h - s.height) // 2
    d = ImageDraw.Draw(bg, "RGBA")
    d.rectangle([x - 6, y - 6, x + s.width + 6, y + s.height + 6], fill=(255, 255, 255, 60))
    bg.paste(s, (x, y))
    # Quellenzeile direkt unter dem tatsaechlichen Bildende (nicht der Box-Hoehe) - sonst wandert sie bei einem
    # schmaleren/kuerzeren Bild (echtes fit statt feste Hoehe, s.o.) unnoetig weit nach unten (rexemre 08.10.2026)
    leiste_y = min(y + s.height + 24, H - 170)
    d.rectangle([x, leiste_y, x + s.width, leiste_y + 72], fill=(8, 20, 45, 235))
    d.rectangle([x, leiste_y, x + 12, leiste_y + 72], fill=(200, 30, 40, 255))
    name = shot["source"].replace(" World", "").replace(" Business", "").replace(" Top News", "")
    d.text((x + 34, leiste_y + 14), f"QUELLE  {name}  ·  {shot['domain']}", font=font(36), fill="white")
    bg.save(out)


def silence(length: float, out: Path):
    run([FFMPEG, "-y", "-f", "lavfi", "-i", f"anullsrc=r={SR}:cl=stereo", "-t", f"{length:.3f}", str(out)])


def pad_wav(src: Path, pre: float, total: float, out: Path, ch: int = CH):
    """Ton mit Vorlauf auf Szenenlaenge; ch=1 nur fuer die LatentSync-Eingabe (Cache-Hash bleibt gleich)."""
    run([FFMPEG, "-y", "-i", str(src), "-af", f"aresample={SR},adelay={int(pre*1000)}:all=1,apad",
         "-ac", str(ch), "-t", f"{total:.3f}", str(out)])


TON_GLEICH_MIN = 0.98


def ton_abweichung(voice, length: float, fwork: Path, name: str) -> str | None:
    """Wurde <name>_studio.mp4 mit genau dem Ton gerendert, den die Szene heute haette? Vergleicht die beim Rendern
    geschriebenen <name>_ton*.wav mit dem heute gepolsterten Ton (wie host_scene). Vorfall 08.10.2026: eine Meldung
    wurde nach dem Lippen-Rendern neu gesprochen, die wiederverwendete Szene hatte versetzte Lippen. Ohne alte
    Tondatei (aeltere Folgen) keine Pruefung. Gibt die Abweichung als Text zurueck, sonst None."""
    import numpy as np
    teile = ([(src, L, fwork / f"{name}_ton_{j:02d}.wav") for j, (src, L) in enumerate(voice)]
             if isinstance(voice, list) else [(voice, length, fwork / f"{name}_ton.wav")])
    tmp = fwork / f"_{name}_tonvergleich.wav"
    try:
        for src, L, alt in teile:
            if not alt.exists():
                return None
            pad_wav(src, 0.25, L, tmp, ch=1)
            with wave.open(str(alt)) as a, wave.open(str(tmp)) as b:
                if a.getnframes() != b.getnframes():
                    return f"{Path(src).name}: Laenge {b.getnframes() / b.getframerate():.2f} s statt "                            f"{a.getnframes() / a.getframerate():.2f} s"
                x = np.frombuffer(a.readframes(a.getnframes()), dtype=np.int16).astype(np.float64)
                y = np.frombuffer(b.readframes(b.getnframes()), dtype=np.int16).astype(np.float64)
            k = float(x @ y / (np.linalg.norm(x) * np.linalg.norm(y) + 1e-9))
            if k < TON_GLEICH_MIN:          # gleiche Datei ~1,0; andere Aufnahme desselben Texts ~0
                return f"{Path(src).name}: anderer Ton als beim Rendern (Korrelation {k:.3f})"
    finally:
        tmp.unlink(missing_ok=True)
    return None


def extract_audio(src: Path, length: float, out: Path):
    """Ton aus einer Video-/Audiodatei als PCM 48 kHz Stereo (Musik bleibt Stereo, keine Neucodierung dazwischen)."""
    run([FFMPEG, "-y", "-i", str(src), "-vn", "-ac", str(CH), "-ar", str(SR), "-t", f"{length:.3f}", str(out)])


def _ebur128(wav: Path) -> dict:
    e = subprocess.run([FFMPEG, "-hide_banner", "-nostats", "-i", str(wav), "-af", "ebur128=peak=true", "-f", "null",
                        "-"], capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
    tail = e[e.rfind("Summary"):]
    val = lambda k: float(re.search(k + r":\s+(-?[\d.]+)", tail).group(1))
    return {"I": val("I"), "LRA": val("LRA"), "TP": val("Peak")}


def marke_angleichen(wav: Path, sprache_lufs: float, out: Path) -> float:
    """Feste Absenkung eines Marken-Tons (Bumper, Intro, Outro-Grafik) auf hoechstens Sprache + MARKE_UEBER_SPRACHE_DB.

    Folge 30.09. (Kerstin): Stimme ~-25 LUFS, Intro/Outro auf -14 LUFS gemastert = ~10 dB Sprung an jedem Uebergang,
    und der Master-Begrenzer bremste wegen der lauten Musik die Gesamtverstaerkung (-15,2 statt -14 LUFS). Nur eine
    lineare Verstaerkung pro Marken-Clip, nie angehoben (leiser Wisch/Raumton bleibt), Stimme wird nie angefasst."""
    ziel = sprache_lufs + MARKE_UEBER_SPRACHE_DB
    gain = min(0.0, ziel - _ebur128(wav)["I"])
    if gain > -0.1:
        return 0.0
    run([FFMPEG, "-y", "-i", str(wav), "-af", f"volume={gain:.2f}dB", "-c:a", "pcm_s16le", str(out)])
    return round(gain, 2)


def szene_stimme_angleichen(wav: Path, ziel_lufs: float, out: Path) -> float:
    """Gleicht die Stimm-wav einer eingefrorenen Sprechszene (Begruessung/Verabschiedung) linear auf die mittlere
    TTS-Lautheit DIESER Folge an (02.10.2026, rexemre: Folge ging mit zwei Lautstaerkespruengen an den Szenen-
    uebergaengen raus). Ursache: diese Dateien sind einmal gebaut und eingefroren (tools/weltlage_begruessung.py /
    weltlage_verabschiedung.py), ihre Tonspur stammt aus einem aelteren Stand der Mischung und weicht darum von der
    aktuellen Chatterbox-/Veredelungs-Kette ab. Anders als marke_angleichen (Toleranzband fuer Musik) gleicht diese
    Funktion Sprache GENAU an Sprache an, keine Toleranz. Nur eine lineare Verstaerkung, kein Kompressor/Limiter;
    master_ton() dahinter gaint ohnehin die ganze Mischung noch einmal gemeinsam auf MASTER_LUFS."""
    gain = ziel_lufs - _ebur128(wav)["I"]
    if abs(gain) < 0.1:
        return 0.0
    run([FFMPEG, "-y", "-i", str(wav), "-af", f"volume={gain:.2f}dB", "-c:a", "pcm_s16le", str(out)])
    return round(gain, 2)


def master_ton(wav: Path, video: Path, out: Path) -> dict:
    """Lautheit GENAU EINMAL, im Master, linear (Task 20260930-210208-ed2c, rexemre: Stimme im Video «verdrueckt»).

    Frueher: loudnorm=I=-14:TP=-2:LRA=11 in einem Durchgang = dynamischer Modus: Verstaerkung schwankte innerhalb
    einer Meldung um 3,2 dB (p5-p95), Crest -2,1 dB, Spitzen auf -4,9 dBTP gedrueckt. Jetzt: Programm messen, eine
    feste Verstaerkung auf MASTER_LUFS, danach nur ein sanfter True-Peak-Begrenzer (4x ueberabgetastet, -1,5 dBTP,
    ohne Auto-Pegel), der nur einzelne Spitzen anfasst. Kein Kompressor, keine Normalisierung pro Szene.
    Ton: AAC 256 kbps, 48 kHz, Stereo - die Telegram-Fassung kopiert ihn unveraendert (tools/telegram_fassung.py).

    True Peak an der Wurzel (Vorfall 07.10.2026, 03:00-Folge: Begrenzer auf -1,5 dBTP, nach der AAC-Codierung
    -0,9 dBTP, Abnahme durchgefallen, 10 h Neuschnitt, Slot verloren). Ursache gemessen: ffmpegs eingebauter AAC-
    Encoder ersetzt mit PNS (Perceptual Noise Substitution) und Intensity Stereo Baender durch synthetisches
    Rauschen bzw. Mono+Pegel - Werkzeuge fuer niedrige Bitraten, die an einzelnen Stellen (Cold Open mit Musikbett)
    bis +6 dB Ueberschwinger erzeugten (dieselbe Folge: -1,5 dBTP begrenzt -> +1,0 dBTP nach AAC, mit -2,0 sogar
    +3,6). Bei 256 kbps bringen sie nichts: AAC_OPT schaltet beide ab (Ueberschwinger danach ~0,1 dB, Stimme naeher
    am Original). Zur Sicherheit Begrenzer-Decke MASTER_TP - TP_CODEC_RESERVE_DB und Nachmessung: liegt der fertige
    Master trotzdem ueber MASTER_TP, Decke um den Ueberschuss + Sicherheitsabstand senken und nur den Ton neu
    codieren (Bild wird kopiert).

    Lautheit nachregeln (Vorfall 29.10.2026): bei spitzem Programmton kostet der Begrenzer >1 LU. Liegt der fertige
    Master mehr als LUFS_TOLERANZ neben MASTER_LUFS, Verstaerkung um die Abweichung erhoehen und neu codieren."""
    m = _ebur128(wav)
    gain = MASTER_LUFS - m["I"]
    decke = MASTER_TP - TP_CODEC_RESERVE_DB
    versuche, nachgeregelt = [], 0
    for _ in range(TP_MAX_VERSUCHE + LUFS_MAX_NACHREGELN):
        af = (f"volume={gain:.2f}dB,aresample={SR * 4},"
              f"alimiter=limit={10 ** (decke / 20):.4f}:attack=2:release=80:level=disabled:latency=true,"
              f"aresample={SR}")
        run([FFMPEG, "-y", "-i", str(video), "-i", str(wav), "-map", "0:v", "-map", "1:a", "-c:v", "copy",
             "-af", af, "-ar", str(SR), "-ac", str(CH), "-c:a", "aac", "-b:a", MASTER_KBPS, *AAC_OPT,
             "-shortest", "-movflags", "+faststart", str(out)])
        nachher = _ebur128(out)
        versuche.append({"decke_dbtp": round(decke, 2), "verstaerkung_db": round(gain, 2), "tp": nachher["TP"],
                         "i": nachher["I"]})
        neu = naechste_tp_decke(decke, nachher["TP"])
        if neu is not None:
            decke = neu
            continue
        neu_gain = naechste_verstaerkung(gain, nachher["I"])
        if neu_gain is None or nachgeregelt >= LUFS_MAX_NACHREGELN:
            break
        gain, nachgeregelt = neu_gain, nachgeregelt + 1
    return {"vorher": m, "verstaerkung_db": round(gain, 2), "nachher": nachher, "tp_versuche": versuche}


AAC_OPT = ["-aac_pns", "0", "-aac_is", "0"]   # keine Rausch-Ersetzung/Intensity Stereo (Ueberschwinger bis +6 dB)
TP_CODEC_RESERVE_DB = 0.3   # Rest-Ueberschwinger des AAC-Encoders ohne PNS/IS (gemessen 0,0-0,2 dB)
TP_SICHERHEIT_DB = 0.2      # zusaetzlicher Abstand, wenn nachgeregelt werden muss
TP_MAX_VERSUCHE = 3
TP_MIN_DECKE = -4.0         # nie tiefer begrenzen (sonst hoerbares Pumpen); Abnahme meldet dann den Rest
# Der Begrenzer kostet Lautheit, je spitzer der Programmton (Vorfall 29.10.2026, Masken-Folge 10:00: Chatterbox-Stimme
# -22,3 LUFS mit Spitzen -0,8 dBTP, +8,3 dB -> Spitzen bis +7,5 dBFS, nach dem Begrenzer -15,4 statt -14 LUFS).
LUFS_TOLERANZ = 0.3         # so nah muss der fertige Master an MASTER_LUFS liegen, sonst Verstaerkung nachregeln
LUFS_MAX_NACHREGELN = 3     # hoechstens so viele Nachregel-Durchgaenge (je ein AAC-Durchlauf, nur Ton)
VERSTAERKUNG_MAX_DB = 24.0  # nie mehr anheben (Schutz vor Stille/kaputtem Programmton)


def naechste_tp_decke(decke: float, gemessen_tp: float) -> float | None:
    """Neue Begrenzer-Decke (dBTP), wenn der fertig codierte Master ueber MASTER_TP liegt, sonst None (passt).
    Senkt um den Ueberschuss plus TP_SICHERHEIT_DB, nie unter TP_MIN_DECKE. Pure Funktion, offline testbar."""
    if gemessen_tp <= MASTER_TP:
        return None
    neu = max(TP_MIN_DECKE, decke - (gemessen_tp - MASTER_TP) - TP_SICHERHEIT_DB)
    return round(neu, 2) if neu < decke - 0.01 else None


def naechste_verstaerkung(gain: float, gemessen_i: float) -> float | None:
    """Neue feste Verstaerkung (dB), wenn der fertig begrenzte Master mehr als LUFS_TOLERANZ neben MASTER_LUFS liegt,
    sonst None (passt). Regelt um die volle Abweichung nach (der Begrenzer frisst davon wieder etwas, darum mehrere
    Durchgaenge), nie ueber VERSTAERKUNG_MAX_DB. Pure Funktion, offline testbar."""
    fehlt = MASTER_LUFS - gemessen_i
    if abs(fehlt) <= LUFS_TOLERANZ:
        return None
    neu = min(VERSTAERKUNG_MAX_DB, gain + fehlt)
    return round(neu, 2) if abs(neu - gain) > 0.01 else None


def master_quellen(work: Path) -> tuple[Path, Path]:
    """(Programmton, Bild) fuer master_erneuern: Latara-Rohschnitt <work>/audio_all.wav + video_all.mp4, sonst das
    Masken-Format im Geschwister-Ordner _maskenformat/ton.wav + roh.mp4 (tools/weltlage_maskenformat.py). Vorfall
    29.10.2026, 10:00-Folge: Nur-Pegel-Reparatur der Masken-Folge scheiterte an fehlendem _schnitt."""
    wav, vid = work / "audio_all.wav", work / "video_all.mp4"
    if wav.exists() and vid.exists():
        return wav, vid
    mf = work.parent / "_maskenformat"
    if (mf / "ton.wav").exists() and (mf / "roh.mp4").exists():
        return mf / "ton.wav", mf / "roh.mp4"
    return wav, vid


def master_erneuern(work: Path, out: Path) -> dict:
    """Nur den Master-Ton neu machen (Sekunden statt Stunden): aus dem ungemasterten Programmton _schnitt/
    audio_all.wav und dem Bild _schnitt/video_all.mp4 eines fertigen Rohschnitts. Fuer Abnahme-Fehler, die nur den
    Gesamtpegel betreffen (True Peak, integrierte Lautheit) - kein Neuschnitt, kein Warten auf die GPU.
    Masken-Format (kein _schnitt): Programmton _maskenformat/ton.wav + Bild _maskenformat/roh.mp4 daneben."""
    wav, vid = master_quellen(work)
    if not (wav.exists() and vid.exists()):
        raise FileNotFoundError(f"{work}: audio_all.wav/video_all.mp4 fehlen - nur ein Neuschnitt hilft")
    tmp = out.with_name(out.stem + "_neu" + out.suffix)
    res = master_ton(wav, vid, tmp)
    tmp.replace(out)
    rz = out.with_name(out.stem + "_renderzeiten.json")
    try:
        zeiten = json.loads(rz.read_text(encoding="utf-8")) if rz.exists() else {}
        zeiten["ton_master"] = res
        zeiten["ton_master_erneuert"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        rz.write_text(json.dumps(zeiten, indent=2), encoding="utf-8")
    except (OSError, ValueError):
        pass
    return res


def xfade_join(v1: Path, v2: Path, len1: float, xd: float, out: Path):
    """Ueberblendet zwei Clips (statt hartem Schnitt); offset = Beginn der Ueberblendung im ersten Clip."""
    run([FFMPEG, "-y", "-i", str(v1), "-i", str(v2), "-filter_complex",
         f"[0:v][1:v]xfade=transition=fade:duration={xd:.3f}:offset={len1 - xd:.3f},format=yuv420p[v]",
         "-map", "[v]", *VENC, str(out)])


def acrossfade_join(a1: Path, a2: Path, xd: float, out: Path):
    """Ton-Pendant zu xfade_join: kein harter Sprung von Stille auf volle Lautstaerke (Klick)."""
    run([FFMPEG, "-y", "-i", str(a1), "-i", str(a2), "-filter_complex",
         f"acrossfade=d={xd:.3f}:c1=tri:c2=tri", str(out)])


def _arg(name):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else None


def _musik_fuer_laenge(musik_datei: Path, L1: float, work: Path) -> Path:
    """Verlaengert das Musikbett per Crossfade-Loop, falls die Cold-Open-Szene laenger ist als die Rohdatei
    (rexemre 01.10.2026: Musik muss bei jeder Cold-Open-Laenge passen, Loop ohne hoerbaren Schnitt). Haengt die
    Rohdatei so oft mit kurzer Ueberblendung an sich selbst, bis sie mindestens L1 Sekunden lang ist; acrossfade_join
    ist derselbe Weichuebergang, der auch zwei Szenen aneinanderhaengt, also kein harter Klick am Loop-Punkt."""
    roh = dur(musik_datei)
    if roh >= L1:
        return musik_datei
    xd = min(2.0, roh / 4)
    aktuelle, aktuelle_dauer, i = musik_datei, roh, 0
    while aktuelle_dauer < L1:
        ziel = work / f"_musikbett_loop_{i}.wav"
        acrossfade_join(aktuelle, musik_datei, xd, ziel)
        aktuelle, aktuelle_dauer, i = ziel, aktuelle_dauer + roh - xd, i + 1
    return aktuelle


def apply_coldopen_musikbett(a1: Path, L1: float, work: Path):
    """Mischt das Musikbett (config/brand/coldopen_musik/aktiv.json) unter die Cold-Open-Stimme a1, ersetzt a1 in
    place. Nur aufgerufen, wenn NEWS_WELTLAGE_COLDOPEN_MUSIKBETT aktiv ist (config/settings.py, Standard seit
    rexemres Entscheid 01.10.2026 16:27, Variante 3). Pegel relativ zur gerade gemessenen Sprachlautheit von a1
    (-19 dB unter der Stimme, Fade-in 1s, Fade-out 1,5s endet exakt beim Schnitt in den Bumper); sanftes
    Sidechain-Ducking zusaetzlich, damit die Musik bei Sprache weiter runtergeht und in Pausen leicht hochkommt.
    Ist die Szene laenger als die Rohdatei, wird vorher per Crossfade-Loop verlaengert (_musik_fuer_laenge). Kein
    erneutes Normalisieren auf MASTER_LUFS noetig: master_ton() hinterher gaint Stimme und Musik gleich, der
    Pegelabstand bleibt erhalten."""
    from config.settings import (NEWS_WELTLAGE_COLDOPEN_MUSIKBETT_DB, NEWS_WELTLAGE_COLDOPEN_MUSIKBETT_FADE_IN,
                                  NEWS_WELTLAGE_COLDOPEN_MUSIKBETT_FADE_OUT)
    cfg_path = BRAND / "coldopen_musik" / "aktiv.json"
    if not cfg_path.exists():
        return
    musik_datei = BRAND / "coldopen_musik" / json.loads(cfg_path.read_text(encoding="utf-8"))["landscape"]
    if not musik_datei.exists():
        return
    musik_datei = _musik_fuer_laenge(musik_datei, L1, work)
    voice_i = _ebur128(a1)["I"]
    fade_out_start = L1 - NEWS_WELTLAGE_COLDOPEN_MUSIKBETT_FADE_OUT
    getrimmt = work / "_musikbett_getrimmt.wav"
    run([FFMPEG, "-y", "-i", str(musik_datei), "-t", f"{L1:.6f}", "-af",
         f"afade=t=in:st=0:d={NEWS_WELTLAGE_COLDOPEN_MUSIKBETT_FADE_IN:.3f},"
         f"afade=t=out:st={fade_out_start:.3f}:d={NEWS_WELTLAGE_COLDOPEN_MUSIKBETT_FADE_OUT:.3f}",
         str(getrimmt)])
    musik_i = _ebur128(getrimmt)["I"]
    gain = (voice_i + NEWS_WELTLAGE_COLDOPEN_MUSIKBETT_DB) - musik_i
    geleveled = work / "_musikbett_leveled.wav"
    run([FFMPEG, "-y", "-i", str(getrimmt), "-af", f"volume={gain:.2f}dB", str(geleveled)])
    geduckt = work / "_musikbett_geduckt.wav"
    run([FFMPEG, "-y", "-i", str(geleveled), "-i", str(a1), "-filter_complex",
         "[0:a][1:a]sidechaincompress=threshold=0.09:ratio=6:attack=15:release=350:makeup=1[duck]",
         "-map", "[duck]", str(geduckt)])
    gemischt = work / "_musikbett_mix.wav"
    run([FFMPEG, "-y", "-i", str(a1), "-i", str(geduckt), "-filter_complex",
         "[0:a][1:a]amix=inputs=2:duration=first:normalize=0[mix]", "-map", "[mix]", str(gemischt)])
    gemischt.replace(a1)


def bild_segmente(shots: list[dict], L: float) -> list[tuple]:
    """Raster einer Meldung mit Schnittbildern: Host HOST_LEAD, dann Bild/Host abwechselnd, Rest Host - reine
    Platzierungslogik, unabhaengig vom eigentlichen Rendern. Einmal berechnet, zweimal verwendet (rexemre
    19.10.2026, Ergaenzung zu Task 20261019-182613-44c1): vor dem Lipsync fuer die Vollbild-Spannen der
    Quellen-Screenshot-Karten (source_plate() deckt den Freisteller vollstaendig und hart ab, kein Ueberblenden -
    anders als ein B-Roll-Vollbild-Clip braucht die Spanne hier keine FADE-Verkuerzung am Rand), danach beim
    eigentlichen Zusammensetzen. Pure Funktion."""
    segs, pos, k = [], 0.0, 0
    segs.append(("host", min(HOST_LEAD, L))); pos += segs[-1][1]
    while shots and pos + CUT_LEN + 1.5 <= L:
        shot = shots[k % len(shots)]
        segs.append(("bild", CUT_LEN, shot))
        pos += CUT_LEN; k += 1
        back = min(HOST_BACK, L - pos)
        if L - pos - back < CUT_LEN + 1.5:
            back = L - pos
        segs.append(("host", back)); pos += back
    if pos < L - 0.01:
        segs.append(("host", L - pos))
    return segs


def bild_spannen(segs: list[tuple]) -> list[tuple[float, float]]:
    """(start, ende)-Zeitspannen aller "bild"-Segmente (Quellen-Screenshot-Karte, deckt den Freisteller
    vollstaendig ab) in `segs`, lokale Sekunden ab Meldungsbeginn - wie weltlage_broll.voll_spannen() fuer
    B-Roll-Vollbild-Clips. Pure Funktion."""
    out, pos = [], 0.0
    for sg in segs:
        if sg[0] == "bild":
            out.append((pos, pos + sg[1]))
        pos += sg[1]
    return out


def main():
    t_all = time.time()
    # absolute Pfade: LatentSync laeuft mit cwd=vendor/LatentSync, relative Ordner fuehrten dort ins Leere (30.09.2026)
    test = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else ROOT / "data" / "weltlage_test_20260929"
    lip = Path(_arg("--lip")) if _arg("--lip") else None
    kurztest = "--kurztest" in sys.argv
    work = Path(_arg("--work")).resolve() if _arg("--work") else test / "_schnitt"
    work.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT))
    from video import freisteller_lipsync as fl
    freisteller = not lip and "--ohne-lipsync" not in sys.argv and fl.available()
    if freisteller and not fl.haar_ok():           # Basis-Python (OpenCV 5): im Lipsync-Python neu starten
        sys.exit(subprocess.call([str(fl.LS_PY), str(Path(__file__).resolve()), *sys.argv[1:]]))
    fwork = work / "_freisteller"
    zeiten = {}
    # rexemre 01.10.2026 (Zeitdruck Deadline): einzelne, schon fertig gerechnete Szenen ueberspringen und ihr
    # vorhandenes <name>_studio.mp4 wiederverwenden, statt sie mit neuen Lipsync-Einstellungen neu zu rechnen.
    skip_szenen = {s.strip() for s in os.environ.get("NEWS_WELTLAGE_SKIP_SZENEN", "").split(",") if s.strip()}

    def host_scene(pose, voice, start, length, name, ort=None, skip_spans=None):
        """Sprechszene nach der Freisteller-Regel; Ton wie add() ihn polstert (0,25 s Vorlauf, auf Szenenlaenge).
        ort: optional anderer Hintergrund (texte.json Feld "ort", config/brand/orte); None = bisheriges Studio.
        skip_spans: Vollbild-Zeitspannen dieser Szene (weltlage_broll.voll_spannen()) - dort laesst der Lipsync
        den teuren Mundabgleich aus, siehe video/freisteller_lipsync.lipsync_freisteller()."""
        fwork.mkdir(exist_ok=True)
        fertig = fwork / f"{name}_studio.mp4"
        if name in skip_szenen and fertig.exists():
            abweichung = ton_abweichung(voice, length, fwork, name)
            if abweichung:
                raise SystemExit(f"{name}: fertiges Lippen-Video passt nicht mehr zum Ton ({abweichung}) - Ton "
                                 "wiederherstellen oder die Szene ohne NEWS_WELTLAGE_SKIP_SZENEN neu rendern")
            zeiten[name] = 0.0
            print(f"{name}: wiederverwendet (schon fertig) -> {fertig}", flush=True)
            return fertig
        wav = fwork / f"{name}_ton.wav"
        if isinstance(voice, list):                  # Meldungen: alle am Stueck, jede wie in add() gepolstert
            padded = []
            for j, (src, L) in enumerate(voice):
                pw = fwork / f"{name}_ton_{j:02d}.wav"
                pad_wav(src, 0.25, L, pw, ch=1)
                padded.append(pw)
            lst = fwork / f"{name}_ton.txt"
            lst.write_text("".join(f"file '{q.as_posix()}'\n" for q in padded), encoding="utf-8")
            run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(wav)])
        else:
            pad_wav(voice, 0.25, length, wav, ch=1)
        t = time.time()
        comp = fl.render_scene(pose, wav, start, length, fwork, name, log=lambda m: print(m, flush=True), ort=ort,
                               skip_spans=skip_spans)
        zeiten[name] = round(time.time() - t, 1)
        return comp
    _texte_roh = json.loads((test / "texte.json").read_text(encoding="utf-8"))
    if not kurztest and "--ohne-intro-bau" not in sys.argv:
        # Unreal-Standard-Intro dieser Folge (Tageskurse + Datum) VOR dem Lipsync bauen: der Bau reiht sich selbst
        # in die GPU-Warteschlange ein und darf keinen Slot von uns halten. Scheitert er, bleibt die letzte gute
        # Fassung (laut geloggt, Abnahme warnt) - die Folge wird nie blockiert.
        import weltlage_intro
        _im = weltlage_intro.vorbereiten(_texte_roh.get("datum") or time.strftime("%Y-%m-%d"),
                                         log=lambda m: print(m, flush=True))
        zeiten["intro_bau_ok"] = bool(_im.get("ok"))
        # Nachweis, WELCHES Intro in dieser Folge steckt (Abnahme: Datum/Laenge; fehlt er = Folge von vor der
        # Umstellung 20.10.2026 mit altem Globus-Intro, nur Warnung statt Laengenfehler).
        (test / "intro_verwendet.json").write_text(json.dumps({"datei": INTRO.name, "laenge": round(dur(INTRO), 2),
                                                               "meta": weltlage_intro.meta_lesen()},
                                                              indent=2, ensure_ascii=False), encoding="utf-8")
    texte = _texte_roh["szenen"]
    # Orte pro Szene (optional, texte.json Feld "ort", z.B. "bruessel"; fehlt es oder ist es "studio", bleibt alles
    # wie bisher). Unbekannte Orte brechen hier ab statt mitten im Render.
    from video import orte as orte_mod
    ort_von = {t["id"]: (None if orte_mod.ist_standard(t.get("ort")) else t["ort"]) for t in texte}
    bilder = json.loads((test / "bilder.json").read_text(encoding="utf-8"))
    wanted = json.loads((test / "bildwahl.json").read_text(encoding="utf-8")) if (test / "bildwahl.json").exists() else {}
    aud = {t["id"]: test / "audio" / f"{t['id']}.wav" for t in texte}
    # Stimmen-Pruefung (rexemre 30.09.2026): jede gesprochene Datei muss nachweislich der Chatterbox-Klon Ramona
    # sein (24 kHz mono + Engine-Nachweis mit Hash; tools/weltlage_tts.py erzeugt beides). Piper ist abgewaehlt.
    from weltlage_tts import pruefe_stimme
    if not kurztest and "s_coldopen" not in aud:
        raise SystemExit("texte.json hat keinen Cold Open (s_coldopen) - zuerst tools/weltlage_update_themen.py")
    gesprochen = ([] if kurztest else ["s_coldopen"]) + ["s_themen"] + [t["id"] for t in texte if t["szene"] == 5] + \
        ([] if kurztest else ["s6_outro"])
    stimm_fehler = [f for f in (pruefe_stimme(aud[i]) for i in gesprochen) if f]
    if BEGRUESSUNG:                       # eingefrorene Begruessung: ihre Stimm-Datei muss denselben Nachweis haben
        f = pruefe_stimme(BEGRUESSUNG_STIMME) if BEGRUESSUNG_STIMME else "keine stimme_wav in begruessung/aktiv.json"
        if f:
            stimm_fehler.append(f"Begruessung {BEGRUESSUNG.name}: {f} (tools/weltlage_begruessung.py build + freeze)")
    if VERABSCHIEDUNG:                    # eingefrorene Verabschiedung: dito
        f = pruefe_stimme(VERABSCHIEDUNG_STIMME) if VERABSCHIEDUNG_STIMME else "keine stimme_wav in verabschiedung/aktiv.json"
        if f:
            stimm_fehler.append(f"Verabschiedung {VERABSCHIEDUNG.name}: {f} (tools/weltlage_verabschiedung.py build + freeze)")
    if ABSCHLUSS:                         # eingefrorener Abschluss: dito
        f = pruefe_stimme(ABSCHLUSS_STIMME) if ABSCHLUSS_STIMME else "keine stimme_wav in abschluss/aktiv.json"
        if f:
            stimm_fehler.append(f"Abschluss {ABSCHLUSS.name}: {f} (tools/weltlage_abschluss.py build + freeze)")
    if stimm_fehler:
        raise SystemExit("Nicht Lataras Chatterbox-Stimme - zuerst tools/weltlage_tts.py laufen lassen:\n  " +
                         "\n  ".join(stimm_fehler))
    # Referenz-Lautheit DIESER Folge aus den frisch vertonten Sprechszenen (Themen + Meldungen + ggf. Cold Open/
    # Outro) - dagegen werden die eingefrorenen Begruessungs-/Verabschiedungs-Dateien unten angeglichen
    # (szene_stimme_angleichen), damit an ihren Uebergaengen kein Lautstaerkesprung entsteht.
    ziel_sprache_lufs = statistics.median(_ebur128(aud[i])["I"] for i in gesprochen)
    parts = []          # (video_mp4, audio_wav, dauer, label)
    stimm_szenen = {}   # label -> (nachgewiesene Stimm-Datei, Vorlauf im Teil, Pruefdauer) fuer die Endpruefung
    n = 0

    def add(video, audio_src, length, label, pre=0.25):
        nonlocal n
        n += 1
        a = work / f"a{n:02d}.wav"
        if audio_src is None:
            silence(length, a)
        elif isinstance(audio_src, tuple):          # ("extract", datei): Ton aus einer Videodatei
            extract_audio(audio_src[1], length, a)
        else:
            pad_wav(audio_src, pre, length, a)
        parts.append((video, a, length, label))

    # Struktur vom 30.09.2026 (rexemre, docs/weltlage_szenenplan.md): Bumper - Intro - Reinlaufen (unveraendert) -
    # Begruessung (neu, fest eingefroren) - Logo-Wisch (neu, fest eingefroren) - Themen (neu, pro Folge) -
    # Meldungen - Verabschiedung - Outro.
    # --kurztest baut nur Reinlaufen + Begruessung + Logo-Wisch + Themen + Anfang der Sitz-Szene (ohne
    # Bumper/Intro/Verabschiedung/Outro).
    if not kurztest:
        # Cold Open (erste Szene, rexemre 30.09.2026): Latara stehend reisst die Top-Meldungen an, pro Folge neu.
        # Ausschnitt ab einem spaeten v6-Ruhepunkt, damit sich die Bewegung nicht mit der Begruessung (ab Frame 0)
        # wiederholt; danach kurze Bild-/Ton-Ueberblendung in den Bumper (kein Klick, wie am 29.09. geloest).
        s_co = aud["s_coldopen"]
        L1 = min(dur(s_co) + 0.25 + 0.6, dur(V6))
        start1 = max([r for r in V6_RUHEPUNKTE if r + L1 <= dur(V6) - 0.1] or [0.0])
        v1 = work / "s_coldopen.mp4"
        if freisteller:
            clip(host_scene("stehend", s_co, start1, L1, "coldopen", ort=ort_von.get("s_coldopen")), 0, L1, v1)
        else:
            clip(V6, start1, L1, v1)
        a1 = work / "s_coldopen_ton.wav"
        pad_wav(s_co, 0.25, L1, a1)
        from config.settings import NEWS_WELTLAGE_COLDOPEN_MUSIKBETT
        if NEWS_WELTLAGE_COLDOPEN_MUSIKBETT:
            apply_coldopen_musikbett(a1, L1, work)
        # Welt-Bumper (config/brand/bumper/aktiv.json), eigener Ton, keine Stimme
        if BUMPER and BUMPER.exists():
            Lb = round(dur(BUMPER) * FPS) / FPS          # bildgenau, sonst läuft der Ton gegen das Bild weg
            v2 = work / "s_bumper.mp4"
            run([FFMPEG, "-y", "-i", str(BUMPER), "-an", "-vf", scale_crop(), *VENC, str(v2)])
            a2 = work / "s_bumper_ton.wav"
            extract_audio(BUMPER, Lb, a2)
            a2p = work / "s_bumper_ton_pegel.wav"         # Bumper-Musik auf Hoehe der Cold-Open-Stimme
            zeiten["pegel_bumper_db"] = marke_angleichen(a2, _ebur128(a1)["I"], a2p)
            if zeiten["pegel_bumper_db"]:
                a2 = a2p
            XD = min(0.3, L1 - 0.1, Lb - 0.1)
            v = work / "s_coldopen_bumper.mp4"
            xfade_join(v1, v2, L1, XD, v)
            a = work / "s_coldopen_bumper.wav"
            acrossfade_join(a1, a2, XD, a)
            add(v, ("extract", a), L1 + Lb - XD, "Szene Cold Open + Welt-Bumper")
            stimm_szenen["Szene Cold Open + Welt-Bumper"] = (s_co, 0.25, L1 - XD)
        else:
            add(v1, ("extract", a1), L1, "Szene Cold Open")
            stimm_szenen["Szene Cold Open"] = (s_co, 0.25, L1)
        # Intro
        L2 = dur(INTRO)
        v = work / "s_intro.mp4"
        run([FFMPEG, "-y", "-i", str(INTRO), "-an", "-vf", scale_crop(), *VENC, str(v)])
        add(v, ("extract", INTRO), L2, "Szene Intro")
    # Reinlaufen/Auftritt: fester, eingefrorener Clip (kein Text, kein Sprechton, nur leiser Raumton); ohne Clip Platzhalter
    if SZENE3 and SZENE3.exists():
        L3 = round(dur(SZENE3) * FPS) / FPS
        v = work / "s3.mp4"
        run([FFMPEG, "-y", "-i", str(SZENE3), "-an", "-vf", scale_crop(), *VENC, str(v)])
        add(v, ("extract", SZENE3), L3, "Szene Reinlaufen")
    else:
        s3 = aud["s3_auftritt"]
        L3 = dur(s3) + 0.25 + 0.7
        f0 = work / "v6_frame0.png"; frame_at(V6, 0, f0)
        p3 = work / "s3_plate.png"
        placeholder_plate(f0, "Szene: Latara läuft ins Bild", "Endet auf dem ersten Frame der stehenden Pose · niedrige Priorität", p3)
        v = work / "s3.mp4"; still_clip(p3, L3, v, zoom=False); add(v, s3, L3, "Szene Reinlaufen Platzhalter")
    # Begruessung: fest eingefrorene Vorlage (Latara begruesst das Publikum allgemein), startet bei V6-Position 0 -
    # schliesst nahtlos an das Ende von Reinlaufen an (letzter Frame Reinlaufen = V6 Frame 0 = erster Frame Begruessung).
    # In jeder Folge identisch, nie neu gerendert (tools/weltlage_begruessung.py).
    if BEGRUESSUNG and BEGRUESSUNG.exists():
        Lbg = round(dur(BEGRUESSUNG) * FPS) / FPS
        v = work / "s_begr.mp4"
        run([FFMPEG, "-y", "-i", str(BEGRUESSUNG), "-an", "-vf", scale_crop(), *VENC, str(v)])
        # Ton direkt aus der nachgewiesenen Stimm-wav statt aus dem AAC des Clips (keine doppelte Neucodierung,
        # Task 20260930-182721-1dc4); gleicher Vorlauf wie beim Lipsync des Clips
        vorlauf = _begr_meta.get("stimme_vorlauf_s", 0.25)
        if BEGRUESSUNG_STIMME and BEGRUESSUNG_STIMME.exists():
            begr_angeglichen = work / "s_begr_stimme_angeglichen.wav"
            zeiten["pegel_begruessung_db"] = szene_stimme_angleichen(BEGRUESSUNG_STIMME, ziel_sprache_lufs,
                                                                     begr_angeglichen)
            quelle = begr_angeglichen if zeiten["pegel_begruessung_db"] else BEGRUESSUNG_STIMME
            add(v, quelle, Lbg, "Szene Begrüssung", pre=vorlauf)
        else:
            add(v, ("extract", BEGRUESSUNG), Lbg, "Szene Begrüssung")
        stimm_szenen["Szene Begrüssung"] = (BEGRUESSUNG_STIMME, _begr_meta.get("stimme_vorlauf_s", 0.25), Lbg)
    else:
        Lbg = 0.0
    # Logo-Wisch (Variante A, rexemre 30.09.2026): kurzer Marken-Uebergang statt hartem Schnitt
    # (config/brand/uebergang/aktiv.json, tools/weltlage_uebergang.py). Seit 04.10.2026 zweimal eingesetzt:
    # Begruessung->Themen (wie bisher) und Themen->Meldungen (rexemre: harter Schnitt beim Steh-Sitz-Wechsel).
    def logo_wisch(suffix):
        if not (UEBERGANG and UEBERGANG.exists()):
            return
        Lu = round(dur(UEBERGANG) * FPS) / FPS
        v = work / f"s_uebergang_{suffix}.mp4"
        run([FFMPEG, "-y", "-i", str(UEBERGANG), "-an", "-vf", scale_crop(), *VENC, str(v)])
        add(v, ("extract", UEBERGANG), Lu, "Logo-Wisch")
    logo_wisch("begr")
    # Themen: stehend am Pult, pro Folge neu - Latara nennt die heutigen Themen als kurze Aufzaehlung (Text
    # automatisch aus den Meldungs-Schlagzeilen gebaut, tools/weltlage_update_themen.py). Startet an einem
    # spaeten v6-Ruhepunkt, damit sich die Bewegung nicht mit der Begruessung wiederholt.
    s_th = aud["s_themen"]
    L_th = dur(s_th) + 0.25 + 0.6
    if BEGRUESSUNG_ENDE is not None and BEGRUESSUNG_ENDE + L_th <= dur(V6) - 0.1:
        start_th = BEGRUESSUNG_ENDE          # bildgenauer Anschluss an die Begruessung, siehe BEGRUESSUNG_ENDE oben
    else:
        start_th = max(0.0, dur(V6) - L_th - 0.1)
        if SZENE3 and SZENE3.exists():
            start_th = max([r for r in V6_RUHEPUNKTE if r <= start_th] or [0.0])
    v = work / "s_themen.mp4"
    if freisteller:
        clip(host_scene("stehend", s_th, start_th, L_th, "themen", ort=ort_von.get("s_themen")), 0, L_th, v)
    else:
        clip(V6, start_th, L_th, v)
    add(v, s_th, L_th, "Szene Themen")
    stimm_szenen["Szene Themen"] = (s_th, 0.25, L_th)
    logo_wisch("sitz")
    # Meldungen sitzend + Schnittbilder; Sitz-Spur läuft durchgehend weiter (Rückschnitte zeigen fortlaufende Bewegung)
    meldungen = [t for t in texte if t["szene"] == 5]
    if kurztest:
        meldungen = meldungen[:1]          # Testclip: nur der Anfang der Sitz-Szene (eine Meldung)
    sitz = lip or SITZ
    # Meldungen mit eigenem Ort (texte.json "ort"): Latara stehend vor diesem Hintergrund statt am Sitz-Pult. Der
    # stehende Freisteller ist ~29 s lang und loopt nicht -> laengere Meldungen bleiben im Studio (Warnung).
    vor_ort = {}
    if freisteller:
        for t in meldungen:
            o = ort_von.get(t["id"])
            if o:
                L = dur(aud[t["id"]]) + 0.25 + GAP
                if L <= dur(V6) - 0.2:
                    vor_ort[t["id"]] = o
                else:
                    print(f"WARNUNG: Meldung {t['id']} ({L:.1f} s) zu lang fuer Ort {o!r}, bleibt im Studio", flush=True)
    # B-Roll-Planung lesen (rexemre 19.10.2026, Task 20261019-182613-44c1): tools/weltlage_tageslauf.py ruft Stufe 1
    # von weltlage_broll.py (Einsatzstellen, Darstellungsart, Clips) seither schon VOR diesem Schritt auf, damit hier
    # bekannt ist, welche Zeitspannen nachher vollflaechig ueberdeckt werden (Variante "voll") - dort braucht der
    # Lipsync unten keinen Mundabgleich. Fehlt der Plan (B-Roll aus, Planung noch nicht fertig/fehlgeschlagen), bleibt
    # voll_je_meldung leer und der Lipsync rechnet wie bisher ueberall normal; nie ein Abbruchgrund fuer das Grundvideo.
    voll_je_meldung = {}
    if freisteller:
        try:
            import weltlage_broll
            voll_je_meldung = weltlage_broll.voll_spannen(test)
            if voll_je_meldung:
                n_spannen = sum(len(v) for v in voll_je_meldung.values())
                print(f"B-Roll-Plan vorab gefunden: {n_spannen} Vollbild-Spanne(n) in {len(voll_je_meldung)} "
                      "Meldung(en) - Lipsync laesst sie aus", flush=True)
        except Exception as e:                            # noqa: BLE001
            print(f"WARNUNG: B-Roll-Plan nicht lesbar, Lipsync rechnet ueberall normal: {e}", flush=True)
    # Schnittbild-Raster je Meldung vorab bestimmen (rexemre 19.10.2026, Ergaenzung zu Task 20261019-182613-44c1):
    # dieselbe Platzierung wie bisher, nur jetzt VOR der Sitz-Spur berechnet, damit auch die Quellen-Screenshot-
    # Spannen (Vollbild, deckt den Freisteller komplett ab) in den Lipsync-Spannen-Ueberspringer einfliessen - nicht
    # nur die B-Roll-"voll"-Spannen aus weltlage_broll.py.
    segs_je_meldung = {}
    for t in meldungen:
        L_t = dur(aud[t["id"]]) + 0.25 + GAP
        shots_t = [s for s in bilder.get(str(t["bild"]), [])
                   if not wanted.get(str(t["bild"])) or Path(s["png"]).name in wanted[str(t["bild"])]]
        segs_je_meldung[t["id"]] = bild_segmente(shots_t, L_t)
    if freisteller:                                  # eine durchgehende Sitz-Spur ueber die Meldungen (+0,2 s Reserve)
        s5 = [(aud[t["id"]], dur(aud[t["id"]]) + 0.25 + GAP) for t in meldungen if t["id"] not in vor_ort]
        if s5:
            skip, acc = [], 0.0
            for t in meldungen:
                if t["id"] in vor_ort:
                    continue
                L = dur(aud[t["id"]]) + 0.25 + GAP
                for a0, b0 in voll_je_meldung.get(t["id"], []) + bild_spannen(segs_je_meldung[t["id"]]):
                    skip.append((acc + a0, acc + b0))
                acc += L
            sitz = host_scene("sitz", s5, 0.0, sum(L for _, L in s5) + 0.2, "s5", skip_spans=skip)
    sitz_t = 0.0
    sitz_len = dur(sitz)
    bild_platzierungen_roh = []       # fuer bilder_platzierung.json (video/einblendungen.py, Abnahme 7.)
    for t in meldungen:
        a = aud[t["id"]]
        L = dur(a) + 0.25 + GAP
        dw = dur(a)
        ort_clip, ort_t = None, 0.0
        if t["id"] in vor_ort:                       # Sprechszene vor Ort, eigene Spur (Lipsync auf dem Freisteller)
            start_o = max([r for r in V6_RUHEPUNKTE if r + L <= dur(V6) - 0.1] or [0.0])
            ort_clip = host_scene("stehend", a, start_o, L, f"s5_{t['id']}_{vor_ort[t['id']]}", ort=vor_ort[t["id"]],
                                  skip_spans=voll_je_meldung.get(t["id"], []) + bild_spannen(segs_je_meldung[t["id"]]))
        segs = segs_je_meldung[t["id"]]
        pos = 0.0
        for sg in segs:
            if sg[0] == "bild":
                bild_platzierungen_roh.append({"meldung": t["id"], "shot": sg[2], "start_in_meldung": pos,
                                               "dauer": sg[1], "text": t["text"], "narration_dauer": dw})
            pos += sg[1]
        seg_files = []
        for j, sg in enumerate(segs):
            out = work / f"s5_{t['id']}_{j}.mp4"
            if sg[0] == "host" and ort_clip is not None:
                clip(ort_clip, ort_t, sg[1], out)
            elif sg[0] == "host":
                clip(sitz, sitz_t % sitz_len, sg[1], out, loop=True)
            else:
                plate = work / f"plate_{Path(sg[2]['png']).stem}.png"
                source_plate(sg[2], plate)
                still_clip(plate, sg[1], out)
            if ort_clip is not None:
                ort_t += sg[1]
            else:
                sitz_t += sg[1]
            seg_files.append(out)
        v = work / f"s5_{t['id']}.mp4"
        lst = work / f"s5_{t['id']}.txt"
        lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in seg_files), encoding="utf-8")
        run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(v)])
        add(v, a, L, f"Szene Meldung {t['id']}")
        stimm_szenen[f"Szene Meldung {t['id']}"] = (a, 0.25, L)
    if not kurztest:
        # Verabschiedung: wie die Begruessung fest eingefroren, sobald config/brand/verabschiedung/aktiv.json
        # existiert (tools/weltlage_verabschiedung.py) - der Text ist in jeder Folge wortgleich, darum einmal
        # gebaut und seither nur noch eingebunden statt jede Folge neu zu vertonen und zu lipsyncen. Ein eigener
        # Ort fuer s6_outro (texte.json "ort") faellt auf den alten Pro-Folge-Weg zurueck, dito ohne eingefrorene
        # Fassung.
        if VERABSCHIEDUNG and VERABSCHIEDUNG.exists() and not ort_von.get("s6_outro"):
            L6 = round(dur(VERABSCHIEDUNG) * FPS) / FPS
            v = work / "s6.mp4"
            run([FFMPEG, "-y", "-i", str(VERABSCHIEDUNG), "-an", "-vf", scale_crop(), *VENC, str(v)])
            vorlauf = _verab_meta.get("stimme_vorlauf_s", 0.25)
            if VERABSCHIEDUNG_STIMME and VERABSCHIEDUNG_STIMME.exists():
                verab_angeglichen = work / "s6_stimme_angeglichen.wav"
                zeiten["pegel_verabschiedung_db"] = szene_stimme_angleichen(VERABSCHIEDUNG_STIMME, ziel_sprache_lufs,
                                                                            verab_angeglichen)
                quelle = verab_angeglichen if zeiten["pegel_verabschiedung_db"] else VERABSCHIEDUNG_STIMME
                add(v, quelle, L6, "Szene Verabschiedung", pre=vorlauf)
            else:
                add(v, ("extract", VERABSCHIEDUNG), L6, "Szene Verabschiedung")
            stimm_szenen["Szene Verabschiedung"] = (VERABSCHIEDUNG_STIMME, vorlauf, L6)
        else:
            # Alter Pro-Folge-Weg: gleicher stehender Freisteller wie Reinlaufen/Begruessung/Themen (rexemre
            # 29.09.), Ausschnitt aus der Taktmitte, damit sich die Bewegung nicht mit Begruessung/Themen wiederholt
            s6 = aud["s6_outro"]
            L6 = dur(s6) + 0.25 + (0.6 if (ABSCHLUSS and ABSCHLUSS.exists()) else 1.8)
            start6 = max(0.0, (dur(V6) - L6) / 2)
            v = work / "s6.mp4"
            if freisteller:
                clip(host_scene("stehend", s6, start6, L6, "s6", ort=ort_von.get("s6_outro")), 0, L6, v)
            else:
                clip(V6, start6, L6, v)
            add(v, s6, L6, "Szene Verabschiedung")
            stimm_szenen["Szene Verabschiedung"] = (s6, 0.25, L6)
        # Abschluss: wie Begruessung/Verabschiedung fest eingefroren (config/brand/abschluss/aktiv.json,
        # tools/weltlage_abschluss.py) - kurzer, zeitloser Kanal-Abschluss mit Latara, WK-Logo und dem
        # animierten Abo-Hinweis (ABO_ICON), ersetzt die alte reine Musik-/Logo-Outro-Grafik (rexemre 04.10.2026:
        # "ein klarer, eigener Abschluss mit Latara und einem deutlichen Abo-Hinweis, keine leeren Felder").
        if ABSCHLUSS and ABSCHLUSS.exists():
            La = round(dur(ABSCHLUSS) * FPS) / FPS
            v_roh = work / "s7_ohne_abo.mp4"
            run([FFMPEG, "-y", "-i", str(ABSCHLUSS), "-an", "-vf", scale_crop(), *VENC, str(v_roh)])
            v = work / "s7.mp4"
            abo_overlay(v_roh, _abschl_meta.get("abo_at", 0.6) + 0.25, v)
            vorlauf = _abschl_meta.get("stimme_vorlauf_s", 0.25)
            if ABSCHLUSS_STIMME and ABSCHLUSS_STIMME.exists():
                abschl_angeglichen = work / "s7_stimme_angeglichen.wav"
                zeiten["pegel_abschluss_db"] = szene_stimme_angleichen(ABSCHLUSS_STIMME, ziel_sprache_lufs,
                                                                        abschl_angeglichen)
                quelle = abschl_angeglichen if zeiten["pegel_abschluss_db"] else ABSCHLUSS_STIMME
                add(v, quelle, La, "Szene Abschluss", pre=vorlauf)
            else:
                add(v, ("extract", ABSCHLUSS), La, "Szene Abschluss")
            stimm_szenen["Szene Abschluss"] = (ABSCHLUSS_STIMME, vorlauf, La)

    # Zusammenfügen
    parts = align_parts(parts, FPS, SR, work)
    # Marken-Musik (Intro) auf Hoehe der Stimme, damit es an den Uebergaengen nicht springt
    sprache = sorted(_ebur128(p[1])["I"] for p in parts if p[3].startswith("Szene Meldung"))
    if sprache:
        ref = sprache[len(sprache) // 2]
        zeiten["pegel_sprache_lufs"] = ref
        for i, p in enumerate(parts):
            if p[3] == "Szene Intro":
                ap_ = p[1].with_name(p[1].stem + "_pegel.wav")
                g = marke_angleichen(p[1], ref, ap_)
                zeiten[f"pegel_{p[3]}_db"] = g
                if g:
                    parts[i] = (p[0], ap_, *p[2:])
            elif p[3] == "Logo-Wisch":
                # Anders als Intro/Outro (Musik, nie anheben) ist der Logo-Wisch nur 1 s lang und sein eigener
                # Ton (Wisch-Geraeusch) lag bisher unbehandelt oft 5-8 dB unter der Sprache (Abnahme 03.10.2026:
                # zwei Lautstaerkespruenge Begruessung->Logo-Wisch->Themen). Darum wie eine eingefrorene
                # Sprechszene (szene_stimme_angleichen) GENAU auf die Sprache dieser Folge angleichen, auch
                # nach oben.
                ap_ = p[1].with_name(p[1].stem + "_pegel.wav")
                g = szene_stimme_angleichen(p[1], ref, ap_)
                zeiten[f"pegel_{p[3]}_db"] = g
                if g:
                    parts[i] = (p[0], ap_, *p[2:])
    vl = work / "video.txt"
    vl.write_text("".join(f"file '{p[0].as_posix()}'\n" for p in parts), encoding="utf-8")
    al = work / "audio.txt"
    al.write_text("".join(f"file '{p[1].as_posix()}'\n" for p in parts), encoding="utf-8")
    vid = work / "video_all.mp4"
    run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(vl), "-vf", f"fps={FPS}", *VENC, str(vid)])
    wav = work / "audio_all.wav"
    run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(al), "-c", "copy", str(wav)])
    stamp = test.name.rsplit("_", 1)[-1]
    out = Path(_arg("--out")).resolve() if _arg("--out") else \
        test / (f"weltlage_rohschnitt_{stamp}" + ("_lipsync" if lip or freisteller else "") +
                 ("_kurztest" if kurztest else "") + ".mp4")
    zeiten["ton_master"] = master_ton(wav, vid, out)
    print("TON MASTER", zeiten["ton_master"], flush=True)
    t, marks, meldung_start = 0.0, [], {}
    for p in parts:
        marks.append(f"{int(t//60):02d}:{t%60:05.2f}  {p[3]} ({p[2]:.1f} s)")
        if p[3].startswith("Szene Meldung "):
            meldung_start[p[3][len("Szene Meldung "):]] = t
        t += p[2]
    zm = out.with_name(out.stem + "_zeitmarken.txt") if _arg("--out") else test / "zeitmarken.txt"
    zm.write_text("\n".join(marks) + f"\nGesamt {t:.1f} s\n", encoding="utf-8")
    # Quellen-Bild-Platzierung (Meldung, Karten-Pfad, Zeit im Master, gesprochener Satz) fuer die semantische
    # Einblendungs-Pruefung (video/einblendungen.py, tools/weltlage_abnahme.py Abschnitt 7.)
    from video.einblendungen import satz_bei
    bilder_platzierung = []
    for roh in bild_platzierungen_roh:
        start_master = meldung_start.get(roh["meldung"])
        if start_master is None:
            continue
        mitte = roh["start_in_meldung"] + roh["dauer"] / 2
        plate = work / f"plate_{Path(roh['shot']['png']).stem}.png"
        bilder_platzierung.append({
            "meldung": roh["meldung"], "plate": str(plate.resolve()),
            "t0": round(start_master + mitte, 3), "dauer": round(roh["dauer"], 3),
            "satz": satz_bei(roh["text"], roh["narration_dauer"], mitte),
            "domain": roh["shot"].get("domain", "")})
    (test / "bilder_platzierung.json").write_text(json.dumps(bilder_platzierung, ensure_ascii=False, indent=1),
                                                   encoding="utf-8")
    # Endpruefung: jede Sprechszene im fertigen Video == ihre nachgewiesene Chatterbox-Datei, sonst unbrauchbar
    from weltlage_stimmpruefung import pruefe_video, zusammenfassung
    t, pruef = 0.0, []
    for p in parts:
        if p[3] in stimm_szenen:
            quelle, pre, laenge = stimm_szenen[p[3]]
            pruef.append({"label": p[3], "start": round(t, 3), "laenge": round(min(laenge, p[2]), 3),
                          "wav": str(quelle), "pre": pre})
        t += p[2]
    bericht = pruefe_video(out, pruef)
    print(zusammenfassung(bericht))
    if not bericht["ok"]:
        schlecht = out.with_name(out.stem + "_UNGUELTIG.mp4")
        out.replace(schlecht)
        raise SystemExit(f"Stimmen-Pruefung fehlgeschlagen - Video als {schlecht.name} markiert, nicht verschicken")
    zeiten["gesamt"] = round(time.time() - t_all, 1)
    out.with_name(out.stem + "_renderzeiten.json").write_text(json.dumps(zeiten, indent=2), encoding="utf-8")
    print("\n".join(marks)); print("ZEITEN", zeiten); print("FERTIG", out, f"{t:.1f}s")


if __name__ == "__main__":
    main()
