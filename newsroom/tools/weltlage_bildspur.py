"""Weltlage Kompakt ohne Moderator (Marlon 20.11.2026: «Maskenmann komplett raus, Bild nur aus Screenshots, Quellen,
Filmmaterial, Text und Grafiken; weniger Quellen einblenden»). Ersetzt die Sprecher-Spur (Masken-Moderator) in den
Folgen (tools/weltlage_maskenformat.py) und in den eigenen Shorts (tools/weltlage_short_eigen.py).

Bildsprache (16:9, 1920x1080, 25 fps), Satz fuer Satz geschnitten:
  * kapitel  Kapitelkarte am Anfang jeder Meldung (Nummer + Kurztitel aus texte.json «kurz»)
  * voll     Filmmaterial vollflaechig mit langsamer Fahrt (B-Roll aus broll/plan.json bzw. Shorts-Suche), kleines
             «Symbolbild», keine Lizenz-Bauchbinde mehr (Attribution steht wie bisher in der Videobeschreibung)
  * satz     der gesprochene Satz als grosse Schrift (Zahlen gelb) auf bewegtem, abgedunkeltem Hintergrund
  * zahl     grosse Zahl + Rest des Satzes, wenn der Satz eine markante Zahl enthaelt
  * zitat    Zitatkarte mit Person/Funktion (texte.json «zitate»), wenn ein «…»-Zitat gesprochen wird
  * quelle   Screenshot des Quellartikels, hoechstens einer je Meldungsbild und QUELLEN_MAX je Folge, nur Domain
  * wort     (Shorts) grosses Stichwort statt Satz - den Satz zeigen dort schon die Untertitel
Hintergrund der Karten: unscharfer Filmclip der Meldung, sonst unscharfer Screenshot, sonst Markenflaeche; er laeuft
ueber aufeinanderfolgende Karten durch (Zeit = Folgenzeit), Wechsel nur an Kapitelgrenzen und alle paar Saetze.
Satzzeiten: Folgen ueber Zeichenanteil je Szenen-WAV, an Sprechpausen eingerastet; Shorts aus dem Whisper-Worttiming.
Nur CPU (ffmpeg libx264, Pillow), keine GPU-Warteschlange noetig.

    python tools/weltlage_bildspur.py karten-probe [--out DIR]     alle Kartentypen als PNG (Sichtpruefung)
"""
from __future__ import annotations

import json
import math
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
W, H, FPS = 1920, 1080, 25
CYAN, ROT, GELB, WEISS = (0, 229, 255), (255, 42, 61), (255, 209, 0), (240, 244, 248)
F_B, F_R, F_I = "C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/segoeuii.ttf"
F_K = "C:/Windows/Fonts/consolab.ttf"
QUELLEN_MAX = 3            # Screenshots je Folge (Marlon 20.11.: zu viele Quellen eingeblendet)
QUELLE_S = 4.5
KAPITEL_S = 3.2
SATZ_MIN_S = 1.6           # kuerzere Saetze werden mit dem naechsten zusammengelegt
SATZ_MAX_Z = 230           # laengere Saetze an einem Komma in zwei Karten teilen
KARTE_MAX_S = 6.5          # laenger steht keine Karte still: der Satz wird auf mehrere Karten verteilt (Zitate bis 12 s)
HG_WECHSEL = 3             # Hintergrund nach so vielen Karten wechseln
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
ZAHL_RE = re.compile(r"(?<![\w])(\d{1,3}(?:['’]\d{3})+|\d+(?:[.,]\d+)?)(\s*(?:Prozent|%|Milliarden|Millionen|Billionen|"
                     r"Tausend|Dollar|Euro|Franken|Kilometer|Tonnen|Jahre|Tage|Stunden|Menschen))?")


MONATE = r"(Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)\b"


def _font(p, g):
    return ImageFont.truetype(p, g)


# ------------------------------------------------------------------ Satzzeiten
def saetze(text: str) -> list[str]:
    roh = []
    for s in (s.strip() for s in re.split(r"(?<=[.!?…])\s+(?=[«\"A-ZÄÖÜ0-9])", text.strip()) if s.strip()):
        if roh and re.search(r"\b\d{1,2}\.$", roh[-1]) and re.match(MONATE, s):   # «Am 8. Dezember» ist kein Satzende
            roh[-1] += " " + s
        else:
            roh.append(s)
    out = []
    for s in roh:
        if len(s) > SATZ_MAX_Z:
            mitte = len(s) // 2
            k = [m.end() for m in re.finditer(r",\s", s)]
            if k:
                c = min(k, key=lambda x: abs(x - mitte))
                if 40 < c < len(s) - 40:
                    out += [s[:c].strip(), s[c:].strip()]
                    continue
        out.append(s)
    return out


