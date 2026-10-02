"""Weltlage Kompakt - Skript-Generator fuer eine Folge (Langformat), Stand 01.10.2026.

Baut aus aktuellen Meldungen (RSS der Pipeline, gruppiert wie im Collector) oder aus einem Transkript ein Folgen-Skript
mit dem Standard-Prompt config/prompts/weltlage_analyse.md (Redaktions-/Analyse-Konzept von Marlon, 01.10.2026) bzw.
dem Fallback config/prompts/weltlage_klassisch.md (bisheriges Meldungsformat). Umschalten in .env:

    NEWS_WELTLAGE_SKRIPT_PROMPT=analyse|klassisch   (oder pro Lauf --prompt)
    NEWS_WELTLAGE_SKRIPT_LLM=claude|ollama          (claude = CLI im Abo, keine GPU; ollama = NEWS_MODEL_SCRIPT)

Ausgabe im Folgenordner (Standard data/weltlage_<datum>[_suffix]):
    material.txt       Ausgangsmaterial genau so, wie es das Modell bekam (zum Nachpruefen der Belege)
    news.json          gewaehlte Meldungsgruppen (gleiches Format wie bisher, Grundlage fuer bilder_holen)
    skript.json        Rohantwort des Modells + Pruefergebnis (Titel-Varianten, Thumbnail-Text, These, Belege ...)
    skript.md          lesbare Fassung mit Bild-Markern fuer Marlon/Telegram
    texte.entwurf.json Szenen im texte.json-Format (s_coldopen, Meldungs-/Analyse-Abschnitte als Szene 5, s6_outro,
                       s_themen aus den "kurz"-Feldern); Bild-Marker sind aus "text" entfernt und stehen in "marker".
                       Jede Szene hat ein Feld "ort" (config/brand/orte/orte.json, video/orte.py): Cold Open/Themen/
                       Outro immer "studio", ein Meldungs-Abschnitt "bruessel" bei einem EU-Thema, "nahost" bei
                       einem Nahost-Thema, "hoersaal" bei Rolle "kontext" (Erklaerteil), sonst "studio"
                       (ort_fuer_abschnitt). Mit --texte wird daraus direkt texte.json (ueberschreibt nie eine
                       vorhandene ohne --texte).

    python tools/weltlage_skript.py [--ordner DIR] [--meldungen 6] [--transkript DATEI] [--prompt analyse]
                                    [--laenge folge|lang|doku] [--texte]
    python tools/weltlage_skript.py --news data/weltlage_20260930d/news.json   (vorhandene Meldungen wiederverwenden)

Paket-Regeln (01.10.2026, nur Prompt analyse, paket_pruefen): Hook nennt alle Themen in ein bis zwei Saetzen mit
Namen, Titel <= 70 Zeichen mit Personenname, Thumbnail-Felder (banderole/zeile1/zeile2/farbe), Ich-Form mit
markierten Meinungssaetzen, genau eine konkrete Kommentarfrage als letzter Satz.

Veroeffentlicht nichts, rendert nichts, keine GPU (ausser mit NEWS_WELTLAGE_SKRIPT_LLM=ollama).
"""
import argparse
import html
import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config.settings import (DATA_DIR, NEWS_CLAUDE_CLI, NEWS_MODEL_SCRIPT, NEWS_WELTLAGE_SKRIPT_LLM,  # noqa: E402
                             NEWS_WELTLAGE_SKRIPT_LAENGE, NEWS_WELTLAGE_SKRIPT_MODELL, NEWS_WELTLAGE_SKRIPT_PROMPT,
                             PROMPTS_DIR)
from weltlage_text_gen import build_themen_text  # noqa: E402

logger = logging.getLogger("weltlage_skript")

VOLLTEXT_ZEICHEN = 4000  # Zitate stehen oft erst weiter unten im Artikel (vorher 2500)
MIN_ZITATE = 3           # darunter harter Fehler (Prompt verlangt mindestens 4)
ZITAT_RE = re.compile(r"«([^«»]{8,})»")
MARKER_RE = re.compile(r"\[(BILD|KARTE|NEWS-CLIP|GRAFIK|HEADLINE EINBLENDEN):\s*([^\]]+)\]")
NEWS_SPRACHE = ["Heute werfen wir einen Blick", "Wie berichtet wurde", "Laut Medienberichten",
                "In einer aktuellen Entwicklung", "Zusammenfassend lässt sich sagen"]
OUTRO = {"id": "s6_outro", "szene": 6, "abo_at": 4.6,
         "text": "Das war Weltlage Kompakt für heute. Morgen bin ich wieder hier mit der Weltlage. Wenn du nichts "
                 "verpassen willst, abonniere den Kanal. Danke fürs Zuschauen, bis morgen."}
# Ort pro Szene (Marlon 01.10.2026, Task 20261001-182941-f24c): Latara steht vor einem zum Thema passenden
# Hintergrund statt immer im Studio (config/brand/orte/orte.json, video/orte.py). Reihenfolge wie von Marlon
# vorgegeben: EU-Thema -> Bruessel, Nahost-Thema -> Nahost, Erklaer-Abschnitt (Rolle "kontext") -> Hoersaal,
# sonst/Standard -> Studio. Cold Open/Themen/Outro bleiben immer im Studio (mischen mehrere Themen).
ORT_EU_RE = re.compile(r"\b(EU|Europäische Union|Europäischen Union|Europaparlament|EU-Parlament|EU-Kommission|"
                      r"Europäische Kommission|Brüssel|von der Leyen|EU-Gipfel|Ministerrat|Mitgliedstaaten)\b")
ORT_NAHOST_RE = re.compile(r"\b(Israel\w*|Gaza\w*|Nahost|Nahen Ostens?|Teheran|Iran\w*|Hamas|Hisbollah|Libanon\w*|"
                          r"Syrien\w*|Jerusalem|Beirut|Netanyahu\w*|Khamenei\w*)\b")


def ort_fuer_abschnitt(a: dict) -> str:
    text = f"{a.get('kurz') or ''} {a.get('text') or ''}"
    if ORT_EU_RE.search(text):
        return "bruessel"
    if ORT_NAHOST_RE.search(text):
        return "nahost"
    if a.get("rolle") == "kontext":
        return "hoersaal"
    return "studio"
