# Horizon X Media Tool — Phase 3 Implementation Plan (ChatGPT script writing → sections → Word → output/log/report)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Turn one script into a finished Word file: drive ChatGPT to rewrite the story (with the CONTINUE loop), collect the raw response, split it into the 9 sections, build the Word document with the required formatting, write everything into `output/<n>/`, and record a per-session `log.txt` and `report.xlsx`.

**Architecture:** Pure logic (section parsing, Word building, output/report) lives in `core/` and is fully unit-tested. `automation/chatgpt.py` drives ChatGPT; its CONTINUE loop and response collection are pure and testable with fakes, while the DOM-touching parts use selectors from `selectors.yaml` (placeholders, tuned against the live site with the user). `core/pipeline.py` orchestrates the SCRIPT_WRITING → WORD_BUILT steps and is tested with a fake writer. A new GUI worker runs the pipeline over the selected input folder.

**Tech Stack:** Python 3.10-compatible, python-docx, openpyxl, Playwright, PySide6, pytest.

**Convention:** UI/log/report text Vietnamese; code identifiers/docstrings/comments English.

**Base branch:** `main`. Work branch: `phase-3-script-word`.

**Verified preconditions:** `selectors.yaml` has `section_headings` (9 keys) + `patterns.continue_marker`; openpyxl and python-docx import fine.

**Honesty note:** The pure logic (Tasks 1–3) and the CONTINUE-loop logic (Task 4) are fully tested. The ChatGPT DOM interaction (new chat, typing, waiting for a response to finish, reading the message, detecting a `.docx` download link) depends on the live ChatGPT UI and cannot be verified here — those methods use YAML selectors marked `# TODO: kiểm tra selector thực tế` and must be tuned on the user's logged-in machine. The GUI worker wiring (Task 5) runs the full pipeline; its ChatGPT step will only succeed once selectors are tuned.

---

### Task 1: Section parser (`core/section_parser.py`)

**Files:**
- Create: `horizon_tool/core/section_parser.py`
- Test: `horizon_tool/tests/test_section_parser.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test, confirm FAIL** (`horizon_tool\.venv\Scripts\python.exe -m pytest horizon_tool/tests/test_section_parser.py -v`).

- [ ] **Step 3: Implement `core/section_parser.py`**

```python
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
```

- [ ] **Step 4: Run test, confirm 5 passed.**

- [ ] **Step 5: Commit**

```bash
cd "D:/Home/wf"
git add horizon_tool/core/section_parser.py horizon_tool/tests/test_section_parser.py
git commit -m "feat: section parser for the 9 Master-Prompt sections + CONTINUE merge"
```

---

### Task 2: Word builder (`core/word_builder.py`)

**Files:**
- Create: `horizon_tool/core/word_builder.py`
- Test: `horizon_tool/tests/test_word_builder.py`

- [ ] **Step 1: Write the failing test**

```python
# horizon_tool/tests/test_word_builder.py
import docx

from horizon_tool.core.section_parser import ParsedSections
from horizon_tool.core.word_builder import build_document


def _parsed():
    return ParsedSections(sections={
        "full_story": "CHAPTER ONE — The Door\n\nHe stood. **The truth was a lie.**",
        "key_scenes": "Scene 1. Scene 2.",
        "image_9x16": "A vertical shot.",
        "thumbnail_16x9": "A key art.",
        "video_prompt": "SHOT 1 — 3s\nSHOT 2 — 3s",
        "fb_title": "his sleeve tore open. what happened next stopped everyone.",
        "fb_description": "A gripping story.",
        "story_teaser": "He never expected it.",
        "hashtags": "#story #viral #drama #twist #fyp",
    }, missing=[])


def _read(path):
    return docx.Document(str(path))


def test_builds_headings_and_bold(tmp_path):
    out = tmp_path / "1.docx"
    build_document(_parsed(), out)
    doc = _read(out)
    styles = [p.style.name for p in doc.paragraphs]
    texts = [p.text for p in doc.paragraphs]
    assert "Heading 1" in styles
    assert any(t == "FULL STORY" for t in texts)           # section title
    assert any(s == "Heading 2" and "CHAPTER ONE" in t
               for s, t in zip(styles, texts))             # chapter heading
    # a real bold run exists
    assert any(r.bold for p in doc.paragraphs for r in p.runs)


def test_facebook_title_uppercase_and_bold(tmp_path):
    out = tmp_path / "2.docx"
    build_document(_parsed(), out)
    doc = _read(out)
    title_paras = [p for p in doc.paragraphs
                   if p.text.startswith("HIS SLEEVE TORE OPEN")]
    assert title_paras
    p = title_paras[0]
    assert p.text == p.text.upper()                        # all uppercase
    assert all(r.bold for r in p.runs if r.text.strip())   # bold


