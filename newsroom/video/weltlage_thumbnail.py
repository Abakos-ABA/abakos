"""Weltlage Kompakt - feste Thumbnail-Vorlage pro Folge (Marlons Ja zur Vorbild-Analyse, 01.10.2026).
STANDARD seit Marlons Entscheid 01.10.2026 nachmittags (neues Thumbnail = diese Vorlage; Tageslauf Schritt «thumbnail»).
Foto-Auswahl erweitert 02.10.2026 (Task bbd8): das Foto der Moderatorin wird automatisch zur Farbe der Folge
passend gewaehlt (echte Freisteller aus Documents/WK, kein KI-Kitsch).
Marlons Entscheid 02.10.2026 (Variante B der 3 Muster): feste Vorlage fuer jede Folge ist jetzt immer die
B-Variante - rot (konflikt) - unabhaengig vom Farbcode-Feld des Skripts, siehe FESTE_FARBE.
Foto-Auswahl nach Stimmung (Task 20261002-220950-b2d6, 02.10.2026): Marlons Foto-Pool (Documents/WK/Latara
Thumbnails) zeigt inzwischen mehrere Ausdruecke (geschockt, nachdenklich, mit Papier, ...). video/latara_foto.py
waehlt daraus automatisch das Bild, das zur Stimmung des Skripttexts passt, und wiederholt keines der letzten
paar Folgen. Ist der Ordner nicht da (Platte nicht eingebunden) oder liefert er nichts Passendes, faellt die
Vorlage auf die alten festen Fotos unter config/brand/thumbnail/ zurueck (FOTO_FUER_FARBE).

Eigenes, festes Layout des Kanals (1280x720 JPG), automatisch aus dem Skript der Folge:
  - Hintergrund: das eigene Studio (config/brand/thumbnail/studio.png), weichgezeichnet, abgedunkelt und mit dem
    Farbcode der Folge eingefaerbt - keine Pressefotos, keine fremden Bilder.
  - links eine durchgehende Farbcode-Leiste; oben links die Banderole (1-2 Woerter) in der Farbcode-Farbe,
    darunter zwei Zeilen grosse Schlagwoerter (Impact, Zeile 1 weiss, Zeile 2 Markengelb) - im Skript als kurze
    Frage angelegt (siehe config/prompts/weltlage_analyse.md), damit das Thumbnail Lust aufs Zusehen macht.
  - rechts Latara (Kopf und Schultern aus einem Freisteller) mit Lichtkante in der Farbcode-Farbe. Welches Foto,
    siehe oben (Stimmung des Texts, sonst FOTO_FUER_FARBE).
  - unten Markenbalken mit Logo und «WELTLAGE KOMPAKT».
Farbcode (Feld «farbe» des Skripts): konflikt = rot, wirtschaft = gruen, politik = blau, krise = orange.

    python -m video.weltlage_thumbnail <folgenordner>      -> <folgenordner>/thumbnails/thumbnail.jpg
    python -m video.weltlage_thumbnail --test <out.jpg> BANDEROLE "ZEILE 1" "ZEILE 2" farbe [foto.png]

Liest texte.json (Feld «thumbnail», sonst «thumbnail_text») bzw. texte.entwurf.json/skript.json. Nur CPU.
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from video import latara_foto

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "config" / "brand" / "thumbnail"
W, H = 1280, 720
FARBEN = {"konflikt": (214, 32, 42), "wirtschaft": (0, 168, 96), "politik": (36, 112, 230), "krise": (245, 124, 0)}
FOTO_FUER_FARBE = {"konflikt": "latara_schock.png", "krise": "latara_schock.png",
                   "wirtschaft": "latara.png", "politik": "latara.png"}
FESTE_FARBE = "konflikt"   # Marlons Entscheid 02.10.: jede Folge bekommt die B-Vorlage (rot, Schock-Pose)
GELB, WEISS, SCHWARZ = (255, 204, 0), (255, 255, 255), (0, 0, 0)
FONTS = Path(r"C:\Windows\Fonts")
TEXT_BREITE = 700          # Schlagwoerter bleiben links von Latara
LEISTE = 18


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    for n in (name, "arialbd.ttf"):
        if (FONTS / n).exists():
            return ImageFont.truetype(str(FONTS / n), size)
    return ImageFont.load_default(size=size)


def _hintergrund(farbe) -> Image.Image:
    bg = Image.open(ASSETS / "studio.png").convert("RGB")
    s = max(W / bg.width, H / bg.height)
    bg = bg.resize((round(bg.width * s), round(bg.height * s)), Image.LANCZOS)
    bg = bg.crop(((bg.width - W) // 2, (bg.height - H) // 2, (bg.width - W) // 2 + W, (bg.height - H) // 2 + H))
    bg = bg.filter(ImageFilter.GaussianBlur(7))
    bg = ImageEnhance.Brightness(bg).enhance(0.42)
    tint = Image.new("RGB", (W, H), farbe)
    bg = Image.blend(bg, tint, 0.16)
    # nach links dunkler, damit die Schrift steht
    maske = Image.linear_gradient("L").rotate(90, expand=True).resize((W, H))   # links hell -> rechts dunkel
    dunkel = Image.new("RGB", (W, H), (6, 8, 14))
    return Image.composite(dunkel, bg, maske.point(lambda v: int(v * 0.75)))


def _foto_datei(farbe: str, foto: str | None = None) -> Path:
    name = foto or FOTO_FUER_FARBE.get(farbe, "latara.png")
    pfad = ASSETS / name
    return pfad if pfad.exists() else ASSETS / "latara.png"


def _foto_pfad(farbe: str, foto: str | None, stimmungstext: str | None, merken: bool = True) -> Path:
    """Welches Foto gezeigt wird: explizite Angabe (CLI-Test) > Stimme-passendes Foto aus Marlons Pool >
    alte feste Fotos je Farbe (FOTO_FUER_FARBE). merken=False fuer Probe-Thumbnails, die nicht in den
    Wiederholungs-Verlauf einer echten Folge gehoeren."""
    if foto:
        return _foto_datei(farbe, foto)
    if stimmungstext:
        gewaehlt = latara_foto.waehle_foto(stimmungstext, merken=merken)
        if gewaehlt and gewaehlt.exists():
            return gewaehlt
    return _foto_datei(farbe)


def _latara(pfad: Path, fc) -> tuple[Image.Image, Image.Image]:
    """Kopf und Schultern als RGBA plus Lichtkante (weiche, eingefaerbte Silhouette). fc ist die RGB-Farbe der
    Lichtkante."""
    im = Image.open(pfad).convert("RGBA")
    im = im.crop((0, 0, im.width, int(im.height * 0.66)))          # bis unter die Schultern
    hoehe = 700
    im = im.resize((round(im.width * hoehe / im.height), hoehe), Image.LANCZOS)
    alpha = im.split()[3]
    kante = Image.new("RGBA", im.size, fc + (0,))
    kante.putalpha(alpha.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(18)).point(lambda v: v * 6 // 10))
    return im, kante


def _zeile_passend(d, text: str, font_name: str, start: int, breite: int, minimum: int = 60):
    size = start
    f = _font(font_name, size)
    while d.textlength(text, font=f) > breite and size > minimum:
        size -= 4
        f = _font(font_name, size)
    return f, size


def _schatten_text(bild: Image.Image, xy, text, font, fill):
    sh = Image.new("RGBA", bild.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).text((xy[0] + 6, xy[1] + 6), text, font=font, fill=(0, 0, 0, 220))
    bild.alpha_composite(sh.filter(ImageFilter.GaussianBlur(7)))
    ImageDraw.Draw(bild).text(xy, text, font=font, fill=fill, stroke_width=4, stroke_fill=SCHWARZ)


def render(banderole: str, zeile1: str, zeile2: str, farbe: str, out: Path, foto: str | None = None,
           *, stimmungstext: str | None = None, merken: bool = True) -> Path:
    fc = FARBEN.get(farbe, FARBEN["politik"])
    bild = _hintergrund(fc).convert("RGBA")
    # Latara rechts, Lichtkante dahinter
    lat, kante = _latara(_foto_pfad(farbe, foto, stimmungstext, merken), fc)
    x = W - lat.width + 40
    y = H - lat.height + 20
    bild.alpha_composite(kante, (x, y))
    bild.alpha_composite(lat, (x, y))
    d = ImageDraw.Draw(bild)
    # Farbcode-Leiste links
    d.rectangle((0, 0, LEISTE, H), fill=fc)
    # Banderole
    ban = banderole.upper().strip()
    fb = _font("arialbd.ttf", 46)
    bw = d.textlength(ban, font=fb)
    bx, by = LEISTE + 34, 52
    d.polygon([(bx, by), (bx + bw + 48, by), (bx + bw + 30, by + 66), (bx, by + 66)], fill=fc)
    d.text((bx + 18, by + 8), ban, font=fb, fill=WEISS)
    # Schlagwoerter
    ty = by + 96
    for text, farbe_text, start in ((zeile1.upper().strip(), WEISS, 132), (zeile2.upper().strip(), GELB, 120)):
        if not text:
            continue
        f, size = _zeile_passend(d, text, "impact.ttf", start, TEXT_BREITE)
        _schatten_text(bild, (bx - 4, ty), text, f, farbe_text)
        d = ImageDraw.Draw(bild)
        ty += int(size * 1.06)
    # Markenbalken unten
    d.rectangle((0, H - 74, W, H), fill=(8, 10, 18))
    d.rectangle((0, H - 78, W, H - 74), fill=fc)
    logo = Image.open(ROOT / "config" / "brand" / "logo.png").convert("RGBA").resize((58, 58), Image.LANCZOS)
    bild.alpha_composite(logo, (LEISTE + 30, H - 66))
    d.text((LEISTE + 102, H - 56), "WELTLAGE KOMPAKT", font=_font("arialbd.ttf", 32), fill=WEISS)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    bild.convert("RGB").save(out, quality=92)
    return out


def felder(ordner: Path) -> dict:
    """banderole/zeile1/zeile2/farbe aus texte.json, texte.entwurf.json oder skript.json der Folge."""
    for name in ("texte.json", "texte.entwurf.json"):
        p = ordner / name
        if p.exists():
            t = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(t.get("thumbnail"), dict) or t.get("thumbnail_text"):
                break
    else:
        t = json.loads((ordner / "skript.json").read_text(encoding="utf-8"))["skript"]
    th = dict(t.get("thumbnail") or {}) if isinstance(t.get("thumbnail"), dict) else {}
    if not th.get("zeile1"):                       # alte Skripte: nur thumbnail_text
        w = str(t.get("thumbnail_text") or t.get("titel") or "").split()
        mitte = max(1, (len(w) + 1) // 2)
        th.update(zeile1=" ".join(w[:mitte]), zeile2=" ".join(w[mitte:]))
    th.setdefault("banderole", "WELTLAGE")
    th["farbe"] = FESTE_FARBE
    felder_ = {k: th.get(k) or "" for k in ("banderole", "zeile1", "zeile2", "farbe")}
    # mehr Text fuer die Stimmungs-Erkennung (video/latara_foto.py) als nur die kurzen Schlagwoerter
    stimmungsteile = [th.get("banderole"), th.get("zeile1"), th.get("zeile2"),
                      t.get("titel"), t.get("zentrale_these"), t.get("hook"), t.get("thumbnail_text")]
    felder_["stimmungstext"] = " ".join(str(s) for s in stimmungsteile if s)
    return felder_


def fuer_folge(ordner: Path) -> Path:
    ordner = Path(ordner)
    f = felder(ordner)
    return render(f["banderole"], f["zeile1"], f["zeile2"], f["farbe"], ordner / "thumbnails" / "thumbnail.jpg",
                  stimmungstext=f["stimmungstext"])


if __name__ == "__main__":
    if sys.argv[1:2] == ["--test"]:
        print(render(sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6], Path(sys.argv[2]),
                     sys.argv[7] if len(sys.argv) > 7 else None))
    else:
        print(fuer_folge(Path(sys.argv[1])))