# Ziellaenge des Sprechtexts ohne Hook (Analyse-Prompt, Platzhalter {{LAENGE}}). "folge" (Standard seit 01.10.2026):
# fertige Folge rund 4 bis 5 Minuten wie die bisherigen (Kerstin Tempo 1.15 spricht ~145 Woerter/min; dazu Cold Open,
# Themen, feste Teile ~1:10). Gekuerzt wird ueber weniger Nebenstraenge, nie ueber weniger Zitate.
LAENGEN = {
    "folge": (380, 520, "Gesamtlänge des Sprechtexts ohne Hook: 380 bis 520 Wörter (etwa 2,5 bis 3,5 Minuten; die "
                        "fertige Folge dauert damit rund vier bis fünf Minuten). Höchstens 5 Abschnitte. Kürze über "
                        "weniger Nebenstränge: konzentriere dich auf die stärkste Geschichte und höchstens eine "
                        "verbundene zweite, lass Meldungen weg, die den roten Faden nicht tragen, und fasse "
                        "Ausgangslage/Wendepunkt oder Relevanz/Einordnung zusammen, wenn das kürzer ist. Die Zitate "
                        "werden NICHT gekürzt: auch in der kurzen Fassung mindestens 4 echte Zitate."),
    "lang": (700, 1300, "Gesamtlänge des Sprechtexts ohne Hook: 700 bis 1300 Wörter (etwa 5 bis 9 Minuten)."),
    "doku": (1300, 2700, "Gesamtlänge des Sprechtexts ohne Hook: 1300 bis 2700 Wörter (etwa 10 bis 20 Minuten als "
                        "lange Folge). Nutze alle Abschnittsrollen der Dramaturgie (Ausgangslage, Wendepunkt, "
                        "Kontext, Verbindung, Gegenargument, Relevanz, Einordnung, Schluss) und vertiefe jede mit "
                        "mehr Fakten, Beispielen und Zitaten aus dem Material statt Nebenstränge zu streichen: was "
                        "in einer kürzeren Fassung aus Längengründen wegfallen würde, darf hier wieder hinein, wenn "
                        "es echt im Material belegt ist. Ziel 6 bis 10 geprüfte Zitate von mindestens 3 "
                        "verschiedenen Personen, über das ganze Skript verteilt, nicht nur in einem Abschnitt."),
}
WOCHENTAGE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
MONATE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
          "November", "Dezember"]


# ------------------------------------------------------------------ Material
def _sauber(text: str | None) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text or ""))).strip()


def aktuelle_gruppen(anzahl: int, abholen: bool = True) -> list[dict]:
    """Aktuelle Meldungsgruppen wie der Collector sie bildet (TF-IDF ueber verschiedene Quellen), aber ohne Jobs
    anzulegen und ohne die bereits fuer Shorts verbrauchten Artikel auszuschliessen. Format = news.json."""
    from collector.dedupe_cluster import _group_articles, sources_of
    from collector.sources import load_sources

    if abholen:
        from collector.fetch import fetch_all
        fetch_all()
    cfg = load_sources()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=cfg.get("lookback_hours", 18) + 6)
    artikel = []
    for p in DATA_DIR.glob("raw/*/*.json"):
        a = json.loads(p.read_text(encoding="utf-8"))
        stempel = a.get("published_at") or a.get("fetched_at")
        try:
            d = datetime.fromisoformat(stempel)
            d = d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            continue
        if d >= cutoff:
            artikel.append(a)
    gruppen = [[artikel[i] for i in g] for g in _group_articles(artikel)] if artikel else []
    gruppen = [g for g in gruppen if len(sources_of(g)) >= cfg.get("min_corroboration", 2)]
    gruppen.sort(key=lambda g: (len(sources_of(g)), len(g)), reverse=True)
    news = []
    for g in gruppen[:anzahl]:
        g.sort(key=lambda a: a.get("published_at") or "", reverse=True)
        news.append({"sources": sorted(sources_of(g)), "n": len(g),
                     "articles": [{k: a.get(k) for k in ("title", "summary", "snippet", "url", "source",
                                                          "published_at", "category")} for a in g]})
    return news


def material_aus_news(news: list[dict], volltext: bool) -> str:
    """Nummeriertes Ausgangsmaterial fuer den Prompt: pro Meldung Schlagzeilen, Auszuege, Quellen, optional Volltext
    der ersten zwei Artikel (gekuerzt, nur als Faktengrundlage)."""
    teile = []
    for nr, m in enumerate(news, 1):
        zeilen = [f"=== MELDUNG {nr} ({len(m['sources'])} Quellen: {', '.join(m['sources'])}) ==="]
        for a in m["articles"][:8]:
            zeilen.append(f"- [{a.get('source')}, {(a.get('published_at') or '')[:16]}] {_sauber(a.get('title'))}")
            auszug = _sauber(a.get("snippet") or a.get("summary"))
            if auszug:
                zeilen.append(f"  {auszug[:400]}")
        if volltext:
            from research.fetch_fulltext import fetch_clean_text
            n = 0
            for a in m["articles"]:
                if n >= 2:
                    break
                t = fetch_clean_text(a["url"]) if a.get("url") else None
                if t and len(t) > 400:
                    # Link + Datum mit dabei: woertliche Zitate aus dem Artikel werden mit genau diesem Link belegt
                    zeilen.append(f"  Volltext-Auszug ({a.get('source')}, {(a.get('published_at') or '')[:10]}, "
                                  f"{a['url']}): {_sauber(t)[:VOLLTEXT_ZEICHEN]}")
                    n += 1
        teile.append("\n".join(zeilen))
    return "\n\n".join(teile)


def vorgabe_block(vorgabe: str) -> str:
    """Storyline aus der Themenwahl (zweimal taeglich, Marlons Wahl A/B/C + Freitext) als verbindliche Vorgabe."""
    return ("\n\nREDAKTIONELLE VORGABE FUER DIESE FOLGE (verbindlich, hat Vorrang vor deiner eigenen Themenauswahl):\n"
            + vorgabe.strip() + "\n- Die ganze Folge erzaehlt genau diese eine Storyline; andere Meldungen nur, wenn "
            "sie direkt dazugehoeren.\n- Der Titel ist eine zugespitzte Frage im Stil der Vorgabe (nie faktisch "
            "falsch).\n- Hinweise von Marlon setzt du um, solange sie den Fakten im Material nicht widersprechen.\n")


