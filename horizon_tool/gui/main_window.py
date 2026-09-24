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