def satz_zeiten(text: str, dauer: float, pausen_s: list[float] | None = None) -> list[tuple[float, float, str]]:
    """(t0, t1, satz) relativ zum Szenenanfang: Zeichenanteil, Grenzen auf die naechste Sprechpause (+-0,9 s) gerastet."""
    ss = saetze(text)
    if not ss:
        return []
    n = sum(len(s) for s in ss)
    grenzen, acc = [0.0], 0
    for s in ss[:-1]:
        acc += len(s)
        g = acc / n * dauer
        if pausen_s:
            p = min(pausen_s, key=lambda x: abs(x - g))
            if abs(p - g) < 0.9 and p > grenzen[-1] + 0.5:
                g = p
        grenzen.append(max(g, grenzen[-1] + 0.3))
    grenzen.append(dauer)
    out = [(grenzen[i], grenzen[i + 1], s) for i, s in enumerate(ss)]
    zus = []
    for t0, t1, s in out:                                  # zu kurze Saetze an den vorigen haengen
        if zus and (t1 - t0 < SATZ_MIN_S or zus[-1][1] - zus[-1][0] < SATZ_MIN_S) and len(zus[-1][2]) + len(s) < SATZ_MAX_Z:
            a = zus.pop()
            zus.append((a[0], t1, a[2] + " " + s))
        else:
            zus.append((t0, t1, s))
    return karten_teilen(zus)


def _teilstellen(satz: str, k: int) -> list[str]:
    """Satz in k etwa gleich lange Teile, bevorzugt nach Komma/Doppelpunkt/Gedankenstrich, sonst an Wortgrenzen."""
    woerter = satz.split()
    if k <= 1 or len(woerter) < 2 * k:
        return [satz]
    teile, start = [], 0
    for j in range(1, k):
        ziel = len(satz) * j / k
        pos, kand = 0, []
        for i, w in enumerate(woerter):
            pos += len(w) + 1
            if start < i + 1 < len(woerter) - 1:
                kand.append((abs(pos - ziel) - (25 if re.search(r"[,:;–-]$", w) else 0), i + 1))
        if not kand:
            break
        cut = min(kand)[1]
        teile.append(" ".join(woerter[start:cut]))
        start = cut
    teile.append(" ".join(woerter[start:]))
    return [t for t in teile if t]


def karten_teilen(zeiten: list[tuple[float, float, str]], tiefe: int = 3) -> list[tuple[float, float, str]]:
    out = []
    for t0, t1, satz in zeiten:
        d = t1 - t0
        grenze = 12.0 if "«" in satz else KARTE_MAX_S
        k = math.ceil(d / grenze) if d > grenze else 1
        if "«" in satz and k > 1:                         # Zitat nie zerreissen: lieber Zitat-Teil + Rest
            m = re.search(r"«[^»]*»?", satz)
            stuecke = [x.strip() for x in (satz[:m.start()], satz[m.start():m.end()], satz[m.end():]) if x.strip()]
        else:
            stuecke = _teilstellen(satz, k)
        n = sum(len(x) for x in stuecke) or 1
        t = t0
        for i, x in enumerate(stuecke):
            e = t1 if i == len(stuecke) - 1 else t + d * len(x) / n
            out.append((t, e, x))
            t = e
    # ungleich lange Teile (Kommabevorzugung) koennen noch zu lang sein -> nochmals teilen
    if tiefe and any(b - a > (12.0 if "«" in x else KARTE_MAX_S) and len(x.split()) >= 4 for a, b, x in out):
        return karten_teilen(out, tiefe - 1)
    return out


def satz_zeiten_woerter(text: str, words: list[dict]) -> list[tuple[float, float, str]]:
    """Shorts: Satzgrenzen aus dem Worttiming (words in Reihenfolge von text.split(), weltlage_shorts._woerter_ausgerichtet)."""
    out, i = [], 0
    for s in saetze(text):
        k = len(s.split())
        if i >= len(words):
            break
        a, b = words[i], words[min(i + k, len(words)) - 1]
        out.append((a["s"], b["e"], s))
        i += k
    for j in range(len(out) - 1):                          # Luecken schliessen: Karte steht bis zum naechsten Satz
        out[j] = (out[j][0], out[j + 1][0], out[j][2])
    if out:
        out[0] = (0.0, out[0][1], out[0][2])
    return karten_teilen(out)


