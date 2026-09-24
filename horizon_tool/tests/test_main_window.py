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

    # Dropdowns are populated FROM config (wiring), and config holds the
    # expected Phase-1 defaults (content).
    durations = [win.duration_combo.itemText(i) for i in range(win.duration_combo.count())]
    qualities = [win.quality_combo.itemText(i) for i in range(win.quality_combo.count())]
    assert durations == cfg.video_durations == ["10s", "15s", "20s"]
    assert qualities == cfg.video_qualities == ["720p", "1080p"]

    assert win.step_script.isChecked()
    assert win.step_img_9x16.isChecked()
    assert win.step_thumb_16x9.isChecked()
    assert win.step_video.isChecked()

    assert win.start_btn is not None
    assert win.stop_btn is not None


def test_idle_state_only_start_enabled(qtbot):
    app = QApplication.instance() or QApplication([])
    win = MainWindow(AppConfig.load(CONFIG))
    qtbot.addWidget(win)

    # Before any run: Start enabled; Pause/Resume/Stop disabled.
    assert win.start_btn.isEnabled()
    assert not win.pause_btn.isEnabled()
    assert not win.resume_btn.isEnabled()
    assert not win.stop_btn.isEnabled()


def test_open_accounts_window(qtbot, tmp_path, monkeypatch):
    import horizon_tool.gui.main_window as mw
    # Redirect state/profiles to a temp dir so the test never touches real data.
    monkeypatch.setattr(mw, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(mw, "PROFILES_DIR", tmp_path / "profiles")
    app = QApplication.instance() or QApplication([])
    win = mw.MainWindow(AppConfig.load(CONFIG))
    qtbot.addWidget(win)
    win.open_accounts_window()
    assert win.accounts_window is not None
    assert win.accounts_window.isVisible()


def test_start_without_inputs_shows_message(qtbot):
    app = QApplication.instance() or QApplication([])
    win = MainWindow(AppConfig.load(CONFIG))
    qtbot.addWidget(win)
    win.on_start()  # no input/output/plugin selected
    assert "Hãy chọn thư mục input" in win.log_pane.toPlainText()
    assert win.worker is None


def test_progress_upserts_one_row_per_script(qtbot):
    app = QApplication.instance() or QApplication([])
    win = MainWindow(AppConfig.load(CONFIG))
    qtbot.addWidget(win)
    # Same ordinal reported twice (running -> done) must update, not duplicate.
    win._on_progress(1, "Đang chạy")
    win._on_progress(1, "Xong")
    win._on_progress(2, "Đang chạy")
    assert win.table.rowCount() == 2
    assert win.table.item(0, 0).text() == "1"
    assert win.table.item(0, 2).text() == "Xong"   # updated in place
    assert win.table.item(1, 2).text() == "Đang chạy"
