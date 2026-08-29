"""
Synthetic voice generation orchestrator.

Central module that handles:
  - Generating synthetic TTS versions of human prompts (skipping open-ended prompts)
  - Voice rotation (no immediate repeats within a session)
  - Dual-engine support (edge_tts + gtts)
  - Idempotency & single-trigger protection (skip if synthetic rows or in-flight runs exist)
  - Per-prompt error handling with summary logging
"""

import time
import random
import datetime
import tempfile
import logging
import threading
from pathlib import Path

import soundfile as sf

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import (
    HF_TOKEN,
    HF_DATASET_REPO,
    ALL_INDIAN_EDGE_VOICES,
    SAMPLE_RATE,
)
from utils.tts_engines import get_engine_by_name
from utils.hf_upload import upload_synthetic_batch

logger = logging.getLogger(__name__)

# ── TTS engines to run for each contribution ────────────────────────────────
SYNTHESIS_ENGINES = ["edge_tts", "gtts"]

# ── In-flight & recency lock (5-minute TTL per contribution+engine) ──────────
_SYNTH_LOCK = threading.Lock()
_RECENT_SYNTH_RUNS: dict[str, float] = {}  # "contribution_id:engine_name" -> timestamp
SYNTH_DEDUP_WINDOW_SECONDS = 300


def _is_synth_already_running_or_done(contribution_id: str, engine_name: str) -> bool:
    """Check if synthetic generation for this contribution+engine ran in the last 5 minutes."""
    key = f"{contribution_id}:{engine_name}"
    now = time.time()
    with _SYNTH_LOCK:
        # Prune old entries
        expired = [k for k, ts in _RECENT_SYNTH_RUNS.items() if now - ts > SYNTH_DEDUP_WINDOW_SECONDS]
        for k in expired:
            del _RECENT_SYNTH_RUNS[k]

        if key in _RECENT_SYNTH_RUNS:
            return True
        # Mark as running right now
        _RECENT_SYNTH_RUNS[key] = now
        return False


# ═══════════════════════════════════════════════════════════════════════════
# Idempotency check against Hugging Face dataset
# ═══════════════════════════════════════════════════════════════════════════

