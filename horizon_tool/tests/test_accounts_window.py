import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402
from horizon_tool.core.account_manager import (  # noqa: E402
    AccountManager, SERVICE_CHATGPT, SERVICE_GROK,
)
from horizon_tool.gui.accounts_window import AccountsWindow  # noqa: E402


def make_window(tmp_path):
    app = QApplication.instance() or QApplication([])
    mgr = AccountManager(tmp_path / "accounts.json", tmp_path / "profiles")
    return AccountsWindow(mgr), mgr


def test_window_builds_with_two_service_tables(qtbot, tmp_path):
    win, _ = make_window(tmp_path)
    qtbot.addWidget(win)
    assert SERVICE_CHATGPT in win.tables
    assert SERVICE_GROK in win.tables


def test_add_account_shows_in_table(qtbot, tmp_path):
    win, mgr = make_window(tmp_path)
    qtbot.addWidget(win)
    win.add_account(SERVICE_CHATGPT, "Tài khoản A")
    table = win.tables[SERVICE_CHATGPT]
    assert table.rowCount() == 1
    assert table.item(0, 0).text() == "Tài khoản A"
    assert len(mgr.list(SERVICE_CHATGPT)) == 1


def test_remove_selected_account(qtbot, tmp_path):
    win, mgr = make_window(tmp_path)
    qtbot.addWidget(win)
    win.add_account(SERVICE_GROK, "G1")
    win.tables[SERVICE_GROK].selectRow(0)
    win.remove_selected(SERVICE_GROK)
    assert win.tables[SERVICE_GROK].rowCount() == 0
    assert mgr.list(SERVICE_GROK) == []


def test_toggle_enabled_persists(qtbot, tmp_path):
    win, mgr = make_window(tmp_path)
    qtbot.addWidget(win)
    acc = win.add_account(SERVICE_CHATGPT, "A")
    win.set_enabled(acc.id, False)
    assert mgr.get(acc.id).enabled is False
