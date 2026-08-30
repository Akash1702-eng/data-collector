"""
Consolidate Hugging Face Dataset Shards into Unified Split Parquet Files.

Merges:
  - data/human-00000-of-00001.parquet + data/human/shard_*.parquet -> data/human-00000-of-00001.parquet
  - data/synthetic-00000-of-00001.parquet + data/synthetic/shard_*.parquet -> data/synthetic-00000-of-00001.parquet

Deletes:
  - All shard files in data/human/ and data/synthetic/ from HF Hub.
"""

import sys
import tempfile
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Ensure UTF-8 output on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import pyarrow as pa
import pyarrow.parquet as pq
import pandas as pd
from huggingface_hub import HfApi, hf_hub_download

from config.settings import HF_TOKEN, HF_DATASET_REPO
from utils.hf_upload import _ensure_login


def deduplicate_table(table: pa.Table, key_columns: list[str]) -> pa.Table:
    """
    Deduplicate a PyArrow table based on specified key columns while preserving
    PyArrow column types and Hugging Face schema metadata (e.g. Audio features).
    """
    if len(table) == 0:
        return table

    # Extract keys as python list of tuples
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

    print(f"   🧹 Deduplicated {len(table)} rows -> {len(keep_indices)} rows (removed {len(table) - len(keep_indices)} duplicate rows).")
    return table.take(pa.array(keep_indices, type=pa.int64()))


def consolidate_split(api: HfApi, split_name: str, key_columns: list[str]) -> tuple[bool, list[str]]:
    """
    Consolidates all parquet files for a split into data/{split_name}-00000-of-00001.parquet.
    Returns (success, list_of_shard_files_to_delete).
    """
    print(f"\n📂 Consolidating split: [{split_name.upper()}]...")
    repo_files = api.list_repo_files(repo_id=HF_DATASET_REPO, repo_type="dataset")

    # Find canonical file and any shard files
    canonical_file = f"data/{split_name}-00000-of-00001.parquet"
    shard_files = [
        f for f in repo_files
        if f.endswith(".parquet")
        and f.startswith(f"data/{split_name}/")
    ]

    all_files_to_merge = []
    if canonical_file in repo_files:
        all_files_to_merge.append(canonical_file)
    all_files_to_merge.extend(shard_files)

    if not all_files_to_merge:
        print(f"   ℹ️ No files found for split '{split_name}'.")
        return True, []

    print(f"   Found {len(all_files_to_merge)} file(s) to merge:")
    for f in all_files_to_merge:
        print(f"     • {f}")

    tables = []
    hf_metadata = None

    for pf in all_files_to_merge:
        try:
            local_path = hf_hub_download(
                repo_id=HF_DATASET_REPO,
                filename=pf,
                repo_type="dataset",
                token=HF_TOKEN,
            )
            t = pq.read_table(local_path)
            if t.schema.metadata and b"huggingface" in t.schema.metadata and not hf_metadata:
                hf_metadata = t.schema.metadata
            tables.append(t)
            print(f"     ✓ Loaded {pf} ({len(t)} rows)")
        except Exception as e:
            print(f"     ❌ Failed to load {pf}: {e}")

    if not tables:
        return False, []

    # Concatenate tables
    try:
        combined_table = pa.concat_tables(tables)
        print(f"   Total combined rows before dedup: {len(combined_table)}")
    except Exception as e:
        print(f"   ❌ Failed to concatenate tables: {e}")
        return False, []

    # Preserve schema metadata
    if hf_metadata:
        combined_table = combined_table.replace_schema_metadata(hf_metadata)

    # Deduplicate
    deduped_table = deduplicate_table(combined_table, key_columns)

    # Write to temp file and upload as canonical split parquet
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_parquet = Path(tmp_dir) / f"{split_name}-00000-of-00001.parquet"
        pq.write_table(deduped_table, str(out_parquet))

        print(f"   ☁️ Uploading consolidated dataset -> {canonical_file} ({len(deduped_table)} rows)...")
        api.upload_file(
            path_or_fileobj=str(out_parquet),
            path_in_repo=canonical_file,
            repo_id=HF_DATASET_REPO,
            repo_type="dataset",
            token=HF_TOKEN,
            commit_message=f"Consolidate {split_name} split into single dataset ({len(deduped_table)} rows)",
        )
        print(f"   ✅ Successfully uploaded {canonical_file}!")

    return True, shard_files


def delete_shards(api: HfApi, shard_files: list[str]):
    """Delete redundant shard files from HF Hub."""
    if not shard_files:
        return

    print(f"\n🗑️ Deleting {len(shard_files)} redundant shard file(s) from HF Hub...")
    for sf in shard_files:
        try:
            api.delete_file(
                path_in_repo=sf,
                repo_id=HF_DATASET_REPO,
                repo_type="dataset",
                token=HF_TOKEN,
                commit_message=f"Remove merged shard {sf}",
            )
            print(f"   ✓ Deleted {sf}")
        except Exception as e:
            print(f"   ⚠️ Could not delete {sf}: {e}")


def main():
    print("=" * 75)
    print("🚀 HUGGING FACE DATASET CONSOLIDATION & CLEANUP")
    print(f"Repository: https://huggingface.co/datasets/{HF_DATASET_REPO}")
    print("=" * 75)

    _ensure_login()
    api = HfApi(token=HF_TOKEN)

    # 1. Consolidate human split
    h_ok, h_shards = consolidate_split(
        api,
        split_name="human",
        key_columns=["contribution_id", "prompt_id"],
    )

    # 2. Consolidate synthetic split
    s_ok, s_shards = consolidate_split(
        api,
        split_name="synthetic",
        key_columns=["contribution_id", "prompt_id", "tts_engine"],
    )

    # 3. Clean up shard files
    all_shards = h_shards + s_shards
    if all_shards and h_ok and s_ok:
        delete_shards(api, all_shards)

    # 4. Final verification of repo files
    print("\n🔍 Final Repository Structure on Hugging Face:")
    final_files = api.list_repo_files(repo_id=HF_DATASET_REPO, repo_type="dataset")
    for f in final_files:
        if f.startswith("data/"):
            print(f"   📄 {f}")

    print("\n" + "=" * 75)
    print("🎉 CONSOLIDATION COMPLETE! All data is stored in the root split datasets.")
    print("=" * 75)


if __name__ == "__main__":
    main()
