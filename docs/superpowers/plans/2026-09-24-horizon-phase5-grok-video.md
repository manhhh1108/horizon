# Horizon X Media Tool — Phase 5 Implementation Plan (Grok video from the 9:16 image)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** After the 9:16 image is produced, feed it into Grok to generate a video: open Grok (its own account profile) in image-to-video mode, upload the 9:16 image, enter the motion prompt (section 5, or a config override), pick duration + quality from the GUI, wait for render, and download the `.mp4`. Skip the video step when the 9:16 image is absent; on refusal/render error, skip (no retry), log, and continue. Wire the video step into the pipeline, the run worker, and the progress table's Video column.

**Architecture:** The video-result decision (refusal → rejected, render-error → failed, else download) is a pure, unit-tested function mirroring `resolve_image`. `automation/grok.py` `GrokVideoMaker` is thin DOM glue over that core, using YAML selectors (placeholders, tuned live). The pipeline gains `make_video`; `ScriptRunWorker` builds a separate Grok session per script (Grok is a different account/browser than ChatGPT), renders the video after the images, and emits the Video step status.

**Tech Stack:** Python 3.10-compatible, Playwright, PySide6, pytest.

**Convention:** UI/log/report text Vietnamese; code identifiers/docstrings/comments English.

**Base branch:** `main`. Work branch: `phase-5-grok-video`.

**Verified preconditions:** `selectors.yaml` has `grok.*` selectors (url_image_to_video, image_upload_input, motion_prompt_box, duration_control, quality_control, generate_button, video_result) and `patterns.policy_refusal`; `config.yaml` has `grok.render_timeout_seconds` (600) and `grok.motion_prompt_override` (""). `patterns.video_error` does NOT exist yet — Task 1 adds it.

**Honesty note (per user):** All the real Grok DOM steps (open image-to-video, upload the image, set duration/quality controls, click generate, wait for render, download the mp4) stay as placeholders marked `# TODO: kiểm tra selector thực tế`, to be tuned tomorrow on the logged-in machine. The decision logic, skip rules, per-step status, and wiring are fully tested with fakes.

---

### Task 1: Grok video maker (`automation/grok.py`) + video-error patterns

**Files:**
- Modify: `horizon_tool/config/selectors.yaml` (add `patterns.video_error`)
- Create: `horizon_tool/automation/grok.py`
- Test: `horizon_tool/tests/test_grok_video.py`

- [ ] **Step 1: Add `video_error` patterns to `selectors.yaml`**

Under the `patterns:` block (right after the `policy_refusal:` list), add:

```yaml
  video_error:
    - "something went wrong"
    - "failed to generate"
    - "render failed"
    - "try again"
```

(These are best-guess English strings to be verified against the live Grok UI; they are the file the user edits when Grok changes.)

- [ ] **Step 2: Write the failing test** (pure decision core; no browser)

```python
# horizon_tool/tests/test_grok_video.py
from horizon_tool.automation.grok import resolve_video, VideoResult
from horizon_tool.core.statuses import STATUS_DONE, STATUS_REJECTED, STATUS_FAILED

REFUSALS = ["against.*content policy", "can't create this video"]
ERRORS = ["something went wrong", "failed to generate"]


def test_resolve_video_rejects_without_downloading():
    calls = []
    result = resolve_video("This is against our content policy.", REFUSALS, ERRORS,
                           download=lambda: calls.append(1))
    assert result.status == STATUS_REJECTED
    assert result.path is None
    assert calls == []  # refusal -> no download, no retry


def test_resolve_video_render_error_is_failed_without_downloading():
    calls = []
    result = resolve_video("Something went wrong, please retry.", REFUSALS, ERRORS,
                           download=lambda: calls.append(1))
    assert result.status == STATUS_FAILED
    assert result.path is None
    assert calls == []  # render error -> no download, no retry


def test_resolve_video_downloads_when_ok():
    result = resolve_video("Your video is ready!", REFUSALS, ERRORS,
                           download=lambda: "out/1.mp4")
    assert result.status == STATUS_DONE
    assert result.path == "out/1.mp4"
```

- [ ] **Step 3: Run test, confirm FAIL** (`ModuleNotFoundError`).

- [ ] **Step 4: Implement `automation/grok.py`**

