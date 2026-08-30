"""
Filter and delete rows matching (gender='Male' and environment='Noisy environment')
from both human and synthetic dataset splits on Hugging Face Hub.
"""

import sys
import tempfile
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Ensure UTF-8 console output
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import pyarrow as pa
import pyarrow.parquet as pq
from huggingface_hub import HfApi, hf_hub_download
from config.settings import HF_TOKEN, HF_DATASET_REPO
from utils.hf_upload import _ensure_login


def filter_and_update_split(api: HfApi, split: str):
    print(f"\nProcessing split: [{split.upper()}]...")
    filename = f"data/{split}-00000-of-00001.parquet"
    path = hf_hub_download(
        repo_id=HF_DATASET_REPO,
        filename=filename,
        repo_type="dataset",
        token=HF_TOKEN,
    )
    table = pq.read_table(path)
    metadata = table.schema.metadata

    gender_col = table.column("gender").to_pylist()
    env_col = table.column("environment").to_pylist()
    cid_col = table.column("contribution_id").to_pylist()

    keep_indices = []
    dropped_cids = set()
    for i in range(len(table)):
        g = str(gender_col[i]).strip().lower()
        e = str(env_col[i]).strip().lower()
        if g == "male" and "noisy" in e:
            dropped_cids.add(str(cid_col[i]))
            continue
        keep_indices.append(i)

    if len(keep_indices) == len(table):
        print(f"  No matching rows to delete in {split} split. (Current rows: {len(table)})")
        return

    filtered_table = table.take(pa.array(keep_indices, type=pa.int64()))
    if metadata:
        filtered_table = filtered_table.replace_schema_metadata(metadata)

    print(f"  Original rows: {len(table)} -> Remaining rows: {len(filtered_table)} (dropped {len(table) - len(filtered_table)} rows)")
    print(f"  Dropped contribution IDs ({len(dropped_cids)}): {list(dropped_cids)}")

    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path = Path(tmp_dir) / f"{split}-00000-of-00001.parquet"
        pq.write_table(filtered_table, str(out_path))

        print(f"  Uploading updated {split} dataset split ({len(filtered_table)} rows)...")
        api.upload_file(
            path_or_fileobj=str(out_path),
            path_in_repo=filename,
            repo_id=HF_DATASET_REPO,
            repo_type="dataset",
            token=HF_TOKEN,
            commit_message=f"Delete rows where gender=male and environment=noisy ({len(filtered_table)} rows remaining)",
        )
    print(f"  Successfully updated {split} split on Hugging Face!")


def main():
    print("=" * 70)
    print("DELETE ROWS WHERE GENDER = MALE AND ENVIRONMENT = NOISY")
    print(f"Repository: https://huggingface.co/datasets/{HF_DATASET_REPO}")
    print("=" * 70)

    _ensure_login()
    api = HfApi(token=HF_TOKEN)

    filter_and_update_split(api, "human")
    filter_and_update_split(api, "synthetic")

    print("\n" + "=" * 70)
    print("COMPLETED FILTERING AND UPDATING DATASETS.")
    print("=" * 70)


if __name__ == "__main__":
    main()
