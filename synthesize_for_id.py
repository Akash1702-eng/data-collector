"""
Generate Synthetic AI Voice Data for Specific Human Contribution ID.

This script fetches human voice prompt data from Dataset 1 ('human' split) on Hugging Face Hub,
generates matching AI synthetic voice audio using configured TTS engines (Edge-TTS + gTTS),
and uploads the generated synthetic clips to Dataset 2 ('synthetic' split).

Usage:
    python synthesize_for_id.py [CONTRIBUTION_ID] [--engine ENGINE] [--force] [--all-missing]

Examples:
    python synthesize_for_id.py
    python synthesize_for_id.py e4a554e7-2eaf-4b7b-bc50-bea2bc8efb5d
    python synthesize_for_id.py e4a554e7-2eaf-4b7b-bc50-bea2bc8efb5d --engine edge_tts
    python synthesize_for_id.py --all-missing
"""

import sys
import os
import time
import argparse
import datetime
import tempfile
import logging
from pathlib import Path
from collections import defaultdict

# ── Fix Windows console UTF-8 encoding ──────────────────────────────────────
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

import pyarrow.parquet as pq
from huggingface_hub import HfApi, login, hf_hub_download
from datasets import Dataset, Audio, concatenate_datasets, load_dataset
import soundfile as sf

from config.settings import (
    HF_TOKEN,
    HF_DATASET_REPO,
    SAMPLE_RATE,
)
from utils.tts_engines import get_engine_by_name
from utils.hf_upload import _ensure_login, upload_synthetic_batch
from utils.synthesis import _build_voice_rotation

DEFAULT_TARGET_ID = "e4a554e7-2eaf-4b7b-bc50-bea2bc8efb5d"
DEFAULT_ENGINES = ["edge_tts"]

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("synthesize_for_id")


def _get_dataset_parquet_files() -> dict[str, list[str]]:
    """Find parquet filenames for 'human' and 'synthetic' splits in repo."""
    _ensure_login()
    api = HfApi(token=HF_TOKEN)
    repo_files = api.list_repo_files(repo_id=HF_DATASET_REPO, repo_type="dataset")

    human_files = []
    synthetic_files = []

    if "data/human-00000-of-00001.parquet" in repo_files:
        human_files.append("data/human-00000-of-00001.parquet")
    if "data/synthetic-00000-of-00001.parquet" in repo_files:
        synthetic_files.append("data/synthetic-00000-of-00001.parquet")

    if not human_files or not synthetic_files:
        for f in repo_files:
            if f.endswith(".parquet"):
                if "human" in f and f not in human_files:
                    human_files.append(f)
                elif "synthetic" in f and f not in synthetic_files:
                    synthetic_files.append(f)

    return {"human": human_files, "synthetic": synthetic_files}


def fetch_human_records_for_id(contribution_id: str) -> list[dict]:
    """
    Fetch prompt metadata for a given contribution_id from the 'human' split.
    Downloads the human parquet file(s) and filters columns for speed.
    """
    print(f"\n🔍 Searching for contribution ID in Dataset 1 (human split)...")
    print(f"   Target ID  : {contribution_id}")
    print(f"   Repository : {HF_DATASET_REPO}")

    _ensure_login()

    try:
        files = _get_dataset_parquet_files()
        human_parquet_files = files.get("human", [])
        if not human_parquet_files:
            raise FileNotFoundError("Could not find human parquet file(s) in repo.")

        all_records = []
        cols = [
            "contribution_id", "source", "language", "prompt_id",
            "prompt_text_romanized", "age_range", "gender", "region",
            "environment", "duration_seconds", "submitted_at"
        ]

        for human_rel_path in human_parquet_files:
            print(f"   Downloading metadata from: {human_rel_path}...")
            local_parquet = hf_hub_download(
                repo_id=HF_DATASET_REPO,
                filename=human_rel_path,
                repo_type="dataset",
                token=HF_TOKEN,
            )

            table = pq.read_table(local_parquet)
            available_cols = [c for c in cols if c in table.column_names]
            df = table.select(available_cols).to_pandas()
            matching_df = df[df["contribution_id"] == contribution_id]
            all_records.extend(matching_df.to_dict(orient="records"))

        return all_records

    except Exception as e:
        logger.error(f"Failed to fetch human records: {e}")
        raise


