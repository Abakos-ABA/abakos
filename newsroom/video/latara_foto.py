"""Latara-Fotoauswahl fuer Weltlage-Thumbnails (Task 20261002-220950-b2d6, 02.10.2026).

Marlon legt Fotos von Latara in seinem eigenen Ordner ab (Documents/WK/Latara Thumbnails, auf der Platte
"latara_thunbnails" geschrieben). Dieses Modul waehlt daraus automatisch das Bild, das zur Stimmung der Folge
passt, und vermeidet die letzten paar zuvor gezeigten Bilder. Der Ordner bleibt Marlons: nur lesen, nie
verschieben, umbenennen oder loeschen.

Die Stimmung eines Fotos kommt aus dem Dateinamen (Schluesselwoerter unten unter DATEINAME_WOERTER). Neue Bilder
im Ordner werden beim naechsten Aufruf automatisch in die Index-Datei (config/brand/thumbnail/latara_index.json)
aufgenommen. Erkennt der Dateiname keine Stimmung, landet das Bild unter "unbekannt" - dann traegt eine
Bildanalyse die Stimmung einmalig von Hand in die Index-Datei ein.

    python -m video.latara_foto "Text der Folge"   -> zeigt gewaehltes Foto + erkannte Stimmungen (Testlauf,
                                                        schreibt NICHT in den Verlauf)
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORDNER = Path(r"C:\Users\Marlon\Documents\WK\latara_thunbnails")   # Marlons Ordner - nur lesen
INDEX = ROOT / "config" / "brand" / "thumbnail" / "latara_index.json"
VERLAUF = ROOT / "state" / "latara_verlauf.json"
LETZTE_AUSSCHLUSS = 3   # so viele letzte Folgen duerfen dasselbe Bild nicht noch einmal bekommen

# Stimmungen, die der Kanal kennt. Reihenfolge = Rangfolge bei Gleichstand (z.B. wenn der Text keine Woerter trifft).
STIMMUNGEN = ["geschockt", "ernst", "nachdenklich", "skeptisch", "zeigend", "laechelnd", "papier"]

# Schluesselwoerter im Dateinamen (klein, Umlaute ausgeschrieben) je Stimmung - fuer neue Bilder.
DATEINAME_WOERTER = {
    "geschockt": ["geschockt", "schock", "schreck"],
    "ernst": ["ernst", "sachlich", "streng"],
    "nachdenklich": ["nachdenklich", "denkend", "gruebel", "ueberlegt"],
    "skeptisch": ["skeptisch", "zweifel", "stirnrunzel", "kritisch"],
    "zeigend": ["zeigend", "zeigt", "finger", "deutet"],
    "laechelnd": ["laechelnd", "lachend", "laecheln", "smile", "froehlich"],
    "papier": ["papier", "dokument", "blatt", "akte", "paper"],
}

# Woerter im Skript/Titel der Folge, die auf eine Stimmung hindeuten (klein, Umlaute ausgeschrieben).
TEXT_WOERTER = {
    "geschockt": ["schock", "eskalation", "angriff", "explo", "kollaps", "chaos", "krieg", "alarm", "krise",
                  "einmarsch", "katastroph", "notfall", "ultimatum", "eklat"],
    "skeptisch": ["wirklich?", "luege", "zweifel", "fake", "taeuschung", "angeblich", "stimmt das", "bluff"],
    "nachdenklich": ["analyse", "hintergrund", "bedeutet", "folgen", "einordnung", "warum", "was das"],
    "ernst": ["warnt", "warnung", "streit", "konflikt", "spannung", "verhandlung", "sanktion", "droht", "drohung"],
    "laechelnd": ["erfolg", "einigung", "durchbruch", "rekord", "aufschwung", "gewinn", "freude", "sieg",
                  "fortschritt", "entspannung"],
    "zeigend": ["fordert", "appelliert", "verlangt", "ruft auf"],
}

_UMLAUT = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def _normalisiert(s: str) -> str:
    return s.lower().translate(_UMLAUT)


def _stimmen_aus_dateiname(datei: str) -> list[str]:
    n = _normalisiert(datei)
    return [m for m, woerter in DATEINAME_WOERTER.items() if any(w in n for w in woerter)]


def lade_index(aktualisieren: bool = True) -> dict:
    """Index Dateiname -> {stimmungen, quelle}. Neue Bilder im Ordner werden ergaenzt, fehlende entfernt."""
    daten = json.loads(INDEX.read_text(encoding="utf-8")) if INDEX.exists() else {}
    if not aktualisieren or not ORDNER.is_dir():
        return daten
    vorhanden = {p.name for p in ORDNER.iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg")}
    geaendert = False
    for name in list(daten):
        if name not in vorhanden:
            del daten[name]
            geaendert = True
    for name in sorted(vorhanden):
        if name not in daten:
            stimmen = _stimmen_aus_dateiname(name)
            daten[name] = {"stimmungen": stimmen or ["unbekannt"],
                           "quelle": "dateiname" if stimmen else "ungeklaert"}
            geaendert = True
    if geaendert:
        INDEX.parent.mkdir(parents=True, exist_ok=True)
        INDEX.write_text(json.dumps(daten, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return daten


def stimmung_aus_text(text: str) -> list[str]:
    """Rangfolge der Stimmungen, die am besten zum Text der Folge passen (meiste Treffer zuerst)."""
    n = _normalisiert(text or "")
    punkte = {m: sum(n.count(w) for w in woerter) for m, woerter in TEXT_WOERTER.items()}
    return sorted(STIMMUNGEN, key=lambda m: -punkte.get(m, 0))


def _verlauf_lesen() -> list[str]:
    return json.loads(VERLAUF.read_text(encoding="utf-8")) if VERLAUF.exists() else []


def _verlauf_schreiben(namen: list[str]) -> None:
    VERLAUF.parent.mkdir(parents=True, exist_ok=True)
    VERLAUF.write_text(json.dumps(namen[-20:], ensure_ascii=False, indent=2), encoding="utf-8")


def _zuletzt_index(verlauf: list[str], name: str) -> int:
    """Index des letzten Vorkommens (-1 = noch nie gezeigt -> wird bevorzugt)."""
    for i in range(len(verlauf) - 1, -1, -1):
        if verlauf[i] == name:
            return i
    return -1


def waehle_foto(text: str, merken: bool = True) -> Path | None:
    """Bestes Foto aus ORDNER fuer den Text der Folge, oder None wenn der Ordner fehlt/leer ist (z.B. Platte
    nicht eingebunden) - dann faellt die Vorlage auf die alten festen Fotos zurueck."""
    index = lade_index()
    if not index:
        return None
    verlauf = _verlauf_lesen()
    gesperrt = set(verlauf[-LETZTE_AUSSCHLUSS:])
    for stimmung in stimmung_aus_text(text):
        kandidaten = sorted(n for n, e in index.items() if stimmung in e.get("stimmungen", []))
        if not kandidaten:
            continue
        pool = [n for n in kandidaten if n not in gesperrt] or kandidaten
        wahl = min(pool, key=lambda n: _zuletzt_index(verlauf, n))
        if merken:
            verlauf.append(wahl)
            _verlauf_schreiben(verlauf)
        return ORDNER / wahl
    return None


if __name__ == "__main__":
    text = " ".join(sys.argv[1:])
    idx = lade_index()
    ungeklaert = [n for n, e in idx.items() if e.get("quelle") == "ungeklaert"]
    print(f"{len(idx)} Fotos im Index, davon ungeklaert: {ungeklaert or 'keine'}")
    print("Stimmungs-Rangfolge fuer den Text:", stimmung_aus_text(text))
    print("Gewaehlt (ohne in den Verlauf zu schreiben):", waehle_foto(text, merken=False))
