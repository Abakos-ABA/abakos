"""Text normalisation for German TTS: what the voice should SAY, not what the caption shows.

No TTS model reads "800.000", "UN", "AfD" or "Dr." the way a news anchor does. Numbers are spelled
out, acronyms are spelled letter by letter with GERMAN letter names unless they are commonly
pronounced as a word (NATO, UNO, NASA), abbreviations are expanded. Only the text sent to the TTS
is changed - captions keep the script's own spelling (align_captions matches the heard words back
to the script by sequence alignment, so "achthunderttausend" maps onto "800.000").

Ausbau 18.10.2026 (Marlons Rueckmeldung "FBI und weitere Woerter schlecht ausgesprochen", Task ad90):
- Buchstabiert wird mit gedehnter Lautschrift ("Eff Beh Ih" statt "Ef Be I"): Chatterbox las die
  kurzen Einzelbuchstaben "I"/"E"/"Be" oft englisch oder verschluckte sie; gemessen mit Whisper-Rueckhoeren
  (jarvis/reports/stimme_aussprache_20261018/messung_abkuerzungen.json).
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

from num2words import num2words

WORTSCHATZ_PFAD = Path(__file__).resolve().parent.parent / "config" / "brand" / "stimme" / "wortschatz_de.txt"

# Acronyms that German newsreaders pronounce as a word - leave them alone.
SAY_AS_WORD = {"NATO", "UNO", "NASA", "UNESCO", "UNICEF", "OPEC", "FIFA", "UEFA", "ESA", "ISIS", "IS", "DAX",
               "AIDS", "LASER", "RADAR", "ASEAN", "BRICS", "OSZE", "OECD", "SWIFT", "GEMA", "ADAC", "TÜV", "ELSTER",
               "MERCOSUR", "INTERPOL", "EUROPOL", "FRONTEX", "HAMAS", "TIKTOK", "AMAZON", "APPLE", "TESLA",
               "NAFTA", "SALT", "START", "COVID", "SARS", "MERS", "EFTA", "CERN", "INTEL", "NOAA", "FEMA", "MAGA",
               "OPEC+", "ICE", "SIM", "PIN", "ISAF", "AKW", "KITA", "BAFÖG", "HARTZ", "IFO", "DIW", "VDA", "UNHCR",
               "UNRWA", "AUKUS", "QUAD", "NOVA", "ATACMS", "HIMARS", "NASDAQ", "BAFIN", "ZEW"}
# Acronyms that are ALWAYS spelled out (also when they don't look like one, e.g. mixed case).
SPELL_OUT = {"AfD", "CSU", "CDU", "SPD", "FDP", "USA", "UN", "EU", "UK", "US", "BBC", "CNN", "FBI", "CIA", "NSA", "IWF",
             "IMF", "EZB", "ECB", "BND", "KI", "IT", "TV", "PKW", "LKW", "SUV", "GPS", "DNA", "HIV", "WM", "EM", "NGO",
             "ICC", "IStGH", "IGH", "EuGH", "BGH", "BVerfG", "ARD", "ZDF", "RTL", "ÖVP", "FPÖ", "SVP", "DUP", "ANC",
             "GOP", "MEP", "MP", "PM", "CEO", "CFO", "KP", "ÖRR", "BIP", "GDP", "MI6", "MI5", "IDF", "PKK", "PLO",
             "WHO", "WTO", "AP", "AFP", "DPA", "SRF", "ORF", "CBS", "NBC", "ABC", "NPR", "CNBC", "DW", "USS", "USB",
             "RAF", "AAP", "BSW", "SED", "DDR", "BRD", "UdSSR", "SBB", "EDA", "SECO", "SNB", "FINMA", "UBS", "ETH",
             "ESC", "WEF", "IAEA", "IAEO", "ILO", "OAS", "AU", "EWG", "EVP", "SPÖ", "KZ", "SS", "NS", "LGBTQ", "NHS",
             "BKA", "LKA", "BfV", "BAMF", "THW", "DGB", "IG", "VW", "BMW", "AG", "GmbH", "SA", "ÖBB", "EKD", "KPCh",
             "AKP", "CHP", "HDP", "PiS", "PO", "ANO", "CNA", "AI", "CPU", "GPU", "PC", "SMS", "PR", "HR", "OB", "MdB",
             "USAID", "DOJ", "DOGE", "IRGC", "RSF", "UAE", "VAE", "EAU", "ID", "PDF", "UKMTO", "BFMTV", "RAC", "AARP",
             "JD", "FP", "KKM", "GFS", "MS", "SB", "ING", "IRA", "IS-K"}
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


def _num(n: float | int, ordinal: bool = False) -> str:
    try:
        return num2words(n, lang="de", to="ordinal" if ordinal else "cardinal")
    except Exception:
        return str(n)


def _jahr(n: int) -> str:
    """Jahreszahl wie ein Sprecher: 1994 -> neunzehnhundertvierundneunzig, 2026 -> zweitausendsechsundzwanzig."""
    try:
        return num2words(n, lang="de", to="year")
    except Exception:
        return _num(n)


def _spell(token: str) -> str:
    letters = [LETTER.get(ch.upper(), ch) for ch in token if ch.isalpha()]
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


def _acronym(match: re.Match) -> str:
    token, hyphen = match.group(1), match.group(2) or ""
    core = token.rstrip("s")                    # "NGOs" -> "NGO" + plural s
    plural = token.endswith("s") and core.isupper() and len(core) >= 2
    if core in SAY_AS_WORD or token in SAY_AS_WORD:
        return token + hyphen
    if token.isupper() and token not in SPELL_OUT and ist_deutsches_wort(token):
        from tts.aussprache_lexikon import anwenden as _lexikon   # TRUMP -> Trump -> Lexikon-Form
        return _lexikon(token.capitalize()) + hyphen   # Betonung in Grossschrift ("die WAHL") -> als Wort sprechen
    if core in SPELL_OUT or (core.isupper() and 2 <= len(core) <= 5 and not re.search(r"[AEIOUÄÖÜ]{2}", core)):
        spelled = _spell(core)
        if hyphen:                              # "US-Angriffe" -> "Uh-Ess-Angriffe" (one compound for the voice)
            return spelled.replace(" ", "-") + "-"
        return spelled + ("s" if plural else "")
    return token + hyphen


def _datum(m: re.Match) -> str:
    tag, monat, jahr = int(m.group(1)), int(m.group(2)), m.group(3)
    if not (1 <= tag <= 31 and 1 <= monat <= 12):
        return m.group(0)
    out = f"{_num(tag, ordinal=True)}n {MONATE[monat - 1]}"
    if jahr:
        j = int(jahr)
        out += " " + _jahr(j if len(jahr) == 4 else 2000 + j)
    return out


def _ordinal(m: re.Match) -> str:
    artikel, zahl = m.group(1), _num(int(m.group(2)), ordinal=True)     # num2words: "zweite"
    if not artikel:
        return zahl + "n"
    endung = "r" if artikel.lower() == "ein" else ""
    return f"{artikel} {zahl}{endung}"


def _numbers(text: str) -> str:
    # Datum 18.10.2026 / 18.10. -> "achtzehnten Oktober zweitausendsechsundzwanzig"
    text = re.sub(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4}|\d{2}(?!\d))?", _datum, text)
    # Uhrzeit 14:30 (Uhr) -> "vierzehn Uhr dreißig", 9:00 Uhr -> "neun Uhr"
    text = re.sub(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)(\s?Uhr)?\b",
                  lambda m: (_num(int(m.group(1))) + " Uhr" + ("" if m.group(2) == "00" else " " + _num(int(m.group(2)))))
                  if (m.group(3) or ":" in m.group(0)) else m.group(0), text)
    # Spannen 2010-2015 / 10–15 -> "bis"; Saison 2025/26 -> "zweitausendfünfundzwanzig auf sechsundzwanzig"
    text = re.sub(r"\b(\d+)\s?[–-]\s?(\d+)\b(?!\s?[–-])", r"\1 bis \2", text)
    text = re.sub(r"\b((?:19|20)\d{2})/(\d{2})\b", r"\1 auf \2", text)
    # Vorzeichen vor Zahlen: -3,5 % -> minus, +2 % -> plus
    text = re.sub(r"(?<![\w\d])[−-](?=\d)", "minus ", text)
    text = re.sub(r"(?<![\w\d])\+(?=\d)", "plus ", text)
    # 3,5 % / 3.5 % / 12 Prozent
    text = re.sub(r"(\d+(?:[.,]\d+)?)\s?%", lambda m: _decimal(m.group(1)) + " Prozent", text)
    # currency: 4,2 Mrd. €  /  $200  /  200 Euro
    text = re.sub(r"€\s?(\d[\d.,]*\d|\d)", lambda m: _decimal(m.group(1)) + " Euro", text)
    text = re.sub(r"\$\s?(\d[\d.,]*\d|\d)", lambda m: _decimal(m.group(1)) + " Dollar", text)
    text = re.sub(r"(\d[\d.,]*)\s?€", lambda m: _decimal(m.group(1)) + " Euro", text)
    text = re.sub(r"(\d[\d.,]*)\s?\$", lambda m: _decimal(m.group(1)) + " Dollar", text)
    # ordinals: "am 3." "der 2. Weltkrieg" (a dot directly after a small number, followed by a word)
    # Endung nach dem Artikel: "der 2. Weltkrieg" -> zweite, "ein 4. Versuch" -> vierter, sonst "am 3." -> dritten
    text = re.sub(r"\b(?:(der|die|das|eine|ein)\s+)?(\d{1,2})\.(?=\s+[A-ZÄÖÜa-zäöü])", _ordinal, text, flags=re.I)
    # Jahreszahlen 1100-1999 wie ein Sprecher ("neunzehnhundert..."), nicht "eintausendneunhundert..."
    text = re.sub(r"(?<![\d.,])(1[1-9]\d{2})(?![\d.,]\d)", lambda m: _jahr(int(m.group(1))), text)
    # remaining numbers with German thousands dots / decimal commas
    text = re.sub(r"\d+(?:\.\d{3})+(?:,\d+)?|\d+,\d+|\d+", lambda m: _decimal(m.group(0)), text)
    # "eins Milliarde/Prozent" -> "eine Milliarde" / "ein Prozent" (num2words kennt nur die Grundzahl)
    text = re.sub(r"\beins(?=\s+(?:Million|Milliarde|Billion)\b)", "eine", text)
    text = re.sub(r"\beins(?=\s+[A-ZÄÖÜ])", "ein", text)
    return text


def _decimal(s: str) -> str:
    s = s.strip()
    if re.fullmatch(r"\d+(?:\.\d{3})+", s):                      # 800.000
        return _num(int(s.replace(".", "")))
    if re.fullmatch(r"\d+(?:\.\d{3})+,\d+", s):                  # 1.234,5
        whole, frac = s.split(",")
        return _num(int(whole.replace(".", ""))) + " Komma " + " ".join(_num(int(d)) for d in frac)
    if re.fullmatch(r"\d+,\d+", s):                              # 3,5
        whole, frac = s.split(",")
        return _num(int(whole)) + " Komma " + " ".join(_num(int(d)) for d in frac)
    if re.fullmatch(r"\d+\.\d+", s):                             # 3.5 (English decimal slipped through)
        whole, frac = s.split(".")
        return _num(int(whole)) + " Komma " + " ".join(_num(int(d)) for d in frac)
    if s.isdigit():
        return _num(int(s))
    return s


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