def find_all_missing_contribution_ids() -> list[str]:
    """
    Find all contribution IDs present in 'human' split but missing in 'synthetic' split.
    """
    print("\n🔎 Scanning for contribution IDs missing synthetic pairs in Dataset 2...")
    _ensure_login()

    files = _get_dataset_parquet_files()
    human_cids = set()
    synth_cids = set()

    for hp_file in files.get("human", []):
        try:
            hp = hf_hub_download(repo_id=HF_DATASET_REPO, filename=hp_file, repo_type="dataset", token=HF_TOKEN)
            htable = pq.read_table(hp, columns=["contribution_id"])
            human_cids.update(str(x) for x in htable.column("contribution_id").to_pylist() if x)
        except Exception as e:
            print(f"⚠️ Could not read human split file {hp_file}: {e}")

    for sp_file in files.get("synthetic", []):
        try:
            sp = hf_hub_download(repo_id=HF_DATASET_REPO, filename=sp_file, repo_type="dataset", token=HF_TOKEN)
            stable = pq.read_table(sp, columns=["contribution_id"])
            synth_cids.update(str(x) for x in stable.column("contribution_id").to_pylist() if x)
        except Exception as e:
            print(f"ℹ️ Synthetic split file might be empty ({sp_file}): {e}")

    missing = sorted(list(human_cids - synth_cids))
    return missing


def check_existing_synthetic_for_id(contribution_id: str) -> dict[str, int]:
    """
    Check how many synthetic records already exist for this ID, grouped by TTS engine.
    """
    existing_by_engine = defaultdict(int)
    _ensure_login()

    try:
        files = _get_dataset_parquet_files()
        synthetic_files = files.get("synthetic", [])
        if not synthetic_files:
            return {}

        for sp_file in synthetic_files:
            try:
                sp = hf_hub_download(
                    repo_id=HF_DATASET_REPO,
                    filename=sp_file,
                    repo_type="dataset",
                    token=HF_TOKEN,
                )
                table = pq.read_table(sp, columns=["contribution_id", "tts_engine"])
                df = table.to_pandas()
                matching = df[df["contribution_id"] == contribution_id]
                for _, row in matching.iterrows():
                    eng = row.get("tts_engine") or "unknown"
                    existing_by_engine[eng] += 1
            except Exception as e:
                logger.debug(f"Synthetic check note for {sp_file}: {e}")

    except Exception as e:
        logger.debug(f"Synthetic check note: {e}")

    return dict(existing_by_engine)