# ------------------------------------------------------------------ LLM
def _claude(prompt: str) -> str:
    cli = NEWS_CLAUDE_CLI
    if not Path(cli).exists():
        raise RuntimeError(f"Claude-CLI nicht gefunden: {cli} (NEWS_CLAUDE_CLI setzen oder NEWS_WELTLAGE_SKRIPT_LLM=ollama)")
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN")}
    cmd = [cli, "-p", "--output-format", "json", "--model", NEWS_WELTLAGE_SKRIPT_MODELL, "--setting-sources", "",
           "--tools", "", "--max-turns", "1"]
    p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=900, env=env, cwd=str(ROOT), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        daten = json.loads(p.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        raise RuntimeError(f"Claude-CLI ohne lesbare Antwort: {(p.stderr or p.stdout)[-500:]}")
    if daten.get("is_error") or p.returncode != 0:
        raise RuntimeError(f"Claude-CLI Fehler: {str(daten.get('result') or daten.get('subtype'))[:500]}")
    return daten.get("result") or ""


def frage_modell(prompt: str) -> dict:
    if NEWS_WELTLAGE_SKRIPT_LLM == "ollama":
        from config.llm_client import call_json
        return call_json(prompt, model=NEWS_MODEL_SCRIPT, max_tokens=8000)
    from config.llm_client import _extract_json
    text = _claude(prompt)
    try:
        return _extract_json(text)
    except json.JSONDecodeError:
        text = _claude(prompt + "\n\nWICHTIG: Antworte nur mit dem JSON-Objekt, ohne Text davor oder danach.")
        return _extract_json(text)


# ------------------------------------------------------------------ Pruefen
def _ss(o):
    if isinstance(o, str):
        return o.replace("ß", "ss")
    if isinstance(o, list):
        return [_ss(x) for x in o]
    if isinstance(o, dict):
        return {k: _ss(v) for k, v in o.items()}
    return o


def sprechtext(text: str) -> str:
    return re.sub(r"\s+([.,!?])", r"\1", re.sub(r"\s{2,}", " ", MARKER_RE.sub("", text))).strip()


def pruefen(s: dict, anzahl_meldungen: int, prompt_name: str, laenge: str = "lang") -> tuple[list[str], list[str]]:
    """(harte Probleme -> ein Neuversuch mit Rueckmeldung, Hinweise -> nur im Bericht)."""
    hart, hinweis = [], []
    for feld in ("titel", "thumbnail_text", "zentrale_these", "hook"):
        if not str(s.get(feld) or "").strip():
            hart.append(f"Feld «{feld}» fehlt oder ist leer.")
    abschnitte = s.get("abschnitte") or []
    if not abschnitte:
        hart.append("Keine Abschnitte.")
    if len(s.get("titel_varianten") or []) != 3:
        hart.append("Es müssen genau drei Titel-Varianten sein.")
    for t in s.get("titel_varianten") or []:
        if len(t) > 75:
            hart.append(f"Titel zu lang ({len(t)} Zeichen): {t}")
    w = len(str(s.get("thumbnail_text") or "").split())
    if not 2 <= w <= 5:
        hart.append(f"Thumbnail-Text muss 2 bis 5 Wörter haben, hat {w}.")
    if "Das alles gleich in Weltlage Kompakt" not in str(s.get("hook")):
        hart.append("Der Hook muss mit «Das alles gleich in Weltlage Kompakt.» enden.")
    hook_w = len(sprechtext(str(s.get("hook") or "")).split())
    if hook_w > 75:
        hinweis.append(f"Hook mit {hook_w} Wörtern eher lang (Ziel 30 bis 60).")
    for i, a in enumerate(abschnitte, 1):
        if not a.get("kurz") or not a.get("text"):
            hart.append(f"Abschnitt {i}: «kurz» oder «text» fehlt.")
        if not a.get("meldungen") or not all(isinstance(n, int) and 1 <= n <= anzahl_meldungen for n in a["meldungen"]):
            hart.append(f"Abschnitt {i}: «meldungen» muss gültige Nummern 1 bis {anzahl_meldungen} enthalten.")
        if len(MARKER_RE.findall(a.get("text") or "")) > 3:
            hinweis.append(f"Abschnitt {i}: mehr als drei Bild-Marker.")
    if prompt_name == "analyse" and anzahl_meldungen > 1:
        verb = [a for a in abschnitte if a.get("rolle") == "verbindung"]
        if not verb:
            hart.append("Abschnitt «verbindung» fehlt (Pflicht bei mehreren Meldungen: A und B ergeben ein grösseres Bild).")
        elif not any(len(set(a.get("meldungen") or [])) >= 2 for a in verb):
            hart.append("Der Abschnitt «verbindung» muss sich auf mindestens zwei Meldungen stützen.")
        if not any(a.get("rolle") == "gegenargument" for a in abschnitte):
            hinweis.append("Kein eigener Abschnitt «gegenargument» (alternative Erklärung).")
    alles = " ".join([str(s.get("hook") or "")] + [a.get("text") or "" for a in abschnitte])
    for floskel in NEWS_SPRACHE:
        if floskel.lower() in alles.lower():
            hart.append(f"Verbotene News-Floskel im Skript: «{floskel}».")
    if not MARKER_RE.search(alles):
        hart.append("Keine Bild-Marker im Skript.")
    wort = len(sprechtext(" ".join(a.get("text") or "" for a in abschnitte)).split())
    lo, hi, _ = LAENGEN[laenge]
    if prompt_name == "analyse" and laenge == "folge" and not lo * 0.85 <= wort <= hi * 1.15:
        hart.append(f"Sprechtext ohne Hook hat {wort} Wörter, Ziel {lo} bis {hi}: kürze über weniger Nebenstränge "
                    f"(Abschnitte zusammenfassen oder weglassen), behalte alle Zitate.")
    elif prompt_name == "analyse" and not lo <= wort <= hi:
        hinweis.append(f"Sprechtext ohne Hook hat {wort} Wörter (Ziel {lo} bis {hi}).")
    return hart, hinweis


# Paket-Regeln (Marlons Ja zur Vorbild-Analyse, 01.10.2026, Task 20261001-152131-dffa): Hook, Titel, Thumbnail,
# Ich-Form mit markierter Meinung, genau eine Kommentarfrage. Nur fuer den Prompt «analyse».
HOOK_SCHLUSS = "Das alles gleich in Weltlage Kompakt."
TITEL_MAX, TITEL_MIN = 70, 35
THUMB_FARBEN = ("konflikt", "wirtschaft", "politik", "krise")
THUMB_ZEILE_MAX = 18
ICH_RE = re.compile(r"\b(ich|mich|mir|mein|meine|meinen|meiner|meinem|meines)\b", re.I)
MEINUNG_RE = re.compile(r"\b(ich (halte|glaube|denke|finde|vermute|bin|wäre|würde|sehe|erwarte|frage mich|zweifle)|"
                        r"meine einschätzung|meiner meinung|mich überzeugt|mir scheint|aus meiner sicht)", re.I)
EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF]")


