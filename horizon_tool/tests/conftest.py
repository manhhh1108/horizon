import sys
from pathlib import Path

# Make the repo root (parent of the horizon_tool package) importable.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
