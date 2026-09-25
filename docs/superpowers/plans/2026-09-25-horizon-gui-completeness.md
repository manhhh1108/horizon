# Horizon X Media Tool — GUI Completeness Pass (spec §4/§5 items 1–5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Fill the spec-listed GUI gaps that need no live selectors: (1) plugin **Xem trước** (preview), (2) a **Cài đặt** (Settings) window bound to `config.yaml`, (3) **live statistics** (total/done/skipped/failed + elapsed + current account), (4) populate the **Tên file** column, (5) wire the **Viết kịch bản** checkbox to gate the word step.

**Architecture:** `ScriptRunWorker` gains a few Qt signals (`run_totals`, `script_started`, `script_finished`, `account_in_use`) and a `do_script` flag; `MainWindow` consumes them for the live stats label (+ a 1s QTimer for elapsed) and the filename column. A new `gui/settings_window.py` edits `config.yaml` through a comment-preserving `save_config` writer added to `core/config_loader.py`; the plugin **Xem trước** button opens a read-only text dialog.

**Tech Stack:** Python 3.10-compatible, PySide6, PyYAML, pytest.

**Convention:** UI text Vietnamese; code identifiers/docstrings English.

**Base branch:** `main`. Work branch: `gui-completeness`.

**Deferred (NOT in this pass):** plugin **Sửa** editor (Phase 8), output-folder conflict dialog OUT-04 (Phase 7).

---

### Task A: Worker signals → live stats, filename column, do_script gate

**Files:**
- Modify: `horizon_tool/gui/worker.py` (ScriptRunWorker: signals + do_script)
- Modify: `horizon_tool/gui/main_window.py` (stats + filename + pass do_script)
- Test: extend `horizon_tool/tests/test_script_run_worker.py`, `horizon_tool/tests/test_main_window.py`

- [ ] **Step 1: Add signals + do_script to `ScriptRunWorker`**

Add these signals to the class (next to the existing `log`/`step_status`/`exhausted`/`done`):

```python
    run_totals = Signal(int, int)       # (total_scripts, skipped_files)
    script_started = Signal(int, str)   # (ordinal, input_filename)
    script_finished = Signal(int, str)  # (ordinal, "done" | "failed")
    account_in_use = Signal(str)        # ChatGPT account display name in use
```

Add a `do_script: bool = True` parameter to `__init__` (place it beside `do_9x16`) and store `self._do_script = do_script`.

- [ ] **Step 2: Gate the word step in `_chatgpt_block`**

At the top of `_chatgpt_block`, extend the word branch so an unchecked "Viết kịch bản" skips the word step (and, having no story, the images too):

```python
        ordinal = script.ordinal
        if self._state.is_done(ordinal, "word"):
            prompts = self._prompts_from_raw(out_dir)
            self.step_status.emit(ordinal, "word", self._state.get_step(ordinal, "word"))
        elif not self._do_script:
            self._state.set_step(ordinal, "word", STATUS_SKIPPED)
            self.step_status.emit(ordinal, "word", STATUS_SKIPPED)
            prompts = (None, None)   # no story -> image steps have no prompt -> skipped
        else:
            outcome = process_script(...)   # (unchanged existing body)
            ...
            prompts = (outcome.image_9x16_prompt, outcome.thumbnail_16x9_prompt)
```

- [ ] **Step 3: Emit the new signals in `run()`**

After scanning + filtering + logging skipped files:

```python
        self.run_totals.emit(len(scripts), len(skipped))
```

Restructure the per-script body to emit start/account/finished (keep the existing rotation/report logic):

