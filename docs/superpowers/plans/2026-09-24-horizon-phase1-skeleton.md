# Horizon X Media Tool — Phase 1 Implementation Plan (Skeleton, Config, Input, Plugin, Basic GUI)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a runnable, browser-free foundation: project skeleton, YAML config loading, input-folder reading (ordinal sort, encoding detection, range selection), plugin management (list/read/docx→markdown/hash/variable substitution), and a basic PySide6 GUI wired to config — with unit tests for all non-GUI logic.

**Architecture:** Logic modules under `horizon_tool/core/` are pure and unit-tested with pytest. The GUI (`horizon_tool/gui/`) is a thin PySide6 layer that consumes those modules and runs any long work on a worker `QThread`. Phase 1 ships a stub worker so Start/Pause/Stop wire up without freezing; the real pipeline lands in later phases.

**Tech Stack:** Python 3.11+ (dev on 3.10 acceptable, code kept 3.10-compatible), PySide6, python-docx, PyYAML, pytest, pytest-qt.

**Convention:** UI text/logs/report in Vietnamese; code identifiers, docstrings, comments in English.

---

### Task 0: Project skeleton, venv, dependencies

**Files:**
- Create: `horizon_tool/requirements.txt`
- Create: `horizon_tool/__init__.py`, `horizon_tool/core/__init__.py`, `horizon_tool/gui/__init__.py`, `horizon_tool/automation/__init__.py`, `horizon_tool/core/security/__init__.py`
- Create: `horizon_tool/config/.gitkeep`, `horizon_tool/plugins/.gitkeep`, `horizon_tool/tests/__init__.py`
- Create: `horizon_tool/README.md`

- [ ] **Step 1: Create the directory tree and package markers**

```bash
cd "D:/Home/wf/horizon_tool"
mkdir -p core/security gui automation config plugins tests
# package markers
: > __init__.py
: > core/__init__.py
: > core/security/__init__.py
: > gui/__init__.py
: > automation/__init__.py
: > tests/__init__.py
: > config/.gitkeep
: > plugins/.gitkeep
```

- [ ] **Step 2: Create `requirements.txt`**

```
# horizon_tool/requirements.txt
PySide6>=6.6
playwright>=1.40
python-docx>=1.1
openpyxl>=3.1
PyYAML>=6.0
cryptography>=42.0
pytest>=8.0
pytest-qt>=4.4
```

- [ ] **Step 3: Create a virtual environment and install deps**

Run:
```bash
cd "D:/Home/wf/horizon_tool"
python -m venv .venv
.venv/Scripts/python.exe -m pip install --upgrade pip
.venv/Scripts/python.exe -m pip install -r requirements.txt
```
Expected: all packages install without error. (Playwright browser binaries are installed later, Phase 2.)

- [ ] **Step 4: Create `README.md`**

```markdown
# Horizon X Media Tool

Desktop tool (Windows) batch-processing story scripts through ChatGPT + Grok
(logged-in browser, no API). See `docs/superpowers/specs/` for the design spec.

## Dev setup
    python -m venv .venv
    .venv/Scripts/python.exe -m pip install -r requirements.txt

## Run
    .venv/Scripts/python.exe main.py

## Tests
    .venv/Scripts/python.exe -m pytest -q
```

- [ ] **Step 5: Commit**

```bash
cd "D:/Home/wf"
git add horizon_tool/
git commit -m "chore: phase 1 project skeleton and dependencies"
```

---

### Task 1: Config loader (`config.yaml`, `selectors.yaml`)

**Files:**
- Create: `horizon_tool/config/config.yaml`
- Create: `horizon_tool/config/selectors.yaml`
- Create: `horizon_tool/core/config_loader.py`
- Test: `horizon_tool/tests/test_config_loader.py`

- [ ] **Step 1: Create `config/config.yaml`**

```yaml
# General runtime configuration. Values here drive GUI dropdowns and timing so
# the tool adapts to ChatGPT/Grok UI changes without touching code.

grok:
  durations: ["10s", "15s", "20s"]      # GUI "Thời lượng" dropdown
  qualities: ["720p", "1080p"]          # GUI "Chất lượng" dropdown
  render_timeout_seconds: 600           # wait up to 10 min for a Grok video
  motion_prompt_override: ""            # if set, used instead of section 5

chatgpt:
  send_mode: "two_messages"             # "combined" or "two_messages"
  runtime_suffix: ""                    # optional text appended after the script
  image_wrapper_9x16: "Generate an image in 9:16 vertical ratio based on this prompt:\n\n{PROMPT}"
  image_wrapper_16x9: "Generate an image in 16:9 horizontal ratio based on this prompt:\n\n{PROMPT}"

timeouts:
  element_wait_seconds: 30
  response_wait_seconds: 600

retry:
  max_attempts: 3
  backoff_base_seconds: 5               # backoff = base * 2**attempt

delays:
  between_steps_min_seconds: 2
  between_steps_max_seconds: 6
  between_scripts_min_seconds: 5
  between_scripts_max_seconds: 15

auto_resume:
  enabled: false
  check_interval_minutes: 30
```

