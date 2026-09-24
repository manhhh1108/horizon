"""Main application window (Phase 1 skeleton).

Vietnamese UI. Wires config-driven dropdowns, folder pickers, plugin dropdown,
per-step checkboxes, control buttons, a progress table, a live log pane, and
statistics. Long work runs on PipelineWorker so the GUI never freezes.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QLineEdit, QPushButton, QComboBox, QCheckBox, QPlainTextEdit,
    QTableWidget, QTableWidgetItem, QFileDialog, QGroupBox,
)

from horizon_tool.core.account_manager import AccountManager
from horizon_tool.core.config_loader import AppConfig
from horizon_tool.core.plugin_manager import list_plugins
from horizon_tool.gui.accounts_window import AccountsWindow
from horizon_tool.gui.worker import PipelineWorker

PLUGINS_DIR = Path(__file__).resolve().parents[1] / "plugins"
STATE_DIR = Path(__file__).resolve().parents[1] / "state"
PROFILES_DIR = Path(__file__).resolve().parents[1] / "profiles"
STEP_COLUMNS = ["STT", "Tên file", "Kịch bản", "Ảnh 9:16", "Ảnh 16:9", "Video"]


class MainWindow(QMainWindow):
    """Top-level window assembling all Phase 1 controls."""

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.config = config
        self.worker: PipelineWorker | None = None
        self.account_manager = AccountManager(
            STATE_DIR / "accounts.json", PROFILES_DIR)
        self.accounts_window: AccountsWindow | None = None
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
        self.resume_btn.clicked.connect(lambda: self._set_paused(False))
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
        self.stats_label = QLabel("Tổng: 0 | Xong: 0 | Bỏ qua: 0 | Lỗi: 0")
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
        # Phase 1: run the stub worker over a dummy list to prove wiring.
        if self.worker is not None and self.worker.isRunning():
            return  # ignore re-clicks while a run is in progress
        self.table.setRowCount(0)
        self.worker = PipelineWorker(scripts=[1, 2, 3])
        self.worker.log.connect(self.append_log)
        self.worker.progress.connect(self._on_progress)
        self.worker.done.connect(self._on_worker_done)
        self._set_running_state(True)
        self.worker.start()

    def _on_progress(self, ordinal: int, status: str) -> None:
        """Append a progress row (runs on the GUI thread via a queued signal)."""
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(str(ordinal)))
        self.table.setItem(row, 2, QTableWidgetItem(status))

    def _set_paused(self, paused: bool) -> None:
        if self.worker is None:
            return
        self.worker.set_paused(paused)
        # Only one of Pause/Resume is actionable at a time.
        self.pause_btn.setEnabled(not paused)
        self.resume_btn.setEnabled(paused)

    def on_stop(self) -> None:
        if self.worker is not None:
            self.worker.request_stop()

    def _on_worker_done(self) -> None:
        """Runs on the GUI thread (queued signal) when the worker finishes."""
        self._set_running_state(False)

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
