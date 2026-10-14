"""Speicherplatz fuer den Weltlage-Rohschnitt sichern (Vorfall 14.10.2026, Folge 2026-10-14_19:00).

Jede Folge liess bis dahin rund 16 GB Lipsync-Zwischendateien unter <folge>/_schnitt/_freisteller liegen (vor allem
s5_freisteller_lipsync_prores4444.mov mit 8-12 GB, dazu der Grau-Freisteller und die LatentSync-Stuecke). Niemand
raeumte sie weg; bei zwei Folgen am Tag war C: nach zwei Wochen voll und ffmpeg brach mitten im s5-Lipsync mit
"No space left on device" ab (die Wache sah nur "Rohschnitt fehlgeschlagen").

Vor jedem Rohschnitt ruft der Tageslauf `sichern(ordner)` auf: liegt weniger als MIN_FREI_GB frei, werden bei schon
veroeffentlichten Folgen (Zustand "veroeffentlicht", mindestens HALTE_STUNDEN her) nur die grossen, nachgelagert nie
mehr gebrauchten Zwischendateien geloescht, die aeltesten zuerst. Bleiben stehen: Master/Clips, *_studio.mp4,
*_fenster.json (Abnahme), Ton, Bilder - und jede Folge, auf die config/brand/**/aktiv.json verweist (eingefrorene
Szenen). Reicht es danach immer noch nicht, bricht der Schnitt mit einer klaren Speicher-Meldung ab statt nach
Stunden Rechenzeit.

    python tools/weltlage_speicher.py            # Stand + was geloescht wuerde
    python tools/weltlage_speicher.py --los      # jetzt aufraeumen (bis MIN_FREI_GB frei)
"""
import json
import re
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
BRAND = ROOT / "config" / "brand"
ZUSTAND = ROOT / "state" / "weltlage_tageslauf.json"

MIN_FREI_GB = 60       # eine Folge braucht ~16 GB Zwischendateien + Master/B-Roll; doppelte Reserve
ZIEL_FREI_GB = 120     # wenn schon aufgeraeumt wird, gleich etwas Luft fuer die naechsten Folgen schaffen
HALTE_STUNDEN = 24     # frisch veroeffentlichte Folgen bleiben einen Tag unangetastet (Nachbesserungen)
_GB = 1024 ** 3


class SpeicherVoll(RuntimeError):
    pass


def frei_gb(pfad: Path = DATA) -> float:
    return shutil.disk_usage(pfad).free / _GB


def zwischendateien(ordner: Path) -> list[Path]:
    """Grosse Lipsync-Zwischendateien einer Folge, die nach dem Rohschnitt + B-Roll niemand mehr liest."""
    fw = Path(ordner) / "_schnitt" / "_freisteller"
    if not fw.is_dir():
        return []
    out = sorted(fw.glob("*_freisteller_lipsync_prores4444.mov")) + sorted(fw.glob("*_freisteller_grau25.mp4"))
    if (fw / "_latentsync").is_dir():
        out.append(fw / "_latentsync")
    return out


def _groesse(p: Path) -> int:
    if p.is_dir():
        return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
    return p.stat().st_size if p.exists() else 0


def geschuetzte_ordner(brand: Path = BRAND) -> set[str]:
    """Ordnernamen (weltlage_*), auf die eine eingefrorene Szene in config/brand verweist - nie anfassen."""
    namen = set()
    for f in brand.rglob("aktiv.json"):          # nur eingefrorene Szenen, nicht das Lexikon (nennt nur die Herkunft)
        try:
            txt = f.read_text(encoding="utf-8")
        except OSError:
            continue
        namen.update(re.findall(r"weltlage_\d{8}_[0-9A-Za-z]+", txt))
    return namen


def kandidaten(zustand: dict, jetzt: datetime | None = None, schutz: set[str] | None = None,
               ausser: Path | None = None) -> list[Path]:
    """Ordner veroeffentlichter Folgen, aelteste zuerst, ohne geschuetzte und ohne `ausser` (laufende Folge)."""
    jetzt = jetzt or datetime.now().astimezone()
    schutz = geschuetzte_ordner() if schutz is None else schutz
    gesehen, liste = set(), []
    for key, e in zustand.items():
        if not isinstance(e, dict) or e.get("status") != "veroeffentlicht" or not e.get("ordner"):
            continue
        o = Path(e["ordner"])
        if o.name in schutz or o.name in gesehen or (ausser and o.resolve() == Path(ausser).resolve()):
            continue
        try:
            fertig = datetime.fromisoformat(e.get("fertig") or "")
        except ValueError:
            continue
        if fertig.tzinfo is None:
            fertig = fertig.astimezone()
        if jetzt - fertig < timedelta(hours=HALTE_STUNDEN):
            continue
        gesehen.add(o.name)
        liste.append((fertig, o))
    return [o for _, o in sorted(liste)]


def aufraeumen(ziel_gb: float = ZIEL_FREI_GB, ausser: Path | None = None, log=print, trocken: bool = False,
               zustand: dict | None = None, frei=frei_gb) -> float:
    """Loescht Zwischendateien veroeffentlichter Folgen, bis `ziel_gb` frei sind. Liefert die freigegebenen GB."""
    if zustand is None:
        zustand = json.loads(ZUSTAND.read_text(encoding="utf-8")) if ZUSTAND.exists() else {}
    weg = 0
    for o in kandidaten(zustand, ausser=ausser):
        if not trocken and frei() >= ziel_gb:
            break
        for p in zwischendateien(o):
            g = _groesse(p)
            if not trocken:
                shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)
            weg += g
            log(f"Speicher: {'würde löschen' if trocken else 'gelöscht'} {o.name}/{p.name} ({g / _GB:.1f} GB)")
    return weg / _GB


def sichern(ordner: Path | None = None, log=print, min_gb: float = MIN_FREI_GB, frei=frei_gb, **kw) -> float:
    """Vor dem Rohschnitt: sorgt fuer min_gb freien Platz, sonst SpeicherVoll. Liefert die freien GB danach."""
    vorher = frei()
    if vorher >= min_gb:
        return vorher
    log(f"Speicher: nur {vorher:.1f} GB frei (brauche {min_gb} GB) - räume Zwischendateien alter Folgen auf")
    aufraeumen(ausser=ordner, log=log, frei=frei, **kw)
    nachher = frei()
    log(f"Speicher: jetzt {nachher:.1f} GB frei")
    if nachher < min_gb:
        raise SpeicherVoll(f"Speicher voll: nur {nachher:.1f} GB frei auf dem Laufwerk der Folgen, Rohschnitt "
                           f"braucht {min_gb} GB - Platz schaffen (Downloads, Papierkorb, alte Testordner)")
    return nachher


if __name__ == "__main__":
    los = "--los" in sys.argv
    print(f"frei: {frei_gb():.1f} GB")
    gb = aufraeumen(trocken=not los)
    print(f"{'freigegeben' if los else 'freigebbar'}: {gb:.1f} GB, frei jetzt {frei_gb():.1f} GB")