- [ ] **Step 2: Create `config/selectors.yaml`**

```yaml
# CSS/XPath selectors and recognition regexes for ChatGPT and Grok.
# The UIs change often; edit this file (no code change needed) when they do.
# Selectors marked TODO must be verified against the real logged-in DOM.

chatgpt:
  url_new_chat: "https://chatgpt.com/"
  input_box: "div#prompt-textarea"          # TODO: kiểm tra selector thực tế
  send_button: "button[data-testid='send-button']"  # TODO: kiểm tra selector thực tế
  stop_button: "button[data-testid='stop-button']"  # TODO: kiểm tra selector thực tế
  assistant_message: "div[data-message-author-role='assistant']"  # TODO: kiểm tra selector thực tế
  file_download_link: "a[href*='sandbox']"  # TODO: kiểm tra selector thực tế
  generated_image: "img[alt*='Generated']"  # TODO: kiểm tra selector thực tế

grok:
  url_image_to_video: "https://grok.com/"   # TODO: kiểm tra selector thực tế
  image_upload_input: "input[type='file']"  # TODO: kiểm tra selector thực tế
  motion_prompt_box: "textarea"             # TODO: kiểm tra selector thực tế
  duration_control: ""                      # TODO: kiểm tra selector thực tế
  quality_control: ""                       # TODO: kiểm tra selector thực tế
  generate_button: ""                       # TODO: kiểm tra selector thực tế
  video_result: "video"                     # TODO: kiểm tra selector thực tế

# Recognition patterns (Python regex, case-insensitive at use site).
patterns:
  continue_marker: "\\[PART\\s+\\d+\\s+COMPLETE.*?CONTINUE.*?\\]"
  quota_exhausted:
    - "you've reached your.*limit"
    - "quota"
    - "try again later"
  policy_refusal:
    - "I can't help with that"
    - "against.*content policy"
    - "unable to generate this image"
  session_expired:
    - "log in"
    - "session expired"

# Section heading regexes (matched on a stripped line, IGNORECASE).
# Order = canonical section order (1..9).
section_headings:
  full_story: "^#*\\s*\\**\\s*(\\d+[\\.\\)]\\s*)?FULL STORY"
  key_scenes: "^#*\\s*\\**\\s*(\\d+[\\.\\)]\\s*)?KEY SCENES"
  image_9x16: "^#*\\s*\\**\\s*(\\d+[\\.\\)]\\s*)?IMAGE PROMPT"
  thumbnail_16x9: "^#*\\s*\\**\\s*(\\d+[\\.\\)]\\s*)?THUMBNAIL"
  video_prompt: "^#*\\s*\\**\\s*(\\d+[\\.\\)]\\s*)?VIDEO AI PROMPT"
  fb_title: "^#*\\s*\\**\\s*(\\d+[\\.\\)]\\s*)?FACEBOOK TITLE"
  fb_description: "^#*\\s*\\**\\s*(\\d+[\\.\\)]\\s*)?FACEBOOK VIDEO DESCRIPTION"
  story_teaser: "^#*\\s*\\**\\s*(\\d+[\\.\\)]\\s*)?STORY TEASER"
  hashtags: "^#*\\s*\\**\\s*(\\d+[\\.\\)]\\s*)?HASHTAGS"
```

- [ ] **Step 3: Write the failing test**

```python
# horizon_tool/tests/test_config_loader.py
from pathlib import Path

from horizon_tool.core.config_loader import load_yaml, AppConfig

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"


def test_load_yaml_reads_mapping():
    data = load_yaml(CONFIG_DIR / "config.yaml")
    assert isinstance(data, dict)
    assert data["grok"]["durations"] == ["10s", "15s", "20s"]


def test_appconfig_exposes_gui_values():
    cfg = AppConfig.load(CONFIG_DIR / "config.yaml")
    assert cfg.video_durations == ["10s", "15s", "20s"]
    assert cfg.video_qualities == ["720p", "1080p"]
    assert cfg.send_mode == "two_messages"
    assert cfg.runtime_suffix == ""


def test_load_yaml_missing_file_raises():
    import pytest
    with pytest.raises(FileNotFoundError):
        load_yaml(CONFIG_DIR / "does_not_exist.yaml")
```

