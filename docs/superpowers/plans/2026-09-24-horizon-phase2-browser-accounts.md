# Horizon X Media Tool — Phase 2 Implementation Plan (Browser Core, Accounts, Manual Login)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the shared browser-automation core (Playwright persistent context + stable helpers), a multi-account manager (per-service pools, CRUD, status, rotation selection, JSON persistence), a manual-login lifecycle (open browser → user logs in → confirm), and an Accounts management GUI — wired into the main window.

**Architecture:** `automation/browser.py` wraps one Playwright persistent context per account profile with retry/wait/paste helpers. `core/account_manager.py` is pure logic (dataclass + JSON store + rotation), fully unit-tested. `automation/login.py` holds a browser-agnostic login lifecycle (browser injected via factory) so it is testable without a real browser. `gui/accounts_window.py` is a thin PySide6 layer over AccountManager. Playwright's sync API always runs on a non-GUI thread.

**Tech Stack:** Python 3.10-compatible, Playwright (Chromium, already installed at `~/AppData/Local/ms-playwright`), PySide6, pytest, pytest-qt.

**Convention:** UI text/logs/report Vietnamese; code identifiers/docstrings/comments English.

**Base branch:** `main`. Work branch: `phase-2-browser-accounts`.

**Verified preconditions (do not re-check):** Chromium is installed; `launch_persistent_context(headless=True)` works; `page.fill`, `page.click`, `page.keyboard.insert_text` all function against `page.set_content(...)`. Browser tests therefore use headless persistent contexts against local `set_content` HTML — no network.

**Passwords are NEVER stored, received, or logged (SEC-01).** The account store holds only display name, service, profile directory, enabled flag, and status.

---

### Task 1: Account model + JSON persistence

**Files:**
- Create: `horizon_tool/core/account_manager.py`
- Test: `horizon_tool/tests/test_account_model.py`

- [ ] **Step 1: Write the failing test**

```python
# horizon_tool/tests/test_account_model.py
from horizon_tool.core.account_manager import (
    Account, AccountStore, SERVICE_CHATGPT, STATUS_READY, STATUS_QUOTA,
)


def test_account_roundtrip_dict():
    acc = Account(
        id="chatgpt_1", service=SERVICE_CHATGPT, display_name="Tài khoản 1",
        profile_dir="profiles/chatgpt_1",
    )
    assert acc.status == STATUS_READY  # default
    assert acc.enabled is True         # default
    restored = Account.from_dict(acc.to_dict())
    assert restored == acc


def test_store_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "accounts.json"
    store = AccountStore(path)
    store.upsert(Account("chatgpt_1", SERVICE_CHATGPT, "A", "p/chatgpt_1"))
    store.upsert(Account("chatgpt_1", SERVICE_CHATGPT, "A", "p/chatgpt_1",
                         status=STATUS_QUOTA))  # same id overwrites
    store.save()

    reloaded = AccountStore(path)
    reloaded.load()
    accounts = reloaded.all()
    assert len(accounts) == 1
    assert accounts[0].status == STATUS_QUOTA


def test_store_load_missing_file_is_empty(tmp_path):
    store = AccountStore(tmp_path / "nope.json")
    store.load()
    assert store.all() == []


def test_store_save_is_atomic(tmp_path):
    # No leftover temp file after a successful save.
    path = tmp_path / "accounts.json"
    store = AccountStore(path)
    store.upsert(Account("grok_1", "grok", "G", "p/grok_1"))
    store.save()
    assert path.exists()
    assert not (tmp_path / "accounts.json.tmp").exists()
```

- [ ] **Step 2: Run test, confirm FAIL**

Run: `horizon_tool\.venv\Scripts\python.exe -m pytest horizon_tool/tests/test_account_model.py -v` (from D:\Home\wf)
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement the model + store in `core/account_manager.py`**

