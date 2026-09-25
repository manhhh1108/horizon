# Horizon X Media Tool — OUT-04 output-conflict + PL-07 plugin editor

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`).

**Goal:** (A) OUT-04 — on a fresh run, if a script's output folder already exists, ask the user once: **Ghi đè / Bỏ qua / Tạo mới (hậu tố thời gian)**, and apply it. (B) PL-07 — a **Sửa** button opening an in-tool plugin editor for `.txt/.md` plugins (edit + save, auto-backing up the previous version to `plugins/_history/`).

**Scope note:** `.plugin` **encryption (SEC-08)** stays in Phase 8; the editor here handles plaintext `.txt/.md` only (a `.docx` selection is redirected to "Mở file"/Word).

**Architecture:** OUT-04 reuses the tested `output_manager.prepare_output_dir(root, ordinal, policy, suffix)`; the worker takes a `conflict_policy` + `run_timestamp` and skips a script when the policy is SKIP and the folder exists. The GUI detects conflicts before launch and asks once. PL-07 adds `plugin_manager.backup_plugin` + `save_plugin_text` (pure, tested) behind a small `gui/plugin_editor.py` dialog.

**Tech Stack:** Python 3.10-compatible, PySide6, pytest. **Base branch:** `main`. Work branch: `feat-out04-plugin-editor`.

---

### Task A: OUT-04 output-folder conflict handling

**Files:**
- Modify: `horizon_tool/gui/worker.py` (conflict_policy + run_timestamp; use prepare_output_dir; skip on None)
- Modify: `horizon_tool/gui/main_window.py` (detect conflicts, ask once, pass policy; count "Bỏ qua")
- Test: extend `horizon_tool/tests/test_script_run_worker.py`, `horizon_tool/tests/test_main_window.py`

- [ ] **Step 1: Worker — accept + apply a conflict policy**

Import the policy constants + helper at the top of `worker.py`:

```python
from horizon_tool.core.output_manager import output_paths, prepare_output_dir, OVERWRITE, SKIP, TIMESTAMP
```

Add constructor params (near the other flags) and store them:

```python
                 conflict_policy: str = OVERWRITE, run_timestamp: str = "",
```
```python
        self._conflict_policy = conflict_policy
        self._run_timestamp = run_timestamp
```

In `run()`, replace the per-script `out_dir = self._output_dir / str(ordinal); out_dir.mkdir(...)` with policy-aware resolution + skip:

```python
            ordinal = script.ordinal
            out_dir = prepare_output_dir(
                self._output_dir, ordinal, self._conflict_policy,
                suffix=self._run_timestamp or None)
            if out_dir is None:  # SKIP policy + folder exists
                self.script_started.emit(ordinal, script.path.name)
                self.step_status.emit(ordinal, "word", STATUS_SKIPPED)
                self.log.emit(f"Bỏ qua kịch bản {ordinal}: thư mục output đã tồn tại.")
                self.script_finished.emit(ordinal, STATUS_SKIPPED)
                continue
            self.script_started.emit(ordinal, script.path.name)
```

(Remove the now-duplicate `self.script_started.emit(...)` / `out_dir.mkdir(...)` lines that followed; `prepare_output_dir` already creates the dir. Keep the rest of the per-script body — `started = time.monotonic()` etc.)

- [ ] **Step 2: main_window — emit STATUS_SKIPPED into the "Bỏ qua" counter**

`_on_script_finished` currently maps done/failed. Make it handle skipped too:

```python
    def _on_script_finished(self, ordinal: int, overall: str) -> None:
        key = {STATUS_DONE: "done", STATUS_FAILED: "failed",
               STATUS_SKIPPED: "skipped"}.get(overall, "done")
        self._stats[key] += 1
        self._refresh_stats_label()
