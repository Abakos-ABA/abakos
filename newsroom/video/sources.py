"""Source proof for the screen: a screenshot of the reporting outlet's article (its own headline,
its own masthead) rendered into a "QUELLE" card - shown when the host introduces the topic, so
every story visibly points at who reported it. The same URLs go into the video description.

Screenshots are taken headless with Playwright (Edge, plain context, no login), viewport 1280x900,
cropped to the article's own content container (its headline down to the end of the body, up to
MAX_ARTIKEL_HOEHE), not a fixed-size window below the headline. Sites that block or time out, or
whose crop shows too little headline/lead text (MIN_HEADLINE_TEXT - Marlon 04.10.2026: france24.com
kept showing only its big title photo, no readable headline/text on some articles; corrected
04.10.2026: no domain is blocked outright, the per-screenshot text-amount check alone decides, so a
france24.com article with a real headline+lead still gets its card), simply yield no card - the
video falls back to the illustrated cutaway, never fails. Cookie banners are dismissed best-effort
by clicking the usual consent buttons.

Marlon 08.10.2026: a recurring bug kept slipping one bad screenshot per episode into the "QUELLE"
card - zoomed into a single line or a random excerpt (wrong scroll position/crop, a banner or the
navigation instead of the article) rather than showing the whole article from its own headline. Root
cause: the old crop was built from the headline box plus up to 520px of the following <p> boxes (a
feature of the page's DOM, easy to pick a navigation widget or a stray short paragraph by accident)
and was clamped to the 900px viewport height - nowhere near "the whole article". Fixed by capturing
the page's own `article`/`main` content container directly (the element that already holds the
headline on virtually every outlet's markup, siblings like nav/ads are not inside it) from its own
top, scrolling through it first so lazy-loaded paragraphs are rendered, and by self-checking every
capture with struktur_probleme() (resolution, aspect ratio - a thin strip is the "one line" bug -,
and a text-similarity match between the found headline and the article's own known title) before it
is ever accepted. The same struktur_probleme() check runs again in tools/weltlage_abnahme.py right
before a finished episode may ship - one function, two call sites, so neither can drift out of sync.
"""
import json
import logging
import re
from pathlib import Path

from PIL import Image, ImageStat

from config.settings import DATA_DIR, NEWS_PLAYWRIGHT_CHANNEL

logger = logging.getLogger(__name__)

MAX_SOURCES = 3
CONSENT_TEXTS = ["Alle akzeptieren", "Akzeptieren", "Zustimmen", "Accept all", "Accept All", "I Accept", "Accept",
                 "Agree", "I agree", "Yes, I agree", "Got it", "OK", "Allow all", "Continue"]
HEADLINE_SEL = "article h1, main h1, h1"
LEAD_SEL = "article p, main p, p"
MIN_HEADLINE_TEXT = 60                # Schlagzeile + Lead-Absatz im Ausschnitt muessen zusammen mindestens so viele
                                       # Zeichen zeigen, sonst ist es ein Hero-Bild/Werbung/Kopfnavigation statt des
                                       # eigentlichen Artikels (Marlon 04.10.2026)


def _cluster_articles(job: dict) -> list[dict]:
    path = DATA_DIR / "clusters" / f"{job.get('cluster_id')}.json"
    if not path.exists():
        return []
    arts = json.loads(path.read_text(encoding="utf-8")).get("articles", [])
    seen, out = set(), []
    for a in arts:                                # one article per outlet, cluster order = corroboration order
        if a.get("source") in seen or not a.get("url"):
            continue
        seen.add(a["source"])
        out.append(a)
    return out[:MAX_SOURCES]


CONSENT_CONTAINER_SEL = ("[id*='consent' i], [class*='consent' i], [id*='cookie' i], [class*='cookie' i], "
                         "[class*='gdpr' i], [id*='gdpr' i], [role='dialog'], [aria-modal='true']")


