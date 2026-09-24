"""QThread wrapper around LoginSession so the Playwright sync context lives on a
non-GUI thread while the GUI stays responsive during manual login.
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QThread, Signal

from horizon_tool.automation.login import LoginSession


class LoginWorker(QThread):
    """Runs a LoginSession on its own thread; the GUI drives confirm/cancel."""

    opened = Signal()               # browser opened, waiting for the user
    finished_result = Signal(bool)  # True = confirmed/logged in, False = cancelled

    def __init__(self, url: str, session_factory: Callable[[], object],
                 parent=None) -> None:
        super().__init__(parent)
        self._session = LoginSession(url, session_factory)

    def confirm(self) -> None:
        self._session.confirm()

    def cancel(self) -> None:
        self._session.cancel()

    def run(self) -> None:  # noqa: D401 - QThread entry point
        try:
            self._session.open()
        except Exception:  # noqa: BLE001 - reported to the GUI as failure
            if self._session._session is not None:
                self._session._session.close()
            self.finished_result.emit(False)
            return
        self.opened.emit()
        result = self._session.wait_and_close()
        self.finished_result.emit(result)