```

Add `STATUS_SKIPPED` to the statuses import in `main_window.py`.

- [ ] **Step 3: main_window — detect conflicts and ask once in `_launch_run`**

Add imports:

```python
from datetime import datetime
from PySide6.QtWidgets import QMessageBox
from horizon_tool.core.input_reader import scan_input_folder, filter_by_selection
from horizon_tool.core.output_manager import OVERWRITE, SKIP, TIMESTAMP
```

Add helpers:

```python
    def _existing_output_ordinals(self, input_dir: str, output_dir: str, selection: str) -> list[int]:
        """Ordinals whose output/<n> folder already exists (fresh-run conflict)."""
        try:
            scripts, _ = scan_input_folder(Path(input_dir))
            scripts = filter_by_selection(scripts, selection)
        except Exception:  # noqa: BLE001 - bad range etc. handled later by the run
            return []
        out = Path(output_dir)
        return [s.ordinal for s in scripts if (out / str(s.ordinal)).exists()]

    def _ask_conflict_policy(self, count: int):
        """Ask how to handle existing output folders. Returns (policy, suffix) or None if cancelled."""
        box = QMessageBox(self)
        box.setWindowTitle("Thư mục output đã tồn tại")
        box.setText(f"{count} thư mục output đã tồn tại. Bạn muốn làm gì?")
        overwrite = box.addButton("Ghi đè", QMessageBox.AcceptRole)
        skip = box.addButton("Bỏ qua", QMessageBox.DestructiveRole)
        newdir = box.addButton("Tạo mới (hậu tố thời gian)", QMessageBox.ActionRole)
        box.addButton("Hủy", QMessageBox.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is overwrite:
            return (OVERWRITE, "")
        if clicked is skip:
            return (SKIP, "")
        if clicked is newdir:
            return (TIMESTAMP, datetime.now().strftime("%Y%m%d_%H%M%S"))
        return None
```

In `_launch_run`, after the input/output/plugin guard and before building the worker, on a fresh (non-resume) run resolve the policy:

```python
        conflict_policy, run_timestamp = OVERWRITE, ""
        if not resume:
            existing = self._existing_output_ordinals(input_dir, output_dir,
                                                      self.range_edit.text().strip())
            if existing:
                choice = self._ask_conflict_policy(len(existing))
                if choice is None:
                    self.append_log("Đã hủy chạy (thư mục output đã tồn tại).")
                    return
                conflict_policy, run_timestamp = choice
```

Pass into the worker construction kwargs:

```python
            conflict_policy=conflict_policy, run_timestamp=run_timestamp,
```

- [ ] **Step 4: Tests**

`test_script_run_worker.py`:

```python
def test_conflict_skip_skips_existing_folder(qtbot, tmp_path):
    from horizon_tool.core.output_manager import SKIP
    app = QCoreApplication.instance() or QCoreApplication([])
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "1.txt").write_text("k", encoding="utf-8")
    (tmp_path / "out" / "1").mkdir(parents=True)   # pre-existing conflict
    mgr = _mgr(tmp_path)
    calls = {"n": 0}
    class CountWriter(FakeWriter):
        def write_script(self, *a, **k):
            calls["n"] += 1
            return super().write_script(*a, **k)
    finished = []
    w = _worker(tmp_path, mgr, writer_factory=lambda acc: CountWriter(),
                conflict_policy=SKIP)
    w.script_finished.connect(lambda o, st: finished.append((o, st)))
    with qtbot.waitSignal(w.done, timeout=5000):
        w.start()
    assert calls["n"] == 0                       # never processed
    assert finished == [(1, STATUS_SKIPPED)]
    assert w.wait(2000)


def test_conflict_timestamp_uses_suffixed_folder(qtbot, tmp_path):
    from horizon_tool.core.output_manager import TIMESTAMP
    app = QCoreApplication.instance() or QCoreApplication([])
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "1.txt").write_text("k", encoding="utf-8")
    (tmp_path / "out" / "1").mkdir(parents=True)   # conflict -> use 1_<ts>
    mgr = _mgr(tmp_path)
    w = _worker(tmp_path, mgr, do_video=False,
                conflict_policy=TIMESTAMP, run_timestamp="20260925_101500")
    with qtbot.waitSignal(w.done, timeout=5000):
        w.start()
    assert (tmp_path / "out" / "1_20260925_101500" / "1.docx").exists()
    assert w.wait(2000)
```

`test_main_window.py`:

```python
def test_existing_output_ordinals_detects_conflicts(qtbot, tmp_path):
    app = QApplication.instance() or QApplication([])
    win = MainWindow(AppConfig.load(CONFIG))
    qtbot.addWidget(win)
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "1.txt").write_text("a", encoding="utf-8")
    (tmp_path / "in" / "2.txt").write_text("b", encoding="utf-8")
    (tmp_path / "out" / "1").mkdir(parents=True)   # only #1 conflicts
    got = win._existing_output_ordinals(str(tmp_path / "in"), str(tmp_path / "out"), "")
    assert got == [1]