```python
            ordinal = script.ordinal
            out_dir = self._output_dir / str(ordinal)
            out_dir.mkdir(parents=True, exist_ok=True)
            self.script_started.emit(ordinal, script.path.name)
            started = time.monotonic()
            account_name = ""
            stop_after = False
            failed = False
            try:
                self.step_status.emit(ordinal, "word", STATUS_RUNNING)
                _, chatgpt_account = run_step_with_rotation(
                    service="chatgpt", account_manager=self._accounts,
                    make_worker=self._writer_factory,
                    do_step=lambda w: self._chatgpt_block(w, script, out_dir),
                    log=self.log.emit,
                )
                account_name = chatgpt_account.display_name
                self.account_in_use.emit(account_name)
                self._save_video_prompt(ordinal, out_dir)
                self._run_video_step(ordinal, out_dir)
            except AllAccountsExhausted as exc:
                self.log.emit(f"Hết tài khoản {exc.service} — tạm dừng, đã lưu trạng thái.")
                self.exhausted.emit(exc.service)
                stop_after = True
            except Exception as exc:  # noqa: BLE001
                failed = True
                for step in ("word", "img_9x16", "img_16x9", "video"):
                    if not self._state.is_done(ordinal, step):
                        self._state.set_step(ordinal, step, STATUS_FAILED)
                        self.step_status.emit(ordinal, step, STATUS_FAILED)
                self.log.emit(f"Lỗi kịch bản {ordinal}: {exc}")
            finally:
                self._write_report_row(report, script, account_name, started)
            if not stop_after:
                self.script_finished.emit(ordinal, "failed" if failed else "done")
            if stop_after:
                break
```

- [ ] **Step 4: Consume signals in `MainWindow` for live stats + filename**

Add imports:

```python
from PySide6.QtCore import QTimer, QElapsedTimer
```

In `__init__` (after the auto-resume timer), add stats state + a 1s elapsed timer:

```python
        self._stats = {"total": 0, "skipped": 0, "done": 0, "failed": 0, "account": "-"}
        self._elapsed = QElapsedTimer()
        self._stats_timer = QTimer(self)
        self._stats_timer.timeout.connect(self._refresh_stats_label)
```

Replace the static `stats_label` text via a live updater. Add these methods:

```python
    def _reset_stats(self) -> None:
        self._stats = {"total": 0, "skipped": 0, "done": 0, "failed": 0, "account": "-"}
        self._elapsed.restart()
        self._refresh_stats_label()

    def _refresh_stats_label(self) -> None:
        s = self._stats
        secs = self._elapsed.elapsed() // 1000 if self._elapsed.isValid() else 0
        clock = f"{secs // 60:02d}:{secs % 60:02d}"
        self.stats_label.setText(
            f"Tổng: {s['total']} | Xong: {s['done']} | Bỏ qua: {s['skipped']} | "
            f"Lỗi: {s['failed']} | Thời gian: {clock} | Tài khoản: {s['account']}")

    def _on_run_totals(self, total: int, skipped: int) -> None:
        self._stats["total"] = total
        self._stats["skipped"] = skipped
        self._refresh_stats_label()

    def _on_script_finished(self, ordinal: int, overall: str) -> None:
        self._stats["done" if overall == "done" else "failed"] += 1
        self._refresh_stats_label()

    def _on_account_in_use(self, name: str) -> None:
        self._stats["account"] = name
        self._refresh_stats_label()

    def _on_script_started(self, ordinal: int, filename: str) -> None:
        row = self._row_for_ordinal(ordinal)
        if row is None:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(str(ordinal)))
        self.table.setItem(row, 1, QTableWidgetItem(filename))   # Tên file column
```

In `_launch_run`, before starting the worker, connect the new signals, reset stats, and start the timer; and pass `do_script`. Add to the worker construction kwargs: `do_script=self.step_script.isChecked(),`. After building `self.worker`:

```python
        self.worker.run_totals.connect(self._on_run_totals)
        self.worker.script_started.connect(self._on_script_started)
        self.worker.script_finished.connect(self._on_script_finished)
        self.worker.account_in_use.connect(self._on_account_in_use)
        # (existing log/step_status/exhausted/done connections stay)
        self._reset_stats()
        self._stats_timer.start(1000)
```

In `_on_worker_done`, stop the stats timer and do a final refresh:

