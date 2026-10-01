"""Text normalisation for German TTS: what the voice should SAY, not what the caption shows.

No TTS model reads "800.000", "UN", "AfD" or "Dr." the way a news anchor does. Numbers are spelled
out, acronyms are spelled letter by letter with GERMAN letter names ("U En", "A Ef De") unless
they are commonly pronounced as a word (NATO, UNO, NASA), abbreviations are expanded. Only the
text sent to the TTS is changed - captions keep the script's own spelling (align_captions matches
the heard words back to the script by sequence alignment, so "achthunderttausend" maps onto
"800.000").
"""
import re

from num2words import num2words

# Acronyms that German newsreaders pronounce as a word - leave them alone.
SAY_AS_WORD = {"NATO", "UNO", "NASA", "UNESCO", "UNICEF", "OPEC", "FIFA", "UEFA", "ESA", "ISIS", "IS", "DAX",
               "AIDS", "LASER", "RADAR", "ASEAN", "BRICS", "OSZE", "OECD", "SWIFT", "GEMA", "ADAC", "TÜV", "ELSTER",
               "MERCOSUR", "INTERPOL", "EUROPOL", "FRONTEX", "HAMAS", "TIKTOK", "AMAZON", "APPLE", "TESLA"}
# Acronyms that are ALWAYS spelled out (also when they don't look like one, e.g. mixed case).
SPELL_OUT = {"AfD", "CSU", "CDU", "SPD", "FDP", "USA", "UN", "EU", "UK", "US", "BBC", "CNN", "FBI", "CIA", "NSA", "IWF",
             "IMF", "EZB", "ECB", "BND", "KI", "IT", "TV", "PKW", "LKW", "SUV", "GPS", "DNA", "HIV", "WM", "EM", "NGO",
             "ICC", "IStGH", "IGH", "EuGH", "BGH", "BVerfG", "ARD", "ZDF", "RTL", "ÖVP", "FPÖ", "SVP", "DUP", "ANC",
             "GOP", "MEP", "MP", "PM", "CEO", "CFO", "KP", "ÖRR", "BIP", "GDP", "MI6", "MI5", "IDF", "PKK", "PLO",
             "WHO", "WTO"}
LETTER = {"A": "A", "B": "Be", "C": "Ce", "D": "De", "E": "E", "F": "Ef", "G": "Ge", "H": "Ha", "I": "I", "J": "Jot",
          "K": "Ka", "L": "El", "M": "Em", "N": "En", "O": "O", "P": "Pe", "Q": "Ku", "R": "Er", "S": "Es", "T": "Te",
          "U": "U", "V": "Vau", "W": "We", "X": "Ix", "Y": "Ypsilon", "Z": "Zett", "Ö": "Ö", "Ä": "Ä", "Ü": "Ü"}
ABBREVIATIONS = [
    (r"\bz\.\s?B\.", "zum Beispiel"), (r"\bbzw\.", "beziehungsweise"), (r"\bca\.", "circa"), (r"\bu\.\s?a\.", "unter anderem"),
    (r"\bd\.\s?h\.", "das heißt"), (r"\bDr\.", "Doktor"), (r"\bProf\.", "Professor"), (r"\bNr\.", "Nummer"),
    (r"\bMio\.", "Millionen"), (r"\bMrd\.", "Milliarden"), (r"\bMr\.", "Mister"), (r"\bMrs\.", "Misses"), (r"\bMs\.", "Miss"),
    (r"\bSt\.", "Sankt"), (r"\bevtl\.", "eventuell"), (r"\bggf\.", "gegebenenfalls"), (r"\binkl\.", "inklusive"),
    (r"\busw\.", "und so weiter"), (r"\bvs\.", "gegen"), (r"\bJh\.", "Jahrhundert"), (r"\bkm/h\b", "Kilometer pro Stunde"),
    (r"\bkm\b", "Kilometer"), (r"\bkg\b", "Kilogramm"), (r"\bkWh\b", "Kilowattstunden"), (r"\bMW\b", "Megawatt"), (r"\bGW\b", "Gigawatt"),
    (r"\bG7\b", "G Sieben"), (r"\bG20\b", "G Zwanzig"),  # vor _numbers(), sonst wird nur die Ziffer gesprochen ("Gsieben")
]


