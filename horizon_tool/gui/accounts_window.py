"""Accounts management window (Vietnamese UI).

Two tables — one per service (ChatGPT, Grok) — over an AccountManager. Add,
remove, rename, enable/disable, and launch manual login. All mutations go
through AccountManager, which persists immediately.
"""
from __future__ import annotations

from functools import partial

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QTableWidget,
    QTableWidgetItem, QPushButton, QInputDialog, QMessageBox, QWidget,
)

from horizon_tool.automation.browser import BrowserSession
from horizon_tool.core.account_manager import (
    Account, AccountManager, SERVICE_CHATGPT, SERVICE_GROK,
)
from horizon_tool.gui.login_worker import LoginWorker

_SERVICE_TITLES = {SERVICE_CHATGPT: "ChatGPT", SERVICE_GROK: "Grok"}
_COLUMNS = ["Tên hiển thị", "Trạng thái", "Bật"]
_LOGIN_URLS = {
    SERVICE_CHATGPT: "https://chatgpt.com/",
    SERVICE_GROK: "https://grok.com/",
}


class AccountsWindow(QDialog):
    """Dialog for managing ChatGPT and Grok accounts."""

    def __init__(self, manager: AccountManager, parent=None) -> None:
        super().__init__(parent)
        self.manager = manager
        self.setWindowTitle("Quản lý tài khoản")
        self.resize(720, 560)
        self.tables: dict[str, QTableWidget] = {}

        root = QVBoxLayout(self)
        for service in (SERVICE_CHATGPT, SERVICE_GROK):
            root.addWidget(self._build_service_group(service))
        self.refresh_all()

    # ----- builders -------------------------------------------------------
    def _build_service_group(self, service: str) -> QGroupBox:
        box = QGroupBox(_SERVICE_TITLES[service])
        layout = QVBoxLayout(box)

        table = QTableWidget(0, len(_COLUMNS))
        table.setHorizontalHeaderLabels(_COLUMNS)
        self.tables[service] = table
        layout.addWidget(table)

        buttons = QWidget()
        row = QHBoxLayout(buttons)
        add_btn = QPushButton("Thêm")
        rename_btn = QPushButton("Đổi tên")
        remove_btn = QPushButton("Xóa")
        login_btn = QPushButton("Đăng nhập")
        toggle_btn = QPushButton("Bật/Tắt")
        add_btn.clicked.connect(lambda: self._on_add(service))
        rename_btn.clicked.connect(lambda: self._on_rename(service))
        remove_btn.clicked.connect(lambda: self.remove_selected(service))
        toggle_btn.clicked.connect(lambda: self._on_toggle(service))
        login_btn.clicked.connect(lambda: self._on_login(service))
        for b in (add_btn, rename_btn, toggle_btn, login_btn, remove_btn):
            row.addWidget(b)
        layout.addWidget(buttons)
        return box

    # ----- data / refresh -------------------------------------------------
    def refresh_all(self) -> None:
        for service in self.tables:
            self._refresh(service)

    def _refresh(self, service: str) -> None:
        table = self.tables[service]
        accounts = self.manager.list(service)
        table.setRowCount(len(accounts))
        for row, acc in enumerate(accounts):
            table.setItem(row, 0, QTableWidgetItem(acc.display_name))
            table.setItem(row, 1, QTableWidgetItem(acc.status))
            table.setItem(row, 2, QTableWidgetItem("Có" if acc.enabled else "Không"))
            table.item(row, 0).setData(Qt.UserRole, acc.id)

    def _selected_account_id(self, service: str) -> str | None:
        table = self.tables[service]
        row = table.currentRow()
        if row < 0 or table.item(row, 0) is None:
            return None
        return table.item(row, 0).data(Qt.UserRole)

    # ----- operations (testable, dialog-free) -----------------------------
    def add_account(self, service: str, display_name: str) -> Account:
        account = self.manager.add(service, display_name)
        self._refresh(service)
        return account

    def remove_selected(self, service: str) -> None:
        account_id = self._selected_account_id(service)
        if account_id is None:
            return
        self.manager.remove(account_id)
        self._refresh(service)

    def set_enabled(self, account_id: str, enabled: bool) -> None:
        account = self.manager.get(account_id)
        self.manager.set_enabled(account_id, enabled)
        self._refresh(account.service)

    # ----- button handlers (wrap operations with dialogs) -----------------
    def _on_add(self, service: str) -> None:
        name, ok = QInputDialog.getText(self, "Thêm tài khoản", "Tên hiển thị:")
        if ok and name.strip():
            self.add_account(service, name.strip())

    def _on_rename(self, service: str) -> None:
        account_id = self._selected_account_id(service)
        if account_id is None:
            return
        current = self.manager.get(account_id).display_name
        name, ok = QInputDialog.getText(
            self, "Đổi tên", "Tên hiển thị:", text=current)
        if ok and name.strip():
            self.manager.rename(account_id, name.strip())
            self._refresh(service)

    def _on_toggle(self, service: str) -> None:
        account_id = self._selected_account_id(service)
        if account_id is None:
            return
        current = self.manager.get(account_id).enabled
        self.set_enabled(account_id, not current)

    def _on_login(self, service: str) -> None:
        existing = getattr(self, "_login_worker", None)
        if existing is not None and existing.isRunning():
            QMessageBox.information(
                self, "Đăng nhập",
                "Đang có một phiên đăng nhập khác. Hãy hoàn tất phiên đó trước.")
            return
        account_id = self._selected_account_id(service)
        if account_id is None:
            QMessageBox.information(
                self, "Đăng nhập", "Hãy chọn một tài khoản trước.")
            return
        account = self.manager.get(account_id)
        url = _LOGIN_URLS[service]

        def factory():
            # Headful so the user can log in; profile persists the session.
            return BrowserSession(account.profile_dir, headless=False)

        self._login_worker = LoginWorker(url, factory, parent=self)
        self._login_worker.opened.connect(
            partial(self._prompt_login_done, service))
        self._login_worker.finished_result.connect(
            partial(self._on_login_finished, service))
        self._login_worker.start()

    def _prompt_login_done(self, service: str) -> None:
        done = QMessageBox.question(
            self, "Đăng nhập",
            "Trình duyệt đã mở. Đăng nhập xong rồi bấm Yes để xác nhận.",
        )
        if done == QMessageBox.StandardButton.Yes:
            self._login_worker.confirm()
        else:
            self._login_worker.cancel()

    def _on_login_finished(self, service: str, ok: bool) -> None:
        if self._login_worker is not None:
            self._login_worker.wait(3000)  # join the finished thread cleanly
        if ok:
            QMessageBox.information(self, "Đăng nhập", "Đã lưu phiên đăng nhập.")
        self._refresh(service)
