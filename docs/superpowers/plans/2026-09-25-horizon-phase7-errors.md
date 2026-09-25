# Horizon X Media Tool — Phase 7 (remaining error handling, spec §12)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`).

**Goal:** the error-table rows from spec §12 not yet covered:
- **Network/page-load failure → retry up to N times with increasing backoff** (config `retry`).
- **Session expired → mark the account, switch to another, tell the user to re-login.**
- **Unknown error → screenshot the browser into the script's output folder, log, move on.**

**Already done (earlier phases):** image/video refusal skip, no-9:16→skip-video, quota rotation, output-conflict (OUT-04), one-script-failure-doesn't-stop-the-run.

**Deferred (live-DOM tuning):** the "response cut off / stalled → click 'Continue generating'" flow — the `[PART X]` CONTINUE loop already covers the documented completion protocol; true stall detection needs the live "Continue generating" selector and is tuned during the selectors session.

**Architecture:** a pure `core/retry.py` (tested, injected sleep); a new `SessionExpired` exception + `detect_session_expired` predicate wired into the DOM read methods; `run_step_with_rotation` gains SessionExpired handling (mark `STATUS_SESSION_EXPIRED`, switch) and an `on_error` hook; `BrowserSession.screenshot` + worker wiring saves `output/<n>/error.png` on an unknown failure.

**Tech Stack:** Python 3.10-compatible, Playwright, PySide6, pytest. **Base branch:** `main` (via `phase-7-errors`, which already carries OUT-04 + plugin editor).

---

### Task 1: Retry with backoff (network/page-load)

**Files:** Create `horizon_tool/core/retry.py`; modify `horizon_tool/automation/browser.py`; test `horizon_tool/tests/test_retry.py`.

- [ ] **Step 1: Write the failing test**

```python
# horizon_tool/tests/test_retry.py
import pytest
from horizon_tool.core.retry import retry_with_backoff


def test_returns_first_success_no_sleep():
    slept = []
    out = retry_with_backoff(lambda: 42, attempts=3, base_seconds=5,
                             sleep=slept.append)
    assert out == 42
    assert slept == []


def test_retries_then_succeeds_with_backoff():
    slept = []
    calls = {"n": 0}
    def fn():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("mạng lỗi")
        return "ok"
    out = retry_with_backoff(fn, attempts=5, base_seconds=2, sleep=slept.append)
    assert out == "ok"
    assert calls["n"] == 3
    assert slept == [2, 4]           # base*2**0, base*2**1 (no sleep after success)


def test_exhausts_and_raises_last():
    slept = []
    def fn():
        raise RuntimeError("down")
    with pytest.raises(RuntimeError):
        retry_with_backoff(fn, attempts=3, base_seconds=1, sleep=slept.append)
    assert slept == [1, 2]           # slept before attempts 2 and 3, not after the last


def test_excluded_exceptions_propagate_immediately():
    slept = []
    class Fatal(Exception):
        pass
    def fn():
        raise Fatal()
    with pytest.raises(Fatal):
        retry_with_backoff(fn, attempts=5, base_seconds=1, sleep=slept.append,
                           exclude=(Fatal,))
    assert slept == []               # no retry for excluded types
```

- [ ] **Step 2: Run test, confirm FAIL.**

- [ ] **Step 3: Implement `core/retry.py`**

```python
"""Retry a callable with exponential backoff (spec §12: network/page-load)."""
from __future__ import annotations

import time
from typing import Callable, Iterable


def retry_with_backoff(fn: Callable, *, attempts: int, base_seconds: float,
                       sleep: Callable[[float], None] = time.sleep,
                       exclude: Iterable[type[BaseException]] = (),
                       log: Callable[[str], None] | None = None):
    """Call fn(); on failure retry up to `attempts` times, sleeping
    base_seconds * 2**i before retry i+1. Exceptions in `exclude` propagate
    immediately (no retry). Re-raises the last error if all attempts fail.
    """
    exclude = tuple(exclude)
    attempts = max(1, attempts)
    last: BaseException | None = None
    for i in range(attempts):
        try:
            return fn()
        except exclude:
            raise
        except Exception as exc:  # noqa: BLE001 - retried below
            last = exc
            if log:
                log(f"Thử lại ({i + 1}/{attempts}) sau lỗi: {exc}")
            if i < attempts - 1:
                sleep(base_seconds * (2 ** i))
    raise last  # type: ignore[misc]
```

