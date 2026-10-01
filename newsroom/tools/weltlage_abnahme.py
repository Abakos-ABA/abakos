"""Weltlage Kompakt - Abnahme-Pruefung einer fertigen Folge VOR dem Versand an Marlon (01.10.2026).

    python tools/weltlage_abnahme.py <folgenordner> <master.mp4>

Prueft und schreibt <master>_abnahme.json + <master>_begleittext.txt (Themen, Zitate mit Quellenliste):
  1. Stimme: <master>_stimmen.json (tools/weltlage_stimmpruefung.py) ok, jede Sprechszene Chatterbox mit der
     Referenz des aktiven Profils (config/brand/stimme/profile.json) und dessen Tempo (Nachweis audio/<id>.tts.json).
  2. Lautheit: Master integriert MASTER_LUFS +-1 LU, True Peak <= MASTER_TP + 0,5 dB.
  3. Keine abrupten Lautstaerkespruenge: Lautheit pro Szene (Zeitmarken) gegen die mittlere Sprachlautheit, und
     benachbarte hoerbare Szenen hoechstens SPRUNG_DB auseinander (Raumton/Stille ausgenommen).
  4. Ton: AAC 48 kHz Stereo >= 230 kbps (Erkenntnis 30.09.: gut 237 kbit, nie neu codieren).
  4b. Lipsync-Aufloesung: bei NEWS_WELTLAGE_LIPSYNC_HD an (Standard seit 01.10., Task d71b) muss jedes
     <name>_fenster.json unter <ordner>/_schnitt/_freisteller mit "hd": true gerechnet worden sein (Real-ESRGAN +
     GFPGAN statt Lanczos) und "zoom" >= 768 erreichen, sonst lief die Szene unbemerkt im alten Lanczos-Pfad.
  5. Zitate: alle Zitate aus skript.json geprueft («ok»), jedes steht wortgleich im Sprechtext von texte.json.
  5b. Orte: jeder in texte.json benutzte "ort"-Slug muss in config/brand/orte/orte.json existieren (video/orte.py).
Exit 1, sobald etwas durchfaellt. Veroeffentlicht und verschickt nichts.
"""
import json
import re
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from weltlage_rohschnitt import FFMPEG, FFPROBE, MASTER_LUFS, MASTER_TP, MARKE_UEBER_SPRACHE_DB  # noqa: E402
from video import orte as orte_mod  # noqa: E402
from config.settings import NEWS_WELTLAGE_LIPSYNC_HD  # noqa: E402

SPRUNG_DB = 4.0          # benachbarte hoerbare Szenen duerfen sich hoechstens so stark unterscheiden
SZENE_MAX_UEBER_DB = MARKE_UEBER_SPRACHE_DB + 1.5   # Szene lauter als Sprache
SZENE_MAX_UNTER_DB = 6.0                            # Sprechszene leiser als die mittlere Sprache
TON_MIN_KBPS = 230


def _lautheit(video: Path, start: float | None = None, dauer: float | None = None) -> dict:
    cmd = [FFMPEG, "-hide_banner", "-nostats"]
    if start is not None:
        cmd += ["-ss", f"{start:.3f}", "-t", f"{dauer:.3f}"]
    cmd += ["-i", str(video), "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"]
    e = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stderr
    tail = e[e.rfind("Summary"):]
    val = lambda k: float(re.search(k + r":\s+(-?[\d.]+|-inf)", tail).group(1).replace("-inf", "-120"))
    return {"I": val("I"), "LRA": val("LRA"), "TP": val("Peak")}


