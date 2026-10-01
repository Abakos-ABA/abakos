"""Aussprache-Lexikon fuer die Stimme: schreibt Eigennamen und Fachbegriffe, die ein deutsches TTS-Modell
falsch liest (Politikernamen wie "Selenskyj"/"Erdoğan"/"Xi Jinping", Abkuerzungen wie "Fed"), in eine
phonetisch gut sprechbare Form um - NUR fuer die Stimme (tts/normalize_de.normalize_for_tts), nie fuer
Untertitel oder den Bildschirmtext (der bleibt bei der Schreibweise des Skripts).

Datei: config/brand/stimme/aussprache_lexikon.json ("eintraege": {Schreibweise: {sprich, quelle, hinzugefuegt}}).
Manuelle Eintraege (quelle="manuell") werden nie von der automatischen Pflege ueberschrieben oder entfernt.

Automatische Pflege (lerne_aus_folge): nach jedem Skript durchsucht ein LLM-Aufruf den Folgentext nach
Eigennamen, die noch nicht im Lexikon stehen, und schlaegt je einen Ausspracheeintrag vor
(quelle="llm"). Nie fatal - schlaegt die Pflege fehl, bleibt das bisherige Lexikon unveraendert und die
Folge laeuft ohne neue Eintraege weiter (tools/weltlage_tageslauf.py, Schritt "aussprache").

    python tts/aussprache_lexikon.py liste
    python tts/aussprache_lexikon.py lerne <folgenordner>
    python tts/aussprache_lexikon.py anwenden "<text>"
"""
import json
import logging
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

LEXIKON_PFAD = ROOT / "config" / "brand" / "stimme" / "aussprache_lexikon.json"
logger = logging.getLogger(__name__)

_HINWEIS = ("Nur fuer die Stimme (TTS-Eingabe vor normalize_for_tts), nie fuer Untertitel oder Bildschirmtext. "
            "Pflege: tts/aussprache_lexikon.py bzw. tools/weltlage_tageslauf.py Schritt 'aussprache'.")


def leer() -> dict:
    return {"_hinweis": _HINWEIS, "eintraege": {}}