```python
"""Multi-account model, JSON persistence, and rotation logic.

Passwords are never stored here; only non-secret account metadata. Browser
session cookies live inside each account's own browser profile directory.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

SERVICE_CHATGPT = "chatgpt"
SERVICE_GROK = "grok"
SERVICES = (SERVICE_CHATGPT, SERVICE_GROK)

STATUS_READY = "ready"
STATUS_IN_USE = "in_use"
STATUS_QUOTA = "quota_exhausted"
STATUS_SESSION_EXPIRED = "session_expired"


@dataclass
class Account:
    """Non-secret metadata for one logged-in browser profile."""

    id: str
    service: str
    display_name: str
    profile_dir: str
    enabled: bool = True
    status: str = STATUS_READY
    quota_reset_at: str | None = None
    last_used: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Account":
        return cls(**data)


class AccountStore:
    """Loads/saves a list of Accounts to a JSON file (atomic writes)."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._accounts: dict[str, Account] = {}

    def load(self) -> None:
        self._accounts = {}
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        for item in data.get("accounts", []):
            acc = Account.from_dict(item)
            self._accounts[acc.id] = acc

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"accounts": [a.to_dict() for a in self._accounts.values()]}
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)  # atomic on Windows and POSIX

    def upsert(self, account: Account) -> None:
        self._accounts[account.id] = account

    def remove(self, account_id: str) -> None:
        self._accounts.pop(account_id, None)

    def get(self, account_id: str) -> Account:
        return self._accounts[account_id]

    def all(self) -> list[Account]:
        return list(self._accounts.values())
```

- [ ] **Step 4: Run test, confirm 4 passed.**

- [ ] **Step 5: Commit**

```bash
cd "D:/Home/wf"
git add horizon_tool/core/account_manager.py horizon_tool/tests/test_account_model.py
git commit -m "feat: account model and atomic JSON store"
```

---

### Task 2: AccountManager (CRUD, status, rotation)

**Files:**
- Modify: `horizon_tool/core/account_manager.py`
- Test: `horizon_tool/tests/test_account_manager.py`

- [ ] **Step 1: Write the failing test**

```python
# horizon_tool/tests/test_account_manager.py
import pytest

from horizon_tool.core.account_manager import (
    AccountManager, SERVICE_CHATGPT, SERVICE_GROK,
    STATUS_READY, STATUS_QUOTA, STATUS_SESSION_EXPIRED,
)


def make_manager(tmp_path):
    return AccountManager(
        store_path=tmp_path / "accounts.json",
        profiles_root=tmp_path / "profiles",
    )


def test_add_creates_unique_id_and_profile_dir(tmp_path):
    mgr = make_manager(tmp_path)
    a = mgr.add(SERVICE_CHATGPT, "Tài khoản 1")
    b = mgr.add(SERVICE_CHATGPT, "Tài khoản 2")
    assert a.id != b.id
    assert a.service == SERVICE_CHATGPT
    assert (tmp_path / "profiles" / a.id).is_dir()  # profile dir created
    # persisted immediately
    reloaded = make_manager(tmp_path)
    assert {x.id for x in reloaded.list(SERVICE_CHATGPT)} == {a.id, b.id}


def test_list_filters_by_service(tmp_path):
    mgr = make_manager(tmp_path)
    mgr.add(SERVICE_CHATGPT, "C1")
    mgr.add(SERVICE_GROK, "G1")
    assert len(mgr.list(SERVICE_CHATGPT)) == 1
    assert len(mgr.list(SERVICE_GROK)) == 1
    assert len(mgr.list()) == 2


def test_rename_enable_status(tmp_path):
    mgr = make_manager(tmp_path)
    a = mgr.add(SERVICE_CHATGPT, "Old")
    mgr.rename(a.id, "New")
    mgr.set_enabled(a.id, False)
    mgr.set_status(a.id, STATUS_QUOTA, quota_reset_at="2026-09-24T10:00:00")
    got = mgr.get(a.id)
    assert got.display_name == "New"
    assert got.enabled is False
    assert got.status == STATUS_QUOTA
    assert got.quota_reset_at == "2026-09-24T10:00:00"


def test_remove_deletes_account(tmp_path):
    mgr = make_manager(tmp_path)
    a = mgr.add(SERVICE_CHATGPT, "X")
    mgr.remove(a.id)
    assert mgr.list(SERVICE_CHATGPT) == []
    with pytest.raises(KeyError):
        mgr.get(a.id)


def test_next_available_skips_disabled_and_unavailable(tmp_path):
    mgr = make_manager(tmp_path)
    a = mgr.add(SERVICE_CHATGPT, "A")
    b = mgr.add(SERVICE_CHATGPT, "B")
    c = mgr.add(SERVICE_CHATGPT, "C")
    mgr.set_enabled(a.id, False)             # disabled -> skip
    mgr.set_status(b.id, STATUS_QUOTA)       # quota -> skip
    nxt = mgr.next_available(SERVICE_CHATGPT)
    assert nxt.id == c.id


def test_next_available_none_when_all_unavailable(tmp_path):
    mgr = make_manager(tmp_path)
    a = mgr.add(SERVICE_GROK, "A")
    mgr.set_status(a.id, STATUS_SESSION_EXPIRED)
    assert mgr.next_available(SERVICE_GROK) is None
```

