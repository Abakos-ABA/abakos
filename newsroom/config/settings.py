"""Central config: every tunable is an env var with a sane default, read once at import time."""
import os
from pathlib import Path

from config import nowindow  # noqa: F401  (pythonw: child consoles stay hidden, see config/nowindow.py)

try:
    from dotenv import load_dotenv
    # Second channel (e.g. NEWS_ENV_FILE=.env.doku for Steel & Ledger): its file wins, .env fills the rest.
    if os.environ.get("NEWS_ENV_FILE"):
        load_dotenv(Path(__file__).resolve().parent.parent / os.environ["NEWS_ENV_FILE"], override=True)
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

# ffmpeg installed via winget lands on the *user* PATH, which processes started before the install
# (or some Task Scheduler contexts) don't have - find the winget package folder ourselves.
import shutil
if not shutil.which("ffmpeg"):
    for _bin in Path(os.environ.get("LOCALAPPDATA", "")).glob("Microsoft/WinGet/Packages/Gyan.FFmpeg*/*/bin"):
        os.environ["PATH"] = str(_bin) + os.pathsep + os.environ.get("PATH", "")
        break

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
# A second channel MUST get its own data/state (jobs.db), otherwise it picks up the other channel's jobs.
DATA_DIR = BASE_DIR / os.environ.get("NEWS_DATA_DIR", "data")
STATE_DIR = BASE_DIR / os.environ.get("NEWS_STATE_DIR", "state")
SECRETS_DIR = BASE_DIR / "secrets"

for _d in (DATA_DIR, STATE_DIR, SECRETS_DIR):
    _d.mkdir(parents=True, exist_ok=True)
for _sub in ("raw", "clusters", "research", "scripts", "audio", "captions", "broll", "video", "thumbs"):
    (DATA_DIR / _sub).mkdir(parents=True, exist_ok=True)

JOBS_DB_PATH = STATE_DIR / "jobs.db"

# --- Keys ---
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "")

# --- Telegram ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# --- YouTube ---
NEWS_UPLOAD_METHOD = os.environ.get("NEWS_UPLOAD_METHOD", "playwright")  # "playwright" | "api"
# The one channel uploads go to (a Google account can own several; the Studio URL is pinned to it).
NEWS_YOUTUBE_CHANNEL_ID = os.environ.get("NEWS_YOUTUBE_CHANNEL_ID", "")
# public | unlisted | private. Use "private" for dry runs / a cautious first week.
NEWS_UPLOAD_VISIBILITY = os.environ.get("NEWS_UPLOAD_VISIBILITY", "public").lower()
YOUTUBE_CLIENT_SECRET_PATH = SECRETS_DIR / "client_secret.json"
# One OAuth token per channel (the consent picks the channel) - never share it between channels.
YOUTUBE_TOKEN_PATH = SECRETS_DIR / os.environ.get("NEWS_YOUTUBE_TOKEN_FILE", "youtube_token.json")
PLAYWRIGHT_PROFILE_DIR = SECRETS_DIR / "playwright_profile"
# Keep this True (visible browser) for the first login and for every run until you've
# verified the automation end-to-end — headless makes failures much harder to diagnose.
NEWS_PLAYWRIGHT_HEADLESS = os.environ.get("NEWS_PLAYWRIGHT_HEADLESS", "false").lower() == "true"
# Use a real installed browser (not Playwright's bundled Chromium): Google's sign-in refuses most
# automated browsers, and a normal browser profile is what makes the one-time login work.
# "msedge" is officially supported and preinstalled on Windows; "chrome" works if Chrome is installed.
NEWS_PLAYWRIGHT_CHANNEL = os.environ.get("NEWS_PLAYWRIGHT_CHANNEL", "msedge")