- [ ] **Step 4: Integrate into `BrowserSession.goto`** (network/page-load retry)

In `automation/browser.py`: add `retry_backoff_base_seconds: float = 5` to `__init__` (store it), import `from horizon_tool.core.retry import retry_with_backoff` and `from horizon_tool.core.exceptions import QuotaExhausted` — actually goto can't raise those; keep exclude empty. Wrap the navigation:

```python
    def goto(self, url: str, timeout_ms: int | None = None) -> None:
        retry_with_backoff(
            lambda: self.page.goto(url, timeout=self._timeout(timeout_ms)),
            attempts=self.retry_attempts,
            base_seconds=self.retry_backoff_base_seconds,
        )
```

- [ ] **Step 5: Run tests (4 retry) + full suite. Commit.**

```bash
git add horizon_tool/core/retry.py horizon_tool/automation/browser.py horizon_tool/tests/test_retry.py
git commit -m "feat(errors): retry-with-backoff helper; retry page navigation"
```

---

### Task 2: Session-expired detection + rotation + re-login notice

**Files:** modify `horizon_tool/core/exceptions.py`, `horizon_tool/automation/chatgpt.py`, `horizon_tool/automation/grok.py`, `horizon_tool/core/rotation.py`; test `horizon_tool/tests/test_quota_detect.py` (extend), `horizon_tool/tests/test_rotation.py` (extend).

- [ ] **Step 1: Add `SessionExpired` to `core/exceptions.py`**

```python
class SessionExpired(Exception):
    """Raised when a service account's login session has expired."""

    def __init__(self, service: str = "", message: str = "") -> None:
        super().__init__(message or f"Session expired for service: {service!r}")
        self.service = service
```

- [ ] **Step 2: Add `detect_session_expired` + raise in read methods**

In `automation/chatgpt.py`, add near `detect_quota`:

```python
def detect_session_expired(response_text: str, patterns: list[str]) -> bool:
    """True if the page text matches any session-expired pattern (logged out)."""
    return _any_match(response_text, patterns)
```

