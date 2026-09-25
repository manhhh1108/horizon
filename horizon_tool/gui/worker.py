"""Background worker thread. Phase 1 stub + Phase 6 rotation/state/report worker."""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from horizon_tool.core.input_reader import scan_input_folder, filter_by_selection, read_script_content
from horizon_tool.core.pipeline import process_script, make_video
from horizon_tool.core.output_manager import output_paths
from horizon_tool.core.report import ReportWriter
from horizon_tool.core.state_store import StateStore
from horizon_tool.core.rotation import run_step_with_rotation
from horizon_tool.core.exceptions import AllAccountsExhausted
from horizon_tool.core.statuses import (
    STATUS_RUNNING, STATUS_DONE, STATUS_FAILED, STATUS_REJECTED, STATUS_SKIPPED,
)


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
    """Runs the full pipeline over an input folder with quota rotation, state
    persistence, Resume, and report output. ChatGPT (word + images) and Grok
    (video) each rotate accounts independently; a service running out ends the
    run with `exhausted` so the user (or auto-resume) can continue later.
    """

    log = Signal(str)
    step_status = Signal(int, str, str)     # (ordinal, step_key, status)
    exhausted = Signal(str)                 # a service ran out of accounts
    done = Signal()

    def __init__(self, *, input_dir: str, output_dir: str, selection: str,
                 plugin_text: str, heading_regexes: dict, account_manager,
                 writer_factory, video_maker_factory=None,
                 do_9x16: bool = True, do_16x9: bool = True, do_video: bool = True,
                 video_duration: str = "", video_quality: str = "",
                 plugin_name: str = "", plugin_hash: str = "",
                 state_path: str | None = None, resume: bool = False,
                 config: dict | None = None, parent=None) -> None:
        super().__init__(parent)
        self._input_dir = Path(input_dir)
        self._output_dir = Path(output_dir)
        self._selection = selection
        self._plugin_text = plugin_text
        self._heading_regexes = heading_regexes
        self._accounts = account_manager
        self._writer_factory = writer_factory
        self._video_maker_factory = video_maker_factory
        self._do_9x16 = do_9x16
        self._do_16x9 = do_16x9
        self._do_video = do_video
        self._video_duration = video_duration
        self._video_quality = video_quality
        self._plugin_name = plugin_name
        self._plugin_hash = plugin_hash
        self._resume = resume
        self._config = config or {}
        self._state = StateStore(Path(state_path) if state_path
                                 else self._output_dir / "run_state.json")
        self._stop = False
        self._paused = False

    def request_stop(self) -> None:
        self._stop = True

    def set_paused(self, paused: bool) -> None:
        self._paused = paused

    # ----- per-script blocks (run inside rotation) ------------------------
    def _chatgpt_block(self, writer, script, out_dir):
        """Word + images on one ChatGPT session.

        Idempotent via state: any sub-step already terminal in the state is
        skipped. This makes a rotation retry (a fresh account after a quota
        switch mid-block) redo ONLY the unfinished sub-steps — the word step is
        never regenerated once it succeeded. A fresh (non-resume) run clears the
        state first, so the skip reflects only this run's progress. Raises
        QuotaExhausted (to the rotation helper) when the account is out.
        """
        ordinal = script.ordinal
        if self._state.is_done(ordinal, "word"):
            prompts = self._prompts_from_raw(out_dir)   # word done -> reparse prompts
            self.step_status.emit(ordinal, "word", self._state.get_step(ordinal, "word"))
        else:
            outcome = process_script(
                writer=writer, ordinal=ordinal, output_dir=out_dir,
                plugin_text=self._plugin_text,
                script_text=read_script_content(script.path),
                heading_regexes=self._heading_regexes,
            )
            self._state.set_meta(ordinal, "conversation_url", outcome.conversation_url or "")
            self._state.set_step(ordinal, "word", outcome.word_status)
            self.step_status.emit(ordinal, "word", outcome.word_status)
            if outcome.missing_sections:
                self.log.emit(f"Kịch bản {ordinal}: thiếu {len(outcome.missing_sections)} section")
            prompts = (outcome.image_9x16_prompt, outcome.thumbnail_16x9_prompt)

        wraps = self._config.get("chatgpt", {})
        plan = [
            ("img_9x16", self._do_9x16, prompts[0],
             wraps.get("image_wrapper_9x16", "{PROMPT}")),
            ("img_16x9", self._do_16x9, prompts[1],
             wraps.get("image_wrapper_16x9", "{PROMPT}")),
        ]
        for key, enabled, prompt, wrapper in plan:
            if self._state.is_done(ordinal, key):   # already produced -> don't redo
                self.step_status.emit(ordinal, key, self._state.get_step(ordinal, key))
                continue
            if not enabled or not prompt:
                status = STATUS_SKIPPED
            else:
                dest = str(output_paths(out_dir, ordinal)[key])
                status = writer.render_image(prompt, wrapper, dest).status  # may raise QuotaExhausted
            self._state.set_step(ordinal, key, status)
            self.step_status.emit(ordinal, key, status)
            if status == STATUS_REJECTED:
                self.log.emit(f"Kịch bản {ordinal} ảnh {key} bị từ chối — bỏ qua, không thử lại.")

    def _grok_block(self, maker, ordinal, out_dir):
        image_path = str(output_paths(out_dir, ordinal)["img_9x16"])
        status = make_video(
            maker=maker, output_dir=out_dir, ordinal=ordinal, config=self._config,
            motion_prompt=self._state.get_meta(ordinal, "video_prompt"),
            duration=self._video_duration, quality=self._video_quality,
            image_path=image_path, do_video=True,
        )  # make_video swallows non-quota errors; QuotaExhausted propagates
        self._state.set_step(ordinal, "video", status)
        self.step_status.emit(ordinal, "video", status)
        return status

    def _prompts_from_raw(self, out_dir):
        """Re-parse section 3/4 prompts from a resumed script's raw_response.txt."""
        from horizon_tool.core.section_parser import parse_sections
        raw_path = out_dir / "raw_response.txt"
        if not raw_path.exists():
            return (None, None)
        parsed = parse_sections(raw_path.read_text(encoding="utf-8"), self._heading_regexes)
        return (parsed.sections.get("image_9x16"), parsed.sections.get("thumbnail_16x9"))

    # ----- main loop ------------------------------------------------------
    def run(self) -> None:  # noqa: D401 - QThread entry point
        scripts, skipped = scan_input_folder(self._input_dir)
        scripts = filter_by_selection(scripts, self._selection)
        for s in skipped:
            self.log.emit(f"Bỏ qua {s.path.name}: {s.reason}")

        if not self._resume:
            self._state.clear()   # fresh run: skip decisions reflect only this run

        report = ReportWriter(self._output_dir / "report.xlsx")
        for script in scripts:
            if self._stop:
                self.log.emit("Đã dừng theo yêu cầu.")
                break
            while self._paused and not self._stop:
                self.msleep(100)
            if self._stop:
                break
            ordinal = script.ordinal
            out_dir = self._output_dir / str(ordinal)
            out_dir.mkdir(parents=True, exist_ok=True)
            started = time.monotonic()
            account_name = ""
            stop_after = False
            try:
                self.step_status.emit(ordinal, "word", STATUS_RUNNING)
                _, chatgpt_account = run_step_with_rotation(
                    service="chatgpt", account_manager=self._accounts,
                    make_worker=self._writer_factory,
                    do_step=lambda w: self._chatgpt_block(w, script, out_dir),
                    log=self.log.emit,
                )
                account_name = chatgpt_account.display_name
                # persist section-5 motion prompt for the (separate) Grok block
                self._save_video_prompt(ordinal, out_dir)
                self._run_video_step(ordinal, out_dir)
            except AllAccountsExhausted as exc:
                self.log.emit(f"Hết tài khoản {exc.service} — tạm dừng, đã lưu trạng thái.")
                self.exhausted.emit(exc.service)
                stop_after = True   # end the run after recording this script's row
            except Exception as exc:  # noqa: BLE001 - one script must not stop the run
                for step in ("word", "img_9x16", "img_16x9", "video"):
                    if not self._state.is_done(ordinal, step):
                        self._state.set_step(ordinal, step, STATUS_FAILED)
                        self.step_status.emit(ordinal, step, STATUS_FAILED)
                self.log.emit(f"Lỗi kịch bản {ordinal}: {exc}")
            finally:
                # Always record the row, including the script that hit exhaustion.
                self._write_report_row(report, script, account_name, started)
            if stop_after:
                break
        report.save()
        self.done.emit()

    def _run_video_step(self, ordinal, out_dir):
        if self._state.is_done(ordinal, "video"):   # already terminal -> skip
            self.step_status.emit(ordinal, "video", self._state.get_step(ordinal, "video"))
            return
        have_9x16 = self._state.get_step(ordinal, "img_9x16") == STATUS_DONE
        if not self._do_video or not have_9x16 or self._video_maker_factory is None:
            self._state.set_step(ordinal, "video", STATUS_SKIPPED)
            self.step_status.emit(ordinal, "video", STATUS_SKIPPED)
            if self._do_video and not have_9x16:
                self.log.emit(f"Kịch bản {ordinal}: không có ảnh 9:16 — bỏ qua video.")
            return
        try:
            _, _ = run_step_with_rotation(
                service="grok", account_manager=self._accounts,
                make_worker=self._video_maker_factory,
                do_step=lambda m: self._grok_block(m, ordinal, out_dir),
                log=self.log.emit,
            )
        except AllAccountsExhausted:
            raise
        except Exception as exc:  # noqa: BLE001 - contain video errors to its column
            self._state.set_step(ordinal, "video", STATUS_FAILED)
            self.step_status.emit(ordinal, "video", STATUS_FAILED)
            self.log.emit(f"Lỗi video kịch bản {ordinal}: {exc}")

    def _save_video_prompt(self, ordinal, out_dir):
        if self._state.get_meta(ordinal, "video_prompt") is not None:
            return
        prompt = None
        raw = out_dir / "raw_response.txt"
        if raw.exists():
            from horizon_tool.core.section_parser import parse_sections
            parsed = parse_sections(raw.read_text(encoding="utf-8"), self._heading_regexes)
            prompt = parsed.sections.get("video_prompt")
        self._state.set_meta(ordinal, "video_prompt", prompt or "")

    def _write_report_row(self, report, script, account_name, started):
        gs = lambda step: self._state.get_step(script.ordinal, step) or ""
        report.add_row(
            ordinal=script.ordinal, input_filename=script.path.name,
            plugin_name=self._plugin_name, plugin_hash=self._plugin_hash,
            account=account_name, word=gs("word"), img_9x16=gs("img_9x16"),
            img_16x9=gs("img_16x9"), video=gs("video"), missing_sections="",
            error="", duration_seconds=time.monotonic() - started,
        )
        report.save()
