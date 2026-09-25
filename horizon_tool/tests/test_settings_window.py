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
