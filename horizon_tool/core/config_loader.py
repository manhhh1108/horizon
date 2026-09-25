"""Load and expose YAML configuration for the tool."""
from __future__ import annotations

import json
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


def save_config(path: Path, cfg: dict) -> None:
    """Write config.yaml from a full config dict, preserving the layout/comments.

    Scalars are emitted with json.dumps (valid YAML double-quoted style, safe for
    embedded newlines); durations/qualities as flow sequences. Round-trips via
    load_yaml.
    """
    g = cfg.get("grok", {})
    c = cfg.get("chatgpt", {})
    t = cfg.get("timeouts", {})
    r = cfg.get("retry", {})
    d = cfg.get("delays", {})
    ar = cfg.get("auto_resume", {})

    def s(v):  # safe YAML scalar
        return json.dumps(v, ensure_ascii=False)

    def lst(v):
        return "[" + ", ".join(json.dumps(i, ensure_ascii=False) for i in v) + "]"

    text = f"""# General runtime configuration. Values here drive GUI dropdowns and timing so
# the tool adapts to ChatGPT/Grok UI changes without touching code.

grok:
  durations: {lst(g.get("durations", []))}      # GUI "Thời lượng" dropdown
  qualities: {lst(g.get("qualities", []))}          # GUI "Chất lượng" dropdown
  render_timeout_seconds: {int(g.get("render_timeout_seconds", 600))}
  motion_prompt_override: {s(g.get("motion_prompt_override", ""))}

chatgpt:
  send_mode: {s(c.get("send_mode", "two_messages"))}
  runtime_suffix: {s(c.get("runtime_suffix", ""))}
  image_wrapper_9x16: {s(c.get("image_wrapper_9x16", "{{PROMPT}}"))}
  image_wrapper_16x9: {s(c.get("image_wrapper_16x9", "{{PROMPT}}"))}

timeouts:
  element_wait_seconds: {int(t.get("element_wait_seconds", 30))}
  response_wait_seconds: {int(t.get("response_wait_seconds", 600))}

retry:
  max_attempts: {int(r.get("max_attempts", 3))}
  backoff_base_seconds: {int(r.get("backoff_base_seconds", 5))}

delays:
  between_steps_min_seconds: {int(d.get("between_steps_min_seconds", 2))}
  between_steps_max_seconds: {int(d.get("between_steps_max_seconds", 6))}
  between_scripts_min_seconds: {int(d.get("between_scripts_min_seconds", 5))}
  between_scripts_max_seconds: {int(d.get("between_scripts_max_seconds", 15))}

auto_resume:
  enabled: {"true" if ar.get("enabled") else "false"}
  check_interval_minutes: {int(ar.get("check_interval_minutes", 30))}
"""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")