def test_video_prompt_is_monospace(tmp_path):
    out = tmp_path / "3.docx"
    build_document(_parsed(), out)
    doc = _read(out)
    runs = [r for p in doc.paragraphs for r in p.runs if "SHOT 1" in r.text]
    assert runs and runs[0].font.name == "Consolas"


def test_missing_sections_still_builds(tmp_path):
    out = tmp_path / "4.docx"
    parsed = ParsedSections(sections={"full_story": "Just a story."}, missing=[
        "key_scenes", "image_9x16", "thumbnail_16x9", "video_prompt",
        "fb_title", "fb_description", "story_teaser", "hashtags"])
    build_document(parsed, out)
    doc = _read(out)
    assert any(p.text == "FULL STORY" for p in doc.paragraphs)
```

- [ ] **Step 2: Run test, confirm FAIL.**

- [ ] **Step 3: Implement `core/word_builder.py`**

```python
"""Build the output Word document from parsed sections."""
from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.shared import Pt

from horizon_tool.core.section_parser import SECTION_ORDER, ParsedSections

# Display heading for each section (canonical Master-Prompt names).
SECTION_TITLES = {
    "full_story": "FULL STORY",
    "key_scenes": "KEY SCENES + CONTINUITY NOTE",
    "image_9x16": "IMAGE PROMPT — 9:16",
    "thumbnail_16x9": "THUMBNAIL PROMPT — 16:9",
    "video_prompt": "VIDEO AI PROMPT",
    "fb_title": "FACEBOOK TITLE",
    "fb_description": "FACEBOOK VIDEO DESCRIPTION",
    "story_teaser": "STORY TEASER",
    "hashtags": "HASHTAGS",
}

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def _add_markdown_runs(paragraph, text: str) -> None:
    """Add text to a paragraph, turning **bold** into real bold runs."""
    pos = 0
    for m in _BOLD_RE.finditer(text):
        if m.start() > pos:
            paragraph.add_run(text[pos:m.start()])
        run = paragraph.add_run(m.group(1))
        run.bold = True
        pos = m.end()
    if pos < len(text):
        paragraph.add_run(text[pos:])


def _render_story(doc, body: str) -> None:
    for line in body.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.upper().startswith("CHAPTER "):
            doc.add_heading(stripped, level=2)
        else:
            _add_markdown_runs(doc.add_paragraph(), line)


def _render_monospace(doc, body: str) -> None:
    for line in body.split("\n"):
        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.left_indent = Pt(18)
        run = paragraph.add_run(line)
        run.font.name = "Consolas"
        run.font.size = Pt(10)


def _render_generic(doc, body: str) -> None:
    for line in body.split("\n"):
        if line.strip():
            _add_markdown_runs(doc.add_paragraph(), line)


def build_document(parsed: ParsedSections, path: Path) -> None:
    """Write parsed sections to a .docx with the required formatting.

    Calibri 11 body; section titles as Heading 1; chapter titles as Heading 2;
    Facebook title uppercase + bold on its own paragraph; Video AI Prompt in a
    monospace (Consolas) indented block. No cover, TOC, header, footer, or page
    numbers (python-docx adds none by default). Missing sections are skipped.
    """
    doc = Document()
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)

    for key in SECTION_ORDER:
        if key not in parsed.sections:
            continue
        doc.add_heading(SECTION_TITLES[key], level=1)
        body = parsed.sections[key]
        if key == "full_story":
            _render_story(doc, body)
        elif key == "fb_title":
            paragraph = doc.add_paragraph()
            run = paragraph.add_run(body.strip().upper())
            run.bold = True
        elif key == "video_prompt":
            _render_monospace(doc, body)
        else:
            _render_generic(doc, body)

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(path))
```

- [ ] **Step 4: Run test, confirm 4 passed.**

- [ ] **Step 5: Commit**

```bash
cd "D:/Home/wf"
git add horizon_tool/core/word_builder.py horizon_tool/tests/test_word_builder.py
git commit -m "feat: Word builder with headings, bold, uppercase title, monospace video prompt"
```

---

### Task 3: Output manager + report + session logging

**Files:**
- Create: `horizon_tool/core/output_manager.py`
- Create: `horizon_tool/core/report.py`
- Create: `horizon_tool/core/logging_setup.py`
- Test: `horizon_tool/tests/test_output_manager.py`, `horizon_tool/tests/test_report.py`

- [ ] **Step 1: Write the failing tests**

```python
# horizon_tool/tests/test_output_manager.py
from horizon_tool.core.output_manager import (
    prepare_output_dir, output_paths, save_raw_response,
    OVERWRITE, SKIP, TIMESTAMP,
)


def test_prepare_creates_dir(tmp_path):
    d = prepare_output_dir(tmp_path, 5, OVERWRITE)
    assert d == tmp_path / "5"
    assert d.is_dir()


def test_prepare_skip_returns_none_when_exists(tmp_path):
    (tmp_path / "5").mkdir()
    assert prepare_output_dir(tmp_path, 5, SKIP) is None