def _dismiss_consent(page):
    """Click the usual consent buttons in the page and in every iframe, then remove whatever
    fixed-position overlay is still covering the article. The button/link search is scoped to elements inside
    an actual cookie/consent/dialog container (CONSENT_CONTAINER_SEL) - Marlon 08.10.2026: an unscoped page-wide
    `a:has-text('Continue')` once matched an unrelated navigation link in a BBC article's own UI (nothing to do
    with cookies) and clicking it navigated clean away from the article to a generic help page before the
    screenshot - the exact "wrong page/random excerpt" bug, just one step earlier than the crop itself. Safe to
    call more than once (e.g. right before the final screenshot, in case a banner reappears after scrolling)."""
    for frame in [page] + list(page.frames):
        try:
            container = frame.locator(CONSENT_CONTAINER_SEL).first
            if not container.count():
                continue
        except Exception:
            continue
        for text in CONSENT_TEXTS:
            try:
                btn = container.locator(f"button:has-text('{text}'), a:has-text('{text}')").first
                if btn.count() and btn.is_visible(timeout=300):
                    btn.click(timeout=1000)
                    page.wait_for_timeout(800)
                    break
            except Exception:
                continue
    try:
        page.evaluate("""() => {
            for (const el of document.querySelectorAll('body *')) {
                const cs = getComputedStyle(el);
                if (cs.position !== 'fixed' && cs.position !== 'sticky') continue;
                const r = el.getBoundingClientRect();
                const grossesOverlay = r.height > 120 && parseInt(cs.zIndex || '0') >= 100;
                // duenne, oben angeheftete Kopfleiste (Navigation) - deckt sonst die Schlagzeile ab, obwohl
                // deren eigene Layout-Position laut DOM ganz oben waere (Marlon 08.10.2026: aljazeera.com)
                const kopfleiste = r.top <= 4 && r.height > 20 && r.height < 200;
                if (grossesOverlay || kopfleiste) el.remove();
            }
            document.documentElement.style.overflow = 'auto'; document.body.style.overflow = 'auto';
        }""")
    except Exception:
        pass


# ---- medium classification + no-login renderers ------------------------------------------
KIND_LABEL = {"article": {"de": "ARTIKEL", "en": "ARTICLE"}, "x": {"de": "BEITRAG AUF X", "en": "POST ON X"},
              "youtube": {"de": "VIDEO", "en": "VIDEO"}, "pdf": {"de": "BERICHT / PDF", "en": "REPORT / PDF"},
              "official": {"de": "OFFIZIELLE MITTEILUNG", "en": "OFFICIAL STATEMENT"}}
_OFFICIAL_HINTS = (".gov", ".gv.", "bundesregierung", "europa.eu", "un.org", "who.int", "nato.int", "bundestag", "whitehouse",
                   "parliament", "ec.europa", "consilium", "ecb.europa", "bundesbank", "auswaertiges-amt", "pressemitteilung")


def classify(url: str) -> str:
    u = (url or "").lower()
    if "twitter.com/" in u or "x.com/" in u:
        return "x"
    if "youtube.com/" in u or "youtu.be/" in u:
        return "youtube"
    if u.split("?")[0].endswith(".pdf"):
        return "pdf"
    if any(h in u for h in _OFFICIAL_HINTS):
        return "official"
    return "article"


def domain(url: str) -> str:
    from urllib.parse import urlparse
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


MIN_SPALTENBREITE = 320                # schmalere Spalte ist kein Artikeltext mehr - dann lieber volle Breite
CONTAINER_SEL = "article, main, [role='main']"
MAX_ARTIKEL_HOEHE = 2000               # mehr Artikel als das wird oben abgeschnitten (Titel bleibt erhalten) -
                                        # verhindert, dass ein sehr langer Artikel + Kommentare/verwandte Artikel
                                        # unten mit ins Bild rutschen; fuer Titel+Lead+Hauptteil reicht das bei
                                        # praktisch jedem Nachrichtenartikel (Marlon 08.10.2026: "lieber den ganzen
                                        # Artikel verkleinert zeigen ... als einen Ausschnitt")
MIN_AUFLOESUNG = (500, 150)            # kleiner ist kein brauchbarer Nachweis mehr
MIN_ASPECT_HOEHE_BREITE = 0.12         # Hoehe/Breite darunter = ein duenner Streifen (eine Zeile, ein Banner),
                                        # nicht der Artikel - genau der wiederkehrende Fehler vom 08.10.2026
MIN_TITEL_AEHNLICHKEIT = 0.34          # Anteil gemeinsamer Woerter (ab 4 Zeichen) - gefundene Schlagzeile vs. der
                                        # aus dem Cluster bekannte Artikeltitel