# Language of the narration/captions/metadata. Research, script and the compliance editor always
# work in English (the sources are English); script/localize.py translates the approved script
# into this language before TTS. YouTube's auto-dubbing translates FROM the declared language, so
# the uploader sets it from here as well.
NEWS_CONTENT_LANGUAGE = os.environ.get("NEWS_CONTENT_LANGUAGE", "en").lower()
LANG_PACK = {
    "en": {"name": "English", "kicker": "WORLD BRIEF", "hashtags": ["#News", "#WorldNews"],
           "quote_marks": ("“", "”"),
           # kicker line of the reusable on-screen card templates (video/cards.py)
           "cards": {"stat": "THE NUMBER", "quote": "QUOTE", "context": "CONTEXT",
                     "takeaway": "WHAT IT MEANS", "developing": "NOT YET CONFIRMED"}},
    "de": {"name": "German", "kicker": "WELTLAGE KOMPAKT", "hashtags": ["#Nachrichten", "#Weltpolitik"],
           "quote_marks": ("„", "“"),
           "cards": {"stat": "DIE ZAHL", "quote": "ZITAT", "context": "KONTEXT",
                     "takeaway": "WAS BEDEUTET DAS?", "developing": "NOCH UNBESTÄTIGT"}},
}
if NEWS_CONTENT_LANGUAGE not in LANG_PACK:
    raise RuntimeError(f"NEWS_CONTENT_LANGUAGE={NEWS_CONTENT_LANGUAGE!r} - add it to LANG_PACK in config/settings.py")
LANG = dict(LANG_PACK[NEWS_CONTENT_LANGUAGE])
if os.environ.get("NEWS_FORMAT", "landscape").lower() == "shorts":
    LANG["hashtags"] = ["#Shorts"] + LANG["hashtags"]
# faster-whisper model: the English-only model is better for English, everything else needs multilingual
NEWS_WHISPER_MODEL = os.environ.get("NEWS_WHISPER_MODEL") or ("base.en" if NEWS_CONTENT_LANGUAGE == "en" else "base")

# --- Format ---
# "landscape" = 16:9 1920x1080 regular YouTube video (host opens every topic, cutaways/sources in
# between); "shorts" = 9:16 1080x1920. Geometry lives in video/layout.py.
NEWS_FORMAT = os.environ.get("NEWS_FORMAT", "landscape").lower()
if NEWS_FORMAT not in ("landscape", "shorts"):
    raise RuntimeError(f"NEWS_FORMAT={NEWS_FORMAT!r} - use landscape or shorts")

# --- Format ---
# "landscape" = 16:9 1920x1080 regular YouTube video (host opens every topic, cutaways/sources in
# between); "shorts" = 9:16 1080x1920. Geometry lives in video/layout.py.
NEWS_FORMAT = os.environ.get("NEWS_FORMAT", "landscape").lower()
if NEWS_FORMAT not in ("landscape", "shorts"):
    raise RuntimeError(f"NEWS_FORMAT={NEWS_FORMAT!r} - use landscape or shorts")

# --- Format ---
# "landscape" = 16:9 1920x1080 regular YouTube video (host opens every topic, cutaways/sources in
# between); "shorts" = 9:16 1080x1920. Geometry lives in video/layout.py.
NEWS_FORMAT = os.environ.get("NEWS_FORMAT", "landscape").lower()
if NEWS_FORMAT not in ("landscape", "shorts"):
    raise RuntimeError(f"NEWS_FORMAT={NEWS_FORMAT!r} - use landscape or shorts")