def zahl_in(satz: str) -> tuple[str, str] | None:
    """Markante Zahl (keine Jahreszahl/Datum, mind. 3 Zeichen oder mit Einheit) -> (Zahl mit Einheit, Satz)."""
    for m in ZAHL_RE.finditer(satz):
        z, einheit = m.group(1), (m.group(2) or "").strip()
        roh = re.sub(r"\D", "", z)
        if re.fullmatch(r"(19|20)\d\d", z) and not einheit:
            continue
        if re.match(r"\s*\.\s*(Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)",
                    satz[m.end():]):
            continue
        if len(roh) >= 3 or einheit:
            return (f"{z} {einheit}".strip().replace("Prozent", "%").replace(" %", " %"), satz)
    return None


def zitat_in(satz: str, zitate: list[dict]) -> dict | None:
    m = re.search(r"«([^»]{12,})»", satz)
    if not m:
        return None
    q = m.group(1)
    for z in zitate or []:
        d = str(z.get("deutsch") or "")
        if d and (d[:24] in satz or q[:24] in d):
            return {"text": q, "person": z.get("person", ""), "funktion": z.get("funktion", "")}
    return {"text": q, "person": "", "funktion": ""}


# ------------------------------------------------------------------ Karten (PNG 1920x1080 RGBA)
def _zeilen(d: ImageDraw.ImageDraw, text: str, font, breite: int) -> list[str]:
    out, z = [], ""
    for w in text.split():
        p = (z + " " + w).strip()
        if z and d.textlength(p, font=font) > breite:
            out.append(z)
            z = w
        else:
            z = p
    return out + ([z] if z else [])


def _passend(d, text, pfad, groessen, breite, max_zeilen):
    for g in groessen:
        f = _font(pfad, g)
        z = _zeilen(d, text, f, breite)
        if len(z) <= max_zeilen:
            return f, z, g
    f = _font(pfad, groessen[-1])
    return f, _zeilen(d, text, f, breite)[:max_zeilen], groessen[-1]


def _leer() -> Image.Image:
    return Image.new("RGBA", (W, H), (0, 0, 0, 0))


def _abdunkeln(im: Image.Image, box, staerke=150):
    """Weiche dunkle Flaeche hinter dem Text (lesbar auf jedem Hintergrund, ohne harte Kante)."""
    m = Image.new("L", (W, H), 0)
    ImageDraw.Draw(m).rounded_rectangle(box, 40, fill=staerke)
    m = m.filter(ImageFilter.GaussianBlur(60))
    schwarz = Image.new("RGBA", (W, H), (4, 8, 14, 255))
    schwarz.putalpha(m)
    return Image.alpha_composite(im, schwarz)


def _schatten_text(im, xy, text, font, fill, anchor="la"):
    s = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(s).text((xy[0] + 3, xy[1] + 4), text, font=font, fill=(0, 0, 0, 200), anchor=anchor)
    im.alpha_composite(s.filter(ImageFilter.GaussianBlur(5)))
    ImageDraw.Draw(im).text(xy, text, font=font, fill=fill, anchor=anchor)


def _kicker(im, x, y, text):
    if not text:
        return
    d = ImageDraw.Draw(im)
    f = _font(F_K, 30)
    d.rectangle((x, y + 4, x + 8, y + 34), fill=ROT + (255,))
    d.text((x + 22, y), text.upper()[:70], font=f, fill=CYAN + (255,))


def _hervorheben(im, x, y, zeile, font, farbe_basis=WEISS):
    """Zeile Wort fuer Wort zeichnen, Zahlen gelb."""
    d = ImageDraw.Draw(im)
    for i, w in enumerate(zeile.split(" ")):
        teil = (" " if i else "") + w
        col = GELB if re.search(r"\d", w) else farbe_basis
        _schatten_text(im, (x, y), teil, font, col + (255,))
        x += d.textlength(teil, font=font)


def satz_karte(satz: str, kicker: str, out: Path, gross: bool = False) -> Path:
    im = _leer()
    d = ImageDraw.Draw(im)
    breite = 1560
    f, zeilen, g = _passend(d, satz, F_B, (88, 80, 72, 64, 58, 52) if gross else (78, 72, 64, 58, 52, 46), breite, 5)
    lh = int(g * 1.28)
    hoehe = lh * len(zeilen)
    y0 = (H - hoehe) // 2 + 30
    im = _abdunkeln(im, (120, y0 - 110, W - 120, y0 + hoehe + 50))
    _kicker(im, 180, y0 - 80, kicker)
    for i, z in enumerate(zeilen):
        _hervorheben(im, 180, y0 + i * lh, z, f)
    im.save(out)
    return out


