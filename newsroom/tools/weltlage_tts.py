"""Weltlage Kompakt - Sprachspur pro Szene/Meldung mit Lataras fester Stimme: Chatterbox-Klon «Ramona»
(Chatterbox Multilingual, Referenz config/brand/voice_ref.wav, exaggeration 0.4, cfg 0.4, 24 kHz mono).
Marlons Entscheid 30.09.2026 (Hoerprobe Nr. 2 aus Task 20260930-125950-d8b3, reports/stimmen_ramona_20260930/
2_ramona_chatterbox_alt.wav): klarer und verstaendlicher als Piper. Die Piper-Umstellung vom 29.09.2026
(de_DE-ramona-low) ist fuer die Moderatorin zurueckgenommen.

    python tools/weltlage_tts.py <folgenordner>              # fehlende audio/<id>.wav erzeugen
    python tools/weltlage_tts.py <folgenordner> --neu s_themen [id ...]   # diese Eintraege neu sprechen
    python tools/weltlage_tts.py <folgenordner> --pruefen    # nur Stimmen-Pruefung aller audio/*.wav
    python tools/weltlage_tts.py --probe <text> <out.wav>    # einzelne Probe (gleiche Engine + Pruefung)

Referenz + Parameter kommen seit 30.09.2026 abends aus dem aktiven Stimm-Profil (config/brand/stimme/profile.json,
A = bisher, B = satzweise/ruhiger, Task 20260930-182721-1dc4); pruefe_stimme() akzeptiert jedes dort eingetragene
Chatterbox-Profil.

Reihenfolge einer Folge: tools/weltlage_update_themen.py -> tools/weltlage_tts.py -> tools/weltlage_rohschnitt.py.
GPU: Chatterbox reiht sich selbst in die GPU-Warteschlange ein (tts_client._synthesize_chatterbox ->
gpu_budget.slot) - diesen Aufruf NIE zusaetzlich in gpu_queue.py run einwickeln.

Engine-Nachweis: zu jeder audio/<id>.wav schreibt das Werkzeug audio/<id>.tts.json (Engine, Referenz-Hash,
Parameter, sha256 der wav) und eine Zeile in audio/tts_engine.log. pruefe_stimme() verlangt 24 kHz mono UND einen
passenden Nachweis mit engine=chatterbox und identischem Hash - eine Piper-Datei (16 kHz) oder eine Datei ohne
Nachweis wird abgelehnt, weltlage_rohschnitt.py bricht dann ab.

Chatterbox haengt gelegentlich einen Kauderwelsch-Nachsatz an (Testlauf 29.09.): jede Datei wird darum mit
faster-whisper (CPU, keine GPU) abgeschrieben und bei zu vielen Zusatzwoertern bis zu zweimal neu gesprochen.
"""
import difflib
import hashlib
import json
import re
import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ENGINE = "chatterbox"
STIMME_SR = 24000
# Referenz + Parameter kommen aus dem aktiven Stimm-Profil (config/brand/stimme/profile.json, tts/stimme_profil.py):
# A = Stand 30.09.2026 (voice_ref.wav c5dc5bbf..., ex 0.4, cfg 0.4), B = optimiert (Task 20260930-182721-1dc4).
from tts.stimme_profil import bekannte_ref_hashes, profil as _profil  # noqa: E402
_P = _profil()
REF_SHA256 = _P["ref_sha256"]
EXAGGERATION = _P["exaggeration"]
CFG = _P["cfg"]
TEMPO = float(_P.get("tempo", 1.0))   # Sprechtempo (atempo nach Chatterbox, tts_client._tempo), Marlon 30.09.2026: 1.15 endgueltig (1.2 zu schnell, 1.1 zu langsam)


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _nachweis(wav: Path) -> Path:
    return wav.with_suffix(".tts.json")