def test_script_finished_counts_skipped(qtbot):
    from horizon_tool.core.statuses import STATUS_SKIPPED
    app = QApplication.instance() or QApplication([])
    win = MainWindow(AppConfig.load(CONFIG))
    qtbot.addWidget(win)
    win._reset_stats()
    win._on_script_finished(1, STATUS_SKIPPED)
    assert "Bỏ qua: 1" in win.stats_label.text()
```

- [ ] **Step 5: Run full suite (exit 0). Commit.**

```bash
git add horizon_tool/gui/worker.py horizon_tool/gui/main_window.py horizon_tool/tests/test_script_run_worker.py horizon_tool/tests/test_main_window.py
git commit -m "feat(out-04): ask on existing output folder (overwrite/skip/timestamp)"
```

---

### Task B: PL-07 plugin editor ("Sửa")

**Files:**
- Modify: `horizon_tool/core/plugin_manager.py` (backup_plugin + save_plugin_text)
- Create: `horizon_tool/gui/plugin_editor.py`
- Modify: `horizon_tool/gui/main_window.py` (Sửa button + handler)
- Test: extend `horizon_tool/tests/test_plugin_manager.py`, create `horizon_tool/tests/test_plugin_editor.py`, extend `horizon_tool/tests/test_main_window.py`

- [ ] **Step 1: plugin_manager — backup + save helpers**

```python
import shutil
from datetime import datetime

HISTORY_DIRNAME = "_history"
EDITABLE_SUFFIXES = {".txt", ".md"}


def backup_plugin(path: Path) -> Path | None:
    """Copy the current plugin file into plugins/_history/ with a timestamp.

    Returns the backup path, or None if the source doesn't exist yet.
    """
    path = Path(path)
    if not path.exists():
        return None
    history = path.parent / HISTORY_DIRNAME
    history.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = history / f"{path.stem}.{stamp}{path.suffix}"
    shutil.copy2(path, backup)
    return backup


def save_plugin_text(path: Path, text: str) -> None:
    """Save edited plugin text, backing up the previous version first (PL-07).

    Only plaintext plugins (.txt/.md) are editable in-tool; .docx/.plugin raise.
    """
    path = Path(path)
    if path.suffix.lower() not in EDITABLE_SUFFIXES:
        raise ValueError(f"Không sửa được trong tool (chỉ .txt/.md): {path.suffix}")
    backup_plugin(path)
    path.write_text(text, encoding="utf-8")
