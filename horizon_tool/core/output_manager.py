"""Create per-script output folders and resolve name conflicts."""
from __future__ import annotations

from pathlib import Path

OVERWRITE = "overwrite"
SKIP = "skip"
TIMESTAMP = "timestamp"


def prepare_output_dir(output_root: Path, ordinal: int, policy: str,
                       suffix: str | None = None) -> Path | None:
    """Return the output dir for a script, applying the conflict policy.

    If the '<n>' dir does not exist yet it is created and returned regardless of
    policy (the policy only matters on a conflict). On conflict:
    - OVERWRITE: reuse the existing dir as-is. Existing files are NOT deleted;
      the pipeline overwrites individual files by name.
    - SKIP: return None (caller skips this script).
    - TIMESTAMP: create and return a sibling '<n>_<suffix>' dir (suffix is a
      timestamp string the caller supplies; required for this policy).
    """
    if policy == TIMESTAMP and suffix is None:
        raise ValueError("TIMESTAMP policy requires a suffix")
    base = Path(output_root) / str(ordinal)
    if not base.exists():
        base.mkdir(parents=True, exist_ok=True)
        return base
    if policy == SKIP:
        return None
    if policy == TIMESTAMP:
        stamped = Path(output_root) / f"{ordinal}_{suffix}"
        stamped.mkdir(parents=True, exist_ok=True)
        return stamped
    return base  # OVERWRITE


def output_paths(output_dir: Path, ordinal: int) -> dict[str, Path]:
    """Canonical filenames inside a script's output dir."""
    output_dir = Path(output_dir)
    return {
        "docx": output_dir / f"{ordinal}.docx",
        "img_9x16": output_dir / f"{ordinal}_9x16.png",
        "img_16x9": output_dir / f"{ordinal}_16x9.png",
        "video": output_dir / f"{ordinal}.mp4",
        "raw": output_dir / "raw_response.txt",
    }


def save_raw_response(output_dir: Path, text: str) -> Path:
    """Write the raw ChatGPT response to raw_response.txt."""
    path = Path(output_dir) / "raw_response.txt"
    path.write_text(text, encoding="utf-8")
    return path
