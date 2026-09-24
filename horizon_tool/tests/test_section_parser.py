# horizon_tool/tests/test_section_parser.py
import yaml
from pathlib import Path

from horizon_tool.core.section_parser import (
    SECTION_ORDER, parse_sections, merge_continue_parts, strip_continue_markers,
)

SELECTORS = yaml.safe_load(
    (Path(__file__).resolve().parents[1] / "config" / "selectors.yaml").read_text(encoding="utf-8")
)
HEADINGS = SELECTORS["section_headings"]
CONTINUE = SELECTORS["patterns"]["continue_marker"]

FULL = """FULL STORY

CHAPTER ONE — The Door

He stood there. **The truth was a lie.**

KEY SCENES + CONTINUITY NOTE

Scene 1 shock. Scene 2 pressure.

IMAGE PROMPT — 9:16

A vertical cinematic shot.

THUMBNAIL PROMPT — 16:9

A horizontal key art.

VIDEO AI PROMPT

SHOT 1 — 3s — tier1

FACEBOOK TITLE

HIS SLEEVE TORE OPEN. WHAT HAPPENED NEXT STOPPED EVERYONE.

FACEBOOK VIDEO DESCRIPTION

A gripping story.

STORY TEASER

He never expected it.

HASHTAGS

#story #viral #drama #twist #fyp
"""


def test_parse_all_nine_sections():
    parsed = parse_sections(FULL, HEADINGS)
    assert parsed.missing == []
    assert set(parsed.sections.keys()) == set(SECTION_ORDER)
    assert "CHAPTER ONE" in parsed.sections["full_story"]
    assert parsed.sections["hashtags"].startswith("#story")
    assert parsed.story == parsed.sections["full_story"]


def test_missing_sections_reported():
    text = "FULL STORY\n\nA short story.\n\nHASHTAGS\n\n#a #b"
    parsed = parse_sections(text, HEADINGS)
    assert "full_story" in parsed.sections
    assert "hashtags" in parsed.sections
    assert "image_9x16" in parsed.missing
    assert len(parsed.missing) == 7


def test_strip_continue_markers():
    text = 'Chapter text.\n[PART 1 COMPLETE — TYPE "CONTINUE" FOR THE NEXT PART]\nMore.'
    out = strip_continue_markers(text, CONTINUE)
    assert "PART 1 COMPLETE" not in out
    assert "Chapter text." in out and "More." in out


def test_merge_continue_parts_joins_and_strips():
    p1 = 'CHAPTER ONE\n\nStart.\n[PART 1 COMPLETE — TYPE "CONTINUE" FOR THE NEXT PART]'
    p2 = 'CHAPTER TWO\n\nEnd.'
    merged = merge_continue_parts([p1, p2], CONTINUE)
    assert "PART 1 COMPLETE" not in merged
    assert "CHAPTER ONE" in merged and "CHAPTER TWO" in merged


def test_headings_tolerate_markdown_and_numbering():
    text = "## 1. FULL STORY\n\nBody.\n\n**HASHTAGS**\n\n#x #y"
    parsed = parse_sections(text, HEADINGS)
    assert "full_story" in parsed.sections
    assert "hashtags" in parsed.sections