# --- Avatar / video ---
NEWS_AVATAR_MODE = os.environ.get("NEWS_AVATAR_MODE", "placeholder")  # "placeholder" | "musetalk"
AVATAR_REFERENCE_DIR = BASE_DIR / "video" / "avatar" / "reference"
AVATAR_WORKFLOWS_DIR = BASE_DIR / "video" / "avatar" / "workflows"
COMFYUI_BASE_URL = os.environ.get("COMFYUI_BASE_URL", "http://127.0.0.1:8188")
# Folder of the ComfyUI *portable* install (contains python_embeded/ and ComfyUI/). When set, the
# pipeline starts ComfyUI itself for the B-roll stage and stops it afterwards to free the VRAM.
COMFYUI_DIR = os.environ.get("COMFYUI_DIR", "")
# B-roll shot size / length / quality (Wan 2.2 TI2V-5B). Dimensions must be multiples of 32,
# frames = 4n+1. 576x1024 x 73 frames ~ 3 s at 24 fps; assemble.py upscales to 1080x1920.
NEWS_BROLL_WIDTH = int(os.environ.get("NEWS_BROLL_WIDTH", "1024" if NEWS_FORMAT == "landscape" else "576"))
NEWS_BROLL_HEIGHT = int(os.environ.get("NEWS_BROLL_HEIGHT", "576" if NEWS_FORMAT == "landscape" else "1024"))
NEWS_BROLL_FRAMES = int(os.environ.get("NEWS_BROLL_FRAMES", "73"))
NEWS_BROLL_STEPS = int(os.environ.get("NEWS_BROLL_STEPS", "20"))
# Wan2.2-TI2V-5B-Turbo (step + CFG distillation, Apache-2.0 base): the LoRA in ComfyUI/models/loras
# turns 20 steps at CFG 5 into 4 steps at CFG 1 - measured in docs/BENCHMARK.md. "0" = off.
NEWS_WAN_TURBO = os.environ.get("NEWS_WAN_TURBO", "0") == "1"
NEWS_WAN_TURBO_LORA = os.environ.get("NEWS_WAN_TURBO_LORA", "Wan22_TI2V_5B_Turbo_lora_rank_64_fp16.safetensors")
NEWS_WAN_TURBO_STEPS = int(os.environ.get("NEWS_WAN_TURBO_STEPS", "4"))
# Render a per-video cold-open host clip with the story's mood (script "host_mood") - ~2 min of GPU
# per video on the 4090; "0" keeps only the reusable neutral clips.
NEWS_HOST_CLIP_PER_JOB = os.environ.get("NEWS_HOST_CLIP_PER_JOB", "1") == "1"
# Lip-sync of the host's spoken segments with LatentSync 1.6 (vendor/LatentSync, .venv-lipsync,
# models/latentsync). "0" = host clips stay mouth-closed voice-over.
NEWS_LIPSYNC = os.environ.get("NEWS_LIPSYNC", "1") == "1"
NEWS_LIPSYNC_STEPS = int(os.environ.get("NEWS_LIPSYNC_STEPS", "8"))
# Preview mode: generated clips (masters/intro/host) at 960x528 and fewer steps, upscaled once with
# Real-ESRGAN to 1920x1080 (video/upscale.py). Screenshots, cards, captions are native 1080p anyway.
NEWS_PREVIEW = os.environ.get("NEWS_PREVIEW", "1") == "1"
NEWS_HOST_STEPS = int(os.environ.get("NEWS_HOST_STEPS", "14" if NEWS_PREVIEW else "20"))
NEWS_UPSCALE_MODEL = os.environ.get("NEWS_UPSCALE_MODEL", "RealESRGAN_x2plus.pth")
# SageAttention 2.2 (installed into the ComfyUI python 2026-09-22): +30-40% on Ada, no quality loss. "0" to disable.
NEWS_SAGE_ATTENTION = os.environ.get("NEWS_SAGE_ATTENTION", "1") == "1"
# MuseTalk isn't pip-installable — it's a cloned repo with its own inference script/env.
MUSETALK_REPO_PATH = os.environ.get("MUSETALK_REPO_PATH", "")
MUSETALK_PYTHON = os.environ.get("MUSETALK_PYTHON", "python")

