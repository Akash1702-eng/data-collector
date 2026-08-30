"""
Generate Synthetic AI Voice Data for Specific Human Contribution ID.
(Helper wrapper inside scripts/ directory)
"""

import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from synthesize_for_id import main

if __name__ == "__main__":
    main()
