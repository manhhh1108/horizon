"""Read and enumerate input scripts from a folder."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import docx  # python-docx

# BOM-less fallbacks tried in order after BOM detection. utf-8 is tried first
# because it errors on invalid sequences; cp1258 is a single-byte last resort
# that decodes almost anything, so it must come last.
_FALLBACK_ENCODINGS = ("utf-8", "cp1258")

_NUMBER_RE = re.compile(r"\d+")

_SUPPORTED_SUFFIXES = {".txt", ".docx"}


def read_text_file(path: Path) -> str:
    """Read a .txt file, auto-detecting a supported encoding.

    A byte-order mark is honoured explicitly (UTF-16 LE/BE, UTF-8-BOM), because
    UTF-16 decoding is greedy and would otherwise mis-decode single-byte
    (e.g. cp1258) content into garbage without raising. Without a BOM, UTF-8 is
    tried first, then cp1258 as a last resort.
    """
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig")
    for enc in _FALLBACK_ENCODINGS:
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise ValueError(f"Cannot decode text file with known encodings: {path}")


def extract_ordinal(filename: str) -> int | None:
    """Return the last integer sequence in the filename stem, or None."""
    stem = Path(filename).stem
    matches = _NUMBER_RE.findall(stem)
    return int(matches[-1]) if matches else None


def read_docx_file(path: Path) -> str:
    """Read a .docx file into plain text, one paragraph per line."""
    document = docx.Document(str(path))
    return "\n".join(p.text for p in document.paragraphs)


def read_script_content(path: Path) -> str:
    """Read a script file by extension (.txt or .docx)."""
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return read_text_file(path)
    if suffix == ".docx":
        return read_docx_file(path)
    raise ValueError(f"Unsupported script file type: {path.suffix}")


@dataclass
class ScriptFile:
    """A valid input script with its ordinal number."""
    ordinal: int
    path: Path

    @property
    def filename(self) -> str:
        return self.path.name


@dataclass
class SkippedFile:
    """An input file that was skipped, with a Vietnamese reason for the log."""
    path: Path
    reason: str


def scan_input_folder(folder: Path) -> tuple[list[ScriptFile], list[SkippedFile]]:
    """Scan a folder for .txt/.docx scripts.

    Returns valid scripts sorted by ordinal ascending, plus skipped files with
    reasons. Files without an ordinal, empty, or unreadable are skipped, never
    raised. Files with unsupported extensions are ignored entirely.
    """
    scripts: list[ScriptFile] = []
    skipped: list[SkippedFile] = []

    for path in folder.iterdir():
        if not path.is_file() or path.suffix.lower() not in _SUPPORTED_SUFFIXES:
            continue
        ordinal = extract_ordinal(path.name)
        if ordinal is None:
            skipped.append(SkippedFile(path, "Không có số thứ tự trong tên file"))
            continue
        try:
            content = read_script_content(path)
        except Exception as exc:  # noqa: BLE001 - report, never halt
            skipped.append(SkippedFile(path, f"Không đọc được file: {exc}"))
            continue
        if not content.strip():
            skipped.append(SkippedFile(path, "File rỗng"))
            continue
        scripts.append(ScriptFile(ordinal=ordinal, path=path))

    scripts.sort(key=lambda s: s.ordinal)
    return scripts, skipped


def _parse_selection(selection: str) -> set[int] | None:
    """Parse '5-20' / '3,7,9' / '1-3,7' into a set; '' -> None (all)."""
    selection = selection.strip()
    if not selection:
        return None
    wanted: set[int] = set()
    for part in selection.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo_s, hi_s = part.split("-", 1)
            lo, hi = int(lo_s), int(hi_s)
            wanted.update(range(min(lo, hi), max(lo, hi) + 1))
        else:
            wanted.add(int(part))
    return wanted


def filter_by_selection(scripts: list, selection: str) -> list:
    """Filter items exposing `.ordinal` by a selection string; '' returns all."""
    wanted = _parse_selection(selection)
    if wanted is None:
        return scripts
    return [s for s in scripts if s.ordinal in wanted]
