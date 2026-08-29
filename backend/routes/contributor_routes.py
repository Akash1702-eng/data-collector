"""
Contributor routes - handles submission of human voice recording sessions.
Automatically generates AI synthetic voice pairs using multiple TTS engines
after upload (Edge-TTS + gTTS), via background task.
Guarded against duplicate submissions within 5 minutes.
"""

import time
import json
import uuid
import datetime
import tempfile
import logging
import threading
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request, status, BackgroundTasks

import sys
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import (
    PROMPTS_FILE,
    MIN_RECORDING_SECONDS,
    MAX_RECORDING_SECONDS,
)
from utils.audio import process_recording, save_wav
from utils.hf_upload import upload_session
from utils.synthesis import run_all_synthetic_engines

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/contributions", tags=["contributions"])

# ── Server-side duplicate submission memory guard (5-minute TTL) ─────────────
_SUBMISSION_GUARD_LOCK = threading.Lock()
_RECENT_CONTRIBUTION_IDS: dict[str, float] = {}
DEDUP_WINDOW_SECONDS = 300


def _check_and_register_submission(contribution_id: str) -> bool:
    """
    Returns True if this is a duplicate submission (already submitted in last 5 minutes).
    Returns False and registers the ID if this is a fresh submission.
    """
    now = time.time()
    with _SUBMISSION_GUARD_LOCK:
        # Purge entries older than 5 minutes
        expired = [cid for cid, ts in _RECENT_CONTRIBUTION_IDS.items() if now - ts > DEDUP_WINDOW_SECONDS]
        for cid in expired:
            del _RECENT_CONTRIBUTION_IDS[cid]

        if contribution_id in _RECENT_CONTRIBUTION_IDS:
            return True

        _RECENT_CONTRIBUTION_IDS[contribution_id] = now
        return False


def _load_prompts_map():
    with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    prompts_map = {}
    for lang, items in data.items():
        for item in items:
            prompts_map[item["id"]] = {**item, "language": lang}
    return prompts_map


def _background_synthesize(clips: list[dict], contribution_id: str):
    """Background task wrapper for synthetic generation."""
    try:
        summaries = run_all_synthetic_engines(clips, contribution_id)
        total_gen = sum(s["generated"] for s in summaries)
        total_fail = sum(s["failed"] for s in summaries)
        logger.info(
            f"Background synthesis done for {contribution_id}: "
            f"{total_gen} generated, {total_fail} failed"
        )
    except Exception as e:
        logger.error(f"Background synthesis task failed for {contribution_id}: {e}")


@router.post("/submit")
async def submit_session_route(request: Request, background_tasks: BackgroundTasks):
    """
    Accepts multipart/form-data containing contributor profile metadata
    and recorded audio clips for all prompts.
    After successful upload, automatically generates AI voice pairs in background
    using multiple TTS engines (Edge-TTS + gTTS).
    Guarded against duplicate submissions within 5 minutes.
    """
    form = await request.form()

    # Parse metadata
    meta_raw = form.get("metadata")
    if not meta_raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing 'metadata' in request form.",
        )

    try:
        metadata = json.loads(meta_raw) if isinstance(meta_raw, str) else meta_raw
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid metadata JSON: {e}",
        )

    contribution_id = metadata.get("contribution_id") or str(uuid.uuid4())

    # ── Server-side duplicate check ─────────────────────────────────────────
    if _check_and_register_submission(contribution_id):
        logger.warning(f"duplicate submission blocked for {contribution_id}")
        return {
            "success": True,
            "message": f"Duplicate submission blocked for {contribution_id} (already saved).",
            "contribution_id": contribution_id,
            "clips_submitted": 0,
            "duplicate": True,
        }

    age_range = metadata.get("age_range", "")
    gender = metadata.get("gender", "")
    environment = metadata.get("environment", "")

    # Validate required fields
    missing = []
    if not age_range:
        missing.append("age_range")
    if not gender:
        missing.append("gender")
    if not environment:
        missing.append("environment")

    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing required fields: {', '.join(missing)}",
        )

    prompts_map = _load_prompts_map()
    custom_prompts = metadata.get("custom_prompts", {})
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    tmp_dir = Path(tempfile.gettempdir()) / "voice_collector" / contribution_id
    tmp_dir.mkdir(parents=True, exist_ok=True)

    clips = []
    processed_prompt_ids = set()

    # Extract audio files from form
    for key, value in form.items():
        if key == "metadata":
            continue

        prompt_id = None
        if key.startswith("file_"):
            prompt_id = key[5:]
        elif key.startswith("audio_"):
            prompt_id = key[6:]
        elif key in prompts_map:
            prompt_id = key
        elif hasattr(value, "filename") and value.filename:
            # Check filename (e.g. en_01.wav, en_01.webm)
            fname_stem = Path(value.filename).stem
            if fname_stem in prompts_map:
                prompt_id = fname_stem

        if not prompt_id or prompt_id not in prompts_map:
            continue

        if prompt_id in processed_prompt_ids:
            continue

        prompt_info = prompts_map[prompt_id]
        custom_info = custom_prompts.get(prompt_id, {})
        romanized_text = custom_info.get("romanized_text") or prompt_info["romanized_text"]

        # Read audio bytes
        if hasattr(value, "read"):
            audio_bytes = await value.read()
        elif isinstance(value, bytes):
            audio_bytes = value
        else:
            continue

        if not audio_bytes:
            continue

        try:
            audio_array, duration = process_recording(audio_bytes)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Could not process audio for prompt {prompt_id}: {e}",
            )

        if duration < (MIN_RECORDING_SECONDS - 0.2):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Audio for prompt {prompt_id} is too short ({duration:.1f}s). Minimum {MIN_RECORDING_SECONDS}s.",
            )

        wav_path = tmp_dir / f"{prompt_id}.wav"
        save_wav(audio_array, wav_path)
        processed_prompt_ids.add(prompt_id)

        clips.append({
            "contribution_id": contribution_id,
            "source": "human",
            "language": prompt_info["language"],
            "prompt_id": prompt_id,
            "prompt_text_romanized": romanized_text,
            "age_range": age_range,
            "gender": gender,
            "region": "",
            "environment": environment,
            "tts_engine": "",
            "voice_id": "",
            "audio_path": str(wav_path),
            "duration_seconds": round(duration, 2),
            "submitted_at": now,
        })

    if len(clips) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid audio recordings were submitted.",
        )

    # Upload human recordings to HF Hub or fallback
    success, message = upload_session(clips)

    # Schedule synthetic generation as a background task (non-blocking)
    background_tasks.add_task(_background_synthesize, clips, contribution_id)

    return {
        "success": success,
        "message": message + " · AI voice pairs (Edge-TTS + gTTS) are being generated automatically.",
        "contribution_id": contribution_id,
        "clips_submitted": len(clips),
    }
