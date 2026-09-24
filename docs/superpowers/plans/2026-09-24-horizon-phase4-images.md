# Horizon X Media Tool — Phase 4 Implementation Plan (ChatGPT image render 9:16 & 16:9 + refusal detection)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** After the Word file is built, render the 9:16 image (from section 3) and the 16:9 thumbnail (from section 4) via ChatGPT, download each to the script's output folder, and detect policy refusals — on refusal, skip immediately (no retry), mark "Bị từ chối", log, and continue. Wire the two image steps into the run pipeline and the progress table.

**Architecture:** A shared status-constants module removes string duplication. Refusal detection and the render-decision (refuse → rejected vs. proceed → download) are pure and unit-tested. `ChatGPTWriter.render_image` is thin DOM glue over that pure core, using YAML selectors (placeholders, tuned live). The pipeline gains `render_images`, and `ScriptRunWorker` emits a per-step status the main window maps to the correct progress column.

**Tech Stack:** Python 3.10-compatible, Playwright, python-docx, PySide6, pytest.

**Convention:** UI/log/report text Vietnamese; code identifiers/docstrings/comments English.

**Base branch:** `main`. Work branch: `phase-4-images`.

**Verified preconditions:** `config.yaml` has `chatgpt.image_wrapper_9x16` / `image_wrapper_16x9` (with `{PROMPT}`); `selectors.yaml` has `patterns.policy_refusal` (list) and `chatgpt.generated_image`.

**Honesty note:** Refusal detection, the render-decision core, and the pipeline/worker wiring are fully tested with fakes. The actual DOM steps (send prompt in a new chat, wait for the image to finish, download the highest-resolution original) need the live ChatGPT UI and stay behind YAML selectors marked `# TODO: kiểm tra selector thực tế`.

---

### Task 1: Shared statuses + image refusal detection + render core + ChatGPTWriter.render_image

**Files:**
- Create: `horizon_tool/core/statuses.py`
- Modify: `horizon_tool/core/report.py` (import STATUS_REJECTED from statuses; keep re-export)
- Modify: `horizon_tool/automation/chatgpt.py` (add detect_refusal, resolve_image, ImageRenderResult, ChatGPTWriter.render_image)
- Test: `horizon_tool/tests/test_image_render.py`, `horizon_tool/tests/test_statuses.py`

- [ ] **Step 1: Create `core/statuses.py`**

```python
"""Shared per-step status strings (Vietnamese, shown in table + report)."""
from __future__ import annotations

STATUS_PENDING = "Chờ"
STATUS_RUNNING = "Đang chạy"
STATUS_DONE = "Xong"
STATUS_SKIPPED = "Bỏ qua"
STATUS_REJECTED = "Bị từ chối"
STATUS_FAILED = "Lỗi"
```

- [ ] **Step 2: Point `report.py` at the shared constant**

In `horizon_tool/core/report.py`, replace the line `STATUS_REJECTED = "Bị từ chối"` with:

```python
from horizon_tool.core.statuses import STATUS_REJECTED  # re-exported for callers
```

(Keep everything else in report.py unchanged. `test_report.py` imports `STATUS_REJECTED` from `report` — the re-export keeps that working.)

- [ ] **Step 3: Write the failing tests**

```python
# horizon_tool/tests/test_statuses.py
from horizon_tool.core import statuses
from horizon_tool.core.report import STATUS_REJECTED as REPORT_REJECTED


def test_report_reexports_shared_rejected():
    assert REPORT_REJECTED == statuses.STATUS_REJECTED == "Bị từ chối"
```

```python
# horizon_tool/tests/test_image_render.py
from horizon_tool.automation.chatgpt import (
    detect_refusal, resolve_image, ImageRenderResult,
)
from horizon_tool.core.statuses import STATUS_DONE, STATUS_REJECTED

REFUSALS = ["I can't help with that", "against.*content policy",
            "unable to generate this image"]


def test_detect_refusal_matches_patterns():
    assert detect_refusal("Sorry, I can't help with that.", REFUSALS)
    assert detect_refusal("This is against our content policy here", REFUSALS)
    assert not detect_refusal("Here is your image!", REFUSALS)


def test_resolve_image_rejects_without_downloading():
    calls = []
    def download():
        calls.append(True)
        return "should-not-be-called.png"
    result = resolve_image("Sorry, I can't help with that.", REFUSALS, download)
    assert result.status == STATUS_REJECTED
    assert result.path is None
    assert calls == []  # never downloaded on refusal (no retry, skip)


def test_resolve_image_downloads_when_ok():
    result = resolve_image("Here is your image!", REFUSALS, lambda: "out/1_9x16.png")
    assert result.status == STATUS_DONE
    assert result.path == "out/1_9x16.png"
```

