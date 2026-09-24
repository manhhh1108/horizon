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
