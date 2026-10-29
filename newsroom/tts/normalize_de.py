"""Text normalisation for German TTS: what the voice should SAY, not what the caption shows.

No TTS model reads "800.000", "UN", "AfD" or "Dr." the way a news anchor does. Numbers are spelled
out, acronyms are spelled letter by letter with GERMAN letter names unless they are commonly
pronounced as a word (NATO, UNO, NASA), abbreviations are expanded. Only the text sent to the TTS
is changed - captions keep the script's own spelling (align_captions matches the heard words back
to the script by sequence alignment, so "achthunderttausend" maps onto "800.000").

Ausbau 18.10.2026 (rexemres Rueckmeldung "FBI und weitere Woerter schlecht ausgesprochen", Task ad90):
- Buchstabiert wird mit gedehnter Lautschrift ("Eff Beh Ih" statt "Ef Be I"): Chatterbox las die
  kurzen Einzelbuchstaben "I"/"E"/"Be" oft englisch oder verschluckte sie; gemessen mit Whisper-Rueckhoeren
  (jarvis/reports/stimme_aussprache_20261018/messung_abkuerzungen.json).
- Zweiter Ausbau 18.10.2026 (Hoerprobe alt/neu, Task ad90 Folgeauftrag): FBI klang mit deutschen Buchstabennamen
  ("Eff Beh Ih") falsch, rexemre will die im Deutschen uebliche englische Aussprache ("Eff Bi Ai"). SPELL_OUT_EN
  listet die wenigen Kuerzel, die deutsche Sprecher englisch buchstabieren (FBI, CIA, NSA); alles andere in
  SPELL_OUT (AfD, CDU, EU, USA ...) bleibt deutsch buchstabiert. LETTER_EN enthaelt bewusst nur die dafuer
  gemessenen Buchstaben, nicht das ganze Alphabet - bei neuen Eintraegen in SPELL_OUT_EN mit Whisper nachmessen
  statt zu raten (siehe Datei-Kopf-Hinweis oben).
- Woerter in Grossschrift zur Betonung (WAHL, JETZT, NICHTS) werden als Wort gesprochen statt buchstabiert, wenn sie
  im Wortschatz (config/brand/stimme/wortschatz_de.txt) stehen.
- Datum (18.10.2026), Uhrzeit (14:30 Uhr), Jahreszahlen (1994 -> neunzehnhundertvierundneunzig), "1 Milliarde"
  (-> eine), Spannen (2010-2015 -> bis), Vorzeichen (-3 % -> minus), Zeichen (&, §, °C, km²) und fremde Sonderzeichen
  (ğ, ł, ş ...) ohne Lexikon-Eintrag. Der Pruefschritt vor jeder Vertonung meldet den Rest: tts/aussprache_pruefung.py.
"""
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from tts.zahlen_de import MONATE as _MONATE_Z, _num as zahlen_num, dezimal as zahlen_dezimal, jahr as zahlen_jahr, zahlen_sprechen

WORTSCHATZ_PFAD = Path(__file__).resolve().parent.parent / "config" / "brand" / "stimme" / "wortschatz_de.txt"

# Acronyms that German newsreaders pronounce as a word - leave them alone.
SAY_AS_WORD = {"NATO", "UNO", "NASA", "UNESCO", "UNICEF", "OPEC", "FIFA", "UEFA", "ESA", "ISIS", "IS", "DAX",
               "AIDS", "LASER", "RADAR", "ASEAN", "BRICS", "OSZE", "OECD", "SWIFT", "GEMA", "ADAC", "TÜV", "ELSTER",
               "MERCOSUR", "INTERPOL", "EUROPOL", "FRONTEX", "HAMAS", "TIKTOK", "AMAZON", "APPLE", "TESLA",
               "NAFTA", "SALT", "START", "COVID", "SARS", "MERS", "EFTA", "CERN", "INTEL", "NOAA", "FEMA", "MAGA",
               "OPEC+", "ICE", "SIM", "PIN", "ISAF", "AKW", "KITA", "BAFÖG", "HARTZ", "IFO", "DIW", "VDA", "UNHCR",
               "UNRWA", "AUKUS", "QUAD", "NOVA", "ATACMS", "HIMARS", "NASDAQ", "BAFIN", "ZEW"}
