"""Lataras Stimm-Profile (Chatterbox-Klon): welche Referenz + Parameter die Erzeugung nutzt.

Quelle: config/brand/stimme/profile.json ("aktiv": "A" | "B"); die Umgebungsvariable NEWS_STIMME_PROFIL
uebersteuert "aktiv" (z.B. fuer Proben). Profil A = Stand 30.09.2026 (voice_ref.wav, ex 0.4, cfg 0.4, Absaetze
bis 280 Zeichen), Profil B = optimiert (Task 20260930-182721-1dc4). Umschalten auf B erst nach Marlons Wahl:

    python tts/stimme_profil.py            # zeigt das aktive Profil
    python tts/stimme_profil.py B          # setzt "aktiv" auf B (danach Begruessung neu bauen, siehe README)
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATEI = ROOT / "config" / "brand" / "stimme" / "profile.json"


def alle() -> dict:
    return json.loads(DATEI.read_text(encoding="utf-8"))


def profil(name: str | None = None) -> dict:
    """Profil-Dict mit absolutem 'ref_pfad'; ohne Namen das aktive (NEWS_STIMME_PROFIL > profile.json)."""
    d = alle()
    name = name or os.environ.get("NEWS_STIMME_PROFIL") or d["aktiv"]
    p = dict(d["profile"][name], profil=name)
    p["ref_pfad"] = ROOT / p["ref"]
    return p


def figur_ref_hashes(name: str | None = None) -> set[str]:
    """Referenz-Hashes, die als dieselbe Figur gelten: das (aktive) Profil plus seine "kompatibel_mit"-Profile
    (18.10.2026: G = Kerstin mit lebendigerer Referenz, C = bisherige Kerstin-Referenz - eine Folge, deren Szenen
    schon mit C gesprochen sind, besteht Stimm- und Abnahmepruefung weiter; neue Szenen spricht G)."""
    d = alle()
    name = name or os.environ.get("NEWS_STIMME_PROFIL") or d["aktiv"]
    p = d["profile"][name]
    return {p["ref_sha256"]} | {d["profile"][k]["ref_sha256"] for k in p.get("kompatibel_mit", []) if k in d["profile"]}


def bekannte_ref_hashes() -> set[str]:
    return {p["ref_sha256"] for p in alle()["profile"].values()}


if __name__ == "__main__":
    if sys.argv[1:]:
        d = alle()
        if sys.argv[1] not in d["profile"]:
            raise SystemExit(f"unbekanntes Profil {sys.argv[1]} (vorhanden: {', '.join(d['profile'])})")
        d["aktiv"] = sys.argv[1]
        DATEI.write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: str(v) for k, v in profil().items()}, indent=1, ensure_ascii=False))
