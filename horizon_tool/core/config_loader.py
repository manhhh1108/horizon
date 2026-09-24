"""Load and expose YAML configuration for the tool."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


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