# Acronyms that are ALWAYS spelled out (also when they don't look like one, e.g. mixed case).
# Englische Medien/Behoerden stehen zusaetzlich in SPELL_OUT_EN (geht vor, siehe unten); die Eintraege hier sind der
# deutsche Altstand fuer Szenen vor KUERZEL_EN_AB.
SPELL_OUT_ALT_EN = {"CNBC", "AP", "CBS", "NBC", "ABC", "NPR", "AI", "GOP", "CEO", "CFO", "NHS", "MI6", "MI5", "DOJ", "USAID", "FP"}
SPELL_OUT = {"AfD", "CSU", "CDU", "SPD", "FDP", "USA", "UN", "EU", "UK", "US", "IWF",
             "IMF", "EZB", "ECB", "BND", "KI", "IT", "TV", "PKW", "LKW", "SUV", "GPS", "DNA", "HIV", "WM", "EM", "NGO",
             "ICC", "IStGH", "IGH", "EuGH", "BGH", "BVerfG", "ARD", "ZDF", "RTL", "ÖVP", "FPÖ", "SVP", "DUP", "ANC",
             "MEP", "MP", "PM", "KP", "ÖRR", "BIP", "GDP", "IDF", "PKK", "PLO",
             "WHO", "WTO", "AFP", "DPA", "SRF", "ORF", "DW", "USS", "USB",
             "RAF", "AAP", "BSW", "SED", "DDR", "BRD", "UdSSR", "SBB", "EDA", "SECO", "SNB", "FINMA", "UBS", "ETH",
             "ESC", "WEF", "IAEA", "IAEO", "ILO", "OAS", "AU", "EWG", "EVP", "SPÖ", "KZ", "SS", "NS", "LGBTQ", "NHS",
             "BKA", "LKA", "BfV", "BAMF", "THW", "DGB", "IG", "VW", "BMW", "AG", "GmbH", "SA", "ÖBB", "EKD", "KPCh",
             "AKP", "CHP", "HDP", "PiS", "PO", "ANO", "CNA", "CPU", "GPU", "PC", "SMS", "PR", "HR", "OB", "MdB",
             "DOGE", "IRGC", "RSF", "UAE", "VAE", "EAU", "ID", "PDF", "UKMTO", "BFMTV", "RAC", "AARP",
             "JD", "KKM", "GFS", "MS", "SB", "ING", "IRA", "IS-K"}
# Deutsche Buchstabennamen in gedehnter Lautschrift (18.10.2026): "I"/"E"/"A" allein liest Chatterbox oft englisch
# ("ai", "i") oder kurz verschluckt, "Be" wie engl. "be", "Ce" wie "ke" - die Dehnung mit h macht sie eindeutig.
LETTER = {"A": "Ah", "B": "Beh", "C": "Zeh", "D": "Deh", "E": "Eh", "F": "Eff", "G": "Geh", "H": "Hah", "I": "Ih",
          "J": "Jott", "K": "Kah", "L": "Ell", "M": "Emm", "N": "Enn", "O": "Oh", "P": "Peh", "Q": "Kuh", "R": "Err",
          "S": "Ess", "T": "Teh", "U": "Uh", "V": "Fau", "W": "Weh", "X": "Iks", "Y": "Üpsilon", "Z": "Zett",
          "Ö": "Öh", "Ä": "Äh", "Ü": "Üh"}