```python
"""Grok automation: make a video from the 9:16 image.

The result decision (refusal → rejected, render-error → failed, else download)
is a pure function tested without a browser. The DOM steps on GrokVideoMaker
use selectors from selectors.yaml — placeholders tuned against the live site.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from horizon_tool.automation.browser import BrowserSession
from horizon_tool.automation.chatgpt import detect_refusal
from horizon_tool.core.statuses import STATUS_DONE, STATUS_FAILED, STATUS_REJECTED


@dataclass
class VideoResult:
    """Outcome of rendering one video."""

    status: str                 # STATUS_DONE / STATUS_REJECTED / STATUS_FAILED
    path: str | None = None
    reason: str = ""


def resolve_video(status_text: str, refusal_patterns: list[str],
                  error_patterns: list[str],
                  download: Callable[[], str]) -> VideoResult:
    """Decide the outcome of a Grok video attempt.

    Policy refusal → REJECTED; render error → FAILED. In both cases the video is
    skipped with NO retry and download() is not called. Otherwise download() saves
    the mp4 and returns its path → DONE.
    """
    if detect_refusal(status_text, refusal_patterns):
        return VideoResult(status=STATUS_REJECTED, reason="Vi phạm chính sách")
    if detect_refusal(status_text, error_patterns):
        return VideoResult(status=STATUS_FAILED, reason="Render lỗi")
    path = download()
    return VideoResult(status=STATUS_DONE, path=path)


class GrokVideoMaker:
    """Drives Grok to turn a 9:16 image into a video.

    DOM methods use selectors from `selectors`; they are placeholders marked in
    selectors.yaml and must be verified against the live Grok UI.
    """

    def __init__(self, session: BrowserSession, selectors: dict, config: dict) -> None:
        self.session = session
        self.selectors = selectors
        self.config = config

    def make_video(self, image_path: str, motion_prompt: str, duration: str,
                   quality: str, dest_path: str) -> VideoResult:
        """Upload the image, set options, generate, and download the video."""
        self._open_image_to_video()
        self._upload_image(image_path)
        self._enter_motion_prompt(motion_prompt)
        self._select_duration(duration)
        self._select_quality(quality)
        self._click_generate()
        status_text = self._wait_and_read_status()
        patterns = self.selectors["patterns"]
        return resolve_video(
            status_text, patterns["policy_refusal"], patterns["video_error"],
            download=lambda: self._download_video(dest_path),
        )

    # ----- DOM methods (selectors are placeholders; tune on live site) ----
    def _open_image_to_video(self) -> None:
        self.session.goto(self.selectors["grok"]["url_image_to_video"])

    def _upload_image(self, image_path: str) -> None:
        # TODO: kiểm tra selector thực tế — set the file input to image_path.
        sel = self.selectors["grok"]["image_upload_input"]
        self.session.page.set_input_files(sel, image_path)

    def _enter_motion_prompt(self, motion_prompt: str) -> None:
        self.session.paste_text(self.selectors["grok"]["motion_prompt_box"], motion_prompt)

    def _select_duration(self, duration: str) -> None:
        # TODO: kiểm tra selector thực tế — choose the duration control matching `duration`.
        pass

    def _select_quality(self, quality: str) -> None:
        # TODO: kiểm tra selector thực tế — choose the quality control matching `quality`.
        pass

    def _click_generate(self) -> None:
        self.session.click_with_retry(self.selectors["grok"]["generate_button"])

    def _wait_and_read_status(self) -> str:
        # TODO: kiểm tra selector thực tế — wait until render finishes (up to
        # grok.render_timeout_seconds), then read any status/result text so a
        # refusal or render error can be detected. Returns that text.
        timeout_ms = int(self.config.get("grok", {}).get("render_timeout_seconds", 600)) * 1000
        self.session.wait_for(self.selectors["grok"]["video_result"], timeout_ms=timeout_ms)
        return ""

    def _download_video(self, dest_path: str) -> str:
        # TODO: kiểm tra selector thực tế — locate the rendered video and save it
        # to dest_path. Returns dest_path.
        raise NotImplementedError("Video download must be tuned on the live site")
```

- [ ] **Step 5: Run test, confirm 3 passed. Then full suite.**

- [ ] **Step 6: Commit**

```bash
cd "D:/Home/wf"
git add horizon_tool/config/selectors.yaml horizon_tool/automation/grok.py horizon_tool/tests/test_grok_video.py
git commit -m "feat: Grok video maker + resolve_video decision core (DOM download TODO)"
```

---

### Task 2: Pipeline video step + worker/GUI wiring