def _aehnlich(a: str, b: str) -> float:
    """Grobe Textaehnlichkeit 0..1 - prueft, ob die im Screenshot gefundene Schlagzeile wirklich zum erwarteten
    Artikeltitel passt und nicht zu einem falschen `h1` (Navigations-Widget, "meistgelesen" o.ae., eine andere
    Teaser-Karte auf derselben Seite). Wortmengen-Ueberlappung (Woerter ab 4 Zeichen) statt Zeichen-Sequenz
    (SequenceMatcher.ratio() haelt selbst voellig unterschiedliche Saetze allein wegen gemeinsamer Buchstaben/
    Leerzeichen oft fuer > 0,3 aehnlich - fuer einen Titel-Abgleich zu grob). Anteil der gemeinsamen Woerter an der
    kuerzeren der beiden Wortmengen. Pure Funktion."""
    wa = set(re.findall(r"[a-zA-ZÄÖÜäöüß0-9]{4,}", (a or "").lower()))
    wb = set(re.findall(r"[a-zA-ZÄÖÜäöüß0-9]{4,}", (b or "").lower()))
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / min(len(wa), len(wb))


OBEN_BAND_ANTEIL = 0.15                # oberste 15% des Bilds - dort sitzt bei einem korrekt ab der Schlagzeile
                                        # aufgenommenen Artikel praktisch immer der helle Seitenhintergrund
                                        # (Eyebrow/Schlagzeile auf Weiss), kein flaechiges Foto
MIN_HELLER_ANTEIL_OBEN = 0.2           # Anteil (na"he-)weisser Pixel im oberen Band, darunter = vermutlich ein
                                        # Foto/Video-Standbild statt der Schlagzeile - kalibriert an echten Folgen
                                        # vom 08.10.2026 (gute Aufnahmen 0,44-0,91, eine fehlerhafte mit fehlender
                                        # Schlagzeile 0,11)


def _heller_anteil_oben(img: Image.Image, band: float = OBEN_BAND_ANTEIL) -> float:
    """Anteil (nahe-)weisser Pixel (RGB je > 200) im obersten `band`-Teil des Bilds. Pure Funktion."""
    import numpy as np
    w, h = img.size
    bh = max(1, round(h * band))
    arr = np.asarray(img.convert("RGB").crop((0, 0, w, bh)))
    hell = int(np.all(arr > 200, axis=-1).sum())
    return hell / (w * bh)


def struktur_probleme(png: Path, zeichen: int, erwarteter_titel: str = "", gefundene_schlagzeile: str = "") -> list[str]:
    """Bild-Analyse eines fertigen Quellen-Screenshots - dieselbe Funktion prueft sowohl die eigene Aufnahme in
    capture() (Selbstkontrolle vor dem Akzeptieren) als auch tools/weltlage_abnahme.py (letzte Kontrolle vor dem
    Versand), damit beide Stellen nie auseinanderlaufen. Findet die typischen wiederkehrenden Fehlbilder:
      - zu kleine Aufloesung oder fast leer/einfarbig (Cookie-Wand, Paywall-Interstitial)
      - ein zu niedriges Seitenverhaeltnis - ein duenner, breiter Streifen ist keine Artikelseite, sondern eine
        einzelne Zeile oder ein Banner (Marlon 08.10.2026, der wiederkehrende Fehler)
      - zu wenig Text im Ausschnitt (Hero-Bild/Werbung/Kopfnavigation statt Artikeltext)
      - die gefundene Schlagzeile passt nicht zum erwarteten Artikeltitel (falsches `h1` erfasst) - das prueft nur
        den DOM-Text, nicht das Bild selbst
      - das obere Bilddrittel ist kein heller Seitenhintergrund, sondern vermutlich ein Foto/Video-Standbild -
        faengt den Fall ab, dass die Schlagzeile zwar im DOM-Text (und damit in "zeichen"/"gefundene_schlagzeile")
        steckt, im tatsaechlich aufgenommenen Bild aber gar nicht zu sehen ist (Marlon 08.10.2026, aljazeera.com:
        nach einer spaeten Layout-Verschiebung begann der Ausschnitt beim Titelfoto statt bei der Schlagzeile,
        obwohl Text und Titel-Abgleich beide "in Ordnung" gemeldet hatten)
    Leere Liste = Bild ist in Ordnung. Pure Funktion bis auf das Lesen der Bilddatei, offline testbar."""
    probleme = []
    try:
        with Image.open(png) as img:
            w, h = img.size
            stat = ImageStat.Stat(img.convert("L"))
            heller_anteil_oben = _heller_anteil_oben(img)
    except Exception as exc:                          # noqa: BLE001
        return [f"Bild nicht lesbar ({exc})"]
    if w < MIN_AUFLOESUNG[0] or h < MIN_AUFLOESUNG[1]:
        probleme.append(f"Aufloesung zu klein ({w}x{h})")
    elif h / w < MIN_ASPECT_HOEHE_BREITE:
        probleme.append(f"Bild zu niedrig fuer seine Breite ({w}x{h}, Seitenverhaeltnis {h/w:.2f}) - sieht nach "
                        "einer einzelnen Zeile oder einem Banner aus, nicht nach dem Artikel")
    if zeichen < MIN_HEADLINE_TEXT:
        probleme.append(f"zu wenig Text im Ausschnitt ({zeichen} Zeichen, Mindestwert {MIN_HEADLINE_TEXT})")
    if erwarteter_titel and gefundene_schlagzeile and _aehnlich(gefundene_schlagzeile, erwarteter_titel) < MIN_TITEL_AEHNLICHKEIT:
        probleme.append(f"gefundene Schlagzeile passt nicht zum erwarteten Titel (\"{gefundene_schlagzeile[:60]}\" "
                        f"statt \"{erwarteter_titel[:60]}\") - vermutlich falsches Element erfasst")
    if stat.stddev[0] < 12:
        probleme.append("Bild fast leer/einfarbig (Cookie-Wand/Paywall-Interstitial?)")
    elif heller_anteil_oben < MIN_HELLER_ANTEIL_OBEN:
        probleme.append(f"oberes Bilddrittel nicht hell genug ({heller_anteil_oben:.2f} statt mindestens "
                        f"{MIN_HELLER_ANTEIL_OBEN:g} heller Flaeche) - sieht nach einem Foto/Video-Standbild statt "
                        "der Schlagzeile auf hellem Hintergrund aus")
    return probleme