- [ ] **Step 4: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest horizon_tool/tests/test_config_loader.py -v`
Expected: FAIL — `ModuleNotFoundError: horizon_tool.core.config_loader`.
(Run pytest from `D:/Home/wf` so `horizon_tool` is importable; add `conftest.py` in Step 6 if needed.)

- [ ] **Step 5: Implement `core/config_loader.py`**

```python
# horizon_tool/core/config_loader.py
"""Load and expose YAML configuration for the tool."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


def load_yaml(path: Path) -> dict[str, Any]:
    """Read a YAML file into a dict. Raises FileNotFoundError if missing."""
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config root must be a mapping: {path}")
    return data


@dataclass
class AppConfig:
    """Typed view over config.yaml for the values the GUI and pipeline need."""

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
```

- [ ] **Step 6: Add `conftest.py` so `horizon_tool` imports during tests**

```python
# horizon_tool/tests/conftest.py
import sys
from pathlib import Path

# Make the repo root (parent of the horizon_tool package) importable.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
```

- [ ] **Step 7: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest horizon_tool/tests/test_config_loader.py -v`
Expected: 3 passed.

- [ ] **Step 8: Commit**

```bash
cd "D:/Home/wf"
git add horizon_tool/config horizon_tool/core/config_loader.py horizon_tool/tests/test_config_loader.py horizon_tool/tests/conftest.py
git commit -m "feat: config loader with config.yaml and selectors.yaml"
```

---

### Task 2: Input reader — text encoding detection

**Files:**
- Create: `horizon_tool/core/input_reader.py`
- Test: `horizon_tool/tests/test_input_reader_encoding.py`

- [ ] **Step 1: Write the failing test**

```python
# horizon_tool/tests/test_input_reader_encoding.py
from horizon_tool.core.input_reader import read_text_file


def test_reads_utf8(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("Xin chào thế giới", encoding="utf-8")
    assert read_text_file(p) == "Xin chào thế giới"


def test_reads_utf8_bom(tmp_path):
    p = tmp_path / "b.txt"
    p.write_text("Nội dung", encoding="utf-8-sig")
    assert read_text_file(p) == "Nội dung"


def test_reads_utf16(tmp_path):
    p = tmp_path / "c.txt"
    p.write_text("Kịch bản", encoding="utf-16")
    assert read_text_file(p) == "Kịch bản"


def test_reads_cp1258(tmp_path):
    p = tmp_path / "d.txt"
    p.write_bytes("Tiếng Việt".encode("cp1258"))
    assert read_text_file(p) == "Tiếng Việt"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest horizon_tool/tests/test_input_reader_encoding.py -v`
Expected: FAIL — `ModuleNotFoundError` / `read_text_file` not defined.

- [ ] **Step 3: Implement encoding detection in `core/input_reader.py`**

```python
# horizon_tool/core/input_reader.py
"""Read and enumerate input scripts from a folder."""
from __future__ import annotations

from pathlib import Path

# Tried in order. utf-8-sig also decodes plain UTF-8; utf-16 catches BOM'd
# UTF-16; cp1258 is a single-byte last resort that rarely fails.
_ENCODINGS = ("utf-8-sig", "utf-16", "utf-8", "cp1258")


def read_text_file(path: Path) -> str:
    """Read a .txt file, auto-detecting a supported encoding."""
    raw = path.read_bytes()
    for enc in _ENCODINGS:
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise ValueError(f"Cannot decode text file with known encodings: {path}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest horizon_tool/tests/test_input_reader_encoding.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
cd "D:/Home/wf"
git add horizon_tool/core/input_reader.py horizon_tool/tests/test_input_reader_encoding.py
git commit -m "feat: input reader text encoding detection"
```

---

### Task 3: Input reader — ordinal extraction and docx reading

**Files:**
- Modify: `horizon_tool/core/input_reader.py`
- Test: `horizon_tool/tests/test_input_reader_ordinal.py`

- [ ] **Step 1: Write the failing test**

```python
# horizon_tool/tests/test_input_reader_ordinal.py
import docx

from horizon_tool.core.input_reader import extract_ordinal, read_docx_file, read_script_content


def test_extract_ordinal_plain_number():
    assert extract_ordinal("1.txt") == 1


def test_extract_ordinal_with_words():
    assert extract_ordinal("Kịch bản 12.docx") == 12


def test_extract_ordinal_uses_last_number():
    assert extract_ordinal("2024_scene_5.txt") == 5


def test_extract_ordinal_none_when_absent():
    assert extract_ordinal("intro.txt") is None


def test_read_docx_file(tmp_path):
    p = tmp_path / "5.docx"
    d = docx.Document()
    d.add_paragraph("Dòng một")
    d.add_paragraph("Dòng hai")
    d.save(p)
    assert read_docx_file(p) == "Dòng một\nDòng hai"


def test_read_script_content_dispatches_by_suffix(tmp_path):
    t = tmp_path / "3.txt"
    t.write_text("nội dung txt", encoding="utf-8")
    assert read_script_content(t) == "nội dung txt"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest horizon_tool/tests/test_input_reader_ordinal.py -v`
Expected: FAIL — `extract_ordinal` / `read_docx_file` not defined.

- [ ] **Step 3: Add ordinal + docx functions to `core/input_reader.py`**

```python
# append to horizon_tool/core/input_reader.py
import re

import docx  # python-docx

_NUMBER_RE = re.compile(r"\d+")


def extract_ordinal(filename: str) -> int | None:
    """Return the last integer sequence in the filename stem, or None."""
    stem = Path(filename).stem
    matches = _NUMBER_RE.findall(stem)
    return int(matches[-1]) if matches else None


def read_docx_file(path: Path) -> str:
    """Read a .docx file into plain text, one paragraph per line."""
    document = docx.Document(str(path))
    return "\n".join(p.text for p in document.paragraphs)


def read_script_content(path: Path) -> str:
    """Read a script file by extension (.txt or .docx)."""
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return read_text_file(path)
    if suffix == ".docx":
        return read_docx_file(path)
    raise ValueError(f"Unsupported script file type: {path.suffix}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest horizon_tool/tests/test_input_reader_ordinal.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
cd "D:/Home/wf"
git add horizon_tool/core/input_reader.py horizon_tool/tests/test_input_reader_ordinal.py
git commit -m "feat: ordinal extraction and docx script reading"
```

---

### Task 4: Input reader — folder scan, skipping, and range/list selection

**Files:**
- Modify: `horizon_tool/core/input_reader.py`
- Test: `horizon_tool/tests/test_input_reader_scan.py`

- [ ] **Step 1: Write the failing test**

```python
# horizon_tool/tests/test_input_reader_scan.py
from horizon_tool.core.input_reader import scan_input_folder, filter_by_selection


def test_scan_sorts_numerically_and_skips_invalid(tmp_path):
    (tmp_path / "2.txt").write_text("two", encoding="utf-8")
    (tmp_path / "10.txt").write_text("ten", encoding="utf-8")
    (tmp_path / "1.txt").write_text("one", encoding="utf-8")
    (tmp_path / "empty.txt").write_text("", encoding="utf-8")      # empty -> skip
    (tmp_path / "notes.txt").write_text("no number", encoding="utf-8")  # no ordinal -> skip
    (tmp_path / "readme.md").write_text("ignored", encoding="utf-8")    # wrong ext -> ignored

    scripts, skipped = scan_input_folder(tmp_path)

    assert [s.ordinal for s in scripts] == [1, 2, 10]  # numeric, not lexicographic
    skipped_names = {s.path.name for s in skipped}
    assert "empty.txt" in skipped_names
    assert "notes.txt" in skipped_names
    assert "readme.md" not in skipped_names  # non txt/docx never considered


def test_filter_by_selection_range():
    class S:
        def __init__(self, o): self.ordinal = o
    items = [S(1), S(2), S(5), S(7), S(20)]
    picked = filter_by_selection(items, "5-20")
    assert [s.ordinal for s in picked] == [5, 7, 20]


def test_filter_by_selection_list():
    class S:
        def __init__(self, o): self.ordinal = o
    items = [S(1), S(3), S(7), S(9)]
    picked = filter_by_selection(items, "3,7,9")
    assert [s.ordinal for s in picked] == [3, 7, 9]


def test_filter_by_selection_empty_returns_all():
    class S:
        def __init__(self, o): self.ordinal = o
    items = [S(1), S(2)]
    assert filter_by_selection(items, "") == items
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest horizon_tool/tests/test_input_reader_scan.py -v`
Expected: FAIL — `scan_input_folder` / `filter_by_selection` not defined.

- [ ] **Step 3: Add scan + selection to `core/input_reader.py`**

```python
# append to horizon_tool/core/input_reader.py
from dataclasses import dataclass

_SUPPORTED_SUFFIXES = {".txt", ".docx"}


@dataclass
class ScriptFile:
    """A valid input script with its ordinal number."""
    ordinal: int
    path: Path

    @property
    def filename(self) -> str:
        return self.path.name


@dataclass
class SkippedFile:
    """An input file that was skipped, with a Vietnamese reason for the log."""
    path: Path
    reason: str


def scan_input_folder(folder: Path) -> tuple[list[ScriptFile], list[SkippedFile]]:
    """Scan a folder for .txt/.docx scripts.

    Returns valid scripts sorted by ordinal ascending, plus skipped files with
    reasons. Files without an ordinal, empty, or unreadable are skipped, never
    raised. Files with unsupported extensions are ignored entirely.
    """
    scripts: list[ScriptFile] = []
    skipped: list[SkippedFile] = []

    for path in folder.iterdir():
        if not path.is_file() or path.suffix.lower() not in _SUPPORTED_SUFFIXES:
            continue
        ordinal = extract_ordinal(path.name)
        if ordinal is None:
            skipped.append(SkippedFile(path, "Không có số thứ tự trong tên file"))
            continue
        try:
            content = read_script_content(path)
        except Exception as exc:  # noqa: BLE001 - report, never halt
            skipped.append(SkippedFile(path, f"Không đọc được file: {exc}"))
            continue
        if not content.strip():
            skipped.append(SkippedFile(path, "File rỗng"))
            continue
        scripts.append(ScriptFile(ordinal=ordinal, path=path))

    scripts.sort(key=lambda s: s.ordinal)
    return scripts, skipped


def _parse_selection(selection: str) -> set[int] | None:
    """Parse '5-20' / '3,7,9' / '1-3,7' into a set; '' -> None (all)."""
    selection = selection.strip()
    if not selection:
        return None
    wanted: set[int] = set()
    for part in selection.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo_s, hi_s = part.split("-", 1)
            lo, hi = int(lo_s), int(hi_s)
            wanted.update(range(min(lo, hi), max(lo, hi) + 1))
        else:
            wanted.add(int(part))
    return wanted


def filter_by_selection(scripts: list, selection: str) -> list:
    """Filter items exposing `.ordinal` by a selection string; '' returns all."""
    wanted = _parse_selection(selection)
    if wanted is None:
        return scripts
    return [s for s in scripts if s.ordinal in wanted]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest horizon_tool/tests/test_input_reader_scan.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
cd "D:/Home/wf"
git add horizon_tool/core/input_reader.py horizon_tool/tests/test_input_reader_scan.py
git commit -m "feat: input folder scan with skipping and range/list selection"
```

---

### Task 5: Plugin manager — list and read plugins

**Files:**
- Create: `horizon_tool/core/plugin_manager.py`
- Test: `horizon_tool/tests/test_plugin_manager.py`

- [ ] **Step 1: Write the failing test**

```python
# horizon_tool/tests/test_plugin_manager.py
import docx

from horizon_tool.core.plugin_manager import (
    list_plugins, read_plugin_text, plugin_hash, apply_variables,
)


def test_list_plugins_finds_supported(tmp_path):
    (tmp_path / "v11.txt").write_text("prompt", encoding="utf-8")
    (tmp_path / "v12.md").write_text("prompt", encoding="utf-8")
    (tmp_path / "v13.docx").write_text("x", encoding="utf-8")  # placeholder, not read here
    (tmp_path / "notes.pdf").write_text("ignore", encoding="utf-8")
    (tmp_path / "_history").mkdir()  # excluded

    names = sorted(p.name for p in list_plugins(tmp_path))
    assert names == ["v11.txt", "v12.md", "v13.docx"]


def test_read_txt_plugin(tmp_path):
    p = tmp_path / "p.txt"
    p.write_text("Line one\nLine two", encoding="utf-8")
    assert read_plugin_text(p) == "Line one\nLine two"


def test_read_docx_plugin_to_markdown(tmp_path):
    p = tmp_path / "p.docx"
    d = docx.Document()
    d.add_heading("MAIN TITLE", level=1)
    para = d.add_paragraph()
    run = para.add_run("bold part")
    run.bold = True
    d.add_paragraph("plain text")
    d.save(p)

    text = read_plugin_text(p)
    assert "# MAIN TITLE" in text
    assert "**bold part**" in text
    assert "plain text" in text


def test_plugin_hash_stable_and_sensitive():
    h1 = plugin_hash("abc")
    h2 = plugin_hash("abc")
    h3 = plugin_hash("abd")
    assert h1 == h2 and h1 != h3
    assert len(h1) == 64  # sha256 hex


def test_apply_variables_replaces_known_and_leaves_rest():
    text = "Length {VIDEO_DURATION}, quality {VIDEO_QUALITY}, keep {OTHER}"
    out = apply_variables(text, {"VIDEO_DURATION": "15s", "VIDEO_QUALITY": "1080p"})
    assert out == "Length 15s, quality 1080p, keep {OTHER}"


def test_apply_variables_no_placeholder_is_verbatim():
    text = "No variables here."
    assert apply_variables(text, {"VIDEO_DURATION": "15s"}) == text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest horizon_tool/tests/test_plugin_manager.py -v`
Expected: FAIL — `ModuleNotFoundError: horizon_tool.core.plugin_manager`.

- [ ] **Step 3: Implement `core/plugin_manager.py`**

```python
# horizon_tool/core/plugin_manager.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest horizon_tool/tests/test_plugin_manager.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
cd "D:/Home/wf"
git add horizon_tool/core/plugin_manager.py horizon_tool/tests/test_plugin_manager.py
git commit -m "feat: plugin manager (list, read, docx->markdown, hash, variables)"
```

---

### Task 6: GUI worker-thread stub (decouple long work from GUI)

**Files:**
- Create: `horizon_tool/gui/worker.py`
- Test: `horizon_tool/tests/test_worker.py`

- [ ] **Step 1: Write the failing test**

```python
# horizon_tool/tests/test_worker.py
import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QCoreApplication  # noqa: E402
from horizon_tool.gui.worker import PipelineWorker  # noqa: E402


def test_worker_emits_log_and_finished(qtbot):
    app = QCoreApplication.instance() or QCoreApplication([])
    worker = PipelineWorker(scripts=[1, 2, 3])
    logs: list[str] = []
    worker.log.connect(logs.append)

    with qtbot.waitSignal(worker.finished, timeout=3000):
        worker.start()

    assert any("Giai đoạn 1" in m for m in logs)
    assert worker.processed == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest horizon_tool/tests/test_worker.py -v`
Expected: FAIL — `ModuleNotFoundError: horizon_tool.gui.worker`.

- [ ] **Step 3: Implement `gui/worker.py`**

```python
# horizon_tool/gui/worker.py
"""Background worker thread. Phase 1 stub: proves threading + signal wiring
without any browser automation. Replaced by the real pipeline in later phases.
"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal


