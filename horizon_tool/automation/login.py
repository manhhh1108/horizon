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
        self.error: Exception | None = None

    @property
    def opened_ok(self) -> bool:
        """True once the browser opened successfully (no factory/start error)."""
        return self._opened.is_set() and self.error is None

    def open(self) -> None:
        """Create and start the browser, then navigate to the login URL.

        On any failure the error is recorded and `_opened` is still set so a
        controlling thread waiting on it never blocks forever; the exception is
        re-raised for the caller (see `run`).
        """
        try:
            self._session = self._factory()
            self._session.start()
            self._session.goto(self._url)
        except Exception as exc:  # noqa: BLE001 - recorded and re-raised
            self.error = exc
            raise
        finally:
            self._opened.set()

    def confirm(self) -> None:
        """User finished logging in."""
        self._decided.set()

    def cancel(self) -> None:
        """User aborted the login."""
        self._cancelled = True
        self._decided.set()

    def wait_and_close(self) -> bool:
        """Block until confirm/cancel, close the browser, return success.

        Reading `_cancelled` after `_decided.wait()` is safe: setting an Event
        establishes a happens-before edge for the waiting thread.
        """
        self._decided.wait()
        if self._session is not None:
            self._session.close()
        return not self._cancelled

    def run(self) -> bool:
        """Full lifecycle for a worker thread: open, wait, close.

        Returns False if the browser failed to open (never blocks), otherwise
        waits for the user's confirm/cancel decision.
        """
        try:
            self.open()
        except Exception:  # noqa: BLE001 - reported via `error`; surfaced as False
            if self._session is not None:
                self._session.close()
            return False
        return self.wait_and_close()