- [ ] **Step 2: Run test, confirm FAIL** (AccountManager not defined).

- [ ] **Step 3: Append `AccountManager` to `core/account_manager.py`**

```python
# append to horizon_tool/core/account_manager.py


class AccountManager:
    """High-level account operations backed by an AccountStore.

    Every mutating call persists immediately so state survives a crash.
    """

    def __init__(self, store_path: Path, profiles_root: Path) -> None:
        self.profiles_root = Path(profiles_root)
        self._store = AccountStore(Path(store_path))
        self._store.load()

    def _next_id(self, service: str) -> str:
        used = [
            int(a.id.rsplit("_", 1)[1])
            for a in self._store.all()
            if a.service == service and a.id.rsplit("_", 1)[1].isdigit()
        ]
        return f"{service}_{(max(used) + 1) if used else 1}"

    def add(self, service: str, display_name: str) -> Account:
        if service not in SERVICES:
            raise ValueError(f"Unknown service: {service}")
        account_id = self._next_id(service)
        profile_dir = self.profiles_root / account_id
        profile_dir.mkdir(parents=True, exist_ok=True)
        account = Account(
            id=account_id, service=service, display_name=display_name,
            profile_dir=str(profile_dir),
        )
        self._store.upsert(account)
        self._store.save()
        return account

    def remove(self, account_id: str) -> None:
        self._store.remove(account_id)
        self._store.save()

    def rename(self, account_id: str, display_name: str) -> None:
        account = self._store.get(account_id)
        account.display_name = display_name
        self._store.upsert(account)
        self._store.save()

    def set_enabled(self, account_id: str, enabled: bool) -> None:
        account = self._store.get(account_id)
        account.enabled = enabled
        self._store.upsert(account)
        self._store.save()

    def set_status(self, account_id: str, status: str,
                   quota_reset_at: str | None = None) -> None:
        account = self._store.get(account_id)
        account.status = status
        account.quota_reset_at = quota_reset_at
        self._store.upsert(account)
        self._store.save()

    def get(self, account_id: str) -> Account:
        return self._store.get(account_id)

    def list(self, service: str | None = None) -> list[Account]:
        accounts = self._store.all()
        if service is None:
            return accounts
        return [a for a in accounts if a.service == service]

    def next_available(self, service: str) -> Account | None:
        for account in self.list(service):
            if account.enabled and account.status == STATUS_READY:
                return account
        return None
```

- [ ] **Step 4: Run test, confirm 6 passed. Then full suite** (`horizon_tool\.venv\Scripts\python.exe -m pytest horizon_tool/tests -q`).

- [ ] **Step 5: Commit**

```bash
cd "D:/Home/wf"
git add horizon_tool/core/account_manager.py horizon_tool/tests/test_account_manager.py
git commit -m "feat: AccountManager CRUD, status, and rotation selection"
```

---

### Task 3: Browser core (`automation/browser.py`)

**Files:**
- Create: `horizon_tool/automation/browser.py`
- Test: `horizon_tool/tests/test_browser.py`

- [ ] **Step 1: Write the failing test** (headless persistent context, local content only)

```python
# horizon_tool/tests/test_browser.py
import tempfile

import pytest

pytest.importorskip("playwright")
from horizon_tool.automation.browser import BrowserSession  # noqa: E402


@pytest.fixture
def session(tmp_path):
    """A started headless BrowserSession, or skip if Chromium can't launch."""
    s = BrowserSession(tmp_path / "profile", headless=True,
                       element_timeout_ms=5000, retry_attempts=2)
    try:
        s.start()
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"Chromium unavailable: {exc}")
    yield s
    s.close()


def test_wait_for_and_visible(session):
    session.page.set_content("<textarea id='box'></textarea>")
    loc = session.wait_for("#box")
    assert loc is not None
    assert session.is_visible("#box")
    assert not session.is_visible("#missing")


def test_paste_text_into_textarea(session):
    session.page.set_content("<textarea id='box'></textarea>")
    session.paste_text("#box", "Đây là một kịch bản dài\nnhiều dòng.")
    value = session.page.eval_on_selector("#box", "e => e.value")
    assert value == "Đây là một kịch bản dài\nnhiều dòng."


def test_paste_text_replaces_existing(session):
    session.page.set_content("<textarea id='box'>cũ</textarea>")
    session.paste_text("#box", "mới")
    value = session.page.eval_on_selector("#box", "e => e.value")
    assert value == "mới"


def test_click_with_retry_success(session):
    session.page.set_content(
        "<button id='go' onclick=\"this.textContent='clicked'\">go</button>"
    )
    session.click_with_retry("#go")
    assert session.page.eval_on_selector("#go", "e => e.textContent") == "clicked"


def test_click_with_retry_raises_when_absent(session):
    session.page.set_content("<div>nothing</div>")
    with pytest.raises(Exception):
        session.click_with_retry("#missing")
```

