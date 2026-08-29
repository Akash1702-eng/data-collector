"""
TTS engine abstraction layer.
Provides a unified interface for multiple TTS backends:
  - CoquiTTSEngine: local neural TTS via coqui-tts (XTTS v2 + VITS)
  - EdgeTTSEngine: Microsoft Edge neural TTS (cloud, many voices/languages)
  - GTTSEngine: Google Text-to-Speech (lightweight cloud TTS, no API key)
  - BarkTTSEngine: Suno Bark (optional, GPU-heavy)
"""

import asyncio
import tempfile
import logging
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf

# ── Auto-detect ffmpeg from ffmpeg-downloader if not on PATH ────────────────
def _setup_ffmpeg():
    """Add ffmpeg-downloader's binary path to PATH if ffmpeg isn't found."""
    if shutil.which("ffmpeg"):
        return
    try:
        import ffmpeg_downloader as ffdl
        ffmpeg_path = Path(ffdl.ffmpeg_path).parent
        import os
        os.environ["PATH"] = str(ffmpeg_path) + os.pathsep + os.environ.get("PATH", "")
    except (ImportError, Exception):
        pass

_setup_ffmpeg()

import sys, os
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import (
    EDGE_TTS_VOICES,
    EDGE_TTS_LOCALE_MAP,
    EDGE_TTS_LANG_CODES,
    ALL_INDIAN_EDGE_VOICES,
    GTTS_LANG_CODES,
    COQUI_LANG_CODES,
    SAMPLE_RATE,
)
from utils.audio import save_wav, _resample

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Runtime Edge-TTS voice discovery (cached)
# ═══════════════════════════════════════════════════════════════════════════

_DISCOVERED_VOICES: dict[str, list[str]] | None = None


def discover_edge_tts_voices() -> dict[str, list[str]]:
    """
    Query edge_tts.list_voices() at runtime and group by language key.
    Returns a dict mapping language keys to lists of voice ShortNames.
    Results are cached after the first call.
    """
    global _DISCOVERED_VOICES
    if _DISCOVERED_VOICES is not None:
        return _DISCOVERED_VOICES

    try:
        import edge_tts

        async def _fetch():
            return await edge_tts.list_voices()

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    voices = pool.submit(asyncio.run, _fetch()).result()
            else:
                voices = loop.run_until_complete(_fetch())
        except RuntimeError:
            voices = asyncio.run(_fetch())

        # Group voices by our language keys using locale prefix
        result: dict[str, list[str]] = {}
        for lang_key, locale_prefix in EDGE_TTS_LOCALE_MAP.items():
            lang_voices = [
                v["ShortName"]
                for v in voices
                if v["ShortName"].startswith(locale_prefix)
            ]
            if lang_voices:
                result[lang_key] = lang_voices

        _DISCOVERED_VOICES = result
        total = sum(len(v) for v in result.values())
        logger.info(f"Discovered {total} Edge-TTS voices across {len(result)} languages")
        return result

    except Exception as e:
        logger.warning(f"Edge-TTS voice discovery failed: {e}. Using hardcoded fallback.")
        _DISCOVERED_VOICES = EDGE_TTS_VOICES
        return _DISCOVERED_VOICES


# ═══════════════════════════════════════════════════════════════════════════
# Base class
# ═══════════════════════════════════════════════════════════════════════════

class TTSEngine(ABC):
    """Abstract base class for TTS engines."""

    name: str = "base"

    @abstractmethod
    def list_voices(self, language: str) -> list[str]:
        """Return available voice IDs for the given language key."""
        ...

    @abstractmethod
    def synthesize(
        self,
        text: str,
        voice_id: str,
        output_path: str | Path,
        language: str,
    ) -> Path:
        """Generate speech and save to output_path. Returns the path."""
        ...

    def supports_cloning(self) -> bool:
        """Whether this engine supports voice cloning."""
        return False

    def clone_voice(
        self,
        text: str,
        reference_wav: str | Path,
        output_path: str | Path,
        language: str,
    ) -> Path:
        """Clone a voice using a reference WAV. Override in subclasses."""
        raise NotImplementedError(f"{self.name} does not support voice cloning")

    @classmethod
    def is_available(cls) -> bool:
        """Check if this engine's dependencies are installed."""
        return True


# ═══════════════════════════════════════════════════════════════════════════
# Coqui TTS (local neural TTS)
# ═══════════════════════════════════════════════════════════════════════════

