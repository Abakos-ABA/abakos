"""TTS stage: approved script_text -> data/audio/<job_id>.wav.

Providers (config/settings.py: NEWS_TTS_PROVIDER): local Kokoro-82M via ONNX (default -
Apache-2.0, free, no account) or ElevenLabs (better voices, needs a paid key). Coqui XTTS-v2
is intentionally not supported: its license is non-commercial, which rules it out for a
monetized channel.
"""
import json
import logging
import os
import wave
from pathlib import Path

from config.settings import (
    NEWS_CHATTERBOX_CFG, NEWS_CHATTERBOX_EXAGGERATION,
    NEWS_CONTENT_LANGUAGE,
    DATA_DIR, ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID, KOKORO_MODEL_PATH, KOKORO_VOICES_PATH,
    NEWS_KOKORO_SPEED, NEWS_KOKORO_VOICE, NEWS_PIPER_LENGTH_SCALE, NEWS_TTS_PROVIDER, PIPER_MODEL_PATH, require,
)
from orchestrator import state_store
from script.localize import localized

logger = logging.getLogger(__name__)

_KOKORO_HELP = (
    "Kokoro model files missing. Put these two files in newsroom/models/ "
    "(from https://github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.0): "
    "kokoro-v1.0.onnx (~310 MB) and voices-v1.0.bin (~27 MB)."
)
_kokoro = None


def _get_kokoro():
    global _kokoro
    if _kokoro is None:
        if not (KOKORO_MODEL_PATH.exists() and KOKORO_VOICES_PATH.exists()):
            raise FileNotFoundError(_KOKORO_HELP)
        from kokoro_onnx import Kokoro  # lazy import: only needed for this provider

        _kokoro = Kokoro(str(KOKORO_MODEL_PATH), str(KOKORO_VOICES_PATH))
    return _kokoro


def _synthesize_kokoro(text: str, out_path):
    import soundfile as sf

    samples, sample_rate = _get_kokoro().create(text, voice=NEWS_KOKORO_VOICE, speed=NEWS_KOKORO_SPEED, lang="en-us")
    sf.write(str(out_path), samples, sample_rate)