def test_prepare_overwrite_reuses_existing(tmp_path):
    (tmp_path / "5").mkdir()
    d = prepare_output_dir(tmp_path, 5, OVERWRITE)
    assert d == tmp_path / "5"


def test_prepare_timestamp_makes_new_dir(tmp_path):
    (tmp_path / "5").mkdir()
    d = prepare_output_dir(tmp_path, 5, TIMESTAMP, suffix="20260924_101500")
    assert d == tmp_path / "5_20260924_101500"
    assert d.is_dir()


def test_output_paths_naming(tmp_path):
    paths = output_paths(tmp_path / "7", 7)
    assert paths["docx"].name == "7.docx"
    assert paths["img_9x16"].name == "7_9x16.png"
    assert paths["img_16x9"].name == "7_16x9.png"
    assert paths["video"].name == "7.mp4"
    assert paths["raw"].name == "raw_response.txt"


def test_save_raw_response(tmp_path):
    d = tmp_path / "1"
    d.mkdir()
    p = save_raw_response(d, "nội dung thô")
    assert p.read_text(encoding="utf-8") == "nội dung thô"
```

```python
# horizon_tool/tests/test_report.py
import openpyxl

from horizon_tool.core.report import ReportWriter, STATUS_REJECTED


def test_report_writes_rows_and_header(tmp_path):
    path = tmp_path / "report.xlsx"
    rw = ReportWriter(path)
    rw.add_row(ordinal=1, input_filename="1.txt", plugin_name="v11",
               plugin_hash="abc123", account="chatgpt_1", word="Xong",
               img_9x16="Xong", img_16x9=STATUS_REJECTED, video="Bỏ qua",
               missing_sections="", error="", duration_seconds=42.5)
    rw.save()

    wb = openpyxl.load_workbook(path)
    ws = wb.active
    header = [c.value for c in ws[1]]
    assert "STT" in header and "Video" in header
    row2 = [c.value for c in ws[2]]
    assert 1 in row2
    assert "v11" in row2


def test_report_highlights_rejected(tmp_path):
    path = tmp_path / "report.xlsx"
    rw = ReportWriter(path)
    rw.add_row(ordinal=2, input_filename="2.txt", plugin_name="v11",
               plugin_hash="h", account="chatgpt_1", word="Xong",
               img_9x16=STATUS_REJECTED, img_16x9="Xong", video="Bỏ qua",
               missing_sections="", error="", duration_seconds=1.0)
    rw.save()
    wb = openpyxl.load_workbook(path)
    ws = wb.active
    # at least one cell in the data row has a non-default fill (highlight)
    fills = [ws.cell(row=2, column=c).fill.fgColor.rgb for c in range(1, ws.max_column + 1)]
    assert any(f not in (None, "00000000") for f in fills)
```

- [ ] **Step 2: Run both tests, confirm FAIL.**

- [ ] **Step 3: Implement `core/output_manager.py`**

```python
"""Create per-script output folders and resolve name conflicts."""
from __future__ import annotations

from pathlib import Path

OVERWRITE = "overwrite"
SKIP = "skip"
TIMESTAMP = "timestamp"


def prepare_output_dir(output_root: Path, ordinal: int, policy: str,
                       suffix: str | None = None) -> Path | None:
    """Return the output dir for a script, applying the conflict policy.

    - OVERWRITE: reuse (create if absent).
    - SKIP: return None if it already exists.
    - TIMESTAMP: if it exists, create a sibling '<n>_<suffix>' dir.
    """
    base = Path(output_root) / str(ordinal)
    if not base.exists():
        base.mkdir(parents=True, exist_ok=True)
        return base
    if policy == SKIP:
        return None
    if policy == TIMESTAMP:
        stamped = Path(output_root) / f"{ordinal}_{suffix}"
        stamped.mkdir(parents=True, exist_ok=True)
        return stamped
    return base  # OVERWRITE


def output_paths(output_dir: Path, ordinal: int) -> dict[str, Path]:
    """Canonical filenames inside a script's output dir."""
    output_dir = Path(output_dir)
    return {
        "docx": output_dir / f"{ordinal}.docx",
        "img_9x16": output_dir / f"{ordinal}_9x16.png",
        "img_16x9": output_dir / f"{ordinal}_16x9.png",
        "video": output_dir / f"{ordinal}.mp4",
        "raw": output_dir / "raw_response.txt",
    }


def save_raw_response(output_dir: Path, text: str) -> Path:
    """Write the raw ChatGPT response to raw_response.txt."""
    path = Path(output_dir) / "raw_response.txt"
    path.write_text(text, encoding="utf-8")
    return path
```

- [ ] **Step 4: Implement `core/report.py`**

```python
"""Write the per-session report.xlsx summary."""
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

STATUS_REJECTED = "Bị từ chối"

