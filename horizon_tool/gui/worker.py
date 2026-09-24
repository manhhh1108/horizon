"""Background worker thread. Phase 1 stub + Phase 3 real pipeline worker."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from horizon_tool.core.input_reader import scan_input_folder, filter_by_selection, read_script_content
from horizon_tool.core.pipeline import process_script, STATUS_FAILED


def _close_writer(writer) -> None:
    """Close a writer's browser session if it exposes one (best effort)."""
    session = getattr(writer, "session", None)
    if session is not None and hasattr(session, "close"):
        try:
            session.close()
        except Exception:  # noqa: BLE001 - cleanup must never raise
            pass


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


class ScriptRunWorker(QThread):
    """Runs the Phase-3 script->Word pipeline over an input folder.

    `writer_factory(account) -> ScriptWriter` builds the ChatGPT writer; it is
    injected so the worker can be exercised without a real browser. Cooperative
    pause/stop at script boundaries.
    """

    log = Signal(str)
    progress = Signal(int, str)      # (ordinal, status)
    done = Signal()

    def __init__(self, *, input_dir: str, output_dir: str, selection: str,
                 plugin_text: str, heading_regexes: dict, writer_factory,
                 parent=None) -> None:
        super().__init__(parent)
        self._input_dir = Path(input_dir)
        self._output_dir = Path(output_dir)
        self._selection = selection
        self._plugin_text = plugin_text
        self._heading_regexes = heading_regexes
        self._writer_factory = writer_factory
        self._stop = False
        self._paused = False

    def request_stop(self) -> None:
        self._stop = True

    def set_paused(self, paused: bool) -> None:
        self._paused = paused

    def run(self) -> None:  # noqa: D401 - QThread entry point
        scripts, skipped = scan_input_folder(self._input_dir)
        scripts = filter_by_selection(scripts, self._selection)
        for s in skipped:
            self.log.emit(f"Bỏ qua {s.path.name}: {s.reason}")
        for script in scripts:
            if self._stop:
                self.log.emit("Đã dừng theo yêu cầu.")
                break
            while self._paused and not self._stop:  # cooperative pause at boundary
                self.msleep(100)
            if self._stop:
                self.log.emit("Đã dừng theo yêu cầu.")
                break
            self.progress.emit(script.ordinal, "Đang chạy")
            writer = None
            try:
                out_dir = self._output_dir / str(script.ordinal)
                out_dir.mkdir(parents=True, exist_ok=True)
                writer = self._writer_factory()
                outcome = process_script(
                    writer=writer, ordinal=script.ordinal, output_dir=out_dir,
                    plugin_text=self._plugin_text,
                    script_text=read_script_content(script.path),
                    heading_regexes=self._heading_regexes,
                )
                if outcome.missing_sections:
                    self.log.emit(
                        f"Kịch bản {script.ordinal}: thiếu {len(outcome.missing_sections)} section")
                self.progress.emit(script.ordinal, outcome.word_status)
                self.log.emit(f"Xong kịch bản {script.ordinal} -> {out_dir / str(script.ordinal)}.docx")
            except Exception as exc:  # noqa: BLE001 - one script must not stop the run
                self.progress.emit(script.ordinal, STATUS_FAILED)
                self.log.emit(f"Lỗi kịch bản {script.ordinal}: {exc}")
            finally:
                if writer is not None:
                    _close_writer(writer)  # never leak a browser between scripts
        self.done.emit()
