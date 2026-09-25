"""Load and expose YAML configuration for the tool."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from ruamel.yaml import YAML


def load_yaml(path: Path) -> dict[str, Any]:
    """Read a YAML file into a dict.

    Raises:
        FileNotFoundError: if the file does not exist.
        ValueError: if the YAML root is not a mapping.
    """
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config root must be a mapping: {path}")
    return data


@dataclass
class AppConfig:
    """Typed view over config.yaml.

    Typed properties are added on demand as each phase needs them; they cover
    the GUI-facing values used so far. For any key without a typed accessor,
    read ``raw`` directly (e.g. ``cfg.raw["timeouts"]``). ``raw`` is the
    intended escape hatch, not a leak.
    """

    raw: dict[str, Any]

    @classmethod
    def load(cls, path: Path) -> "AppConfig":
        return cls(raw=load_yaml(path))

    @property
    def video_durations(self) -> list[str]:
        return list(self.raw.get("grok", {}).get("durations", []))

    @property
    def video_qualities(self) -> list[str]:
        return list(self.raw.get("grok", {}).get("qualities", []))

    @property
    def send_mode(self) -> str:
        return str(self.raw.get("chatgpt", {}).get("send_mode", "two_messages"))

    @property
    def runtime_suffix(self) -> str:
        return str(self.raw.get("chatgpt", {}).get("runtime_suffix", ""))


def _deep_merge(dst: Any, src: dict) -> None:
    """Recursively write src's values into dst (a ruamel mapping), in place.

    Nested dicts are merged key-by-key so existing keys/comments in dst are kept;
    only the keys present in src are updated. Keys in dst but not in src survive.
    """
    for key, value in src.items():
        if isinstance(value, dict) and isinstance(dst.get(key), dict):
            _deep_merge(dst[key], value)
        else:
            dst[key] = value


def save_config(path: Path, cfg: dict) -> None:
    """Persist config changes, preserving comments AND any unknown keys.

    Loads the existing config.yaml with ruamel (round-trip), merges the provided
    values into it, and writes it back. Keys/comments already in the file that
    are absent from ``cfg`` are kept — no silent data loss. If the file does not
    exist yet, a fresh document is written from ``cfg``.
    """
    path = Path(path)
    yaml_rt = YAML()  # round-trip: preserves comments, quoting, key order
    yaml_rt.preserve_quotes = True
    if path.exists():
        with path.open("r", encoding="utf-8") as fh:
            doc = yaml_rt.load(fh) or {}
    else:
        doc = {}
    _deep_merge(doc, cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        yaml_rt.dump(doc, fh)