# Getrennt mit Leerzeichen ("Eff Beh Ih"), nur in Zusammensetzungen mit Bindestrich ("Uh-Ess-Angriffe"). Gemessen
# 18.10.2026 (Whisper medium, 6 Saetze x 2 Seeds): alt "Ef Be I" 27/35 erkannt, "Eff-Beh-Ih" 30/32, "Eff Beh Ih" 31/32 -
# der Bindestrich zieht Nachbarbuchstaben zu Diphthongen zusammen ("Weh-Hah-Oh" -> "Wehau").
SPELL_JOIN = " "
# Kuerzel, die englisch buchstabiert werden (FBI -> "Eff Bi Ai", nicht "Eff Beh Ih"). Regel (rexemre 18./22.10.2026):
# englische Medien-/Organisationskuerzel englisch, deutsche und EU/UN-Kuerzel deutsch (SPELL_OUT).
SPELL_OUT_EN_ALT = {"FBI", "CIA", "NSA"}      # Stand bis KUERZEL_EN_AB
SPELL_OUT_EN = {"FBI", "CIA", "NSA",
                # 22.10.2026 (rexemre: "CNBC falsch, englische Medien-/Organisationskuerzel englisch"): englischsprachige
                # Medien, US/UK-Behoerden und Unternehmensbegriffe. Deutsch bleiben EU, UN, USA, US, UK, CDU, AfD ... (SPELL_OUT).
                "CNBC", "CNN", "BBC", "NBC", "ABC", "CBS", "AP", "NPR", "NYT", "WSJ", "MSNBC", "HBO", "ESPN", "RAC", "AAA",
                "DOJ", "DHS", "IRS", "TSA", "FAA", "FDA", "CDC", "DEA", "ATF", "NYPD", "LAPD", "GOP", "CEO", "CFO", "COO", "CTO",
                "NHS", "MI5", "MI6", "USAID", "FP", "AI", "WTI", "SEC", "FCC", "FTC", "OMB"}

KUERZEL_EN_PFAD = Path(__file__).resolve().parent.parent / "config" / "brand" / "stimme" / "kuerzel_en.json"


_GELERNT_ZEIT: dict[str, str] = {}


def _kuerzel_gelernt() -> set:
    """Automatisch gelernte englische Kuerzel (tts/kuerzel_lernen.py); fehlt die Datei, ist die Menge leer."""
    try:
        import json
        d = json.loads(KUERZEL_EN_PFAD.read_text(encoding="utf-8"))
        gesperrt = set(d.get("gesperrt", []))
        _GELERNT_ZEIT.update({k: str(e.get("zeit", "")) for k, e in d.get("eintraege", {}).items()})
        return {k for k in d.get("eintraege", {}) if k not in gesperrt}
    except (OSError, ValueError):
        return set()


# Von Hand gepflegte Liste plus automatisch gelernte Kuerzel (config/brand/stimme/kuerzel_en.json, tts/kuerzel_lernen.py).
# Deterministisch: die Datei aendert sich nur durch Lernen/Rueckgaengig, nicht pro Aufruf.
SPELL_OUT_EN |= _kuerzel_gelernt()
# Szenen, die VOR diesem Zeitpunkt vertont wurden, behalten ihre Tonspur: weltlage_tts.sprechtext_veraltet rechnet fuer
# sie mit dem alten Stand (ohne_gelernt_ab, tts/aussprache_lexikon.py), sonst wuerde jede laufende Folge neu vertont.
KUERZEL_EN_AB = "2026-10-22 14:20:00"
# Englische Buchstabennamen in deutscher Lautschrift. A/B/C/F/I/N/S gemessen mit Whisper-Rueckhoeren 18.10.2026
# (jarvis/reports/stimme_aussprache_20261018/messung_fbi_cia_englisch.json), der Rest 22.10.2026 per Rueckhoeren
# der echten Stimme nachgemessen (jarvis/reports/stimme_aussprache_20261022/).
LETTER_EN = {"A": "Ei", "B": "Bi", "C": "Si", "D": "Di", "E": "Ih", "F": "Eff", "G": "Dschi", "H": "Eitsch", "I": "Ai",
             "J": "Dschej", "K": "Kei", "L": "El", "M": "Em", "N": "En", "O": "Oh", "P": "Pi", "Q": "Kju", "R": "Ahr",
             "S": "Es", "T": "Ti", "U": "Ju", "V": "Wi", "W": "Dabbeljuh", "X": "Eks", "Y": "Wai", "Z": "Sed"}
MONATE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November",
          "Dezember"]