- [ ] **Step 4: Run tests, confirm FAIL.**

- [ ] **Step 5: Add image code to `automation/chatgpt.py`**

Add near the top imports:

```python
from horizon_tool.core.statuses import STATUS_DONE, STATUS_FAILED, STATUS_REJECTED
```

Add these after `should_continue` (module-level), the dataclass near `ScriptResult`, and the method inside `ChatGPTWriter`:

```python
# --- module level ---
def detect_refusal(response_text: str, refusal_patterns: list[str]) -> bool:
    """True if the response matches any policy-refusal pattern (case-insensitive)."""
    return any(
        re.search(p, response_text, flags=re.IGNORECASE) for p in refusal_patterns
    )


def resolve_image(response_text: str, refusal_patterns: list[str],
                  download) -> "ImageRenderResult":
    """Decide the outcome of an image response.

    On a policy refusal: return REJECTED and do NOT download or retry. Otherwise
    call `download()` (which saves the image and returns its path) and return DONE.
    """
    if detect_refusal(response_text, refusal_patterns):
        return ImageRenderResult(status=STATUS_REJECTED, reason="Vi phạm chính sách")
    path = download()
    return ImageRenderResult(status=STATUS_DONE, path=path)


@dataclass
class ImageRenderResult:
    """Outcome of rendering one image."""

    status: str                 # STATUS_DONE / STATUS_REJECTED / STATUS_FAILED
    path: str | None = None
    reason: str = ""
```

Add this method to `ChatGPTWriter` (uses the pure `resolve_image` core):

```python
    def render_image(self, prompt: str, wrapper: str, dest_path: str) -> ImageRenderResult:
        """Render one image in a NEW chat and save it to dest_path.

        The wrapper wraps the section prompt (its {PROMPT} placeholder is
        replaced). On a policy refusal the image is skipped (no retry). DOM
        selectors are placeholders tuned against the live site.
        """
        self._open_new_chat()
        message = wrapper.replace("{PROMPT}", prompt)
        self._send(message)
        response_text = self._read_last_response()
        refusal_patterns = self.selectors["patterns"]["policy_refusal"]
        return resolve_image(
            response_text, refusal_patterns,
            download=lambda: self._download_image(dest_path),
        )

    def _download_image(self, dest_path: str) -> str:
        # TODO: kiểm tra selector thực tế — locate the generated image, get the
        # highest-resolution source, and save it to dest_path. Returns dest_path.
        sel = self.selectors["chatgpt"]
        self.session.wait_for(sel["generated_image"])
        loc = self.session.page.locator(sel["generated_image"]).last
        src = loc.get_attribute("src")
        # A real implementation downloads `src` (or the full-res variant) to
        # dest_path via the browser context request. Placeholder for live tuning.
        self._save_image_from_src(src, dest_path)
        return dest_path

    def _save_image_from_src(self, src: str | None, dest_path: str) -> None:
        # TODO: kiểm tra selector thực tế — fetch the image bytes (handles data:
        # URIs and https URLs via the page context) and write them to dest_path.
        raise NotImplementedError("Image download must be tuned on the live site")
```

- [ ] **Step 6: Run tests, confirm 1 (statuses) + 3 (image) passed. Then full suite.**

- [ ] **Step 7: Commit**

```bash
cd "D:/Home/wf"
git add horizon_tool/core/statuses.py horizon_tool/core/report.py horizon_tool/automation/chatgpt.py horizon_tool/tests/test_image_render.py horizon_tool/tests/test_statuses.py
git commit -m "feat: shared statuses + image refusal detection + render core (DOM download TODO)"
```

---

### Task 2: Pipeline image step + worker/GUI wiring

