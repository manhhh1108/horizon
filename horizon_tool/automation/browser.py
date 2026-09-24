"""Shared browser-automation core built on Playwright's sync API.

One BrowserSession wraps one persistent context (one account profile). It must
be created and used entirely within a single (non-GUI) thread, because the
Playwright sync API is not thread-safe.
"""
from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Page, sync_playwright


class BrowserSession:
    """A Playwright persistent context plus stable interaction helpers."""

    def __init__(
        self,
        profile_dir: Path,
        *,
        headless: bool = False,
        element_timeout_ms: int = 30000,
        retry_attempts: int = 3,
    ) -> None:
        self.profile_dir = Path(profile_dir)
        self.headless = headless
        self.element_timeout_ms = element_timeout_ms
        self.retry_attempts = max(1, retry_attempts)
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
    def goto(self, url: str, timeout_ms: int | None = None) -> None:
        self.page.goto(url, timeout=timeout_ms or self.element_timeout_ms)

    def wait_for(self, selector: str, timeout_ms: int | None = None):
        """Wait until a selector is present; return its first locator."""
        self.page.wait_for_selector(
            selector, timeout=timeout_ms or self.element_timeout_ms,
        )
        return self.page.locator(selector).first

    def is_visible(self, selector: str) -> bool:
        loc = self.page.locator(selector).first
        return loc.count() > 0 and loc.is_visible()

    def click_with_retry(self, selector: str, attempts: int | None = None) -> None:
        """Click a selector, retrying with linear backoff on failure."""
        attempts = attempts or self.retry_attempts
        last_error: Exception | None = None
        for i in range(attempts):
            try:
                self.page.click(selector, timeout=self.element_timeout_ms)
                return
            except Exception as exc:  # noqa: BLE001 - retried below
                last_error = exc
                self.page.wait_for_timeout(300 * (i + 1))
        raise last_error  # type: ignore[misc]

    def paste_text(self, selector: str, text: str) -> None:
        """Insert long text in one shot (not char-by-char) after clearing.

        Uses keyboard.insert_text, which works for <input>, <textarea>, and
        contenteditable — the last is what ChatGPT/Grok use. This mimics a
        paste and avoids slow per-character typing.
        """
        loc = self.page.locator(selector).first
        loc.click()
        self.page.keyboard.press("Control+A")
        self.page.keyboard.press("Delete")
        self.page.keyboard.insert_text(text)