Import `SessionExpired` from `core.exceptions`. In `_read_last_response`, check session BEFORE quota (a logged-out page can't be "over quota"):

```python
        text = self.session.page.locator(sel["assistant_message"]).last.inner_text()
        if detect_session_expired(text, self.selectors["patterns"]["session_expired"]):
            raise SessionExpired("chatgpt", text)
        if detect_quota(text, self.selectors["patterns"]["quota_exhausted"]):
            raise QuotaExhausted("chatgpt", text)
        return text
```

In `automation/grok.py` `_wait_and_read_status`, add the same session check before the quota check (import `detect_session_expired`, `SessionExpired`).

Extend `test_quota_detect.py`:

```python
def test_detect_session_expired():
    from horizon_tool.automation.chatgpt import detect_session_expired
    pats = ["log in", "session expired"]
    assert detect_session_expired("Please log in to continue", pats)
    assert not detect_session_expired("Here is your story.", pats)
```

- [ ] **Step 3: Handle `SessionExpired` in `run_step_with_rotation`**

In `core/rotation.py`, import `SessionExpired` and add a branch (mirrors quota, different status + message):

```python
from horizon_tool.core.account_manager import (
    AccountManager, STATUS_IN_USE, STATUS_QUOTA, STATUS_READY, STATUS_SESSION_EXPIRED,
)
from horizon_tool.core.exceptions import AllAccountsExhausted, QuotaExhausted, SessionExpired
```
```python
        try:
            worker = make_worker(account)
            result = do_step(worker)
        except QuotaExhausted:
            account_manager.set_status(account.id, STATUS_QUOTA)
            if log:
                log(f"Tài khoản '{account.display_name}' hết quota — chuyển tài khoản khác.")
            continue
        except SessionExpired:
            account_manager.set_status(account.id, STATUS_SESSION_EXPIRED)
            if log:
                log(f"Tài khoản '{account.display_name}': phiên đăng nhập hết hạn — "
                    f"hãy đăng nhập lại. Đang chuyển tài khoản khác.")
            continue
        except Exception:
            ...
```

`next_available` already returns only `STATUS_READY` accounts, so expired ones are skipped and `AllAccountsExhausted` fires when none remain (the worker already pauses + notifies on that).

Extend `test_rotation.py`:

```python
def test_session_expired_marks_and_switches(tmp_path):
    from horizon_tool.core.account_manager import STATUS_SESSION_EXPIRED
    from horizon_tool.core.exceptions import SessionExpired
    mgr = make_mgr(tmp_path, 2)
    a1, a2 = mgr.list(SERVICE_CHATGPT)
    calls = {"n": 0}
    def do_step(w):
        calls["n"] += 1
        if calls["n"] == 1:
            raise SessionExpired("chatgpt")
        return "OK"
    result, account = run_step_with_rotation(
        service=SERVICE_CHATGPT, account_manager=mgr,
        make_worker=lambda acc: FakeWorker(acc), do_step=do_step)
    assert result == "OK"
    assert mgr.get(a1.id).status == STATUS_SESSION_EXPIRED
    assert account.id == a2.id
```

- [ ] **Step 4: Run tests + full suite. Commit.**

```bash
git add horizon_tool/core/exceptions.py horizon_tool/automation/chatgpt.py horizon_tool/automation/grok.py horizon_tool/core/rotation.py horizon_tool/tests/test_quota_detect.py horizon_tool/tests/test_rotation.py
git commit -m "feat(errors): detect session-expired, rotate + mark account, prompt re-login"
```

---

### Task 3: Screenshot on unknown error

**Files:** modify `horizon_tool/automation/browser.py`, `horizon_tool/core/rotation.py`, `horizon_tool/gui/worker.py`; test `horizon_tool/tests/test_browser.py` (extend), `horizon_tool/tests/test_rotation.py` (extend), `horizon_tool/tests/test_script_run_worker.py` (extend).

- [ ] **Step 1: `BrowserSession.screenshot`**

```python
    def screenshot(self, path: str) -> None:
        """Save a full-page screenshot to `path` (best effort, for error capture)."""
        self.page.screenshot(path=str(path), full_page=True)
```

Extend `test_browser.py`:

```python
def test_screenshot_writes_file(session, tmp_path):
    session.page.set_content("<h1>error state</h1>")
    dest = tmp_path / "error.png"
    session.screenshot(str(dest))
    assert dest.exists() and dest.stat().st_size > 0
```

- [ ] **Step 2: `on_error` hook in `run_step_with_rotation`**

Add `on_error: Callable[[Any], None] | None = None` param. In the non-quota/non-session `except Exception` branch, call it before freeing/closing:

```python
        except Exception:
            if on_error is not None:
                try:
                    on_error(worker)
                except Exception:  # noqa: BLE001 - error capture must not mask the real error
                    pass
            account_manager.set_status(account.id, STATUS_READY)
            raise
```

Extend `test_rotation.py`:

```python
def test_on_error_hook_called_before_close(tmp_path):
    mgr = make_mgr(tmp_path, 1)
    captured = {}
    def on_error(worker):
        captured["worker"] = worker
    with pytest.raises(RuntimeError):
        run_step_with_rotation(
            service=SERVICE_CHATGPT, account_manager=mgr,
            make_worker=lambda acc: FakeWorker(acc),
            do_step=lambda w: (_ for _ in ()).throw(RuntimeError("boom")),
            on_error=on_error)
    assert "worker" in captured           # hook fired with the live worker
```

- [ ] **Step 3: Worker wiring — save `output/<n>/error.png`**

In `gui/worker.py`, add a screenshot helper and pass `on_error` to both rotation calls:

```python
    def _screenshot_error(self, worker, out_dir) -> None:
        """Best-effort browser screenshot into the script's output folder."""
        session = getattr(worker, "session", None)
        if session is not None and hasattr(session, "screenshot"):
            try:
                session.screenshot(str(Path(out_dir) / "error.png"))
                self.log.emit(f"Đã lưu ảnh màn hình lỗi: {out_dir}/error.png")
            except Exception:  # noqa: BLE001
                pass
```

Pass to the ChatGPT rotation call:

```python
                    _, chatgpt_account = run_step_with_rotation(
                        service="chatgpt", account_manager=self._accounts,
                        make_worker=self._tracking_factory(self._writer_factory),
                        do_step=lambda w: self._chatgpt_block(w, script, out_dir),
                        log=self.log.emit,
                        on_error=lambda w: self._screenshot_error(w, out_dir),
                    )
```

And to the Grok rotation call in `_run_video_step`:

```python
            _, _ = run_step_with_rotation(
                service="grok", account_manager=self._accounts,
                make_worker=self._tracking_factory(self._video_maker_factory),
                do_step=lambda m: self._grok_block(m, ordinal, out_dir),
                log=self.log.emit,
                on_error=lambda m: self._screenshot_error(m, out_dir),
            )
```

Extend `test_script_run_worker.py` — give `FakeSession` a `screenshot` recorder and assert it's used on an unknown error:

```python
def test_unknown_error_captures_screenshot(qtbot, tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "1.txt").write_text("k", encoding="utf-8")
    mgr = _mgr(tmp_path)
    shots = []

    class ShotSession(FakeSession):
        def screenshot(self, path):
            shots.append(path)
            Path(path).write_bytes(b"PNG")

    class BoomWriter:
        def __init__(self): self.session = ShotSession()
        def write_script(self, *a, **k):
            raise RuntimeError("lỗi lạ")
        def render_image(self, *a, **k):
            from horizon_tool.automation.chatgpt import ImageRenderResult
            return ImageRenderResult(status=STATUS_DONE)

    w = _worker(tmp_path, mgr, writer_factory=lambda acc: BoomWriter(), do_video=False)
    with qtbot.waitSignal(w.done, timeout=5000):
        w.start()
    assert shots and shots[0].endswith("error.png")
    assert (tmp_path / "out" / "1" / "error.png").exists()
    assert w.wait(2000)
```

(Note: `FakeSession` in the test file currently has `close`; adding `screenshot` on the subclass is enough. Ensure the base `FakeSession` used by other fakes still works — subclass only where needed.)

- [ ] **Step 4: Run tests + full suite (exit 0). Commit.**

```bash
git add horizon_tool/automation/browser.py horizon_tool/core/rotation.py horizon_tool/gui/worker.py horizon_tool/tests/test_browser.py horizon_tool/tests/test_rotation.py horizon_tool/tests/test_script_run_worker.py
git commit -m "feat(errors): screenshot browser into output/<n>/error.png on unknown error"
```

---

## Self-Review
- §12 network/page-load → retry with backoff → Task 1 ✓
- §12 session expired → mark account + switch + re-login notice → Task 2 ✓
- §12 unknown error → screenshot to output folder + log + continue (per-script isolation already exists) → Task 3 ✓
- Deferred (live-DOM): "Continue generating" stall click (CONTINUE loop already covers the [PART] protocol).
- Detection predicates are pure/tested; rotation branches tested with fakes; screenshot tested headless. No live selectors required for the logic.