def generate_synthetic_for_clips(
    clips: list[dict],
    contribution_id: str,
    engines: list[str],
) -> tuple[list[dict], dict]:
    """
    Generate synthetic speech audio for the given human clips using specified TTS engines.
    Returns:
        (generated_clip_dicts, summary_dict)
    """
    # Filter out open-ended prompts without concrete reading text
    eligible_clips = [
        c for c in clips
        if c.get("prompt_text_romanized")
        and not str(c.get("prompt_text_romanized", "")).lower().startswith("in your own words")
        and not str(c.get("prompt_text_romanized", "")).lower().startswith("apne shabdon")
        and not str(c.get("prompt_text_romanized", "")).lower().startswith("tumchya swatahchya")
    ]

    if not eligible_clips:
        print("⚠️ No eligible prompts found with romanized text to synthesize.")
        return [], {"generated": 0, "failed": 0}

    print(f"\n🎙️  Starting AI Speech Synthesis:")
    print(f"   • Eligible Prompts: {len(eligible_clips)} per engine")
    print(f"   • TTS Engines: {', '.join(engines)}")
    print(f"   • Total Audio Clips to Generate: {len(eligible_clips) * len(engines)}")

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    session_tmp_dir = Path(tempfile.gettempdir()) / "voice_collector_manual_synth" / f"{contribution_id[:8]}_{int(time.time())}"
    session_tmp_dir.mkdir(parents=True, exist_ok=True)

    all_generated_clips = []
    summary = {"generated": 0, "failed": 0, "by_engine": {}}

    for engine_name in engines:
        print(f"\n─── Running Engine: [{engine_name.upper()}] ───")
        eng_summary = {"generated": 0, "failed": 0}

        engine = get_engine_by_name(engine_name)
        if not engine:
            print(f"   ❌ Engine '{engine_name}' is not installed or available. Skipping.")
            eng_summary["failed"] += len(eligible_clips)
            summary["by_engine"][engine_name] = eng_summary
            continue

        # Group prompts by language for voice rotation
        lang_prompt_counts: dict[str, int] = {}
        lang_prompt_order: dict[str, list[int]] = {}

        for i, clip in enumerate(eligible_clips):
            lang = clip.get("language", "english_indian")
            lang_prompt_counts[lang] = lang_prompt_counts.get(lang, 0) + 1
            lang_prompt_order.setdefault(lang, []).append(i)

        voice_rotation = _build_voice_rotation(
            engine, list(lang_prompt_counts.keys()), lang_prompt_counts
        )

        for lang_key, clip_indices in lang_prompt_order.items():
            voices = voice_rotation.get(lang_key, [])
            if not voices:
                print(f"   ⚠️ No voices available for language '{lang_key}' with {engine_name}. Skipping {len(clip_indices)} prompts.")
                eng_summary["failed"] += len(clip_indices)
                continue

            for offset, clip_idx in enumerate(clip_indices):
                clip = eligible_clips[clip_idx]
                prompt_id = clip.get("prompt_id", f"p_{clip_idx}")
                prompt_text = clip.get("prompt_text_romanized", "")

                voice_id = voices[offset % len(voices)]
                safe_voice = voice_id.replace("/", "_").replace(":", "_")
                out_path = session_tmp_dir / f"ai_{prompt_id}_{engine_name}_{safe_voice}.wav"

                print(f"   ▶ [{engine_name}] Prompt: {prompt_id: <8} | Lang: {lang_key: <14} | Voice: {voice_id}")
                try:
                    engine.synthesize(
                        text=prompt_text,
                        voice_id=voice_id,
                        output_path=out_path,
                        language=lang_key,
                    )

                    data, sr = sf.read(str(out_path))
                    duration = round(len(data) / sr, 2)

                    all_generated_clips.append({
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
                        "duration_seconds": duration,
                        "submitted_at": now_iso,
                    })

                    eng_summary["generated"] += 1
                    summary["generated"] += 1
                    print(f"     ✅ Generated successfully ({duration:.2f}s)")

                except Exception as e:
                    print(f"     ❌ Synthesis failed: {e}")
                    eng_summary["failed"] += 1
                    summary["failed"] += 1

        summary["by_engine"][engine_name] = eng_summary

    return all_generated_clips, summary