def pruefe_stimme(wav: Path) -> str | None:
    """None wenn die Datei nachweislich vom Chatterbox-Klon stammt, sonst eine Fehlermeldung."""
    try:
        with wave.open(str(wav)) as w:
            sr, ch = w.getframerate(), w.getnchannels()
    except Exception as e:
        return f"{wav.name}: nicht lesbar ({e})"
    if sr != STIMME_SR or ch != 1:
        alt = " - vermutlich Piper (abgewaehlt 30.09.)" if sr in (16000, 22050) else ""
        return f"{wav.name}: {sr} Hz / {ch} Kanal statt {STIMME_SR} Hz mono (Chatterbox){alt}"
    nw = _nachweis(wav)
    if not nw.exists():
        return f"{wav.name}: kein Engine-Nachweis {nw.name}"
    meta = json.loads(nw.read_text(encoding="utf-8"))
    if meta.get("engine") != ENGINE or meta.get("ref_sha256") not in bekannte_ref_hashes():
        return f"{wav.name}: Nachweis sagt engine={meta.get('engine')}, ref={str(meta.get('ref_sha256'))[:12]}"
    # streng seit 30.09.2026 23:00 (Stimmwechsel auf Profil C/Kerstin + Tempo, seit 23:00 1.10): nur das AKTIVE Profil zaehlt,
    # eine Datei einer frueheren Stimme (z.B. Ramona, Profil A/B) oder mit anderem Tempo wird abgelehnt
    if meta.get("ref_sha256") != REF_SHA256 or abs(float(meta.get("tempo", 1.0)) - TEMPO) > 1e-6:
        return (f"{wav.name}: alte Stimme/Tempo (Profil {meta.get('profil')}, ref {str(meta.get('ref_sha256'))[:12]}, "
                f"tempo {meta.get('tempo', 1.0)}) statt aktivem Profil {_P['profil']} (ref {REF_SHA256[:12]}, tempo {TEMPO})")
    if meta.get("wav_sha256") != sha256(wav):
        return f"{wav.name}: Hash passt nicht zum Nachweis (Datei nachtraeglich veraendert)"
    return None


def sprechtext_veraltet(text: str, wav: Path) -> str | None:
    """Meldung, wenn audio/<id>.wav aus einem anderen TTS-Text stammt als dem, den normalize_for_tts (inkl.
    Aussprache-Lexikon) heute aus dem Szenentext macht. Vorfall 02.10.2026: die Stimme der Folge war um 00:38-01:11
    gerechnet, das Lexikon (u.a. Trump -> Tramp) haengt erst seit 01:15 in normalize_for_tts - ein Neustart des Laufs
    hielt die alten Dateien fuer gueltig, weil nur Engine/Profil/Hash der wav geprueft wurden."""
    from tts.normalize_de import normalize_for_tts
    meta = json.loads(_nachweis(wav).read_text(encoding="utf-8"))
    soll = hashlib.sha256(normalize_for_tts(text).encode("utf-8")).hexdigest()
    if meta.get("text_sha256") != soll:
        return f"{wav.name}: Sprechtext/Aussprache-Lexikon seit dem Rendern geaendert"
    return None


def _pruefe_einstellung():
    ref = _P["ref_pfad"]
    if not ref.exists() or sha256(ref) != REF_SHA256:
        raise SystemExit(f"{ref} fehlt oder passt nicht zum Hash von Stimm-Profil {_P['profil']}")


_whisper = None


def _abschrift(wav: Path) -> str:
    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel
        from config.settings import WHISPER_MODEL_DIR
        _whisper = WhisperModel("base", device="cpu", compute_type="int8", download_root=str(WHISPER_MODEL_DIR))
    segs, _ = _whisper.transcribe(str(wav), language="de", beam_size=5)
    return " ".join(s.text for s in segs)


def _woerter(t: str) -> list[str]:
    return re.findall(r"\w+", t.lower())


def _kontrolle(text: str, wav: Path) -> dict:
    """Vergleicht die Whisper-Abschrift mit dem Sprechtext; Zusatzwoerter am Ende = Kauderwelsch-Nachsatz."""
    try:
        ab = _abschrift(wav)
    except Exception as e:                       # ohne Whisper nicht blockieren, nur vermerken
        return {"ok": True, "hinweis": f"keine Abschrift ({e})"}
    soll, ist = _woerter(text), _woerter(ab)
    sm = difflib.SequenceMatcher(None, soll, ist, autojunk=False)
    treffer = sum(b.size for b in sm.get_matching_blocks())
    letzter = max((b.b + b.size for b in sm.get_matching_blocks() if b.size), default=0)
    extra_ende = len(ist) - letzter
    quote = treffer / max(1, len(soll))
    return {"ok": quote >= 0.6 and extra_ende <= 3, "quote": round(quote, 3), "extra_woerter_ende": extra_ende,
            "abschrift": ab.strip()}