class PipelineWorker(QThread):
    """Runs script processing off the GUI thread. Cooperative pause/stop."""

    log = Signal(str)                 # a line for the live log pane
    progress = Signal(int, str)       # (ordinal, status text) for the table
    finished = Signal()               # emitted when the run ends

    def __init__(self, scripts: list[int], parent=None) -> None:
        super().__init__(parent)
        self._scripts = scripts
        self._stop = False
        self._paused = False
        self.processed = 0

    def request_stop(self) -> None:
        self._stop = True

    def set_paused(self, paused: bool) -> None:
        self._paused = paused

    def run(self) -> None:  # noqa: D401 - QThread entry point
        self.log.emit("Giai đoạn 1 — pipeline chưa được nối (bản khung).")
        for ordinal in self._scripts:
            if self._stop:
                self.log.emit("Đã dừng theo yêu cầu.")
                break
            while self._paused and not self._stop:
                self.msleep(100)
            self.progress.emit(ordinal, "Xong (giả lập)")
            self.log.emit(f"Đã xử lý (giả lập) kịch bản {ordinal}.")
            self.processed += 1
        self.finished.emit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest horizon_tool/tests/test_worker.py -v`
Expected: 1 passed. (Requires `pytest-qt`, already in requirements.)

- [ ] **Step 5: Commit**

```bash
cd "D:/Home/wf"
git add horizon_tool/gui/worker.py horizon_tool/tests/test_worker.py
git commit -m "feat: background pipeline worker stub with cooperative pause/stop"
```

---

### Task 7: Main window GUI (assembled from config + modules)

**Files:**
- Create: `horizon_tool/gui/main_window.py`
- Test: `horizon_tool/tests/test_main_window.py`

- [ ] **Step 1: Write the failing test**

```python
# horizon_tool/tests/test_main_window.py
import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402
from horizon_tool.core.config_loader import AppConfig  # noqa: E402
from horizon_tool.gui.main_window import MainWindow  # noqa: E402
from pathlib import Path  # noqa: E402