```python
    def _on_worker_done(self) -> None:
        self._auto_resume_timer.stop()
        self._stats_timer.stop()
        self._refresh_stats_label()
        self._set_running_state(False)
```

- [ ] **Step 5: Tests**

Extend `test_script_run_worker.py` — in `test_full_pipeline_produces_all_outputs`, also capture and assert the new signals:

```python
def test_worker_emits_stats_signals(qtbot, tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "1.txt").write_text("k", encoding="utf-8")
    mgr = _mgr(tmp_path)
    totals, started, finished, accounts = [], [], [], []
    w = _worker(tmp_path, mgr)
    w.run_totals.connect(lambda t, s: totals.append((t, s)))
    w.script_started.connect(lambda o, f: started.append((o, f)))
    w.script_finished.connect(lambda o, st: finished.append((o, st)))
    w.account_in_use.connect(accounts.append)
    with qtbot.waitSignal(w.done, timeout=5000):
        w.start()
    assert totals == [(1, 0)]
    assert started == [(1, "1.txt")]
    assert finished == [(1, "done")]
    assert accounts and accounts[0] == "C1"
    assert w.wait(2000)


def test_do_script_false_skips_word_and_images(qtbot, tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "1.txt").write_text("k", encoding="utf-8")
    mgr = _mgr(tmp_path)
    calls = {"n": 0}
    class NoCallWriter(FakeWriter):
        def write_script(self, *a, **k):
            calls["n"] += 1
            return super().write_script(*a, **k)
    statuses = []
    w = _worker(tmp_path, mgr, writer_factory=lambda acc: NoCallWriter(),
                do_script=False, do_video=False)
    w.step_status.connect(lambda o, s, st: statuses.append((o, s, st)))
    with qtbot.waitSignal(w.done, timeout=5000):
        w.start()
    assert calls["n"] == 0                       # word never generated
    assert (1, "word", STATUS_SKIPPED) in statuses
    assert (1, "img_9x16", STATUS_SKIPPED) in statuses   # no prompt -> skipped
    assert w.wait(2000)
```

Extend `test_main_window.py`:

```python
def test_stats_label_updates_from_signals(qtbot):
    app = QApplication.instance() or QApplication([])
    win = MainWindow(AppConfig.load(CONFIG))
    qtbot.addWidget(win)
    win._reset_stats()
    win._on_run_totals(3, 1)
    win._on_script_finished(1, "done")
    win._on_script_finished(2, "failed")
    win._on_account_in_use("C1")
    text = win.stats_label.text()
    assert "Tổng: 3" in text and "Xong: 1" in text and "Bỏ qua: 1" in text
    assert "Lỗi: 1" in text and "Tài khoản: C1" in text


def test_script_started_fills_filename_column(qtbot):
    app = QApplication.instance() or QApplication([])
    win = MainWindow(AppConfig.load(CONFIG))
    qtbot.addWidget(win)
    win._on_script_started(7, "7.txt")
    row = win._row_for_ordinal(7)
    assert row is not None
    assert win.table.item(row, 0).text() == "7"
    assert win.table.item(row, 1).text() == "7.txt"   # Tên file column
```

- [ ] **Step 6: Run full suite (exit 0). Commit.**

```bash
cd "D:/Home/wf"
git add horizon_tool/gui/worker.py horizon_tool/gui/main_window.py horizon_tool/tests/test_script_run_worker.py horizon_tool/tests/test_main_window.py
git commit -m "feat(gui): live statistics, filename column, and Viết kịch bản gating"
```

---

### Task B: Plugin preview + Settings window

**Files:**
- Modify: `horizon_tool/core/config_loader.py` (add `save_config`)
- Create: `horizon_tool/gui/settings_window.py`
- Modify: `horizon_tool/gui/main_window.py` (Xem trước button + handler; wire Cài đặt)
- Test: extend `horizon_tool/tests/test_config_loader.py`, create `horizon_tool/tests/test_settings_window.py`, extend `horizon_tool/tests/test_main_window.py`