def zahl_karte(zahl: str, satz: str, kicker: str, out: Path) -> Path:
    im = _leer()
    d = ImageDraw.Draw(im)
    fz, _, gz = _passend(d, zahl, F_B, (230, 200, 170, 140, 120), 1560, 1)
    f, zeilen, g = _passend(d, satz, F_R, (58, 54, 50, 46), 1540, 3)
    lh = int(g * 1.3)
    gesamt = gz + 40 + lh * len(zeilen)
    y0 = (H - gesamt) // 2 + 20
    im = _abdunkeln(im, (120, y0 - 100, W - 120, y0 + gesamt + 40))
    _kicker(im, 180, y0 - 70, kicker)
    _schatten_text(im, (180, y0 - int(gz * 0.12)), zahl, fz, GELB + (255,))
    for i, z in enumerate(zeilen):
        _schatten_text(im, (184, y0 + gz + 40 + i * lh), z, f, WEISS + (235,))
    im.save(out)
    return out


def zitat_karte(text: str, person: str, funktion: str, out: Path) -> Path:
    im = _leer()
    d = ImageDraw.Draw(im)
    f, zeilen, g = _passend(d, text, F_I, (70, 62, 56, 50, 44), 1440, 5)
    lh = int(g * 1.3)
    hoehe = lh * len(zeilen)
    y0 = (H - hoehe) // 2 - 10
    im = _abdunkeln(im, (120, y0 - 130, W - 120, y0 + hoehe + 120))
    _schatten_text(im, (170, y0 - 150), "«", _font(F_B, 200), CYAN + (255,))
    for i, z in enumerate(zeilen):
        _schatten_text(im, (300, y0 + i * lh), z, f, WEISS + (255,))
    wer = ", ".join(x for x in (person, funktion) if x)
    if wer:
        _schatten_text(im, (300, y0 + hoehe + 30), "— " + wer, _font(F_B, 38), CYAN + (255,))
    im.save(out)
    return out


def kapitel_karte(nr: str, titel: str, out: Path) -> Path:
    im = _leer()
    d = ImageDraw.Draw(im)
    f, zeilen, g = _passend(d, titel, F_B, (104, 92, 82, 72), 1500, 2)
    lh = int(g * 1.2)
    y0 = (H - lh * len(zeilen)) // 2 + 30
    im = _abdunkeln(im, (120, y0 - 150, W - 120, y0 + lh * len(zeilen) + 60), 170)
    d = ImageDraw.Draw(im)
    if nr:
        _schatten_text(im, (180, y0 - 120), nr, _font(F_K, 44), CYAN + (255,))
    d.rectangle((180, y0 - 40, 420, y0 - 32), fill=ROT + (255,))
    for i, z in enumerate(zeilen):
        _schatten_text(im, (176, y0 + i * lh), z, f, WEISS + (255,))
    im.save(out)
    return out


def wort_karte(wort: str, kicker: str, out: Path) -> Path:
    """Shorts: grosses Stichwort (Zahlen gelb) - im 9:16-Band gut lesbar, ohne die Untertitel zu wiederholen."""
    im = _leer()
    d = ImageDraw.Draw(im)
    f, zeilen, g = _passend(d, wort, F_B, (200, 180, 160, 140, 120, 104), 1640, 2)
    lh = int(g * 1.12)
    y0 = (H - lh * len(zeilen)) // 2 + 20
    im = _abdunkeln(im, (100, y0 - 110, W - 100, y0 + lh * len(zeilen) + 50), 160)
    if kicker:
        _kicker(im, int((W - ImageDraw.Draw(im).textlength(kicker.upper()[:70], font=_font(F_K, 30))) / 2) - 22, y0 - 80, kicker)
    for i, z in enumerate(zeilen):
        x = (W - ImageDraw.Draw(im).textlength(z, font=f)) / 2
        _hervorheben(im, x, y0 + i * lh, z, f)
    im.save(out)
    return out


def etikett(text: str, out: Path, gross: int = 26) -> Path:
    """Kleines Etikett unten links («Symbolbild», «Quelle cnbc.com»)."""
    f = _font(F_B, gross)
    tw = int(ImageDraw.Draw(_leer()).textlength(text, font=f))
    im = Image.new("RGBA", (tw + 44, gross + 22), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, tw + 43, gross + 21), 8, fill=(6, 10, 16, 170))
    d.text((22, 8), text, font=f, fill=(225, 232, 240, 230))
    im.save(out)
    return out