def _ohne_zitate(text: str) -> str:
    return re.sub(r"«[^«»]*»", " ", text)


def _saetze(text: str) -> list[str]:
    return [x.strip() for x in re.split(r"(?<=[.!?])\s+", text.strip()) if x.strip()]


def _nachnamen(s: dict) -> set[str]:
    """Nachnamen (bzw. Ein-Wort-Namen) aller Akteure aus Analyse, Zitaten und Handlungen."""
    namen = set()
    an = s.get("analyse") or {}
    for p in ([a.get("person") for a in an.get("akteure") or []] + [z.get("person") for z in s.get("zitate") or []]
              + [h.get("wer") for h in s.get("handlungen") or []]):
        p = re.sub(r"\(.*?\)", "", str(p or "")).strip()
        if p:
            last = p.split()[-1].strip(".,;:")
            if len(last) >= 3 and last[0].isupper():
                namen.add(last)
    return namen


def paket_pruefen(s: dict) -> tuple[list[str], list[str]]:
    """Hook (alle Themen in ein bis zwei Saetzen), Titel-Schema, Thumbnail-Felder, Ich-Form/Meinung, Kommentarfrage."""
    hart, hinweis = [], []
    abschnitte = s.get("abschnitte") or []
    namen = _nachnamen(s)
    # Hook / Cold Open
    hook = sprechtext(str(s.get("hook") or ""))
    kern = hook.replace(HOOK_SCHLUSS, "").strip()
    saetze = _saetze(kern)
    if len(saetze) > 3:
        hart.append(f"Hook hat {len(saetze)} Sätze vor «{HOOK_SCHLUSS}»: alle Themen in ein bis zwei Sätzen, danach "
                    "höchstens ein kurzer Fragesatz.")
    elif len(saetze) == 3 and not saetze[-1].endswith("?"):
        hinweis.append("Hook hat drei Sätze; der dritte sollte ein kurzer Fragesatz sein.")
    hw = len(hook.split())
    if not 25 <= hw <= 90:
        hart.append(f"Hook hat {hw} Wörter (Ziel 35 bis 75).")
    elif not 35 <= hw <= 75:
        hinweis.append(f"Hook hat {hw} Wörter (Ziel 35 bis 75).")
    im_hook = {n for n in namen if re.search(rf"\b{re.escape(n)}", hook)}
    if not im_hook:
        hart.append("Hook nennt keine Person mit Namen (mindestens zwei Namen aus den Akteuren).")
    elif len(im_hook) < 2:
        hinweis.append(f"Hook nennt nur einen Namen ({', '.join(im_hook)}), Ziel zwei.")
    if not re.search(r"\d", hook):
        hinweis.append("Hook ohne Zahl.")
    themen = s.get("hook_themen") or []
    gedeckt = set()
    for h in themen:
        wort = str(h.get("stichwort") or "").strip()
        if not wort or wort.lower() not in hook.lower():
            hart.append(f"hook_themen: Stichwort «{wort}» steht nicht im Hook.")
        elif str(h.get("meldung", "")).isdigit():
            gedeckt.add(int(h["meldung"]))
    themen_folge = {a["meldungen"][0] for a in abschnitte if a.get("meldungen") and isinstance(a["meldungen"][0], int)}
    fehlt = sorted(themen_folge - gedeckt)
    if fehlt:
        hart.append(f"Hook nennt nicht alle Themen der Folge: Meldung {', '.join(map(str, fehlt))} fehlt im Hook "
                    "(bzw. in «hook_themen» mit wörtlichem Stichwort).")
    # Titel-Schema
    for i, tv in enumerate(s.get("titel_varianten") or []):
        if len(tv) > TITEL_MAX:
            hart.append(f"Titel-Variante {i + 1} hat {len(tv)} Zeichen (höchstens {TITEL_MAX}).")
    titel = str(s.get("titel") or "")
    if len(titel) > TITEL_MAX:
        hart.append(f"Titel hat {len(titel)} Zeichen (höchstens {TITEL_MAX}).")
    elif len(titel) < TITEL_MIN:
        hinweis.append(f"Titel mit {len(titel)} Zeichen eher kurz (Ziel {TITEL_MIN} bis {TITEL_MAX}).")
    if namen and not any(re.search(rf"\b{re.escape(n)}", titel) for n in namen):
        hart.append("Titel nennt keine Person mit Namen (Schema «Person + Handlung», Nachname reicht).")
    if not titel.rstrip().endswith(("?", "!")):
        hinweis.append("Titel endet weder mit «?» noch mit «!» (Zuspitzung).")
    if len(re.findall(r"\b[A-ZÄÖÜ]{4,}\b", titel)) > 1:
        hart.append("Titel hat mehr als ein Wort in GROSSBUCHSTABEN.")
    if EMOJI_RE.search(titel):
        hart.append("Titel enthält ein Emoji.")
    # Thumbnail-Felder fuer die feste Vorlage (video/weltlage_thumbnail.py)
    th = s.get("thumbnail") if isinstance(s.get("thumbnail"), dict) else {}
    if not th:
        hart.append("Feld «thumbnail» (banderole, zeile1, zeile2, farbe) fehlt.")
    else:
        if not 1 <= len(str(th.get("banderole") or "").split()) <= 2:
            hart.append("Thumbnail-Banderole muss 1 bis 2 Wörter haben.")
        zeilen = [str(th.get("zeile1") or "").strip(), str(th.get("zeile2") or "").strip()]
        w = sum(len(z.split()) for z in zeilen)
        if not zeilen[0] or not 2 <= w <= 5:
            hart.append(f"Thumbnail zeile1+zeile2 müssen zusammen 2 bis 5 Wörter haben, haben {w}.")
        for z in zeilen:
            if len(z) > THUMB_ZEILE_MAX:
                hart.append(f"Thumbnail-Zeile «{z}» ist länger als {THUMB_ZEILE_MAX} Zeichen.")
        if th.get("farbe") not in THUMB_FARBEN:
            hart.append(f"Thumbnail-Farbe muss eine von {', '.join(THUMB_FARBEN)} sein.")
    # Ich-Form und markierte Meinung (Zitate anderer Personen zaehlen nicht)
    eigen = _ohne_zitate(sprechtext(" ".join(a.get("text") or "" for a in abschnitte)))
    n_ich = len(ICH_RE.findall(eigen))
    if n_ich < 3:
        hart.append(f"Zu wenig Ich-Form ({n_ich}x): Latara spricht als Person («ich», «meine Einschätzung»).")
    meinungen = [str(m) for m in s.get("meinungen") or [] if str(m).strip()]
    if not meinungen:
        hart.append("Feld «meinungen» fehlt: 2 bis 4 klar markierte Meinungssätze in Ich-Form.")
    elif not 2 <= len(meinungen) <= 4:
        hinweis.append(f"{len(meinungen)} Meinungssätze (Ziel 2 bis 4).")
    eigen_n = _norm(eigen)
    for m in meinungen:
        if _norm(_ohne_zitate(sprechtext(m))) not in eigen_n:
            hart.append(f"Meinungssatz steht nicht wörtlich im Sprechtext: «{m[:70]}».")
        elif not MEINUNG_RE.search(m):
            hart.append(f"Meinungssatz ohne hörbaren Marker («Ich halte …», «Meine Einschätzung: …»): «{m[:70]}».")
    if not MEINUNG_RE.search(eigen):
        hart.append("Keine klar markierte Meinung im Sprechtext («Ich halte …», «Meine Einschätzung: …»).")
    einordnung = " ".join(a.get("text") or "" for a in abschnitte if a.get("rolle") == "einordnung")
    if einordnung and not MEINUNG_RE.search(_ohne_zitate(einordnung)):
        hinweis.append("Einordnung ohne markierte Meinung.")
    # genau eine konkrete Kommentarfrage als Schluss
    frage = sprechtext(str(s.get("kommentarfrage") or "")).strip()
    letzter = _ohne_zitate(sprechtext(abschnitte[-1].get("text") or "")) if abschnitte else ""
    if not frage or not frage.endswith("?"):
        hart.append("Feld «kommentarfrage» fehlt oder endet nicht mit «?».")
    else:
        if abschnitte and abschnitte[-1].get("rolle") != "schluss":
            hinweis.append("Letzter Abschnitt hat nicht die Rolle «schluss».")
        if _norm(frage) not in _norm(" ".join(_saetze(letzter)[-2:])):
            hart.append("Die Kommentarfrage muss der letzte Satz des letzten Abschnitts sein (wörtlich wie «kommentarfrage»).")
        if letzter.count("?") != 1:
            hart.append(f"Der Schluss enthält {letzter.count('?')} Fragezeichen: genau eine Kommentarfrage, keine weitere Frage.")
        if "kommentar" not in letzter.lower():
            hart.append("Der Schluss lädt nicht hörbar zum Kommentieren ein (Wort «Kommentar»/«Kommentare»).")
        if not (" oder " in frage or re.search(r"\d", frage)):
            hart.append("Kommentarfrage nicht konkret: Entweder-oder («… oder …?») oder Skala mit Zahl (1 bis 10).")
    return hart, hinweis


