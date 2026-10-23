"""Weltlage Kompakt - Eilmeldungs-Thumbnail (Marlons Auftrag 21.10.2026, Vorlage: heller Hintergrund, roter Balken).

Layout (1280x720 Langvideo/Livestream, 1080x1920 Short mit sicherer Mittelzone): heller Hintergrund, oben roter
Balken mit weisser Grossschrift (Label), darunter zwei Zeilen dunkle Schlagzeile mit Ausrufezeichen, unten links ein
lizenzsicheres Pressefoto mit rotem geschwungenem Pfeil, rechts gross Latara (Pool-Foto «geschockt», keine echte
Person).

Foto-Quellen nur lizenzsicher: Wikimedia Commons (CC0/PD/CC BY/CC BY-SA, geprueft mit den Regeln und der Sperrliste
von tools/weltlage_broll.py) und Pexels. Attribution landet in <ordner>/thumbnails/thumbnail_quelle.json und wird von
tageslauf.metadaten in die Beschreibung uebernommen. Ohne passendes Foto: Layout ohne Foto-Feld (Latara gross), nie
ein unlizenziertes Bild. Keine Gewaltbilder (Textfilter GEWALT).

Ehrlichkeit: Label «EILMELDUNG!» nur bei frischem Ereignis (label_waehlen), sonst ein anderes Schock-Label (nie «Weltlage»).

    python -m video.weltlage_thumbnail_eil out.jpg "LABEL" "ZEILE 1" "ZEILE 2" [suchbegriff] [--short]
"""
from __future__ import annotations

import html
import json
import math
import re
import sys
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from video import latara_foto  # noqa: E402

FONTS = Path(r"C:\Windows\Fonts")
ROT, DUNKEL, WEISS, HELL = (222, 30, 40), (22, 30, 48), (255, 255, 255), (244, 247, 250)
UA = "WeltlageKompakt-Thumbnail/1.0 (newsroom; info@iota-plus.com)"
GEWALT = re.compile(r"\b(blood|bloody|corpse|dead body|body|bodies|killed|wounded|injured|victim|gore|execution|"
                    r"massacre|leiche|toter|tote|verletzt|opfer|enthaupt|hinricht|nude|naked)\b", re.I)
# Pool-Foto: Gesicht erschrocken, Haende erhoben (ein Haende-vor-dem-Mund-Bild gibt es im Pool nicht)
POOL_BEVORZUGT = "latara_front_stehend_geschockt_hände.png"


def _font(name: str, size: int):
    for n in (name, "arialbd.ttf"):
        if (FONTS / n).exists():
            return ImageFont.truetype(str(FONTS / n), size)
    return ImageFont.load_default(size=size)


# Schock-Labels (Marlon 21.10.2026): im roten Balken und am Titelanfang steht NIE «Weltlage», sondern ein Schock-Label.
# Regeln statt LLM (deterministisch, kein Ausfall); Rotation ueber die letzten Labels, damit es nicht immer gleich ist.
LABELS_THEMA = [
    (r"eskalat|angriff|krieg|rakete|truppen|milit|waffen|drohne|bomb|invasion",
     ["ESKALATION!", "ES GEHT LOS!", "ALARM!"]),
    (r"offiziell|best[aä]tigt|beschlo|abkommen|sanktion|entscheid|pr[aä]sident|regierung|wahl|gesetz|vertrag",
     ["JETZT OFFIZIELL!", "ES IST SOWEIT!", "ACHTUNG!"]),
    (r"b[oö]rse|crash|inflation|zins|[oö]l|gas|dollar|wirtschaft|schulden|pleite|bank",
     ["SCHOCK!", "ALARM!", "ACHTUNG!"]),
]
LABELS_ALLGEMEIN = ["SCHOCK!", "ALARM!", "ACHTUNG!", "ES GEHT LOS!"]
LABEL_EIL = "EILMELDUNG!"
LABEL_HISTORIE = ROOT / "state" / "eil_labels.json"