- [ ] **Step 1: Add `save_config` to `core/config_loader.py`**

Writes the canonical, commented `config.yaml` with the given values (comment-preserving; uses `json.dumps` for safe scalar quoting incl. embedded newlines, and a flow list for durations/qualities):

```python
import json


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
```

Note: the `{{PROMPT}}` in the f-string defaults renders literally as `{PROMPT}` (escaped braces) — required so the wrapper default stays valid.

- [ ] **Step 2: Test `save_config` round-trip** (extend `test_config_loader.py`)

```python
def test_save_config_roundtrips(tmp_path):
    from horizon_tool.core.config_loader import save_config
    original = load_yaml(CONFIG_DIR / "config.yaml")
    original["timeouts"]["element_wait_seconds"] = 45
    original["auto_resume"]["enabled"] = True
    out = tmp_path / "config.yaml"
    save_config(out, original)
    reloaded = load_yaml(out)
    assert reloaded["timeouts"]["element_wait_seconds"] == 45
    assert reloaded["auto_resume"]["enabled"] is True
    assert reloaded["grok"]["durations"] == original["grok"]["durations"]
    assert reloaded["chatgpt"]["image_wrapper_9x16"] == original["chatgpt"]["image_wrapper_9x16"]
```

- [ ] **Step 3: Create `gui/settings_window.py`**

```python
"""Settings dialog: edit the runtime knobs in config.yaml (Vietnamese UI)."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QFormLayout, QVBoxLayout, QDialogButtonBox, QSpinBox, QComboBox,
    QCheckBox, QLineEdit,
)

from horizon_tool.core.config_loader import AppConfig, save_config


class SettingsWindow(QDialog):
    """Edits a subset of config.yaml and saves it (comment-preserving)."""

    def __init__(self, config: AppConfig, config_path: Path, parent=None) -> None:
        super().__init__(parent)
        self.config_path = Path(config_path)
        self._cfg = deepcopy(config.raw)
        self.setWindowTitle("Cài đặt")
        self.resize(460, 460)

        form = QFormLayout()
        c, t, r, d, g, ar = (self._cfg.get(k, {}) for k in
                             ("chatgpt", "timeouts", "retry", "delays", "grok", "auto_resume"))

        self.send_mode = QComboBox()
        self.send_mode.addItems(["two_messages", "combined"])
        self.send_mode.setCurrentText(c.get("send_mode", "two_messages"))
        self.runtime_suffix = QLineEdit(c.get("runtime_suffix", ""))

        def spin(val, lo, hi):
            sb = QSpinBox(); sb.setRange(lo, hi); sb.setValue(int(val)); return sb

        self.element_wait = spin(t.get("element_wait_seconds", 30), 1, 600)
        self.response_wait = spin(t.get("response_wait_seconds", 600), 1, 3600)
        self.max_attempts = spin(r.get("max_attempts", 3), 1, 10)
        self.backoff = spin(r.get("backoff_base_seconds", 5), 0, 120)
        self.steps_min = spin(d.get("between_steps_min_seconds", 2), 0, 600)
        self.steps_max = spin(d.get("between_steps_max_seconds", 6), 0, 600)
        self.scripts_min = spin(d.get("between_scripts_min_seconds", 5), 0, 3600)
        self.scripts_max = spin(d.get("between_scripts_max_seconds", 15), 0, 3600)
        self.render_timeout = spin(g.get("render_timeout_seconds", 600), 10, 3600)
        self.auto_enabled = QCheckBox("Bật tự động Resume")
        self.auto_enabled.setChecked(bool(ar.get("enabled")))
        self.auto_interval = spin(ar.get("check_interval_minutes", 30), 1, 240)

        form.addRow("Cách gửi (ChatGPT):", self.send_mode)
        form.addRow("Chỉ dẫn phụ (runtime suffix):", self.runtime_suffix)
        form.addRow("Timeout chờ phần tử (s):", self.element_wait)
        form.addRow("Timeout chờ phản hồi (s):", self.response_wait)
        form.addRow("Số lần thử lại:", self.max_attempts)
        form.addRow("Backoff cơ bản (s):", self.backoff)
        form.addRow("Trễ giữa bước — nhỏ nhất (s):", self.steps_min)
        form.addRow("Trễ giữa bước — lớn nhất (s):", self.steps_max)
        form.addRow("Trễ giữa kịch bản — nhỏ nhất (s):", self.scripts_min)
        form.addRow("Trễ giữa kịch bản — lớn nhất (s):", self.scripts_max)
        form.addRow("Timeout render video Grok (s):", self.render_timeout)
        form.addRow("", self.auto_enabled)
        form.addRow("Chu kỳ tự động Resume (phút):", self.auto_interval)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(buttons)

    def collect(self) -> dict:
        """Return an updated config dict from the form values."""
        cfg = deepcopy(self._cfg)
        cfg.setdefault("chatgpt", {})["send_mode"] = self.send_mode.currentText()
        cfg["chatgpt"]["runtime_suffix"] = self.runtime_suffix.text()
        cfg.setdefault("timeouts", {})["element_wait_seconds"] = self.element_wait.value()
        cfg["timeouts"]["response_wait_seconds"] = self.response_wait.value()
        cfg.setdefault("retry", {})["max_attempts"] = self.max_attempts.value()
        cfg["retry"]["backoff_base_seconds"] = self.backoff.value()
        dd = cfg.setdefault("delays", {})
        dd["between_steps_min_seconds"] = self.steps_min.value()
        dd["between_steps_max_seconds"] = self.steps_max.value()
        dd["between_scripts_min_seconds"] = self.scripts_min.value()
        dd["between_scripts_max_seconds"] = self.scripts_max.value()
        cfg.setdefault("grok", {})["render_timeout_seconds"] = self.render_timeout.value()
        ar = cfg.setdefault("auto_resume", {})
        ar["enabled"] = self.auto_enabled.isChecked()
        ar["check_interval_minutes"] = self.auto_interval.value()
        return cfg

    def save(self) -> None:
        save_config(self.config_path, self.collect())
        self.accept()
```

