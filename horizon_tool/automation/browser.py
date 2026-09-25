"""Shared browser-automation core built on Playwright's sync API.

One BrowserSession wraps one persistent context (one account profile). It must
be created and used entirely within a single (non-GUI) thread, because the
Playwright sync API is not thread-safe.
"""
from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Locator, Page, sync_playwright

from horizon_tool.core.retry import retry_with_backoff


class BrowserSession:
    """A Playwright persistent context plus stable interaction helpers."""

    def __init__(
        self,
        profile_dir: Path,
        *,
        headless: bool = False,
        element_timeout_ms: int = 30000,
        retry_attempts: int = 3,
        retry_backoff_base_seconds: float = 5,
    ) -> None:
        self.profile_dir = Path(profile_dir)
        self.headless = headless
        self.element_timeout_ms = element_timeout_ms
        self.retry_attempts = max(1, retry_attempts)
        self.retry_backoff_base_seconds = retry_backoff_base_seconds
        self._pw = None
        self._context = None
        self._page: Page | None = None

    # ----- lifecycle ------------------------------------------------------
    def start(self) -> "BrowserSession":
        """Launch the persistent context and grab its first page."""
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._pw = sync_playwright().start()
        self._context = self._pw.chromium.launch_persistent_context(
            str(self.profile_dir), headless=self.headless,
        )
        pages = self._context.pages
        self._page = pages[0] if pages else self._context.new_page()
        return self

    def close(self) -> None:
        """Close the context and stop Playwright (idempotent)."""
        try:
            if self._context is not None:
                self._context.close()
        finally:
            if self._pw is not None:
                self._pw.stop()
            self._context = None
            self._pw = None
            self._page = None

    def __enter__(self) -> "BrowserSession":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.close()

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("BrowserSession not started")
        return self._page

    # ----- helpers --------------------------------------------------------
    def _timeout(self, timeout_ms: int | None) -> int:
        # A caller may pass 0 to mean "no timeout"; only None falls back.
        return self.element_timeout_ms if timeout_ms is None else timeout_ms

    def goto(self, url: str, timeout_ms: int | None = None) -> None:
        retry_with_backoff(
            lambda: self.page.goto(url, timeout=self._timeout(timeout_ms)),
            attempts=self.retry_attempts,
            base_seconds=self.retry_backoff_base_seconds,
        )

    def screenshot(self, path: str) -> None:
        """Save a full-page screenshot to `path` (best effort, for error capture)."""
        self.page.screenshot(path=str(path), full_page=True)

    def wait_for(self, selector: str, timeout_ms: int | None = None) -> Locator:
        """Wait until a selector is present; return its first locator."""
        self.page.wait_for_selector(selector, timeout=self._timeout(timeout_ms))
        return self.page.locator(selector).first

    def is_visible(self, selector: str) -> bool:
        loc = self.page.locator(selector).first
        return loc.count() > 0 and loc.is_visible()

    def click_with_retry(self, selector: str, attempts: int | None = None) -> None:
        """Click a selector, retrying with linear backoff on failure."""
        attempts = attempts or self.retry_attempts
        last_error: Exception = RuntimeError("click_with_retry ran zero attempts")
        for i in range(attempts):
            try:
                self.page.click(selector, timeout=self.element_timeout_ms)
                return
            except Exception as exc:  # noqa: BLE001 - retried below
                last_error = exc
                self.page.wait_for_timeout(300 * (i + 1))
        raise last_error

    def paste_text(self, selector: str, text: str) -> None:
        """Insert long text in one shot (not char-by-char) after clearing.

        Uses keyboard.insert_text, which works for <input>, <textarea>, and
        contenteditable — the last is what ChatGPT/Grok use. This mimics a
        paste and avoids slow per-character typing. Note: some framework-backed
        contenteditable editors need site-specific event handling; that is
        tuned against the live sites in Phase 3.
        """
        loc = self.page.locator(selector).first
        loc.click()
        self.page.keyboard.press("Control+A")
        self.page.keyboard.press("Delete")
        self.page.keyboard.insert_text(text)