def _ton(video: Path) -> dict:
    out = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "a:0", "-show_entries",
                          "stream=codec_name,sample_rate,channels,bit_rate", "-of", "json", str(video)],
                         capture_output=True, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    a = json.loads(out)["streams"][0]
    return {"codec": a["codec_name"], "sr": int(a["sample_rate"]), "ch": int(a["channels"]),
            "kbps": int(a.get("bit_rate", 0)) // 1000}


def _zeitmarken(video: Path) -> list[dict]:
    zm = video.with_name(video.stem + "_zeitmarken.txt")
    szenen = []
    for z in zm.read_text(encoding="utf-8").splitlines():
        m = re.match(r"(\d+):([\d.]+)\s+(.+?) \(([\d.]+) s\)", z)
        if m:
            szenen.append({"start": int(m.group(1)) * 60 + float(m.group(2)), "label": m.group(3),
                           "laenge": float(m.group(4))})
    return szenen


def pruefen(ordner: Path, video: Path) -> dict:
    fehler, info = [], {}
    # 1. Stimme
    profile = json.loads((ROOT / "config/brand/stimme/profile.json").read_text(encoding="utf-8"))
    aktiv = profile["profile"][profile["aktiv"]]
    stimmen = json.loads(video.with_name(video.stem + "_stimmen.json").read_text(encoding="utf-8"))
    if not stimmen.get("ok"):
        fehler.append("Stimmenpruefung im Video nicht bestanden")
    sprech = []
    for s in stimmen["szenen"]:
        nachweis = Path(s["wav"]).with_suffix(".tts.json")
        n = json.loads(nachweis.read_text(encoding="utf-8")) if nachweis.exists() else {}
        ok = (s.get("ok") and s.get("engine") == "chatterbox" and s.get("ref_sha256") == aktiv["ref_sha256"]
              and abs(float(n.get("tempo", -1)) - float(aktiv.get("tempo", 1.0))) < 1e-6)
        sprech.append({"szene": s["label"], "profil": n.get("profil"), "tempo": n.get("tempo"),
                       "korrelation": s.get("korrelation"), "ok": bool(ok)})
        if not ok:
            fehler.append(f"Stimme {s['label']}: nicht Profil {profile['aktiv']} / Tempo {aktiv.get('tempo')}")
    info["stimme"] = {"profil": profile["aktiv"], "name": aktiv["name"][:40], "szenen": sprech}
    # 2. Lautheit gesamt + 3. Spruenge
    g = _lautheit(video)
    info["lautheit"] = {k: g[k] for k in ("I", "LRA", "TP")}
    if abs(g["I"] - MASTER_LUFS) > 1.0:
        fehler.append(f"Lautheit {g['I']} LUFS, Ziel {MASTER_LUFS} +-1")
    if g["TP"] > MASTER_TP + 0.5:
        fehler.append(f"True Peak {g['TP']} dBTP ueber {MASTER_TP}")
    szenen = _zeitmarken(video)
    for s in szenen:
        s["I"] = _lautheit(video, s["start"], s["laenge"])["I"]
    sprache = [s["I"] for s in szenen if s["label"].startswith("Szene Meldung")]
    ref = statistics.median(sprache) if sprache else g["I"]
    info["sprache_lufs"] = ref
    for s in szenen:
        d = s["I"] - ref
        s["abweichung_db"] = round(d, 1)
        if s["I"] < -45:                        # Raumton/Stille (Reinlaufen) zaehlt nicht
            continue
        if d > SZENE_MAX_UEBER_DB:
            fehler.append(f"{s['label']} {d:+.1f} dB lauter als die Sprache")
        sprechszene = s["label"].startswith(("Szene Meldung", "Szene Themen", "Szene Begr", "Szene Verab", "Szene Cold"))
        if sprechszene and d < -SZENE_MAX_UNTER_DB:
            fehler.append(f"{s['label']} {d:+.1f} dB leiser als die Sprache")
    info["szenen"] = [{k: s[k] for k in ("label", "start", "I", "abweichung_db")} for s in szenen]
    # Uebergaenge: benachbarte hoerbare Szenen (Raumton/Stille ausgenommen) duerfen nicht stark springen
    hoerbar = [s for s in szenen if s["I"] >= -45]
    spruenge = [(b["I"] - a["I"], b["label"], b["start"]) for a, b in zip(hoerbar, hoerbar[1:])]
    gross = max(spruenge, key=lambda x: abs(x[0]), default=(0.0, None, None))
    info["groesster_sprung_db"] = round(gross[0], 1)
    info["groesster_sprung_bei"] = gross[1]
    for d, label, start in spruenge:
        if abs(d) > SPRUNG_DB:
            fehler.append(f"Lautstaerkesprung {d:+.1f} dB beim Uebergang zu {label} ({start:.1f} s)")
    # 4. Ton
    t = _ton(video)
    info["ton"] = t
    if not (t["codec"] == "aac" and t["sr"] == 48000 and t["ch"] == 2 and t["kbps"] >= TON_MIN_KBPS):
        fehler.append(f"Ton {t} statt AAC 48 kHz Stereo >= {TON_MIN_KBPS} kbps")
    # 4b. Lipsync-Aufloesung: Gesichtsfenster muss bei aktivem Schalter wirklich KI-hochskaliert worden sein
    fenster_dir = ordner / "_schnitt" / "_freisteller"
    fenster_dateien = sorted(fenster_dir.glob("*_fenster.json")) if fenster_dir.is_dir() else []
    info["lipsync_hd"] = {"erwartet": NEWS_WELTLAGE_LIPSYNC_HD, "szenen": len(fenster_dateien)}
    if NEWS_WELTLAGE_LIPSYNC_HD:
        if not fenster_dateien:
            fehler.append(f"kein _fenster.json unter {fenster_dir} gefunden, Lipsync-Aufloesung nicht pruefbar")
        for fp in fenster_dateien:
            fj = json.loads(fp.read_text(encoding="utf-8"))
            if not fj.get("hd"):
                fehler.append(f"{fp.name}: ohne HD-Hochskalierung gerechnet (Lanczos statt Real-ESRGAN/GFPGAN)")
            elif int(fj.get("zoom") or 0) < 768:
                fehler.append(f"{fp.name}: Gesichtsfenster nur {fj.get('zoom')} px statt mind. 768 px")
    # 5. Zitate
    skp = ordner / "skript.json"
    sk = json.loads(skp.read_text(encoding="utf-8")) if skp.exists() else {"meta": {}, "skript": {}}
    if not skp.exists():
        fehler.append("kein skript.json (Folge nicht mit tools/weltlage_skript.py erzeugt)")
    texte = json.loads((ordner / "texte.json").read_text(encoding="utf-8"))
    # 5b. Orte: jeder in texte.json benutzte Ort-Slug muss in config/brand/orte/orte.json existieren
    bekannte_orte = set(orte_mod.orte())
    info["orte"] = sorted({s.get("ort", "studio") for s in texte["szenen"]})
    unbekannt = sorted({s["ort"] for s in texte["szenen"] if s.get("ort") and s["ort"] not in bekannte_orte})
    if unbekannt:
        fehler.append(f"Unbekannter Ort-Slug in texte.json: {', '.join(unbekannt)} (bekannt: {', '.join(bekannte_orte)})")
    sprechtext = " ".join(s.get("text") or "" for s in texte["szenen"])
    zitate = sk["meta"].get("zitate") or []
    for z in zitate:
        if z.get("pruefung") != "ok":
            fehler.append(f"Zitat {z.get('nr')} nicht geprueft: {z.get('pruefung')}")
        if f"«{z['deutsch']}»" not in sprechtext and z["deutsch"] not in sprechtext:
            fehler.append(f"Zitat {z.get('nr')} steht nicht im Sprechtext")
    info["zitate"] = len(zitate)
    info["zitate_geprueft"] = sum(1 for z in zitate if z.get("pruefung") == "ok")
    if info["zitate_geprueft"] < 3:
        fehler.append("weniger als 3 gepruefte Zitate")
    # Begleittext
    kurz = [s["kurz"] for s in texte["szenen"] if s.get("kurz")]
    zl = [f"{z['nr']} {z['person']} ({z.get('funktion') or ''}, {z.get('kanal')}, {z.get('datum') or ''})"
          f"{' übersetzt' if z.get('uebersetzt') else ''}: «{z['deutsch']}»\n   Quelle: {z['url']}" for z in zitate]
    text = (f"Weltlage Kompakt, Probefolge im neuen Dialog-Format\n{sk['skript'].get('titel')}\n\n"
            f"Themen: {'; '.join(kurz)}\n\n{info['zitate_geprueft']} echte Zitate, Wort für Wort gegen die Quelle "
            f"geprüft:\n" + "\n".join(zl))
    info["begleittext"] = str(video.with_name(video.stem + "_begleittext.txt"))
    Path(info["begleittext"]).write_text(text, encoding="utf-8")
    info["fehler"] = fehler
    info["ok"] = not fehler
    video.with_name(video.stem + "_abnahme.json").write_text(json.dumps(info, indent=1, ensure_ascii=False),
                                                            encoding="utf-8")
    return info


if __name__ == "__main__":
    r = pruefen(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
    print(json.dumps({k: v for k, v in r.items() if k not in ("szenen",)}, indent=1, ensure_ascii=False))
    for s in r["szenen"]:
        print(f"  {s['start']:7.1f}s  {s['I']:6.1f} LUFS  {s['abweichung_db']:+5.1f} dB  {s['label']}")
    print("ABNAHME OK" if r["ok"] else "ABNAHME FEHLER:\n  " + "\n  ".join(r["fehler"]))
    sys.exit(0 if r["ok"] else 1)
