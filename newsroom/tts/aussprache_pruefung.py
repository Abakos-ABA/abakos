"""Aussprache-Pruefschritt vor jeder Vertonung (18.10.2026, rexemres Rueckmeldung "FBI und weitere Woerter schlecht
ausgesprochen", Task ad90): meldet, was die Stimme vermutlich falsch liest, und loest auf, was sich automatisch
aufloesen laesst.

Meldungen (art):
- abkuerzung_unbekannt: Grossbuchstaben-Kuerzel, das weder in SAY_AS_WORD/SPELL_OUT (tts/normalize_de.py) noch im
  Lexikon steht. AUFGELOEST: die Regel buchstabiert es (ohne Vokal oder <= 5 Zeichen) bzw. spricht es als Wort;
  die Meldung sagt, wie. Sicher als Wort gemeinte Kuerzel gehoeren nach SAY_AS_WORD.
- fremdzeichen: Wort mit Akzent/Sonderbuchstabe ohne Lexikon-Eintrag. AUFGELOEST: normalize_de.fremdzeichen
  (Sébastien -> Sebastien); ein Lexikon-Eintrag waere genauer.
- englisch_verdacht: Name mit starkem englischem Schriftbild (sh, oo, ea, ou, ay, igh, wh, -ing), der weder
  in 3+ bisherigen Folgen noch im Lexikon steht. NICHT aufgeloest: nur gemeldet (die LLM-Pflege, aussprache_lexikon.lerne_aus_folge,
  laeuft im Tageslauf direkt davor und sollte ihn erfasst haben).
- rest: was nach normalize_for_tts noch nach Ziffer/Zeichen/Kuerzel aussieht (Ziffern, %, /, &, # ...).
  NICHT aufgeloest: Regel fehlt, gehoert in normalize_de.

    python tts/aussprache_pruefung.py text "<text>"          # einzelner Text
    python tts/aussprache_pruefung.py folge <folgenordner>   # alle Szenen, schreibt <ordner>/aussprache_pruefung.json
    python tts/aussprache_pruefung.py scan                   # alle Skripte data/*/texte.json, Kandidatenliste
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tts import normalize_de as nd  # noqa: E402
from tts.aussprache_lexikon import laden as _lexikon_laden  # noqa: E402

_KUERZEL = re.compile(r"(?<![\w-])([A-ZÄÖÜ][A-Za-zÄÖÜäöü]*[A-ZÄÖÜ][A-Za-zÄÖÜäöü]*)(?![\w])")
_FREMD_WORT = re.compile(r"\b\w*[^\x00-\x7FäöüÄÖÜß\W\d_]\w*\b")
_NAME = re.compile(r"(?<![\w-])([A-Z][a-z]{2,}(?:-[A-Z][a-z]+)?)\b")
# Nur starke englische Schriftbilder (th/ee/ck/tion/j kommen im Deutschen zu oft vor: Methode, Armee, Druck, Nation,
# Jahr); "sh" nicht in deutschen Zusammensetzungen mit -s-h- (Gerichtshof, Untersuchungshaft).
_ENGLISCH = re.compile(r"^sh|[^s]sh(?![aeiou]f|aft)|oo(?!t|r|s)|ea(?!l|k|g|t)|ou(?!r|t)|ay|igh(?!e)|wh|^Th(?![eoa])"
                       r"|[a-z]{3}ing$", re.I)
_REST = re.compile(r"\d|[%/&#@+=<>§°²³\\|_~^*]|\b[A-ZÄÖÜ]{2,}\b")


_haeufig_cache: set[str] | None = None


def _haeufig(min_folgen: int = 3) -> set[str]:
    """Woerter, die in mindestens `min_folgen` bisherigen Folgen vorkommen: die hat rexemre schon oft gehoert, ohne
    dass sie ins Lexikon kamen (Washington, Biden ...) - kein Verdachtsfall mehr. Nur fuers Melden, nicht fuer die
    Sprechform (die bleibt deterministisch)."""
    global _haeufig_cache
    if _haeufig_cache is None:
        folgen = Counter()
        for f in ROOT.glob("data/*/texte.json"):
            try:
                folgen.update(set(re.findall(r"[A-Za-zÄÖÜäöüß]{3,}", f.read_text(encoding="utf-8"))))
            except OSError:
                continue
        _haeufig_cache = {w for w, n in folgen.items() if n >= min_folgen}
    return _haeufig_cache


def _sprechformen() -> set[str]:
    """Woerter, die selbst schon Sprechform eines Lexikon-Eintrags sind (Beijing -> Peking)."""
    return {w for e in _lexikon_laden()["eintraege"].values() for w in str(e.get("sprich", "")).split()}


def _lexikon_schluessel() -> set[str]:
    return set(_lexikon_laden()["eintraege"])


def _im_lexikon(wort: str, lexikon: set[str]) -> bool:
    return wort in lexikon or wort.rstrip("s") in lexikon or any(wort in k.split() for k in lexikon)


def pruefe(text: str, lexikon: set[str] | None = None) -> dict:
    """Prueft einen Sprechtext (Rohfassung aus dem Skript). Rueckgabe {ok, sprechtext, meldungen: [{art, wort,
    aufgeloest, hinweis}]}; ok = keine unaufgeloeste Meldung."""
    lexikon = _lexikon_schluessel() if lexikon is None else lexikon
    meldungen, gesehen = [], set()

    def melde(art, wort, aufgeloest, hinweis):
        if (art, wort) not in gesehen:
            gesehen.add((art, wort))
            meldungen.append({"art": art, "wort": wort, "aufgeloest": aufgeloest, "hinweis": hinweis})

    for m in _KUERZEL.finditer(text):
        wort = m.group(1)
        kern = wort[:-1] if wort.endswith("s") and wort[:-1].isupper() else wort
        if not (kern.isupper() or sum(c.isupper() for c in kern) >= len(kern) - 1):
            continue                                       # CamelCase-Namen (McConnell, OpenAI) sind keine Kuerzel
        if kern in nd.SAY_AS_WORD or kern in nd.SPELL_OUT or kern in nd.SPELL_OUT_EN or kern in nd.SPELL_OUT_ALT_EN or _im_lexikon(wort, lexikon):
            continue
        if kern.isupper() and nd.ist_deutsches_wort(kern):
            continue                                       # Betonung in Grossschrift (WAHL) -> als Wort, kein Fall
        gesprochen = nd.normalize_for_tts(wort)
        weise = "buchstabiert" if gesprochen.count(" ") >= len(kern) - 1 >= 1 else "als Wort"
        melde("abkuerzung_unbekannt", wort, True, f"{weise}: «{gesprochen}» (Liste SAY_AS_WORD/SPELL_OUT/SPELL_OUT_EN "
              "in tts/normalize_de.py ergänzen, wenn das falsch ist)")
    for m in _FREMD_WORT.finditer(text):
        wort = m.group(0)
        if not _im_lexikon(wort, lexikon):
            melde("fremdzeichen", wort, True, f"vereinfacht zu «{nd.fremdzeichen(wort)}» (Lexikon-Eintrag wäre genauer)")
    for m in _NAME.finditer(text):
        wort = m.group(1)
        teile = wort.split("-")
        # <= 10 Zeichen: lange Woerter sind fast immer deutsche Zusammensetzungen (Verhandlungsteam, Haushaltsamt)
        verdacht = [t for t in teile if len(t) <= 10 and _ENGLISCH.search(t) and t not in _haeufig()
                    and not _im_lexikon(t, lexikon) and t not in _sprechformen()]
        if verdacht and not _im_lexikon(wort, lexikon):
            melde("englisch_verdacht", wort, False, "englisches Schriftbild, kein Lexikon-Eintrag")
    sprechtext = nd.normalize_for_tts(text)
    for m in _REST.finditer(sprechtext):
        if m.group(0) in nd.SAY_AS_WORD or nd.ist_deutsches_wort(m.group(0)):
            continue                                       # NATO/UNO bleiben absichtlich in Grossschrift
        ctx = sprechtext[max(0, m.start() - 15): m.end() + 15]
        melde("rest", m.group(0), False, f"nach der Normalisierung noch da: «…{ctx}…» (Regel in normalize_de fehlt)")
    return {"ok": not any(not x["aufgeloest"] for x in meldungen), "sprechtext": sprechtext, "meldungen": meldungen}


def kurz(ergebnis: dict) -> str:
    """Eine Logzeile: "3 Meldungen (1 offen): englisch_verdacht Burnham; abkuerzung_unbekannt XYZ -> ..."."""
    m = ergebnis["meldungen"]
    if not m:
        return "Aussprache-Prüfung: nichts zu melden"
    offen = sum(1 for x in m if not x["aufgeloest"])
    teile = [f"{x['art']} {x['wort']}" for x in m[:8]]
    return f"Aussprache-Prüfung: {len(m)} Meldung(en), {offen} offen: " + "; ".join(teile) + (" …" if len(m) > 8 else "")


def _szenen(ordner: Path) -> list[dict]:
    texte = json.loads((ordner / "texte.json").read_text(encoding="utf-8"))
    return [s for s in texte.get("szenen") or [] if (s.get("text") or "").strip()]


def pruefe_folge(ordner: Path, log=print) -> dict:
    """Alle Szenen einer Folge pruefen, Ergebnis nach <ordner>/aussprache_pruefung.json. Nie fatal."""
    try:                                       # englische Kuerzel lernen (tts/kuerzel_lernen.py), vor der Pruefung
        from tts.kuerzel_lernen import lerne_aus_folge
        lerne_aus_folge(ordner, log=log)
    except Exception as e:  # noqa: BLE001
        log(f"Kuerzel-Lernen uebersprungen: {e}")
    lexikon = _lexikon_schluessel()
    szenen = {s["id"]: pruefe(s["text"], lexikon) for s in _szenen(ordner)}
    alle = [dict(x, szene=sid) for sid, e in szenen.items() for x in e["meldungen"]]
    gesamt = {"ok": all(e["ok"] for e in szenen.values()), "meldungen": alle,
              "offen": [x for x in alle if not x["aufgeloest"]]}
    (ordner / "aussprache_pruefung.json").write_text(json.dumps(gesamt, indent=1, ensure_ascii=False), encoding="utf-8")
    log(kurz(gesamt))
    return gesamt


def scan(muster: str = "data/*/texte.json") -> dict:
    """Alle bisherigen Skripte durchsuchen: Kandidaten je Art mit Haeufigkeit (fuer die Lexikon-Pflege)."""
    lexikon = _lexikon_schluessel()
    zaehler: dict[str, Counter] = {}
    for f in sorted(ROOT.glob(muster)):
        try:
            for s in _szenen(f.parent):
                for x in pruefe(s["text"], lexikon)["meldungen"]:
                    zaehler.setdefault(x["art"], Counter())[x["wort"]] += 1
        except (json.JSONDecodeError, OSError):
            continue
    return {art: c.most_common() for art, c in zaehler.items()}


def main():
    args = sys.argv[1:]
    if args[:1] == ["text"] and len(args) > 1:
        print(json.dumps(pruefe(" ".join(args[1:])), indent=1, ensure_ascii=False))
    elif args[:1] == ["folge"] and len(args) > 1:
        e = pruefe_folge(Path(args[1]))
        print(json.dumps(e["offen"], indent=1, ensure_ascii=False))
    elif args[:1] == ["scan"]:
        print(json.dumps(scan(*args[1:2]), indent=1, ensure_ascii=False))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
