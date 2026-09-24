"""Discover, read, hash, and templatize Master Prompt plugin files."""
from __future__ import annotations

import hashlib
from pathlib import Path

import docx  # python-docx

SUPPORTED_SUFFIXES = {".txt", ".md", ".docx", ".plugin"}


def list_plugins(folder: Path) -> list[Path]:
    """List plugin files in a folder (excludes the _history backup dir)."""
    if not folder.exists():
        return []
    return [
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES
    ]


def docx_to_markdown(path: Path) -> str:
    """Convert a .docx to Markdown-ish text.

    Heading styles become '#'-prefixed lines; bold runs become **bold** so
    ChatGPT can see the prompt's structure. One paragraph per line.
    """
    document = docx.Document(str(path))
    lines: list[str] = []
    for para in document.paragraphs:
        style = (para.style.name or "").lower() if para.style else ""
        if style.startswith("heading"):
            level = "".join(ch for ch in style if ch.isdigit()) or "1"
            lines.append("#" * int(level) + " " + para.text)
            continue
        parts: list[str] = []
        for run in para.runs:
            text = run.text
            if run.bold and text.strip():
                text = f"**{text}**"
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
    """Replace {VAR} placeholders with values; unknown placeholders untouched."""
    for key, value in variables.items():
        text = text.replace("{" + key + "}", value)
    return text