# --- Triggers: tick cadence, RSS scan cadence, breaking-news detection, fixed slots ---
NEWS_TICK_SECONDS = int(os.environ.get("NEWS_TICK_SECONDS", "60"))              # pipeline loop (cheap when idle)
NEWS_INGEST_INTERVAL_MINUTES = int(os.environ.get("NEWS_INGEST_INTERVAL_MINUTES", "15"))  # RSS scan, around the clock
# A cluster is a breaking candidate when this many distinct feeds report it within this many hours;
# the research model then scores it 0-10 and only >= NEWS_BREAKING_MIN_SCORE is produced at once
# (outside the night window, priority), at most NEWS_BREAKING_MAX_PER_DAY times a day.
NEWS_BREAKING_MIN_SOURCES = int(os.environ.get("NEWS_BREAKING_MIN_SOURCES", "4"))
NEWS_BREAKING_WINDOW_HOURS = float(os.environ.get("NEWS_BREAKING_WINDOW_HOURS", "3"))
NEWS_BREAKING_MIN_SCORE = int(os.environ.get("NEWS_BREAKING_MIN_SCORE", "7"))
NEWS_BREAKING_MAX_PER_DAY = int(os.environ.get("NEWS_BREAKING_MAX_PER_DAY", "2"))

# --- Pacing / autonomy ---
NEWS_REVIEW_WINDOW_MINUTES = int(os.environ.get("NEWS_REVIEW_WINDOW_MINUTES", "120"))
NEWS_MAX_CATCHUP_POSTS_PER_DAY = int(os.environ.get("NEWS_MAX_CATCHUP_POSTS_PER_DAY", "4"))
NEWS_TARGET_POSTS_PER_DAY = int(os.environ.get("NEWS_TARGET_POSTS_PER_DAY", "2"))
# How many videos may be in production at once (GPU is shared; the owner reviews one at a time).
NEWS_MAX_INFLIGHT = int(os.environ.get("NEWS_MAX_INFLIGHT", "1"))
# Local hours in which the pipeline may start/advance jobs, e.g. "1-7" (wraps: "22-6"); empty = always.
# The PC is shared with you - keep GPU-heavy work in the night. (Manual `--once` runs ignore it.)
NEWS_ACTIVE_HOURS = os.environ.get("NEWS_ACTIVE_HOURS", "")
# A review never auto-publishes before this local hour, so a video rendered at 3 am gives you the
# morning to reject it instead of going live while you sleep.
NEWS_PUBLISH_NOT_BEFORE_HOUR = int(os.environ.get("NEWS_PUBLISH_NOT_BEFORE_HOUR", "8"))

# --- LLM provider ---
# "auto": Anthropic when ANTHROPIC_API_KEY is set, otherwise a local Ollama model (no account,
# no per-token cost). Anthropic is the recommended provider for the editor/compliance stage.
NEWS_LLM_PROVIDER = os.environ.get("NEWS_LLM_PROVIDER", "auto")
if NEWS_LLM_PROVIDER == "auto":
    NEWS_LLM_PROVIDER = "anthropic" if ANTHROPIC_API_KEY else "ollama"
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")

# Per-stage model tiers; defaults depend on the provider. Env vars override (empty = default).
_DEFAULT_MODELS = {
    "anthropic": ("claude-haiku-4-5-20251001", "claude-sonnet-5", "claude-sonnet-5"),
    # qwen3:8b fits in the VRAM left free by the desktop (~16 GB); 27-30B models don't and thrash.
    "ollama": ("qwen3:8b", "qwen3:8b", "qwen3:8b"),
}
_dm_research, _dm_script, _dm_editor = _DEFAULT_MODELS[NEWS_LLM_PROVIDER]
NEWS_MODEL_RESEARCH = os.environ.get("NEWS_MODEL_RESEARCH") or _dm_research
NEWS_MODEL_SCRIPT = os.environ.get("NEWS_MODEL_SCRIPT") or _dm_script
NEWS_MODEL_EDITOR = os.environ.get("NEWS_MODEL_EDITOR") or _dm_editor

