"""
Hugging Face Hub upload utilities.
Handles batching, schema creation, push_to_hub with retry + local fallback,
duplicate detection guards, and dataset auditing.
"""

import json
import time
import threading
import logging
import datetime
import traceback
from pathlib import Path
from collections import defaultdict

from datasets import Dataset, Audio, DatasetDict, load_dataset, concatenate_datasets
from huggingface_hub import HfApi, login

import sys, os
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import HF_TOKEN, HF_DATASET_REPO, LOCAL_FALLBACK_DIR, SAMPLE_RATE

logger = logging.getLogger(__name__)

# ── Thread-safe memory cache of recent human submissions (5-minute TTL) ──────
_RECENT_SUBMISSION_LOCK = threading.Lock()
_RECENT_SUBMISSIONS: dict[str, float] = {}  # contribution_id -> timestamp (time.time())
SUBMISSION_DEDUP_WINDOW_SECONDS = 300  # 5 minutes


def _is_recent_duplicate(contribution_id: str) -> bool:
    """Check if this contribution_id was submitted within the last 5 minutes."""
    if not contribution_id:
        return False
    now = time.time()
    with _RECENT_SUBMISSION_LOCK:
        # Cleanup entries older than window
        expired = [cid for cid, ts in _RECENT_SUBMISSIONS.items() if now - ts > SUBMISSION_DEDUP_WINDOW_SECONDS]
        for cid in expired:
            del _RECENT_SUBMISSIONS[cid]

        if contribution_id in _RECENT_SUBMISSIONS:
            return True
        return False


def _record_recent_submission(contribution_id: str):
    """Record a contribution_id in the 5-minute cache."""
    if not contribution_id:
        return
    with _RECENT_SUBMISSION_LOCK:
        _RECENT_SUBMISSIONS[contribution_id] = time.time()


def _ensure_login():
    """Login to HF Hub using the token from settings."""
    if not HF_TOKEN:
        raise ValueError(
            "HF_TOKEN is not set. Please set it in your .env file or as an environment variable. "
            "Get a token from https://huggingface.co/settings/tokens"
        )
    login(token=HF_TOKEN, add_to_git_credential=False)


def _build_dataset(clips: list[dict]) -> Dataset:
    """
    Build a HF Dataset from a list of clip dicts.

    Each clip dict must contain:
      - audio_path: str (path to WAV file)
      - contribution_id, source, language, prompt_id, prompt_text_romanized,
        age_range, gender, region, environment, tts_engine, voice_id,
        duration_seconds, submitted_at
    """
    data = {
        "contribution_id": [],
        "source": [],
        "language": [],
        "prompt_id": [],
        "prompt_text_romanized": [],
        "age_range": [],
        "gender": [],
        "region": [],
        "environment": [],
        "tts_engine": [],
        "voice_id": [],
        "audio": [],
        "duration_seconds": [],
        "submitted_at": [],
    }

    for clip in clips:
        data["contribution_id"].append(clip["contribution_id"])
        data["source"].append(clip["source"])
        data["language"].append(clip["language"])
        data["prompt_id"].append(clip["prompt_id"])
        data["prompt_text_romanized"].append(clip["prompt_text_romanized"])
        data["age_range"].append(clip.get("age_range", ""))
        data["gender"].append(clip.get("gender", ""))
        data["region"].append(clip.get("region", ""))
        data["environment"].append(clip.get("environment", ""))
        data["tts_engine"].append(clip.get("tts_engine", ""))
        data["voice_id"].append(clip.get("voice_id", ""))
        data["audio"].append(clip["audio_path"])
        data["duration_seconds"].append(clip["duration_seconds"])
        data["submitted_at"].append(clip["submitted_at"])

    ds = Dataset.from_dict(data)
    ds = ds.cast_column("audio", Audio(sampling_rate=SAMPLE_RATE))
    return ds