CONFIG = Path(__file__).resolve().parents[1] / "config" / "config.yaml"


def test_main_window_builds_and_populates(qtbot):
    app = QApplication.instance() or QApplication([])
    cfg = AppConfig.load(CONFIG)
    win = MainWindow(cfg)
    qtbot.addWidget(win)

    # Grok dropdowns populated from config
    durations = [win.duration_combo.itemText(i) for i in range(win.duration_combo.count())]
    assert durations == ["10s", "15s", "20s"]
    qualities = [win.quality_combo.itemText(i) for i in range(win.quality_combo.count())]
    assert qualities == ["720p", "1080p"]

    # Per-step checkboxes exist and default checked
    assert win.step_script.isChecked()
    assert win.step_img_9x16.isChecked()
    assert win.step_thumb_16x9.isChecked()
    assert win.step_video.isChecked()

    # Control buttons exist
    assert win.start_btn is not None
    assert win.stop_btn is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest horizon_tool/tests/test_main_window.py -v`
Expected: FAIL — `ModuleNotFoundError: horizon_tool.gui.main_window`.

- [ ] **Step 3: Implement `gui/main_window.py`**

```python
# horizon_tool/gui/main_window.py
"""Main application window (Phase 1 skeleton).

Vietnamese UI. Wires config-driven dropdowns, folder pickers, plugin dropdown,
per-step checkboxes, control buttons, a progress table, a live log pane, and
statistics. Long work runs on PipelineWorker so the GUI never freezes.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QLineEdit, QPushButton, QComboBox, QCheckBox, QPlainTextEdit,
    QTableWidget, QTableWidgetItem, QFileDialog, QGroupBox,
)

from horizon_tool.core.config_loader import AppConfig
from horizon_tool.core.plugin_manager import list_plugins
from horizon_tool.gui.worker import PipelineWorker

PLUGINS_DIR = Path(__file__).resolve().parents[1] / "plugins"
STEP_COLUMNS = ["STT", "Tên file", "Kịch bản", "Ảnh 9:16", "Ảnh 16:9", "Video"]


class MainWindow(QMainWindow):
    """Top-level window assembling all Phase 1 controls."""

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.config = config
        self.worker: PipelineWorker | None = None
        self.setWindowTitle("Horizon X Media Tool")
        self.resize(1100, 720)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        root.addWidget(self._build_io_group())
        root.addWidget(self._build_options_group())
        root.addWidget(self._build_controls())
        root.addWidget(self._build_progress_table(), stretch=2)
        root.addWidget(self._build_log_pane(), stretch=1)
        root.addWidget(self._build_stats())

        self.refresh_plugins()

    # ----- builders -------------------------------------------------------
    def _build_io_group(self) -> QGroupBox:
        box = QGroupBox("Thư mục")
        grid = QGridLayout(box)
        self.input_edit = QLineEdit()
        self.output_edit = QLineEdit()
        in_btn = QPushButton("Chọn…")
        out_btn = QPushButton("Chọn…")
        in_btn.clicked.connect(lambda: self._pick_folder(self.input_edit))
        out_btn.clicked.connect(lambda: self._pick_folder(self.output_edit))
        grid.addWidget(QLabel("Thư mục input:"), 0, 0)
        grid.addWidget(self.input_edit, 0, 1)
        grid.addWidget(in_btn, 0, 2)
        grid.addWidget(QLabel("Thư mục output:"), 1, 0)
        grid.addWidget(self.output_edit, 1, 1)
        grid.addWidget(out_btn, 1, 2)
        grid.addWidget(QLabel("Phạm vi (vd 5-20 hoặc 3,7,9):"), 2, 0)
        self.range_edit = QLineEdit()
        grid.addWidget(self.range_edit, 2, 1)
        return box

    def _build_options_group(self) -> QGroupBox:
        box = QGroupBox("Plugin & tùy chọn video")
        layout = QHBoxLayout(box)
        self.plugin_combo = QComboBox()
        reload_btn = QPushButton("Tải lại")
        open_btn = QPushButton("Mở file")
        reload_btn.clicked.connect(self.refresh_plugins)
        layout.addWidget(QLabel("Plugin:"))
        layout.addWidget(self.plugin_combo, stretch=1)
        layout.addWidget(open_btn)
        layout.addWidget(reload_btn)

        self.duration_combo = QComboBox()
        self.duration_combo.addItems(self.config.video_durations)
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(self.config.video_qualities)
        layout.addWidget(QLabel("Thời lượng:"))
        layout.addWidget(self.duration_combo)
        layout.addWidget(QLabel("Chất lượng:"))
        layout.addWidget(self.quality_combo)

        self.step_script = QCheckBox("Viết kịch bản")
        self.step_img_9x16 = QCheckBox("Ảnh 9:16")
        self.step_thumb_16x9 = QCheckBox("Thumbnail 16:9")
        self.step_video = QCheckBox("Video")
        for cb in (self.step_script, self.step_img_9x16, self.step_thumb_16x9, self.step_video):
            cb.setChecked(True)
            layout.addWidget(cb)
        return box

    def _build_controls(self) -> QWidget:
        w = QWidget()
        layout = QHBoxLayout(w)
        self.start_btn = QPushButton("Start")
        self.pause_btn = QPushButton("Pause")
        self.resume_btn = QPushButton("Resume")
        self.stop_btn = QPushButton("Stop")
        self.accounts_btn = QPushButton("Quản lý tài khoản")
        self.settings_btn = QPushButton("Cài đặt")
        self.start_btn.clicked.connect(self.on_start)
        self.pause_btn.clicked.connect(lambda: self._set_paused(True))
        self.resume_btn.clicked.connect(lambda: self._set_paused(False))
        self.stop_btn.clicked.connect(self.on_stop)
        for b in (self.start_btn, self.pause_btn, self.resume_btn, self.stop_btn,
                  self.accounts_btn, self.settings_btn):
            layout.addWidget(b)
        return w

    def _build_progress_table(self) -> QTableWidget:
        self.table = QTableWidget(0, len(STEP_COLUMNS))
        self.table.setHorizontalHeaderLabels(STEP_COLUMNS)
        return self.table

    def _build_log_pane(self) -> QPlainTextEdit:
        self.log_pane = QPlainTextEdit()
        self.log_pane.setReadOnly(True)
        return self.log_pane

    def _build_stats(self) -> QLabel:
        self.stats_label = QLabel("Tổng: 0 | Xong: 0 | Bỏ qua: 0 | Lỗi: 0")
        return self.stats_label

    # ----- behavior -------------------------------------------------------
    def refresh_plugins(self) -> None:
        self.plugin_combo.clear()
        for p in list_plugins(PLUGINS_DIR):
            self.plugin_combo.addItem(p.name, userData=str(p))

    def _pick_folder(self, target: QLineEdit) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục")
        if folder:
            target.setText(folder)

    def append_log(self, message: str) -> None:
        self.log_pane.appendPlainText(message)

    def on_start(self) -> None:
        # Phase 1: run the stub worker over a dummy list to prove wiring.
        self.worker = PipelineWorker(scripts=[1, 2, 3])
        self.worker.log.connect(self.append_log)
        self.worker.start()

    def _set_paused(self, paused: bool) -> None:
        if self.worker is not None:
            self.worker.set_paused(paused)

    def on_stop(self) -> None:
        if self.worker is not None:
            self.worker.request_stop()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest horizon_tool/tests/test_main_window.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
cd "D:/Home/wf"
git add horizon_tool/gui/main_window.py horizon_tool/tests/test_main_window.py
git commit -m "feat: main window GUI skeleton wired to config and plugins"
```

---

### Task 8: Application entry point + full test run

**Files:**
- Create: `horizon_tool/main.py`
- Test: manual smoke run + full pytest.

- [ ] **Step 1: Implement `main.py`**

```python
# horizon_tool/main.py
"""Application entry point."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