def marke_hintergrund(out: Path) -> Path:
    """Markenflaeche 2112x1188: tiefes Blau-Schwarz, weiche Cyan/Rot-Lichter, feines Raster (wird langsam verschoben)."""
    if out.exists():
        return out
    w, h = 2112, 1188
    im = Image.new("RGB", (w, h), (6, 10, 18))
    licht = Image.new("RGB", (w, h), (0, 0, 0))
    d = ImageDraw.Draw(licht)
    d.ellipse((-300, -200, 1100, 900), fill=(0, 70, 90))
    d.ellipse((1300, 500, 2500, 1500), fill=(90, 12, 24))
    licht = licht.filter(ImageFilter.GaussianBlur(220))
    im = Image.blend(im, licht, 0.55)
    d = ImageDraw.Draw(im, "RGBA")
    for x in range(0, w, 96):
        d.line((x, 0, x, h), fill=(0, 229, 255, 10))
    for y in range(0, h, 96):
        d.line((0, y, w, y), fill=(0, 229, 255, 10))
    im.save(out)
    return out


# ------------------------------------------------------------------ Planung
def _hg_quellen(clips: list[str], marke: Path) -> list[dict]:
    """Bewegte Clips der Meldung im Wechsel mit der Markenflaeche (Screenshots sind als Hintergrund zu hell/grau)."""
    q = []
    for c in clips:
        q += [{"typ": "clip", "datei": c}, {"typ": "marke", "datei": str(marke)}]
    return q or [{"typ": "marke", "datei": str(marke)}]


def karte_fuer(satz: str, kicker: str, zitate: list[dict], letzte_art: str | None, work: Path, n: int,
               short: bool = False, stichwort: str | None = None) -> tuple[str, Path]:
    z = zitat_in(satz, zitate)
    if z and not short:
        return "zitat", zitat_karte(z["text"], z["person"], z["funktion"], work / f"k{n:03d}_zitat.png")
    zz = zahl_in(satz)
    if zz and letzte_art != "zahl" and (short or len(satz) <= 150):
        if short:
            return "zahl", wort_karte(zz[0], kicker, work / f"k{n:03d}_zahl.png")
        return "zahl", zahl_karte(zz[0], satz, kicker, work / f"k{n:03d}_zahl.png")
    if short:
        return "wort", wort_karte(stichwort or kicker, "", work / f"k{n:03d}_wort.png")
    return "satz", satz_karte(satz, kicker, work / f"k{n:03d}_satz.png")