def upload_session(clips: list[dict], max_retries: int = 2) -> tuple[bool, str]:
    """
    Upload a contributor's full recording session to HF Hub.
    Guards against duplicate submissions within the last 5 minutes.

    Args:
        clips: list of clip dicts (see _build_dataset for schema)
        max_retries: number of retry attempts on failure

    Returns:
        (success: bool, message: str)
    """
    if not clips:
        return False, "No clips to upload"

    contribution_id = clips[0].get("contribution_id", "")
    source = clips[0].get("source", "human")

    # Guard: if this is a human submission and already submitted in last 5 min, block it
    if source == "human" and contribution_id:
        if _is_recent_duplicate(contribution_id):
            logger.warning(f"duplicate submission blocked for {contribution_id}")
            return True, f"⚠️ Duplicate submission blocked for {contribution_id} (already saved recently)."

    try:
        _ensure_login()
    except ValueError as e:
        # Save locally if HF_TOKEN is not configured
        fallback_msg = _save_local_fallback(clips, str(e))
        return False, f"⚠️ {e}\n{fallback_msg}"

    ds = _build_dataset(clips)
    split_name = "human" if source == "human" else "synthetic"

    for attempt in range(max_retries + 1):
        try:
            # Try to load existing split to append
            try:
                existing_ds = load_dataset(
                    HF_DATASET_REPO,
                    split=split_name,
                    token=HF_TOKEN,
                )
                combined_ds = concatenate_datasets([existing_ds, ds])
            except Exception:
                combined_ds = ds

            combined_ds.push_to_hub(
                HF_DATASET_REPO,
                split=split_name,
                private=True,
                token=HF_TOKEN,
            )

            # Record in recent submission cache on success
            if source == "human" and contribution_id:
                _record_recent_submission(contribution_id)

            url = f"https://huggingface.co/datasets/{HF_DATASET_REPO}"
            return True, f"✅ Uploaded {len(clips)} clips → {url}"
        except Exception as e:
            if attempt < max_retries:
                continue
            # Final failure — save locally
            error_msg = f"Upload failed after {max_retries + 1} attempts: {e}"
            fallback_msg = _save_local_fallback(clips, error_msg)
            return False, f"❌ {error_msg}\n{fallback_msg}"

    return False, "Unexpected error in upload loop"


def upload_synthetic_batch(clips: list[dict], max_retries: int = 2) -> tuple[bool, str]:
    """
    Upload a batch of synthetic clips to HF Hub.
    Same as upload_session but ensures source='synthetic'.
    """
    for clip in clips:
        clip["source"] = "synthetic"
    return upload_session(clips, max_retries)


def _save_local_fallback(clips: list[dict], error_msg: str) -> str:
    """Save clips metadata to local fallback directory when upload fails."""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    fallback_dir = LOCAL_FALLBACK_DIR / timestamp
    fallback_dir.mkdir(parents=True, exist_ok=True)

    meta = {
        "error": error_msg,
        "timestamp": timestamp,
        "clips": [],
    }
    for clip in clips:
        clip_meta = {k: v for k, v in clip.items()}
        meta["clips"].append(clip_meta)

    meta_path = fallback_dir / "metadata.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, default=str)

    return f"💾 Saved {len(clips)} clips locally to {fallback_dir}"


_CONTRIB_COUNT_LOCK = threading.Lock()
_CONTRIB_COUNT_CACHE = {"count": 0, "timestamp": 0.0}


def get_contributor_count() -> int:
    """
    Fetch the total number of unique people who contributed voice sessions.
    Cached for 60 seconds to provide instant responses.
    """
    global _CONTRIB_COUNT_CACHE
    now = time.time()
    with _CONTRIB_COUNT_LOCK:
        if now - _CONTRIB_COUNT_CACHE["timestamp"] < 60 and _CONTRIB_COUNT_CACHE["timestamp"] > 0:
            return _CONTRIB_COUNT_CACHE["count"]

    try:
        _ensure_login()
        ds = load_dataset(
            HF_DATASET_REPO,
            split="human",
            token=HF_TOKEN,
            streaming=True,
        )
        try:
            ds = ds.cast_column("audio", Audio(decode=False))
        except Exception:
            pass

        unique_cids = set()
        for row in ds:
            cid = row.get("contribution_id")
            if cid:
                unique_cids.add(str(cid))

        count = len(unique_cids)
        with _CONTRIB_COUNT_LOCK:
            _CONTRIB_COUNT_CACHE = {"count": count, "timestamp": now}
        return count
    except Exception as e:
        logger.debug(f"Could not load contributor count: {e}")
        with _CONTRIB_COUNT_LOCK:
            return _CONTRIB_COUNT_CACHE["count"]