- [ ] **Step 2: Run test, confirm FAIL** (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `automation/browser.py`**

```python
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
```

- [ ] **Step 4: Run test, confirm 5 passed** (or skipped if Chromium truly unavailable — but it is installed, so expect passed).

- [ ] **Step 5: Commit**

```bash
cd "D:/Home/wf"
git add horizon_tool/automation/browser.py horizon_tool/tests/test_browser.py
git commit -m "feat: Playwright browser session core with wait/click/paste helpers"
```

---

### Task 4: Manual-login lifecycle (`automation/login.py`)

**Files:**
- Create: `horizon_tool/automation/login.py`
- Test: `horizon_tool/tests/test_login.py`

- [ ] **Step 1: Write the failing test** (uses a fake browser — no real Chromium)

```python
# horizon_tool/tests/test_login.py
import threading

from horizon_tool.automation.login import LoginSession


class FakeSession:
    def __init__(self):
        self.started = False
        self.url = None
        self.closed = False

    def start(self):
        self.started = True
        return self

    def goto(self, url, timeout_ms=None):
        self.url = url

    def close(self):
        self.closed = True


def test_open_starts_and_navigates():
    fake = FakeSession()
    login = LoginSession("https://chatgpt.com/", session_factory=lambda: fake)
    login.open()
    assert fake.started is True
    assert fake.url == "https://chatgpt.com/"
    assert fake.closed is False


def test_confirm_closes_and_reports_success():
    fake = FakeSession()
    login = LoginSession("https://x/", session_factory=lambda: fake)
    login.open()
    login.confirm()
    assert login.wait_and_close() is True   # confirmed -> logged in
    assert fake.closed is True


def test_cancel_closes_and_reports_failure():
    fake = FakeSession()
    login = LoginSession("https://x/", session_factory=lambda: fake)
    login.open()
    login.cancel()
    assert login.wait_and_close() is False  # cancelled -> not logged in
    assert fake.closed is True


def test_run_blocks_until_confirmed_in_thread():
    fake = FakeSession()
    login = LoginSession("https://x/", session_factory=lambda: fake)
    result = {}
    t = threading.Thread(target=lambda: result.setdefault("ok", login.run()))
    t.start()
    # give the thread time to open, then confirm from this thread
    login._opened.wait(timeout=2)
    login.confirm()
    t.join(timeout=2)
    assert result["ok"] is True
    assert fake.closed is True
```

- [ ] **Step 2: Run test, confirm FAIL** (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `automation/login.py`**

```python
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
```

- [ ] **Step 4: Run test, confirm 4 passed.**

- [ ] **Step 5: Commit**

```bash
cd "D:/Home/wf"
git add horizon_tool/automation/login.py horizon_tool/tests/test_login.py
git commit -m "feat: browser-agnostic manual-login lifecycle"
```

---

### Task 5: Accounts GUI window (`gui/accounts_window.py`)

**Files:**
- Create: `horizon_tool/gui/accounts_window.py`
- Test: `horizon_tool/tests/test_accounts_window.py`

- [ ] **Step 1: Write the failing test**

```python
# horizon_tool/tests/test_accounts_window.py
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
```

- [ ] **Step 2: Run test, confirm FAIL** (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `gui/accounts_window.py`**

```python
"""Accounts management window (Vietnamese UI).

Two tables — one per service (ChatGPT, Grok) — over an AccountManager. Add,
remove, rename, enable/disable, and launch manual login. All mutations go
through AccountManager, which persists immediately.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QTableWidget,
    QTableWidgetItem, QPushButton, QInputDialog, QMessageBox, QWidget,
)

from horizon_tool.core.account_manager import (
    Account, AccountManager, SERVICE_CHATGPT, SERVICE_GROK,
)

_SERVICE_TITLES = {SERVICE_CHATGPT: "ChatGPT", SERVICE_GROK: "Grok"}
_COLUMNS = ["Tên hiển thị", "Trạng thái", "Bật"]


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
            table.item(row, 0).setData(0x0100, acc.id)  # Qt.UserRole = 256

    def _selected_account_id(self, service: str) -> str | None:
        table = self.tables[service]
        row = table.currentRow()
        if row < 0 or table.item(row, 0) is None:
            return None
        return table.item(row, 0).data(0x0100)

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
        # Manual login is wired to a real browser in Task 6 (needs the app's
        # config + a worker thread). Here we surface a clear placeholder so the
        # button is never silently dead.
        QMessageBox.information(
            self, "Đăng nhập",
            "Chức năng đăng nhập thủ công sẽ mở trình duyệt (được nối ở bước sau).",
        )
```

- [ ] **Step 4: Run test, confirm 4 passed.**

- [ ] **Step 5: Commit**

```bash
cd "D:/Home/wf"
git add horizon_tool/gui/accounts_window.py horizon_tool/tests/test_accounts_window.py
git commit -m "feat: accounts management window over AccountManager"
```

---

### Task 6: Wire manual login + open Accounts window from main window

**Files:**
- Create: `horizon_tool/gui/login_worker.py`
- Modify: `horizon_tool/gui/accounts_window.py` (replace `_on_login` placeholder)
- Modify: `horizon_tool/gui/main_window.py` (create AccountManager, open AccountsWindow)
- Test: `horizon_tool/tests/test_login_worker.py`, extend `horizon_tool/tests/test_main_window.py`

- [ ] **Step 1: Write the failing test for the login worker** (fake session, no real browser)

```python
# horizon_tool/tests/test_login_worker.py
import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QCoreApplication  # noqa: E402
from horizon_tool.gui.login_worker import LoginWorker  # noqa: E402


class FakeSession:
    def __init__(self):
        self.closed = False
    def start(self):
        return self
    def goto(self, url, timeout_ms=None):
        self.url = url
    def close(self):
        self.closed = True


def test_login_worker_emits_finished_on_confirm(qtbot):
    app = QCoreApplication.instance() or QCoreApplication([])
    fake = FakeSession()
    worker = LoginWorker("https://x/", session_factory=lambda: fake)
    results = []
    worker.finished_result.connect(results.append)

    with qtbot.waitSignal(worker.opened, timeout=2000):
        worker.start()
    worker.confirm()
    with qtbot.waitSignal(worker.finished_result, timeout=2000):
        pass

    assert results == [True]
    assert fake.closed is True
```

- [ ] **Step 2: Run test, confirm FAIL.**

- [ ] **Step 3: Implement `gui/login_worker.py`**

```python
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
        self._session.open()
        self.opened.emit()
        result = self._session.wait_and_close()
        self.finished_result.emit(result)
```

- [ ] **Step 4: Run the login-worker test, confirm 1 passed.**

- [ ] **Step 5: Replace the `_on_login` placeholder in `gui/accounts_window.py`**

Replace the entire `_on_login` method body with a real browser-backed login. Add these imports at the top of `gui/accounts_window.py` (next to the existing imports):

```python
from functools import partial

from horizon_tool.automation.browser import BrowserSession
from horizon_tool.gui.login_worker import LoginWorker
```

Add a module-level mapping near `_COLUMNS`:

```python
_LOGIN_URLS = {
    SERVICE_CHATGPT: "https://chatgpt.com/",
    SERVICE_GROK: "https://grok.com/",
}
```

New `_on_login` (replaces the placeholder):

```python
    def _on_login(self, service: str) -> None:
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
        if ok:
            QMessageBox.information(self, "Đăng nhập", "Đã lưu phiên đăng nhập.")
        self._refresh(service)
```

- [ ] **Step 6: Wire the Accounts window into `gui/main_window.py`**

Add imports at the top of `gui/main_window.py`:

```python
from horizon_tool.core.account_manager import AccountManager
from horizon_tool.gui.accounts_window import AccountsWindow
```

Add module-level constants near `PLUGINS_DIR`:

```python
STATE_DIR = Path(__file__).resolve().parents[1] / "state"
PROFILES_DIR = Path(__file__).resolve().parents[1] / "profiles"
```

In `MainWindow.__init__`, after `self.worker = None`, create the manager:

```python
        self.account_manager = AccountManager(
            STATE_DIR / "accounts.json", PROFILES_DIR)
        self.accounts_window: AccountsWindow | None = None
```

In `_build_controls`, connect the accounts button (it currently has no handler):

```python
        self.accounts_btn.clicked.connect(self.open_accounts_window)
```

Add the method in the behavior section:

```python
    def open_accounts_window(self) -> None:
        """Open (or re-show) the accounts management window."""
        if self.accounts_window is None:
            self.accounts_window = AccountsWindow(self.account_manager, self)
        self.accounts_window.show()
        self.accounts_window.raise_()
```

- [ ] **Step 7: Extend `horizon_tool/tests/test_main_window.py`** with:

```python
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
```

Note: `MainWindow.__init__` reads `STATE_DIR`/`PROFILES_DIR` at construction, so the monkeypatch must be applied before constructing the window (as above).

- [ ] **Step 8: Run the FULL suite**

Run: `cd "D:/Home/wf" && horizon_tool/.venv/Scripts/python.exe -m pytest horizon_tool/tests -q`
Expected: all pass (Phase 1 + Phase 2 tests).

- [ ] **Step 9: Manual smoke check** (offscreen, no real login)

Run:
```
cd "D:/Home/wf" && QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 horizon_tool/.venv/Scripts/python.exe -c "import sys; from pathlib import Path; sys.path.insert(0, r'D:\Home\wf'); from PySide6.QtWidgets import QApplication; from horizon_tool.core.config_loader import AppConfig; from horizon_tool.gui.main_window import MainWindow; app=QApplication([]); w=MainWindow(AppConfig.load(Path(r'D:\Home\wf\horizon_tool\config\config.yaml'))); w.open_accounts_window(); print('accounts window OK, services:', list(w.accounts_window.tables.keys())); app.processEvents()"
```
Expected: prints `accounts window OK, services: ['chatgpt', 'grok']`.

- [ ] **Step 10: Commit**

```bash
cd "D:/Home/wf"
git add horizon_tool/gui/login_worker.py horizon_tool/gui/accounts_window.py horizon_tool/gui/main_window.py horizon_tool/tests/test_login_worker.py horizon_tool/tests/test_main_window.py
git commit -m "feat: wire manual login and open accounts window from main window"
```

---

## Self-Review

**Spec coverage (Phase 2 = spec §16 item 2, plus AC-01/AC-02):**
- Browser core shared by ChatGPT/Grok, persistent context per profile, stable helpers (wait/click-retry/paste), configurable timeouts → Task 3 ✓ (§3.6)
- AC-01 accounts split ChatGPT/Grok, add/remove/rename/enable-disable → Tasks 2, 5 ✓
- AC-02 manual login via profile, never store passwords, "Đã đăng nhập xong" confirm → Tasks 4, 6 ✓
- AC-03 per-account status display (Sẵn sàng/Đang dùng/Hết quota/Phiên hết hạn) → status field + table column (Task 5) ✓ (transitions/auto-detection are Phase 6)
- Rotation selection primitive `next_available` → Task 2 ✓ (full rotation-on-quota is Phase 6)
- State persistence (atomic JSON) → Task 1 ✓ (SEC profile encryption is Phase 8)

**Deferred (intentional):** quota/session auto-detection + rotation (Phase 6); profile encryption at rest (Phase 8); real ChatGPT/Grok selectors (this phase only navigates; login is manual). The login URLs are in `_LOGIN_URLS`; page selectors are not needed for manual login.

**Placeholder scan:** No TODO placeholders in code steps. `_on_login` placeholder in Task 5 is explicitly replaced with a working implementation in Task 6.

**Type consistency:** `Account`/`AccountStore`/`AccountManager` names and method signatures (`add`, `remove`, `rename`, `set_enabled`, `set_status`, `get`, `list`, `next_available`) are consistent across Tasks 1–2 and consumed identically in Tasks 5–6. `BrowserSession(profile_dir, headless=..., element_timeout_ms=..., retry_attempts=...)` matches between Task 3 and the login factory in Task 6. `LoginSession(url, session_factory)` with `open/confirm/cancel/wait_and_close/run` and event `_opened` is consistent between Task 4 and Task 6's `LoginWorker`.

**Testability note:** Browser code is tested headless against local `set_content` (no network). Login lifecycle and login worker are tested with a fake session factory (no real browser). Only the final headful manual-login flow (Task 6 `_on_login`) needs manual verification on the user's machine — it is thin glue over already-tested pieces.
```
