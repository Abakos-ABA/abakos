"""Weltlage Kompakt - Abwechslung je Folge gegen das Monetarisierungsrisiko «massenproduzierte/vorlagenhafte
Inhalte» (rexemres Freigabe 28.10.2026 zur Analyse jarvis/reports/youtube-algorithmus-frequenz-20261028.md).

YouTube monetarisiert seit 15.07.2025 keine Kanaele mehr, deren Videos austauschbar wirken (gleicher Aufbau, gleicher
Einstieg, reine Nachrichtenwiedergabe mit KI-Stimme). Gleiche Intros/Outros sind erlaubt, der Hauptinhalt muss
variieren und einen eigenen Beitrag zeigen. Darum bekommt jede Folge zusaetzlich zum festen Prompt
(config/prompts/weltlage_analyse.md) einen Variantenblock:

  - ERZAEHLFORM: welcher Teil der Dramaturgie das Gewicht traegt (Leitfrage, Gewinner/Verlierer, Zahl im Zentrum,
    Wie es dazu kam, Zwei Lesarten, Was niemand sagt). Rollen und Pflichtteile bleiben, damit pruefen()/paket_pruefen()
    und Schnitt unveraendert laufen.
  - EINSTIEG: womit der erste Satz des Hooks beginnt (Zitat, Zahl, Szene, Widerspruch, direkte Frage).
  - EIGENE EINORDNUNG: Pflicht in jeder Variante - Abschnitt «einordnung» mit klarer, begruendeter Ich-Einschaetzung
    (mindestens EINORDNUNG_MIN_WOERTER), nicht nur Nacherzaehlen. einordnung_pruefen() meldet es als Hinweis.

Auswahl: zufaellig mit Seed aus dem Folgenordner, aber nie dieselbe Erzaehlform wie in den letzten 3 und nie derselbe
Einstieg wie in den letzten 2 Folgen (Verlauf state/weltlage_vielfalt.json). Abschalten: NEWS_WELTLAGE_VIELFALT=0.
Der Kanal-Manager kann die Varianten spaeter gegen die Aufrufe je Folge auswerten (Feld meta.vielfalt in skript.json).
"""
from __future__ import annotations

import hashlib
import json
import os
import random
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERLAUF = ROOT / os.environ.get("NEWS_STATE_DIR", "state") / "weltlage_vielfalt.json"
AKTIV = os.environ.get("NEWS_WELTLAGE_VIELFALT", "1") == "1"
EINORDNUNG_MIN_WOERTER = 60

FORMATE = [
    {"id": "leitfrage", "name": "Eine Leitfrage",
     "anweisung": "Die ganze Folge beantwortet EINE Leitfrage, die du im Abschnitt «ausgangslage» ausdrücklich "
                  "stellst. Jeder weitere Abschnitt bringt ein Indiz dafür oder dagegen; in «einordnung» gibst du "
                  "deine begründete Antwort."},
    {"id": "gewinner_verlierer", "name": "Wer gewinnt, wer verliert",
     "anweisung": "Ordne die Lage über die Frage, wer davon profitiert und wer verliert. «kontext» und «relevanz» "
                  "gehen Akteur für Akteur vor (Staaten, Personen, Märkte); in «einordnung» sagst du, wessen Rechnung "
                  "aus deiner Sicht aufgeht und warum."},
    {"id": "zahl_im_zentrum", "name": "Die Zahl dahinter",
     "anweisung": "Stelle EINE belegte Zahl aus dem Material ins Zentrum und erkläre, was sie bedeutet, wie sie "
                  "zustande kommt und was sie verschweigt. Vergleiche sie mit einer zweiten Grösse aus dem Material. "
                  "In «einordnung» bewertest du, ob die Zahl die Aufregung rechtfertigt."},
    {"id": "wie_es_dazu_kam", "name": "Wie es dazu kam",
     "anweisung": "Erzähle «kontext» als kurze Vorgeschichte in drei Schritten (früher, vor kurzem, jetzt) und "
                  "zeige, an welcher Stelle es hätte anders laufen können. In «einordnung» sagst du, welcher "
                  "Schritt aus deiner Sicht der entscheidende war."},
    {"id": "zwei_lesarten", "name": "Zwei Lesarten",
     "anweisung": "Baue die Folge als Gegenüberstellung zweier plausibler Deutungen auf; «gegenargument» ist hier "
                  "ein vollwertiger Abschnitt, nicht nur ein Einwand. In «einordnung» entscheidest du dich offen für "
                  "eine Lesart und nennst, welcher Beleg dich umstimmen würde."},
    {"id": "was_niemand_sagt", "name": "Was in den Meldungen fehlt",
     "anweisung": "Zeige, welche Frage in den Meldungen offen bleibt oder welcher Akteur auffällig schweigt (nur "
                  "aus dem Material belegbar, nichts erfinden). In «einordnung» erklärst du, warum diese Lücke aus "
                  "deiner Sicht wichtig ist, klar als Einschätzung markiert."},
]

