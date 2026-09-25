"""Main application window (Phase 1 skeleton).

Vietnamese UI. Wires config-driven dropdowns, folder pickers, plugin dropdown,
per-step checkboxes, control buttons, a progress table, a live log pane, and
statistics. Long work runs on PipelineWorker so the GUI never freezes.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QElapsedTimer, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QLineEdit, QPushButton, QComboBox, QCheckBox, QPlainTextEdit,
    QTableWidget, QTableWidgetItem, QFileDialog, QGroupBox,
)

from horizon_tool.automation.browser import BrowserSession
from horizon_tool.automation.chatgpt import ChatGPTWriter
from horizon_tool.core.account_manager import AccountManager, STATUS_QUOTA, STATUS_READY
from horizon_tool.core.statuses import STATUS_DONE, STATUS_FAILED
from horizon_tool.core.config_loader import AppConfig, load_yaml
from horizon_tool.core.plugin_manager import (
    list_plugins, read_plugin_text, apply_variables,
    plugin_hash as compute_plugin_hash,  # aliased so the kwarg name can't shadow it
)
from horizon_tool.gui.accounts_window import AccountsWindow
from horizon_tool.gui.worker import PipelineWorker, ScriptRunWorker

PLUGINS_DIR = Path(__file__).resolve().parents[1] / "plugins"
STATE_DIR = Path(__file__).resolve().parents[1] / "state"
PROFILES_DIR = Path(__file__).resolve().parents[1] / "profiles"
SELECTORS_PATH = Path(__file__).resolve().parents[1] / "config" / "selectors.yaml"
STEP_COLUMNS = ["STT", "Tên file", "Kịch bản", "Ảnh 9:16", "Ảnh 16:9", "Video"]
STEP_COLUMN_INDEX = {"word": 2, "img_9x16": 3, "img_16x9": 4, "video": 5}


class MainWindow(QMainWindow):
    """Top-level window assembling all Phase 1 controls."""

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.config = config
        self.worker: PipelineWorker | ScriptRunWorker | None = None
        self.account_manager = AccountManager(
            STATE_DIR / "accounts.json", PROFILES_DIR)
        self.accounts_window: AccountsWindow | None = None
        self._auto_resume_timer = QTimer(self)
        self._auto_resume_timer.timeout.connect(self._auto_resume_tick)
        self._stats = {"total": 0, "skipped": 0, "done": 0, "failed": 0, "account": "-"}
        self._elapsed = QElapsedTimer()
        self._stats_timer = QTimer(self)
        self._stats_timer.timeout.connect(self._refresh_stats_label)
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
        self._set_running_state(False)  # idle: only Start enabled

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
        open_btn.clicked.connect(self.open_selected_plugin)
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
        self.start_btn = QPushButton("Bắt đầu")
        self.pause_btn = QPushButton("Tạm dừng")
        self.resume_btn = QPushButton("Tiếp tục")
        self.stop_btn = QPushButton("Dừng")
        self.accounts_btn = QPushButton("Quản lý tài khoản")
        self.settings_btn = QPushButton("Cài đặt")
        self.start_btn.clicked.connect(self.on_start)
        self.pause_btn.clicked.connect(lambda: self._set_paused(True))
        self.resume_btn.clicked.connect(self.on_resume)
        self.stop_btn.clicked.connect(self.on_stop)
        self.accounts_btn.clicked.connect(self.open_accounts_window)
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
        self.stats_label = QLabel(
            "Tổng: 0 | Xong: 0 | Bỏ qua: 0 | Lỗi: 0 | Thời gian: 00:00 | Tài khoản: -")
        return self.stats_label

    # ----- behavior -------------------------------------------------------
    def refresh_plugins(self) -> None:
        self.plugin_combo.clear()
        for p in list_plugins(PLUGINS_DIR):
            self.plugin_combo.addItem(p.name, userData=str(p))

    def open_selected_plugin(self) -> None:
        """Open the selected plugin file with the OS default app (PL-04)."""
        path = self.plugin_combo.currentData()
        if not path:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _pick_folder(self, target: QLineEdit) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục")
        if folder:
            target.setText(folder)

    def append_log(self, message: str) -> None:
        self.log_pane.appendPlainText(message)

    def on_start(self) -> None:
        self._launch_run(resume=False)

    def on_resume(self) -> None:
        # Resume a paused running worker, or start a fresh worker in resume mode.
        if self.worker is not None and self.worker.isRunning():
            self._set_paused(False)
            return
        self._launch_run(resume=True)

    def _launch_run(self, *, resume: bool) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        input_dir = self.input_edit.text().strip()
        output_dir = self.output_edit.text().strip()
        plugin_path = self.plugin_combo.currentData()
        if not input_dir or not output_dir or not plugin_path:
            self.append_log("Hãy chọn thư mục input, output và plugin trước khi chạy.")
            return
        selectors = load_yaml(SELECTORS_PATH)
        raw_plugin = read_plugin_text(Path(plugin_path))
        plugin_text = apply_variables(raw_plugin, {
            "VIDEO_DURATION": self.duration_combo.currentText(),
            "VIDEO_QUALITY": self.quality_combo.currentText()})

        el_ms = self.config.raw.get("timeouts", {}).get("element_wait_seconds", 30) * 1000

        def writer_factory(account):
            session = BrowserSession(account.profile_dir, headless=False, element_timeout_ms=el_ms)
            session.start()
            return ChatGPTWriter(session, selectors, self.config.raw)

        def video_maker_factory(account):
            from horizon_tool.automation.grok import GrokVideoMaker
            session = BrowserSession(account.profile_dir, headless=False, element_timeout_ms=el_ms)
            session.start()
            return GrokVideoMaker(session, selectors, self.config.raw)

        if not resume:
            self.table.setRowCount(0)
        self.worker = ScriptRunWorker(
            input_dir=input_dir, output_dir=output_dir,
            selection=self.range_edit.text().strip(), plugin_text=plugin_text,
            heading_regexes=selectors["section_headings"], account_manager=self.account_manager,
            writer_factory=writer_factory, video_maker_factory=video_maker_factory,
            do_script=self.step_script.isChecked(),
            do_9x16=self.step_img_9x16.isChecked(), do_16x9=self.step_thumb_16x9.isChecked(),
            do_video=self.step_video.isChecked(),
            video_duration=self.duration_combo.currentText(),
            video_quality=self.quality_combo.currentText(),
            plugin_name=self.plugin_combo.currentText(),
            plugin_hash=compute_plugin_hash(raw_plugin),
            state_path=str(Path(output_dir) / "run_state.json"), resume=resume,
            config=self.config.raw, parent=self)
        self.worker.log.connect(self.append_log)
        self.worker.step_status.connect(self._on_step_status)
        self.worker.exhausted.connect(self._on_exhausted)
        self.worker.done.connect(self._on_worker_done)
        self.worker.run_totals.connect(self._on_run_totals)
        self.worker.script_started.connect(self._on_script_started)
        self.worker.script_finished.connect(self._on_script_finished)
        self.worker.account_in_use.connect(self._on_account_in_use)
        self._reset_stats()
        self._stats_timer.start(1000)
        self._set_running_state(True)
        self.worker.start()

    def _on_exhausted(self, service: str) -> None:
        self.append_log(f"Đã hết tài khoản {service}. Nhấn Tiếp tục khi quota hồi, hoặc bật tự động Resume trong Cài đặt.")
        auto = self.config.raw.get("auto_resume", {})
        if auto.get("enabled"):
            minutes = int(auto.get("check_interval_minutes", 30))
            self._auto_resume_timer.start(max(1, minutes) * 60 * 1000)

    def _auto_resume_tick(self) -> None:
        # Re-check quota accounts: mark them ready again and resume the run.
        if self.worker is not None and self.worker.isRunning():
            return
        reset = 0
        for acc in self.account_manager.list():
            if acc.status == STATUS_QUOTA:
                self.account_manager.set_status(acc.id, STATUS_READY)
                reset += 1
        if reset:
            self.append_log(f"Tự động Resume: đã đặt lại {reset} tài khoản hết quota.")
            self._auto_resume_timer.stop()
            self.on_resume()

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

    def _row_for_ordinal(self, ordinal: int) -> int | None:
        """Return the existing table row for a script ordinal, or None."""
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is not None and item.text() == str(ordinal):
                return row
        return None

    def _set_paused(self, paused: bool) -> None:
        if self.worker is not None and hasattr(self.worker, "set_paused"):
            self.worker.set_paused(paused)
        # Only one of Pause/Resume is actionable at a time.
        self.pause_btn.setEnabled(not paused)
        self.resume_btn.setEnabled(paused)

    def on_stop(self) -> None:
        if self.worker is not None:
            self.worker.request_stop()

    def _on_worker_done(self) -> None:
        """Runs on the GUI thread (queued signal) when the worker finishes."""
        self._auto_resume_timer.stop()
        self._stats_timer.stop()
        self._refresh_stats_label()
        self._set_running_state(False)

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
        self._stats["failed" if overall == STATUS_FAILED else "done"] += 1
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

    def _set_running_state(self, running: bool) -> None:
        """Toggle control buttons so a run cannot be started twice.

        On start, only Pause is actionable (nothing is paused yet); Resume
        becomes actionable after Pause is pressed (see _set_paused).
        """
        self.start_btn.setEnabled(not running)
        self.pause_btn.setEnabled(running)
        self.resume_btn.setEnabled(False)
        self.stop_btn.setEnabled(running)

    def open_accounts_window(self) -> None:
        """Open (or re-show) the accounts management window."""
        if self.accounts_window is None:
            self.accounts_window = AccountsWindow(self.account_manager, self)
        self.accounts_window.show()
        self.accounts_window.raise_()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override name
        """Stop a running worker cleanly before the window closes."""
        if self.worker is not None and self.worker.isRunning():
            self.worker.request_stop()
            self.worker.wait(3000)
        super().closeEvent(event)