class CoquiTTSEngine(TTSEngine):
    name = "coqui_tts"

    _xtts_model = None
    _vits_model = None

    XTTS_MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"
    VITS_MODEL_NAME = "tts_models/en/vctk/vits"

    @classmethod
    def is_available(cls) -> bool:
        try:
            from TTS.api import TTS
            return True
        except ImportError:
            return False

    def _get_xtts(self):
        """Lazy-load XTTS v2 model."""
        if self._xtts_model is None:
            from TTS.api import TTS
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(f"Loading XTTS v2 on {device}...")
            CoquiTTSEngine._xtts_model = TTS(self.XTTS_MODEL_NAME).to(device)
        return self._xtts_model

    def _get_vits(self):
        """Lazy-load VITS model (English multi-speaker)."""
        if self._vits_model is None:
            from TTS.api import TTS
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(f"Loading VITS on {device}...")
            CoquiTTSEngine._vits_model = TTS(self.VITS_MODEL_NAME).to(device)
        return self._vits_model

    def list_voices(self, language: str) -> list[str]:
        voices = []

        # XTTS v2 — multilingual, supports all our languages
        try:
            xtts = self._get_xtts()
            if hasattr(xtts, "speakers") and xtts.speakers:
                for spk in xtts.speakers[:5]:  # Limit to first 5 speakers
                    voices.append(f"xtts_v2:{spk}")
        except Exception as e:
            logger.warning(f"Could not list XTTS voices: {e}")

        # VITS — English only, 109 speakers
        if language in ("english_indian", "en"):
            try:
                vits = self._get_vits()
                if hasattr(vits, "speakers") and vits.speakers:
                    for spk in vits.speakers[:5]:
                        voices.append(f"vits:{spk}")
            except Exception as e:
                logger.warning(f"Could not list VITS voices: {e}")

        return voices

    def synthesize(
        self,
        text: str,
        voice_id: str,
        output_path: str | Path,
        language: str,
    ) -> Path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        lang_code = COQUI_LANG_CODES.get(language, "en")
        model_tag, speaker = voice_id.split(":", 1)

        if model_tag == "xtts_v2":
            tts = self._get_xtts()
            tts.tts_to_file(
                text=text,
                file_path=str(output_path),
                speaker=speaker,
                language=lang_code,
            )
        elif model_tag == "vits":
            tts = self._get_vits()
            tts.tts_to_file(
                text=text,
                file_path=str(output_path),
                speaker=speaker,
            )
        else:
            raise ValueError(f"Unknown Coqui model tag: {model_tag}")

        # Ensure 16 kHz output
        _ensure_16khz(output_path)
        return output_path

    def supports_cloning(self) -> bool:
        return True

    def clone_voice(
        self,
        text: str,
        reference_wav: str | Path,
        output_path: str | Path,
        language: str,
    ) -> Path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        lang_code = COQUI_LANG_CODES.get(language, "en")
        tts = self._get_xtts()
        tts.tts_to_file(
            text=text,
            file_path=str(output_path),
            speaker_wav=str(reference_wav),
            language=lang_code,
        )
        _ensure_16khz(output_path)
        return output_path


# ═══════════════════════════════════════════════════════════════════════════
# Edge TTS (Microsoft cloud neural TTS — no API key needed)
# ═══════════════════════════════════════════════════════════════════════════

class EdgeTTSEngine(TTSEngine):
    name = "edge_tts"

    @classmethod
    def is_available(cls) -> bool:
        try:
            import edge_tts
            return True
        except ImportError:
            return False

    def list_voices(self, language: str) -> list[str]:
        """
        Return ALL available Edge-TTS voices for this language,
        discovered dynamically at runtime. Falls back to hardcoded list.
        """
        discovered = discover_edge_tts_voices()
        voices = discovered.get(language, [])
        if not voices:
            # Fallback to hardcoded
            voices = EDGE_TTS_VOICES.get(language, [])
        return voices

    def list_all_indian_voices(self) -> list[str]:
        """Return all Indian Edge-TTS voices across all locales."""
        discovered = discover_edge_tts_voices()
        all_voices = []
        for lang_voices in discovered.values():
            all_voices.extend(lang_voices)
        # Also include any from the static fallback not already found
        for v in ALL_INDIAN_EDGE_VOICES:
            if v not in all_voices:
                all_voices.append(v)
        return all_voices

    def synthesize(
        self,
        text: str,
        voice_id: str,
        output_path: str | Path,
        language: str,
    ) -> Path:
        import edge_tts

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Edge-tts outputs mp3 by default — save as mp3 then convert
        mp3_path = output_path.with_suffix(".mp3")

        async def _generate():
            communicate = edge_tts.Communicate(text, voice_id)
            await communicate.save(str(mp3_path))

        # Run async in sync context
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    pool.submit(asyncio.run, _generate()).result()
            else:
                loop.run_until_complete(_generate())
        except RuntimeError:
            asyncio.run(_generate())

        # Convert mp3 → 16 kHz mono WAV
        from pydub import AudioSegment
        seg = AudioSegment.from_mp3(str(mp3_path))
        seg = seg.set_channels(1).set_frame_rate(SAMPLE_RATE).set_sample_width(2)
        seg.export(str(output_path), format="wav")

        # Clean up mp3
        if mp3_path.exists():
            mp3_path.unlink()

        return output_path