# --- Weltlage Kompakt (Langformat): Skript-Generator tools/weltlage_skript.py ---
# Prompt: "analyse" = Redaktions-/Analyse-Konzept vom 01.10.2026 (config/prompts/weltlage_analyse.md, Standard),
# "klassisch" = bisheriges Meldungsformat als Fallback (config/prompts/weltlage_klassisch.md).
NEWS_WELTLAGE_SKRIPT_PROMPT = os.environ.get("NEWS_WELTLAGE_SKRIPT_PROMPT", "analyse")
# Laenge des Analyse-Skripts (01.10.2026): "folge" = rund 4 bis 5 Minuten fertige Folge (Standard), "lang" = 5 bis 9 Min. Sprechtext
NEWS_WELTLAGE_SKRIPT_LAENGE = os.environ.get("NEWS_WELTLAGE_SKRIPT_LAENGE", "folge")
# LLM: "claude" = Claude-Code-CLI im Abo (headless, ohne Werkzeuge, keine GPU-Last), "ollama" = lokales
# NEWS_MODEL_SCRIPT (GPU). Modell nur fuer "claude" (Alias wie opus/sonnet oder volle Modell-ID).
NEWS_WELTLAGE_SKRIPT_LLM = os.environ.get("NEWS_WELTLAGE_SKRIPT_LLM", "claude")
NEWS_WELTLAGE_SKRIPT_MODELL = os.environ.get("NEWS_WELTLAGE_SKRIPT_MODELL", "opus")
NEWS_CLAUDE_CLI = os.environ.get("NEWS_CLAUDE_CLI", r"C:\Users\Marlon\projekte\jarvis\bin\claude.exe")

# --- Weltlage Kompakt: Musikbett Cold Open (Standard seit Marlons Entscheid 01.10.2026 16:27, Variante 3 = dunkler
# Synth-Pad mit Ticken und tiefem Puls, Task 20261001-150542-feaf) - Musik nur unter der ersten Szene (Cold Open),
# nicht in den Analyse-Passagen. Asset/Rohdatei liegt in config/brand/coldopen_musik/aktiv.json (ACE-Step 1.5, MIT),
# Pegel/Ducking/Loop-Verlaengerung macht tools/weltlage_rohschnitt.py (apply_coldopen_musikbett).
NEWS_WELTLAGE_COLDOPEN_MUSIKBETT = os.environ.get("NEWS_WELTLAGE_COLDOPEN_MUSIKBETT", "1") == "1"
# Pegel relativ zur Sprachlautheit der Cold-Open-Stimme in dB (negativ = leiser). Erster Test 01.10.2026 mit -26 dB
# war fuer Marlon nicht hoerbar; zweiter Test gleichentags mit -19 dB (Richtwert -18 bis -20) ist der neue Default.
NEWS_WELTLAGE_COLDOPEN_MUSIKBETT_DB = float(os.environ.get("NEWS_WELTLAGE_COLDOPEN_MUSIKBETT_DB", "-19"))
# Fade-in/Fade-out der Musik in Sekunden (Fade-out endet exakt beim Schnitt in den Bumper).
NEWS_WELTLAGE_COLDOPEN_MUSIKBETT_FADE_IN = float(os.environ.get("NEWS_WELTLAGE_COLDOPEN_MUSIKBETT_FADE_IN", "1.0"))
NEWS_WELTLAGE_COLDOPEN_MUSIKBETT_FADE_OUT = float(os.environ.get("NEWS_WELTLAGE_COLDOPEN_MUSIKBETT_FADE_OUT", "1.5"))