def process_single_contribution(
    contribution_id: str,
    engines: list[str],
    force: bool = False,
) -> bool:
    """
    Orchestrates the entire process for one contribution ID:
      1. Fetches human rows
      2. Checks existing synthetic rows
      3. Generates synthetic speech audio
      4. Uploads to Hugging Face Hub (dataset 2 / 'synthetic' split)
      5. Verifies upload
    """
    print("=" * 75)
    print(f"🚀 VOICE AUTHENTICITY DATASET - SYNTHETIC DATA GENERATOR")
    print("=" * 75)
    print(f"Target Contribution ID : {contribution_id}")
    print(f"Hugging Face Dataset   : {HF_DATASET_REPO}")
    print(f"Configured TTS Engines : {', '.join(engines)}")
    print("=" * 75)

    # 1. Fetch human records from dataset 1
    human_clips = fetch_human_records_for_id(contribution_id)
    if not human_clips:
        print(f"\n❌ Error: No human recording data found in Dataset 1 ('human' split) for ID:")
        print(f"   {contribution_id}")
        print("   Please check the contribution ID and ensure it was uploaded to Dataset 1.")
        return False

    print(f"   ✅ Found {len(human_clips)} human prompt recordings for ID: {contribution_id}")
    langs = sorted(list(set(c['language'] for c in human_clips)))
    print(f"   • Languages represented: {', '.join(langs)}")
    print(f"   • Contributor Gender   : {human_clips[0].get('gender') or 'N/A'}")
    print(f"   • Age Range            : {human_clips[0].get('age_range') or 'N/A'}")
    print(f"   • Recording Environment: {human_clips[0].get('environment') or 'N/A'}")

    # 2. Check existing synthetic data in dataset 2
    existing_counts = check_existing_synthetic_for_id(contribution_id)
    if existing_counts and not force:
        print(f"\n⚠️ Notice: Synthetic data already exists in Dataset 2 for this ID:")
        for eng, count in existing_counts.items():
            print(f"   • {eng}: {count} clips")
        print(f"   Total existing: {sum(existing_counts.values())} clips")
        print("   Use --force flag if you wish to re-generate and append anyway.")
        return True

    # 3. Generate synthetic audio clips
    synthetic_clips, summary = generate_synthetic_for_clips(human_clips, contribution_id, engines)

    if not synthetic_clips:
        print(f"\n❌ No synthetic clips were generated. Check error logs above.")
        return False

    print(f"\n📊 Generation Summary:")
    print(f"   • Successfully Generated: {summary['generated']} clips")
    print(f"   • Failed: {summary['failed']} clips")

    # 4. Upload to Hugging Face Hub (Dataset 2 / 'synthetic' split)
    print(f"\n☁️  Uploading {len(synthetic_clips)} synthetic clips to Dataset 2 ('synthetic' split)...")
    print(f"   Target: https://huggingface.co/datasets/{HF_DATASET_REPO}")

    success, message = upload_synthetic_batch(synthetic_clips)

    print("-" * 75)
    if success:
        print(f"🎉 SUCCESS! {message}")
        print(f"✅ Data for ID '{contribution_id}' has been successfully added to Dataset 2 (synthetic split)!")
    else:
        print(f"❌ Upload Failed: {message}")
        print("   Audio files are saved locally. Please check network connection and HF_TOKEN permissions.")
    print("=" * 75)

    return success


def main():
    parser = argparse.ArgumentParser(
        description="Generate and upload AI synthetic speech data for human recording sessions into Dataset 2."
    )
    parser.add_argument(
        "contribution_id",
        nargs="?",
        default=DEFAULT_TARGET_ID,
        help=f"Contribution UUID from Dataset 1 (default: {DEFAULT_TARGET_ID})",
    )
    parser.add_argument(
        "--engine",
        choices=["edge_tts", "gtts", "all"],
        default="all",
        help="TTS engine to use (default: all -> edge_tts and gtts)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force generation even if synthetic rows already exist for this ID",
    )
    parser.add_argument(
        "--all-missing",
        action="store_true",
        help="Scan and generate synthetic data for ALL human contributions that are missing in Dataset 2",
    )
    parser.add_argument(
        "--list-missing",
        action="store_true",
        help="List all human contribution IDs that are currently missing in Dataset 2 and exit",
    )

    args = parser.parse_args()

    engines = DEFAULT_ENGINES if args.engine == "all" else [args.engine]

    if args.list_missing:
        missing = find_all_missing_contribution_ids()
        print(f"\nFound {len(missing)} contribution IDs in Dataset 1 missing from Dataset 2:")
        for idx, cid in enumerate(missing, 1):
            print(f"  {idx}. {cid}")
        return

    if args.all_missing:
        missing = find_all_missing_contribution_ids()
        if not missing:
            print("✅ All human contributions already have matching synthetic datasets in Dataset 2!")
            return
        print(f"\nProcessing {len(missing)} missing contribution IDs...")
        for idx, cid in enumerate(missing, 1):
            print(f"\n>>> Processing [{idx}/{len(missing)}]: {cid} <<<")
            process_single_contribution(cid, engines, force=args.force)
        return

    # Process specific ID
    target_id = args.contribution_id.strip()
    process_single_contribution(target_id, engines, force=args.force)


if __name__ == "__main__":
    main()
