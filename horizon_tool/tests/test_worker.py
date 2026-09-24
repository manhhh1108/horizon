import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QCoreApplication  # noqa: E402
from horizon_tool.gui.worker import PipelineWorker  # noqa: E402


def test_worker_emits_log_and_finished(qtbot):
    app = QCoreApplication.instance() or QCoreApplication([])
    worker = PipelineWorker(scripts=[1, 2, 3])
    logs: list[str] = []
    worker.log.connect(logs.append)

    with qtbot.waitSignal(worker.done, timeout=3000):
        worker.start()

    assert any("Giai đoạn 1" in m for m in logs)
    assert worker.processed == 3