_HEADERS = [
    "STT", "File input", "Plugin", "Hash", "Tài khoản",
    "Word", "Ảnh 9:16", "Ảnh 16:9", "Video",
    "Section thiếu", "Lỗi/Bỏ qua", "Thời gian (s)",
]
_REJECT_FILL = PatternFill(start_color="FFF4CCCC", end_color="FFF4CCCC",
                           fill_type="solid")


class ReportWriter:
    """Accumulates report rows and saves an .xlsx with highlighted rejects."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._wb = Workbook()
        self._ws = self._wb.active
        self._ws.title = "Report"
        self._ws.append(_HEADERS)
        for cell in self._ws[1]:
            cell.font = Font(bold=True)

    def add_row(self, *, ordinal: int, input_filename: str, plugin_name: str,
                plugin_hash: str, account: str, word: str, img_9x16: str,
                img_16x9: str, video: str, missing_sections: str, error: str,
                duration_seconds: float) -> None:
        values = [ordinal, input_filename, plugin_name, plugin_hash, account,
                  word, img_9x16, img_16x9, video, missing_sections, error,
                  round(duration_seconds, 1)]
        self._ws.append(values)
        row = self._ws.max_row
        # Highlight any step cell that was rejected.
        for col, value in enumerate(values, start=1):
            if value == STATUS_REJECTED:
                self._ws.cell(row=row, column=col).fill = _REJECT_FILL

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._wb.save(str(self.path))
```

- [ ] **Step 5: Implement `core/logging_setup.py`**

```python
"""Session logging helpers (file + optional GUI callback)."""
from __future__ import annotations

import logging
from pathlib import Path


def setup_session_logger(log_path: Path, name: str = "horizon") -> logging.Logger:
    """Return a logger that writes to log_path (UTF-8). Idempotent per name."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    # Avoid stacking duplicate file handlers for the same path.
    for h in logger.handlers:
        if isinstance(h, logging.FileHandler) and getattr(h, "_horizon_path", None) == str(log_path):
            return logger
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler._horizon_path = str(log_path)  # type: ignore[attr-defined]
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger
```

- [ ] **Step 6: Run both tests, confirm all pass. Then full suite.**

- [ ] **Step 7: Commit**

```bash
cd "D:/Home/wf"
git add horizon_tool/core/output_manager.py horizon_tool/core/report.py horizon_tool/core/logging_setup.py horizon_tool/tests/test_output_manager.py horizon_tool/tests/test_report.py
git commit -m "feat: output manager, report.xlsx writer, and session logging"
```

---

### Task 4: ChatGPT script-writing automation (`automation/chatgpt.py`)

**Files:**
- Create: `horizon_tool/automation/chatgpt.py`
- Test: `horizon_tool/tests/test_chatgpt_loop.py`

- [ ] **Step 1: Write the failing test** (pure CONTINUE-loop logic; no browser)

```python
# horizon_tool/tests/test_chatgpt_loop.py
from horizon_tool.automation.chatgpt import should_continue, run_continue_loop

CONTINUE = r'\[PART\s+\d+\s+COMPLETE.*?CONTINUE.*?\]'


def test_should_continue_detects_marker():
    assert should_continue('text\n[PART 1 COMPLETE — TYPE "CONTINUE" FOR THE NEXT PART]', CONTINUE)
    assert not should_continue("just a normal ending.", CONTINUE)


def test_run_continue_loop_collects_all_parts():
    responses = [
        'PART ONE BODY\n[PART 1 COMPLETE — TYPE "CONTINUE" FOR THE NEXT PART]',
        'PART TWO BODY\n[PART 2 COMPLETE — TYPE "CONTINUE" FOR THE NEXT PART]',
        'PART THREE BODY (final)',
    ]
    reads = iter(responses)
    sent: list[str] = []

    def read_response() -> str:
        return next(reads)

    def send_message(text: str) -> None:
        sent.append(text)

    parts = run_continue_loop(read_response, send_message, CONTINUE, max_parts=10)

    assert len(parts) == 3
    assert parts[0].startswith("PART ONE")
    assert sent == ["CONTINUE", "CONTINUE"]  # sent twice, not after the last


def test_run_continue_loop_respects_max_parts():
    def read_response() -> str:
        return '...\n[PART 9 COMPLETE — TYPE "CONTINUE" FOR THE NEXT PART]'  # never ends
    sent: list[str] = []
    parts = run_continue_loop(read_response, lambda t: sent.append(t), CONTINUE, max_parts=3)
    assert len(parts) == 3  # stopped at the cap
