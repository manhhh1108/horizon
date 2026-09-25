import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402
from horizon_tool.core.config_loader import AppConfig  # noqa: E402
from horizon_tool.gui.main_window import MainWindow  # noqa: E402
from horizon_tool.core.statuses import (  # noqa: E402
    STATUS_RUNNING, STATUS_DONE, STATUS_FAILED, STATUS_REJECTED,
)
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


def test_resume_button_starts_resume_run_when_idle(qtbot, tmp_path, monkeypatch):
    import horizon_tool.gui.main_window as mw
    monkeypatch.setattr(mw, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(mw, "PROFILES_DIR", tmp_path / "profiles")
    app = QApplication.instance() or QApplication([])
    win = mw.MainWindow(AppConfig.load(CONFIG))
    qtbot.addWidget(win)
    launched = {}
    monkeypatch.setattr(win, "_launch_run", lambda *, resume: launched.setdefault("resume", resume))
    win.on_resume()   # idle -> should launch a resume run
    assert launched == {"resume": True}


def test_on_exhausted_logs(qtbot, tmp_path, monkeypatch):
    import horizon_tool.gui.main_window as mw
    monkeypatch.setattr(mw, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(mw, "PROFILES_DIR", tmp_path / "profiles")
    app = QApplication.instance() or QApplication([])
    win = mw.MainWindow(AppConfig.load(CONFIG))
    qtbot.addWidget(win)
    win._on_exhausted("chatgpt")
    assert "hết tài khoản chatgpt" in win.log_pane.toPlainText().lower()


def test_on_resume_unpauses_running_worker(qtbot, tmp_path, monkeypatch):
    import horizon_tool.gui.main_window as mw
    monkeypatch.setattr(mw, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(mw, "PROFILES_DIR", tmp_path / "profiles")
    app = QApplication.instance() or QApplication([])
    win = mw.MainWindow(AppConfig.load(CONFIG))
    qtbot.addWidget(win)

    class FakeRunningWorker:
        def isRunning(self):
            return True
        def set_paused(self, paused):
            self.paused = paused
        def request_stop(self):  # used by closeEvent on teardown
            pass
        def wait(self, ms=0):
            return True

    win.worker = FakeRunningWorker()
    launched = {"called": False}
    monkeypatch.setattr(win, "_launch_run", lambda *, resume: launched.update(called=True))
    win.on_resume()   # a worker is running -> unpause, do NOT relaunch
    assert win.worker.paused is False
    assert launched["called"] is False


def test_auto_resume_tick_resets_quota_and_resumes(qtbot, tmp_path, monkeypatch):
    import horizon_tool.gui.main_window as mw
    from horizon_tool.core.account_manager import SERVICE_CHATGPT, STATUS_QUOTA, STATUS_READY
    monkeypatch.setattr(mw, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(mw, "PROFILES_DIR", tmp_path / "profiles")
    app = QApplication.instance() or QApplication([])
    win = mw.MainWindow(AppConfig.load(CONFIG))
    qtbot.addWidget(win)
    acc = win.account_manager.add(SERVICE_CHATGPT, "C1")
    win.account_manager.set_status(acc.id, STATUS_QUOTA)
    resumed = {"called": False}
    monkeypatch.setattr(win, "on_resume", lambda: resumed.update(called=True))

    win._auto_resume_tick()   # no worker running -> reset quota accounts + resume

    assert win.account_manager.get(acc.id).status == STATUS_READY
    assert resumed["called"] is True


def test_auto_resume_tick_skips_while_worker_running(qtbot, tmp_path, monkeypatch):
    import horizon_tool.gui.main_window as mw
    from horizon_tool.core.account_manager import SERVICE_CHATGPT, STATUS_QUOTA
    monkeypatch.setattr(mw, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(mw, "PROFILES_DIR", tmp_path / "profiles")
    app = QApplication.instance() or QApplication([])
    win = mw.MainWindow(AppConfig.load(CONFIG))
    qtbot.addWidget(win)
    acc = win.account_manager.add(SERVICE_CHATGPT, "C1")
    win.account_manager.set_status(acc.id, STATUS_QUOTA)

    class Running:
        def isRunning(self): return True
        def request_stop(self): pass       # used by closeEvent on teardown
        def wait(self, ms=0): return True
    win.worker = Running()
    resumed = {"called": False}
    monkeypatch.setattr(win, "on_resume", lambda: resumed.update(called=True))

    win._auto_resume_tick()   # worker running -> must NOT touch accounts or resume

    assert win.account_manager.get(acc.id).status == STATUS_QUOTA  # untouched
    assert resumed["called"] is False


def test_step_status_upserts_and_maps_columns(qtbot):
    app = QApplication.instance() or QApplication([])
    win = MainWindow(AppConfig.load(CONFIG))
    qtbot.addWidget(win)
    win._on_step_status(1, "word", STATUS_RUNNING)
    win._on_step_status(1, "word", STATUS_DONE)          # updates in place
    win._on_step_status(1, "img_9x16", STATUS_REJECTED)
    win._on_step_status(2, "word", STATUS_RUNNING)
    assert win.table.rowCount() == 2
    assert win.table.item(0, 2).text() == STATUS_DONE       # word col
    assert win.table.item(0, 3).text() == STATUS_REJECTED   # 9:16 col
    assert win.table.item(1, 2).text() == STATUS_RUNNING


def test_stats_label_updates_from_signals(qtbot):
    app = QApplication.instance() or QApplication([])
    win = MainWindow(AppConfig.load(CONFIG))
    qtbot.addWidget(win)
    win._reset_stats()
    win._on_run_totals(3, 1)
    win._on_script_finished(1, STATUS_DONE)
    win._on_script_finished(2, STATUS_FAILED)
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