def check_existing_synthetic(contribution_id: str, engine_name: str) -> bool:
    """
    Query the HF synthetic split (streaming) to check if rows already
    exist for this contribution_id + engine_name combination.
    Returns True if synthetic data already exists (should skip).
    """
    try:
        from datasets import load_dataset, Audio

        ds = load_dataset(
            HF_DATASET_REPO,
            split="synthetic",
            token=HF_TOKEN,
            streaming=True,
        )
        try:
            ds = ds.cast_column("audio", Audio(decode=False))
        except Exception:
            pass

        for row in ds:
            if (
                row.get("contribution_id") == contribution_id
                and row.get("tts_engine") == engine_name
            ):
                return True

        return False

    except Exception as e:
        # If dataset/split doesn't exist yet, nothing to skip
        logger.debug(f"Could not check existing synthetic data on HF: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════════
# Voice rotation
# ═══════════════════════════════════════════════════════════════════════════

def _build_voice_rotation(
    engine,
    language_keys: list[str],
    prompts_per_language: dict[str, int],
) -> dict[str, list[str]]:
    """
    For each language, build a list of voices to use for each prompt,
    ensuring no two consecutive prompts use the same voice.

    Returns dict: language_key -> [voice_id_for_prompt_0, voice_id_for_prompt_1, ...]
    """
    rotation: dict[str, list[str]] = {}

    for lang_key in language_keys:
        count = prompts_per_language.get(lang_key, 0)
        if count == 0:
            continue

        # Get native voices for this language
        voices = list(engine.list_voices(lang_key))

        # For Edge-TTS: if not enough native voices, pull cross-locale Indian voices
        if engine.name == "edge_tts" and len(voices) < count:
            for v in ALL_INDIAN_EDGE_VOICES:
                if v not in voices:
                    voices.append(v)
                if len(voices) >= max(count, 9):
                    break

        if not voices:
            logger.warning(
                f"No voices available for {engine.name}/{lang_key}. "
                f"Will skip prompts for this language."
            )
            rotation[lang_key] = []
            continue

        # Shuffle to randomize which voices are used
        shuffled = list(voices)
        random.shuffle(shuffled)

        # Assign round-robin, avoiding immediate repeats
        assigned: list[str] = []
        for i in range(count):
            candidate = shuffled[i % len(shuffled)]

            # Avoid immediate repeat (if possible and there are >1 voices)
            if len(shuffled) > 1 and assigned and candidate == assigned[-1]:
                alt_idx = (i + 1) % len(shuffled)
                candidate = shuffled[alt_idx]

            assigned.append(candidate)

        rotation[lang_key] = assigned

    return rotation


# ═══════════════════════════════════════════════════════════════════════════
# Core generation for one engine
# ═══════════════════════════════════════════════════════════════════════════

def generate_synthetic_session(
    clips: list[dict],
    contribution_id: str,
    engine_name: str,
) -> dict:
    """
    Generate synthetic TTS for all non-open prompts using one engine.
    Skips any prompt containing '_open_'.

    Args:
        clips: list of human clip dicts (contribution_id, language, prompt_id,
               prompt_text_romanized, age_range, gender, region, environment, ...)
        contribution_id: unique session ID
        engine_name: "edge_tts" or "gtts"

    Returns:
        Summary dict with keys: generated, skipped_existing, failed, errors
    """
    summary = {
        "engine": engine_name,
        "generated": 0,
        "skipped_existing": 0,
        "failed": 0,
        "errors": [],
    }

    # Filter out prompts that are open-ended instructions without concrete reading text
    clips_to_synthesize = [
        c for c in clips
        if c.get("prompt_text_romanized")
        and not c.get("prompt_text_romanized", "").lower().startswith("in your own words")
        and not c.get("prompt_text_romanized", "").lower().startswith("apne shabdon")
        and not c.get("prompt_text_romanized", "").lower().startswith("tumchya swatahchya")
    ]

    if not clips_to_synthesize:
        logger.info(f"No prompts eligible for synthetic generation for {contribution_id}.")
        return summary

    # 1. In-flight / recency single-trigger check
    if _is_synth_already_running_or_done(contribution_id, engine_name):
        total = len(clips_to_synthesize)
        summary["skipped_existing"] = total
        logger.warning(
            f"duplicate synthetic generation trigger blocked for {contribution_id}/{engine_name}"
        )
        return summary

    # 2. Idempotency check against Hugging Face dataset
    if check_existing_synthetic(contribution_id, engine_name):
        total = len(clips_to_synthesize)
        summary["skipped_existing"] = total
        logger.info(
            f"Contribution {contribution_id}/{engine_name}: "
            f"0 generated, {total} skipped (already exist on HF), 0 failed"
        )
        return summary

    # 3. Get engine instance
    engine = get_engine_by_name(engine_name)
    if not engine:
        msg = f"{engine_name} engine not available (not installed)"
        summary["failed"] = len(clips_to_synthesize)
        summary["errors"].append(msg)
        logger.warning(msg)
        return summary

    # 4. Build voice rotation
    lang_prompt_counts: dict[str, int] = {}
    lang_prompt_order: dict[str, list[int]] = {}

    for i, clip in enumerate(clips_to_synthesize):
        lang = clip["language"]
        lang_prompt_counts[lang] = lang_prompt_counts.get(lang, 0) + 1
        lang_prompt_order.setdefault(lang, []).append(i)

    voice_rotation = _build_voice_rotation(
        engine, list(lang_prompt_counts.keys()), lang_prompt_counts
    )

    # 5. Generate synthetic audio
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    synth_id = f"synth_{contribution_id[:8]}_{engine_name}"
    tmp_dir = Path(tempfile.gettempdir()) / "voice_collector_auto_synth" / synth_id
    tmp_dir.mkdir(parents=True, exist_ok=True)

    synthetic_clips = []

    for lang_key, clip_indices in lang_prompt_order.items():
        voices = voice_rotation.get(lang_key, [])

        for prompt_offset, clip_idx in enumerate(clip_indices):
            clip = clips_to_synthesize[clip_idx]
            prompt_id = clip["prompt_id"]
            prompt_text = clip["prompt_text_romanized"]

            # Get assigned voice for this prompt slot
            if not voices:
                msg = f"No voices for {engine_name}/{lang_key}, skipping {prompt_id}"
                logger.warning(msg)
                summary["failed"] += 1
                summary["errors"].append(msg)
                continue

            voice_id = voices[prompt_offset % len(voices)]
            safe_voice = voice_id.replace("/", "_").replace(":", "_")
            out_path = tmp_dir / f"ai_{prompt_id}_{engine_name}_{safe_voice}.wav"

            try:
                engine.synthesize(
                    text=prompt_text,
                    voice_id=voice_id,
                    output_path=out_path,
                    language=lang_key,
                )

                data, sr = sf.read(str(out_path))
                duration = len(data) / sr

                synthetic_clips.append({
                    "contribution_id": contribution_id,
                    "source": "synthetic",
                    "language": lang_key,
                    "prompt_id": prompt_id,
                    "prompt_text_romanized": prompt_text,
                    "age_range": clip.get("age_range", ""),
                    "gender": clip.get("gender", ""),
                    "region": clip.get("region", ""),
                    "environment": clip.get("environment", ""),
                    "tts_engine": engine_name,
                    "voice_id": voice_id,
                    "audio_path": str(out_path),
                    "duration_seconds": round(duration, 2),
                    "submitted_at": now,
                })
                summary["generated"] += 1
                logger.info(f"  [{engine_name}] {prompt_id} → {voice_id} ({duration:.1f}s)")

            except Exception as e:
                msg = f"{engine_name}/{prompt_id}: {e}"
                logger.error(f"  [{engine_name}] Failed {prompt_id}: {e}")
                summary["failed"] += 1
                summary["errors"].append(msg)
                continue

    # 6. Upload batch to HF Hub
    if synthetic_clips:
        success, message = upload_synthetic_batch(synthetic_clips)
        if success:
            logger.info(f"  [{engine_name}] Uploaded {len(synthetic_clips)} synthetic clips")
        else:
            logger.error(f"  [{engine_name}] Upload failed: {message}")
            summary["errors"].append(f"Upload failed: {message}")

    # 7. Log summary
    logger.info(
        f"Contribution {contribution_id}/{engine_name}: "
        f"{summary['generated']} generated, "
        f"{summary['skipped_existing']} skipped (existing), "
        f"{summary['failed']} failed"
    )

    return summary


# ═══════════════════════════════════════════════════════════════════════════
# Multi-engine orchestrator
# ═══════════════════════════════════════════════════════════════════════════

def run_all_synthetic_engines(
    clips: list[dict],
    contribution_id: str,
) -> list[dict]:
    """
    Generate synthetic sessions for ALL configured engines (edge_tts + gtts).
    Each engine runs independently — one failing does not affect the other.
    Automatically filters out open-ended prompts (_open_).

    Args:
        clips: list of human clip dicts
        contribution_id: session ID

    Returns:
        List of summary dicts (one per engine)
    """
    logger.info(
        f"Starting synthetic generation for contribution {contribution_id} "
        f"({len(clips)} input clips × {len(SYNTHESIS_ENGINES)} engines)"
    )

    summaries = []

    for engine_name in SYNTHESIS_ENGINES:
        try:
            summary = generate_synthetic_session(clips, contribution_id, engine_name)
            summaries.append(summary)
        except Exception as e:
            logger.error(
                f"Unexpected error in {engine_name} synthesis for {contribution_id}: {e}"
            )
            summaries.append({
                "engine": engine_name,
                "generated": 0,
                "skipped_existing": 0,
                "failed": len(clips),
                "errors": [str(e)],
            })

    # Final summary across all engines
    total_gen = sum(s["generated"] for s in summaries)
    total_skip = sum(s["skipped_existing"] for s in summaries)
    total_fail = sum(s["failed"] for s in summaries)
    logger.info(
        f"Synthesis complete for {contribution_id}: "
        f"{total_gen} total generated, {total_skip} total skipped, {total_fail} total failed "
        f"across {len(SYNTHESIS_ENGINES)} engines"
    )

    return summaries
