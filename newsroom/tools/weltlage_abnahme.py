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
     Dazu muss "guidance" jedes _fenster.json dem Standard NEWS_WELTLAGE_LIPSYNC_GUIDANCE entsprechen (02.10.2026:
     Stuecke mit 1,5 aus einem abgebrochenen Lauf duerfen nie in einer 2,0-Folge landen).
  4c. Feste Szenen (Intro/Reinlaufen/Begruessung/Logo-Wisch/Verabschiedung/Outro-Grafik): ihre Laenge im Video
     muss zur aktuell aktiven Fassung (jeweilige aktiv.json) passen, sonst steckt eine veraltete Fassung aus einem
     Render drin, der vor einer spaeteren Aenderung losgelaufen ist.
  4d. Welt-Bumper: der Ton am Ende der Szene "Cold Open + Welt-Bumper" muss der aktiven Bumper-Datei
     (bumper/aktiv.json) entsprechen (Kreuzkorrelation >= BUMPER_MIN_KORR). 4c sieht das nicht: ein neuer Bumper-Ton
     hat dieselbe Bildlaenge (Vorfall 02.10.2026: Marlon bekam eine Folge mit dem alten Bumper-Ton).
  4e. Eingefrorene Sprechszenen (Begruessung/Verabschiedung): 4c prueft nur, ob das Video die aktuell aktive
     Datei verwendet, nicht, mit welcher Lipsync-Staerke/HD-Stufe genau diese Datei gebaut wurde. Darum zusaetzlich
     deren aktiv.json gegen NEWS_WELTLAGE_LIPSYNC_GUIDANCE/_HD pruefen (Task 20261002-163146-afaf, 02.10.2026):
     sonst koennte eine mit alter Staerke (z.B. 1,5) eingefrorene Fassung unbemerkt in einer 2,0-Folge landen.
     Fehlt das Feld (Fassung von vor diesem Datum, z.B. begruessung_v3.mp4), nur eine Warnung, kein Abbruch.
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
from weltlage_rohschnitt import (FFMPEG, FFPROBE, MASTER_LUFS, MASTER_TP, MARKE_UEBER_SPRACHE_DB,  # noqa: E402
                                  dur, INTRO, SZENE3, BEGRUESSUNG, UEBERGANG, OUTRO, BUMPER, VERABSCHIEDUNG, FPS)
from video import orte as orte_mod  # noqa: E402
from config.settings import NEWS_WELTLAGE_LIPSYNC_HD, NEWS_WELTLAGE_LIPSYNC_GUIDANCE  # noqa: E402

SPRUNG_DB = 4.0          # benachbarte hoerbare Szenen duerfen sich hoechstens so stark unterscheiden
SZENE_MAX_UEBER_DB = MARKE_UEBER_SPRACHE_DB + 1.5   # Szene lauter als Sprache
SZENE_MAX_UNTER_DB = 6.0                            # Sprechszene leiser als die mittlere Sprache
TON_MIN_KBPS = 230
BUMPER_MIN_KORR = 0.6    # Bumper-Ton im Master vs. aktive Bumper-Datei (Pegel/Crossfade aendern wenig, fremder Ton < 0,3)


