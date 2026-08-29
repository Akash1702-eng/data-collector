"""
App-wide configuration and constants.
Loads secrets from .env file and provides structured config for the entire app.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ── Load .env ───────────────────────────────────────────────────────────────
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# ── Hugging Face ────────────────────────────────────────────────────────────
HF_TOKEN: str = os.getenv("HF_TOKEN", "")
HF_DATASET_REPO: str = os.getenv("HF_DATASET_REPO", "username/voice-authenticity-dataset")

# ── Admin ───────────────────────────────────────────────────────────────────
ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "change_me_in_production")

# ── Google Gemini API ───────────────────────────────────────────────────────
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", os.getenv("GOOGLE_API_KEY", ""))
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

# ── Audio ───────────────────────────────────────────────────────────────────
SAMPLE_RATE: int = 16_000          # 16 kHz mono WAV
MAX_RECORDING_SECONDS: int = 15    # auto-stop ceiling
MIN_RECORDING_SECONDS: float = 1.0 # reject clips shorter than this
AUDIO_FORMAT: str = "wav"

# ── Paths ───────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROMPTS_FILE = PROJECT_ROOT / "config" / "prompts.json"
LOCAL_FALLBACK_DIR = PROJECT_ROOT / "local_fallback"
LOCAL_FALLBACK_DIR.mkdir(exist_ok=True)

# ── Form Options ────────────────────────────────────────────────────────────
LANGUAGES = {
    "english_indian": "English (Indian)",
    "hindi":          "Hindi",
    "marathi":        "Marathi",
}

AGE_RANGES = ["18-24", "25-34", "35-44", "45-54", "55+"]

GENDERS = ["Male", "Female", "Non-binary", "Prefer not to say"]

ENVIRONMENTS = [
    "Quiet room",
    "Some background noise",
    "Noisy environment",
]

# ── Edge-TTS: Locale prefix per language key ────────────────────────────────
# Used to filter voices from edge_tts.list_voices() dynamically at runtime.
EDGE_TTS_LOCALE_MAP = {
    "english_indian": "en-IN",
    "hindi": "hi-IN",
    "marathi": "mr-IN",
}

# ── Hardcoded fallback (used only if runtime discovery fails) ───────────────
EDGE_TTS_VOICES = {
    "english_indian": [
        "en-IN-NeerjaNeural",
        "en-IN-PrabhatNeural",
        "en-IN-NeerjaExpressiveNeural",
    ],
    "hindi": [
        "hi-IN-SwaraNeural",
        "hi-IN-MadhurNeural",
    ],
    "marathi": [
        "mr-IN-AarohiNeural",
        "mr-IN-ManoharNeural",
    ],
}

# ── All known Indian Edge-TTS voices (cross-locale fallback pool) ───────────
# When a language has fewer unique voices than prompts, voices from other
# Indian locales can be pulled in since they can all read romanized text.
ALL_INDIAN_EDGE_VOICES = [
    "en-IN-NeerjaNeural", "en-IN-NeerjaExpressiveNeural", "en-IN-PrabhatNeural",
    "hi-IN-SwaraNeural", "hi-IN-MadhurNeural",
    "mr-IN-AarohiNeural", "mr-IN-ManoharNeural",
    "bn-IN-TanishaaNeural", "bn-IN-BashkarNeural",
    "gu-IN-DhwaniNeural", "gu-IN-NiranjanNeural",
    "kn-IN-SapnaNeural", "kn-IN-GaganNeural",
    "ml-IN-SobhanaNeural", "ml-IN-MidhunNeural",
    "ta-IN-PallaviNeural", "ta-IN-ValluvarNeural",
    "te-IN-ShrutiNeural", "te-IN-MohanNeural",
    "ur-IN-GulNeural", "ur-IN-SalmanNeural",
]

# ── Edge-TTS language code mapping ──────────────────────────────────────────
EDGE_TTS_LANG_CODES = {
    "english_indian": "en-IN",
    "hindi": "hi-IN",
    "marathi": "mr-IN",
}

# ── gTTS language code mapping ──────────────────────────────────────────────
GTTS_LANG_CODES = {
    "english_indian": "en",
    "hindi": "hi",
    "marathi": "mr",
}

# ── Coqui TTS language code mapping (for XTTS) ─────────────────────────────
COQUI_LANG_CODES = {
    "english_indian": "en",
    "hindi": "hi",
    "marathi": "mr",
}
