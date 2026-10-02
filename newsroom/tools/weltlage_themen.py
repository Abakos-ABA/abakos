"""Weltlage Kompakt - Themenwahl vor jeder Folge: Recherche, drei Storylines A/B/C, Empfehlung (Marlon 02.10.2026).

Teil des Zweimal-taeglich-Ablaufs (tools/weltlage_tageslauf.py, Slots 11:00 und 19:00). Format wie die
Materialsammlung aus Task 20261002-221534-c7be: pro Storyline ein zugespitzter Titel als Frage, ein Satz Inhalt,
passende gruene Bildquellen (Lizenz-Ampel config/quellen_netzwerk.json), dazu eine Empfehlung mit Grund.
Stilvorbild: Vermietertagebuch (newsroom/reports/vorbild_vermietertagebuch_20261001/).

Recherche = die Rohmeldungen der Pipeline (data/raw/<tag>/*.json, RSS aller Quellen) der letzten
NEWS_WELTLAGE_THEMEN_STUNDEN Stunden; das Modell (Claude-CLI im Abo wie tools/weltlage_skript.py, keine GPU) waehlt pro
Storyline die passenden Artikelnummern und gruppiert sie zu Meldungen. Daraus wird nach der Wahl die news.json der
Folge (gleiches Format wie aktuelle_gruppen), die tools/weltlage_skript.py --news ... --vorgabe ... verarbeitet.

Themenpool (state/weltlage_themenpool.json): Storylines, die Marlon ausdruecklich auch noch machen will (z.B. B und C
einer frueheren Wahl). Sie werden bei den naechsten Vorschlaegen bevorzugt angeboten, solange es frische Meldungen
dazu gibt, und fliegen raus, sobald sie gewaehlt wurden oder ablaufen (Feld "bis").

    python tools/weltlage_themen.py vorschlagen <ordner>          (schreibt storylines.json, druckt den Bericht)
    python tools/weltlage_themen.py pool                          (Themenpool anzeigen)
    python tools/weltlage_themen.py pool-add "<Titel?>" "<Inhalt>" [--tage 4]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config.settings import DATA_DIR, STATE_DIR  # noqa: E402

POOL = STATE_DIR / "weltlage_themenpool.json"
QUELLEN_NETZ = ROOT / "config" / "quellen_netzwerk.json"
STUNDEN = 48
MAX_ARTIKEL = 260
BUCHSTABEN = ["A", "B", "C"]


# ------------------------------------------------------------------ Themenpool
def pool_laden(jetzt: datetime | None = None) -> list[dict]:
    jetzt = jetzt or datetime.now().astimezone()
    try:
        pool = json.loads(POOL.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    return [p for p in pool if not p.get("bis") or datetime.fromisoformat(p["bis"]) >= jetzt]


def pool_speichern(pool: list[dict]):
    POOL.parent.mkdir(parents=True, exist_ok=True)
    tmp = POOL.with_suffix(".tmp")
    tmp.write_text(json.dumps(pool, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(POOL)


def pool_add(titel: str, inhalt: str, tage: float = 4, quelle: str = "", such: str = "") -> dict:
    pool = pool_laden()
    eintrag = {"id": re.sub(r"[^a-z0-9]+", "-", titel.lower())[:40].strip("-"), "titel": titel, "inhalt": inhalt,
               "seit": datetime.now().astimezone().isoformat(timespec="minutes"), "quelle": quelle,
               "bis": (datetime.now().astimezone() + timedelta(days=tage)).isoformat(timespec="minutes")}
    if such:
        eintrag["suchmuster"] = such
    pool = [p for p in pool if p["id"] != eintrag["id"]] + [eintrag]
    pool_speichern(pool)
    return eintrag


def pool_entfernen(pool_id: str | None):
    if pool_id:
        pool_speichern([p for p in pool_laden() if p.get("id") != pool_id])


# ------------------------------------------------------------------ Recherche
def artikel_liste(stunden: float = STUNDEN, jetzt: datetime | None = None) -> list[dict]:
    """Rohmeldungen der letzten Stunden, ohne doppelte URLs/Titel, neueste zuerst, nummeriert ab 1."""
    jetzt = jetzt or datetime.now(timezone.utc)
    cutoff = jetzt - timedelta(hours=stunden)
    gesehen, out = set(), []
    for p in DATA_DIR.glob("raw/*/*.json"):
        try:
            a = json.loads(p.read_text(encoding="utf-8"))
            d = datetime.fromisoformat(a.get("published_at") or a.get("fetched_at"))
        except (OSError, ValueError, TypeError):
            continue
        d = d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        if d < cutoff:
            continue
        schluessel = (a.get("url") or "").split("?")[0] or (a.get("title") or "").lower()
        if not schluessel or schluessel in gesehen:
            continue
        gesehen.add(schluessel)
        out.append({k: a.get(k) for k in ("title", "summary", "snippet", "url", "source", "published_at", "category")})
    out.sort(key=lambda a: a.get("published_at") or "", reverse=True)
    out = out[:MAX_ARTIKEL]
    for i, a in enumerate(out, 1):
        a["nr"] = i
    return out


def gruene_quellen() -> list[str]:
    try:
        d = json.loads(QUELLEN_NETZ.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ["Wikimedia Commons", "DVIDS", "NASA", "Pexels"]
    namen = [q.get("name") or q.get("quelle") for liste in d.get("kategorien", {}).values()
             for q in liste if isinstance(q, dict) and q.get("ampel") == "gruen" and (q.get("name") or q.get("quelle"))]
    # nur echte Bild-/Videoquellen (die Liste enthaelt auch Rechtsgrundlagen und Datenquellen)
    nein = re.compile(r"recht|Content-ID|EuGH|Werke der|Zitat|GDELT|Pew|Census|Destatis|Eurostat|Our World|Audio|"
                      r"Legal Notice|gespiegelt", re.I)
    return list(dict.fromkeys(n for n in namen if not nein.search(n)))


def _sauber(t: str | None) -> str:
    from weltlage_skript import _sauber as s
    return s(t)


def _liste_text(artikel: list[dict]) -> str:
    return "\n".join(f"{a['nr']}. [{a.get('source')}, {(a.get('published_at') or '')[:16]}] {_sauber(a.get('title'))}"
                     f" - {_sauber(a.get('snippet') or a.get('summary'))[:160]}" for a in artikel)


def _prompt(artikel: list[dict], pool: list[dict], feste: dict | None, heute: str) -> str:
    stil = ("Stil wie der YouTube-Kanal «Vermietertagebuch»: eine einzige, klar zugespitzte Frage pro Folge, ein "
            "konkreter Aufhaenger (Person, Zahl, Ort, Frist), Konflikt und Countdown-Gefuehl, nie reisserisch falsch.")
    gruen = ", ".join(gruene_quellen()[:25])
    if feste:
        auftrag = (f"Die Storyline ist bereits gewaehlt: Titel «{feste['titel']}», Inhalt: {feste['inhalt']}\n"
                   "Gib genau EINE Storyline zurueck (Buchstabe A) mit diesem Titel und Inhalt (Inhalt darfst du mit "
                   "frischen Fakten aus der Liste praezisieren) und waehle die passenden Artikel.")
        anzahl = 1
    else:
        pool_txt = "\n".join(f"- {p['titel']} ({p['inhalt']})" for p in pool) or "(leer)"
        auftrag = ("Schlage genau DREI Storylines A, B, C fuer die naechste Folge vor (verschiedene Themen) und "
                   "empfiehl eine davon. Themenpool - diese Storylines will Marlon ausdruecklich auch noch machen; "
                   "biete jede davon an, solange die Liste frische Meldungen dazu enthaelt (Feld pool_id setzen):\n"
                   + pool_txt)
        anzahl = 3
    return f"""Du bist Redaktionsleiter des deutschsprachigen YouTube-Analysekanals «Weltlage Kompakt» (Moderatorin Latara).
