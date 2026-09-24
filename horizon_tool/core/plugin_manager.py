"""Discover, read, hash, and templatize Master Prompt plugin files."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import docx  # python-docx

SUPPORTED_SUFFIXES = {".txt", ".md", ".docx", ".plugin"}

# Filename of a plugin backup directory that should never be listed as a plugin.
_HISTORY_DIR_NAME = "_history"


def list_plugins(folder: Path) -> list[Path]:
    """List plugin files directly in a folder (non-recursive).

    Only files with a supported suffix are returned; directories (including the
    ``_history`` backup dir) are excluded. Returns an empty list if the folder
    does not exist.
    """
    if not folder.exists():
        return []
    return [
        p for p in folder.iterdir()
        if p.is_file()
        and p.suffix.lower() in SUPPORTED_SUFFIXES
        and p.name != _HISTORY_DIR_NAME
    ]


def _bold_wrap(text: str) -> str:
    """Wrap the non-space content of a run in Markdown bold.

    Bold delimiters must hug the text (``**word**``); surrounding spaces would
    make CommonMark treat the asterisks as literal, so leading/trailing spaces
    are kept outside the markers. Whitespace-only runs are returned unchanged.
    """
    stripped = text.strip()
    if not stripped:
        return text
    prefix = text[: len(text) - len(text.lstrip())]
    suffix = text[len(text.rstrip()):]
    return f"{prefix}**{stripped}**{suffix}"


def docx_to_markdown(path: Path) -> str:
    """Convert a .docx to Markdown-ish text.

    Heading styles become '#'-prefixed lines (level clamped to 1-6); bold runs
    become **bold** so ChatGPT can see the prompt's structure. One paragraph
    per line.
    """
    document = docx.Document(str(path))
    lines: list[str] = []
    for para in document.paragraphs:
        style = (para.style.name or "").lower() if para.style else ""
        if style.startswith("heading"):
            match = re.search(r"\d+", style)
            level = min(int(match.group()) if match else 1, 6)
            lines.append("#" * level + " " + para.text)
            continue
        parts: list[str] = []
        for run in para.runs:
            text = run.text
            if run.bold:
                text = _bold_wrap(text)
            parts.append(text)
        lines.append("".join(parts) if parts else para.text)
    return "\n".join(lines)


def read_plugin_text(path: Path) -> str:
    """Read a plugin file to text. (.plugin decryption handled in Phase 8.)"""
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8")
    if suffix == ".docx":
        return docx_to_markdown(path)
    raise ValueError(f"Unsupported or not-yet-supported plugin type: {path.suffix}")


def plugin_hash(text: str) -> str:
    """SHA-256 hex digest of plugin content, for versioning in logs/reports."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def apply_variables(text: str, variables: dict[str, str]) -> str:
    """Replace {VAR} placeholders with values; unknown placeholders untouched.

    Values are assumed not to contain ``{OTHER_KEY}`` placeholder syntax (they
    are simple settings like "15s"), so the sequential replacements do not
    re-substitute each other.
    """
    for key, value in variables.items():
        text = text.replace("{" + key + "}", value)
    return text