```

- [ ] **Step 2: Run test, confirm FAIL.**

- [ ] **Step 3: Implement `automation/chatgpt.py`**

```python
"""ChatGPT automation for script writing.

The CONTINUE loop and response collection are pure functions (testable without
a browser). The DOM-touching methods on ChatGPTWriter use selectors from
selectors.yaml — those are placeholders to be tuned against the live site.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from horizon_tool.automation.browser import BrowserSession


def should_continue(response_text: str, continue_regex: str) -> bool:
    """True if a response ends with a [PART X COMPLETE …] marker."""
    return re.search(continue_regex, response_text, flags=re.IGNORECASE) is not None


def run_continue_loop(read_response: Callable[[], str],
                      send_message: Callable[[str], None],
                      continue_regex: str, max_parts: int = 20) -> list[str]:
    """Collect response parts, sending CONTINUE while the marker appears.

    read_response(): return the latest completed assistant message.
    send_message(text): send a user message (used to send 'CONTINUE').
    Stops when a part lacks the marker or max_parts is reached.
    """
    parts: list[str] = []
    for _ in range(max_parts):
        text = read_response()
        parts.append(text)
        if not should_continue(text, continue_regex):
            break
        send_message("CONTINUE")
    return parts


@dataclass
class ScriptResult:
    """Outcome of writing one script."""

    raw_text: str
    conversation_url: str | None = None
    docx_path: str | None = None


class ChatGPTWriter:
    """Drives ChatGPT to rewrite a story from a plugin + reference script.

    DOM methods use selectors from `selectors`; they are placeholders marked in
    selectors.yaml and must be verified against the live ChatGPT UI.
    """

    def __init__(self, session: BrowserSession, selectors: dict, config: dict) -> None:
        self.session = session
        self.selectors = selectors
        self.config = config
        self._continue_regex = selectors["patterns"]["continue_marker"]

    # ----- pure orchestration (testable via subclassing/fakes) ------------
    def write_script(self, plugin_text: str, script_text: str,
                     runtime_suffix: str = "") -> ScriptResult:
        """Open a chat, send plugin+script, run the CONTINUE loop, collect text."""
        self._open_new_chat()
        send_mode = self.config.get("chatgpt", {}).get("send_mode", "two_messages")
        if send_mode == "combined":
            first = plugin_text + "\n\n" + script_text
            if runtime_suffix:
                first += "\n\n" + runtime_suffix
            self._send(first)
        else:
            self._send(plugin_text)
            second = script_text + ("\n\n" + runtime_suffix if runtime_suffix else "")
            self._send(second)

        parts = run_continue_loop(
            self._read_last_response, self._send, self._continue_regex,
            max_parts=int(self.config.get("chatgpt", {}).get("max_parts", 20)),
        )
        from horizon_tool.core.section_parser import merge_continue_parts
        raw = merge_continue_parts(parts, self._continue_regex)
        return ScriptResult(
            raw_text=raw,
            conversation_url=self._current_url(),
            docx_path=self._try_download_docx(),
        )

    # ----- DOM methods (selectors are placeholders; tune on live site) ----
    def _open_new_chat(self) -> None:
        self.session.goto(self.selectors["chatgpt"]["url_new_chat"])

    def _send(self, text: str) -> None:
        sel = self.selectors["chatgpt"]
        self.session.paste_text(sel["input_box"], text)
        self.session.click_with_retry(sel["send_button"])

    def _read_last_response(self) -> str:
        # TODO: kiểm tra selector thực tế — wait for the Stop button to vanish
        # (response finished), then read the last assistant message text.
        sel = self.selectors["chatgpt"]
        self.session.wait_for(sel["assistant_message"])
        loc = self.session.page.locator(sel["assistant_message"]).last
        return loc.inner_text()

    def _current_url(self) -> str | None:
        try:
            return self.session.page.url
        except Exception:  # noqa: BLE001
            return None

    def _try_download_docx(self) -> str | None:
        # TODO: kiểm tra selector thực tế — detect a .docx download link and
        # save it. Returns None if ChatGPT returned text only.
        return None
```

- [ ] **Step 4: Run test, confirm 3 passed.**

- [ ] **Step 5: Commit**

```bash
cd "D:/Home/wf"
git add horizon_tool/automation/chatgpt.py horizon_tool/tests/test_chatgpt_loop.py
git commit -m "feat: ChatGPT script writer with tested CONTINUE loop (DOM selectors TODO)"
```

---

### Task 5: Pipeline (script → Word) + GUI worker wiring

**Files:**
- Create: `horizon_tool/core/pipeline.py`
- Modify: `horizon_tool/gui/worker.py` (add a real script pipeline worker; keep the Phase-1 stub class intact for existing tests)
- Modify: `horizon_tool/gui/main_window.py` (use the real worker in `on_start`)
- Test: `horizon_tool/tests/test_pipeline.py`, extend `horizon_tool/tests/test_main_window.py`

- [ ] **Step 1: Write the failing test** (fake writer produces a full 9-section response)

```python
# horizon_tool/tests/test_pipeline.py
import docx

from horizon_tool.core.pipeline import process_script
from horizon_tool.core.section_parser import ParsedSections
from horizon_tool.automation.chatgpt import ScriptResult

FULL = """FULL STORY

CHAPTER ONE — The Door

He stood. **The truth was a lie.**

KEY SCENES + CONTINUITY NOTE

Scene 1.

IMAGE PROMPT — 9:16