def _clip_aus_boxen(box: dict, lead_boxen: list[dict], vp: dict, pad: int = 24) -> dict:
    """x/Breite des Playwright-Clips aus der Schlagzeilen-Box + den verwendeten Lead-Absatz-Boxen - NICHT die
    volle Viewport-Breite (Marlon 08.10.2026: Seiten mit zweispaltigem Layout, z.B. aljazeera.com, zeigten so
    rechts eine Werbe-/Empfehlungs-Spalte im Bild statt nur den Artikel). y/Hoehe wie bisher unveraendert aus
    `box`/`lead_boxen` berechnet (Aufruferin reicht sie weiter). Faellt eine Seite ungewoehnlich schmal aus
    (MIN_SPALTENBREITE), ist das vermutlich keine echte Artikelspalte - dann wie zuvor die volle Breite. Pure
    Funktion, offline testbar."""
    x0 = box["x"]
    x1 = box["x"] + box["width"]
    for pb in lead_boxen:
        x0 = min(x0, pb["x"])
        x1 = max(x1, pb["x"] + pb["width"])
    cx0 = max(0, round(x0 - pad))
    cx1 = min(vp["width"], round(x1 + pad))
    if cx1 - cx0 < MIN_SPALTENBREITE:
        return {"x": 0, "width": vp["width"]}
    return {"x": cx0, "width": cx1 - cx0}


def _artikel_container(page, h1_box: dict):
    """Das kleinste `article`/`main`/`[role=main]`-Element, das die Schlagzeile vollstaendig umschliesst - auf
    praktisch jeder Nachrichtenseite ist das die saubere Artikelspalte selbst (Navigation/Werbespalten liegen als
    Geschwister daneben, nicht darin), darum reicht sein eigener Rahmen als Aufnahme-Ausschnitt. None, wenn keines
    passt (seltenes/altes Markup ohne article/main) - die Aufruferin faellt dann auf die alte Absatz-Sammlung
    zurueck."""
    beste = None
    try:
        kandidaten = page.locator(CONTAINER_SEL).all()
    except Exception:
        kandidaten = []
    for loc in kandidaten:
        try:
            box = loc.bounding_box()
        except Exception:
            box = None
        if not box or box["height"] < 80:
            continue
        if box["y"] > h1_box["y"] + 4 or box["y"] + box["height"] < h1_box["y"] + h1_box["height"] - 4:
            continue                                   # enthaelt die Schlagzeile nicht vollstaendig
        if beste is None or box["height"] < beste[1]["height"]:
            beste = (loc, box)
    return beste