**Files:**
- Modify: `horizon_tool/core/pipeline.py` (`video_prompt` in ScriptOutcome; `make_video`)
- Modify: `horizon_tool/gui/worker.py` (Grok maker factory; render video after images; flags/options)
- Modify: `horizon_tool/gui/main_window.py` (build Grok factory; pass do_video + duration/quality)
- Test: `horizon_tool/tests/test_make_video.py`, extend `horizon_tool/tests/test_script_run_worker.py`

- [ ] **Step 1: Write the failing test** for `make_video`

```python
# horizon_tool/tests/test_make_video.py
from horizon_tool.core.pipeline import make_video
from horizon_tool.automation.grok import VideoResult
from horizon_tool.core.statuses import (
    STATUS_DONE, STATUS_REJECTED, STATUS_SKIPPED, STATUS_FAILED,
)

CONFIG = {"grok": {"motion_prompt_override": ""}}


class FakeMaker:
    def __init__(self, status=STATUS_DONE):
        self._status = status
        self.calls = []

    def make_video(self, image_path, motion_prompt, duration, quality, dest_path):
        self.calls.append(dict(image_path=image_path, motion_prompt=motion_prompt,
                               duration=duration, quality=quality, dest_path=dest_path))
        path = dest_path if self._status == STATUS_DONE else None
        return VideoResult(status=self._status, path=path)


def test_make_video_success(tmp_path):
    maker = FakeMaker(STATUS_DONE)
    status = make_video(
        maker=maker, output_dir=tmp_path, ordinal=1, config=CONFIG,
        motion_prompt="camera slowly pushes in", duration="15s", quality="1080p",
        image_path=str(tmp_path / "1_9x16.png"), do_video=True)
    assert status == STATUS_DONE
    assert maker.calls[0]["motion_prompt"] == "camera slowly pushes in"
    assert maker.calls[0]["duration"] == "15s"
    assert maker.calls[0]["dest_path"].endswith("1.mp4")


def test_make_video_uses_config_override_prompt(tmp_path):
    cfg = {"grok": {"motion_prompt_override": "fixed motion"}}
    maker = FakeMaker(STATUS_DONE)
    make_video(maker=maker, output_dir=tmp_path, ordinal=1, config=cfg,
               motion_prompt="from section 5", duration="10s", quality="720p",
               image_path=str(tmp_path / "1_9x16.png"), do_video=True)
    assert maker.calls[0]["motion_prompt"] == "fixed motion"  # override wins


def test_make_video_skipped_when_disabled(tmp_path):
    maker = FakeMaker()
    status = make_video(maker=maker, output_dir=tmp_path, ordinal=2, config=CONFIG,
                        motion_prompt="p", duration="10s", quality="720p",
                        image_path=str(tmp_path / "2_9x16.png"), do_video=False)
    assert status == STATUS_SKIPPED
    assert maker.calls == []


def test_make_video_skipped_when_no_image(tmp_path):
    maker = FakeMaker()
    status = make_video(maker=maker, output_dir=tmp_path, ordinal=3, config=CONFIG,
                        motion_prompt="p", duration="10s", quality="720p",
                        image_path=None, do_video=True)   # 9:16 missing
    assert status == STATUS_SKIPPED
    assert maker.calls == []


def test_make_video_rejection(tmp_path):
    maker = FakeMaker(STATUS_REJECTED)
    status = make_video(maker=maker, output_dir=tmp_path, ordinal=4, config=CONFIG,
                        motion_prompt="p", duration="10s", quality="720p",
                        image_path=str(tmp_path / "4_9x16.png"), do_video=True)
    assert status == STATUS_REJECTED
    assert len(maker.calls) == 1  # no retry


def test_make_video_exception_is_failed(tmp_path):
    class Boom:
        def make_video(self, *a, **k):
            raise RuntimeError("mạng lỗi")
    status = make_video(maker=Boom(), output_dir=tmp_path, ordinal=5, config=CONFIG,
                        motion_prompt="p", duration="10s", quality="720p",
                        image_path=str(tmp_path / "5_9x16.png"), do_video=True)
    assert status == STATUS_FAILED
```

- [ ] **Step 2: Run test, confirm FAIL.**

- [ ] **Step 3: Update `core/pipeline.py`**

Add a `VideoMaker` Protocol near `ImageWriter`:

```python
class VideoMaker(Protocol):
    """Anything that can turn an image into a video and return a VideoResult."""

    def make_video(self, image_path: str, motion_prompt: str, duration: str,
                   quality: str, dest_path: str): ...
```

