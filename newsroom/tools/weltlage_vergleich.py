"""Top-vs-Flop-Vergleich fuer Weltlage Kompakt (Marlon-Auftrag 19.10.2026, Task 20261019-115559-7e79 im
Jarvis-Repo): dasselbe Ziel wie jarvis/tools/jarvis_kanal_vergleich.py (Top- gegen Flop-Videos nebeneinander,
Gemeinsamkeiten mit Zahlen belegt) - aber mit DEUTLICH weniger Daten.

WICHTIGE EINSCHRAENKUNG: tools/weltlage_kanalmanager.analytics_abrufen() liest bisher NUR die Studio-Tabelle
"Deine erfolgreichsten Inhalte in diesem Zeitraum" (Top-10 nach Aufrufen im Studio-Standardzeitraum) - keine
CTR/Impressionen/Bindungskurve/Traffic-Quellen/Suchbegriffe je Video, kein kompletter Kanal-Katalog (anders als
Jarvis KI, siehe jarvis/tools/jarvis_kanal_vielfalt.py: Studio-Videoanalyse je Video). Ein ECHTER Flop-Vergleich
ist darum noch nicht moeglich - Studio zeigt hier gar keine schlecht laufenden Videos an, nur die 10 besten.
Dieses Modul vergleicht deshalb nur Rang 1-3 ("sehr erfolgreich") gegen die letzten 3 Raenge der Top-10-Liste
("noch unter den Top 10, aber am schwaechsten davon") - und markiert diese Einschraenkung im Bericht deutlich.
Die eigentliche Idee (Studio-Videoanalyse je Video wie bei Jarvis KI aufbauen) steht als Vorschlag im
Rueckstau (jarvis/tools/kanal_backlog.py, Kanal "weltlage") statt hier stillschweigend ignoriert zu werden.

    .venv\\Scripts\\python -m tools.weltlage_vergleich bericht   Vergleich schreiben (reports\\weltlage_vergleich\\<Datum>.md)
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from config.settings import STATE_DIR  # noqa: E402

VERLAUF_PFAD = STATE_DIR / "weltlage_kanalmanager" / "analytics_verlauf.json"
BERICHT_DIR = ROOT / "reports" / "weltlage_vergleich"
MIN_INHALTE = 6   # unter dieser Listenlaenge kein belastbarer Rang-Vergleich


def _lesen(pfad: Path, default):
    try:
        return json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


ZAHLWORT_RE = re.compile(r"\b\d+\b")


def titel_merkmale(titel: str) -> dict:
    t = titel or ""
    return {
        "laenge": len(t), "frage": "?" in t, "zahl": bool(ZAHLWORT_RE.search(t)),
        "gedankenstrich": "–" in t or "-" in t,
    }


def _woerter(text: str) -> set[str]:
    stop = {"der", "die", "das", "und", "ist", "im", "in", "mit", "bei", "fuer", "für", "nach", "von", "zu",
            "ein", "eine", "wie", "was", "nur", "noch"}
    return {w for w in re.findall(r"[a-zäöüß0-9]{3,}", (text or "").lower()) if w not in stop}


def juengster_schnappschuss(verlauf: list[dict] | None = None) -> dict | None:
    verlauf = verlauf if verlauf is not None else _lesen(VERLAUF_PFAD, [])
    if not verlauf:
        return None
    return sorted(verlauf, key=lambda e: e.get("abgerufen_um") or "")[-1]


def vergleichen(inhalte: list[dict], n: int = 3) -> dict:
    """Rang 1..n vs. die letzten n Raenge der Liste (schon von Studio nach Aufrufen sortiert)."""
    liste = sorted(inhalte, key=lambda v: v.get("rang", 0))
    if len(liste) < MIN_INHALTE:
        return {"ok": False, "grund": f"nur {len(liste)} Einträge in der Top-Liste, braucht mind. {MIN_INHALTE}"}
    top, flop = liste[:n], liste[-n:]
    top_m = [{**v, **titel_merkmale(v.get("titel"))} for v in top]
    flop_m = [{**v, **titel_merkmale(v.get("titel"))} for v in flop]
    muster = []
    for feld in ("frage", "zahl", "gedankenstrich"):
        t_anteil = sum(1 for v in top_m if v[feld])
        f_anteil = sum(1 for v in flop_m if v[feld])
        if t_anteil != f_anteil:
            muster.append({"merkmal": feld, "top": f"{t_anteil}/{len(top_m)}", "flop": f"{f_anteil}/{len(flop_m)}"})
    laenge_top = sum(v["laenge"] for v in top_m) / len(top_m)
    laenge_flop = sum(v["laenge"] for v in flop_m) / len(flop_m)
    gemeinsame_woerter = set.union(*[_woerter(v.get("titel")) for v in top_m]) & \
                        set.union(*[_woerter(v.get("titel")) for v in flop_m])
    return {"ok": True, "n": n, "top": top_m, "flop": flop_m, "muster": muster,
            "laenge_mittel": {"top": round(laenge_top, 1), "flop": round(laenge_flop, 1)},
            "gemeinsame_woerter": sorted(gemeinsame_woerter)}


def bericht(verlauf: list[dict] | None = None, n: int = 3, pfad: Path | None = None) -> Path:
    schnappschuss = juengster_schnappschuss(verlauf)
    heute = dt.date.today().isoformat()
    pfad = Path(pfad or (BERICHT_DIR / f"{heute}.md"))
    z = [f"# Weltlage Kompakt – Top-/Flop-Vergleich (Stand {heute})", "",
        "**Einschraenkung** (siehe Modul-Doku `tools/weltlage_vergleich.py`): Studio liefert hier nur die Top-10 "
        "\"erfolgreichsten Inhalte\" des Zeitraums - keine CTR/Impressionen/Bindung/Traffic-Quellen je Video, kein "
        "Katalog aller Videos. Es gibt deshalb noch KEINEN echten Top-vs-Flop-Vergleich, nur Rang 1-N gegen die "
        "letzten N RAENGE INNERHALB der Top-10. Siehe Vorschlag im Rueckstau "
        "(`jarvis\\tools\\kanal_backlog.py liste --kanal weltlage`).", ""]
    if not schnappschuss:
        z.append("Noch kein Analytics-Verlauf vorhanden.")
    else:
        z.append(f"Grundlage: Schnappschuss vom {schnappschuss.get('abgerufen_um', '?')}.")
        z.append("")
        vgl = vergleichen(schnappschuss.get("inhalte") or [], n=n)
        if not vgl.get("ok"):
            z.append(f"Kein Vergleich moeglich: {vgl.get('grund')}.")
        else:
            z += ["## Top (Rang 1-{})".format(vgl["n"]), ""]
            z += ["| Rang | Titel | Aufrufe | Laenge | Frage | Zahl |", "|---|---|---|---|---|---|"]
            for v in vgl["top"]:
                z.append(f"| {v['rang']} | {v['titel'][:70]} | {v.get('aufrufe')} | {v['laenge']} | "
                         f"{'ja' if v['frage'] else 'nein'} | {'ja' if v['zahl'] else 'nein'} |")
            z += ["", f"## Flop (letzte {vgl['n']} Raenge der Top-10)", ""]
            z += ["| Rang | Titel | Aufrufe | Laenge | Frage | Zahl |", "|---|---|---|---|---|---|"]
            for v in vgl["flop"]:
                z.append(f"| {v['rang']} | {v['titel'][:70]} | {v.get('aufrufe')} | {v['laenge']} | "
                         f"{'ja' if v['frage'] else 'nein'} | {'ja' if v['zahl'] else 'nein'} |")
            z += ["", "## Muster", ""]
            if vgl["muster"]:
                for m in vgl["muster"]:
                    z.append(f"- **{m['merkmal']}**: Top {m['top']}, Flop {m['flop']}")
            else:
                z.append("- Keine der geprueften Titel-Merkmale (Frage, Zahl, Gedankenstrich) unterscheidet sich.")
            z.append(f"- Titellaenge Ø: Top {vgl['laenge_mittel']['top']}, Flop {vgl['laenge_mittel']['flop']} Zeichen")
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text("\n".join(z) + "\n", encoding="utf-8")
    return pfad


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("bericht")
    args = ap.parse_args()
    if args.cmd == "bericht":
        print(str(bericht()))
    else:
        print(__doc__)
