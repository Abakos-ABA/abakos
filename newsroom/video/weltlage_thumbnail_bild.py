"""Weltlage Kompakt - Themenbild fuer Thumbnails (rexemres Auftrag 23.10.2026).

Befund: Die Suche nahm die ersten Woerter des Titels als Begriffe. «BREAKING» (Label-Praefix) fand auf Commons
«Big wave breaking in Santa Cruz» (Macron- und Lula-Shorts alle mit demselben Wellenbild), und bei «Trump» lieferte
Commons immer dasselbe erste Portrait (Tanker-/Netanyahu-Shorts). Es gab keine Merkliste, kein Quellbild, keine B-Roll.

Reihenfolge jetzt (erste zulaessige Stufe gewinnt, jede Entscheidung wird protokolliert):
  1. Quellbild: og:image der Quellmeldungen der Folge (news.json) - nur wenn die Quelle nachweislich frei nutzbar ist
     (FREIE_QUELLEN: Regierungs-/Wikimedia-/DVIDS-Domains); Agentur- und Zeitungsbilder sind urheberrechtlich
     geschuetzt und werden mit Grund abgelehnt (Protokoll).
  2. Lizenzfreies Foto (Wikimedia Commons CC0/PD/CC BY/BY-SA, Pexels) mit Eigennamen/Themenwoertern statt Label-Woertern.
  3. Standbild aus dem B-Roll der Folge (Clips mit Lizenzliste broll_lizenzen.json).
  4. Kein Foto (Latara gross) - nie ein Platzhalter.
Merkliste state/thumbnail_bildverlauf.json: dasselbe Bild nie fuer zwei verschiedene Themen (Folgenordner); Teil 1/2
desselben Themas bekommen bevorzugt verschiedene Bilder. Pro Short wird die Wahl gespeichert
(<ordner>/thumbnails/foto_<szene>.jpg/.json), damit ein Neurendern (Titelaenderung) dasselbe Bild nimmt.
"""
from __future__ import annotations

import json
import re
import subprocess
from io import BytesIO
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
VERLAUF = ROOT / "state" / "thumbnail_bildverlauf.json"
UA = "WeltlageKompakt-Thumbnail/1.0 (newsroom; info@iota-plus.com)"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

# Label-/Fuellwoerter, die nie Suchbegriff sein duerfen («BREAKING» -> Wellenbild)
STOPP = set("""breaking eilmeldung alarm teil jetzt offiziell soweit weltlage kompakt nach dann doch auch wird werden wurde
verliert gegen entscheidet greift fuer für eine einen einer eines dieser diese dieses sind ist hat haben kann koennte
könnte schon mehr noch nicht wegen waren wartet zeigt zielt führt fuehrt dreht wie was wer wen wem warum weil nur
ohne unter ueber über bei aus von vor zum zur zwischen krawallen""".split())
# Themenwoerter DE->EN fuer Commons/Pexels (nur wo der Eigenname allein nichts Passendes liefert)
UEBERSETZUNG = {"tanker": "oil tanker", "ölhahn": "oil", "oelhahn": "oil", "stichwahl": "election", "wahl": "election",
                "krawallen": "riots", "krawalle": "riots", "proteste": "protest", "streik": "strike",
                "krieg": "war", "waffenruhe": "ceasefire", "zölle": "tariffs", "zoelle": "tariffs",
                "regierung": "government", "haushalt": "budget", "kontrolle": "government", "deal": "negotiations"}

# Quellen, deren Bilder nachweislich frei nutzbar sind (Host der Quellmeldung)
FREIE_QUELLEN = re.compile(r"(\.gov$|\.gov\.[a-z]{2}$|\.mil$|wikimedia\.org$|wikipedia\.org$|dvidshub\.net$|"
                           r"europa\.eu$|kremlin\.ru$|bundesregierung\.de$|admin\.ch$|gouvernement\.fr$)")


