"""Weltlage Kompakt - Marlons Feedback zu einer fertigen Folge umsetzen (Freigabe-Schleife, Marlon 02.10.2026).

Teil des Zweimal-taeglich-Ablaufs (tools/weltlage_tageslauf.py, Schritt freigabe): Marlon drueckt unter dem Video
«Feedback» und schreibt, was anders sein soll. Das Modell (gleiches wie tools/weltlage_skript.py, Claude-CLI im Abo)
bekommt die Szenentexte, Titel und Thumbnail-Text der Folge plus das Feedback und gibt NUR die geaenderten Teile
zurueck. Danach:

  - geaenderte Szenentexte -> texte.json (alte Fassung als texte.vor_feedback_<runde>.json daneben); der fertige
    Master, die Clip-Fassung und die Abnahme werden entfernt, damit der Tageslauf Stimme, Schnitt, B-Roll und Abnahme
    erneut ausfuehrt. Neu gerechnet werden dabei nur die betroffenen Szenen: tools/weltlage_tts.py spricht nur
    Szenen mit geaendertem Text neu (Text-Hash im Nachweis), die LatentSync-Stuecke liegen nach Inhalt im Cache
    (video/freisteller_lipsync.py), feste Szenen (Bumper, Intro, Auftritt, Begruessung, Verabschiedung) sind
    eingefroren.
  - nur Titel/Thumbnail geaendert -> kein Rendern, nur Thumbnail + Metadaten neu.

Feste Szenen sind tabu (FEST): die Verabschiedung s6_outro ist in jeder Folge identisch.

    python tools/weltlage_ueberarbeiten.py <folgenordner> "<feedback>" [--runde 1] [--probe]   (--probe: nichts schreiben)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

FEST = {"s6_outro"}
THUMB_FELDER = ("banderole", "zeile1", "zeile2", "farbe")


def _prompt(texte: dict, feedback: str) -> str:
    szenen = [{"id": s["id"], "text": s["text"]} for s in texte["szenen"] if s["id"] not in FEST]
    return f"""Du bist Redakteur des deutschsprachigen YouTube-Analysekanals «Weltlage Kompakt» (Moderatorin Latara).
Die Folge unten ist fertig produziert. Marlon (Kanalchef) hat sie angesehen und will Aenderungen:

FEEDBACK VON MARLON:
{feedback.strip()}

Setze genau dieses Feedback um, so knapp wie moeglich: aendere nur Szenen, die das Feedback betrifft (jede geaenderte
Szene muss neu vertont und neu gerendert werden - also nichts ohne Grund anfassen). Behalte Stil, Ich-Form, markierte
Meinungssaetze, Bild-Marker in eckigen Klammern und alle Fakten bei; erfinde keine neuen Fakten, Zahlen oder Zitate
(nur Umformulieren, Kuerzen, Umstellen, Gewichten). Laenge einer Szene hoechstens 20 Prozent laenger als vorher.
Schweizer Schreibweise (ss statt sz). Titel: zugespitzte Frage, hoechstens 70 Zeichen, nie faktisch falsch.

Antworte NUR mit JSON:
{{"szenen": {{"<id>": "<neuer vollstaendiger Text>"}}, "titel": null, "thumbnail": null,
 "zusammenfassung": "ein Satz fuer Marlon, was geaendert wurde"}}
("titel" nur setzen, wenn er sich aendern soll; "thumbnail" nur als Objekt mit banderole/zeile1/zeile2/farbe.)