**Files:**
- Modify: `horizon_tool/core/pipeline.py` (image prompts in ScriptOutcome; `render_images`; shared statuses)
- Modify: `horizon_tool/gui/worker.py` (render images after word; per-step status signal; flags)
- Modify: `horizon_tool/gui/main_window.py` (per-step column mapping; pass checkbox flags)
- Test: `horizon_tool/tests/test_render_images.py`, extend `horizon_tool/tests/test_script_run_worker.py`, extend `horizon_tool/tests/test_main_window.py`

- [ ] **Step 1: Write the failing test** for `render_images`

```python
# horizon_tool/tests/test_render_images.py
from horizon_tool.core.pipeline import render_images
from horizon_tool.automation.chatgpt import ImageRenderResult
from horizon_tool.core.statuses import STATUS_DONE, STATUS_REJECTED, STATUS_SKIPPED

CONFIG = {"chatgpt": {
    "image_wrapper_9x16": "9:16 ratio:\n{PROMPT}",
    "image_wrapper_16x9": "16:9 ratio:\n{PROMPT}",
}}


class FakeWriter:
    def __init__(self, statuses):
        self._statuses = statuses          # dict dest-substr -> status
        self.calls = []

    def render_image(self, prompt, wrapper, dest_path):
        self.calls.append((prompt, wrapper, dest_path))
        for key, status in self._statuses.items():
            if key in dest_path:
                path = dest_path if status == STATUS_DONE else None
                return ImageRenderResult(status=status, path=path)
        return ImageRenderResult(status=STATUS_DONE, path=dest_path)


def test_renders_both_images(tmp_path):
    writer = FakeWriter({"9x16": STATUS_DONE, "16x9": STATUS_DONE})
    out = render_images(
        writer=writer, output_dir=tmp_path, ordinal=1, config=CONFIG,
        image_9x16_prompt="a vertical scene", thumbnail_16x9_prompt="a key art",
        do_9x16=True, do_16x9=True)
    assert out["img_9x16"] == STATUS_DONE
    assert out["img_16x9"] == STATUS_DONE
    # correct wrappers applied and prompts substituted
    assert any("9:16 ratio:\na vertical scene" == c[0] or
               c[1].replace("{PROMPT}", c[0]) for c in writer.calls)


def test_rejection_is_recorded_without_retry(tmp_path):
    writer = FakeWriter({"9x16": STATUS_REJECTED, "16x9": STATUS_DONE})
    out = render_images(
        writer=writer, output_dir=tmp_path, ordinal=2, config=CONFIG,
        image_9x16_prompt="p", thumbnail_16x9_prompt="q",
        do_9x16=True, do_16x9=True)
    assert out["img_9x16"] == STATUS_REJECTED
    assert out["img_16x9"] == STATUS_DONE
    # exactly two render calls total (no retry of the rejected one)
    assert len(writer.calls) == 2


def test_missing_prompt_is_skipped(tmp_path):
    writer = FakeWriter({})
    out = render_images(
        writer=writer, output_dir=tmp_path, ordinal=3, config=CONFIG,
        image_9x16_prompt=None, thumbnail_16x9_prompt="q",
        do_9x16=True, do_16x9=True)
    assert out["img_9x16"] == STATUS_SKIPPED   # no section 3 -> skip
    assert out["img_16x9"] == STATUS_DONE


def test_disabled_steps_are_skipped(tmp_path):
    writer = FakeWriter({})
    out = render_images(
        writer=writer, output_dir=tmp_path, ordinal=4, config=CONFIG,
        image_9x16_prompt="p", thumbnail_16x9_prompt="q",
        do_9x16=False, do_16x9=False)
    assert out["img_9x16"] == STATUS_SKIPPED
    assert out["img_16x9"] == STATUS_SKIPPED
    assert writer.calls == []
```

- [ ] **Step 2: Run test, confirm FAIL.**

- [ ] **Step 3: Update `core/pipeline.py`**

Replace the status constants block and `ScriptOutcome`, and add `render_images`:

```python
from horizon_tool.core.statuses import (
    STATUS_DONE, STATUS_FAILED, STATUS_SKIPPED, STATUS_REJECTED,
)
from horizon_tool.core.output_manager import output_paths, save_raw_response
from horizon_tool.core.section_parser import parse_sections
from horizon_tool.core.word_builder import build_document
```

