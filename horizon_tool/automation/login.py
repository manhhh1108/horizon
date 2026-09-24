"""Manual-login lifecycle.

Opens a browser for a given account profile, waits for the user to log in and
confirm, then closes it. The browser is created via an injected factory so the
lifecycle is unit-testable without launching a real browser. `run()` is meant to
execute on a dedicated (non-GUI) thread that owns the Playwright sync context.

The tool never receives or stores passwords — the user types them directly into
the browser.
"""
from __future__ import annotations

import threading
from typing import Callable


class LoginSession:
    """State machine: open -> (confirm | cancel) -> closed."""

    def __init__(self, url: str, session_factory: Callable[[], object]) -> None:
        self._url = url
        self._factory = session_factory
        self._session = None
        self._opened = threading.Event()
        self._decided = threading.Event()
        self._cancelled = False

    def open(self) -> None:
        """Create and start the browser, then navigate to the login URL."""
        self._session = self._factory()
        self._session.start()
        self._session.goto(self._url)
        self._opened.set()

    def confirm(self) -> None:
        """User finished logging in."""
        self._decided.set()

    def cancel(self) -> None:
        """User aborted the login."""
        self._cancelled = True
        self._decided.set()

    def wait_and_close(self) -> bool:
        """Block until confirm/cancel, close the browser, return success."""
        self._decided.wait()
        if self._session is not None:
            self._session.close()
        return not self._cancelled

    def run(self) -> bool:
        """Full lifecycle for a worker thread: open, wait, close."""
        self.open()
        return self.wait_and_close()
