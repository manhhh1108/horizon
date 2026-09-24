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
    # Register the finished wait BEFORE confirm(), else the signal can fire in
    # the gap and the wait would miss it (race).
    with qtbot.waitSignal(worker.finished_result, timeout=2000):
        worker.confirm()

    assert results == [True]
    assert fake.closed is True
    worker.wait(2000)


def test_login_worker_emits_false_on_cancel(qtbot):
    app = QCoreApplication.instance() or QCoreApplication([])
    fake = FakeSession()
    worker = LoginWorker("https://x/", session_factory=lambda: fake)
    results = []
    worker.finished_result.connect(results.append)

    with qtbot.waitSignal(worker.opened, timeout=2000):
        worker.start()
    with qtbot.waitSignal(worker.finished_result, timeout=2000):
        worker.cancel()

    assert results == [False]   # cancel -> not logged in
    assert fake.closed is True
    worker.wait(2000)


class ExplodingFactory:
    """Its start() fails, to exercise the open-failure path."""
    def start(self):
        raise RuntimeError("Chromium không khởi động được")
    def goto(self, url, timeout_ms=None):  # pragma: no cover
        pass
    def close(self):  # pragma: no cover
        pass


def test_login_worker_emits_false_on_open_failure(qtbot):
    app = QCoreApplication.instance() or QCoreApplication([])
    worker = LoginWorker("https://x/", session_factory=ExplodingFactory)
    results = []
    worker.finished_result.connect(results.append)
    opened_fired = []
    worker.opened.connect(lambda: opened_fired.append(True))

    with qtbot.waitSignal(worker.finished_result, timeout=2000):
        worker.start()

    assert results == [False]      # failure reported
    assert opened_fired == []      # opened must NOT fire on failure
    worker.wait(2000)
