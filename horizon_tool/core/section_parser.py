"""Split a ChatGPT response into the 9 Master-Prompt sections."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Canonical order of the 9 output sections.
SECTION_ORDER = [
    "full_story", "key_scenes", "image_9x16", "thumbnail_16x9", "video_prompt",
    "fb_title", "fb_description", "story_teaser", "hashtags",
]


@dataclass
class ParsedSections:
    """Result of splitting a response into sections."""

    sections: dict[str, str] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)

    @property
    def story(self) -> str:
        return self.sections.get("full_story", "")


def _compile(regexes: dict[str, str]) -> dict[str, re.Pattern]:
    return {k: re.compile(v, re.IGNORECASE) for k, v in regexes.items()}


def strip_continue_markers(text: str, continue_regex: str) -> str:
    """Remove any [PART X COMPLETE …] markers from text."""
    return re.sub(continue_regex, "", text, flags=re.IGNORECASE)


def merge_continue_parts(parts: list[str], continue_regex: str) -> str:
    """Join CONTINUE parts into one text and strip the part markers."""
    cleaned = [strip_continue_markers(p, continue_regex).strip() for p in parts]
    return "\n\n".join(p for p in cleaned if p).strip()


def parse_sections(text: str, heading_regexes: dict[str, str]) -> ParsedSections:
    """Split text into the 9 sections using per-section heading regexes.

    Each regex matches a section's heading line (tolerating '#', '**', an
    optional leading number, and case). Content is everything from after a
    heading line up to the next heading. The first occurrence of each section
    wins. Sections not found are reported in `missing`.
    """
    patterns = _compile(heading_regexes)
    lines = text.splitlines()

    matches: list[tuple[int, str]] = []
    seen: set[str] = set()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        for key, pat in patterns.items():
            if key in seen:
                continue
            if pat.search(stripped):
                matches.append((i, key))
                seen.add(key)
                break
    matches.sort()

    sections: dict[str, str] = {}
    for idx, (line_i, key) in enumerate(matches):
        start = line_i + 1
        end = matches[idx + 1][0] if idx + 1 < len(matches) else len(lines)
        sections[key] = "\n".join(lines[start:end]).strip()

    missing = [k for k in SECTION_ORDER if k not in sections]
    return ParsedSections(sections=sections, missing=missing)
