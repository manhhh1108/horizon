"""Per-script pipeline: ChatGPT script writing -> sections -> Word (Phase 3)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from horizon_tool.core.statuses import (
    STATUS_DONE, STATUS_FAILED, STATUS_SKIPPED, STATUS_REJECTED,
)
from horizon_tool.core.output_manager import output_paths, save_raw_response
from horizon_tool.core.section_parser import parse_sections
from horizon_tool.core.word_builder import build_document

__all__ = ["ScriptWriter", "ImageWriter", "ScriptOutcome",
           "process_script", "render_images"]


class ScriptWriter(Protocol):
    """Anything that can turn a plugin + script into a ScriptResult.

    (The writer returns a ScriptResult; process_script wraps that into a
    ScriptOutcome for the caller.)
    """

    def write_script(self, plugin_text: str, script_text: str,
                     runtime_suffix: str = ""): ...


class ImageWriter(Protocol):
    """Anything that can render one image and return an ImageRenderResult."""

    def render_image(self, prompt: str, wrapper: str, dest_path: str): ...


@dataclass
class ScriptOutcome:
    """Result of processing one script through the Phase-3 steps.

    process_script only returns this on success; failures propagate as
    exceptions the worker catches.
    """

    ordinal: int
    word_status: str = STATUS_DONE
    missing_sections: list[str] = field(default_factory=list)
    conversation_url: str | None = None
    image_9x16_prompt: str | None = None
    thumbnail_16x9_prompt: str | None = None


def process_script(*, writer: ScriptWriter, ordinal: int, output_dir: Path,
                   plugin_text: str, script_text: str,
                   heading_regexes: dict[str, str],
                   runtime_suffix: str = "") -> ScriptOutcome:
    """Write the script via ChatGPT, save raw text, split sections, build Word.

    The final Word file always comes from the tool-built document so it contains
    every section the response provided (Master Prompt §7.3 preference).
    """
    result = writer.write_script(plugin_text, script_text, runtime_suffix)
    save_raw_response(output_dir, result.raw_text)

    parsed = parse_sections(result.raw_text, heading_regexes)
    docx_path = output_paths(output_dir, ordinal)["docx"]
    build_document(parsed, docx_path)

    return ScriptOutcome(
        ordinal=ordinal,
        word_status=STATUS_DONE,
        missing_sections=parsed.missing,
        conversation_url=result.conversation_url,
        image_9x16_prompt=parsed.sections.get("image_9x16"),
        thumbnail_16x9_prompt=parsed.sections.get("thumbnail_16x9"),
    )


def render_images(*, writer: ImageWriter, output_dir: Path, ordinal: int,
                  config: dict, image_9x16_prompt: str | None,
                  thumbnail_16x9_prompt: str | None,
                  do_9x16: bool = True, do_16x9: bool = True) -> dict[str, str]:
    """Render the 9:16 image and 16:9 thumbnail, returning per-step statuses.

    A step is SKIPPED when disabled or its section prompt is absent. A policy
    refusal yields REJECTED (no retry). Any other error yields FAILED. One
    image failing never blocks the other.
    """
    paths = output_paths(output_dir, ordinal)
    chatgpt_cfg = config.get("chatgpt", {})
    plan = [
        ("img_9x16", do_9x16, image_9x16_prompt,
         chatgpt_cfg.get("image_wrapper_9x16", "{PROMPT}"), str(paths["img_9x16"])),
        ("img_16x9", do_16x9, thumbnail_16x9_prompt,
         chatgpt_cfg.get("image_wrapper_16x9", "{PROMPT}"), str(paths["img_16x9"])),
    ]
    results: dict[str, str] = {}
    for key, enabled, prompt, wrapper, dest in plan:
        if not enabled or not prompt:
            results[key] = STATUS_SKIPPED
            continue
        try:
            results[key] = writer.render_image(prompt, wrapper, dest).status
        except Exception:  # noqa: BLE001 - one image must not stop the other
            results[key] = STATUS_FAILED
    return results