# Allow running as `python main.py` from inside horizon_tool/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from horizon_tool.core.config_loader import AppConfig  # noqa: E402
from horizon_tool.gui.main_window import MainWindow  # noqa: E402

CONFIG_PATH = Path(__file__).resolve().parent / "config" / "config.yaml"


def main() -> int:
    app = QApplication(sys.argv)
    config = AppConfig.load(CONFIG_PATH)
    window = MainWindow(config)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run the full test suite**

Run: `cd "D:/Home/wf" && horizon_tool/.venv/Scripts/python.exe -m pytest horizon_tool/tests -q`
Expected: all tests pass (config, encoding, ordinal, scan, plugin, worker, main window).

- [ ] **Step 3: Manual GUI smoke test**

Run: `cd "D:/Home/wf/horizon_tool" && .venv/Scripts/python.exe main.py`
Expected: window opens; Grok dropdowns show 10s/15s/20s and 720p/1080p; plugin dropdown lists any files in `plugins/`; clicking Start appends "Giai đoạn 1 — pipeline chưa được nối" and three simulated lines to the log; GUI stays responsive. Close the window to exit.

- [ ] **Step 4: Commit**

```bash
cd "D:/Home/wf"
git add horizon_tool/main.py
git commit -m "feat: application entry point and Phase 1 wiring"
```

