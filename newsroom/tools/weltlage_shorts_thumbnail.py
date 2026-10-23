#!/usr/bin/env python
"""Weltlage Kompakt: eigenes, komponiertes Vorschaubild fuer Shorts (1080x1920, Marlons Auftrag 15.10.2026).

Vorher: upload_datei() lud Shorts immer mit thumb_path=None hoch, Studio waehlte selbst einen Zufalls-Frame
(spaeter ersetzt durch einen rohen ffmpeg-Standbild-Grab aus der Titelkarten-Phase, _thumbnail_aus_titelkarte in
weltlage_shorts_takt.py - aber immer noch kein Text/Branding, nur ein Videoframe). Problem (wie beim parallelen
Fund fuer den Jarvis-KI-Kanal): die Kachelansicht im Kanal/den Suggestions schneidet ein 9:16-Bild auf ein
schmaleres Seitenverhaeltnis zu, dabei gehen oben und unten je etwa ein Viertel des Bilds verloren. Inhalt muss
darum in einer sicheren Mittelzone bleiben (SAFE_TOP..SAFE_UNTEN unten) - dieselben Grenzwerte wie beim Jarvis-KI-
Kanal (tools/jarvis_shorts_thumbnail.py im jarvis-Repo), weil es dieselbe YouTube-UI ist, kein kanalspezifischer
Wert.

Stil wie die bestehende Folgen-Thumbnail-Vorlage (video/weltlage_thumbnail.py): eigenes Studio als Hintergrund,
Latara-Freisteller passend zur Stimmung, Markengelb/Logo - nur im Hochformat neu angeordnet (Banderole oben,
Frage/Hook-Text darunter, Latara, Markenbalken unten), alles als EIN Block vertikal in der Safe-Zone zentriert,
damit kurze wie lange Titel nie oben/unten aus der Zone ragen.

    python -m tools.weltlage_shorts_thumbnail <out.jpg> "Titel/Frage des Shorts" [banderole]

Aufruf-Stellen: tools/weltlage_shorts.py (baut das Bild einmal beim Schneiden jedes Shorts), reports/-Skripte zum
nachtraeglichen Setzen auf bereits veroeffentlichte Shorts. Reine Pillow-Bildverarbeitung, kein Netz-/GPU-Zugriff.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from video.weltlage_thumbnail import (  # noqa: E402
    ASSETS, FARBEN, FESTE_FARBE, SCHWARZ, WEISS, _font, _foto_pfad, _latara, _schatten_text,
)

W, H = 1080, 1920
RAND_X = 80
MAX_BREITE = W - 2 * RAND_X
# Safe-Zone: identisch zu jarvis_shorts_thumbnail.py (gleiche YouTube-Kachel-/Shorts-Player-UI, kanalunabhaengig).
SAFE_TOP = 320
SAFE_UNTEN = 1600
ACCENT = (255, 209, 0)   # Markengelb, wie tts/align_captions.ACCENT (#FFD100)
BANDEROLE_H = 78
PHOTO_H = 560
BRAND_H = 84


def _hintergrund(fc) -> Image.Image:
    bg = Image.open(ASSETS / "studio.png").convert("RGB")
    s = max(W / bg.width, H / bg.height)
    bg = bg.resize((round(bg.width * s), round(bg.height * s)), Image.LANCZOS)
    bg = bg.crop(((bg.width - W) // 2, (bg.height - H) // 2, (bg.width - W) // 2 + W, (bg.height - H) // 2 + H))
    bg = bg.filter(ImageFilter.GaussianBlur(10))
    bg = ImageEnhance.Brightness(bg).enhance(0.30)
    tint = Image.new("RGB", (W, H), fc)
    return Image.blend(bg, tint, 0.20)


def _woerter_umbrechen(d, text: str, font, max_breite: int) -> list[str]:
    woerter, zeilen, zeile = text.split(), [], ""
    for w in woerter:
        probe = (zeile + " " + w).strip()
        if d.textlength(probe, font=font) > max_breite and zeile:
            zeilen.append(zeile)
            zeile = w
        else:
            zeile = probe
    if zeile:
        zeilen.append(zeile)
    return zeilen


def _headline_passend(d, text: str, max_breite: int, verfuegbare_hoehe: int, start: int = 100, minimum: int = 46,
                      max_zeilen: int = 4):
    """Schrumpft die Schrift, bis Zeilenumbruch UND Gesamthoehe (Zeilen * 1.18*size) in verfuegbare_hoehe
    passen - reine Zeilenzahl reicht nicht (ein 4-zeiliger Titel bei 100pt ist oft hoeher als die ganze
    Safe-Zone erlaubt, siehe Testfall 'Starlink-Brand...')."""
    size = start
    while size > minimum:
        f = _font("impact.ttf", size)
        zeilen = _woerter_umbrechen(d, text, f, max_breite)
        if len(zeilen) <= max_zeilen and len(zeilen) * int(size * 1.18) <= verfuegbare_hoehe:
            return f, zeilen, size
        size -= 4
    f = _font("impact.ttf", minimum)
    return f, _woerter_umbrechen(d, text, f, max_breite), minimum


def _banderole(bild: Image.Image, text: str, fc, y: int) -> None:
    d = ImageDraw.Draw(bild)
    ban = (text or "WELTLAGE").upper().strip()
    f = _font("arialbd.ttf", 38)
    bw = d.textlength(ban, font=f)
    bx0, bx1 = (W - (bw + 60)) / 2, (W + (bw + 60)) / 2
    d.rounded_rectangle((bx0, y, bx1, y + BANDEROLE_H), radius=BANDEROLE_H / 2, fill=fc)
    d.text(((W - bw) / 2, y + (BANDEROLE_H - 38) / 2 - 4), ban, font=f, fill=WEISS)


def _markenbalken(bild: Image.Image, y: int) -> None:
    d = ImageDraw.Draw(bild)
    d.rectangle((0, y, W, y + BRAND_H), fill=(8, 10, 18, 255) if bild.mode == "RGBA" else (8, 10, 18))
    logo = Image.open(ROOT / "config" / "brand" / "logo.png").convert("RGBA").resize((56, 56), Image.LANCZOS)
    logo_x = (W - 56 - 16 - int(_font("arialbd.ttf", 32).getlength("WELTLAGE KOMPAKT"))) // 2
    bild.alpha_composite(logo, (max(RAND_X, logo_x), y + (BRAND_H - 56) // 2))
    d = ImageDraw.Draw(bild)
    d.text((max(RAND_X, logo_x) + 56 + 16, y + (BRAND_H - 32) // 2 - 2), "WELTLAGE KOMPAKT",
            font=_font("arialbd.ttf", 32), fill=WEISS)


def render(titel: str, banderole: str, out: Path, farbe: str = FESTE_FARBE, foto: str | None = None,
          stimmungstext: str | None = None, merken: bool = True) -> Path:
    """Baut das komponierte Shorts-Thumbnail. titel ist der themenbezogene Text (Frage/Hook des einzelnen
    Shorts), banderole das Thema-Schlagwort der Folge (z.B. 'KRISE'), farbe der Farbcode wie bei der
    Folgen-Vorlage (FESTE_FARBE = immer 'konflikt', Marlons Entscheid 02.10.2026)."""
    fc = FARBEN.get(farbe, FARBEN["politik"])
    bild = _hintergrund(fc).convert("RGBA")
    d = ImageDraw.Draw(bild)
    gap1, gap2, gap3 = 30, 40, 26
    verfuegbar = SAFE_UNTEN - SAFE_TOP
    fixe_h = BANDEROLE_H + gap1 + gap2 + PHOTO_H + gap3 + BRAND_H
    headline, zeilen, size = _headline_passend(d, (titel or "").strip().upper(), MAX_BREITE, verfuegbar - fixe_h)
    zeilenhoehe = int(size * 1.18)
    headline_h = zeilenhoehe * len(zeilen)
    lat, kante = _latara(_foto_pfad(farbe, foto, stimmungstext, merken), fc)
    faktor = PHOTO_H / lat.height
    lat = lat.resize((round(lat.width * faktor), PHOTO_H), Image.LANCZOS)
    kante = kante.resize((round(kante.width * faktor), PHOTO_H), Image.LANCZOS)

    gesamt_h = BANDEROLE_H + gap1 + headline_h + gap2 + PHOTO_H + gap3 + BRAND_H
    y = SAFE_TOP + max(0, (verfuegbar - gesamt_h) // 2)
    if y + gesamt_h > SAFE_UNTEN:
        y = max(SAFE_TOP, SAFE_UNTEN - gesamt_h)

    _banderole(bild, banderole, fc, y)
    y += BANDEROLE_H + gap1
    for zeile in zeilen:
        bw = d.textlength(zeile, font=headline)
        _schatten_text(bild, ((W - bw) / 2, y), zeile, headline, WEISS)
        d = ImageDraw.Draw(bild)
        y += zeilenhoehe
    y += gap2
    foto_x = (W - lat.width) // 2
    bild.alpha_composite(kante, (foto_x, y))
    bild.alpha_composite(lat, (foto_x, y))
    y += PHOTO_H + gap3
    _markenbalken(bild, y)

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    bild.convert("RGB").save(out, quality=92)
    return out


def fuer_short(meta: dict, out: Path, ordner: Path | None = None, merken: bool = True) -> Path:
    """Einstieg fuer die Pipeline: meta ist das meta_short-Dict aus weltlage_shorts._baue_einen (title,
    description), ordner (falls bekannt) die Folge, aus der der Short geschnitten wurde - liefert das
    Thema-Schlagwort (Banderole) der Folge, damit der Short dasselbe Branding wie die Folge trägt."""
    titel = str(meta.get("title") or meta.get("titel") or "").strip()
    banderole = "WELTLAGE"
    stimmungsteile = [titel, meta.get("description")]
    if ordner is not None:
        try:
            from video.weltlage_thumbnail import felder
            f = felder(Path(ordner))
            banderole = f.get("banderole") or banderole
            stimmungsteile.append(f.get("stimmungstext"))
        except Exception:   # noqa: BLE001 - Branding-Schlagwort ist Zusatznutzen, kein Pflichtschritt
            pass
    stimmungstext = " ".join(str(s) for s in stimmungsteile if s)
    try:   # seit 21.10.2026 Eilmeldungs-Vorlage im Hochformat, alte Vorlage bleibt Rueckfall
        from video import weltlage_thumbnail_eil as eil
        szene = Path(out).stem.removesuffix("_thumb")
        nr = re.match(r"short_(\d+)", szene)
        w = titel.split()
        mitte = max(1, (len(w) + 1) // 2)
        return eil.baue({"zeile1": " ".join(w[:mitte]), "zeile2": " ".join(w[mitte:]), "banderole": banderole,
                         "stimmungstext": stimmungstext, "titel": titel, "szene": szene,
                         "short_nr": int(nr.group(1)) if nr else 1}, Path(out), short=True, ordner=ordner,
                        frisch=bool(ordner is not None and (Path(ordner) / "breaking.flag").exists()))
    except Exception as e:   # noqa: BLE001
        print(f"WARNUNG Eilmeldungs-Short-Thumbnail fehlgeschlagen ({type(e).__name__}: {e}) - alte Vorlage",
              file=sys.stderr)
    return render(titel, banderole, Path(out), stimmungstext=stimmungstext, merken=merken)


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("out", type=Path)
    p.add_argument("titel")
    p.add_argument("banderole", nargs="?", default="WELTLAGE")
    a = p.parse_args()
    print(render(a.titel, a.banderole, a.out, stimmungstext=a.titel, merken=False))


if __name__ == "__main__":
    main()