(Remove the old local `STATUS_DONE = "Xong"` / `STATUS_FAILED = "Lỗi"` definitions — they now come from statuses.)

Extend `ScriptOutcome` with the image prompts:

```python
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
```

In `process_script`, capture the two image prompts from the parsed sections before returning:

```python
    return ScriptOutcome(
        ordinal=ordinal,
        word_status=STATUS_DONE,
        missing_sections=parsed.missing,
        conversation_url=result.conversation_url,
        image_9x16_prompt=parsed.sections.get("image_9x16"),
        thumbnail_16x9_prompt=parsed.sections.get("thumbnail_16x9"),
    )
```

Add `render_images` at the end of the module:

```python
def render_images(*, writer, output_dir: Path, ordinal: int, config: dict,
                  image_9x16_prompt: str | None, thumbnail_16x9_prompt: str | None,
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
```

- [ ] **Step 4: Run test_render_images.py, confirm 4 passed.**

- [ ] **Step 5: Update `gui/worker.py`** — emit a per-step status and render images after the word step

Change `ScriptRunWorker` to a single per-step signal and add image flags. Replace the class's signals and `__init__`/`run` as follows (keep `_close_writer` and imports; add render_images + statuses import):

```python
from horizon_tool.core.pipeline import process_script, render_images
from horizon_tool.core.statuses import STATUS_RUNNING, STATUS_FAILED
```

Signals + constructor:

```python
    log = Signal(str)
    step_status = Signal(int, str, str)   # (ordinal, step_key, status)
    done = Signal()

    def __init__(self, *, input_dir: str, output_dir: str, selection: str,
                 plugin_text: str, heading_regexes: dict, writer_factory,
                 do_9x16: bool = True, do_16x9: bool = True,
                 config: dict | None = None, parent=None) -> None:
        super().__init__(parent)
        self._input_dir = Path(input_dir)
        self._output_dir = Path(output_dir)
        self._selection = selection
        self._plugin_text = plugin_text
        self._heading_regexes = heading_regexes
        self._writer_factory = writer_factory
        self._do_9x16 = do_9x16
        self._do_16x9 = do_16x9
        self._config = config or {}
        self._stop = False
        self._paused = False
```

`run` body (per script): emit word running/status, then images:

```python
    def run(self) -> None:  # noqa: D401 - QThread entry point
        scripts, skipped = scan_input_folder(self._input_dir)
        scripts = filter_by_selection(scripts, self._selection)
        for s in skipped:
            self.log.emit(f"Bỏ qua {s.path.name}: {s.reason}")
        for script in scripts:
            if self._stop:
                self.log.emit("Đã dừng theo yêu cầu.")
                break
            while self._paused and not self._stop:
                self.msleep(100)
            if self._stop:
                self.log.emit("Đã dừng theo yêu cầu.")
                break
            self.step_status.emit(script.ordinal, "word", STATUS_RUNNING)
            writer = None
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
                self.step_status.emit(script.ordinal, "word", outcome.word_status)
                self.log.emit(f"Xong Word kịch bản {script.ordinal}")
                # TODO (Phase 6): add a ReportWriter row for this script.

                img = render_images(
                    writer=writer, output_dir=out_dir, ordinal=script.ordinal,
                    config=self._config,
                    image_9x16_prompt=outcome.image_9x16_prompt,
                    thumbnail_16x9_prompt=outcome.thumbnail_16x9_prompt,
                    do_9x16=self._do_9x16, do_16x9=self._do_16x9,
                )
                self.step_status.emit(script.ordinal, "img_9x16", img["img_9x16"])
                self.step_status.emit(script.ordinal, "img_16x9", img["img_16x9"])
                self.log.emit(
                    f"Ảnh kịch bản {script.ordinal}: 9:16={img['img_9x16']}, 16:9={img['img_16x9']}")
            except Exception as exc:  # noqa: BLE001 - one script must not stop the run
                self.step_status.emit(script.ordinal, "word", STATUS_FAILED)
                self.log.emit(f"Lỗi kịch bản {script.ordinal}: {exc}")
                # TODO (Phase 6): add a ReportWriter row with error=str(exc).
            finally:
                if writer is not None:
                    _close_writer(writer)
        self.done.emit()
```

- [ ] **Step 6: Update `gui/main_window.py`** — map step keys to columns and pass flags