# --- Weltlage Kompakt: B-Roll / Symbolclips (tools/weltlage_broll.py, Marlon 01.10.2026) ---
# Nur frei lizenzierte Clips (Pexels, Pixabay, Wikimedia Commons CC0/PD/CC-BY/CC-BY-SA, NASA), nie Sender, Agenturen,
# Social Media oder YouTube. Lizenz pro Clip in <folge>/broll_lizenzen.json, Attribution in broll_attribution.txt.
NEWS_WELTLAGE_BROLL = os.environ.get("NEWS_WELTLAGE_BROLL", "1") == "1"                 # an/aus
NEWS_WELTLAGE_BROLL_ABSTAND = float(os.environ.get("NEWS_WELTLAGE_BROLL_ABSTAND", "30"))   # Ziel-Abstand in s (20-40)
NEWS_WELTLAGE_BROLL_VARIANTEN = os.environ.get("NEWS_WELTLAGE_BROLL_VARIANTEN", "wand,pip,voll")   # Reihenfolge = Rotation
NEWS_WELTLAGE_BROLL_QUELLEN = os.environ.get("NEWS_WELTLAGE_BROLL_QUELLEN", "pexels,pixabay,commons,nasa")
NEWS_WELTLAGE_BROLL_MODELL = os.environ.get("NEWS_WELTLAGE_BROLL_MODELL", "sonnet")   # Suchbegriffe (Claude-CLI)
NEWS_WELTLAGE_BROLL_MODELL_WAHL = os.environ.get("NEWS_WELTLAGE_BROLL_MODELL_WAHL", "opus")   # strenge Clipwahl

# --- Weltlage Kompakt: realistischeres Studio-Compositing der stehenden Pose (Marlons Wahl 01.10.2026, Task
# 20261001-165559-5e26/180145-c47f): Kontaktschatten unter den Schuhen, Schlagschatten, Bodenspiegelung, kuehleres
# Studiolicht, Randlicht/Light-Wrap von der LED-Wand, Koernung (video/composite_fx.py). Nur die stehende Pose (bei
# der Sitz-Pose verdeckt das Pult die Fuesse). Default an.
NEWS_WELTLAGE_COMPOSITE_FX = os.environ.get("NEWS_WELTLAGE_COMPOSITE_FX", "1") == "1"

# --- Weltlage Kompakt: Lipsync-Gesicht KI-hochskaliert (Task 20261001-184254-d71b, video/gesicht_hd.py): das enge
# Gesichtsfenster geht mit Real-ESRGAN + GFPGAN (untere Gesichtshaelfte) statt Lanczos in LatentSync, die Mundpartie der
# Ausgabe wird nochmals mit GFPGAN nachgezeichnet. Kostet ~1-2 min GPU pro 7-s-Stueck zusaetzlich. Marlon hat den
# Vergleichsclip am 01.10.2026 abgenommen: Default an fuer alle Folgen. tools/weltlage_abnahme.py prueft dazu, dass
# jedes _fenster.json unter <ordner>/_schnitt/_freisteller tatsaechlich mit HD gerechnet wurde.
NEWS_WELTLAGE_LIPSYNC_HD = os.environ.get("NEWS_WELTLAGE_LIPSYNC_HD", "1") == "1"

# --- Weltlage Kompakt: LatentSync-Staerke der Mundbewegung (video/freisteller_lipsync.py GUIDANCE, Task
# 20261001-202910-0180, gesenkt auf 1,5 in Task 20261002-002731-6861): die Probe vom 29.09. (Task 1fa2) hatte bewusst
# auf 2,5 erhoeht (Mund ~50 % staerker als mit LatentSync-Standard 1,5); auf 2,0 gesenkt wirkte Marlon am 01.10. immer
# noch zu stark. Jetzt auf den LatentSync-Standard 1,5 gesenkt. Bei erneuten Beschwerden ueber zu starke/zu schwache
# Mundbewegung hier weiterdrehen statt den Code zu aendern.
NEWS_WELTLAGE_LIPSYNC_GUIDANCE = float(os.environ.get("NEWS_WELTLAGE_LIPSYNC_GUIDANCE", "1.5"))