def _synthesize_elevenlabs(text: str, out_path):
    require("ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID")
    from elevenlabs.client import ElevenLabs  # lazy import: only needed for this provider

    client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
    audio = client.text_to_speech.convert(
        voice_id=ELEVENLABS_VOICE_ID,
        model_id="eleven_multilingual_v2",
        text=text,
        output_format="pcm_24000",
    )
    with wave.open(str(out_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(b"".join(audio))


_piper = None


def _synthesize_piper(text: str, out_path):
    """Local Piper voice (models/piper/<voice>.onnx + .json). Works with both piper-tts APIs."""
    global _piper
    if not PIPER_MODEL_PATH.exists():
        raise FileNotFoundError(f"Piper voice missing: {PIPER_MODEL_PATH} (+ .json) - see README")
    if _piper is None:
        from piper import PiperVoice  # lazy import: only for this provider
        _piper = PiperVoice.load(str(PIPER_MODEL_PATH))
    with wave.open(str(out_path), "wb") as w:
        if hasattr(_piper, "synthesize_wav"):          # piper-tts >= 1.3
            from piper import SynthesisConfig
            _piper.synthesize_wav(text, w, syn_config=SynthesisConfig(length_scale=NEWS_PIPER_LENGTH_SCALE))
        else:                                           # piper-tts 1.2
            _piper.synthesize(text, w, length_scale=NEWS_PIPER_LENGTH_SCALE, sentence_silence=0.25)


WORKER_ANLAEUFE = 2       # Anlaeufe fuer einen abgestuerzten GPU-Worker (Exit-Code = Windows-Ausnahmecode)
WORKER_PAUSE_S = 20


def worker_mit_wiederholung(lauf, out_path, name: str = "worker", log=print, anlaeufe: int = WORKER_ANLAEUFE,
                            pause_s: float = WORKER_PAUSE_S):
    """Fuehrt lauf() (subprocess.run eines GPU-Workers, Rueckgabe CompletedProcess) aus und wiederholt es, wenn der
    Worker ABGESTUERZT ist (Exit-Code >= 0xC0000000 bzw. negativ, z.B. 0xC0000409 Fail-Fast im NVIDIA-Treiber
    nvcuda64.dll, 10.10.2026) - nicht bei regulaeren Fehlern (Exit 1: falscher Text, fehlende Referenz, ...), die
    bleiben wie bisher sofort ein Fehler. Vor jedem Anlauf wird eine halbfertige Ausgabedatei entfernt."""
    from tts.veredelung import exit_text, ist_absturz
    result = None
    for anlauf in range(1, max(1, int(anlaeufe)) + 1):
        Path(out_path).unlink(missing_ok=True)
        result = lauf()
        if not ist_absturz(result.returncode):
            return result
        if result.returncode == STILLSTAND_RC:
            log(f"{name} hing (keine Ausgabe mehr, Stillstands-Waechter hat ihn beendet) - Anlauf {anlauf}/{anlaeufe}")
        else:
            log(f"{name} abgestuerzt ({exit_text(result.returncode)}, typisch NVIDIA-Treiber nvcuda64.dll) - "
                f"Anlauf {anlauf}/{anlaeufe}")
        if anlauf < anlaeufe and pause_s > 0:
            import time
            time.sleep(pause_s)
    return result


_AUSGABE_WICHTIG = ("model loaded", "chunk ", "wrote ", "Traceback", "Error", "error", "CUDA", "cuda")


def worker_mit_ausgabe(cmd, cwd=None, prefix: str = "worker", tail: int = 40):
    """subprocess.run-Ersatz fuer GPU-Worker: reicht Fortschrittszeilen (model loaded / chunk i/n / wrote, Fehler)
    sofort an stdout weiter und behaelt die letzten `tail` Zeilen fuer die Fehlermeldung (CompletedProcess.stderr).
    Vorfall 21.10.2026: capture_output verschluckte die Zeilen des Chatterbox-Workers; neben Cinema-Renders auf der
    geteilten GPU brauchte eine 70-s-Szene ueber eine Stunde, und der Stillstands-Waechter des Tageslaufs
    (kein Log, keine Datei seit 60 min) beendete die lebende Vertonung - zweimal am selben Tag."""
    import collections
    import subprocess
    import time
    t0 = time.time()
    letzte = collections.deque(maxlen=tail)
    p = subprocess.Popen([str(c) for c in cmd], cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    assert p.stdout is not None
    for line in p.stdout:
        line = line.rstrip()
        if not line:
            continue
        letzte.append(line)
        if any(m in line for m in _AUSGABE_WICHTIG):
            print(f"  [{prefix} {time.time() - t0:.0f} s] {line[:200]}", flush=True)
    rc = p.wait()
    return subprocess.CompletedProcess(cmd, rc, stdout="", stderr="\n".join(letzte))


# Stillstands-Waechter (Vorfall 04.11.2026, Weltlage 00:00): der Chatterbox-Dauerprozess blieb bei «chunk 3/10» in CUDA
# haengen (spaeter Treiber-Exit 0xFFFFFFFF), der Client las blockierend auf stdout und wartete 20'038 s; die Spur hielt
# dabei 18,5 GB VRAM in der GPU-Warteschlange, die Karte war die ganze Nacht mit 22 von 23 GB voll, der Desktop stockte
# (Haenger 141 s) und das Shorts-Studio bekam zweimal 60 min keinen Platz. Darum: kommt STILLSTAND_S lang keine Zeile vom
# Worker (ein Chunk meldet sich normal nach Sekunden, Veredelung nach 1-7 s, Modell-Laden nach ~12-45 s), wird der Prozess
# beendet und der Auftrag wie ein Absturz gemeldet (worker_mit_wiederholung startet ihn neu).
STILLSTAND_S = float(os.environ.get("NEWS_TTS_STILLSTAND_S", "900"))
STILLSTAND_RC = -1          # negativer Exit-Code = Absturz (veredelung.ist_absturz), nie ein Windows-Exit-Code


class _ChatterboxServer:
    """Dauerprozess tts/chatterbox_worker.py --server: Modell einmal laden (Import + Laden kosten ~20 s je Aufruf), danach
    beliebig viele Auftraege. Folge 30.10.2026: 45 Modell-Ladevorgaenge = rund 9 min der Vertonung. Ein Absturz oder
    Fehler-Exit des Prozesses wird dem Aufrufer wie bei einem Einzelaufruf gemeldet (CompletedProcess), der naechste
    Auftrag startet den Prozess neu. Die Ausgabe liest ein eigener Thread; bleibt sie STILLSTAND_S lang aus, gilt der
    Worker als haengend und wird beendet (STILLSTAND_RC)."""

    def __init__(self, python, worker, cwd, prefix: str, stillstand_s: float | None = None):
        self.python, self.worker, self.cwd, self.prefix = python, worker, cwd, prefix
        self.stillstand_s = STILLSTAND_S if stillstand_s is None else float(stillstand_s)
        self.p = None
        self.q = None

    @staticmethod
    def _leser(p, q):
        try:
            for line in p.stdout:
                q.put(line.rstrip())
        except (OSError, ValueError):
            pass
        finally:
            q.put(None)                                    # EOF: Prozess beendet

    def _stillstand(self, seit_s: float, letzte):
        p, self.p = self.p, None
        msg = (f"Stillstand: {seit_s:.0f} s keine Ausgabe vom Worker (PID {getattr(p, 'pid', '?')}), "
               f"Prozess beendet (Waechter {self.stillstand_s:.0f} s)")
        print(f"  [{self.prefix}] {msg}", flush=True)
        letzte.append(msg)
        if p is not None:
            try:
                p.kill()
                p.wait(timeout=30)
            except Exception:  # noqa: BLE001
                pass
            _pipes_zu(p)

    def _lies_bis_marke(self):
        import collections
        import queue
        import time
        t0 = time.time()
        letzte = collections.deque(maxlen=40)
        rc = None
        while True:
            try:
                line = self.q.get(timeout=self.stillstand_s)
            except queue.Empty:
                self._stillstand(time.time() - t0, letzte)
                return STILLSTAND_RC, letzte
            if line is None:                               # Prozess gestorben
                return None, letzte
            if line.startswith("@@FERTIG"):
                rest = line.split(" ", 1)[1] if " " in line else ""
                rc = 0 if rest == "bereit" else int(rest)
                break
            if not line:
                continue
            letzte.append(line)
            if any(m in line for m in _AUSGABE_WICHTIG):
                print(f"  [{self.prefix} {time.time() - t0:.0f} s] {line[:200]}", flush=True)
        return rc, letzte

    def _starte(self):
        import queue
        import subprocess
        import threading
        self.p = subprocess.Popen([str(self.python), str(self.worker), "--server"], cwd=self.cwd, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, stdin=subprocess.PIPE, text=True, encoding="utf-8",
                                  errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.q = queue.Queue()
        threading.Thread(target=self._leser, args=(self.p, self.q), daemon=True,
                         name=f"tts-leser-{self.prefix}").start()
        rc, letzte = self._lies_bis_marke()
        if rc == STILLSTAND_RC:                            # Laden blieb haengen, Prozess schon beendet
            return STILLSTAND_RC, letzte
        if rc is None:                                 # Prozess vor "bereit" gestorben
            code = self.p.wait()
            self.p = None
            return code or 1, letzte
        return 0, letzte

    def lauf(self, args: list):
        """Ein Auftrag (Argumentliste wie beim Einzelaufruf, ohne Python/Skript) -> CompletedProcess."""
        import json
        import subprocess
        letzte = []
        if self.p is None or self.p.poll() is not None:
            rc, letzte = self._starte()
            if rc != 0:
                return subprocess.CompletedProcess(args, rc, stdout="", stderr=_NL.join(letzte))
        try:
            self.p.stdin.write(json.dumps([str(a) for a in args]) + _NL)
            self.p.stdin.flush()
            rc, letzte = self._lies_bis_marke()
        except (OSError, ValueError):
            rc, letzte = None, []
        if rc == STILLSTAND_RC:                            # haengender Worker beendet, naechster Auftrag startet neu
            return subprocess.CompletedProcess(args, STILLSTAND_RC, stdout="", stderr=_NL.join(letzte))
        if rc is None:                                 # Prozess waehrend des Auftrags gestorben
            code = self.p.wait() if self.p else 1
            self.p = None
            return subprocess.CompletedProcess(args, code or 1, stdout="", stderr=_NL.join(letzte))
        return subprocess.CompletedProcess(args, rc, stdout="", stderr=_NL.join(letzte))

    def schliessen(self):
        p, self.p = self.p, None
        if p is None:
            return
        try:
            p.stdin.write("quit" + _NL)
            p.stdin.flush()
            p.wait(timeout=30)
        except Exception:  # noqa: BLE001
            p.kill()
        _pipes_zu(p)


def _pipes_zu(p) -> None:
    for f in (getattr(p, "stdin", None), getattr(p, "stdout", None)):
        try:
            if f is not None:
                f.close()
        except Exception:  # noqa: BLE001
            pass


_NL = chr(10)
import threading as _threading  # noqa: E402
_server_lock = _threading.Lock()
_server_aktiv = False
_server_alle: list = []
_server_tl = None


class server_sitzung:
    """with server_sitzung(): _synthesize_chatterbox nutzt je Thread einen Dauerprozess (Modell einmal geladen) statt
    je Aufruf einen neuen. Beim Verlassen werden alle Prozesse beendet. Ausserhalb der Sitzung (und mit
    NEWS_TTS_SERVER=0) bleibt es beim Einzelaufruf wie bisher."""

    def __enter__(self):
        import os
        import threading
        global _server_aktiv, _server_tl
        _server_tl = threading.local()
        _server_aktiv = os.environ.get("NEWS_TTS_SERVER", "1") != "0"
        return self

    def __exit__(self, *exc):
        global _server_aktiv, _enhance_gemeinsam
        _server_aktiv = False
        _enhance_gemeinsam = None
        for sv in _server_alle:
            sv.schliessen()
        _server_alle.clear()
        return False


def _server_dieses_threads(python, worker, cwd, art: str = "chatterbox"):
    """Dauerprozess dieses Threads fuer `art` (je Spur einer): "chatterbox" oder "enhance"."""
    d = getattr(_server_tl, "server", None)
    if d is None:
        d = _server_tl.server = {}
    sv = d.get(art)
    if sv is None:
        sv = d[art] = _ChatterboxServer(python, worker, cwd, prefix=f"{art} {len(_server_alle) + 1}")
        _server_alle.append(sv)
    return sv


class _GemeinsamerServer:
    """Ein Dauerprozess fuer mehrere Spuren: Aufrufe nacheinander (Sperre). Resemble Enhance braucht je Satz/Szene bis ~9 GB
    VRAM-Spitze (gemessen 30.10.2026: 8,4-8,8 GB bei 33-53 s Ton) - zweimal nebeneinander plus zwei Chatterbox-Prozesse
    (je ~4 GB) sprengt die 24-GB-Karte (Ueberlauf in den Hauptspeicher: Satz in 164 s statt 12 s). Darum ein Prozess, den
    sich alle Spuren teilen."""

    def __init__(self, server):
        import threading
        self.server, self.sperre = server, threading.Lock()

    def lauf(self, args: list):
        with self.sperre:
            return self.server.lauf(args)

    def schliessen(self):
        self.server.schliessen()


_enhance_gemeinsam = None
ENHANCE_BRAUCHT_MB = 10500       # Enhance-Spitze (bis ~9 GB bei 30-s-Fenstern) + Luft


def vram_fuer_enhance_freimachen(log=print) -> bool:
    """Nur aus der exklusiven Veredelungs-Phase (kein Sprech-Auftrag laeuft): reicht der freie VRAM nicht fuer die
    Veredelung neben den geladenen Chatterbox-Prozessen (je ~4 GB), werden diese beendet; der naechste Sprech-Auftrag
    startet sie neu (~12 s). Messlauf 30.10.2026: ein fremder Cinema-Job belegte ~14 GB, Chatterbox (4 GB) + Enhance (9 GB)
    daneben liefen ueber die 24 GB, die Veredelung brauchte 16+ min statt ~15 s. True, wenn Prozesse beendet wurden."""
    try:
        import gpu_budget
        frei = gpu_budget.vram()[2]
    except Exception:  # noqa: BLE001
        return False
    if frei == 0 or frei >= ENHANCE_BRAUCHT_MB:
        return False
    beendet = 0
    for sv in list(_server_alle):
        if isinstance(sv, _ChatterboxServer) and sv.p is not None and "chatterbox" in sv.prefix:
            sv.schliessen()
            beendet += 1
    if beendet:
        log(f"  VRAM knapp ({frei} MB frei): {beendet} Chatterbox-Prozess(e) fuer die Veredelung beendet, starten neu")
    return bool(beendet)


def enhance_server():
    """Gemeinsamer Veredelungs-Dauerprozess (tts/_enhance_worker.py --server, Modell einmal geladen); None ausserhalb
    einer server_sitzung (dann bleibt es beim Einzelaufruf wie bisher)."""
    global _enhance_gemeinsam
    if not _server_aktiv:
        return None
    import threading
    with _server_lock:
        if _enhance_gemeinsam is None:
            from config.settings import BASE_DIR, ENHANCE_PYTHON
            sv = _ChatterboxServer(ENHANCE_PYTHON, BASE_DIR / "tts" / "_enhance_worker.py", str(BASE_DIR), "enhance")
            _enhance_gemeinsam = _GemeinsamerServer(sv)
            _server_alle.append(_enhance_gemeinsam)
        return _enhance_gemeinsam


def _synthesize_chatterbox(text: str, out_path, seed: int | None = None):
    """Chatterbox Multilingual in its own venv (tts/chatterbox_worker.py); the host's voice is the
    fixed reference wav in config/brand/voice_ref.wav, so every video sounds like the same person.

    `seed` ueberschreibt, wenn angegeben, das Stimm-Profil (das selbst meist seed=null hat): Chatterbox
    sampelt sonst mit unkontrolliertem RNG-Stand, darum klingt derselbe Name (z.B. "Tramp" aus dem
    Aussprache-Lexikon) von Aufruf zu Aufruf unterschiedlich deutlich/undeutlich (rexemres Beobachtung
    13.10.2026: Eigennamen "oft, aber nicht immer" falsch betont). weltlage_tts.sprich() setzt hier pro
    Versuch einen aus Text+Versuch abgeleiteten festen Seed: gleicher Text+Versuch -> reproduzierbar,
    ein neuer Versuch bei schlechter Kontrolle bekommt trotzdem einen anderen Seed und damit eine echte
    zweite Chance."""
    import subprocess
    import tempfile

    from config.settings import BASE_DIR, CHATTERBOX_PYTHON, NEWS_CONTENT_LANGUAGE
    from tts.stimme_profil import profil
    st = profil()          # Stimm-Profil A/B aus config/brand/stimme/profile.json (Referenz + Parameter, 30.09.2026)
    if not Path(CHATTERBOX_PYTHON).exists():
        raise FileNotFoundError(f"{CHATTERBOX_PYTHON} not found - create .venv-tts (see README)")
    with tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8", delete=False) as f:
        f.write(text)
        text_file = f.name
    cmd = [str(CHATTERBOX_PYTHON), str(BASE_DIR / "tts" / "chatterbox_worker.py"), "--text-file", text_file,
           "--out", str(out_path), "--lang", NEWS_CONTENT_LANGUAGE]
    # Ohne Referenz spricht Chatterbox mit seiner eingebauten Standardstimme - nie still dorthin ausweichen.
    if not st["ref_pfad"].exists():
        raise FileNotFoundError(f"{st['ref_pfad']} fehlt - Lataras Stimme braucht die Referenz, kein Rueckfall")
    cmd += ["--ref", str(st["ref_pfad"]), "--exaggeration", str(st["exaggeration"]), "--cfg", str(st["cfg"]),
            "--temperature", str(st["temperature"]), "--max-chars", str(st["max_chars"])]
    seed = seed if seed is not None else st.get("seed")
    if seed is not None:
        cmd += ["--seed", str(seed)]
    from config.settings import NEWS_WELTLAGE_STIMME_VEREDELN       # Variante A (rexemre 01.10.2026), Default an
    if NEWS_WELTLAGE_STIMME_VEREDELN:
        cmd += ["--veredeln"]
    if st.get("prosodie"):                       # Satzmelodie-Plan je Satz (Profil-Schalter, 18.10.2026)
        cmd += ["--prosodie"]
    from tts import gpu_spur                               # zentrale GPU-Warteschlange (29.09.), Fallback ohne; in einer Spur schon gebucht

    sv = (_server_dieses_threads(CHATTERBOX_PYTHON, BASE_DIR / "tts" / "chatterbox_worker.py", str(BASE_DIR))
          if _server_aktiv else None)

    def _lauf():
        with gpu_spur.slot("tts", name="tts chatterbox (newsroom)", vram_mb=5000):
            if sv is not None:
                with gpu_spur.phasen.gemeinsam():        # Sprechen mehrerer Spuren gleichzeitig ok, Veredeln nie daneben
                    return sv.lauf(cmd[2:])              # cmd = [python, worker, *argumente]
            return worker_mit_ausgabe(cmd, cwd=str(BASE_DIR), prefix="chatterbox")
    result = worker_mit_wiederholung(_lauf, out_path, name="chatterbox worker", log=logger.warning)
    Path(text_file).unlink(missing_ok=True)
    if result.returncode != 0 or not Path(out_path).exists():
        from tts.veredelung import exit_text
        raise RuntimeError(f"chatterbox worker failed ({exit_text(result.returncode)}):\n{result.stderr[-2500:]}")
    _tempo(out_path, float(st.get("tempo", 1.0)))
    if NEWS_WELTLAGE_STIMME_VEREDELN:
        from tts.veredelung import veredeln                # Schritt 2: Resemble Enhance + Klangkette, 24 kHz bleibt
        veredeln(out_path, log=logger.info)


def _tempo(wav_path, tempo: float):
    """Sprechtempo aus dem Stimm-Profil ("tempo", z.B. 1.15 = 15 % schneller, rexemre 30.09.2026 endgueltig; 1.2 zu schnell, 1.1 zu langsam). Chatterbox hat
    keinen Speed-Parameter, darum danach ffmpeg atempo (tonhoehenneutral, WSOLA) - nie per Resampling. Format bleibt
    24 kHz mono 16 bit (weltlage_tts.pruefe_stimme)."""
    if abs(tempo - 1.0) < 1e-6:
        return
    import os
    import subprocess
    ff = next(iter(Path(os.environ.get("LOCALAPPDATA", "")).glob("Microsoft/WinGet/Packages/Gyan.FFmpeg*/*/bin")), None)
    ffmpeg = str(ff / "ffmpeg.exe") if ff else "ffmpeg"
    src = Path(wav_path)
    tmp = src.with_name(src.stem + "_tempo.wav")
    r = subprocess.run([ffmpeg, "-y", "-v", "error", "-i", str(src), "-af", f"atempo={tempo}",
                        "-c:a", "pcm_s16le", "-ar", "24000", "-ac", "1", str(tmp)], capture_output=True, text=True)
    if r.returncode or not tmp.exists():
        raise RuntimeError(f"atempo {tempo} fehlgeschlagen: {r.stderr[-800:]}")
    tmp.replace(src)


def run(job_id: str) -> str:
    script = json.loads((DATA_DIR / "scripts" / f"{job_id}.approved.json").read_text(encoding="utf-8"))
    text = localized(script)["script_text"]
    if NEWS_CONTENT_LANGUAGE == "de":
        from tts.normalize_de import normalize_for_tts
        text = normalize_for_tts(text)      # what the voice says; captions keep the script's spelling
    out_path = DATA_DIR / "audio" / f"{job_id}.wav"

    if NEWS_TTS_PROVIDER == "elevenlabs":
        _synthesize_elevenlabs(text, out_path)
    elif NEWS_TTS_PROVIDER == "chatterbox":
        _synthesize_chatterbox(text, out_path)
    elif NEWS_TTS_PROVIDER == "piper":
        _synthesize_piper(text, out_path)
    else:
        _synthesize_kokoro(text, out_path)

    state_store.update_job(job_id, status="tts_done")
    logger.info("tts done for %s (%s) -> %s", job_id, NEWS_TTS_PROVIDER, out_path)
    return str(out_path)


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    run(sys.argv[1])