def _norm(t: str | None) -> str:
    """Vergleichsform fuer Zitate: Anfuehrungszeichen weg, Apostrophe/Striche vereinheitlicht, Leerraum gestaucht."""
    t = html.unescape(t or "").lower()
    t = re.sub(r"[\"“”„«»‹›]", "", t)
    t = re.sub(r"[’‘`´]", "'", t)
    t = re.sub(r"[–—‑]", "-", t).replace("…", " ").replace("...", " ")
    t = re.sub(r"\s+([.,;:!?])", r"\1", re.sub(r"\s+", " ", t))
    return t.strip()


def quellen_bloecke(material: str) -> dict[str, str]:
    """{"M1": Text der Meldung 1 inkl. Volltext, "A3": Aussage 3 inkl. Kopfzeile mit Link} aus material.txt."""
    bl = {f"M{m.group(1)}": m.group(0)
          for m in re.finditer(r"=== MELDUNG (\d+).*?(?=\n=== |\Z)", material, re.S)}
    bl.update({m.group(1): m.group(0)
               for m in re.finditer(r"^\[(A\d+)\].*?(?=^\[A\d+\]|\n=== |\Z)", material, re.S | re.M)})
    return bl


def zitate_pruefen(s: dict, material: str) -> tuple[list[str], list[str], list[dict]]:
    """Echtheits-Pruefung der Zitate (Marlon 01.10.: nichts erfinden, belegbar, Uebersetzung gekennzeichnet).
    Jedes «original» muss woertlich im Material stehen, die «url» im Material, «deutsch» woertlich im Sprechtext,
    eine Uebersetzung hoerbar markiert. Gibt (hart, hinweis, zitate mit Feld «pruefung») zurueck."""
    hart, hinweis, out = [], [], []
    bloecke = {k: _norm(v) for k, v in quellen_bloecke(material).items()}
    mat = _norm(material)
    gesprochen = _norm(sprechtext(" ".join([str(s.get("hook") or "")]
                                           + [a.get("text") or "" for a in s.get("abschnitte") or []])))
    for i, z in enumerate(s.get("zitate") or [], 1):
        z = dict(z)
        nr = z.get("nr") or f"Z{i}"
        orig, de = _norm(z.get("original")), _norm(z.get("deutsch"))
        # Auslassungen («…», «[...]») trennen Teilstuecke; jedes Teilstueck muss fuer sich woertlich im Material stehen
        teile = [_norm(t) for t in re.split(r"\[\s*(?:…|\.\.\.)\s*\]|…|\.\.\.", z.get("original") or "")
                 if len(_norm(t).split()) >= 3] or [orig]
        fehler = []
        if len(orig.split()) < 4:
            fehler.append("«original» zu kurz oder leer")
        elif not all(t in bloecke.get(str(z.get("quelle")), "") for t in teile):
            gefunden = [k for k, b in bloecke.items() if all(t in b for t in teile)]
            if gefunden:
                hinweis.append(f"Zitat {nr}: Quelle korrigiert {z.get('quelle')} -> {gefunden[0]}.")
                z["quelle"] = gefunden[0]
            else:
                fehler.append("Wortlaut steht nicht im Material (erfunden, geglättet oder zusammengesetzt?)")
        url = str(z.get("url") or "").strip()
        if not url or url not in material:
            fehler.append("Link fehlt oder steht nicht im Material")
        elif z.get("quelle") in bloecke and url not in quellen_bloecke(material).get(z["quelle"], ""):
            hinweis.append(f"Zitat {nr}: Link gehört nicht zur Quelle {z.get('quelle')}.")
        pos = gesprochen.find(de) if de else -1
        if pos < 0:
            fehler.append("«deutsch» steht nicht wörtlich zwischen «» im Sprechtext")
        if de and orig and de != orig:
            if not z.get("uebersetzt"):
                hinweis.append(f"Zitat {nr}: als Übersetzung markiert (deutsch weicht vom Original ab).")
                z["uebersetzt"] = True
            if pos >= 0 and "übersetzt" not in gesprochen[max(0, pos - 220):pos]:
                fehler.append("Übersetzung im Sprechtext nicht hörbar gekennzeichnet («übersetzt» kurz vor dem Zitat)")
        z["pruefung"] = "ok" if not fehler else "; ".join(fehler)
        if fehler:
            hart.append(f"Zitat {nr} ({z.get('person')}): {z['pruefung']}.")
        out.append(z)
    ok = [z for z in out if z["pruefung"] == "ok"]
    belegt = [_norm(z.get("deutsch")) for z in ok]
    # nur gesprochene «»: Schlagzeilen in [HEADLINE EINBLENDEN: «...»] sind Einblendungen, keine Zitate
    for frei in ZITAT_RE.findall(sprechtext(" ".join([str(s.get("hook") or "")]
                                                     + [a.get("text") or "" for a in s.get("abschnitte") or []]))):
        f = _norm(frei)
        if len(f.split()) >= 4 and not any(f in b or b in f for b in belegt):
            hart.append(f"Zitat im Sprechtext ohne geprüften Beleg in «zitate»: «{frei[:80]}».")
    if len(ok) < MIN_ZITATE:
        (hart if "=== AUSSAGEN" in material else hinweis).append(
            f"Nur {len(ok)} geprüfte Zitate (mindestens {MIN_ZITATE}, Ziel 5 bis 8).")
    if len({z.get("person") for z in ok}) < 2 and ok:
        hinweis.append("Alle Zitate von derselben Person (Ziel: Dialog mehrerer Akteure).")
    return hart, hinweis, out


