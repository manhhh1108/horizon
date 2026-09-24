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

    durations = [win.duration_combo.itemText(i) for i in range(win.duration_combo.count())]
    assert durations == ["10s", "15s", "20s"]
    qualities = [win.quality_combo.itemText(i) for i in range(win.quality_combo.count())]
    assert qualities == ["720p", "1080p"]

    assert win.step_script.isChecked()
    assert win.step_img_9x16.isChecked()
    assert win.step_thumb_16x9.isChecked()
    assert win.step_video.isChecked()

    assert win.start_btn is not None
    assert win.stop_btn is not None