def _num(n: float | int, ordinal: bool = False) -> str:
    try:
        return num2words(n, lang="de", to="ordinal" if ordinal else "cardinal")
    except Exception:
        return str(n)


def _spell(token: str) -> str:
    letters = [LETTER.get(ch.upper(), ch) for ch in token if ch.isalpha()]
    return " ".join(letters)


def _acronym(match: re.Match) -> str:
    token, hyphen = match.group(1), match.group(2) or ""
    core = token.rstrip("s")                    # "NGOs" -> "NGO" + plural s
    plural = token.endswith("s") and core.isupper() and len(core) >= 2
    if core in SAY_AS_WORD:
        return token + hyphen
    if core in SPELL_OUT or (core.isupper() and 2 <= len(core) <= 5 and not re.search(r"[AEIOUÄÖÜ]{2}", core)):
        spelled = _spell(core)
        if hyphen:                              # "US-Angriffe" -> "U-Es-Angriffe" (one compound for the voice)
            return spelled.replace(" ", "-") + "-"
        return spelled + (" s" if plural else "")
    return token + hyphen


def _numbers(text: str) -> str:
    # 3,5 % / 3.5 % / 12 Prozent
    text = re.sub(r"(\d+(?:[.,]\d+)?)\s?%", lambda m: _decimal(m.group(1)) + " Prozent", text)
    # currency: 4,2 Mrd. €  /  $200  /  200 Euro
    text = re.sub(r"€\s?(\d[\d.,]*)", lambda m: _decimal(m.group(1)) + " Euro", text)
    text = re.sub(r"\$\s?(\d[\d.,]*)", lambda m: _decimal(m.group(1)) + " Dollar", text)
    text = re.sub(r"(\d[\d.,]*)\s?€", lambda m: _decimal(m.group(1)) + " Euro", text)
    text = re.sub(r"(\d[\d.,]*)\s?\$", lambda m: _decimal(m.group(1)) + " Dollar", text)
    # ordinals: "am 3." "der 2. Weltkrieg" (a dot directly after a small number, followed by a word)
    text = re.sub(r"\b(\d{1,2})\.(?=\s+[A-ZÄÖÜa-zäöü])", lambda m: _num(int(m.group(1)), ordinal=True) + "n", text)
    # years 1900-2099 read as a number word already ("zweitausendfünfundzwanzig") - num2words handles it
    # remaining numbers with German thousands dots / decimal commas
    text = re.sub(r"\d+(?:\.\d{3})+(?:,\d+)?|\d+,\d+|\d+", lambda m: _decimal(m.group(0)), text)
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


def normalize_for_tts(text: str) -> str:
    """German narration -> what the voice should pronounce."""
    from tts.aussprache_lexikon import anwenden as _aussprache_anwenden
    out = _aussprache_anwenden(text)  # Eigennamen/Fachbegriffe zuerst (config/brand/stimme/aussprache_lexikon.json),
    for pattern, repl in ABBREVIATIONS:                                       # bevor Zahlen/Akronyme angefasst werden
        out = re.sub(pattern, repl, out)
    out = _numbers(out)
    # acronyms: runs of letters with >= 2 capitals (UN, USA, AfD, NGOs, U.S.)
    out = re.sub(r"\b(?:[A-ZÄÖÜ]\.){2,}", lambda m: _spell(m.group(0).replace(".", "")), out)   # U.S. -> U Es
    out = re.sub(r"\b([A-ZÄÖÜ][A-Za-zÄÖÜäöü]*[A-ZÄÖÜ][A-Za-zÄÖÜäöü]*s?)\b(-)?", _acronym, out)
    out = out.replace("€", " Euro").replace("$", " Dollar").replace("£", " Pfund")
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out


if __name__ == "__main__":
    import sys
    print(normalize_for_tts(" ".join(sys.argv[1:]) or
          "Die UN und die USA: Dr. Brown sagte, 800.000 Menschen starben 1994; die AfD und die CDU, 3,5 % der NGOs, "
          "am 3. Oktober, US-Angriffe, die NATO und die UNO, 68 Angriffe seit September 2025, 4,2 Mrd. €."))