def _historie() -> list[str]:
    try:
        return list(json.loads(LABEL_HISTORIE.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return []


def _merken(label: str) -> None:
    try:
        LABEL_HISTORIE.parent.mkdir(parents=True, exist_ok=True)
        LABEL_HISTORIE.write_text(json.dumps((_historie() + [label])[-8:], ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def label_waehlen(stimmung_text: str, frisch: bool, historie: list[str] | None = None) -> str:
    """Schock-Label zum Thema, abwechselnd. EILMELDUNG! nur bei wirklich frischem Ereignis (frisch=True, < 24 h;
    hoechstens zweimal hintereinander), sonst ein anderes Label. Nie «Weltlage». Nur Auswahl, keine Aussage ueber
    Ereignisse - inhaltlich wahr bleibt die Zeile darunter."""
    hist = _historie() if historie is None else historie
    text = (stimmung_text or "").lower()
    kand: list[str] = []
    if frisch and hist[-2:] != [LABEL_EIL, LABEL_EIL]:
        return LABEL_EIL
    for muster, labels in LABELS_THEMA:
        if re.search(muster, text):
            kand += labels
    kand += LABELS_ALLGEMEIN
    kand = list(dict.fromkeys(kand))
    # am laengsten nicht benutzt zuerst (Themen-Reihenfolge bleibt Tie-Break)
    return min(kand, key=lambda l: (hist[::-1].index(l) * -1 if l in hist else -99, kand.index(l)))


def label_fuer(ordner: Path | None, stimmung_text: str, frisch: bool) -> str:
    """Ein Label je Folge: Thumbnail und Titel nutzen dasselbe (gemerkt in <ordner>/thumbnails/eil_label.json)."""
    datei = Path(ordner) / "thumbnails" / "eil_label.json" if ordner is not None else None
    if datei is not None and datei.exists():
        try:
            return json.loads(datei.read_text(encoding="utf-8"))["label"]
        except (OSError, ValueError, KeyError):
            pass
    label = label_waehlen(stimmung_text, frisch)
    _merken(label)
    if datei is not None:
        try:
            datei.parent.mkdir(parents=True, exist_ok=True)
            datei.write_text(json.dumps({"label": label, "frisch": frisch}, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
    return label


def titel_mit_label(titel: str, label: str) -> str:
    """Label an den Titelanfang (ohne «!»-Doppelung, max. 100 Zeichen); alte Praefixe BREAKING:/WELTLAGE entfernt."""
    t = re.sub(r"^\s*(breaking|weltlage( kompakt)?)\s*[:!\-–]\s*", "", titel or "", flags=re.I).strip()
    if t.upper().startswith(label.upper()):
        return t[:100]
    return f"{label} {t}"[:100].rstrip()


# ---------------------------------------------------------------- Pressefoto
def _lizenz_ok(k: dict) -> str | None:
    from tools import weltlage_broll as b
    if k["quelle"] != "pexels":
        liz = (k.get("lizenz") or "").strip()
        if not liz or not b.LIZENZ_OK.match(liz) or re.search(r"\b(nc|nd)\b", liz.lower()):
            return f"Lizenz nicht zugelassen ({liz or 'fehlt'})"
        if k.get("einschraenkung") or k.get("nonfree"):
            return "Einschraenkung/nicht frei"
    grund = b.gesperrt(k.get("herkunftstext", ""))
    if grund:
        return grund
    if GEWALT.search(k.get("herkunftstext", "")):
        return "Gewaltbezug"
    if re.search(r"\.(png|svg|gif)(\?|$)", str(k.get("datei") or "").lower()):
        return "PNG/SVG = meist Screenshot oder Grafik, kein Foto"
    if re.search(r"\b(kill|funeral|death|dead|burn|bomb|terror|weapon|screenshot|truth social|tweet|twitter|facebook|instagram|social media|logo|map)\b|\.svg",
                 _flach(k.get("titel"))):
        return "Screenshot/Social-Media/Grafik statt Foto"
    if (k.get("breite") or 0) < 900:
        return "Aufloesung zu klein"
    return None


def _themenbezug(q: str, k: dict) -> bool:
    """Foto muss zum Thema passen (kein irrefuehrendes Bild): bei <=2 Suchwoertern (>3 Zeichen) alle, sonst 2/3
    steht in Titel/Beschreibung/Kategorien des Fotos."""
    w = [x for x in re.split(r"\W+", q.lower()) if len(x) > 3]
    if not w:
        return False
    text = _flach(k.get("titel"), k.get("herkunftstext"))
    treffer = sum(1 for x in w if re.search(r"(?<![a-z0-9])" + re.escape(x), text))
    return treffer >= (len(w) if len(w) <= 2 else math.ceil(len(w) * 2 / 3))


def _flach(*t) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html.unescape(str(x or ""))) for x in t).lower()


def such_commons_bild(q: str) -> list[dict]:
    import httpx
    r = httpx.get("https://commons.wikimedia.org/w/api.php", params=dict(
        action="query", format="json", generator="search", gsrsearch=f"{q} filetype:bitmap", gsrnamespace=6,
        gsrlimit=20, prop="imageinfo|categories", cllimit=30, iiprop="url|size|mime|extmetadata",
        iiurlwidth=1600), headers={"User-Agent": UA}, timeout=30)
    out = []
    for p in (r.json().get("query", {}).get("pages", {}) or {}).values() if r.status_code == 200 else []:
        ii = (p.get("imageinfo") or [{}])[0]
        if not str(ii.get("mime", "")).startswith(("image/jpeg", "image/png")):
            continue
        em = {k: (v or {}).get("value", "") for k, v in (ii.get("extmetadata") or {}).items()}
        kats = " ".join(c.get("title", "") for c in p.get("categories", []))
        titel = re.sub(r"^File:|\.(jpe?g|png)$", "", p.get("title", ""), flags=re.I)
        out.append({"quelle": "commons", "id": f"commons-{p.get('pageid')}", "titel": titel,
                    "seite": ii.get("descriptionurl"), "datei": ii.get("thumburl") or ii.get("url"),
                    "breite": ii.get("thumbwidth") or ii.get("width"), "hoehe": ii.get("thumbheight") or ii.get("height"),
                    "urheber": _flach(em.get("Artist")).strip()[:120] or "unbekannt",
                    "lizenz": html.unescape(em.get("LicenseShortName", "")), "lizenz_url": em.get("LicenseUrl", ""),
                    "einschraenkung": _flach(em.get("Restrictions")).strip(), "nonfree": em.get("NonFree") == "true",
                    "herkunftstext": _flach(em.get("Artist"), em.get("Credit"), em.get("ImageDescription"), kats,
                                            p.get("title"))})
    return out


def such_pexels_bild(q: str, key: str) -> list[dict]:
    import httpx
    r = httpx.get("https://api.pexels.com/v1/search", params={"query": q, "orientation": "landscape", "per_page": 12},
                  headers={"Authorization": key, "User-Agent": UA}, timeout=30)
    out = []
    for v in r.json().get("photos", []) if r.status_code == 200 else []:
        src = (v.get("src") or {}).get("large2x") or (v.get("src") or {}).get("large")
        if not src:
            continue
        alt = v.get("alt") or ""
        out.append({"quelle": "pexels", "id": f"pexels-{v['id']}", "titel": alt, "seite": v.get("url"), "datei": src,
                    "breite": v.get("width"), "hoehe": v.get("height"), "urheber": v.get("photographer", ""),
                    "lizenz": "Pexels License", "lizenz_url": "https://www.pexels.com/license/",
                    "herkunftstext": f"{alt} {v.get('photographer', '')}".lower()})
    return out


def attribution_zeile(k: dict) -> str:
    if k["quelle"] == "og":
        return f"Thumbnail-Foto: Quellbild von {k['urheber']} ({k['seite']}), {k['lizenz']}"
    if k["quelle"] == "broll":
        return f"Thumbnail-Standbild aus B-Roll: «{k['titel']}» von {k.get('urheber', '')}, {k['lizenz']} ({k.get('seite', '')})"
    if k["quelle"] == "pexels":
        return f"Thumbnail-Foto: {k['urheber']} auf Pexels ({k['seite']}), Pexels-Lizenz"
    return (f"Thumbnail-Foto: «{k['titel']}» von {k['urheber']}, {k['lizenz']}"
            + (f" ({k['lizenz_url']})" if k.get("lizenz_url") else "") + f", via Wikimedia Commons ({k['seite']})")


def pressefoto(begriffe: list[str], log=print, ok=lambda fid: True) -> tuple[Image.Image, dict] | None:
    """Erstes lizenzsicheres Foto zu den Suchbegriffen. None = nichts Sicheres gefunden. ok(id) = Merkliste."""
    import httpx
    from tools import weltlage_broll as b
    key = (b.keys() or {}).get("pexels") or ""
    for q in begriffe:
        q = q.strip()
        if not q:
            continue
        kand = []
        try:
            kand += such_commons_bild(q)
        except Exception as e:   # noqa: BLE001
            log(f"Foto: Commons-Suche '{q}' Fehler {type(e).__name__}")
        if key:
            try:
                kand += such_pexels_bild(q, key)
            except Exception as e:   # noqa: BLE001
                log(f"Foto: Pexels-Suche '{q}' Fehler {type(e).__name__}")
        for k in kand:
            if _lizenz_ok(k) or not _themenbezug(q, k) or not ok(k["id"]):
                continue
            try:
                r = httpx.get(k["datei"], headers={"User-Agent": UA}, timeout=40, follow_redirects=True)
                im = Image.open(BytesIO(r.content)).convert("RGB")
            except Exception:   # noqa: BLE001
                continue
            if im.width < 900 or im.width < im.height * 0.9:
                continue
            log(f"Foto: {k['id']} ({q})")
            return im, k
    return None


# ---------------------------------------------------------------- Zeichnen
def _pfeil(d: ImageDraw.ImageDraw, start, ende, ctrl, breite: int):
    """Dicker roter geschwungener Pfeil: quadratische Bezier-Kurve mit Spitze."""
    pts = []
    for i in range(41):
        t = i / 40
        pts.append(((1 - t) ** 2 * start[0] + 2 * (1 - t) * t * ctrl[0] + t ** 2 * ende[0],
                    (1 - t) ** 2 * start[1] + 2 * (1 - t) * t * ctrl[1] + t ** 2 * ende[1]))
    for i in range(40):
        w = max(4, int(breite * (0.35 + 0.65 * i / 40)))
        d.line([pts[i], pts[i + 1]], fill=ROT, width=w)
        d.ellipse((pts[i][0] - w / 2, pts[i][1] - w / 2, pts[i][0] + w / 2, pts[i][1] + w / 2), fill=ROT)
    a = math.atan2(ende[1] - pts[-4][1], ende[0] - pts[-4][0])
    L = breite * 1.6
    spitze = (ende[0] + math.cos(a) * L, ende[1] + math.sin(a) * L)
    l = (ende[0] + math.cos(a + 1.57) * L * 0.8, ende[1] + math.sin(a + 1.57) * L * 0.8)
    r = (ende[0] + math.cos(a - 1.57) * L * 0.8, ende[1] + math.sin(a - 1.57) * L * 0.8)
    d.polygon([spitze, l, r], fill=ROT)


def _latara_bild(hoehe: int, breite_max: int) -> Image.Image:
    pfad = latara_foto.ORDNER / POOL_BEVORZUGT
    if not pfad.exists():
        from video.weltlage_thumbnail import ASSETS
        pfad = ASSETS / "latara_schock.png"
    im = Image.open(pfad).convert("RGBA")
    # Leuchten rund um den Freisteller weg: nur stark deckende Pixel behalten
    a = im.split()[3].point(lambda v: 0 if v < 200 else 255).filter(ImageFilter.MinFilter(3)).filter(
        ImageFilter.GaussianBlur(1.2))
    im.putalpha(a)
    bbox = a.point(lambda v: 255 if v > 128 else 0).getbbox()
    if bbox:
        h = bbox[3] - bbox[1]
        im = im.crop((bbox[0], bbox[1], bbox[2], bbox[1] + int(h * 0.46)))   # Kopf, Oberkoerper, Haende
    f = min(hoehe / im.height, breite_max / im.width)
    return im.resize((round(im.width * f), round(im.height * f)), Image.LANCZOS)


def _passend(d, text, name, start, breite, minimum=40):
    size = start
    f = _font(name, size)
    while d.textlength(text, font=f) > breite and size > minimum:
        size -= 3
        f = _font(name, size)
    return f, size


def _foto_feld(bild: Image.Image, foto: Image.Image, box):
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    s = max(w / foto.width, h / foto.height)
    f = foto.resize((round(foto.width * s), round(foto.height * s)), Image.LANCZOS)
    f = f.crop(((f.width - w) // 2, (f.height - h) // 2, (f.width - w) // 2 + w, (f.height - h) // 2 + h))
    bild.paste(f, (x0, y0))
    ImageDraw.Draw(bild).rectangle(box, outline=WEISS, width=4)


def _kopf(d, x0, x1, y, label, hoehe, start):
    d.rectangle((x0, y, x1, y + hoehe), fill=ROT)
    fl, _ = _passend(d, label, "impact.ttf", start, x1 - x0 - 40)
    tw = d.textlength(label, font=fl)
    d.text((x0 + (x1 - x0 - tw) / 2, y + 4), label, font=fl, fill=WEISS)


def render(label: str, zeile1: str, zeile2: str, out: Path, foto: Image.Image | None = None,
           short: bool = False) -> Path:
    label = label.upper()
    if short:
        return _render_short(label, zeile1, zeile2, out, foto)
    W, H = 1280, 720
    bild = Image.new("RGB", (W, H), HELL)
    d = ImageDraw.Draw(bild)
    d.rounded_rectangle((18, 18, W - 18, H - 18), radius=34, fill=WEISS)
    _kopf(d, 42, 800, 48, label, 142, 118)
    ty = 206
    for t in (zeile1.upper().strip(), zeile2.upper().strip()):
        if not t:
            continue
        f, size = _passend(d, t, "arialbd.ttf", 58, 740)
        tw = d.textlength(t, font=f)
        d.text((42 + (758 - tw) / 2, ty), t, font=f, fill=DUNKEL, stroke_width=1, stroke_fill=DUNKEL)
        ty += int(size * 1.15)
    if foto is not None:
        _foto_feld(bild, foto, (170, 378, 740, 688))
        _pfeil(ImageDraw.Draw(bild), (70, 380), (200, 580), (35, 545), 28)
    lat = _latara_bild(620, 540)
    rgba = bild.convert("RGBA")
    rgba.alpha_composite(lat, (W - lat.width - 6, H - 28 - lat.height))
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    rgba.convert("RGB").save(out, quality=92)
    return out


def _render_short(label, zeile1, zeile2, out, foto) -> Path:
    W, H = 1080, 1920
    SAFE_TOP, SAFE_UNTEN = 320, 1600   # wie tools/weltlage_shorts_thumbnail.py
    bild = Image.new("RGB", (W, H), HELL)
    d = ImageDraw.Draw(bild)
    d.rounded_rectangle((20, SAFE_TOP - 40, W - 20, SAFE_UNTEN + 40), radius=40, fill=WEISS)
    y = SAFE_TOP
    _kopf(d, 50, W - 50, y, label, 150, 118)
    y += 180
    for t in (zeile1.upper().strip(), zeile2.upper().strip()):
        if not t:
            continue
        f, size = _passend(d, t, "arialbd.ttf", 78, W - 130)
        tw = d.textlength(t, font=f)
        d.text(((W - tw) / 2, y), t, font=f, fill=DUNKEL, stroke_width=1, stroke_fill=DUNKEL)
        y += int(size * 1.18)
    y += 20
    foto_h = 400
    if foto is not None:
        _foto_feld(bild, foto, (80, y, W - 80, y + foto_h))
        _pfeil(ImageDraw.Draw(bild), (W - 120, y + foto_h + 70), (W - 330, y + foto_h - 60), (W - 90, y + foto_h - 20), 24)
    y += foto_h + 10
    lat = _latara_bild(SAFE_UNTEN - y, W - 160)
    rgba = bild.convert("RGBA")
    rgba.alpha_composite(lat, ((W - lat.width) // 2, SAFE_UNTEN - lat.height))
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    rgba.convert("RGB").save(out, quality=92)
    return out


# ---------------------------------------------------------------- Einstieg Pipeline
MEHRDEUTIG = {"wanze", "waren", "bruch", "minen", "wahl", "brand", "trumps", "gegen", "inflation", "jagd", "druck",
              "krise", "kampf", "streit", "deal", "macht", "angst"}


def _begriffe(felder: dict) -> list[str]:
    roh = re.sub(r"[!?.,:;]", " ", " ".join(str(felder.get(k) or "") for k in ("zeile1", "zeile2")))
    w = [x for x in roh.split() if len(x) > 3]
    # Einzelwoerter nur ohne mehrdeutige Alltagswoerter (Beispiel «Wanze» = Insekt statt Abhoergeraet)
    ein = [x for x in w[:3] if x.lower() not in MEHRDEUTIG and (x[0].isupper() or len(w) <= 1)]
    return [" ".join(w[:3]), " ".join(w[:2]), *ein]


def baue(felder: dict, out: Path, *, short: bool = False, frisch: bool = False, ordner: Path | None = None,
         suche: list[str] | None = None, log=print) -> Path:
    """felder: zeile1/zeile2/banderole/stimmungstext. Schreibt die Attribution nach <ordner>/thumbnails/
    thumbnail_quelle[_short].json (nur wenn ein Foto verwendet wurde)."""
    label = label_fuer(ordner, felder.get("stimmungstext") or "", frisch)
    titel = felder.get("titel") or f"{felder.get('zeile1', '')} {felder.get('zeile2', '')}"
    if suche is None and ordner is not None:   # seit 23.10.2026: Quellbild > lizenzfrei > B-Roll, Merkliste
        from video import weltlage_thumbnail_bild as tb
        gef = tb.waehle(titel, ordner, felder.get("szene") or ("short" if short else "lang"),
                        int(felder.get("short_nr") or 1), log=log)
    else:
        gef = pressefoto(suche or _begriffe(felder), log=log)
    foto, k = gef if gef else (None, None)
    z1, z2 = (felder.get("zeile1") or "").strip(), (felder.get("zeile2") or "").strip()
    if z2 and not z2.endswith(("!", "?")):
        z2 += "!"
    elif not z2 and z1 and not z1.endswith(("!", "?")):
        z1 += "!"
    res = render(label, z1, z2, out, foto, short)
    if ordner is not None:
        q = Path(ordner) / "thumbnails" / ("thumbnail_quelle_short.json" if short else "thumbnail_quelle.json")
        q.parent.mkdir(parents=True, exist_ok=True)
        if k:
            q.write_text(json.dumps({"id": k["id"], "stufe": k.get("stufe"), "attribution": attribution_zeile(k), "label": label},
                                    ensure_ascii=False, indent=1), encoding="utf-8")
        elif q.exists():
            q.unlink()
    return res


def live_thumbnail(out: Path, stimmung_text: str = "") -> str:
    """Livestream-Thumbnail im Eil-Stil (Programm laeuft dauernd, kein einzelnes frisches Ereignis -> nie EILMELDUNG,
    Zeilen sagen nur, was der Stream ist). Gibt das gewaehlte Label zurueck."""
    label = label_waehlen(stimmung_text, False)
    _merken(label)
    render(label, "NACHRICHTEN LIVE", "KRIEG & POLITIK JETZT!", Path(out), None, False)
    return label


if __name__ == "__main__":
    if sys.argv[1:2] == ["--live"]:
        print(live_thumbnail(Path(sys.argv[2]), " ".join(sys.argv[3:])))
        sys.exit(0)
    a = [x for x in sys.argv[1:] if x != "--short"]
    felder = {"zeile1": a[2], "zeile2": a[3], "stimmungstext": a[1]}
    print(baue(felder, Path(a[0]), short="--short" in sys.argv, frisch=a[1].upper().startswith("EIL"),
               suche=[a[4]] if len(a) > 4 else None))