# --- Weltlage Kompakt: taeglicher Lauf zu fixen Zeiten (tools/weltlage_tageslauf.py, Marlon 01.10.2026) ---
# Die resident laufende Pipeline (Aufgabe AbakosNewsroomPipeline, orchestrator/pipeline.py) startet pro Slot einen
# Tageslauf: Skript -> Bilder -> Stimme -> Rohschnitt/Lipsync -> B-Roll -> Abnahme -> Thumbnail -> Upload. Slots =
# Veroeffentlichungszeiten (lokal, HH:MM, Komma-Liste; Vorschlag Vorbild-Analyse 01.10.: erst 07:00, spaeter
# 07:00,18:00). Die Produktion beginnt VORLAUF Stunden vorher; ist sie frueher fertig, wartet der Upload bis zum Slot.
NEWS_WELTLAGE_TAEGLICH = os.environ.get("NEWS_WELTLAGE_TAEGLICH", "0") == "1"
NEWS_WELTLAGE_SLOTS = [s.strip() for s in os.environ.get("NEWS_WELTLAGE_SLOTS", "07:00").split(",") if s.strip()]
NEWS_WELTLAGE_VORLAUF_STUNDEN = float(os.environ.get("NEWS_WELTLAGE_VORLAUF_STUNDEN", "4"))
# Sichtbarkeit nur fuer Weltlage-Folgen (die Shorts-Pipeline behaelt NEWS_UPLOAD_VISIBILITY): public|unlisted|private
NEWS_WELTLAGE_UPLOAD_VISIBILITY = os.environ.get("NEWS_WELTLAGE_UPLOAD_VISIBILITY", "public").lower()
# spaetestens so viele Stunden nach dem Slot noch veroeffentlichen, sonst Folge verwerfen (veraltet) + Meldung
NEWS_WELTLAGE_MAX_VERSPAETUNG_STUNDEN = float(os.environ.get("NEWS_WELTLAGE_MAX_VERSPAETUNG_STUNDEN", "5"))
# Upload im Browser: so lange auf 100 Prozent Dateitransfer + Verarbeitungsstart warten (Minuten)
NEWS_UPLOAD_TIMEOUT_MINUTEN = float(os.environ.get("NEWS_UPLOAD_TIMEOUT_MINUTEN", "60"))

# --- TTS provider ---
# "auto": ElevenLabs when key + voice id are set; otherwise local Kokoro-82M (Apache-2.0) for
# English, local Piper (MIT engine; German voice licensed per-voice, see NEWS_PIPER_VOICE below)
# for other languages.
# NOTE: Coqui XTTS-v2 is deliberately NOT an option - its license is non-commercial.
NEWS_TTS_PROVIDER = os.environ.get("NEWS_TTS_PROVIDER", "auto")
if NEWS_TTS_PROVIDER == "auto":
    if ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID:
        NEWS_TTS_PROVIDER = "elevenlabs"
    else:
        # German: Latara's Chatterbox clone, never a silent fallback to Piper (owner, 2026-09-30)
        NEWS_TTS_PROVIDER = "kokoro" if NEWS_CONTENT_LANGUAGE == "en" else "chatterbox"