def laden() -> dict:
    try:
        daten = json.loads(LEXIKON_PFAD.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return leer()
    daten.setdefault("eintraege", {})
    return daten


def sichern(daten: dict):
    daten = {**daten, "_hinweis": _HINWEIS}
    LEXIKON_PFAD.parent.mkdir(parents=True, exist_ok=True)
    tmp = LEXIKON_PFAD.with_suffix(".tmp")
    tmp.write_text(json.dumps(daten, indent=1, ensure_ascii=False, sort_keys=False), encoding="utf-8")
    tmp.replace(LEXIKON_PFAD)


def anwenden(text: str, eintraege: dict | None = None) -> str:
    """Ersetzt bekannte Schreibweisen durch ihre Sprich-Form (Wortgrenzen, verträgt ein angehängtes
    deutsches Genitiv-/Plural-s: "Erdoğans" -> "Erdoans"). Laengere Eintraege (z.B. "Xi Jinping") gehen
    vor kuerzeren ("Xi"), damit die Mehrwort-Form zuerst greift."""
    eintraege = eintraege if eintraege is not None else laden()["eintraege"]
    if not eintraege:
        return text
    keys = sorted(eintraege.keys(), key=len, reverse=True)
    pattern = re.compile(r"\b(" + "|".join(re.escape(k) for k in keys) + r")(s)?\b")

    def repl(m: re.Match) -> str:
        key, genitiv_s = m.group(1), m.group(2) or ""
        return eintraege[key]["sprich"] + genitiv_s

    return pattern.sub(repl, text)


# ------------------------------------------------------------------ automatische Pflege (LLM-Vorschlag)
_PROMPT = """Du prüfst das Skript einer deutschen Nachrichtensendung auf Eigennamen, die ein TTS-Modell beim
Vorlesen falsch ausspricht (fremdsprachige Politiker- und Ortsnamen, ungewöhnliche Transliterationen,
Abkürzungen, die wie ein Wort und nicht buchstabiert gesprochen werden).

Bereits bekannt (NICHT erneut vorschlagen): {bekannt}

Skripttext:
{text}

Nenne nur Namen/Begriffe, die wortwörtlich im Skripttext vorkommen, die noch NICHT in der bekannten Liste
stehen, und bei denen ein deutsches TTS-Modell mit hoher Wahrscheinlichkeit falsch betont oder falsch liest
(z.B. weil Buchstaben im Deutschen anders klingen als in der Herkunftssprache, oder weil Sonderzeichen wie
ğ/ş/ı vorkommen). Normale deutsche Wörter oder Namen, die ein deutscher Sprecher ohnehin richtig liest
(z.B. "Merkel", "Berlin", "Putin"), gehören NICHT in die Liste.

Antworte NUR mit diesem JSON-Objekt (leere Liste, wenn nichts zu melden ist):
{{"vorschlaege": [{{"name": "<Schreibweise exakt wie im Text>", "sprich": "<einzusprechende Schreibweise, rein phonetisch fuer einen deutschen Vorleser>"}}]}}"""


def _szenen_text(ordner: Path) -> str:
    texte = json.loads((ordner / "texte.json").read_text(encoding="utf-8"))
    teile = [texte.get("titel") or "", texte.get("zentrale_these") or ""]
    teile += [s.get("text") or "" for s in texte.get("szenen") or []]
    return "\n".join(t for t in teile if t.strip())


def vorschlaege_erzeugen(text: str, bekannt: set[str], frage_modell=None) -> list[dict]:
    """Ein LLM-Aufruf -> Liste roher Vorschlaege {name, sprich}. `frage_modell` default: Claude-CLI/Ollama
    aus tools/weltlage_skript.py (gleicher Mechanismus wie die Skript-Erzeugung, kein zweiter LLM-Pfad)."""
    if frage_modell is None:
        sys.path.insert(0, str(ROOT / "tools"))
        from weltlage_skript import frage_modell as frage_modell  # noqa: E402
    prompt = _PROMPT.format(bekannt=", ".join(sorted(bekannt)) or "(noch keine)", text=text[:6000])
    antwort = frage_modell(prompt)
    return [v for v in (antwort.get("vorschlaege") or [])
            if isinstance(v, dict) and v.get("name") and v.get("sprich")]


def lerne_aus_folge(ordner: Path, frage_modell=None, log=print) -> dict:
    """Liest texte.json der Folge, schlaegt neue Eintraege vor und nimmt sie SOFORT ins Lexikon auf
    (quelle="llm"). Manuelle Eintraege bleiben unberuehrt. Gibt {neu: [...], fehler: str|None} zurueck -
    ein Fehler ist nie fatal fuer den Tageslauf."""
    daten = laden()
    eintraege = daten["eintraege"]
    try:
        text = _szenen_text(ordner)
        rohvorschlaege = vorschlaege_erzeugen(text, set(eintraege), frage_modell)
    except Exception as e:  # noqa: BLE001 - Pflege ist ein Zusatznutzen, nie ein Abbruchgrund
        log(f"Aussprache-Pflege: Vorschlag fehlgeschlagen ({e}) - Lexikon bleibt unveraendert")
        return {"neu": [], "fehler": str(e)}
    neu = []
    for v in rohvorschlaege:
        name = v["name"].strip()
        if not name or name in eintraege or name not in text:
            continue
        eintraege[name] = {"sprich": v["sprich"].strip(), "quelle": "llm", "hinzugefuegt": date.today().isoformat(),
                           "folge": ordner.name}
        neu.append(name)
    if neu:
        sichern(daten)
        log(f"Aussprache-Pflege: {len(neu)} neue(r) Eintrag/Eintraege: {', '.join(neu)}")
    else:
        log("Aussprache-Pflege: keine neuen Eigennamen gefunden")
    return {"neu": neu, "fehler": None}


def main():
    logging.basicConfig(level=logging.INFO)
    args = sys.argv[1:]
    if args[:1] == ["liste"]:
        for name, e in laden()["eintraege"].items():
            print(f"{name!r} -> {e['sprich']!r} ({e.get('quelle')}, {e.get('hinzugefuegt')})")
    elif args[:1] == ["lerne"] and len(args) > 1:
        print(json.dumps(lerne_aus_folge(Path(args[1])), indent=1, ensure_ascii=False))
    elif args[:1] == ["anwenden"] and len(args) > 1:
        print(anwenden(args[1]))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
