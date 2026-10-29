"""Automatisches Lernen englischer Kuerzel (22.10.2026, rexemre: "CNBC falsch, englische Medien-/Organisationskuerzel
englisch, EU/CDU deutsch"). Laeuft im Tageslauf-Schritt aussprache (aussprache_pruefung.pruefe_folge), also VOR der
Vertonung der Folge.

Regel: Ein Grossbuchstaben-Kuerzel (2-5 Buchstaben), das weder in SAY_AS_WORD/SPELL_OUT/SPELL_OUT_EN noch im Lexikon
steht und kein deutsches Wort ist, gilt als ENGLISCH, wenn es in mindestens MIN_BELEGE englischsprachigen
Quellartikeln dieser Folge (news.json: Titel/Zusammenfassung/Ausschnitt) als eigenes Grossbuchstaben-Wort steht.
Gelernt wird in config/brand/stimme/kuerzel_en.json (quelle "auto", mit Folge, Zeit, Belegen; Protokoll
state/aussprache_lernen/kuerzel_protokoll.jsonl). normalize_de liest die Datei als Teil von SPELL_OUT_EN; Szenen, die
vor dem Lernzeitpunkt vertont wurden, behalten ihre Tonspur (normalize_de._alter_stand).

    python tts/kuerzel_lernen.py folge <folgenordner>   # lernen
    python tts/kuerzel_lernen.py liste
    python tts/kuerzel_lernen.py sperre <KUERZEL>       # Eintrag entfernen und nie wieder lernen (bleibt deutsch)
    python tts/kuerzel_lernen.py dazu <KUERZEL>         # von Hand als englisch eintragen

Schalter: Umgebung NEWS_KUERZEL_LERNEN=0 schaltet das Lernen ab.
"""
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tts import normalize_de as nd  # noqa: E402
from tts.aussprache_lexikon import laden as _lexikon_laden  # noqa: E402

PFAD = nd.KUERZEL_EN_PFAD
PROTOKOLL = ROOT / "state" / "aussprache_lernen" / "kuerzel_protokoll.jsonl"
MIN_BELEGE = 2
MAX_NEU_JE_FOLGE = 5
_TOKEN = re.compile(r"(?<![\w-])([A-Z]{2,5})(?![\w])")
# Grossschrift, die nie ein Kuerzel ist (englische Betonung, roemische Zahlen, Waehrungen/Einheiten)
_KEIN_KUERZEL = {"THE", "AND", "FOR", "NOT", "NEW", "NOW", "ALL", "ONE", "TWO", "WAR", "NEWS", "LIVE", "II", "III", "IV",
                 "VI", "VII", "VIII", "IX", "XI", "XII", "OK", "RIP", "USD", "EUR", "GBP", "CHF", "MPH", "KM", "HQ", "TBD"}


def aktiv() -> bool:
    return os.environ.get("NEWS_KUERZEL_LERNEN", "1") != "0"


def laden() -> dict:
    try:
        d = json.loads(PFAD.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    d.setdefault("eintraege", {})
    d.setdefault("gesperrt", [])
    return d


def sichern(d: dict):
    PFAD.parent.mkdir(parents=True, exist_ok=True)
    tmp = PFAD.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(PFAD)


def _protokoll(ereignis: dict):
    PROTOKOLL.parent.mkdir(parents=True, exist_ok=True)
    with PROTOKOLL.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"zeit": time.strftime("%Y-%m-%d %H:%M:%S"), **ereignis}, ensure_ascii=False) + "\n")


def _bekannt(k: str, lexikon: set, d: dict) -> bool:
    return (k in nd.SAY_AS_WORD or k in nd.SPELL_OUT or k in nd.SPELL_OUT_EN or k in nd.SPELL_OUT_ALT_EN or k in lexikon
            or k in d["eintraege"] or k in d["gesperrt"] or k in _KEIN_KUERZEL or nd.ist_deutsches_wort(k))


def _quelltexte(ordner: Path) -> list[str]:
    try:
        news = json.loads((ordner / "news.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for gruppe in news if isinstance(news, list) else [news]:
        for a in (gruppe.get("articles") or []) if isinstance(gruppe, dict) else []:
            out.append(" ".join(str(a.get(f) or "") for f in ("title", "summary", "snippet")))
    return out


def kandidaten(ordner: Path) -> dict[str, int]:
    """Unbekannte Kuerzel des Skripts -> Zahl englischer Quellartikel, in denen sie vorkommen."""
    texte = json.loads((ordner / "texte.json").read_text(encoding="utf-8"))
    skript = " ".join((s.get("text") or "") for s in texte.get("szenen") or [])
    lexikon = set(_lexikon_laden()["eintraege"])
    d = laden()
    kand = {k for k in _TOKEN.findall(skript) if not _bekannt(k, lexikon, d)}
    quellen = _quelltexte(ordner)
    return {k: sum(1 for q in quellen if re.search(rf"(?<![\w-]){k}(?![\w])", q)) for k in sorted(kand)}


def lerne_aus_folge(ordner: Path, log=print) -> dict:
    """Lernt englische Kuerzel einer Folge. Rueckgabe {gelernt: [...], offen: {kuerzel: belege}}."""
    if not aktiv():
        return {"gelernt": [], "offen": {}}
    ordner = Path(ordner)
    d = laden()
    gelernt, offen = [], {}
    for k, n in sorted(kandidaten(ordner).items(), key=lambda x: -x[1]):
        if n >= MIN_BELEGE and len(gelernt) < MAX_NEU_JE_FOLGE:
            d["eintraege"][k] = {"quelle": "auto", "zeit": time.strftime("%Y-%m-%d %H:%M:%S"), "folge": ordner.name, "belege": n}
            gelernt.append(k)
            _protokoll({"ereignis": "gelernt", "kuerzel": k, "folge": ordner.name, "belege": n})
        else:
            offen[k] = n
    if gelernt:
        sichern(d)
        nd.SPELL_OUT_EN.update(gelernt)
        nd._GELERNT_ZEIT.update({k: d["eintraege"][k]["zeit"] for k in gelernt})
    log(f"Kuerzel-Lernen: {len(gelernt)} neu als englisch ({', '.join(gelernt) or '-'}), {len(offen)} bleiben deutsch gebuchstabiert")
    return {"gelernt": gelernt, "offen": offen}


def sperre(k: str):
    d = laden()
    d["eintraege"].pop(k, None)
    if k not in d["gesperrt"]:
        d["gesperrt"].append(k)
    sichern(d)
    _protokoll({"ereignis": "gesperrt", "kuerzel": k})


def dazu(k: str):
    d = laden()
    d["gesperrt"] = [x for x in d["gesperrt"] if x != k]
    d["eintraege"][k] = {"quelle": "manuell", "zeit": time.strftime("%Y-%m-%d %H:%M:%S")}
    sichern(d)
    _protokoll({"ereignis": "manuell", "kuerzel": k})


def main():
    a = sys.argv[1:]
    if a[:1] == ["folge"] and len(a) > 1:
        print(json.dumps(lerne_aus_folge(Path(a[1])), ensure_ascii=False, indent=1))
    elif a[:1] == ["liste"]:
        print(json.dumps(laden(), ensure_ascii=False, indent=1))
    elif a[:1] == ["sperre"] and len(a) > 1:
        sperre(a[1].upper())
    elif a[:1] == ["dazu"] and len(a) > 1:
        dazu(a[1].upper())
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
