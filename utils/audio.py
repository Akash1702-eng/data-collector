"""
Audio processing utilities.
Handles conversion from browser-captured audio (webm/wav) to standardized
16 kHz mono WAV format used throughout the dataset.
"""

import io
import tempfile
import shutil
from pathlib import Path

import numpy as np
import soundfile as sf

# ── Auto-detect ffmpeg from ffmpeg-downloader if not on PATH ────────────────
def _setup_ffmpeg():
    if shutil.which("ffmpeg"):
        return
    try:
        import ffmpeg_downloader as ffdl
        import os
        ffmpeg_path = Path(ffdl.ffmpeg_path).parent
        os.environ["PATH"] = str(ffmpeg_path) + os.pathsep + os.environ.get("PATH", "")
    except (ImportError, Exception):
        pass

_setup_ffmpeg()

from pydub import AudioSegment


def process_recording(audio_bytes: bytes) -> tuple[np.ndarray, float]:
    """
    Convert raw browser audio bytes (may be webm, ogg, or wav) to a
    16 kHz mono float32 numpy array.

    Returns:
        (audio_array, duration_seconds)
    """
    try:
        # First try reading directly with soundfile (works for WAV/FLAC)
        buf = io.BytesIO(audio_bytes)
        data, sr = sf.read(buf, dtype="float32")
    except Exception:
        # Fallback: use pydub which handles webm/ogg via ffmpeg
        buf = io.BytesIO(audio_bytes)
        seg = AudioSegment.from_file(buf)
        seg = seg.set_channels(1).set_frame_rate(16_000).set_sample_width(2)
        raw = np.array(seg.get_array_of_samples(), dtype=np.float32)
        data = raw / 32768.0  # int16 → float32
        sr = 16_000

    # Ensure mono
    if data.ndim > 1:
        data = data.mean(axis=1)

    # Resample to 16 kHz if needed
    if sr != 16_000:
        data = _resample(data, sr, 16_000)

    duration = len(data) / 16_000
    return data, duration


def save_wav(audio_array: np.ndarray, path: str | Path, sr: int = 16_000) -> Path:
    """Write a float32 numpy array to a WAV file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), audio_array, sr, subtype="PCM_16")
    return path


def load_wav(path: str | Path) -> tuple[np.ndarray, int]:
    """Load a WAV file and return (data, sample_rate)."""
    data, sr = sf.read(str(path), dtype="float32")
    return data, sr


def audio_bytes_to_wav_file(audio_bytes: bytes, output_path: str | Path) -> tuple[Path, float]:
    """
    Convenience: process browser audio and save as standardized WAV.
    Returns (saved_path, duration_seconds).
    """
    data, duration = process_recording(audio_bytes)
    saved = save_wav(data, output_path)
    return saved, duration


def wav_to_bytes(path: str | Path) -> bytes:
    """Read a WAV file and return its raw bytes (for st.audio playback)."""
    with open(path, "rb") as f:
        return f.read()


def _resample(data: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """Simple linear interpolation resampling (no external dependency)."""
    if orig_sr == target_sr:
        return data
    duration = len(data) / orig_sr
    target_len = int(duration * target_sr)
    indices = np.linspace(0, len(data) - 1, target_len)
    return np.interp(indices, np.arange(len(data)), data).astype(np.float32)
