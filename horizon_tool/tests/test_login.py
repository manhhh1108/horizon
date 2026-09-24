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
    assert login._opened.is_set()
    assert login.opened_ok is True


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


class ExplodingFactory:
    """A session whose start() fails, to test the failure path."""
    def start(self):
        raise RuntimeError("Chromium không khởi động được")
    def goto(self, url, timeout_ms=None):  # pragma: no cover - never reached
        pass
    def close(self):  # pragma: no cover
        pass


def test_run_returns_false_and_unblocks_on_open_failure():
    login = LoginSession("https://x/", session_factory=ExplodingFactory)
    result = {}
    t = threading.Thread(target=lambda: result.setdefault("ok", login.run()))
    t.start()
    # A controller waiting on _opened must not hang even though open() failed.
    assert login._opened.wait(timeout=2) is True
    t.join(timeout=2)
    assert result["ok"] is False
    assert login.opened_ok is False
    assert login.error is not None
