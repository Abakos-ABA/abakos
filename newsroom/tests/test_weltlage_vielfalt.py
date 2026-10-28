"""Test tools/weltlage_vielfalt.py (28.10.2026): Variante je Folge, keine Wiederholung der letzten Formen/Einstiege,
gleiche Folge -> gleiche Wahl, Einordnungs-Hinweis. Offline, Wegwerf-Verlauf.

    .venv\Scripts\python tests\test_weltlage_vielfalt.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import weltlage_vielfalt as wv  # noqa: E402

fails = 0


def check(ok, msg):
    global fails
    print(("OK   " if ok else "FAIL ") + msg)
    fails += 0 if ok else 1


tmp = Path(tempfile.mkdtemp(prefix="wv-")) / "v.json"
w = [wv.waehlen(f"weltlage_202610{t:02d}_1000", tmp) for t in range(1, 21)]
check(all(w[i]["format"] not in {x["format"] for x in w[max(0, i - 3):i]} for i in range(len(w))),
      "keine Erzaehlform wie in den letzten 3 Folgen")
check(all(w[i]["einstieg"] not in {x["einstieg"] for x in w[max(0, i - 2):i]} for i in range(len(w))),
      "kein Einstieg wie in den letzten 2 Folgen")
check(len({x["format"] for x in w}) >= 5, "ueber 20 Folgen kommen mindestens 5 Erzaehlformen vor")
check(wv.waehlen("weltlage_20261005_1000", tmp) == w[4], "gleiche Folge (Neuversuch) -> gleiche Wahl")
b = wv.block(w[0])
check("VARIANTE DIESER FOLGE" in b and "einordnung" in b and str(wv.EINORDNUNG_MIN_WOERTER) in b,
      "Prompt-Block nennt Variante und Einordnungs-Pflicht")
check(wv.einordnung_pruefen({"abschnitte": [{"rolle": "schluss", "text": "x"}]}) != [], "fehlende Einordnung -> Hinweis")
check(wv.einordnung_pruefen({"abschnitte": [{"rolle": "einordnung", "text": "wort " * 20}]}) != [], "zu kurz -> Hinweis")
check(wv.einordnung_pruefen({"abschnitte": [{"rolle": "einordnung", "text": "wort " * 80}]}) == [], "genug -> ok")
print("\nALLE OK" if not fails else f"\n{fails} FEHLER")
sys.exit(1 if fails else 0)