ABBREVIATIONS = [
    (r"\bz\.\s?B\.", "zum Beispiel"), (r"\bbzw\.", "beziehungsweise"), (r"\bca\.", "circa"), (r"\bu\.\s?a\.", "unter anderem"),
    (r"\bd\.\s?h\.", "das heißt"), (r"\bDr\.", "Doktor"), (r"\bProf\.", "Professor"), (r"\bNr\.", "Nummer"),
    (r"\bMio\.", "Millionen"), (r"\bMrd\.", "Milliarden"), (r"\bMr\.", "Mister"), (r"\bMrs\.", "Misses"), (r"\bMs\.", "Miss"),
    (r"\bSt\.", "Sankt"), (r"\bevtl\.", "eventuell"), (r"\bggf\.", "gegebenenfalls"), (r"\binkl\.", "inklusive"),
    (r"\busw\.", "und so weiter"), (r"\bvs\.", "gegen"), (r"\bJh\.", "Jahrhundert"), (r"\bkm/h\b", "Kilometer pro Stunde"),
    (r"\bkm²", "Quadratkilometer"), (r"\bm²", "Quadratmeter"), (r"\bkm\b", "Kilometer"), (r"\bkg\b", "Kilogramm"),
    (r"\bkWh\b", "Kilowattstunden"), (r"\bMW\b", "Megawatt"), (r"\bGW\b", "Gigawatt"), (r"\bTWh\b", "Terawattstunden"),
    (r"\bG7\b", "Geh Sieben"), (r"\bG20\b", "Geh Zwanzig"),  # vor _numbers(), sonst wird nur die Ziffer gesprochen ("Gsieben")
    (r"\bAT&T\b", "Ah-Teh und Teh"), (r"\s&\s", " und "), (r"§§\s?", "Paragrafen "), (r"§\s?", "Paragraf "),
    (r"\s?°C\b", " Grad Celsius"), (r"\s?°", " Grad"), (r"\bMrd\b", "Milliarden"), (r"\bMio\b", "Millionen"),
]
# Sonderbuchstaben fremder Sprachen, die NFKD nicht auf einen Grundbuchstaben zerlegt (Lexikon geht vor).
_FREMD = {"ı": "i", "ł": "l", "Ł": "L", "ø": "ö", "Ø": "Ö", "æ": "ä", "Æ": "Ä", "å": "o", "Å": "O", "đ": "d", "Đ": "D",
          "ğ": "", "ş": "sch", "Ş": "Sch", "ș": "sch", "Ș": "Sch", "ț": "z", "Ț": "Z", "č": "tsch", "Č": "Tsch",
          "ć": "tsch", "Ć": "Tsch", "š": "sch", "Š": "Sch", "ž": "sch", "Ž": "Sch", "ñ": "nj", "œ": "ö", "þ": "th"}


_num = zahlen_num
_jahr = zahlen_jahr
_decimal = zahlen_dezimal


def _spell(token: str, table: dict[str, str] = LETTER) -> str:
    letters = [table.get(ch.upper(), ch) for ch in token if ch.isalpha()]
    digits = [_num(int(ch)) for ch in token if ch.isdigit()]
    return SPELL_JOIN.join(letters + digits)


@lru_cache(maxsize=1)
def wortschatz() -> frozenset:
    """Deutsche Woerter (klein), die in Grossschrift als Wort gesprochen werden (WAHL -> Wahl). Feste Datei statt
    laufend aus den Folgen gelernt: normalize_for_tts muss fuer denselben Text immer dasselbe liefern, sonst
    gilt jede Sprachspur als veraltet (weltlage_tts.sprechtext_veraltet)."""
    try:
        zeilen = WORTSCHATZ_PFAD.read_text(encoding="utf-8").splitlines()
        return frozenset(z.strip().lower() for z in zeilen if z.strip() and not z.lstrip().startswith("#"))
    except FileNotFoundError:
        return frozenset()


def ist_deutsches_wort(token: str) -> bool:
    return len(token) >= 3 and token.lower() in wortschatz()


def _alter_stand(core: str) -> bool:
    """True, wenn gerade fuer eine Szene vor KUERZEL_EN_AB gerechnet wird und `core` damals noch deutsch lief."""
    from tts import aussprache_lexikon as lex
    ab = lex._OHNE_GELERNT_AB
    if not ab or core in SPELL_OUT_EN_ALT:
        return False
    return ab < _GELERNT_ZEIT.get(core, KUERZEL_EN_AB)   # gelernte Kuerzel: erst ab Lernzeitpunkt, Handliste: ab KUERZEL_EN_AB