def sprich(text: str, out: Path, versuche: int = 3, log: Path | None = None) -> dict:
    from tts.normalize_de import normalize_for_tts
    from tts.tts_client import _synthesize_chatterbox
    norm = normalize_for_tts(text)
    for v in range(1, versuche + 1):
        t0 = time.time()
        _synthesize_chatterbox(norm, out)
        k = _kontrolle(text, out)
        if k["ok"] or v == versuche:
            break
        print(f"  {out.name}: Versuch {v} verworfen (Quote {k.get('quote')}, {k.get('extra_woerter_ende')} "
              f"Zusatzwoerter am Ende) - neu", flush=True)
    with wave.open(str(out)) as w:
        sr, laenge = w.getframerate(), w.getnframes() / w.getframerate()
    from config.settings import NEWS_WELTLAGE_STIMME_VEREDELN
    meta = {"engine": ENGINE, "modell": "ChatterboxMultilingualTTS (chatterbox-tts 0.1.7, .venv-tts)",
            "profil": _P["profil"], "ref": _P["ref"], "ref_sha256": REF_SHA256, "exaggeration": EXAGGERATION,
            "cfg": CFG, "tempo": TEMPO, "veredelt": NEWS_WELTLAGE_STIMME_VEREDELN,
            "temperature": _P["temperature"], "max_chars": _P["max_chars"], "seed": _P.get("seed"), "sr": sr, "laenge_s": round(laenge, 2), "versuche": v, "kontrolle": k,
            "text_sha256": hashlib.sha256(norm.encode("utf-8")).hexdigest(), "wav_sha256": sha256(out),
            "zeit": time.strftime("%Y-%m-%d %H:%M:%S"), "dauer_s": round(time.time() - t0, 1)}
    _nachweis(out).write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")
    log = log or out.parent / "tts_engine.log"
    with open(log, "a", encoding="utf-8") as f:
        f.write(f"{meta['zeit']}  {out.name}  engine={ENGINE}  profil={_P['profil']}  ref={REF_SHA256[:12]}  ex={EXAGGERATION} "
                f"cfg={CFG}  tempo={TEMPO}  {sr} Hz  {laenge:.1f} s  sha256={meta['wav_sha256'][:16]}  "
                f"versuche={v}  kontrolle={'ok' if k['ok'] else 'NICHT OK'}\n")
    return meta


def main():
    args = sys.argv[1:]
    if args[:1] == ["--probe"]:
        _pruefe_einstellung()
        meta = sprich(args[1], Path(args[2]))
        print(json.dumps(meta, indent=1, ensure_ascii=False))
        return
    ordner = Path(args[0]) if args and not args[0].startswith("--") else ROOT / "data" / "weltlage_test_20260929"
    szenen = json.loads((ordner / "texte.json").read_text(encoding="utf-8"))["szenen"]
    audio = ordner / "audio"
    if "--pruefen" in args:
        ids = {s["id"] for s in szenen}
        fehler = [f for f in (pruefe_stimme(p) for p in sorted(audio.glob("*.wav")) if p.stem in ids) if f]
        print("\n".join(fehler) or f"alle audio/*.wav sind Chatterbox Profil {_P['profil']} tempo {TEMPO} (24 kHz mono, Nachweis + Hash ok)")
        sys.exit(1 if fehler else 0)
    neu = set(args[args.index("--neu") + 1:]) if "--neu" in args else set()
    _pruefe_einstellung()
    audio.mkdir(exist_ok=True)
    for s in szenen:
        out = audio / f"{s['id']}.wav"
        if out.exists() and s["id"] not in neu and not pruefe_stimme(out):
            veraltet = sprechtext_veraltet(s["text"], out)
            if not veraltet:
                continue
            print(f"  {s['id']}: {veraltet} - neu sprechen", flush=True)
        meta = sprich(s["text"], out)
        print(f"Chatterbox: {s['id']} {meta['laenge_s']} s, Versuche {meta['versuche']}, "
              f"Kontrolle {meta['kontrolle'].get('quote')}", flush=True)
    print("TTS FERTIG", flush=True)


if __name__ == "__main__":
    main()
