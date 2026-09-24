"""Background worker thread. Phase 1 stub: proves threading + signal wiring
without any browser automation. Replaced by the real pipeline in later phases.
"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal


class PipelineWorker(QThread):
    """Runs script processing off the GUI thread. Cooperative pause/stop."""

    log = Signal(str)                 # a line for the live log pane
    progress = Signal(int, str)       # (ordinal, status text) for the table
    done = Signal()                   # emitted when the run ends
    # NOTE: QThread already defines a built-in `finished` signal; redefining it
    # as Signal() causes PySide6 to shadow the slot without actually firing it.
    # The plan's original name `finished` was verified to not fire — renamed to
    # `done` per the plan's fallback instruction.

    def __init__(self, scripts: list[int], parent=None) -> None:
        super().__init__(parent)
        self._scripts = scripts
        self._stop = False
        self._paused = False
        self.processed = 0

    def request_stop(self) -> None:
        self._stop = True

    def set_paused(self, paused: bool) -> None:
        self._paused = paused

    def run(self) -> None:  # noqa: D401 - QThread entry point
        self.log.emit("Giai đoạn 1 — pipeline chưa được nối (bản khung).")
        for ordinal in self._scripts:
            if self._stop:
                self.log.emit("Đã dừng theo yêu cầu.")
                break
            while self._paused and not self._stop:
                self.msleep(100)
            self.progress.emit(ordinal, "Xong (giả lập)")
            self.log.emit(f"Đã xử lý (giả lập) kịch bản {ordinal}.")
            self.processed += 1
        self.done.emit()