def plan_bauen(szenen: list[dict], work: Path, zitate: list[dict] | None = None, short: bool = False) -> list[dict]:
    """szenen: [{t0, dauer, saetze:[(t0,t1,satz)], kicker, kapitel:(nr,titel)|None, clips:[{datei, t, k}],
    bild: png|None, stichworte:[...]}] (Zeiten relativ zur Folge bzw. zur Szene bei saetze/clips.t).
    Ergebnis: Segmente {art, t0, dauer, hg, karte, clip, etikett} lueckenlos ueber die ganze Laenge."""
    work.mkdir(parents=True, exist_ok=True)
    marke = marke_hintergrund(work / "marke.png")
    segs, n, quellen, gezeigt, letzte_art = [], 0, 0, set(), None
    alle_clips = [c["datei"] for s in szenen for c in s.get("clips", [])]
    for sz in szenen:
        T = sz["t0"]
        hgq = _hg_quellen([c["datei"] for c in sz.get("clips", [])] or alle_clips[:1], marke)
        hg_i, karten_seit = 0, 0
        clips = sorted(sz.get("clips", []), key=lambda c: c["t"])
        start_kapitel = sz.get("kapitel")
        quelle_hier = (sz.get("bild") and sz["bild"] not in gezeigt and quellen < QUELLEN_MAX and not short)
        for si, (a, b, satz) in enumerate(sz["saetze"]):
            t, ende = T + a, T + b
            if si == len(sz["saetze"]) - 1:
                ende = T + sz["dauer"]
            stw = (sz.get("stichworte") or [None] * 99)[si] if si < len(sz.get("stichworte") or []) else None

            def karte_seg(t0, t1, art_karte=None):
                nonlocal n, letzte_art, hg_i, karten_seit
                if t1 - t0 < 0.3:
                    return
                if karten_seit >= HG_WECHSEL:
                    hg_i, karten_seit = hg_i + 1, 0
                hg = hgq[hg_i % len(hgq)]
                if art_karte:
                    art, png = art_karte
                else:
                    art, png = karte_fuer(satz, sz.get("kicker", ""), zitate or [], letzte_art, work, n, short, stw)
                segs.append(dict(art=art, t0=round(t0, 3), dauer=round(t1 - t0, 3), hg=hg, karte=str(png)))
                n += 1
                letzte_art = art
                karten_seit += 1

            if si == 0 and start_kapitel:
                k_ende = min(ende, t + KAPITEL_S) if (ende - t) > KAPITEL_S + 2.0 else ende
                karte_seg(t, k_ende, ("kapitel", kapitel_karte(start_kapitel[0], start_kapitel[1], work / f"k{n:03d}_kap.png")))
                t = k_ende
            if quelle_hier and ende - t > 2.0:                # Screenshot gleich nach der Kapitelkarte, einmal je Bild
                q_ende = min(ende, t + QUELLE_S) if (ende - t) > QUELLE_S + 2.0 else ende
                segs.append(dict(art="quelle", t0=round(t, 3), dauer=round(q_ende - t, 3), bild=sz["bild"],
                                 etikett=str(etikett(f"Quelle  {sz.get('domain') or Path(sz['bild']).stem}",
                                                     work / f"e{n:03d}.png"))))
                n += 1
                gezeigt.add(sz["bild"])
                quellen += 1
                t = q_ende
                letzte_art = "quelle"
                quelle_hier = False
            # Filmclip, der in diesen Satz faellt (Startzeit des Clips im Satz oder kurz davor)
            c = next((c for c in clips if a - 1.5 <= c["t"] < b and not c.get("benutzt")), None)
            if c and ende - t > 2.0:
                c["benutzt"] = True
                cl = float(c.get("laenge") or 6.0) - 0.15
                v_ende = min(ende, t + cl)
                if ende - v_ende < 1.4:                    # Rest zu kurz fuer eine Karte -> Clip-Ende halten
                    v_ende = ende if ende - t <= cl + 0.6 else v_ende
                segs.append(dict(art="voll", t0=round(t, 3), dauer=round(v_ende - t, 3), clip=c["datei"],
                                 etikett=str(etikett("Symbolbild", work / f"e{n:03d}.png", 22))))
                n += 1
                letzte_art = "voll"
                t = v_ende
            if ende - t > 0.05:
                karte_seg(t, ende)
    # Blitzkarten (< 1,2 s) flackern nur: dem Vorgaenger zuschlagen
    segs = [x for i, x in enumerate(segs) if i == 0 or x["dauer"] >= 1.2 or x["art"] == "kapitel"]
    # lueckenlos: kleine Rundungsluecken dem Vorgaenger zuschlagen
    for x, y in zip(segs, segs[1:]):
        x["dauer"] = round(y["t0"] - x["t0"], 3)
    return segs


# ------------------------------------------------------------------ Rendern
def _laenge(p: str) -> float:
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p],
                           capture_output=True, text=True, creationflags=NOWIN)
        return float(r.stdout.strip() or 0)
    except Exception:          # noqa: BLE001
        return 0.0


_LAENGEN: dict[str, float] = {}