- [ ] **Step 4: Wire into `MainWindow`** (`gui/main_window.py`)

Add a `CONFIG_PATH` constant near `SELECTORS_PATH`:

```python
CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "config.yaml"
```

Add a **Xem trước** button in `_build_options_group` (next to Mở file / Tải lại):

```python
        preview_btn = QPushButton("Xem trước")
        preview_btn.clicked.connect(self.preview_selected_plugin)
        # add preview_btn to the same layout, after open_btn
```

Add handlers (behavior section), and wire the Settings button:

```python
    def _selected_plugin_text(self) -> str | None:
        path = self.plugin_combo.currentData()
        if not path:
            return None
        try:
            return read_plugin_text(Path(path))
        except Exception as exc:  # noqa: BLE001
            return f"(Không đọc được plugin: {exc})"

    def preview_selected_plugin(self) -> None:
        text = self._selected_plugin_text()
        if text is None:
            self.append_log("Chưa chọn plugin để xem trước.")
            return
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QPlainTextEdit
        dlg = QDialog(self)
        dlg.setWindowTitle("Xem trước plugin")
        dlg.resize(720, 600)
        lay = QVBoxLayout(dlg)
        viewer = QPlainTextEdit()
        viewer.setReadOnly(True)
        viewer.setPlainText(text)
        lay.addWidget(viewer)
        dlg.exec()

    def open_settings_window(self) -> None:
        from horizon_tool.gui.settings_window import SettingsWindow
        dlg = SettingsWindow(self.config, CONFIG_PATH, self)
        if dlg.exec():
            self.config = AppConfig.load(CONFIG_PATH)   # reload for next run
            self.append_log("Đã lưu cài đặt.")
```

