"""Per-script pipeline: ChatGPT script writing -> sections -> Word (Phase 3)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from horizon_tool.core.output_manager import output_paths, save_raw_response
from horizon_tool.core.section_parser import parse_sections
from horizon_tool.core.word_builder import build_document

STATUS_DONE = "Xong"
STATUS_FAILED = "Lỗi"


class ScriptWriter(Protocol):
    """Anything that can turn a plugin + script into a ScriptResult.

    (The writer returns a ScriptResult; process_script wraps that into a
    ScriptOutcome for the caller.)
    """

    def write_script(self, plugin_text: str, script_text: str,
                     runtime_suffix: str = ""): ...


@dataclass
class ScriptOutcome:
    """Result of processing one script through the Phase-3 steps.

    process_script only returns this on success (word_status == STATUS_DONE);
    failures propagate as exceptions the worker catches, so word_status has no
    failure default here.
    """

    ordinal: int
    word_status: str = STATUS_DONE
    missing_sections: list[str] = field(default_factory=list)
    conversation_url: str | None = None


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
    )