# ------------------------------------------------------------------ Ausgabe
def _thumb_text(s: dict) -> dict:
    """thumbnail_text aus den Vorlagen-Feldern ableiten, wenn das Modell ihn weglaesst."""
    th = s.get("thumbnail") if isinstance(s.get("thumbnail"), dict) else None
    if th and not str(s.get("thumbnail_text") or "").strip():
        s["thumbnail_text"] = " ".join(x for x in (th.get("zeile1"), th.get("zeile2")) if x)
    return s


def texte_entwurf(s: dict, news: list[dict], datum: str) -> dict:
    szenen = [{"id": "s_coldopen", "szene": "coldopen", "text": sprechtext(s["hook"]), "ort": "studio",
               "marker": [{"typ": t, "beschreibung": b.strip()} for t, b in MARKER_RE.findall(s["hook"])]}]
    for i, a in enumerate(s["abschnitte"], 1):
        szenen.append({
            "id": f"s5_a{i}_{a.get('rolle') or 'abschnitt'}", "szene": 5, "bild": a["meldungen"][0] - 1,
            "kurz": a["kurz"].strip().rstrip("."), "rolle": a.get("rolle"), "meldungen": a["meldungen"],
            "text": sprechtext(a["text"]), "ort": ort_fuer_abschnitt(a),
            "marker": [{"typ": t, "beschreibung": b.strip()} for t, b in MARKER_RE.findall(a["text"])],
        })
    szenen.append(dict(OUTRO, ort="studio"))
    szenen.append({"id": "s_themen", "szene": "themen", "text": build_themen_text(szenen), "ort": "studio"})
    bilder = [{"idx": i, "thema": _sauber(m["articles"][0]["title"])[:60],
               "urls": [a["url"] for a in m["articles"][:3] if a.get("url")]} for i, m in enumerate(news)]
    return {"datum": datum, "titel": s["titel"], "titel_varianten": s["titel_varianten"],
            "thumbnail_text": s["thumbnail_text"], "zentrale_these": s["zentrale_these"],
            # Paket fuer Upload/Thumbnail (tools/weltlage_tageslauf.py, video/weltlage_thumbnail.py)
            "thumbnail": s.get("thumbnail"), "hook": sprechtext(s["hook"]), "hook_themen": s.get("hook_themen") or [],
            "kommentarfrage": s.get("kommentarfrage"), "meinungen": s.get("meinungen") or [],
            "szenen": szenen, "bilder": bilder,
            # gepruefte Zitate (fuer spaetere Einblendung mit Quelle), Handlungen der Akteure
            "zitate": [q for q in s.get("zitate") or [] if q.get("pruefung", "ok") == "ok"],
            "handlungen": s.get("handlungen") or []}