Connect the settings button in `_build_controls`:

```python
        self.settings_btn.clicked.connect(self.open_settings_window)
```

- [ ] **Step 5: Tests** — `test_settings_window.py`:

```python
import pytest
import yaml
from pathlib import Path

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402
from horizon_tool.core.config_loader import AppConfig  # noqa: E402
from horizon_tool.gui.settings_window import SettingsWindow  # noqa: E402

CONFIG = Path(__file__).resolve().parents[1] / "config" / "config.yaml"


def test_settings_saves_changes(qtbot, tmp_path):
    app = QApplication.instance() or QApplication([])
    cfg = AppConfig.load(CONFIG)
    out = tmp_path / "config.yaml"
    win = SettingsWindow(cfg, out)
    qtbot.addWidget(win)
    win.element_wait.setValue(42)
    win.auto_enabled.setChecked(True)
    win.send_mode.setCurrentText("combined")
    win.save()
    saved = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert saved["timeouts"]["element_wait_seconds"] == 42
    assert saved["auto_resume"]["enabled"] is True
    assert saved["chatgpt"]["send_mode"] == "combined"
    # untouched values preserved
    assert saved["grok"]["qualities"] == cfg.video_qualities
```

Extend `test_main_window.py`:

```python
def test_open_settings_window(qtbot, tmp_path, monkeypatch):
    import horizon_tool.gui.main_window as mw
    monkeypatch.setattr(mw, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(mw, "PROFILES_DIR", tmp_path / "profiles")
    app = QApplication.instance() or QApplication([])
    win = mw.MainWindow(AppConfig.load(CONFIG))
    qtbot.addWidget(win)
    opened = {}
    # Don't actually exec a modal dialog in tests: stub SettingsWindow.exec.
    import horizon_tool.gui.settings_window as sw
    monkeypatch.setattr(sw.SettingsWindow, "exec", lambda self: opened.setdefault("ok", True) or 0)
    win.open_settings_window()
    assert opened == {"ok": True}


def test_preview_plugin_reads_selected(qtbot, tmp_path, monkeypatch):
    import horizon_tool.gui.main_window as mw
    monkeypatch.setattr(mw, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(mw, "PROFILES_DIR", tmp_path / "profiles")
    app = QApplication.instance() or QApplication([])
    win = mw.MainWindow(AppConfig.load(CONFIG))
    qtbot.addWidget(win)
    p = tmp_path / "v11.txt"
    p.write_text("NỘI DUNG PLUGIN", encoding="utf-8")
    win.plugin_combo.addItem("v11.txt", userData=str(p))
    win.plugin_combo.setCurrentText("v11.txt")
    assert win._selected_plugin_text() == "NỘI DUNG PLUGIN"
```

- [ ] **Step 6: Run full suite (exit 0), smoke, commit.**

Smoke (offscreen): build MainWindow, call `open_settings_window` after stubbing exec, and `_selected_plugin_text` — or just assert the app constructs. Then:

```bash
cd "D:/Home/wf"
git add horizon_tool/core/config_loader.py horizon_tool/gui/settings_window.py horizon_tool/gui/main_window.py horizon_tool/tests/test_config_loader.py horizon_tool/tests/test_settings_window.py horizon_tool/tests/test_main_window.py
git commit -m "feat(gui): plugin preview dialog and Settings window bound to config.yaml"
```

---

## Self-Review
- §4 statistics (total/done/skipped/failed + elapsed + current account) → Task A ✓
- §4 progress table "Tên file" populated → Task A ✓
- §4 per-step checkbox "Viết kịch bản" gates the word step → Task A ✓
- §5 PL-04 "Xem trước" → Task B ✓
- §4 "Cài đặt" window (edits config.yaml, comment-preserving save) → Task B ✓
- Deferred by plan (unchanged): "Sửa" plugin editor (Phase 8), OUT-04 conflict dialog (Phase 7).
- No live selectors touched; everything testable with fakes/offscreen Qt.