def _ausschnitt_aus_absaetzen(page, h1_box: dict, vp: dict) -> dict | None:
    """Rueckfall ohne article/main-Element: Ausschnitt aus der Schlagzeile + den folgenden <p>-Absaetzen
    zusammensetzen, bis MAX_ARTIKEL_HOEHE erreicht ist (nicht mehr auf 520px/die Viewport-Hoehe gedeckelt wie vor
    dem 08.10.2026 - das war der Hauptgrund, warum der Ausschnitt oft nur eine einzelne Zeile zeigte). Der
    zusammengesetzte Text wird von der Aufruferin separat ueber dieselben <p>-Elemente ermittelt."""
    unten = h1_box["y"] + h1_box["height"] + 24
    try:
        absaetze = page.locator(LEAD_SEL).all()
    except Exception:
        absaetze = []
    lead_boxen = []
    for p in absaetze[:40]:
        try:
            pb = p.bounding_box()
        except Exception:
            pb = None
        if not pb or pb["y"] < h1_box["y"]:
            continue
        if pb["y"] > h1_box["y"] + MAX_ARTIKEL_HOEHE:
            break
        lead_boxen.append(pb)
        unten = max(unten, pb["y"] + pb["height"])
    y0 = max(0, h1_box["y"] - 16)
    y1 = max(unten, h1_box["y"] + h1_box["height"] + 120)
    if y1 - y0 < 80:
        return None
    xbreite = _clip_aus_boxen(h1_box, lead_boxen, vp)
    return {"x": xbreite["x"], "y": y0, "width": xbreite["width"], "height": y1 - y0}


def _voll_scrollen(page, max_y: float):
    """Scrollt einmal zuegig bis `max_y`, damit lazy-geladene Absaetze/Bilder im Artikel vor dem Screenshot
    bereits gerendert sind - der bisherige einmalige wheel(0,250) triggerte nur das erste Bildschirmfenster, bei
    einem langen Artikel blieb der Rest der Seite ungeladen (Marlon 08.10.2026)."""
    y, schritt = 0.0, 700
    while y < max_y:
        page.mouse.wheel(0, schritt)
        page.wait_for_timeout(180)
        y += schritt
    page.wait_for_timeout(300)


def _headline_region(page) -> tuple[dict | None, int, str]:
    """Liefert einen Playwright-Clip (x, y, width, height) fuer den ganzen Artikel ab seiner eigenen Schlagzeile
    (nicht nur Schlagzeile + ein kurzes Stueck Lead wie vor dem 08.10.2026), dazu dessen Zeichenzahl und die
    gefundene Schlagzeile selbst (fuer den Titel-Abgleich in struktur_probleme()). Bevorzugt den Artikel-eigenen
    `article`/`main`-Container (_artikel_container) - zuverlaessiger als eine Absatz-fuer-Absatz-Sammlung, die bei
    ungewoehnlichem Markup leicht die falsche Stelle trifft. None, 0, "" wenn keine Schlagzeile gefunden wurde.

    Nebenwirkung (Marlon 08.10.2026, aljazeera.com): vergroessert das Browserfenster grosszuegig, BEVOR irgendetwas
    vermessen wird, und scrollt an den Dokumentanfang zurueck. Zwei Gruende: (1) ein `page.screenshot(clip=...)`
    ueber die aktuelle Fensterhoehe hinaus ("capture beyond viewport") lieferte im produktiven Browser-Kanal
    "msedge" (anders als im Playwright-eigenen Chromium, mit dem der Fix zuerst getestet wurde) zuverlaessig
    falsche/leere Flaechen statt des tatsaechlichen Seiteninhalts. (2) das Vergroessern selbst kann noch einmal
    Layout veraendern (z.B. ein Werbeblock, der erst bei genug sichtbarer Flaeche nachlaedt und den Artikel nach
    unten verschiebt) - eine Messung VOR dieser Vergroesserung waere dann schon wieder veraltet und der
    Ausschnitt begaenne wieder irgendwo mitten im Artikel statt bei der Schlagzeile. Darum: erst vergroessern,
    dann (und nur dann) messen."""
    try:
        h1 = page.locator(HEADLINE_SEL).first
        if not h1.count() or not h1.is_visible(timeout=1500):
            return None, 0, ""
        h1.scroll_into_view_if_needed(timeout=2000)
        page.wait_for_timeout(400)
        h1_box = h1.bounding_box()
        if not h1_box:
            return None, 0, ""
        vp = page.viewport_size
        container = _artikel_container(page, h1_box)
        scroll_ziel = min((container[1]["height"] if container else None) or MAX_ARTIKEL_HOEHE, MAX_ARTIKEL_HOEHE)
        _voll_scrollen(page, scroll_ziel)                 # lazy-geladene Absaetze/Bilder nachladen
        page.evaluate("() => window.scrollTo(0, 0)")
        page.set_viewport_size({"width": vp["width"], "height": vp["height"] + MAX_ARTIKEL_HOEHE + 600})
        page.wait_for_timeout(400)                         # ab hier: Fenster gross genug, Koordinaten verlaesslich
        h1_box = h1.bounding_box() or h1_box
        schlagzeile = (h1.inner_text(timeout=1000) or "").strip()
        if container is not None:
            loc, _ = container
            box = loc.bounding_box()
            text = (loc.inner_text(timeout=1500) or "").strip()
        else:
            box = _ausschnitt_aus_absaetzen(page, h1_box, vp)
            text = schlagzeile
            if box:
                try:
                    for p in page.locator(LEAD_SEL).all()[:40]:
                        pb = p.bounding_box()
                        if pb and box["y"] <= pb["y"] <= box["y"] + box["height"]:
                            text += " " + (p.inner_text(timeout=500) or "")
                except Exception:
                    pass
        if not box:
            return None, 0, ""
        xbreite = {"x": 0, "width": vp["width"]} if box["width"] >= vp["width"] - 40 else \
                  {"x": max(0, round(box["x"])), "width": min(vp["width"], round(box["width"]))}
        if xbreite["width"] < MIN_SPALTENBREITE:
            xbreite = {"x": 0, "width": vp["width"]}
        hoehe = min(box["height"], MAX_ARTIKEL_HOEHE)
        clip = {"x": xbreite["x"], "y": max(0, round(box["y"])), "width": xbreite["width"], "height": round(hoehe)}
        if clip["height"] < 80:
            return None, 0, ""
        return clip, len(re.sub(r"\s+", " ", text).strip()), schlagzeile
    except Exception:
        return None, 0, ""