---

## Self-Review

**Spec coverage (Phase 1 scope = spec §16 item 1):**
- Skeleton + config → Task 0, Task 1 ✓ (config.yaml + selectors.yaml, IN/OUT config-driven)
- Input reading IN-01..IN-05 → Tasks 2–4 ✓ (txt+docx, ordinal numeric sort, range/list, skip invalid, encoding UTF-8/BOM/UTF-16/cp1258)
- Plugin management PL-01/PL-02/PL-05/PL-06 + docx→markdown → Task 5 ✓ (PL-03 hot-reload-per-script and PL-04 open/preview/PL-07 editor are wired minimally in GUI now; full per-script reload lands in Phase 3 pipeline, editor+history in Phase 8 — noted, not silently dropped)
- Basic GUI (folders, plugin dropdown+reload, Grok options from config, per-step checkboxes, Start/Pause/Resume/Stop, progress table, live log, stats, buttons to accounts/settings) → Tasks 6–8 ✓
- Threading (logic decoupled from GUI, worker thread) → Task 6 ✓

**Deferred to later phases (intentional, in spec order):** browser core & accounts (Phase 2); ChatGPT/section/Word/report (Phase 3); images (Phase 4); Grok video (Phase 5); quota/resume/state (Phase 6); full error handling (Phase 7); security & plugin editor/history (Phase 8); packaging (Phase 9). The "Mở file / Sửa / Xem trước" plugin buttons and accounts/settings windows are present as controls now and fully implemented in their phases.

**Placeholder scan:** No TBD/TODO in code steps except intentional `# TODO: kiểm tra selector thực tế` markers in `selectors.yaml` (a design requirement). Every code step shows complete code.

**Type consistency:** `AppConfig.load()`, `list_plugins() -> list[Path]`, `scan_input_folder() -> (list[ScriptFile], list[SkippedFile])`, `filter_by_selection()`, `PipelineWorker(scripts=...)` with signals `log`/`progress`/`finished` — names used consistently across tasks and the GUI.