def bericht_md(s: dict, news: list[dict], meta: dict) -> str:
    z = [f"# Weltlage Kompakt – Skript ({meta['prompt']}) vom {meta['datum']}", "",
         f"Erzeugt {meta['erzeugt']} mit {meta['llm']}, Prompt `config/prompts/weltlage_{meta['prompt']}.md`. "
         "Probelauf/Entwurf: nicht vertont, nicht gerendert, nicht veröffentlicht.", "",
         f"**TITEL:** {s['titel']}", "", "Varianten:"]
    z += [f"- {t}" for t in s["titel_varianten"]]
    z += ["", f"**THUMBNAIL-TEXT:** {s['thumbnail_text']}"]
    th = s.get("thumbnail") if isinstance(s.get("thumbnail"), dict) else None
    if th:
        z += [f"Thumbnail-Vorlage: Banderole «{th.get('banderole')}», Zeile 1 «{th.get('zeile1')}», "
              f"Zeile 2 «{th.get('zeile2')}», Farbcode {th.get('farbe')}"]
    z += ["", f"**ZENTRALE THESE:** {s['zentrale_these']}", ""]
    if s.get("kommentarfrage"):
        z += [f"**KOMMENTARFRAGE:** {s['kommentarfrage']}", ""]
    if s.get("meinungen"):
        z += ["**MEINUNG (Ich-Form, markiert):**"] + [f"- {m}" for m in s["meinungen"]] + [""]
    an = s.get("analyse") or {}
    z += ["## Analyse (intern)", "", f"- Thema: {an.get('thema', '')}", f"- Konflikt: {an.get('konflikt', '')}",
          f"- Zentrale Frage: {an.get('zentrale_frage', '')}", f"- Verbindung: {an.get('verbindung', '')}"]
    z += [f"- Tragend: {f}" for f in an.get("tragende_fakten") or []]
    z += [f"- Widerspruch: {f}" for f in an.get("widersprueche") or []]
    z += [f"- Gestrichen: {f}" for f in an.get("gestrichen") or []]
    if an.get("akteure") or an.get("reaktionskette"):
        z += ["", "### Akteure und Reaktionskette", ""]
        z += [f"- {a.get('person')} ({a.get('funktion')}): {a.get('interesse')}" for a in an.get("akteure") or []]
        z += [f"{i}. {k}" for i, k in enumerate(an.get("reaktionskette") or [], 1)]
    z += ["", "## SKRIPT", "", "### Hook (Cold Open)", "", s["hook"], ""]
    for i, a in enumerate(s["abschnitte"], 1):
        z += [f"### {i}. {str(a.get('rolle') or '').capitalize()} – {a['kurz']} (Meldung {', '.join(map(str, a['meldungen']))})",
              "", a["text"], ""]
    z += ["### Verabschiedung (fest)", "", OUTRO["text"], "", "## Belege", ""]
    z += [f"- {b.get('aussage')} (Meldung {b.get('meldung')})" for b in s.get("belege") or []]
    if meta.get("zitate") is not None:
        ok = sum(1 for q in meta["zitate"] if q.get("pruefung") == "ok")
        z += ["", f"## Zitate mit Quelle ({ok} von {len(meta['zitate'])} automatisch Wort für Wort gegen das Material "
                  "geprüft)", ""]
        for q in meta["zitate"]:
            uebers = " – *Übersetzung* (Original unten)" if q.get("uebersetzt") else ""
            z += [f"- **{q.get('nr')}** {q.get('person')} ({q.get('funktion')}), {q.get('kanal')}, {q.get('datum')}"
                  f"{uebers}: «{q.get('deutsch')}»",
                  f"  - Original: „{q.get('original')}“",
                  f"  - Quelle {q.get('quelle')}: {q.get('url')}",
                  f"  - Prüfung: {q.get('pruefung')}"]
    if s.get("handlungen"):
        z += ["", "## Handlungen der Akteure", ""]
        z += [f"- {h.get('wann')}: {h.get('wer')} – {h.get('was')} (Quelle {h.get('quelle')})"
              for h in s["handlungen"]]
    z += ["", "## Als unsicher/Spekulation gekennzeichnet", ""] + [f"- {u}" for u in s.get("unsicher") or []]
    z += ["", "## Automatische Prüfung", ""]
    z += [f"- Problem: {p}" for p in meta["probleme"]] + [f"- Hinweis: {h}" for h in meta["hinweise"]]
    if not meta["probleme"] and not meta["hinweise"]:
        z.append("- keine Auffälligkeiten")
    z += [f"- Wörter: Hook {meta['woerter_hook']}, Abschnitte {meta['woerter']} (ca. {meta['minuten']:.1f} min)", "",
          "## Meldungen im Material", ""]
    for nr, m in enumerate(news, 1):
        a = m["articles"][0]
        z.append(f"{nr}. {_sauber(a['title'])} – {', '.join(m['sources'])} ({a.get('url')})")
    if meta.get("aussagen_kanaele"):
        z += ["", "## Aussagen-Kanäle (Originalquellen, ohne Login)", ""]
        z += [f"- {k}: {v if isinstance(v, str) else f'{v} frische Einträge'}"
              for k, v in meta["aussagen_kanaele"].items()]
    return "\n".join(z) + "\n"


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ordner", type=Path, help="Folgenordner (Standard data/weltlage_<datum>_skript)")
    ap.add_argument("--meldungen", type=int, default=6, help="Anzahl Meldungsgruppen aus den aktuellen Quellen")
    ap.add_argument("--news", type=Path, help="vorhandene news.json statt neu abholen")
    ap.add_argument("--transkript", type=Path, help="Transkript/Rohtext als Ausgangsmaterial (statt Meldungen)")
    ap.add_argument("--prompt", choices=["analyse", "klassisch"], default=NEWS_WELTLAGE_SKRIPT_PROMPT)
    ap.add_argument("--ohne-volltext", action="store_true", help="nur Schlagzeilen/Auszuege, keine Artikeltexte")
    ap.add_argument("--ohne-aussagen", action="store_true",
                    help="keine Originalkanaele (Truth Social, Telegram, ...) ins Material (nur Prompt analyse)")
    ap.add_argument("--laenge", choices=sorted(LAENGEN), default=NEWS_WELTLAGE_SKRIPT_LAENGE,
                    help="folge = rund 4-5 Min. fertige Folge (Standard), lang = 5-9 Min., "
                         "doku = 10-20 Min. lange Folge, Sprechtext")
    ap.add_argument("--texte", action="store_true", help="texte.json im Folgenordner schreiben (sonst nur Entwurf)")
    ap.add_argument("--vorgabe", type=Path, help="Storyline-Vorgabe (Text: Titel-Frage, Inhalt, Marlons Hinweise) aus "
                                                 "der Themenwahl von tools/weltlage_tageslauf.py; hat Vorrang")
    args = ap.parse_args()

    jetzt = datetime.now().astimezone()
    datum = jetzt.strftime("%Y-%m-%d")
    ordner = args.ordner or DATA_DIR / f"weltlage_{jetzt:%Y%m%d}_skript"
    ordner.mkdir(parents=True, exist_ok=True)

    if args.transkript:
        news = [{"sources": ["Transkript"], "n": 1, "articles": [{"title": args.transkript.stem, "url": None,
                                                                  "source": "Transkript"}]}]
        material = "=== MELDUNG 1 (Transkript) ===\n" + args.transkript.read_text(encoding="utf-8")
    else:
        news = json.loads(args.news.read_text(encoding="utf-8")) if args.news else aktuelle_gruppen(args.meldungen)
        if not news:
            sys.exit("keine aktuellen Meldungsgruppen mit genug Quellen gefunden")
        material = material_aus_news(news, volltext=not args.ohne_volltext)
    kanaele = None
    if args.prompt == "analyse" and not args.ohne_aussagen:
        import weltlage_zitate
        aussagen, kanaele = weltlage_zitate.sammeln(weltlage_zitate.stichworte(
            [_sauber(a.get("title")) + " " + _sauber(a.get("snippet") or a.get("summary"))
             for m in news for a in m["articles"]]))
        material += "\n\n" + weltlage_zitate.material_block(aussagen)
        (ordner / "aussagen.json").write_text(json.dumps(aussagen, indent=1, ensure_ascii=False, default=str),
                                              encoding="utf-8")
        logger.info("%d Aussagen aus Originalkanaelen: %s", len(aussagen), kanaele)
    (ordner / "material.txt").write_text(material, encoding="utf-8")  # Faktengrundlage zum Nachpruefen
    (ordner / "news.json").write_text(json.dumps(news, indent=1, ensure_ascii=False), encoding="utf-8")

    heute = f"{WOCHENTAGE[jetzt.weekday()]}, {jetzt.day}. {MONATE[jetzt.month - 1]} {jetzt.year}"
    vorlage = (PROMPTS_DIR / f"weltlage_{args.prompt}.md").read_text(encoding="utf-8")
    vorlage = re.sub(r"\A<!--.*?-->\s*", "", vorlage, flags=re.DOTALL)  # Kopfkommentar nicht ans Modell
    prompt = vorlage.replace("{{HEUTE}}", heute).replace("{{LAENGE}}", LAENGEN[args.laenge][2])         .replace("{{NEWS_TRANSCRIPT_OR_SOURCE}}", material)
    if args.vorgabe and args.vorgabe.exists() and args.vorgabe.read_text(encoding="utf-8").strip():
        prompt += vorgabe_block(args.vorgabe.read_text(encoding="utf-8"))
    llm = f"claude-cli/{NEWS_WELTLAGE_SKRIPT_MODELL}" if NEWS_WELTLAGE_SKRIPT_LLM != "ollama" else f"ollama/{NEWS_MODEL_SCRIPT}"
    logger.info("Prompt %s, %d Meldungen, %d Zeichen Material, %s", args.prompt, len(news), len(material), llm)

    def alles_pruefen(sk):
        hart, hinw = pruefen(sk, len(news), args.prompt, args.laenge)
        if args.prompt != "analyse":
            return hart, hinw, None
        zh, zw, zit = zitate_pruefen(sk, material)
        ph, pw = paket_pruefen(sk)
        return hart + zh + ph, hinw + zw + pw, zit

    s = _thumb_text(_ss(frage_modell(prompt)))
    probleme, hinweise, zitate = alles_pruefen(s)
    if probleme:
        logger.warning("Neuversuch wegen: %s", probleme)
        s2 = _thumb_text(_ss(frage_modell(prompt + "\n\nDein letzter Entwurf hatte diese Fehler, behebe jeden "
                                          "davon:\n" + "\n".join(f"- {p}" for p in probleme))))
        p2, h2, z2 = alles_pruefen(s2)
        if len(p2) <= len(probleme):
            s, probleme, hinweise, zitate = s2, p2, h2, z2
    if zitate is not None:
        s["zitate"] = zitate  # mit Pruefergebnis und korrigierter Quelle/Uebersetzungs-Markierung

    woerter_hook = len(sprechtext(s.get("hook") or "").split())
    woerter = len(sprechtext(" ".join(a.get("text") or "" for a in s.get("abschnitte") or [])).split())
    meta = {"prompt": args.prompt, "laenge": args.laenge, "datum": datum, "erzeugt": jetzt.strftime("%d.%m.%Y %H:%M"), "llm": llm,
            "probleme": probleme, "hinweise": hinweise, "woerter_hook": woerter_hook, "woerter": woerter,
            "minuten": (woerter_hook + woerter) / 140, "zitate": zitate, "aussagen_kanaele": kanaele,
            "zitate_geprueft": sum(1 for q in zitate or [] if q.get("pruefung") == "ok")}
    (ordner / "skript.json").write_text(json.dumps({"meta": meta, "skript": s}, indent=1, ensure_ascii=False),
                                        encoding="utf-8")
    (ordner / "skript.md").write_text(bericht_md(s, news, meta), encoding="utf-8")
    if not probleme:
        entwurf = texte_entwurf(s, news, datum)
        (ordner / "texte.entwurf.json").write_text(json.dumps(entwurf, indent=1, ensure_ascii=False), encoding="utf-8")
        if args.texte:
            (ordner / "texte.json").write_text(json.dumps(entwurf, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"ordner": str(ordner), "titel": s.get("titel"), "probleme": probleme, "hinweise": hinweise,
                      "woerter": woerter, "zitate_geprueft": meta["zitate_geprueft"]}, ensure_ascii=False, indent=1))
    return 1 if probleme else 0


if __name__ == "__main__":
    sys.exit(main())