def get_dataset_stats() -> dict:
    """
    Fetch basic stats about the existing dataset on HF Hub.
    Returns dict with counts per source and language.
    """
    try:
        _ensure_login()
        stats = {"human": 0, "synthetic": 0, "by_language": {}, "total": 0}

        for split_name in ["human", "synthetic"]:
            try:
                ds = load_dataset(
                    HF_DATASET_REPO,
                    split=split_name,
                    token=HF_TOKEN,
                    streaming=True,
                )
                try:
                    ds = ds.cast_column("audio", Audio(decode=False))
                except Exception:
                    pass

                count = 0
                for row in ds:
                    count += 1
                    lang = row.get("language", "unknown")
                    stats["by_language"][lang] = stats["by_language"].get(lang, 0) + 1
                stats[split_name] = count
                stats["total"] += count
            except Exception:
                pass

        return stats
    except Exception as e:
        return {"error": str(e), "human": 0, "synthetic": 0, "by_language": {}, "total": 0}



def audit_dataset() -> dict:
    """
    Full audit of the Hugging Face dataset (both human and synthetic splits):
      - Total row count per split and overall
      - Unique contribution_ids count
      - Identifies any (contribution_id, prompt_id) pairs appearing more than once
      - Identifies duplicate contribution sessions
    """
    report = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "dataset_repo": HF_DATASET_REPO,
        "splits": {},
        "total_rows": 0,
        "total_unique_contributions": 0,
        "has_duplicates": False,
        "error": None,
    }

    try:
        _ensure_login()
    except Exception as e:
        report["error"] = str(e)
        return report

    all_unique_contributions = set()

    for split_name in ["human", "synthetic"]:
        split_report = {
            "total_rows": 0,
            "unique_contributions": 0,
            "duplicate_pairs": [],  # [{"contribution_id": ..., "prompt_id": ..., "count": ...}]
            "duplicate_contributions": [], # contribution_ids that appear across multiple redundant sessions
        }

        try:
            ds = load_dataset(
                HF_DATASET_REPO,
                split=split_name,
                token=HF_TOKEN,
                streaming=True,
            )
            try:
                ds = ds.cast_column("audio", Audio(decode=False))
            except Exception:
                pass

            # Pair counter: (contribution_id, prompt_id) -> count
            pair_counts = defaultdict(int)
            contrib_counts = defaultdict(int)
            contrib_prompt_set = defaultdict(set)

            for row in ds:
                cid = str(row.get("contribution_id", "unknown"))
                pid = str(row.get("prompt_id", "unknown"))
                tts_engine = row.get("tts_engine", "")

                split_report["total_rows"] += 1
                all_unique_contributions.add(cid)
                contrib_counts[cid] += 1

                # In synthetic split, pair includes tts_engine
                if split_name == "synthetic" and tts_engine:
                    pair_key = (cid, pid, tts_engine)
                else:
                    pair_key = (cid, pid)

                pair_counts[pair_key] += 1
                contrib_prompt_set[cid].add(pid)

            split_report["unique_contributions"] = len(contrib_counts)

            # Find duplicate pairs
            for pair_key, count in pair_counts.items():
                if count > 1:
                    if len(pair_key) == 3:
                        cid, pid, eng = pair_key
                        split_report["duplicate_pairs"].append({
                            "contribution_id": cid,
                            "prompt_id": pid,
                            "tts_engine": eng,
                            "count": count,
                        })
                    else:
                        cid, pid = pair_key
                        split_report["duplicate_pairs"].append({
                            "contribution_id": cid,
                            "prompt_id": pid,
                            "count": count,
                        })

            # Check if any contribution has more than expected prompts (duplicate submissions)
            for cid, count in contrib_counts.items():
                if len(split_report["duplicate_pairs"]) > 0:
                    c_dupes = [p for p in split_report["duplicate_pairs"] if p["contribution_id"] == cid]
                    if c_dupes and cid not in split_report["duplicate_contributions"]:
                        split_report["duplicate_contributions"].append(cid)

            if len(split_report["duplicate_pairs"]) > 0:
                report["has_duplicates"] = True

        except Exception as e:
            split_report["error"] = str(e)

        report["splits"][split_name] = split_report
        report["total_rows"] += split_report["total_rows"]

    report["total_unique_contributions"] = len(all_unique_contributions)
    return report