def _oembed(url: str, endpoint: str) -> dict | None:
    import httpx
    try:
        r = httpx.get(endpoint, params={"url": url, "omit_script": "true", "lang": "de", "dnt": "true"}, timeout=15,
                      headers={"User-Agent": "Mozilla/5.0"})
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def render_x_post(url: str, out: Path) -> dict | None:
    """An X post as a clean card (author, handle, text, date) from the oEmbed endpoint or the
    fxtwitter JSON API; None when neither answers (the caller then screenshots the post page)."""
    import html as htmlmod, re as re_
    from PIL import ImageDraw
    from video.thumbnail import _load_font, _wrap_text
    data = _oembed(url, "https://publish.twitter.com/oembed") or _oembed(url, "https://publish.x.com/oembed")
    if not data:
        m_id = re_.search(r"/status/(\d+)", url)
        if m_id:
            try:
                import httpx
                r = httpx.get(f"https://api.fxtwitter.com/status/{m_id.group(1)}", timeout=15, headers={"User-Agent": "Mozilla/5.0"})
                t = r.json().get("tweet") if r.status_code == 200 else None
            except Exception:
                t = None
            if t:
                au = t.get("author") or {}
                data = {"html": f"<p>{htmlmod.escape(t.get('text', ''))}</p>&mdash; {htmlmod.escape(au.get('name', ''))} "
                                f"(@{au.get('screen_name', '')}) <a>{str(t.get('created_at', ''))[:16]}</a>", "author_name": au.get("name", "")}
    if not data:
        return None
    raw = data.get("html", "")
    text = re_.sub(r"<[^>]+>", " ", raw.split("</p>")[0]) if "</p>" in raw else re_.sub(r"<[^>]+>", " ", raw)
    text = htmlmod.unescape(re_.sub(r"\s+", " ", text)).strip()
    m = re_.search(r"&mdash;\s*(.*?)\s*\((@[\w_]+)\)\s*<a[^>]*>([^<]*)</a>", raw)
    author, handle, date = (htmlmod.unescape(m.group(1)), m.group(2), m.group(3)) if m else (data.get("author_name", ""), "", "")
    img = Image.new("RGB", (1280, 800), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.ellipse([50, 50, 130, 130], fill=(29, 155, 240))
    d.text((150, 52), author, font=_load_font(40), fill=(15, 20, 25))
    d.text((150, 100), handle, font=_load_font(30), fill=(83, 100, 113))
    d.text((1150, 60), "X", font=_load_font(64), fill=(15, 20, 25))
    y = 170
    for line in _wrap_text(d, text, _load_font(42), 1180)[:9]:
        d.text((50, y), line, font=_load_font(42), fill=(15, 20, 25)); y += 54
    d.text((50, min(y + 20, 740)), date, font=_load_font(28), fill=(83, 100, 113))
    img.save(out)
    return {"title": text[:160], "source": f"{author} ({handle}) auf X" if handle else f"{author} auf X", "date": date}


def render_youtube(url: str, out: Path) -> dict | None:
    """A YouTube source as its official thumbnail + title (oEmbed), framed like a player."""
    import httpx, re as re_
    from PIL import ImageDraw
    data = _oembed(url, "https://www.youtube.com/oembed")
    if not data:
        return None
    m = re_.search(r"(?:v=|youtu\.be/|shorts/)([\w-]{11})", url)
    thumb = None
    if m:
        try:
            r = httpx.get(f"https://i.ytimg.com/vi/{m.group(1)}/hqdefault.jpg", timeout=15)
            if r.status_code == 200:
                from io import BytesIO
                thumb = Image.open(BytesIO(r.content)).convert("RGB").resize((1280, 720))
        except Exception:
            thumb = None
    img = thumb or Image.new("RGB", (1280, 720), (20, 20, 20))
    d = ImageDraw.Draw(img)
    d.polygon([(590, 300), (590, 420), (700, 360)], fill=(255, 255, 255))
    d.rectangle([540, 280, 740, 440], outline=(255, 0, 0), width=6)
    img.save(out)
    return {"title": data.get("title", ""), "source": f"{data.get('author_name', '')} auf YouTube", "date": ""}


def capture(job_id: str, articles: list[dict]) -> list[dict]:
    """Screenshots -> data/broll/<job>/source{i}.png. Returns [{index, source, title, url, png}]."""
    out_dir = DATA_DIR / "broll" / job_id
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("playwright not installed - no source screenshots")
        return results
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel=NEWS_PLAYWRIGHT_CHANNEL, headless=True)
        except Exception:
            browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900}, locale="de-DE",
                                      user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                                 "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
        context.set_default_timeout(15000)                  # kein Playwright-Aufruf wartet mehr die vollen 30 s
        for i, a in enumerate(articles):
            png = out_dir / f"source{i}.png"
            kind = classify(a["url"])
            meta = {"index": i, "source": a["source"], "title": a["title"], "url": a["url"], "png": png, "kind": kind,
                    "domain": domain(a["url"]), "date": str(a.get("published_at") or "")[:10]}
            if png.exists():
                results.append(meta)
                continue
            if kind in ("x", "youtube"):                 # built from official embeds when available, no browser needed
                built = render_x_post(a["url"], png) if kind == "x" else render_youtube(a["url"], png)
                if built:
                    meta.update({k: v for k, v in built.items() if v})
                    results.append(meta)
                    logger.info("source %d for %s built from %s embed: %s", i, job_id, kind, meta["source"])
                    continue
                if kind == "youtube":
                    continue
                # X no longer serves oEmbed (404, Sept 2026): fall through to a plain screenshot of the post
            page = context.new_page()
            try:
                page.goto(a["url"], wait_until="domcontentloaded", timeout=25000)
                try:
                    page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass
                page.wait_for_timeout(1200)
                # redirected to a section page / homepage (bot wall, geo redirect)? then it is not proof
                want = {w.lower() for w in re.findall(r"[A-Za-zÄÖÜäöüß]{4,}", a.get("title", ""))}
                got = (page.title() or "").lower() + " " + (page.inner_text("h1", timeout=1500) if page.locator("h1").count() else "").lower()
                if want and len([w for w in want if w in got]) < max(2, len(want) // 3):
                    logger.info("source screenshot %d for %s skipped: page does not show the article (%s)", i, job_id, a["source"])
                    continue
                _dismiss_consent(page)
                page.mouse.wheel(0, 250)               # trigger lazy-loaded headline/lead images
                page.wait_for_timeout(1200)
                page.mouse.wheel(0, -250)
                page.wait_for_timeout(600)
                clip, zeichen, schlagzeile = _headline_region(page)
                if clip is None or zeichen < MIN_HEADLINE_TEXT:
                    logger.info("source screenshot %d for %s skipped: keine Schlagzeile+Text im Ausschnitt "
                                "(%d Zeichen) (%s)", i, job_id, zeichen, a["source"])
                    continue
                # manche Cookie-/Consent-Leisten erscheinen erst verzoegert oder nach dem Scrollen in
                # _headline_region neu - ein zweiter Versuch direkt vor der Aufnahme faengt das ab (Marlon
                # 08.10.2026: ein BBC-Artikel zeigte trotz erfolgreichem ersten Klick noch eine Cookie-Leiste
                # am unteren Bildrand)
                _dismiss_consent(page)
                page.screenshot(path=str(png), clip=clip)
                # Selbstkontrolle (Marlon 08.10.2026): dieselbe Pruefung wie die Abnahme vor dem Versand - zu
                # klein/leer, ein duenner Streifen (eine Zeile/Banner) oder eine Schlagzeile, die nicht zum
                # erwarteten Artikeltitel passt, verwirft den Screenshot statt ihn stillschweigend zu akzeptieren.
                probleme = struktur_probleme(png, zeichen, a.get("title", ""), schlagzeile)
                if probleme:
                    logger.info("source screenshot %d for %s verworfen: %s (%s)", i, job_id,
                               "; ".join(probleme), a["source"])
                    png.unlink(missing_ok=True)
                    continue
                meta["textzeichen"] = zeichen
                meta["schlagzeile"] = schlagzeile
                results.append(meta)
                logger.info("source screenshot %d for %s: %s (%d Zeichen Schlagzeile+Text)", i, job_id, a["source"],
                           zeichen)
            except Exception as e:
                logger.info("source screenshot skipped (%s): %s", a.get("source"), str(e)[:120])
            finally:
                page.close()
        browser.close()
    return results


CAPTURE_FRIST_S = 600


def capture_mit_frist(job_id: str, articles: list[dict], frist_s: int = CAPTURE_FRIST_S) -> list[dict]:
    """capture() in einem eigenen Prozess mit harter Frist. Ein haengender Browser/Seitenaufruf (21.10.2026: Schritt
    "bilder" der 10:00-Folge stand 7,5 h ohne Logzeile) wird samt Prozessbaum beendet; bereits fertige PNGs bleiben
    liegen und werden beim naechsten Aufruf wiederverwendet. Bei Fristablauf gibt es [] (der Aufrufer loggt)."""
    import subprocess
    import sys
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        ein, aus = Path(tmp) / "ein.json", Path(tmp) / "aus.json"
        ein.write_text(json.dumps({"job": job_id, "articles": articles}, default=str), encoding="utf-8")
        p = subprocess.Popen([sys.executable, "-m", "video.sources", "--capture-json", str(ein), str(aus)],
                             cwd=str(Path(__file__).resolve().parent.parent), stdin=subprocess.DEVNULL,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            p.wait(timeout=frist_s)
        except subprocess.TimeoutExpired:
            subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            p.wait()
            logger.warning("capture %s: Frist %d s abgelaufen, Prozessbaum beendet", job_id, frist_s)
            return []
        if not aus.exists():
            return []
        shots = json.loads(aus.read_text(encoding="utf-8"))
    for s in shots:
        s["png"] = Path(s["png"])
    return shots


def run(job_id: str) -> list[dict]:
    from orchestrator import state_store
    job = state_store.get_job(job_id) or {}
    articles = _cluster_articles(job)
    if not articles:
        return []
    shots = capture(job_id, articles)
    (DATA_DIR / "broll" / job_id / "sources.json").write_text(
        json.dumps([{k: (str(v) if isinstance(v, Path) else v) for k, v in s.items()} for s in shots], indent=2, ensure_ascii=False),
        encoding="utf-8")
    return shots


def load(job_id: str) -> list[dict]:
    path = DATA_DIR / "broll" / job_id / "sources.json"
    if not path.exists():
        return []
    shots = json.loads(path.read_text(encoding="utf-8"))
    return [s for s in shots if Path(s["png"]).exists()]


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) == 4 and sys.argv[1] == "--capture-json":
        _d = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
        _r = capture(_d["job"], _d["articles"])
        Path(sys.argv[3]).write_text(json.dumps([{k: (str(v) if isinstance(v, Path) else v) for k, v in x.items()}
                                                 for x in _r], ensure_ascii=False), encoding="utf-8")
        raise SystemExit(0)
    print(run(sys.argv[1]))