Add `VideoMaker` to `__all__` and add `make_video` to it. Extend `ScriptOutcome` with the motion prompt:

```python
    video_prompt: str | None = None
```

In `process_script`, set it from the parsed sections:

```python
        video_prompt=parsed.sections.get("video_prompt"),
```

Add `make_video` at the end of the module:

```python
def make_video(*, maker: VideoMaker, output_dir: Path, ordinal: int, config: dict,
               motion_prompt: str | None, duration: str, quality: str,
               image_path: str | None, do_video: bool = True) -> str:
    """Render the video from the 9:16 image, returning a step status.

    SKIPPED when disabled or the 9:16 image is missing. A config
    `grok.motion_prompt_override` (if non-empty) replaces the section-5 prompt.
    Refusal → REJECTED, render error → FAILED (both no retry); any other error
    → FAILED. Never raises.
    """
    if not do_video or not image_path:
        return STATUS_SKIPPED
    override = config.get("grok", {}).get("motion_prompt_override", "")
    prompt = override or (motion_prompt or "")
    dest = str(output_paths(output_dir, ordinal)["video"])
    try:
        return maker.make_video(image_path, prompt, duration, quality, dest).status
    except Exception:  # noqa: BLE001 - a video failure must not stop the run
        return STATUS_FAILED
```

- [ ] **Step 4: Run test_make_video.py, confirm 6 passed.**

- [ ] **Step 5: Update `gui/worker.py`** — add the Grok maker factory + options and render the video after images

Add imports:

```python
from horizon_tool.core.pipeline import process_script, render_images, make_video
from horizon_tool.core.statuses import STATUS_RUNNING, STATUS_FAILED, STATUS_REJECTED, STATUS_DONE, STATUS_SKIPPED
from horizon_tool.core.output_manager import output_paths
```

Add constructor params (after the image flags):

```python
                 do_video: bool = True, video_maker_factory=None,
                 video_duration: str = "", video_quality: str = "",
```

Store them:

```python
        self._do_video = do_video
        self._video_maker_factory = video_maker_factory
        self._video_duration = video_duration
        self._video_quality = video_quality
```

In `run()`, after the image `step_status.emit(...)` lines and the refusal log loop, add the video step:

```python
                # Video step: needs the 9:16 image. Uses a SEPARATE Grok session.
                img_9x16_path = str(output_paths(out_dir, script.ordinal)["img_9x16"])
                have_9x16 = img["img_9x16"] == STATUS_DONE
                if not self._do_video:
                    self.step_status.emit(script.ordinal, "video", STATUS_SKIPPED)
                elif not have_9x16:
                    self.step_status.emit(script.ordinal, "video", STATUS_SKIPPED)
                    self.log.emit(f"Kịch bản {script.ordinal}: không có ảnh 9:16 — bỏ qua video.")
                elif self._video_maker_factory is None:
                    self.step_status.emit(script.ordinal, "video", STATUS_SKIPPED)
                else:
                    maker = None
                    try:
                        maker = self._video_maker_factory()
                        v_status = make_video(
                            maker=maker, output_dir=out_dir, ordinal=script.ordinal,
                            config=self._config, motion_prompt=outcome.video_prompt,
                            duration=self._video_duration, quality=self._video_quality,
                            image_path=img_9x16_path, do_video=True,
                        )
                    finally:
                        if maker is not None:
                            _close_writer(maker)  # closes maker.session too
                    self.step_status.emit(script.ordinal, "video", v_status)
                    if v_status == STATUS_REJECTED:
                        self.log.emit(
                            f"Kịch bản {script.ordinal} video bị từ chối — bỏ qua, không thử lại.")
                    else:
                        self.log.emit(f"Video kịch bản {script.ordinal}: {v_status}")
```

Also, in the `except Exception` (script-level failure) block, resolve the video column too so no cell is blank:

```python
                self.step_status.emit(script.ordinal, "video", STATUS_FAILED)
```

(add it alongside the existing word/img_9x16/img_16x9 FAILED emits.)

Note: `_close_writer` already closes any object exposing a `.session` with `.close()`, so it works for the GrokVideoMaker too.

- [ ] **Step 6: Update `gui/main_window.py`** — build the Grok factory and pass video options

In `on_start`, after the ChatGPT `writer_factory` definition, add a Grok maker factory and extend the worker construction:

