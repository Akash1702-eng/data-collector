"""
Hugging Face Hub upload utilities.
Handles batching, schema creation, push_to_hub with retry + local fallback,
duplicate detection guards, and dataset auditing.

Memory-optimized: avoids loading full dataset into memory for concatenation.
Uses shard-based uploads and column-selective pyarrow reads for stats.
"""

import gc
import json
import time
import tempfile
import threading
import logging
import datetime
import traceback
from pathlib import Path
from collections import defaultdict

import pyarrow as pa
import pyarrow.parquet as pq
from datasets import Dataset, Audio
from huggingface_hub import HfApi, hf_hub_download, login

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

        # Read the raw WAV binary bytes and embed them directly so bytes is never None
        audio_path_str = clip.get("audio_path", "")
        if audio_path_str and Path(audio_path_str).exists():
            wav_bytes = Path(audio_path_str).read_bytes()
            data["audio"].append({"bytes": wav_bytes, "path": Path(audio_path_str).name})
        elif "audio_bytes" in clip and clip["audio_bytes"]:
            data["audio"].append({"bytes": clip["audio_bytes"], "path": f"{clip.get('prompt_id', 'audio')}.wav"})
        elif isinstance(clip.get("audio"), dict) and clip["audio"].get("bytes"):
            data["audio"].append(clip["audio"])
        else:
            data["audio"].append({"bytes": b"", "path": ""})

        data["duration_seconds"].append(clip["duration_seconds"])
        data["submitted_at"].append(clip["submitted_at"])

    ds = Dataset.from_dict(data)
    ds = ds.cast_column("audio", Audio(sampling_rate=SAMPLE_RATE))
    return ds


def _deduplicate_table(table: pa.Table, key_columns: list[str]) -> pa.Table:
    """
    Deduplicate a PyArrow table based on specified key columns while preserving
    PyArrow column types and Hugging Face schema metadata (e.g. Audio features).
    """
    if len(table) == 0:
        return table

    cols_data = [table.column(col).to_pylist() for col in key_columns if col in table.column_names]
    if len(cols_data) != len(key_columns):
        return table

    seen = set()
    keep_indices = []
    for i in range(len(table)):
        key = tuple(cols_data[c_idx][i] for c_idx in range(len(key_columns)))
        if key not in seen:
            seen.add(key)
            keep_indices.append(i)

    if len(keep_indices) == len(table):
        return table

    return table.take(pa.array(keep_indices, type=pa.int64()))


