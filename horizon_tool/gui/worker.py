"""Background worker thread. Phase 1 stub + Phase 3 real pipeline worker."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from horizon_tool.core.input_reader import scan_input_folder, filter_by_selection, read_script_content
from horizon_tool.core.pipeline import process_script, render_images, make_video
from horizon_tool.core.statuses import STATUS_RUNNING, STATUS_FAILED, STATUS_REJECTED, STATUS_DONE, STATUS_SKIPPED
from horizon_tool.core.output_manager import output_paths


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
    """Runs the Phase-3 script->Word pipeline over an input folder, then renders images.

    `writer_factory() -> ScriptWriter` builds the ChatGPT writer; it is
    injected so the worker can be exercised without a real browser. Cooperative
    pause/stop at script boundaries.
    """

    log = Signal(str)
    step_status = Signal(int, str, str)   # (ordinal, step_key, status)
    done = Signal()

    def __init__(self, *, input_dir: str, output_dir: str, selection: str,
                 plugin_text: str, heading_regexes: dict, writer_factory,
                 do_9x16: bool = True, do_16x9: bool = True,
                 do_video: bool = True, video_maker_factory=None,
                 video_duration: str = "", video_quality: str = "",
                 config: dict | None = None, parent=None) -> None:
        super().__init__(parent)
        self._input_dir = Path(input_dir)
        self._output_dir = Path(output_dir)
        self._selection = selection
        self._plugin_text = plugin_text
        self._heading_regexes = heading_regexes
        self._writer_factory = writer_factory
        self._do_9x16 = do_9x16
        self._do_16x9 = do_16x9
        self._do_video = do_video
        self._video_maker_factory = video_maker_factory
        self._video_duration = video_duration
        self._video_quality = video_quality
        self._config = config or {}
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
            while self._paused and not self._stop:
                self.msleep(100)
            if self._stop:
                self.log.emit("Đã dừng theo yêu cầu.")
                break
            self.step_status.emit(script.ordinal, "word", STATUS_RUNNING)
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
                self.step_status.emit(script.ordinal, "word", outcome.word_status)
                self.log.emit(f"Xong Word kịch bản {script.ordinal}")
                # TODO (Phase 6): add a ReportWriter row for this script.

                img = render_images(
                    writer=writer, output_dir=out_dir, ordinal=script.ordinal,
                    config=self._config,
                    image_9x16_prompt=outcome.image_9x16_prompt,
                    thumbnail_16x9_prompt=outcome.thumbnail_16x9_prompt,
                    do_9x16=self._do_9x16, do_16x9=self._do_16x9,
                )
                self.step_status.emit(script.ordinal, "img_9x16", img["img_9x16"])
                self.step_status.emit(script.ordinal, "img_16x9", img["img_16x9"])
                self.log.emit(
                    f"Ảnh kịch bản {script.ordinal}: 9:16={img['img_9x16']}, 16:9={img['img_16x9']}")
                # Dedicated refusal log (spec §7.4: log the rejection explicitly).
                for label, status in (("9:16", img["img_9x16"]), ("16:9", img["img_16x9"])):
                    if status == STATUS_REJECTED:
                        self.log.emit(
                            f"Kịch bản {script.ordinal} ảnh {label} bị từ chối (vi phạm chính sách) — bỏ qua, không thử lại.")

                # Video step: needs the 9:16 image. Uses a SEPARATE Grok session.
                img_9x16_path = str(output_paths(out_dir, script.ordinal)["img_9x16"])
                have_9x16 = img["img_9x16"] == STATUS_DONE
                if not self._do_video:
                    self.step_status.emit(script.ordinal, "video", STATUS_SKIPPED)
                elif not have_9x16:
                    self.step_status.emit(script.ordinal, "video", STATUS_SKIPPED)
                    self.log.emit(f"Kịch bản {script.ordinal}: không có ảnh 9:16 — bỏ qua video.")
                elif self._video_maker_factory is None:
                    self.step_status.emit(script.ordinal, "video", STATUS_SKIPPED)
                else:
                    maker = None
                    v_status = STATUS_FAILED
                    try:
                        maker = self._video_maker_factory()
                        v_status = make_video(
                            maker=maker, output_dir=out_dir, ordinal=script.ordinal,
                            config=self._config, motion_prompt=outcome.video_prompt,
                            duration=self._video_duration, quality=self._video_quality,
                            image_path=img_9x16_path, do_video=True,
                        )
                    except Exception as exc:  # noqa: BLE001 - contain video errors
                        # A video failure (e.g. no Grok account) must NOT clobber
                        # the word/image results — keep it in the video column.
                        self.log.emit(f"Lỗi video kịch bản {script.ordinal}: {exc}")
                    finally:
                        if maker is not None:
                            _close_writer(maker)  # closes maker.session too
                    self.step_status.emit(script.ordinal, "video", v_status)
                    if v_status == STATUS_REJECTED:
                        self.log.emit(
                            f"Kịch bản {script.ordinal} video bị từ chối — bỏ qua, không thử lại.")
                    elif v_status != STATUS_FAILED:
                        self.log.emit(f"Video kịch bản {script.ordinal}: {v_status}")
            except Exception as exc:  # noqa: BLE001 - one script must not stop the run
                # The script that produces the image prompts failed, so every
                # column resolves to a terminal state (no blank cells).
                self.step_status.emit(script.ordinal, "word", STATUS_FAILED)
                self.step_status.emit(script.ordinal, "img_9x16", STATUS_FAILED)
                self.step_status.emit(script.ordinal, "img_16x9", STATUS_FAILED)
                self.step_status.emit(script.ordinal, "video", STATUS_FAILED)
                self.log.emit(f"Lỗi kịch bản {script.ordinal}: {exc}")
                # TODO (Phase 6): add a ReportWriter row with error=str(exc).
            finally:
                if writer is not None:
                    _close_writer(writer)
        self.done.emit()