Heute ist {heute}. {stil}

{auftrag}

Regeln:
- Jede Storyline stuetzt sich NUR auf Artikel aus der nummerierten Liste unten (mindestens 3 Artikel, moeglichst aus
  verschiedenen Quellen). Gruppiere die Artikel einer Storyline in 2 bis 4 «meldungen» (jede Meldung = Liste von
  Artikelnummern zu einem Teilaspekt, wichtigste zuerst).
- titel: zugespitzte Frage auf Deutsch, hoechstens 70 Zeichen, endet mit «?», nennt Person/Land/Ort.
- inhalt: genau ein Satz auf Deutsch, was die Folge erzaehlt (konkret, mit dem staerksten Fakt).
- gruene_quellen: 1 bis 3 passende frei lizenzierte Bildquellen fuer Symbolbilder aus dieser Liste: {gruen}
- Schweizer Schreibweise (ss statt sz).

Antworte NUR mit JSON:
{{"storylines": [{{"buchstabe": "A", "titel": "...?", "inhalt": "...", "meldungen": [[1, 4, 9], [12, 15]],
   "gruene_quellen": ["..."], "pool_id": null}}{', ...' if anzahl > 1 else ''}],
 "empfehlung": "A", "grund": "ein Satz, warum"}}

ARTIKEL:
{_liste_text(artikel)}
"""


def pruefen(d: dict, artikel: list[dict], anzahl: int) -> list[str]:
    fehler = []
    nrs = {a["nr"] for a in artikel}
    st = d.get("storylines") or []
    if len(st) != anzahl:
        fehler.append(f"genau {anzahl} Storylines verlangt, bekommen {len(st)}")
    for s in st:
        b = s.get("buchstabe")
        if not str(s.get("titel") or "").strip().endswith("?"):
            fehler.append(f"{b}: Titel ist keine Frage")
        if not s.get("inhalt"):
            fehler.append(f"{b}: Inhalt fehlt")
        alle = [n for m in s.get("meldungen") or [] for n in m]
        if len([n for n in alle if n in nrs]) < 2:
            fehler.append(f"{b}: zu wenige gueltige Artikelnummern")
    if anzahl > 1 and d.get("empfehlung") not in [s.get("buchstabe") for s in st]:
        fehler.append("Empfehlung ist keiner der Buchstaben")
    return fehler


def _modell(prompt: str) -> dict:
    from weltlage_skript import frage_modell
    return frage_modell(prompt)


def _heute() -> str:
    from weltlage_skript import MONATE, WOCHENTAGE
    j = datetime.now().astimezone()
    return f"{WOCHENTAGE[j.weekday()]}, {j.day}. {MONATE[j.month - 1]} {j.year}, {j:%H:%M} Uhr"


def vorschlagen(ordner: Path, feste: dict | None = None, modell=None, artikel: list[dict] | None = None) -> dict:
    """Recherche + Storylines. feste = {"titel","inhalt"}: Storyline schon gewaehlt (nur Artikel zuordnen)."""
    modell = modell or _modell
    artikel = artikel if artikel is not None else artikel_liste()
    if not artikel:
        raise RuntimeError("keine Rohmeldungen der letzten Stunden (Pipeline/RSS laeuft nicht?)")
    pool = pool_laden()
    anzahl = 1 if feste else 3
    prompt = _prompt(artikel, pool, feste, _heute())
    d = modell(prompt)
    fehler = pruefen(d, artikel, anzahl)
    if fehler:
        d2 = modell(prompt + "\n\nDein letzter Vorschlag hatte diese Fehler, behebe jeden:\n"
                    + "\n".join(f"- {f}" for f in fehler))
        f2 = pruefen(d2, artikel, anzahl)
        if len(f2) < len(fehler):
            d, fehler = d2, f2
    if fehler:
        raise RuntimeError("Themenvorschlag unbrauchbar: " + "; ".join(fehler))
    if feste:
        d["storylines"][0].update({"buchstabe": "A", "titel": feste["titel"]})
        d["empfehlung"] = "A"
        d.setdefault("grund", "Storyline vorab von Marlon gewaehlt")
    pool_ids = {p["id"] for p in pool}
    for s in d["storylines"]:
        if s.get("pool_id") not in pool_ids:
            s["pool_id"] = None
    d["erstellt"] = datetime.now().astimezone().isoformat(timespec="seconds")
    d["artikel"] = artikel
    ordner.mkdir(parents=True, exist_ok=True)
    (ordner / "storylines.json").write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")
    return d


def storyline(d: dict, buchstabe: str) -> dict:
    return next(s for s in d["storylines"] if s["buchstabe"] == buchstabe)


def news_fuer(d: dict, buchstabe: str) -> list[dict]:
    """news.json der Folge (Format wie weltlage_skript.aktuelle_gruppen) aus den Meldungen der Storyline."""
    nach_nr = {a["nr"]: a for a in d["artikel"]}
    news = []
    for m in storyline(d, buchstabe)["meldungen"]:
        arts = [{k: v for k, v in nach_nr[n].items() if k != "nr"} for n in m if n in nach_nr]
        if arts:
            news.append({"sources": sorted({a.get("source") or "?" for a in arts}), "n": len(arts), "articles": arts})
    return news


def vorgabe_text(s: dict, feedback: str | None = None) -> str:
    z = [f"Storyline: {s['titel']}", f"Inhalt: {s['inhalt']}"]
    if s.get("gruene_quellen"):
        z.append("Passende freie Bildquellen: " + ", ".join(s["gruene_quellen"]))
    if feedback:
        z.append(f"Hinweise von Marlon zur Wahl: {feedback}")
    return "\n".join(z)


def bericht(d: dict, frist: str | None = None, kopf: str = "") -> str:
    """Telegram-/App-Text im Format der Materialsammlung (c7be)."""
    z = [kopf] if kopf else []
    for s in d["storylines"]:
        mark = "  (Empfehlung)" if s["buchstabe"] == d.get("empfehlung") else ""
        n = sum(len(m) for m in s.get("meldungen") or [])
        z.append(f"{s['buchstabe']}{mark}: {s['titel']}\n{s['inhalt']}\n"
                 f"Material: {n} Meldungen, freie Bilder: {', '.join(s.get('gruene_quellen') or []) or '-'}"
                 + ("  [Themenpool]" if s.get("pool_id") else ""))
    if len(d["storylines"]) > 1:
        z.append(f"Meine Empfehlung: {d.get('empfehlung')} - {d.get('grund', '')}")
    if frist:
        z.append(f"Ohne Antwort nehme ich um {frist} die Empfehlung. Antwort: Knopf A/B/C oder Antwort mit "
                 f"Buchstabe plus Hinweis, z.B. «B, mehr zur Rolle Chinas».")
    return "\n\n".join(z)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("vorschlagen")
    v.add_argument("ordner", type=Path)
    sub.add_parser("pool")
    pa = sub.add_parser("pool-add")
    pa.add_argument("titel")
    pa.add_argument("inhalt")
    pa.add_argument("--tage", type=float, default=4)
    a = ap.parse_args()
    if a.cmd == "vorschlagen":
        print(bericht(vorschlagen(a.ordner)))
    elif a.cmd == "pool":
        print(json.dumps(pool_laden(), indent=1, ensure_ascii=False))
    elif a.cmd == "pool-add":
        print(json.dumps(pool_add(a.titel, a.inhalt, a.tage, quelle="manuell"), indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