Vertical.

THUMBNAIL PROMPT — 16:9

Horizontal.

VIDEO AI PROMPT

SHOT 1 — 3s

FACEBOOK TITLE

a title. another sentence.

FACEBOOK VIDEO DESCRIPTION

Desc.

STORY TEASER

Teaser.

HASHTAGS

#a #b #c #d #e
"""


class FakeWriter:
    def write_script(self, plugin_text, script_text, runtime_suffix=""):
        return ScriptResult(raw_text=FULL, conversation_url="https://chat/x")


def test_process_script_builds_word_and_raw(tmp_path):
    import yaml
    from pathlib import Path
    selectors = yaml.safe_load(
        (Path("horizon_tool/config/selectors.yaml")).read_text(encoding="utf-8"))
    out_dir = tmp_path / "output" / "3"
    out_dir.mkdir(parents=True)

    result = process_script(
        writer=FakeWriter(), ordinal=3, output_dir=out_dir,
        plugin_text="PLUGIN", script_text="SCRIPT",
        heading_regexes=selectors["section_headings"],
    )

    assert (out_dir / "raw_response.txt").exists()
    docx_path = out_dir / "3.docx"
    assert docx_path.exists()
    doc = docx.Document(str(docx_path))
    assert any(p.text == "FULL STORY" for p in doc.paragraphs)
    assert result.word_status == "Xong"
    assert result.missing_sections == []
    assert result.conversation_url == "https://chat/x"


def test_process_script_reports_missing_sections(tmp_path):
    class PartialWriter:
        def write_script(self, plugin_text, script_text, runtime_suffix=""):
            return ScriptResult(raw_text="FULL STORY\n\nOnly a story.\n\nHASHTAGS\n\n#a")
    import yaml
    from pathlib import Path
    selectors = yaml.safe_load(
        (Path("horizon_tool/config/selectors.yaml")).read_text(encoding="utf-8"))
    out_dir = tmp_path / "5"
    out_dir.mkdir(parents=True)
    result = process_script(
        writer=PartialWriter(), ordinal=5, output_dir=out_dir,
        plugin_text="P", script_text="S",
        heading_regexes=selectors["section_headings"])
    assert (out_dir / "5.docx").exists()
    assert "image_9x16" in result.missing_sections
```

- [ ] **Step 2: Run test, confirm FAIL.**

- [ ] **Step 3: Implement `core/pipeline.py`**

```python
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
    """Anything that can turn a plugin + script into a ScriptResult."""

    def write_script(self, plugin_text: str, script_text: str,
                     runtime_suffix: str = ""): ...


@dataclass
class ScriptOutcome:
    """Result of processing one script through the Phase-3 steps."""

    ordinal: int
    word_status: str = STATUS_FAILED
    missing_sections: list[str] = field(default_factory=list)
    conversation_url: str | None = None
    error: str = ""


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
```

- [ ] **Step 4: Run test, confirm 2 passed.**

- [ ] **Step 5: Add a real script worker to `gui/worker.py`** (append; keep `PipelineWorker` stub for existing tests)

```python
# append to horizon_tool/gui/worker.py

from pathlib import Path

from horizon_tool.core.input_reader import scan_input_folder, filter_by_selection
from horizon_tool.core.pipeline import process_script


class ScriptRunWorker(QThread):
    """Runs the Phase-3 script->Word pipeline over an input folder.

    `writer_factory(account) -> ScriptWriter` builds the ChatGPT writer; it is
    injected so the worker can be exercised without a real browser. Cooperative
    pause/stop at script boundaries.
    """

    log = Signal(str)
    progress = Signal(int, str)      # (ordinal, status)
    done = Signal()

    def __init__(self, *, input_dir: str, output_dir: str, selection: str,
                 plugin_text: str, heading_regexes: dict, writer_factory,
                 parent=None) -> None:
        super().__init__(parent)
        self._input_dir = Path(input_dir)
        self._output_dir = Path(output_dir)
        self._selection = selection
        self._plugin_text = plugin_text
        self._heading_regexes = heading_regexes
        self._writer_factory = writer_factory
        self._stop = False

    def request_stop(self) -> None:
        self._stop = True

    def run(self) -> None:  # noqa: D401 - QThread entry point
        from horizon_tool.core.input_reader import read_script_content
        scripts, skipped = scan_input_folder(self._input_dir)
        scripts = filter_by_selection(scripts, self._selection)
        for s in skipped:
            self.log.emit(f"Bỏ qua {s.path.name}: {s.reason}")
        for script in scripts:
            if self._stop:
                self.log.emit("Đã dừng theo yêu cầu.")
                break
            self.progress.emit(script.ordinal, "Đang chạy")
            try:
                out_dir = self._output_dir / str(script.ordinal)
                out_dir.mkdir(parents=True, exist_ok=True)
                writer = self._writer_factory()
                outcome = process_script(
                    writer=writer, ordinal=script.ordinal, output_dir=out_dir,
                    plugin_text=self._plugin_text,
                    script_text=read_script_content(script.path),
                    heading_regexes=self._heading_regexes,
                )
                if outcome.missing_sections:
                    self.log.emit(
                        f"Kịch bản {script.ordinal}: thiếu {len(outcome.missing_sections)} section")
                self.progress.emit(script.ordinal, outcome.word_status)
                self.log.emit(f"Xong kịch bản {script.ordinal} -> {out_dir/str(script.ordinal)}.docx")
            except Exception as exc:  # noqa: BLE001 - one script must not stop the run
                self.progress.emit(script.ordinal, "Lỗi")
                self.log.emit(f"Lỗi kịch bản {script.ordinal}: {exc}")
        self.done.emit()
```

- [ ] **Step 6: Write the failing worker test**

```python
# horizon_tool/tests/test_script_run_worker.py
import pytest
import yaml
from pathlib import Path

pytest.importorskip("PySide6")
from PySide6.QtCore import QCoreApplication  # noqa: E402
from horizon_tool.gui.worker import ScriptRunWorker  # noqa: E402
from horizon_tool.automation.chatgpt import ScriptResult  # noqa: E402

FULL = """FULL STORY