Add near `STEP_COLUMNS`:

```python
STEP_COLUMN_INDEX = {"word": 2, "img_9x16": 3, "img_16x9": 4, "video": 5}
```

Replace `_on_progress` with a step-aware version and keep a thin compat wrapper:

```python
    def _on_step_status(self, ordinal: int, step: str, status: str) -> None:
        """Upsert the row for `ordinal` and set the given step's column.

        Runs on the GUI thread (queued signal). One row per script.
        """
        row = self._row_for_ordinal(ordinal)
        if row is None:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(str(ordinal)))
        self.table.setItem(row, STEP_COLUMN_INDEX[step], QTableWidgetItem(status))

    def _on_progress(self, ordinal: int, status: str) -> None:
        """Compat shim for PipelineWorker (Phase-1 stub): the word step."""
        self._on_step_status(ordinal, "word", status)
```

(`_row_for_ordinal` already exists.)

In `on_start`, pass flags + config to the worker and connect the new signal. Change the worker construction and connections:

```python
        self.worker = ScriptRunWorker(
            input_dir=input_dir, output_dir=output_dir,
            selection=self.range_edit.text().strip(), plugin_text=plugin_text,
            heading_regexes=selectors["section_headings"],
            writer_factory=writer_factory,
            do_9x16=self.step_img_9x16.isChecked(),
            do_16x9=self.step_thumb_16x9.isChecked(),
            config=self.config.raw, parent=self,
        )
        self.worker.log.connect(self.append_log)
        self.worker.step_status.connect(self._on_step_status)
        self.worker.done.connect(self._on_worker_done)
        self._set_running_state(True)
        self.worker.start()
```

- [ ] **Step 7: Update `test_script_run_worker.py`** for the new `step_status` signal

The existing tests connect `worker.progress`; change them to `step_status`. In `test_worker_processes_folder`, FakeWriter now also needs `render_image` (the worker calls it). Update the FakeWriter and add step-status capture:

```python
class FakeWriter:
    def __init__(self):
        self.session = FakeSession()

    def write_script(self, plugin_text, script_text, runtime_suffix=""):
        return ScriptResult(raw_text=FULL)

    def render_image(self, prompt, wrapper, dest_path):
        from horizon_tool.automation.chatgpt import ImageRenderResult
        from horizon_tool.core.statuses import STATUS_DONE
        # simulate a saved file
        from pathlib import Path
        Path(dest_path).write_bytes(b"PNG")
        return ImageRenderResult(status=STATUS_DONE, path=dest_path)
```

In `test_worker_processes_folder`, construct the worker with `config={}` (or a config dict) and after `done`, assert the image files exist and that step_status was emitted for img steps:

```python
    statuses = []
    worker = ScriptRunWorker(
        input_dir=str(tmp_path / "in"), output_dir=str(out), selection="",
        plugin_text="PLUGIN", heading_regexes=selectors["section_headings"],
        writer_factory=factory, do_9x16=True, do_16x9=True,
        config={"chatgpt": {"image_wrapper_9x16": "{PROMPT}",
                            "image_wrapper_16x9": "{PROMPT}"}},
    )
    worker.step_status.connect(lambda o, s, st: statuses.append((o, s, st)))
    with qtbot.waitSignal(worker.done, timeout=5000):
        worker.start()

    assert (out / "1" / "1.docx").exists()
    assert (out / "1" / "1_9x16.png").exists()
    assert (out / "1" / "1_16x9.png").exists()
    assert any(s == "img_9x16" for _, s, _ in statuses)
    assert all(w.session.closed for w in created)
    assert worker.wait(2000)
```

For `test_worker_continues_after_one_script_fails`, change `worker.progress.connect` to `worker.step_status.connect(lambda o, s, st: statuses.append((o, s, st)))`, add `render_image` to `FlakyWriter` (same as FakeWriter), pass `config={...}` and `do_9x16=True, do_16x9=True`, and assert a `("word", "Lỗi")`-style status appears:

```python
    assert any(st == "Lỗi" for _, _, st in statuses)
```

- [ ] **Step 8: Update `test_main_window.py`** — the progress test now uses `_on_step_status`

Replace `test_progress_upserts_one_row_per_script` body to exercise the step-aware method and image columns:

```python
def test_step_status_upserts_and_maps_columns(qtbot):
    app = QApplication.instance() or QApplication([])
    win = MainWindow(AppConfig.load(CONFIG))
    qtbot.addWidget(win)
    win._on_step_status(1, "word", "Đang chạy")
    win._on_step_status(1, "word", "Xong")          # updates in place
    win._on_step_status(1, "img_9x16", "Bị từ chối")
    win._on_step_status(2, "word", "Đang chạy")
    assert win.table.rowCount() == 2
    assert win.table.item(0, 2).text() == "Xong"       # word col
    assert win.table.item(0, 3).text() == "Bị từ chối"  # 9:16 col
    assert win.table.item(1, 2).text() == "Đang chạy"
```

- [ ] **Step 9: Run the FULL suite, then smoke check**

Run: `cd "D:/Home/wf" && horizon_tool/.venv/Scripts/python.exe -m pytest horizon_tool/tests -q` — expect all pass, exit 0.

Smoke (offscreen; guard path, no browser):
```
QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 horizon_tool/.venv/Scripts/python.exe -c "import sys; from pathlib import Path; sys.path.insert(0, r'D:\Home\wf'); from PySide6.QtWidgets import QApplication; from horizon_tool.core.config_loader import AppConfig; from horizon_tool.gui.main_window import MainWindow; app=QApplication([]); w=MainWindow(AppConfig.load(Path(r'D:\Home\wf\horizon_tool\config\config.yaml'))); w._on_step_status(1,'img_16x9','Bị từ chối'); print('cell:', w.table.item(0,4).text()); app.processEvents()"
```
Expect: `cell: Bị từ chối`.

- [ ] **Step 10: Commit**

```bash
cd "D:/Home/wf"
git add horizon_tool/core/pipeline.py horizon_tool/gui/worker.py horizon_tool/gui/main_window.py horizon_tool/tests/test_render_images.py horizon_tool/tests/test_script_run_worker.py horizon_tool/tests/test_main_window.py
git commit -m "feat: render 9:16 + 16:9 images in the pipeline with per-step progress and refusal handling"
```

---

## Self-Review

**Spec coverage (Phase 4 = spec §16 item 4 / §7.4):**
- Prompt from section 3 (9:16) and section 4 (16:9) → `render_images` reads `image_9x16_prompt` / `thumbnail_16x9_prompt` from the parsed sections (Task 2) ✓
- Each image in a NEW chat, wrapper command from config → `ChatGPTWriter.render_image` opens a new chat and applies `image_wrapper_9x16/16x9` (Task 1) ✓
- Wait for image, download highest-res original → `_download_image` (DOM placeholder, live-tuned) ✓ (structure present; download body is the marked TODO)
- Refusal detection via YAML patterns; on refusal skip immediately, no retry, mark "Bị từ chối", log, continue → `detect_refusal` + `resolve_image` (tested: no download on refusal) + worker logs + REJECTED status ✓
- Save to `<n>_9x16.png` / `<n>_16x9.png` → dest paths from `output_paths` ✓
- One image failing never stops the other / the run → per-step try/except in `render_images` and per-script try/except in the worker ✓
- Progress table per-step columns (Ảnh 9:16, Ảnh 16:9) → `step_status` signal + `STEP_COLUMN_INDEX` mapping ✓
- GUI checkboxes gate the steps → `do_9x16`/`do_16x9` from `step_img_9x16`/`step_thumb_16x9` ✓

**Deferred (intentional):** the actual image byte download (`_save_image_from_src`) and new-message wait are live-DOM TODOs; skip-video-when-no-9:16 is Phase 5; report.xlsx row population is Phase 6 (TODO markers present).

**Placeholder scan:** No TODO in code except the clearly-marked live-DOM image-download selectors.

**Type/name consistency:** `ImageRenderResult(status, path, reason)` returned by `render_image` and consumed by `render_images`. `render_images(writer, output_dir, ordinal, config, image_9x16_prompt, thumbnail_16x9_prompt, do_9x16, do_16x9) -> dict[str,str]` matches the worker call. Status strings come from the single `core/statuses.py`. `step_status(int, str, str)` emitted by the worker matches `_on_step_status(ordinal, step, status)` and `STEP_COLUMN_INDEX` keys ("word","img_9x16","img_16x9","video").
