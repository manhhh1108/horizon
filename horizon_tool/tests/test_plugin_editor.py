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
