"""TTS stage: approved script_text -> data/audio/<job_id>.wav.

Providers (config/settings.py: NEWS_TTS_PROVIDER): local Kokoro-82M via ONNX (default -
Apache-2.0, free, no account) or ElevenLabs (better voices, needs a paid key). Coqui XTTS-v2
is intentionally not supported: its license is non-commercial, which rules it out for a
monetized channel.
"""
import json
import logging
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


def _synthesize_chatterbox(text: str, out_path):
    """Chatterbox Multilingual in its own venv (tts/chatterbox_worker.py); the host's voice is the
    fixed reference wav in config/brand/voice_ref.wav, so every video sounds like the same person."""
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
    if st.get("seed") is not None:
        cmd += ["--seed", str(st["seed"])]
    from config.settings import NEWS_WELTLAGE_STIMME_VEREDELN       # Variante A (Marlon 01.10.2026), Default an
    if NEWS_WELTLAGE_STIMME_VEREDELN:
        cmd += ["--veredeln"]
    import gpu_budget                                      # zentrale GPU-Warteschlange (29.09.), Fallback ohne
    with gpu_budget.slot("tts", name="tts chatterbox (newsroom)", vram_mb=5000):
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                cwd=str(BASE_DIR))
    Path(text_file).unlink(missing_ok=True)
    if result.returncode != 0 or not Path(out_path).exists():
        raise RuntimeError(f"chatterbox worker failed:\n{result.stderr[-2500:]}")
    _tempo(out_path, float(st.get("tempo", 1.0)))
    if NEWS_WELTLAGE_STIMME_VEREDELN:
        from tts.veredelung import veredeln                # Schritt 2: Resemble Enhance + Klangkette, 24 kHz bleibt
        veredeln(out_path, log=logger.info)


def _tempo(wav_path, tempo: float):
    """Sprechtempo aus dem Stimm-Profil ("tempo", z.B. 1.15 = 15 % schneller, Marlon 30.09.2026 endgueltig; 1.2 zu schnell, 1.1 zu langsam). Chatterbox hat
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