```python
        from horizon_tool.automation.grok import GrokVideoMaker

        def video_maker_factory():
            account = self.account_manager.next_available("grok")
            if account is None:
                raise RuntimeError("Không có tài khoản Grok khả dụng.")
            session = BrowserSession(
                account.profile_dir, headless=False,
                element_timeout_ms=self.config.raw.get("timeouts", {}).get("element_wait_seconds", 30) * 1000)
            session.start()
            return GrokVideoMaker(session, selectors, self.config.raw)

        self.worker = ScriptRunWorker(
            input_dir=input_dir, output_dir=output_dir,
            selection=self.range_edit.text().strip(), plugin_text=plugin_text,
            heading_regexes=selectors["section_headings"],
            writer_factory=writer_factory,
            do_9x16=self.step_img_9x16.isChecked(),
            do_16x9=self.step_thumb_16x9.isChecked(),
            do_video=self.step_video.isChecked(),
            video_maker_factory=video_maker_factory,
            video_duration=self.duration_combo.currentText(),
            video_quality=self.quality_combo.currentText(),
            config=self.config.raw, parent=self,
        )
        self.worker.log.connect(self.append_log)
        self.worker.step_status.connect(self._on_step_status)
        self.worker.done.connect(self._on_worker_done)
        self._set_running_state(True)
        self.worker.start()
```

(Replace the existing `self.worker = ScriptRunWorker(...)` block and its connections with the above.)

- [ ] **Step 7: Extend `test_script_run_worker.py`** — the worker now renders a video