```

- [ ] **Step 2: Test the helpers** (extend `test_plugin_manager.py`)

```python
def test_backup_and_save_plugin_text(tmp_path):
    from horizon_tool.core.plugin_manager import save_plugin_text, HISTORY_DIRNAME
    p = tmp_path / "v11.txt"
    p.write_text("bản cũ", encoding="utf-8")
    save_plugin_text(p, "bản mới")
    assert p.read_text(encoding="utf-8") == "bản mới"
    backups = list((tmp_path / HISTORY_DIRNAME).glob("v11.*.txt"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "bản cũ"   # old version kept


def test_save_plugin_text_rejects_docx(tmp_path):
    import pytest
    from horizon_tool.core.plugin_manager import save_plugin_text
    p = tmp_path / "v11.docx"
    p.write_bytes(b"x")
    with pytest.raises(ValueError):
        save_plugin_text(p, "text")


def test_save_plugin_text_no_backup_when_new(tmp_path):
    from horizon_tool.core.plugin_manager import save_plugin_text, HISTORY_DIRNAME
    p = tmp_path / "new.md"
    save_plugin_text(p, "nội dung")   # file didn't exist -> no backup
    assert p.read_text(encoding="utf-8") == "nội dung"
    assert not (tmp_path / HISTORY_DIRNAME).exists()
```

- [ ] **Step 3: Create `gui/plugin_editor.py`**

```python
"""In-tool plugin editor (PL-07) for plaintext .txt/.md plugins."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QPlainTextEdit, QDialogButtonBox,
)

from horizon_tool.core.plugin_manager import read_plugin_text, save_plugin_text


class PluginEditorDialog(QDialog):
    """Edit and save a plaintext plugin, backing up the previous version."""

    def __init__(self, path: Path, parent=None) -> None:
        super().__init__(parent)
        self.path = Path(path)
        self.setWindowTitle(f"Sửa plugin — {self.path.name}")
        self.resize(760, 640)
        self.editor = QPlainTextEdit()
        self.editor.setPlainText(read_plugin_text(self.path))
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        root = QVBoxLayout(self)
        root.addWidget(self.editor)
        root.addWidget(buttons)

    def save(self) -> None:
        save_plugin_text(self.path, self.editor.toPlainText())
        self.accept()
```

- [ ] **Step 4: main_window — "Sửa" button + handler**

In `_build_options_group`, add the button next to "Xem trước":

```python
        edit_btn = QPushButton("Sửa")
        edit_btn.clicked.connect(self.edit_selected_plugin)
        # add edit_btn after preview_btn
```

Add the handler:

```python
    def edit_selected_plugin(self) -> None:
        """Open the in-tool editor for a .txt/.md plugin (PL-07)."""
        path = self.plugin_combo.currentData()
        if not path:
            self.append_log("Chưa chọn plugin để sửa.")
            return
        if Path(path).suffix.lower() not in {".txt", ".md"}:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(
                self, "Sửa plugin",
                "Chỉ sửa được .txt/.md trong tool. Với .docx hãy dùng 'Mở file' (Word).")
            return
        from horizon_tool.gui.plugin_editor import PluginEditorDialog
        dlg = PluginEditorDialog(Path(path), self)
        if dlg.exec():
            self.append_log("Đã lưu plugin (bản cũ đã sao lưu vào _history).")
```

- [ ] **Step 5: Tests** — `test_plugin_editor.py`:

```python
import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402
from horizon_tool.gui.plugin_editor import PluginEditorDialog  # noqa: E402


def test_editor_loads_and_saves(qtbot, tmp_path):
    app = QApplication.instance() or QApplication([])
    p = tmp_path / "v11.txt"
    p.write_text("cũ", encoding="utf-8")
    dlg = PluginEditorDialog(p)
    qtbot.addWidget(dlg)
    assert dlg.editor.toPlainText() == "cũ"
    dlg.editor.setPlainText("mới")
    dlg.save()          # writes + backs up
    assert p.read_text(encoding="utf-8") == "mới"
```

Extend `test_main_window.py`:

```python
def test_edit_plugin_rejects_docx(qtbot, tmp_path, monkeypatch):
    import horizon_tool.gui.main_window as mw
    monkeypatch.setattr(mw, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(mw, "PROFILES_DIR", tmp_path / "profiles")
    app = QApplication.instance() or QApplication([])
    win = mw.MainWindow(AppConfig.load(CONFIG))
    qtbot.addWidget(win)
    p = tmp_path / "v11.docx"
    p.write_bytes(b"x")
    win.plugin_combo.addItem("v11.docx", userData=str(p))
    win.plugin_combo.setCurrentText("v11.docx")
    shown = {}
    import PySide6.QtWidgets as W
    monkeypatch.setattr(W.QMessageBox, "information",
                        lambda *a, **k: shown.setdefault("msg", True))
    win.edit_selected_plugin()
    assert shown.get("msg") is True   # docx -> guided to Word, editor not opened
```

- [ ] **Step 6: Run full suite (exit 0), commit.**

```bash
git add horizon_tool/core/plugin_manager.py horizon_tool/gui/plugin_editor.py horizon_tool/gui/main_window.py horizon_tool/tests/test_plugin_manager.py horizon_tool/tests/test_plugin_editor.py horizon_tool/tests/test_main_window.py
git commit -m "feat(pl-07): in-tool plugin editor for .txt/.md with _history backup"
```

---

## Self-Review
- OUT-04: worker applies overwrite/skip/timestamp; GUI asks once on a fresh run; skipped scripts counted → Task A ✓
- PL-07: Sửa button + editor for .txt/.md, previous version backed up to plugins/_history/ → Task B ✓
- Deferred: `.plugin` encryption (SEC-08) stays Phase 8; the editor extends to `.plugin` then.
- No live selectors touched; everything testable offscreen/with fakes.