def upload_session(clips: list[dict], max_retries: int = 2) -> tuple[bool, str]:
    """
    Upload a contributor's full recording session to HF Hub.
    Guards against duplicate submissions within the last 5 minutes.

    Appends directly to the canonical dataset split file:
      data/{split_name}-00000-of-00001.parquet
    using memory-efficient PyArrow concatenation (zero audio decoding).

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
    canonical_filename = f"data/{split_name}-00000-of-00001.parquet"

    for attempt in range(max_retries + 1):
        try:
            api = HfApi(token=HF_TOKEN)

            with tempfile.TemporaryDirectory() as tmp_dir:
                # 1. Convert new clips dataset to PyArrow table
                new_local_parquet = Path(tmp_dir) / "new_shard.parquet"
                ds.to_parquet(str(new_local_parquet))
                new_table = pq.read_table(str(new_local_parquet))

                # 2. Download and load existing canonical parquet table if present
                try:
                    local_existing = hf_hub_download(
                        repo_id=HF_DATASET_REPO,
                        filename=canonical_filename,
                        repo_type="dataset",
                        token=HF_TOKEN,
                    )
                    existing_table = pq.read_table(local_existing)
                    hf_metadata = existing_table.schema.metadata or new_table.schema.metadata
                    combined_table = pa.concat_tables([existing_table, new_table])
                    if hf_metadata:
                        combined_table = combined_table.replace_schema_metadata(hf_metadata)
                    del existing_table
                except Exception as load_err:
                    logger.info(f"Could not load existing dataset '{canonical_filename}' ({load_err}). Creating new split.")
                    combined_table = new_table

                # 3. Deduplicate
                key_columns = ["contribution_id", "prompt_id"]
                if split_name == "synthetic":
                    key_columns.append("tts_engine")
                combined_table = _deduplicate_table(combined_table, key_columns)

                # 4. Save combined table and upload directly to canonical split file
                out_parquet = Path(tmp_dir) / f"{split_name}-00000-of-00001.parquet"
                pq.write_table(combined_table, str(out_parquet))

                api.upload_file(
                    path_or_fileobj=str(out_parquet),
                    path_in_repo=canonical_filename,
                    repo_id=HF_DATASET_REPO,
                    repo_type="dataset",
                    token=HF_TOKEN,
                    commit_message=f"Append {len(clips)} clips to {split_name} dataset ({len(combined_table)} total rows)",
                )

                del combined_table
                del new_table

            # Record in recent submission cache on success
            if source == "human" and contribution_id:
                _record_recent_submission(contribution_id)

            # Free memory
            del ds
            gc.collect()

            url = f"https://huggingface.co/datasets/{HF_DATASET_REPO}"
            return True, f"✅ Uploaded {len(clips)} clips → {url}"
        except Exception as e:
            if attempt < max_retries:
                logger.warning(f"Upload attempt {attempt + 1} failed: {e}. Retrying...")
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


def _find_split_parquet_files(split_name: str) -> list[str]:
    """
    Find parquet file(s) for a given split in the HF repo.
    Prioritizes the canonical data/{split_name}-00000-of-00001.parquet file.
    """
    canonical = f"data/{split_name}-00000-of-00001.parquet"
    try:
        api = HfApi(token=HF_TOKEN)
        repo_files = api.list_repo_files(repo_id=HF_DATASET_REPO, repo_type="dataset")
        if canonical in repo_files:
            return [canonical]
        matches = [
            f for f in repo_files
            if f.endswith(".parquet") and split_name in f
        ]
        return matches if matches else [canonical]
    except Exception as e:
        logger.debug(f"Could not list repo files for split '{split_name}': {e}")
        return [canonical]
        logger.debug(f"Could not list repo files for split '{split_name}': {e}")
        return []


def _read_column_from_split(split_name: str, column: str) -> list:
    """
    Memory-efficient: download parquet files for a split and read only
    a single column using pyarrow (no audio decoding, minimal RAM).
    """
    values = []
    parquet_files = _find_split_parquet_files(split_name)

    for pf in parquet_files:
        try:
            local_p = hf_hub_download(
                repo_id=HF_DATASET_REPO,
                filename=pf,
                repo_type="dataset",
                token=HF_TOKEN,
            )
            table = pq.read_table(local_p, columns=[column])
            values.extend(table.column(column).to_pylist())
            del table
        except Exception as e:
            logger.debug(f"Could not read column '{column}' from {pf}: {e}")

    gc.collect()
    return values


def get_contributor_count() -> int:
    """
    Fetch the total number of unique people who contributed voice sessions.
    Memory-optimized: reads only the contribution_id column via pyarrow.
    Cached for 60 seconds to provide instant responses.
    """
    global _CONTRIB_COUNT_CACHE
    now = time.time()
    with _CONTRIB_COUNT_LOCK:
        if now - _CONTRIB_COUNT_CACHE["timestamp"] < 60 and _CONTRIB_COUNT_CACHE["timestamp"] > 0:
            return _CONTRIB_COUNT_CACHE["count"]

    try:
        _ensure_login()
        cid_values = _read_column_from_split("human", "contribution_id")
        unique_cids = set(str(x) for x in cid_values if x)
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
    Memory-optimized: reads only 'language' column via pyarrow.
    Returns dict with counts per source and language.
    """
    try:
        _ensure_login()
        stats = {"human": 0, "synthetic": 0, "by_language": {}, "total": 0}

        for split_name in ["human", "synthetic"]:
            try:
                lang_values = _read_column_from_split(split_name, "language")
                stats[split_name] = len(lang_values)
                stats["total"] += len(lang_values)
                for lang in lang_values:
                    lang_str = str(lang) if lang else "unknown"
                    stats["by_language"][lang_str] = stats["by_language"].get(lang_str, 0) + 1
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

    Memory-optimized: reads only needed columns via pyarrow.
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
            "duplicate_pairs": [],
            "duplicate_contributions": [],
        }

        try:
            # Read only needed columns via pyarrow (no audio decoding)
            audit_columns = ["contribution_id", "prompt_id"]
            if split_name == "synthetic":
                audit_columns.append("tts_engine")

            parquet_files = _find_split_parquet_files(split_name)
            rows = []
            for pf in parquet_files:
                try:
                    local_p = hf_hub_download(
                        repo_id=HF_DATASET_REPO,
                        filename=pf,
                        repo_type="dataset",
                        token=HF_TOKEN,
                    )
                    # Only read the columns we need
                    available_cols = pq.read_schema(local_p).names
                    cols_to_read = [c for c in audit_columns if c in available_cols]
                    table = pq.read_table(local_p, columns=cols_to_read)
                    df = table.to_pandas()
                    rows.append(df)
                    del table
                except Exception as e:
                    logger.debug(f"Could not read {pf} for audit: {e}")

            if not rows:
                report["splits"][split_name] = split_report
                continue

            import pandas as pd
            combined = pd.concat(rows, ignore_index=True)
            del rows

            split_report["total_rows"] = len(combined)

            # Pair counter
            pair_counts = defaultdict(int)
            contrib_counts = defaultdict(int)

            for _, row in combined.iterrows():
                cid = str(row.get("contribution_id", "unknown"))
                pid = str(row.get("prompt_id", "unknown"))
                tts_engine = row.get("tts_engine", "") if "tts_engine" in combined.columns else ""

                all_unique_contributions.add(cid)
                contrib_counts[cid] += 1

                if split_name == "synthetic" and tts_engine:
                    pair_key = (cid, pid, tts_engine)
                else:
                    pair_key = (cid, pid)
                pair_counts[pair_key] += 1

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

            # Identify contributions with duplicates
            for cid, count in contrib_counts.items():
                c_dupes = [p for p in split_report["duplicate_pairs"] if p["contribution_id"] == cid]
                if c_dupes and cid not in split_report["duplicate_contributions"]:
                    split_report["duplicate_contributions"].append(cid)

            if split_report["duplicate_pairs"]:
                report["has_duplicates"] = True

            del combined
            gc.collect()

        except Exception as e:
            split_report["error"] = str(e)

        report["splits"][split_name] = split_report
        report["total_rows"] += split_report["total_rows"]

    report["total_unique_contributions"] = len(all_unique_contributions)
    return report