Add a `render_video`-capable fake and assert the Video step. Update `FakeWriter` is unchanged (it's the ChatGPT writer). Add a `FakeVideoMaker`:

```python
class FakeVideoMaker:
    def __init__(self):
        self.session = FakeSession()
        self.calls = []

    def make_video(self, image_path, motion_prompt, duration, quality, dest_path):
        from horizon_tool.automation.grok import VideoResult
        from pathlib import Path
        Path(dest_path).write_bytes(b"MP4")
        self.calls.append((image_path, duration, quality, dest_path))
        return VideoResult(status=STATUS_DONE, path=dest_path)
```

In `test_worker_processes_folder`, construct the worker with the video factory + options and assert the mp4 exists and a `video` step fired:

```python
    made = []
    def vfactory():
        m = FakeVideoMaker()
        made.append(m)
        return m
    worker = ScriptRunWorker(
        input_dir=str(tmp_path / "in"), output_dir=str(out), selection="",
        plugin_text="PLUGIN", heading_regexes=selectors["section_headings"],
        writer_factory=factory, do_9x16=True, do_16x9=True,
        do_video=True, video_maker_factory=vfactory,
        video_duration="15s", video_quality="1080p",
        config={"chatgpt": {"image_wrapper_9x16": "{PROMPT}",
                            "image_wrapper_16x9": "{PROMPT}"},
                "grok": {"motion_prompt_override": ""}},
    )
    # ... existing step_status capture + waitSignal(done) ...
    assert (out / "1" / "1.mp4").exists()
    assert any(s == "video" for _, s, _ in statuses)
    assert all(m.session.closed for m in made)   # Grok session closed per script
```

Add a focused test that no 9:16 image → video skipped:

```python
def test_video_skipped_when_no_9x16(qtbot, tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "1.txt").write_text("k", encoding="utf-8")
    out = tmp_path / "out"
    selectors = yaml.safe_load(SELECTORS_PATH.read_text(encoding="utf-8"))

    class RejectingWriter:
        def __init__(self):
            self.session = FakeSession()
        def write_script(self, *a, **k):
            return ScriptResult(raw_text=FULL)
        def render_image(self, prompt, wrapper, dest_path):
            from horizon_tool.core.statuses import STATUS_REJECTED
            return ImageRenderResult(status=STATUS_REJECTED)  # no image saved

    vmade = []
    def vfactory():
        m = FakeVideoMaker(); vmade.append(m); return m
    statuses = []
    worker = ScriptRunWorker(
        input_dir=str(tmp_path / "in"), output_dir=str(out), selection="",
        plugin_text="P", heading_regexes=selectors["section_headings"],
        writer_factory=lambda: RejectingWriter(), do_9x16=True, do_16x9=True,
        do_video=True, video_maker_factory=vfactory,
        video_duration="10s", video_quality="720p",
        config={"chatgpt": {"image_wrapper_9x16": "{PROMPT}",
                            "image_wrapper_16x9": "{PROMPT}"},
                "grok": {"motion_prompt_override": ""}})
    worker.step_status.connect(lambda o, s, st: statuses.append((o, s, st)))
    with qtbot.waitSignal(worker.done, timeout=5000):
        worker.start()
    from horizon_tool.core.statuses import STATUS_SKIPPED
    assert (1, "video", STATUS_SKIPPED) in statuses
    assert vmade == []          # Grok never invoked when there's no 9:16
    assert worker.wait(2000)
```

Also update `test_worker_continues_after_one_script_fails`: pass `do_video=False` (or a video factory) so it still runs; the simplest is `do_video=False` to keep that test focused on script-failure isolation. Ensure the failed script also emits `(1, "video", STATUS_FAILED)` if do_video path resolves columns — since do_video is False, the except block still emits video FAILED (from Step 5). Assert accordingly if desired.

- [ ] **Step 8: Run the FULL suite, then smoke check**

Run: `cd "D:/Home/wf" && horizon_tool/.venv/Scripts/python.exe -m pytest horizon_tool/tests -q` — all pass, exit 0.

Smoke (offscreen; the Video column path):
```
QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 horizon_tool/.venv/Scripts/python.exe -c "import sys; from pathlib import Path; sys.path.insert(0, r'D:\Home\wf'); from PySide6.QtWidgets import QApplication; from horizon_tool.core.config_loader import AppConfig; from horizon_tool.gui.main_window import MainWindow; app=QApplication([]); w=MainWindow(AppConfig.load(Path(r'D:\Home\wf\horizon_tool\config\config.yaml'))); w._on_step_status(1,'video','Bỏ qua'); print('cell:', w.table.item(0,5).text()); app.processEvents()"
```
Expect: `cell: Bỏ qua`.

- [ ] **Step 9: Commit**

```bash
cd "D:/Home/wf"
git add horizon_tool/core/pipeline.py horizon_tool/gui/worker.py horizon_tool/gui/main_window.py horizon_tool/tests/test_make_video.py horizon_tool/tests/test_script_run_worker.py
git commit -m "feat: Grok video step in the pipeline with per-step status and skip/refusal rules"
```

---

## Self-Review

**Spec coverage (Phase 5 = spec §16 item 5 / §9 VD-01..VD-04):**
- VD-01 open Grok (own account profile) image-to-video → `GrokVideoMaker._open_image_to_video` + a separate Grok session per script via `video_maker_factory` using `next_available("grok")` (Task 2) ✓
- VD-02 upload the 9:16 image; motion prompt from section 5 or a config override → `make_video` picks `grok.motion_prompt_override` else `video_prompt` (from parsed section 5); `_upload_image` sets the file input (Task 1/2) ✓
- VD-03 duration + quality from GUI → passed from `duration_combo`/`quality_combo` through the worker to `make_video`/`make_video` (Task 2) ✓
- VD-04 wait for render (config timeout, default 10 min), download video → `_wait_and_read_status` uses `grok.render_timeout_seconds`; `_download_video` placeholder (live-tuned) ✓
- No 9:16 image → skip video → `make_video` returns SKIPPED when `image_path` is None, and the worker only passes a path when `img["img_9x16"] == STATUS_DONE` ✓
- Refusal / render error → skip, no retry, log → `resolve_video` (tested: no download on refusal/error), worker logs the rejection; REJECTED/FAILED statuses ✓
- Save `<n>.mp4` → dest from `output_paths` ✓
- Video gated by the GUI "Video" checkbox → `do_video` from `step_video` ✓
- One video failure never stops the run → `make_video` never raises; worker per-script try/except ✓

**Deferred (intentional, per user):** every real Grok DOM step (upload, option controls, generate, wait, download bytes) is a marked placeholder; `_download_video` raises NotImplementedError so a placeholder run surfaces as FAILED, not a silent success. Quota rotation + report-row population remain Phase 6.

**Placeholder scan:** No TODO in code except the clearly-marked live-DOM Grok selectors.

**Type/name consistency:** `VideoResult(status, path, reason)` returned by `resolve_video`/`GrokVideoMaker.make_video`, consumed by pipeline `make_video`. `make_video(maker, output_dir, ordinal, config, motion_prompt, duration, quality, image_path, do_video) -> str` matches the worker call. `VideoMaker` Protocol matches `GrokVideoMaker`. Status strings from `core/statuses.py`. The worker emits `step_status(ordinal, "video", status)` which `_on_step_status` maps via `STEP_COLUMN_INDEX["video"] == 5`.
