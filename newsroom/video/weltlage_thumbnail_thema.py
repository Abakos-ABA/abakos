"""Weltlage Kompakt - Themenbild-Thumbnail «Cyber-Noir» (Marlons Auftrag 27.10.2026).

Kein Moderator, keine Moderatorin und keine Masken-Figur auf dem Bild. Gross das Foto der Person/Sache, um die es in
der Folge geht, dazu eine kurze Schlagzeile (max. 5 Woerter) und ein Symbol (Warndreieck, Pfeil, Fadenkreuz, Blitz).

Farbwelt passend zum Masken-Moderator: Nachtschwarz/Tiefblau, Neon-Cyan als Kanalfarbe, Alarm-Rot fuer Konflikte.
Layout Langvideo 1280x720: Foto rechts gross und randlos, links dunkler Verlauf mit Label-Chip, Schlagzeile und Symbol,
unten Markenbalken. Layout Short 1080x1920: Foto oben bis Mitte, Schlagzeile + Symbol darunter, alles in der sicheren
Mittelzone (320..1600, wie tools/weltlage_shorts_thumbnail.py).

Bildwahl: video/weltlage_thumbnail_bild.waehle (Quellbild freier Quelle > lizenzfreies Foto Commons/Pexels > B-Roll-
Standbild, Merkliste, Attribution). Ohne Treffer: eigenes Symbolbild (Noir-Raster + grosses Symbol, rein
berechnet) - nie ein KI-Fake einer echten Person, nie ein unlizenziertes Bild.

Schalter: Umgebungsvariable WELTLAGE_THUMB_VORLAGE=thema oder config/weltlage_thumbnail.json {"vorlage": "thema"}.
Standard "eil" (alte Vorlage bleibt). Eingehaengt in video/weltlage_thumbnail_eil.baue.

    python -m video.weltlage_thumbnail_thema out.jpg "TITEL" [--short] [--foto datei.jpg] [--symbol warnung]
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FONTS = Path(r"C:\Windows\Fonts")
NACHT, TIEF = (6, 8, 16), (10, 18, 36)
CYAN, ROT, WEISS, GELB = (0, 229, 255), (255, 42, 62), (255, 255, 255), (255, 204, 0)
SCHALTER_DATEI = ROOT / "config" / "weltlage_thumbnail.json"
MAX_WOERTER = 5

# Symbol nach Thema (erste passende Regel gewinnt)
SYMBOL_REGELN = [
    (r"crash|b[oö]rse|einbruch|verlust|pleite|absturz|schulden|rezession|inflation|sinkt|f[aä]llt", "pfeil_runter", CYAN),
    (r"steigt|rekord|boom|explod|hoch|gewinn", "pfeil_hoch", CYAN),
    (r"angriff|krieg|rakete|drohne|milit|truppen|bomb|eskalat|iran|ukraine|gaza|israel|waffen", "fadenkreuz", ROT),
    (r"blackout|strom|energie|gas|[oö]l|sanktion|zoll|z[oö]lle", "blitz", GELB),
]
SYMBOL_STANDARD = ("warnung", ROT)


def schalter_aktiv() -> bool:
    v = os.environ.get("WELTLAGE_THUMB_VORLAGE", "").strip().lower()
    if not v:
        try:
            v = str(json.loads(SCHALTER_DATEI.read_text(encoding="utf-8")).get("vorlage", "")).strip().lower()
        except (OSError, ValueError):
            v = ""
    return v == "thema"


def _font(name: str, size: int):
    for n in (name, "arialbd.ttf"):
        if (FONTS / n).exists():
            return ImageFont.truetype(str(FONTS / n), size)
    return ImageFont.load_default(size=size)


def kurz_titel(zeilen: list[str], maxw: int = MAX_WOERTER) -> str:
    """Schlagzeile aus den Textzeilen, hoechstens maxw Woerter, Label-Woerter vorn weg."""
    t = re.sub(r"[«»\"„“]", "", " ".join(z for z in zeilen if z))
    t = re.sub(r"^\s*(breaking|eilmeldung|weltlage( kompakt)?|teil \d+)\s*[:!\-–]*\s*", "", t, flags=re.I)
    w = t.split()
    # Seit 18.11.2026: reine Gedankenstriche zaehlen nicht als Wort, und eine Neugier-Frage am Ende («WER KANN STÜRZEN?»)
    # bleibt ganz (ein Wort mehr), sonst fehlt genau die Luecke, die den Klick bringt.
    nutz = [x for x in w if re.search(r"\w", x)]
    if nutz and nutz[-1].endswith("?"):
        maxw += 1
    if len(nutz) > maxw:
        w = w[:maxw]
        # Seit 13.11.2026 (Thumbnail-Wache): nie mitten im Nebensatz enden («...SPIONIN: WIRD», «...EISENKOT STATT»).
        # Gibt es nach dem 2. Wort eine Satzgrenze (: , ; – ?), dort schneiden; sonst Fuellwoerter am Ende weg.
        grenze = max((i for i, x in enumerate(w[:-1]) if i >= 1 and re.search(r"[:,;?!–]$", x)), default=None)
        if grenze is not None:
            w = w[:grenze + 1]      # ganzer Satzteil: Endwort bleiben lassen («GIBT AFFÄRE ZU»)
        while grenze is None and len(w) > 2 and w[-1].lower().strip(",.:;?!") in _FUELL_ENDE:
            w.pop()
    return " ".join(w).upper().rstrip(",.:;–-")


_FUELL_ENDE = {"und", "oder", "aber", "der", "die", "das", "den", "dem", "des", "von", "vom", "mit", "für", "fuer", "in",
               "im", "zu", "zum", "zur", "nach", "bei", "ein", "eine", "einen", "einem", "statt", "was", "wer", "wie", "wird",
               "werden", "warum", "ob", "dass", "als", "auf", "an", "am", "um", "über", "ueber", "vor", "gegen", "ist",
               "sind", "hat", "haben", "kann", "will", "soll", "nun", "jetzt", "so"}


def symbol_waehlen(text: str) -> tuple[str, tuple]:
    t = (text or "").lower()
    for muster, name, farbe in SYMBOL_REGELN:
        if re.search(muster, t):
            return name, farbe
    return SYMBOL_STANDARD


# ---------------------------------------------------------------- Symbole (gezeichnet)
def symbol_zeichnen(name: str, farbe, groesse: int) -> Image.Image:
    s = groesse
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c, lw = s / 2, max(6, s // 11)
    if name == "warnung":
        d.polygon([(c, s * .06), (s * .96, s * .90), (s * .04, s * .90)], outline=farbe, width=lw)
        d.rounded_rectangle((c - lw * .55, s * .34, c + lw * .55, s * .62), radius=lw // 2, fill=farbe)
        d.ellipse((c - lw * .62, s * .69, c + lw * .62, s * .69 + lw * 1.24), fill=farbe)
    elif name in ("pfeil_runter", "pfeil_hoch"):
        d.rectangle((c - lw * .8, s * .08, c + lw * .8, s * .60), fill=farbe)
        d.polygon([(s * .12, s * .55), (s * .88, s * .55), (c, s * .95)], fill=farbe)
        if name == "pfeil_hoch":
            im = im.transpose(Image.FLIP_TOP_BOTTOM)
    elif name == "fadenkreuz":
        d.ellipse((s * .14, s * .14, s * .86, s * .86), outline=farbe, width=lw)
        d.ellipse((s * .38, s * .38, s * .62, s * .62), fill=farbe)
        for a, b in (((c, 0), (c, s * .30)), ((c, s * .70), (c, s)), ((0, c), (s * .30, c)), ((s * .70, c), (s, c))):
            d.line([a, b], fill=farbe, width=lw)
    elif name == "blitz":
        d.polygon([(s * .60, s * .02), (s * .20, s * .56), (s * .46, s * .56), (s * .36, s * .98),
                   (s * .82, s * .38), (s * .54, s * .38)], fill=farbe)
    # Leuchten
    glow = Image.new("RGBA", im.size, farbe + (0,))
    glow.putalpha(im.split()[3].filter(ImageFilter.GaussianBlur(s // 14)).point(lambda v: min(255, v * 2 // 3)))
    out = Image.new("RGBA", im.size, (0, 0, 0, 0))
    out.alpha_composite(glow)
    out.alpha_composite(im)
    return out


# ---------------------------------------------------------------- Hintergruende
def _noir_raster(w: int, h: int, farbe) -> Image.Image:
    bg = Image.new("RGB", (w, h), NACHT)
    d = ImageDraw.Draw(bg)
    for x in range(0, w, 48):
        d.line([(x, 0), (x, h)], fill=(14, 24, 44), width=1)
    for y in range(0, h, 48):
        d.line([(0, y), (w, y)], fill=(14, 24, 44), width=1)
    gl = Image.radial_gradient("L").resize((w, h)).point(lambda v: 255 - v)
    return Image.composite(Image.new("RGB", (w, h), tuple(int(x * .35) for x in farbe)), bg, gl.point(lambda v: v // 3))


def symbolbild(w: int, h: int, name: str, farbe) -> Image.Image:
    """Eigenes Symbolbild ohne Foto: Noir-Raster mit grossem leuchtendem Symbol."""
    bg = _noir_raster(w, h, farbe).convert("RGBA")
    sym = symbol_zeichnen(name, farbe, int(min(w, h) * .62))
    bg.alpha_composite(sym, ((w - sym.width) // 2, (h - sym.height) // 2))
    return bg.convert("RGB")


def _foto_einpassen(foto: Image.Image, w: int, h: int) -> Image.Image:
    """Fuellt w x h; Zuschnitt oben betont (Gesichter sitzen im oberen Drittel), Gesichtserkennung wenn verfuegbar."""
    s = max(w / foto.width, h / foto.height)
    f = foto.resize((round(foto.width * s), round(foto.height * s)), Image.LANCZOS)
    cx, cy = f.width / 2, f.height * 0.38
    try:
        import cv2
        import numpy as np
        g = cv2.cvtColor(np.array(foto.convert("RGB")), cv2.COLOR_RGB2GRAY)
        casc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        gs = foto.width / 800
        kl = cv2.resize(g, (800, round(foto.height / gs)))
        ge = casc.detectMultiScale(kl, 1.15, 5, minSize=(40, 40))
        if len(ge):
            x, y, bw, bh = max(ge, key=lambda r: r[2] * r[3])
            cx, cy = (x + bw / 2) * gs * s, (y + bh / 2) * gs * s
    except Exception:   # noqa: BLE001 - Zusatznutzen
        pass
    x0 = int(min(max(cx - w / 2, 0), f.width - w))
    y0 = int(min(max(cy - h * 0.42, 0), f.height - h))
    return f.crop((x0, y0, x0 + w, y0 + h))


def _noir_look(foto: Image.Image, farbe) -> Image.Image:
    """Foto kontrastreich, leicht entsaettigt, mit kalter Toenung - einheitlicher Kanal-Look."""
    im = ImageEnhance.Color(foto).enhance(0.78)
    im = ImageEnhance.Contrast(im).enhance(1.18)
    im = ImageEnhance.Brightness(im).enhance(0.92)
    tint = Image.new("RGB", im.size, (0, 40, 70))
    return ImageChops.screen(im, ImageChops.multiply(tint, Image.new("RGB", im.size, (90, 90, 90))))


def _scanlines(bild: Image.Image) -> None:
    ov = Image.new("RGBA", bild.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    for y in range(0, bild.height, 4):
        d.line([(0, y), (bild.width, y)], fill=(0, 0, 0, 34), width=1)
    bild.alpha_composite(ov)


def _ecken(bild: Image.Image, box, farbe, l: int = 54, b: int = 6) -> None:
    d = ImageDraw.Draw(bild)
    x0, y0, x1, y1 = box
    for (x, y, dx, dy) in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
        d.line([(x, y), (x + dx * l, y)], fill=farbe, width=b)
        d.line([(x, y), (x, y + dy * l)], fill=farbe, width=b)


def _text_glitch(bild: Image.Image, xy, text, font, akzent):
    """Weisse Impact-Schrift mit Cyan/Rot-Versatz (Glitch) und schwarzem Rand."""
    d = ImageDraw.Draw(bild)
    sh = Image.new("RGBA", bild.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).text((xy[0] + 6, xy[1] + 8), text, font=font, fill=(0, 0, 0, 230))
    bild.alpha_composite(sh.filter(ImageFilter.GaussianBlur(8)))
    d = ImageDraw.Draw(bild)
    d.text((xy[0] - 4, xy[1] + 2), text, font=font, fill=akzent + (255,))
    d.text((xy[0] + 4, xy[1] - 2), text, font=font, fill=(255, 42, 62, 255) if akzent == CYAN else CYAN + (255,))
    d.text(xy, text, font=font, fill=WEISS, stroke_width=3, stroke_fill=(0, 0, 0))


def _umbrechen(d, text: str, font, breite: int) -> list[str]:
    zeilen, z = [], ""
    for w in text.split():
        p = (z + " " + w).strip()
        if d.textlength(p, font=font) > breite and z:
            zeilen.append(z)
            z = w
        else:
            z = p
    return zeilen + ([z] if z else [])


def _schlagzeile_passend(d, text: str, breite: int, hoehe: int, start: int, minimum: int = 52, max_zeilen: int = 3):
    size = start
    while size > minimum:
        f = _font("impact.ttf", size)
        z = _umbrechen(d, text, f, breite)
        if len(z) <= max_zeilen and len(z) * int(size * 1.08) <= hoehe:
            return f, z, size
        size -= 4
    f = _font("impact.ttf", minimum)
    return f, _umbrechen(d, text, f, breite), minimum


def _marke(bild: Image.Image, x: int, y: int, h: int, mitte: bool = False, breite: int = 0) -> None:
    logo = Image.open(ROOT / "config" / "brand" / "logo.png").convert("RGBA").resize((h, h), Image.LANCZOS)
    f = _font("arialbd.ttf", int(h * .52))
    d = ImageDraw.Draw(bild)
    tw = d.textlength("WELTLAGE KOMPAKT", font=f)
    if mitte:
        x = int((breite - (h + 14 + tw)) // 2)
    bild.alpha_composite(logo, (x, y))
    ImageDraw.Draw(bild).text((x + h + 14, y + h * .22), "WELTLAGE KOMPAKT", font=f, fill=WEISS)


def _label_chip(bild: Image.Image, xy, text: str, farbe) -> int:
    d = ImageDraw.Draw(bild)
    f = _font("arialbd.ttf", 40)
    tw = d.textlength(text, font=f)
    x, y = xy
    d.polygon([(x, y), (x + tw + 54, y), (x + tw + 34, y + 62), (x, y + 62)], fill=farbe)
    d.text((x + 18, y + 8), text, font=f, fill=WEISS if farbe == ROT else NACHT)
    return int(y + 62)


# ---------------------------------------------------------------- Render
def render(titel: str, label: str, out: Path, foto: Image.Image | None = None, short: bool = False,
           symbol: str | None = None, text_fuer_symbol: str = "") -> Path:
    titel = kurz_titel([titel])
    sname, sfarbe = symbol_waehlen(text_fuer_symbol or titel)
    if symbol:
        sname = symbol
    akzent = CYAN
    W, H = (1080, 1920) if short else (1280, 720)
    if short:
        bild = _render_short(W, H, titel, label, foto, sname, sfarbe, akzent)
    else:
        bild = _render_lang(W, H, titel, label, foto, sname, sfarbe, akzent)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    bild.convert("RGB").save(out, quality=92)
    return out


def _render_lang(W, H, titel, label, foto, sname, sfarbe, akzent) -> Image.Image:
    bild = _noir_raster(W, H, sfarbe).convert("RGBA")
    fx = 430   # Foto beginnt hier (laeuft randlos bis rechts/oben/unten)
    ph = H - 74
    if foto is not None:
        f = _noir_look(_foto_einpassen(foto, W - fx, ph), sfarbe).convert("RGBA")
    else:
        f = symbolbild(W - fx, ph, sname, sfarbe).convert("RGBA")
    bild.alpha_composite(f, (fx, 0))
    # Verlauf: Foto geht nach links in Nachtschwarz ueber
    verl = Image.linear_gradient("L").rotate(90, expand=True).resize((560, ph)).point(lambda v: 255 - v)   # links deckend -> rechts durchsichtig
    maske = Image.new("L", (W, H), 0)
    maske.paste(verl, (fx, 0))
    maske.paste(255, (0, 0, fx, H))
    bild.paste(Image.new("RGBA", (W, H), NACHT + (255,)), (0, 0), maske.point(lambda v: int(v * .96)))
    _scanlines(bild)
    d = ImageDraw.Draw(bild)
    d.rectangle((0, 0, 14, H), fill=sfarbe)
    # Label + Schlagzeile
    y = _label_chip(bild, (46, 44), label.upper(), sfarbe if sfarbe != GELB else ROT) + 26
    f, zeilen, size = _schlagzeile_passend(d, titel, 700, H - 74 - y - 150, 170)
    for z in zeilen:
        _text_glitch(bild, (46, y), z, f, akzent)
        y += int(size * 1.08)
    # Symbol unten links neben dem Markenbalken
    sym = symbol_zeichnen(sname, sfarbe, 110)
    bild.alpha_composite(sym, (50, H - 74 - 110 - 16))
    d = ImageDraw.Draw(bild)
    d.line([(0, H - 74), (W, H - 74)], fill=akzent, width=3)
    d.rectangle((0, H - 71, W, H), fill=NACHT)
    _marke(bild, 46, H - 62, 50)
    _ecken(bild, (fx + 26, 26, W - 26, ph - 26), akzent)
    return bild


def _render_short(W, H, titel, label, foto, sname, sfarbe, akzent) -> Image.Image:
    SAFE_TOP, SAFE_UNTEN = 320, 1600
    bild = _noir_raster(W, H, sfarbe).convert("RGBA")
    foto_h = 880
    box = (40, SAFE_TOP, W - 40, SAFE_TOP + foto_h)
    f = (_noir_look(_foto_einpassen(foto, box[2] - box[0], foto_h), sfarbe) if foto is not None
         else symbolbild(box[2] - box[0], foto_h, sname, sfarbe)).convert("RGBA")
    # unten ins Schwarz auslaufen
    m = Image.linear_gradient("L").resize((f.width, foto_h)).point(lambda v: 255 - max(0, v - 150) * 255 // 105)
    schwarz = Image.new("RGBA", f.size, NACHT + (255,))
    f = Image.composite(f, schwarz, m)
    bild.alpha_composite(f, (box[0], box[1]))
    _scanlines(bild)
    d = ImageDraw.Draw(bild)
    _ecken(bild, (box[0] + 12, box[1] + 12, box[2] - 12, box[3] - 40), akzent)
    # Label-Chip links oben im Foto
    _label_chip(bild, (box[0] + 28, box[1] + 28), label.upper(), sfarbe if sfarbe != GELB else ROT)
    y = box[3] + 8
    fnt, zeilen, size = _schlagzeile_passend(d, titel, W - 120, SAFE_UNTEN - y - 130, 150, minimum=60)
    sym_h = 0
    for z in zeilen:
        bw = d.textlength(z, font=fnt)
        _text_glitch(bild, ((W - bw) / 2, y), z, fnt, akzent)
        y += int(size * 1.08)
    sym = symbol_zeichnen(sname, sfarbe, 120)
    bild.alpha_composite(sym, (W - sym.width - 56, box[1] + foto_h - 60 - 120))
    _marke(bild, 0, SAFE_UNTEN - 56, 54, mitte=True, breite=W)
    return bild


# ---------------------------------------------------------------- Pipeline-Einstieg
def baue(felder: dict, out: Path, *, short: bool = False, frisch: bool = False, ordner: Path | None = None,
         suche: list[str] | None = None, log=print) -> Path:
    """Gleiche Signatur wie weltlage_thumbnail_eil.baue (dort eingehaengt). Schreibt dieselbe Attribution
    (thumbnail_quelle[_short].json), die tageslauf.metadaten in die Beschreibung uebernimmt."""
    from video import weltlage_thumbnail_eil as eil
    label = eil.label_fuer(ordner, felder.get("stimmungstext") or "", frisch)
    titel = felder.get("titel") or f"{felder.get('zeile1', '')} {felder.get('zeile2', '')}"
    zeilen = [felder.get("zeile1") or "", felder.get("zeile2") or ""] if (felder.get("zeile1") or felder.get("zeile2")) else [titel]
    if suche is None and ordner is not None:
        from video import weltlage_thumbnail_bild as tb
        gef = tb.waehle(titel, ordner, felder.get("szene") or ("short" if short else "lang"),
                        int(felder.get("short_nr") or 1), log=log)
    elif suche is not None:
        gef = eil.pressefoto(suche, log=log)
    else:
        from video import weltlage_thumbnail_bild as tb
        gef = eil.pressefoto(tb.begriffe(titel), log=log)
    foto, k = gef if gef else (None, None)
    res = render(" ".join(zeilen), label, out, foto, short, text_fuer_symbol=f"{titel} {felder.get('stimmungstext') or ''}")
    if ordner is not None:
        q = Path(ordner) / "thumbnails" / ("thumbnail_quelle_short.json" if short else "thumbnail_quelle.json")
        q.parent.mkdir(parents=True, exist_ok=True)
        if k:
            q.write_text(json.dumps({"id": k["id"], "stufe": k.get("stufe"), "attribution": eil.attribution_zeile(k),
                                     "label": label, "vorlage": "thema"}, ensure_ascii=False, indent=1), encoding="utf-8")
        elif q.exists():
            q.unlink()
    return res


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    opt = {sys.argv[i]: sys.argv[i + 1] for i in range(1, len(sys.argv) - 1) if sys.argv[i] in ("--foto", "--symbol")}
    a = [x for x in a if x not in opt.values()]
    foto = Image.open(opt["--foto"]).convert("RGB") if "--foto" in opt else None
    print(render(a[1], "ALARM!", Path(a[0]), foto, "--short" in sys.argv, opt.get("--symbol")))