def guidance_probleme(meta: dict, guidance: float, hd: bool) -> list[str]:
    """Vergleicht die beim Bau einer eingefrorenen Sprechszene (Begruessung/Verabschiedung) verwendete
    Lipsync-Staerke/HD-Stufe (aktiv.json-Felder "guidance"/"hd") gegen die aktuellen Einstellungen. Leere Liste =
    passt (oder Fassung von vor 02.10.2026 ohne die Felder, dafuer siehe Rueckgabe mit "aktiv.json ohne..."). Pure
    Funktion (kein Dateizugriff) - direkt testbar."""
    if "guidance" not in meta:
        return ["aktiv.json ohne 'guidance'-Feld (gebaut vor 02.10.2026) - Staerke beim Bau nicht geprueft, "
                "bei Zweifel neu bauen (build + freeze)"]
    probleme = []
    if abs(float(meta["guidance"]) - guidance) > 1e-6:
        probleme.append(f"eingefroren mit Guidance {meta['guidance']} statt Standard {guidance:g}")
    if bool(meta.get("hd", False)) != bool(hd):
        probleme.append(f"eingefroren mit hd={meta.get('hd', False)} statt Standard {hd}")
    return probleme


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
    fehler, warnungen, info = [], [], {}
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
    # 4c. Feste, eingefrorene Szenen (Intro/Reinlaufen/Begruessung/Logo-Wisch/Outro-Grafik): ihre Laenge im Video
    #     muss zur aktuell aktiven Fassung passen. Weicht sie ab, lief der Render vor einer spaeteren Aenderung an
    #     der jeweiligen aktiv.json los und hat die alte Fassung eingebacken (Task 20261001-202910-0180: Szene
    #     Reinlaufen lief ungekuerzt mit, obwohl szene3_auftritt/aktiv.json laengst die gekuerzte Fassung zeigte).
    fest = {"Szene Intro": INTRO, "Szene Reinlaufen": SZENE3, "Szene Begrüssung": BEGRUESSUNG,
            "Logo-Wisch": UEBERGANG, "Szene Verabschiedung": VERABSCHIEDUNG, "Szene Outro-Grafik": OUTRO}
    laenge_im_video = {s["label"]: s["laenge"] for s in szenen}
    info["feste_szenen"] = {}
    for label, pfad in fest.items():
        if not (pfad and pfad.exists()) or label not in laenge_im_video:
            continue
        soll, ist = round(dur(pfad), 2), laenge_im_video[label]
        info["feste_szenen"][label] = {"soll": soll, "ist": ist}
        if abs(ist - soll) > 0.1:
            fehler.append(f"{label}: {ist:.2f} s im Video, aktuell eingefroren sind {soll:.2f} s ({pfad.name}) - "
                          f"Render lief vor einer Aenderung an der zugehoerigen aktiv.json, Folge neu rendern")
    # 4e. Eingefrorene Sprechszenen: Lipsync-Staerke/HD-Stufe beim Bau gegen die aktuellen Einstellungen (4c sieht
    # nur die Laenge, nicht wie die aktive Datei gebaut wurde).
    info["feste_sprechszenen_staerke"] = {}
    for label, ordner_name in (("Szene Begrüssung", "begruessung"), ("Szene Verabschiedung", "verabschiedung")):
        cfg = ROOT / "config" / "brand" / ordner_name / "aktiv.json"
        if not cfg.exists() or label not in laenge_im_video:
            continue
        meta = json.loads(cfg.read_text(encoding="utf-8"))
        probleme = guidance_probleme(meta, NEWS_WELTLAGE_LIPSYNC_GUIDANCE, NEWS_WELTLAGE_LIPSYNC_HD)
        info["feste_sprechszenen_staerke"][label] = {"guidance": meta.get("guidance"), "hd": meta.get("hd"),
                                                      "probleme": probleme}
        if probleme and "guidance" not in meta:
            warnungen.append(f"{label}: {probleme[0]}")
        elif probleme:
            fehler.append(f"{label}: " + "; ".join(probleme) + " - neu bauen (build + freeze)")
    # 4d. Welt-Bumper-Ton: gleiche Laenge wie frueher, darum per Kreuzkorrelation gegen die aktive Datei pruefen
    cob = next((s for s in szenen if "Welt-Bumper" in s["label"]), None)
    if BUMPER and BUMPER.exists() and cob:
        from weltlage_stimmpruefung import _lade, korrelation
        Lb = round(dur(BUMPER) * FPS) / FPS
        k = korrelation(_lade(video), cob["start"] + cob["laenge"] - Lb, Lb, _lade(BUMPER), 0.0)
        info["bumper"] = {"datei": BUMPER.name, "korrelation": round(k, 3)}
        if k < BUMPER_MIN_KORR:
            fehler.append(f"Welt-Bumper: Ton im Video passt nicht zur aktiven Fassung {BUMPER.name} (Korrelation "
                          f"{k:.2f} < {BUMPER_MIN_KORR}) - Render lief vor einem Bumper-Wechsel, Folge neu rendern")
    elif BUMPER and BUMPER.exists():
        fehler.append("Welt-Bumper aktiv, aber keine Szene 'Welt-Bumper' in den Zeitmarken")
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
    info["lipsync_guidance"] = {"erwartet": NEWS_WELTLAGE_LIPSYNC_GUIDANCE, "szenen": {}}
    for fp in fenster_dateien:
        g = json.loads(fp.read_text(encoding="utf-8")).get("guidance")
        info["lipsync_guidance"]["szenen"][fp.name] = g
        if g is None or abs(float(g) - NEWS_WELTLAGE_LIPSYNC_GUIDANCE) > 1e-6:
            fehler.append(f"{fp.name}: Lipsync-Guidance {g} statt Standard {NEWS_WELTLAGE_LIPSYNC_GUIDANCE:g}")
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
    info["warnungen"] = warnungen
    info["ok"] = not fehler
    video.with_name(video.stem + "_abnahme.json").write_text(json.dumps(info, indent=1, ensure_ascii=False),
                                                            encoding="utf-8")
    return info


if __name__ == "__main__":
    r = pruefen(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
    print(json.dumps({k: v for k, v in r.items() if k not in ("szenen",)}, indent=1, ensure_ascii=False))
    for s in r["szenen"]:
        print(f"  {s['start']:7.1f}s  {s['I']:6.1f} LUFS  {s['abweichung_db']:+5.1f} dB  {s['label']}")
    if r["warnungen"]:
        print("WARNUNG:\n  " + "\n  ".join(r["warnungen"]))
    print("ABNAHME OK" if r["ok"] else "ABNAHME FEHLER:\n  " + "\n  ".join(r["fehler"]))
    sys.exit(0 if r["ok"] else 1)