# Latara's fixed voice since 2026-09-30 (owner's decision, sample 2 of task 20260930-125950-d8b3): the Chatterbox
# clone below (NEWS_TTS_PROVIDER=chatterbox, voice_ref.wav, exaggeration 0.4, cfg 0.4), enforced for Weltlage by
# tools/weltlage_tts.py. The Piper switch of 2026-09-29 is reverted; Piper only when explicitly selected.
# CAUTION (analysis 2026-09-30 evening): voice_ref.wav itself is a Piper de_DE-ramona-low recording (16 kHz, 8.88 s,
# speaker similarity 0.974 to a Piper re-synthesis of its text) - so the clone is the SAME speaker as the Piper voice,
# only articulated by Chatterbox. A genuinely different voice needs a new reference file, not a new engine.
# Piper voice (was Latara's voice 2026-09-29/30 only): de_DE-ramona-low, trained on the M-AILABS Speech Dataset (LibriVox recordings + pre-1964
# Gutenberg texts, both public domain; caito.de license explicitly permits commercial use,
# including monetized redistribution) - safe for the monetized YouTube channel.
PIPER_MODEL_PATH = BASE_DIR / "models" / "piper" / os.environ.get("NEWS_PIPER_VOICE", "de_DE-ramona-low.onnx")
# Chatterbox (MIT, multilingual, GPU) lives in its own venv because of its pinned torch;
# NEWS_TTS_PROVIDER=chatterbox selects it. The host voice = the reference wav below.
CHATTERBOX_PYTHON = BASE_DIR / ".venv-tts" / "Scripts" / "python.exe"
VOICE_REF_PATH = CONFIG_DIR / "brand" / "voice_ref.wav"
# --- Weltlage Kompakt: Stimm-Veredelung Variante A (Marlons Wahl 01.10.2026, Task 20261001-165559-5e26/180145-c47f):
# satzweise natuerliche Pausen + leiser synthetischer Atmer (tts/chatterbox_worker.py), danach Resemble Enhance
# (.venv-enhance, MIT, CPU) gegen den dumpfen Klang und eine leichte Klangkette (tts/veredelung.py). Default an;
# Ausgabe bleibt 24 kHz mono (STIMME_SR in tools/weltlage_tts.py), damit Stimmpruefung/Abnahme unveraendert bleiben.
NEWS_WELTLAGE_STIMME_VEREDELN = os.environ.get("NEWS_WELTLAGE_STIMME_VEREDELN", "1") == "1"
ENHANCE_PYTHON = BASE_DIR / ".venv-enhance" / "Scripts" / "python.exe"
NEWS_CHATTERBOX_EXAGGERATION = float(os.environ.get("NEWS_CHATTERBOX_EXAGGERATION", "0.4"))
NEWS_CHATTERBOX_CFG = float(os.environ.get("NEWS_CHATTERBOX_CFG", "0.4"))
NEWS_PIPER_LENGTH_SCALE = float(os.environ.get("NEWS_PIPER_LENGTH_SCALE", "0.95"))   # <1 = a bit faster
MODELS_DIR = BASE_DIR / "models"
WHISPER_MODEL_DIR = MODELS_DIR / "whisper"   # faster-whisper caches its model here
KOKORO_MODEL_PATH = MODELS_DIR / "kokoro-v1.0.onnx"
KOKORO_VOICES_PATH = MODELS_DIR / "voices-v1.0.bin"
NEWS_KOKORO_VOICE = os.environ.get("NEWS_KOKORO_VOICE", "af_heart")
NEWS_KOKORO_SPEED = float(os.environ.get("NEWS_KOKORO_SPEED", "1.05"))

# --- B-roll ---
# "comfyui": generate shots via Wan 2.2 (needs ComfyUI running + workflows/broll_template.json).
# "none": skip B-roll (plain background + captions) - for testing before ComfyUI is set up.
NEWS_BROLL_MODE = os.environ.get("NEWS_BROLL_MODE", "comfyui")

# --- Content config files ---
SOURCES_YAML = CONFIG_DIR / "sources.yaml"
VARIANCE_POOL_YAML = CONFIG_DIR / "variance_pool.yaml"
STYLE_GUIDE_MD = CONFIG_DIR / "style_guide.md"
PROMPTS_DIR = CONFIG_DIR / "prompts"


def require(*names):
    """Raise with a clear message if any of the named settings are empty — call at the start
    of a stage that actually needs them, not at import time, so unrelated stages keep working."""
    missing = [n for n in names if not globals().get(n)]
    if missing:
        raise RuntimeError(
            f"Missing required setting(s): {', '.join(missing)}. Set them in newsroom/.env "
            f"(see newsroom/.env.example)."
        )