# ---------------------------------------------------------------- Merkliste
def _verlauf() -> dict:
    try:
        return json.loads(VERLAUF.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _merken(foto_id: str, ordner: str, szene: str, stufe: str) -> None:
    v = _verlauf()
    e = v.setdefault(foto_id, {"stufe": stufe, "themen": {}})
    e["themen"].setdefault(ordner, [])
    if szene not in e["themen"][ordner]:
        e["themen"][ordner].append(szene)
    try:
        VERLAUF.parent.mkdir(parents=True, exist_ok=True)
        VERLAUF.write_text(json.dumps(v, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


def zulaessig(foto_id: str, ordner: str, szene: str, verlauf: dict, streng: bool) -> bool:
    """Nie ein Bild, das ein anderes Thema (Ordner) nutzt. streng=True: auch nicht von einem anderen Short desselben Themas."""
    themen = (verlauf.get(foto_id) or {}).get("themen") or {}
    if any(o != ordner for o in themen):
        return False
    if streng and any(s != szene for s in themen.get(ordner, [])):
        return False
    return True


# ---------------------------------------------------------------- Suchbegriffe
def begriffe(titel: str) -> list[str]:
    """Eigennamen zuerst (gross geschrieben, kein Label-/Fuellwort), dann uebersetzte Themenwoerter."""
    roh = re.sub(r"[!?.,:;\"'«»„“–+]", " ", titel or "")
    woerter = [w for w in roh.split() if len(w) > 3 and w.lower() not in STOPP]
    namen = [w for w in woerter if w[0].isupper() and not w.isupper() and w.lower() not in UEBERSETZUNG]
    namen = [w[:-1] if w.lower() in ("trumps", "putins", "macrons") else w for w in namen]
    namen = list(dict.fromkeys(namen))
    thema = [UEBERSETZUNG[w.lower()] for w in woerter if w.lower() in UEBERSETZUNG]
    q: list[str] = []
    if len(namen) >= 2:
        q.append(" ".join(namen[:2]))
    for n in namen[:3]:
        if thema:
            q.append(f"{n} {thema[0]}")
        q.append(n)
    q += thema[:2]
    return list(dict.fromkeys(q))


# ---------------------------------------------------------------- Stufe 1: Quellbild
def _og_image(url: str) -> str | None:
    import httpx
    r = httpx.get(url, headers={"User-Agent": UA}, timeout=20, follow_redirects=True)
    m = (re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', r.text, re.I)
         or re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', r.text, re.I))
    return m.group(1) if m else None


def _host(url: str) -> str:
    m = re.match(r"https?://([^/:]+)", url or "")
    return (m.group(1).lower() if m else "").removeprefix("www.")


def quellbild(ordner: Path, titel: str, protokoll: list, ok=lambda fid: True):
    """og:image der zum Titel passenden Quellmeldungen; nur bei nachweislich freier Quelle. Rueckgabe (Bild, k) oder None."""
    import httpx
    try:
        news = json.loads((ordner / "news.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        protokoll.append("Quellbild: news.json fehlt")
        return None
    w = {x.lower() for x in re.split(r"\W+", titel) if len(x) > 3 and x.lower() not in STOPP}
    arts = [a for g in news for a in (g.get("articles") or []) if isinstance(a, dict) and a.get("url")]
    arts.sort(key=lambda a: -sum(1 for x in w if x in (str(a.get("title", "")) + str(a.get("snippet", ""))).lower()))
    gesehen: set[str] = set()
    for a in arts[:8]:
        host = _host(a["url"])
        if not FREIE_QUELLEN.search(host):
            if host not in gesehen:
                protokoll.append(f"Quellbild: {host} abgelehnt (Agentur-/Verlagsbild, keine freie Lizenz nachweisbar)")
                gesehen.add(host)
            continue
        try:
            u = _og_image(a["url"])
            if not u:
                continue
            fid = f"og-{u}"
            if not ok(fid):
                protokoll.append(f"Quellbild: {fid[:60]} schon bei anderem Thema/Short verwendet")
                continue
            im = Image.open(BytesIO(httpx.get(u, headers={"User-Agent": UA}, timeout=30,
                                              follow_redirects=True).content)).convert("RGB")
        except Exception as e:   # noqa: BLE001
            protokoll.append(f"Quellbild: {host} Fehler {type(e).__name__}")
            continue
        if im.width < 900:
            continue
        return im, {"id": fid, "quelle": "og", "stufe": "quelle", "seite": a["url"], "titel": a.get("title", ""),
                    "urheber": host, "lizenz": f"freie Quelle ({host})", "lizenz_url": ""}
    return None


# ---------------------------------------------------------------- Stufe 3: B-Roll-Standbild
def broll_standbild(ordner: Path, short_nr: int, protokoll: list, ok=lambda fid: True):
    """Standbild aus einem B-Roll-Clip, der im Video der Folge tatsaechlich lizenziert verwendet wurde
    (broll_lizenzen.json 'clips'); nicht verwendete Vorratsclips (generische Stock-Motive) zaehlen nicht."""
    try:
        lj = json.loads((ordner / "broll_lizenzen.json").read_text(encoding="utf-8"))
        lizenzen = [x for x in (lj.get("clips") or []) if isinstance(x, dict) and x.get("lizenz")]
    except (OSError, ValueError):
        lizenzen = []
    if not lizenzen:
        protokoll.append("B-Roll: kein lizenzierter, im Video verwendeter Clip in der Folge")
        return None
    for i in range(len(lizenzen)):
        meta = lizenzen[(short_nr - 1 + i) % len(lizenzen)]
        cands = [c for c in sorted((ordner / "broll").glob(f"clip{int(meta.get('nr', 0)):02d}_*.mp4"))
                 if "_ersatz" not in c.name]
        if not cands:
            continue
        c = cands[0]
        fid = f"broll-{ordner.name}-{c.stem}"
        if not ok(fid):
            continue
        tmp = ordner / "thumbnails" / f"_frame_{c.stem}.jpg"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", "1.0", "-i", str(c),
                            "-frames:v", "1", "-q:v", "2", str(tmp)], capture_output=True, creationflags=NO_WINDOW)
        if r.returncode != 0 or not tmp.exists():
            continue
        im = Image.open(tmp).convert("RGB")
        im.load()
        tmp.unlink(missing_ok=True)
        if im.width < 900:
            continue
        return im, {"id": fid, "quelle": "broll", "stufe": "broll", "seite": meta.get("seite", ""),
                    "titel": meta.get("titel") or c.stem, "urheber": meta.get("urheber", ""),
                    "lizenz": meta["lizenz"], "lizenz_url": meta.get("lizenz_url", "")}
    protokoll.append("B-Roll: kein verwendbares Standbild")
    return None


# ---------------------------------------------------------------- Einstieg
def waehle(titel: str, ordner: Path | None, szene: str, short_nr: int, log=print):
    """Rueckgabe (Bild, k) oder None. Nimmt zuerst die gespeicherte Wahl dieses Shorts; sonst Stufen 1-3."""
    from video import weltlage_thumbnail_eil as eil
    ordner = Path(ordner) if ordner is not None else None
    name = ordner.name if ordner else "ohne-ordner"
    fdatei = ordner / "thumbnails" / f"foto_{szene}.jpg" if ordner else None
    if fdatei is not None and fdatei.exists() and fdatei.with_suffix(".json").exists():
        try:
            return Image.open(fdatei).convert("RGB"), json.loads(fdatei.with_suffix(".json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    verlauf = _verlauf()
    protokoll: list[str] = []
    gef = None
    for streng in (True, False):
        def ok(fid, s=streng):
            return zulaessig(fid, name, szene, verlauf, s)
        if ordner is not None:
            gef = quellbild(ordner, titel, protokoll, ok)
        if not gef:
            gef = eil.pressefoto(begriffe(titel), log=log, ok=ok)
            if gef:
                gef[1]["stufe"] = "lizenzfrei"
        if not gef and ordner is not None:
            gef = broll_standbild(ordner, short_nr, protokoll, ok)
        if gef:
            break
    for z in protokoll:
        log(z)
    if not gef:
        log(f"Thumbnail-Bild: nichts Passendes fuer '{titel[:60]}' - Layout ohne Foto")
        return None
    im, k = gef
    log(f"Thumbnail-Bild: Stufe {k.get('stufe')} {k['id']} fuer {szene}")
    _merken(k["id"], name, szene, k.get("stufe", ""))
    if fdatei is not None:
        try:
            fdatei.parent.mkdir(parents=True, exist_ok=True)
            im.save(fdatei, quality=92)
            fdatei.with_suffix(".json").write_text(json.dumps(k, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass
    return im, k