TITEL: {texte.get('titel')}
THUMBNAIL: {json.dumps(texte.get('thumbnail'), ensure_ascii=False)}
SZENEN:
{json.dumps(szenen, ensure_ascii=False, indent=1)}
"""


def pruefen(antwort: dict, texte: dict) -> list[str]:
    fehler = []
    ids = {s["id"]: s for s in texte["szenen"]}
    for sid, neu in (antwort.get("szenen") or {}).items():
        if sid in FEST:
            fehler.append(f"{sid} ist eine feste Szene und darf nicht geaendert werden")
        elif sid not in ids:
            fehler.append(f"unbekannte Szene {sid}")
        elif not str(neu or "").strip():
            fehler.append(f"{sid}: leerer Text")
        elif len(str(neu)) > 1.35 * len(ids[sid]["text"]) + 80:
            fehler.append(f"{sid}: deutlich zu lang ({len(str(neu))} statt {len(ids[sid]['text'])} Zeichen)")
    t = antwort.get("titel")
    if t and (len(t) > 100 or not str(t).strip()):
        fehler.append("Titel zu lang oder leer")
    th = antwort.get("thumbnail")
    if th is not None and not (isinstance(th, dict) and all(th.get(k) for k in THUMB_FELDER[:3])):
        fehler.append("Thumbnail braucht banderole, zeile1, zeile2")
    return fehler


def vorschlag(texte: dict, feedback: str, modell=None) -> dict:
    if modell is None:
        from weltlage_skript import frage_modell as modell
    from weltlage_skript import _ss
    prompt = _prompt(texte, feedback)
    a = _ss(modell(prompt))
    fehler = pruefen(a, texte)
    if fehler:
        a2 = _ss(modell(prompt + "\n\nDein letzter Vorschlag hatte diese Fehler, behebe jeden:\n"
                        + "\n".join(f"- {f}" for f in fehler)))
        f2 = pruefen(a2, texte)
        if len(f2) < len(fehler):
            a, fehler = a2, f2
    if fehler:
        raise RuntimeError("Feedback nicht sauber umsetzbar: " + "; ".join(fehler))
    return a


def anwenden(ordner: Path, antwort: dict, runde: int, master: Path | None = None) -> dict:
    """Schreibt die Aenderungen in texte.json und raeumt die Render-Ergebnisse weg, die neu entstehen muessen.
    Rueckgabe: {"szenen": [ids], "titel": bool, "thumbnail": bool, "neu_rendern": bool, "zusammenfassung": str}."""
    pfad = ordner / "texte.json"
    texte = json.loads(pfad.read_text(encoding="utf-8"))
    (ordner / f"texte.vor_feedback_{runde}.json").write_text(json.dumps(texte, indent=1, ensure_ascii=False),
                                                              encoding="utf-8")
    geaendert = []
    for s in texte["szenen"]:
        neu = (antwort.get("szenen") or {}).get(s["id"])
        if neu and neu.strip() != s["text"].strip():
            s["text"] = neu.strip()
            geaendert.append(s["id"])
    titel = bool(antwort.get("titel")) and antwort["titel"].strip() != texte.get("titel")
    if titel:
        texte["titel"] = antwort["titel"].strip()
    thumb = isinstance(antwort.get("thumbnail"), dict) and antwort["thumbnail"] != texte.get("thumbnail")
    if thumb:
        texte["thumbnail"] = {**(texte.get("thumbnail") or {}), **{k: v for k, v in antwort["thumbnail"].items()
                                                                     if k in THUMB_FELDER and v}}
    pfad.write_text(json.dumps(texte, indent=1, ensure_ascii=False), encoding="utf-8")
    if geaendert and master is not None:
        for p in (master, master.with_name(master.stem + "_clips.mp4"), master.with_name(master.stem + "_abnahme.json")):
            if p.exists():
                p.replace(p.with_name(f"{p.stem}.vor_feedback_{runde}{p.suffix}"))
    return {"szenen": geaendert, "titel": titel, "thumbnail": thumb, "neu_rendern": bool(geaendert),
            "zusammenfassung": antwort.get("zusammenfassung") or ""}


def ueberarbeiten(ordner: Path, feedback: str, runde: int, master: Path | None = None, modell=None) -> dict:
    texte = json.loads((ordner / "texte.json").read_text(encoding="utf-8"))
    a = vorschlag(texte, feedback, modell)
    (ordner / f"feedback_{runde}.json").write_text(json.dumps({"feedback": feedback, "antwort": a}, indent=1,
                                                              ensure_ascii=False), encoding="utf-8")
    return anwenden(ordner, a, runde, master)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ordner", type=Path)
    ap.add_argument("feedback")
    ap.add_argument("--runde", type=int, default=1)
    ap.add_argument("--probe", action="store_true")
    a = ap.parse_args()
    texte = json.loads((a.ordner / "texte.json").read_text(encoding="utf-8"))
    if a.probe:
        print(json.dumps(vorschlag(texte, a.feedback), indent=1, ensure_ascii=False))
    else:
        print(json.dumps(ueberarbeiten(a.ordner, a.feedback, a.runde), indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
