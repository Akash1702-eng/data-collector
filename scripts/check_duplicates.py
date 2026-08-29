"""
Standalone Dataset Integrity & Duplicates Verification Tool.
Queries the full Hugging Face dataset (human and synthetic splits) and reports:
  - Total row counts
  - Unique contribution IDs
  - Duplicate (contribution_id, prompt_id) pairs
  - Duplicate contribution sessions
"""

import sys
import json
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Ensure UTF-8 output on Windows consoles
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from utils.hf_upload import audit_dataset
from config.settings import HF_DATASET_REPO


def main():
    print("=" * 70)
    print(f"📊 VOICE AUTHENTICITY DATASET INTEGRITY AUDIT")
    print(f"Dataset Repository: {HF_DATASET_REPO}")
    print("=" * 70)
    print("Fetching and auditing full dataset from Hugging Face Hub...\n")

    report = audit_dataset()

    if report.get("error"):
        print(f"❌ Error during audit: {report['error']}")
        sys.exit(1)

    print(f"Timestamp: {report.get('timestamp')}")
    print(f"Total Rows across all splits: {report.get('total_rows')}")
    print(f"Total Unique Contributors: {report.get('total_unique_contributions')}")
    print("-" * 70)

    for split_name, s_data in report.get("splits", {}).items():
        print(f"\n📂 Split: [{split_name.upper()}]")
        if "error" in s_data and s_data["error"]:
            print(f"   ⚠️ Could not load split: {s_data['error']}")
            continue

        print(f"   • Total Rows: {s_data.get('total_rows', 0)}")
        print(f"   • Unique Contributors: {s_data.get('unique_contributions', 0)}")

        dupe_pairs = s_data.get("duplicate_pairs", [])
        if dupe_pairs:
            print(f"   ❌ DUPLICATES FOUND: {len(dupe_pairs)} duplicate prompt entries!")
            for p in dupe_pairs[:20]:  # Show first 20
                eng = f" [{p.get('tts_engine')}]" if p.get('tts_engine') else ""
                print(f"      - Contrib ID: {p.get('contribution_id')}, Prompt: {p.get('prompt_id')}{eng} -> Count: {p.get('count')}")
            if len(dupe_pairs) > 20:
                print(f"      ... and {len(dupe_pairs) - 20} more duplicate entries.")
        else:
            print(f"   ✅ No duplicate (contribution_id, prompt_id) pairs found in {split_name} split.")

        dupe_contribs = s_data.get("duplicate_contributions", [])
        if dupe_contribs:
            print(f"   ⚠️ Repeated contribution IDs: {len(dupe_contribs)}")
            for cid in dupe_contribs[:10]:
                print(f"      - {cid}")

    print("\n" + "=" * 70)
    if report.get("has_duplicates"):
        print("⚠️ AUDIT RESULT: Duplicate entries detected in dataset.")
    else:
        print("✅ AUDIT RESULT: Clean! Zero duplicate entries detected in dataset.")
    print("=" * 70)


if __name__ == "__main__":
    main()