def _acronym(match: re.Match) -> str:
    token, hyphen = match.group(1), match.group(2) or ""
    core = token.rstrip("s")                    # "NGOs" -> "NGO" + plural s
    plural = token.endswith("s") and core.isupper() and len(core) >= 2
    if core in SAY_AS_WORD or token in SAY_AS_WORD:
        return token + hyphen
    if token.isupper() and token not in SPELL_OUT and token not in SPELL_OUT_EN and ist_deutsches_wort(token):
        from tts.aussprache_lexikon import anwenden as _lexikon   # TRUMP -> Trump -> Lexikon-Form
        return _lexikon(token.capitalize()) + hyphen   # Betonung in Grossschrift ("die WAHL") -> als Wort sprechen
    if core in SPELL_OUT_EN and not _alter_stand(core):
        spelled = _spell(core, LETTER_EN)
        if hyphen:
            return spelled.replace(" ", "-") + "-"
        return spelled + ("s" if plural else "")
    if core in SPELL_OUT or core in SPELL_OUT_ALT_EN or (core.isupper() and 2 <= len(core) <= 5 and not re.search(r"[AEIOUÄÖÜ]{2}", core)):
        spelled = _spell(core)
        if hyphen:                              # "US-Angriffe" -> "Uh-Ess-Angriffe" (one compound for the voice)
            return spelled.replace(" ", "-") + "-"
        return spelled + ("s" if plural else "")
    return token + hyphen


def _numbers(text: str) -> str:
    """Zahlen, Daten, Uhrzeiten: eine gemeinsame Funktion fuer alle Ton-Ketten (tts/zahlen_de.py)."""
    return zahlen_sprechen(text)


def fremdzeichen(text: str) -> str:
    """Akzente/Sonderbuchstaben ohne Lexikon-Eintrag auf deutsch lesbare Buchstaben (Sébastien -> Sebastien,
    Nicușor -> Nicuschor); deutsche Umlaute und ß bleiben."""
    out = []
    for ch in text:
        if ch in "äöüÄÖÜß" or ord(ch) < 128 or not ch.isalpha():   # Ziffern/Zeichen (², €) nicht anfassen
            out.append(ch)
        elif ch in _FREMD:
            out.append(_FREMD[ch])
        else:
            zerlegt = unicodedata.normalize("NFKD", ch)
            basis = "".join(c for c in zerlegt if not unicodedata.combining(c))
            out.append(basis if basis.isascii() and basis else ch)
    return "".join(out)


def normalize_for_tts(text: str) -> str:
    """German narration -> what the voice should pronounce."""
    from tts.aussprache_lexikon import anwenden as _aussprache_anwenden
    out = _aussprache_anwenden(text)  # Eigennamen/Fachbegriffe zuerst (config/brand/stimme/aussprache_lexikon.json),
    out = fremdzeichen(out)                                                   # bevor Zahlen/Akronyme angefasst werden
    for pattern, repl in ABBREVIATIONS:
        out = re.sub(pattern, repl, out)
    out = _numbers(out)
    # acronyms: runs of letters with >= 2 capitals (UN, USA, AfD, NGOs, U.S.)
    out = re.sub(r"\b(?:[A-ZÄÖÜ]\.){2,}", lambda m: _spell(m.group(0).replace(".", "")) + " ", out)   # U.S. -> Uh-Ess
    out = re.sub(r"\b([A-ZÄÖÜ][A-Za-zÄÖÜäöü]*[A-ZÄÖÜ][A-Za-zÄÖÜäöü]*s?)\b(-)?", _acronym, out)
    out = out.replace("€", " Euro").replace("$", " Dollar").replace("£", " Pfund")
    out = re.sub(r"\s{2,}", " ", out).strip()
    out = re.sub(r"\s+([,.;:!?])", r"\1", out)
    return out


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    print(normalize_for_tts(" ".join(sys.argv[1:]) or
          "Die UN und die USA: Dr. Brown sagte, 800.000 Menschen starben 1994; die AfD und die CDU, 3,5 % der NGOs, "
          "am 3. Oktober, US-Angriffe, die NATO und die UNO, 68 Angriffe seit September 2025, 4,2 Mrd. €."))