def _hg_filter(hg: dict, t0: float, d: float, idx: int) -> tuple[list, str]:
    """Eingabe + Filter fuer den bewegten, unscharfen Hintergrund. Zeit = Folgenzeit -> fliessend ueber Karten hinweg."""
    if hg["typ"] == "clip":
        L = _LAENGEN.setdefault(hg["datei"], _laenge(hg["datei"]) or 6.0)
        # Pingpong waere teuer; der Clip laeuft halb so schnell und in Schleife (unscharf faellt der Sprung kaum auf)
        ss = (t0 / 2.0) % max(L - 0.2, 1.0)
        return (["-stream_loop", "-1", "-ss", f"{ss:.3f}", "-i", hg["datei"]],
                f"[{idx}:v]setpts=2.0*PTS,fps={FPS},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                f"gblur=sigma=22,eq=brightness=-0.20:saturation=0.75")
    z = 1.10
    cw, ch = int(W * z), int(H * z)
    # langsame Lissajous-Drift ueber die Folgenzeit
    x = f"'{(cw - W) / 2:.0f}+{(cw - W) / 2 - 4:.0f}*sin((t+{t0:.3f})/9)'"
    y = f"'{(ch - H) / 2:.0f}+{(ch - H) / 2 - 4:.0f}*cos((t+{t0:.3f})/13)'"
    blur = "gblur=sigma=26,eq=brightness=-0.25:saturation=0.7," if hg["typ"] == "bild" else ""
    return (["-loop", "1", "-framerate", str(FPS), "-i", hg["datei"]],
            f"[{idx}:v]scale={cw}:{ch}:force_original_aspect_ratio=increase,crop={cw}:{ch},{blur}"
            f"crop={W}:{H}:{x}:{y}")


def _cover(f, w=W, h=H):
    import cv2
    sh, sw = f.shape[:2]
    k = max(w / sw, h / sh)
    f = cv2.resize(f, (max(w, round(sw * k)), max(h, round(sh * k))), interpolation=cv2.INTER_AREA if k < 1 else cv2.INTER_CUBIC)
    y, x = (f.shape[0] - h) // 2, (f.shape[1] - w) // 2
    return f[y:y + h, x:x + w]


def _quelle_bild(png: str):
    """Screenshot (oberer Teil, cyan Rahmen) mittig auf seiner eigenen, unscharf abgedunkelten Flaeche."""
    import cv2
    import numpy as np
    roh = cv2.imdecode(np.fromfile(png, np.uint8), cv2.IMREAD_COLOR)
    hg = cv2.GaussianBlur(_cover(roh), (0, 0), 28)
    hg = (cv2.cvtColor(cv2.cvtColor(hg, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR) * 0.4 + hg * 0.6) * 0.62
    fw = 1240
    fg = cv2.resize(roh, (fw, round(roh.shape[0] * fw / roh.shape[1])), interpolation=cv2.INTER_AREA)[:740]
    fg = cv2.copyMakeBorder(fg, 3, 3, 3, 3, cv2.BORDER_CONSTANT, value=(255, 229, 0))
    y, x = (H - fg.shape[0]) // 2 - 20, (W - fg.shape[1]) // 2
    hg[y:y + fg.shape[0], x:x + fg.shape[1]] = fg
    return np.clip(hg, 0, 255).astype(np.uint8)


def fahrt_rendern(seg: dict, d: float, out: Path, ffmpeg: str = "ffmpeg") -> Path:
    """Langsame, gleichmaessige Kamerafahrt (Zoom zur Mitte) subpixelgenau mit warpAffine. ffmpeg-zoompan rundet den
    Ausschnitt auf ganze Pixel: gemessen sprang die Zoomrate je Bild zwischen 0,2 und 0,67 px (sichtbares Ruckeln)."""
    import cv2
    nf = max(1, int(round(d * FPS)))
    z_end = 0.06 if seg["art"] == "voll" else 0.035
    cap, still = None, None
    if seg["art"] == "voll":
        cap = cv2.VideoCapture(seg["clip"])
    else:
        still = _quelle_bild(seg["bild"])
    p = subprocess.Popen([ffmpeg, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(FPS),
                          "-i", "-", "-c:v", "libx264", "-crf", "14", "-preset", "fast", "-pix_fmt", "yuv420p", str(out)],
                         stdin=subprocess.PIPE, creationflags=NOWIN)
    letzt = None
    for i in range(nf):
        if cap is not None:
            ok, f = cap.read()
            f = _cover(f) if ok else letzt                 # Clip zu kurz: letztes Bild halten
            letzt = f
        else:
            f = still
        z = 1.0 + z_end * i / max(1, nf - 1)
        M = cv2.getRotationMatrix2D((W / 2, H / 2), 0, z)
        p.stdin.write(cv2.warpAffine(f, M, (W, H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT).tobytes())
    if cap is not None:
        cap.release()
    p.stdin.close()
    if p.wait():
        raise RuntimeError(f"Fahrt {out.name} fehlgeschlagen")
    return out


def segment_rendern(seg: dict, out: Path, ffmpeg: str = "ffmpeg", overlays: list[tuple[Path, str]] | None = None) -> Path:
    """overlays: zusaetzliche PNGs mit Position (Uhr, Logo), z.B. [(png, "x=(W-w)/2:y=14")]."""
    d, art = seg["dauer"], seg["art"]
    inp, fc = [ffmpeg, "-v", "error", "-y"], []
    if art in ("voll", "quelle"):
        fahrt = out.with_name(out.stem + "_fahrt.mp4")
        fahrt_rendern(seg, d, fahrt, ffmpeg)
        inp += ["-i", str(fahrt)]
        fc.append("[0:v]null[b0]")
    else:
        i_hg, f_hg = _hg_filter(seg["hg"], seg["t0"], d, 0)
        inp += i_hg
        inp += ["-loop", "1", "-framerate", str(FPS), "-i", seg["karte"]]
        fc.append(f_hg + "[hg]")
        fade = "fade=t=in:st=0:d=0.35:alpha=1" + (f",fade=t=out:st={d - 0.35:.3f}:d=0.35:alpha=1" if art == "kapitel" else "")
        fc.append(f"[1:v]format=rgba,{fade}[k]")
        fc.append("[hg][k]overlay=0:0[b0]")
    cur, idx = "b0", sum(1 for x in inp if x == "-i")
    if seg.get("etikett"):
        inp += ["-loop", "1", "-framerate", str(FPS), "-i", seg["etikett"]]
        fc.append(f"[{cur}][{idx}:v]overlay=48:H-h-44[e]")
        cur, idx = "e", idx + 1
    for j, (png, pos) in enumerate(overlays or []):
        inp += ["-loop", "1", "-framerate", str(FPS), "-i", str(png)]
        en = ""
        if "|" in pos:
            pos, en = pos.split("|", 1)
            en = f":enable='{en}'"
        fc.append(f"[{cur}][{idx}:v]overlay={pos}{en}[o{j}]")
        cur, idx = f"o{j}", idx + 1
    fc.append(f"[{cur}]format=yuv420p[out]")
    cmd = inp + ["-filter_complex", ";".join(fc), "-map", "[out]", "-t", f"{d:.3f}", "-r", str(FPS),
                 "-c:v", "libx264", "-crf", "18", "-preset", "fast", "-threads", "4", "-an", str(out)]
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, creationflags=NOWIN)
    if r.returncode:
        raise RuntimeError(f"Segment {out.name} ({art}): {r.stderr[-800:]}")
    return out


def alle_rendern(segs: list[dict], work: Path, ffmpeg: str = "ffmpeg", overlays_je=None, parallel: int = 3,
                 log=print) -> list[Path]:
    """overlays_je(seg) -> Liste (png, pos) je Segment (z.B. Uhr mit Minutenwechsel). Gibt die Segmentdateien zurueck."""
    def eins(i_s):
        i, s = i_s
        o = work / f"bseg{i:03d}.mp4"
        segment_rendern(s, o, ffmpeg, overlays_je(s) if overlays_je else None)
        return o
    with ThreadPoolExecutor(parallel) as ex:
        teile = list(ex.map(eins, enumerate(segs)))
    log(f"Bildspur: {len(teile)} Segmente gerendert")
    return teile


def zusammenfuegen(teile: list[Path], out: Path, ffmpeg: str = "ffmpeg") -> Path:
    lst = out.with_suffix(".txt")
    lst.write_text("\n".join(f"file '{p.as_posix()}'" for p in teile), encoding="utf-8")
    r = subprocess.run([ffmpeg, "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)],
                       capture_output=True, text=True, creationflags=NOWIN)
    if r.returncode:
        raise RuntimeError(f"concat: {r.stderr[-800:]}")
    return out


def statistik(segs: list[dict]) -> dict:
    from collections import Counter
    c = Counter(s["art"] for s in segs)
    dauer = {}
    for s in segs:
        dauer[s["art"]] = round(dauer.get(s["art"], 0) + s["dauer"], 1)
    return {"segmente": len(segs), "arten": dict(c), "sekunden": dauer}


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["karten-probe"])
    ap.add_argument("--out", default=str(ROOT / "output" / "bildspur_karten"))
    a = ap.parse_args()
    o = Path(a.out)
    o.mkdir(parents=True, exist_ok=True)
    satz_karte("Das Handelsministerium hat 879'000 KI-Chips für chinesische Firmen genehmigt, teils mit Verbindungen "
               "zum Militär.", "Was der Kongress offenlegt", o / "satz.png")
    zahl_karte("879'000", "KI-Chips hat das Handelsministerium für chinesische Firmen genehmigt.", "Exportlizenzen", o / "zahl.png")
    zitat_karte("Es war eine grossartige und höchst folgenreiche Reise.", "Donald Trump", "Präsident der USA", o / "zitat.png")
    kapitel_karte("1 / 8", "Was der Kongress plötzlich offenlegt", o / "kapitel.png")
    wort_karte("879'000 KI-Chips", "Exportlizenzen", o / "wort.png")
    print(json.dumps({"out": str(o)}))


if __name__ == "__main__":
    main()