EINSTIEGE = [
    {"id": "zitat", "anweisung": "Der Hook beginnt mit einem kurzen, belegten Zitat aus dem Material (in «»)."},
    {"id": "zahl", "anweisung": "Der Hook beginnt mit einer überraschenden, belegten Zahl."},
    {"id": "szene", "anweisung": "Der Hook beginnt mit einem konkreten Bild/Moment (wer stand wo und tat was), "
                                 "nur belegt aus dem Material."},
    {"id": "widerspruch", "anweisung": "Der Hook beginnt mit einem Widerspruch («A sagt …, gleichzeitig …»)."},
    {"id": "frage", "anweisung": "Der Hook beginnt mit einer direkten Frage an das Publikum."},
]


def _lesen(pfad: Path) -> list[dict]:
    try:
        d = json.loads(pfad.read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def waehlen(schluessel: str, verlauf_pfad: Path | None = None, speichern: bool = True) -> dict:
    """Variante fuer eine Folge (schluessel = Folgenordner-Name). Gleicher Schluessel -> gleiche Wahl (Neuversuch
    derselben Folge wechselt nicht die Form)."""
    pfad = verlauf_pfad or VERLAUF
    verlauf = _lesen(pfad)
    for e in verlauf:
        if e.get("schluessel") == schluessel:
            return e
    letzte = [e for e in verlauf if e.get("schluessel") != schluessel]
    format_gesperrt = {e.get("format") for e in letzte[-3:]}
    einstieg_gesperrt = {e.get("einstieg") for e in letzte[-2:]}
    rnd = random.Random(int(hashlib.sha256(schluessel.encode("utf-8")).hexdigest()[:12], 16))
    formate = [f for f in FORMATE if f["id"] not in format_gesperrt] or FORMATE
    einstiege = [e for e in EINSTIEGE if e["id"] not in einstieg_gesperrt] or EINSTIEGE
    wahl = {"schluessel": schluessel, "format": rnd.choice(formate)["id"], "einstieg": rnd.choice(einstiege)["id"],
            "zeit": datetime.now().isoformat(timespec="seconds")}
    if speichern:
        pfad.parent.mkdir(parents=True, exist_ok=True)
        tmp = pfad.with_suffix(".tmp")
        tmp.write_text(json.dumps((verlauf + [wahl])[-60:], indent=1, ensure_ascii=False), encoding="utf-8")
        tmp.replace(pfad)
    return wahl


def block(wahl: dict) -> str:
    f = next(x for x in FORMATE if x["id"] == wahl["format"])
    e = next(x for x in EINSTIEGE if x["id"] == wahl["einstieg"])
    return ("\n\nVARIANTE DIESER FOLGE (damit sich die Folgen nicht wie aus einer Vorlage anhören; alle Regeln oben "
            "gelten weiter, auch Rollen, Hook-Schluss und Kommentarfrage):\n"
            f"- Erzählform «{f['name']}»: {f['anweisung']}\n"
            f"- Einstieg: {e['anweisung']}\n"
            f"- Eigene Einordnung ist Pflicht: Der Abschnitt «einordnung» enthält mindestens {EINORDNUNG_MIN_WOERTER} "
            "Wörter mit deiner klar markierten, begründeten Einschätzung («Ich halte … für …, weil …»), nicht nur "
            "eine Zusammenfassung der Meldungen. Fakten bleiben Fakten, Meinung bleibt als Meinung erkennbar.")


def einordnung_pruefen(s: dict) -> list[str]:
    """Hinweise (nicht hart), wenn die eigene Einordnung fehlt oder zu duenn ist."""
    teile = [a.get("text") or "" for a in s.get("abschnitte") or [] if a.get("rolle") == "einordnung"]
    if not teile:
        return ["Kein Abschnitt «einordnung» (eigene Einschätzung) - Monetarisierungsrisiko reine Nachrichtenwiedergabe."]
    woerter = len(" ".join(teile).split())
    if woerter < EINORDNUNG_MIN_WOERTER:
        return [f"Einordnung nur {woerter} Wörter (Ziel mindestens {EINORDNUNG_MIN_WOERTER})."]
    return []