CHAPTER ONE — X

Body. **twist.**

KEY SCENES + CONTINUITY NOTE

s

IMAGE PROMPT — 9:16

i

THUMBNAIL PROMPT — 16:9

t

VIDEO AI PROMPT

SHOT 1 — 3s

FACEBOOK TITLE

a. b.

FACEBOOK VIDEO DESCRIPTION

d

STORY TEASER

te

HASHTAGS

#a #b
"""


class FakeWriter:
    def write_script(self, plugin_text, script_text, runtime_suffix=""):
        return ScriptResult(raw_text=FULL)


def test_worker_processes_folder(qtbot, tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "1.txt").write_text("kịch bản 1", encoding="utf-8")
    (tmp_path / "in" / "2.txt").write_text("kịch bản 2", encoding="utf-8")
    out = tmp_path / "out"
    selectors = yaml.safe_load(
        Path("horizon_tool/config/selectors.yaml").read_text(encoding="utf-8"))

    worker = ScriptRunWorker(
        input_dir=str(tmp_path / "in"), output_dir=str(out), selection="",
        plugin_text="PLUGIN", heading_regexes=selectors["section_headings"],
        writer_factory=lambda: FakeWriter(),
    )
    with qtbot.waitSignal(worker.done, timeout=5000):
        worker.start()

    assert (out / "1" / "1.docx").exists()
    assert (out / "2" / "2.docx").exists()
    worker.wait(2000)
```

- [ ] **Step 7: Run the pipeline + worker tests, confirm pass.**

- [ ] **Step 8: Wire the real worker into `gui/main_window.py`**

Replace `on_start` so it runs the real pipeline when an input folder + plugin are chosen. Keep it defensive (show a message if inputs are missing). Add near the top of `main_window.py`:

```python
from horizon_tool.automation.browser import BrowserSession
from horizon_tool.automation.chatgpt import ChatGPTWriter
from horizon_tool.core.config_loader import load_yaml
from horizon_tool.core.plugin_manager import read_plugin_text, apply_variables
from horizon_tool.gui.worker import ScriptRunWorker

SELECTORS_PATH = Path(__file__).resolve().parents[1] / "config" / "selectors.yaml"
```

Replace the body of `on_start` with:

```python
    def on_start(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        input_dir = self.input_edit.text().strip()
        output_dir = self.output_edit.text().strip()
        plugin_path = self.plugin_combo.currentData()
        if not input_dir or not output_dir or not plugin_path:
            self.append_log("Hãy chọn thư mục input, output và plugin trước khi chạy.")
            return

        selectors = load_yaml(SELECTORS_PATH)
        plugin_text = apply_variables(
            read_plugin_text(Path(plugin_path)),
            {"VIDEO_DURATION": self.duration_combo.currentText(),
             "VIDEO_QUALITY": self.quality_combo.currentText()},
        )

        def writer_factory():
            account = self.account_manager.next_available("chatgpt")
            if account is None:
                raise RuntimeError("Không có tài khoản ChatGPT khả dụng.")
            session = BrowserSession(account.profile_dir, headless=False,
                                     element_timeout_ms=self.config.raw.get("timeouts", {}).get("element_wait_seconds", 30) * 1000)
            session.start()
            return ChatGPTWriter(session, selectors, self.config.raw)

        self.table.setRowCount(0)
        self.worker = ScriptRunWorker(
            input_dir=input_dir, output_dir=output_dir,
            selection=self.range_edit.text().strip(), plugin_text=plugin_text,
            heading_regexes=selectors["section_headings"],
            writer_factory=writer_factory, parent=self,
        )
        self.worker.log.connect(self.append_log)
        self.worker.progress.connect(self._on_progress)
        self.worker.done.connect(self._on_worker_done)
        self._set_running_state(True)
        self.worker.start()
```

Note: `self.worker` is now a `ScriptRunWorker` (has `.log/.progress/.done/.request_stop/.isRunning`), which is signal-compatible with the existing `_on_progress`, `_on_worker_done`, `_set_paused` (ScriptRunWorker has no `set_paused`; guard it) and `on_stop` handlers. Update `_set_paused` to no-op safely if the worker lacks `set_paused`:

```python
    def _set_paused(self, paused: bool) -> None:
        if self.worker is not None and hasattr(self.worker, "set_paused"):
            self.worker.set_paused(paused)
```

- [ ] **Step 9: Update the existing main-window run test** so it still passes. In `horizon_tool/tests/test_main_window.py`, `test_run_completes_and_returns_to_idle` calls `win.on_start()` with no folders set — with the new guard it will just log and not start a worker. Change that test to assert the guard message instead:

```python
def test_start_without_inputs_shows_message(qtbot):
    app = QApplication.instance() or QApplication([])
    win = MainWindow(AppConfig.load(CONFIG))
    qtbot.addWidget(win)
    win.on_start()  # no input/output/plugin selected
    assert "Hãy chọn thư mục input" in win.log_pane.toPlainText()
    assert win.worker is None
```

(Delete the old `test_run_completes_and_returns_to_idle`, which depended on the Phase-1 dummy worker; the stub is now covered by `test_worker.py` and the real path by `test_script_run_worker.py`.)

- [ ] **Step 10: Run the FULL suite, then a smoke check**

Run: `cd "D:/Home/wf" && horizon_tool/.venv/Scripts/python.exe -m pytest horizon_tool/tests -q` — expect all pass.

Smoke (offscreen; verifies the guard path without a browser):
```
QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 horizon_tool/.venv/Scripts/python.exe -c "import sys; from pathlib import Path; sys.path.insert(0, r'D:\Home\wf'); from PySide6.QtWidgets import QApplication; from horizon_tool.core.config_loader import AppConfig; from horizon_tool.gui.main_window import MainWindow; app=QApplication([]); w=MainWindow(AppConfig.load(Path(r'D:\Home\wf\horizon_tool\config\config.yaml'))); w.on_start(); print('guard log:', 'Hãy chọn' in w.log_pane.toPlainText()); app.processEvents()"
```
Expect: `guard log: True`.

- [ ] **Step 11: Commit**

```bash
cd "D:/Home/wf"
git add horizon_tool/core/pipeline.py horizon_tool/gui/worker.py horizon_tool/gui/main_window.py horizon_tool/tests/test_pipeline.py horizon_tool/tests/test_script_run_worker.py horizon_tool/tests/test_main_window.py
git commit -m "feat: script->Word pipeline and real GUI run worker wired to ChatGPT"
```

---

## Self-Review

**Spec coverage (Phase 3 = spec §16 item 3):**
- §7.2 script writing (new chat, plugin+script, send mode, runtime_suffix, CONTINUE loop, save conversation URL, raw_response.txt) → Task 4 + Task 5 (raw saved in pipeline) ✓
- §7.3 get result (docx link OR text; tool-built Word authoritative) → pipeline always builds the Word from parsed text; docx-link download is a stubbed `_try_download_docx` (returns None) to be completed when the live selector is known — noted, not silently dropped ✓
- §8.1 section split (9 sections, flexible headings, merge CONTINUE, strip PART markers, report missing) → Task 1 ✓
- §8.2 Word build (Calibri, Heading 1/2, real bold, uppercase FB title bold, monospace video prompt, no cover/TOC/header/footer) → Task 2 ✓
- §10 output folders/filenames/conflict policy, raw_response, log.txt, report.xlsx (reject highlight) → Task 3 ✓
- §14 state machine SCRIPT_WRITING → WORD_BUILT with done/failed per step → Task 5 (process_script + worker; a failed script never stops the run) ✓

**Deferred (intentional):** image render (Phase 4), Grok video (Phase 5), quota rotation + full Resume/state persistence (Phase 6), report row wiring into the live run + screenshot-on-error (Phase 6/7 — the ReportWriter exists and is tested now; the worker will populate it once account/error handling lands). The `_try_download_docx` and `_read_last_response` DOM selectors are placeholders tuned against live ChatGPT.

**Placeholder scan:** No TODO in code except the two clearly-marked live-DOM selectors in `chatgpt.py`, consistent with the design's selector-externalization requirement.

**Type consistency:** `ParsedSections` (sections/missing/story) used identically in parser, word_builder, pipeline. `ScriptResult` (raw_text/conversation_url/docx_path) returned by ChatGPTWriter and consumed by pipeline. `process_script(writer, ordinal, output_dir, plugin_text, script_text, heading_regexes, runtime_suffix)` signature matches the worker call. `ScriptRunWorker` signals (log/progress/done) match the main-window handlers.