# ═══════════════════════════════════════════════════════════════════════════
# gTTS (Google Text-to-Speech — lightweight, cloud, no API key)
# ═══════════════════════════════════════════════════════════════════════════

class GTTSEngine(TTSEngine):
    name = "gtts"

    # gTTS supported languages that we use
    _SUPPORTED_LANGS = {"en", "hi", "mr"}

    @classmethod
    def is_available(cls) -> bool:
        try:
            import gtts
            return True
        except ImportError:
            return False

    def list_voices(self, language: str) -> list[str]:
        """
        gTTS has one voice per language — return ["gtts_default"] if the
        language is supported, otherwise empty list (graceful skip).
        """
        lang_code = GTTS_LANG_CODES.get(language, "")
        if lang_code in self._SUPPORTED_LANGS:
            return ["gtts_default"]
        logger.warning(
            f"gTTS does not support language '{language}' (code='{lang_code}'). "
            f"Skipping gTTS for this language."
        )
        return []

    def synthesize(
        self,
        text: str,
        voice_id: str,
        output_path: str | Path,
        language: str,
    ) -> Path:
        import gtts

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        lang_code = GTTS_LANG_CODES.get(language, "en")

        # gTTS saves mp3 — convert to 16 kHz mono WAV
        mp3_path = output_path.with_suffix(".mp3")
        tts = gtts.gTTS(text=text, lang=lang_code)
        tts.save(str(mp3_path))

        from pydub import AudioSegment
        seg = AudioSegment.from_mp3(str(mp3_path))
        seg = seg.set_channels(1).set_frame_rate(SAMPLE_RATE).set_sample_width(2)
        seg.export(str(output_path), format="wav")

        # Clean up mp3
        if mp3_path.exists():
            mp3_path.unlink()

        return output_path


# ═══════════════════════════════════════════════════════════════════════════
# Bark TTS (optional, GPU-heavy)
# ═══════════════════════════════════════════════════════════════════════════

class BarkTTSEngine(TTSEngine):
    name = "bark"

    SPEAKER_PRESETS = [
        "v2/en_speaker_0",
        "v2/en_speaker_1",
        "v2/en_speaker_2",
        "v2/en_speaker_3",
        "v2/en_speaker_4",
        "v2/en_speaker_5",
        "v2/en_speaker_6",
        "v2/en_speaker_7",
        "v2/en_speaker_8",
        "v2/en_speaker_9",
    ]

    @classmethod
    def is_available(cls) -> bool:
        try:
            from bark import generate_audio, SAMPLE_RATE as BARK_SR
            return True
        except ImportError:
            return False

    def list_voices(self, language: str) -> list[str]:
        # Bark is effectively English-only for reliable output
        if language in ("english_indian", "en"):
            return self.SPEAKER_PRESETS[:5]
        return []

    def synthesize(
        self,
        text: str,
        voice_id: str,
        output_path: str | Path,
        language: str,
    ) -> Path:
        from bark import generate_audio, SAMPLE_RATE as BARK_SR

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        audio_array = generate_audio(text, history_prompt=voice_id)

        # Resample to 16 kHz if Bark's native rate differs
        if BARK_SR != SAMPLE_RATE:
            audio_array = _resample(audio_array, BARK_SR, SAMPLE_RATE)

        save_wav(audio_array, output_path, SAMPLE_RATE)
        return output_path


# ═══════════════════════════════════════════════════════════════════════════
# Engine registry / discovery
# ═══════════════════════════════════════════════════════════════════════════

def get_available_engines() -> list[TTSEngine]:
    """Return instances of all TTS engines that are currently installed."""
    engines = []
    for cls in [CoquiTTSEngine, EdgeTTSEngine, GTTSEngine, BarkTTSEngine]:
        if cls.is_available():
            engines.append(cls())
    return engines


def get_engine_by_name(name: str) -> Optional[TTSEngine]:
    """Get a specific engine by name."""
    mapping = {
        "coqui_tts": CoquiTTSEngine,
        "edge_tts": EdgeTTSEngine,
        "gtts": GTTSEngine,
        "bark": BarkTTSEngine,
    }
    cls = mapping.get(name)
    if cls and cls.is_available():
        return cls()
    return None


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _ensure_16khz(path: Path):
    """Re-encode a WAV file to 16 kHz mono if it isn't already."""
    data, sr = sf.read(str(path), dtype="float32")
    if data.ndim > 1:
        data = data.mean(axis=1)
    if sr != SAMPLE_RATE:
        data = _resample(data, sr, SAMPLE_RATE)
        sf.write(str(path), data, SAMPLE_RATE, subtype="PCM_16")
