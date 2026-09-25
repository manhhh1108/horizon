# Horizon X Media Tool — Phase 6 Implementation Plan (quota rotation, state, Resume, report)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Detect account quota, rotate to another same-type account and redo the in-progress step; persist per-script step state after every step; Resume an interrupted run at the exact unfinished step (surviving app/machine restart); auto-pause + notify when a service's accounts are all exhausted; populate `report.xlsx` during the run; and optionally auto-resume by re-checking exhausted accounts on a timer.

**Architecture:** Small pure, unit-tested cores — `core/exceptions.py` (QuotaExhausted / AllAccountsExhausted), `core/state_store.py` (per-script step state, atomic JSON), `core/rotation.py` (`run_step_with_rotation`). Quota detection is a pure predicate; the DOM read methods raise `QuotaExhausted` when it fires (placeholders). `ScriptRunWorker` becomes an orchestrator: per script it runs a **ChatGPT block** (word + images, one session) and a **Grok block** (video) each through `run_step_with_rotation`, skipping steps already terminal in the state (so a switch redoes only the unfinished sub-steps), saving state per step, writing a report row, and ending the run with an `exhausted` signal when a service runs out. The GUI Start/Resume/auto-resume drive it.

**Tech Stack:** Python 3.10-compatible, PySide6, openpyxl, pytest.

**Convention:** UI/log/report text Vietnamese; code identifiers/docstrings/comments English.

**Base branch:** `main`. Work branch: `phase-6-quota-resume`.

**Verified preconditions:** `selectors.yaml` `patterns.quota_exhausted` exists; `config.yaml` `auto_resume` = {enabled: false, check_interval_minutes: 30}. `AccountManager` has `set_status`, `next_available`, `list`, `get`; statuses live in `core/statuses.py` (STATUS_IN_USE/READY/QUOTA present). `report.py` `ReportWriter` exists (Phase 3, tested).

**Honesty note (per user):** The live-DOM ChatGPT/Grok methods stay placeholders. Quota detection is wired into the (placeholder) read methods and the pure predicate is tested; the rotation/state/resume/report/auto-resume logic is fully tested with fakes.

---

### Task 1: Exceptions + State store

**Files:**
- Create: `horizon_tool/core/exceptions.py`
- Create: `horizon_tool/core/state_store.py`
- Test: `horizon_tool/tests/test_state_store.py`

- [ ] **Step 1: Create `core/exceptions.py`**

```python
"""Domain exceptions for account quota and rotation."""
from __future__ import annotations


class QuotaExhausted(Exception):
    """Raised when the current service account has hit its usage quota."""

    def __init__(self, service: str = "", message: str = "") -> None:
        super().__init__(message or f"Quota exhausted for service: {service!r}")
        self.service = service


class AllAccountsExhausted(Exception):
    """Raised when no enabled account of a service has quota left."""

    def __init__(self, service: str) -> None:
        super().__init__(f"All {service!r} accounts are exhausted")
        self.service = service
```

- [ ] **Step 2: Write the failing test**

```python
# horizon_tool/tests/test_state_store.py
from horizon_tool.core.state_store import StateStore
from horizon_tool.core.statuses import STATUS_DONE, STATUS_FAILED, STATUS_REJECTED, STATUS_SKIPPED


def test_set_and_get_step(tmp_path):
    st = StateStore(tmp_path / "run_state.json")
    st.set_step(1, "word", STATUS_DONE)
    assert st.get_step(1, "word") == STATUS_DONE
    assert st.get_step(1, "video") is None


def test_is_done_only_for_terminal_success(tmp_path):
    st = StateStore(tmp_path / "s.json")
    st.set_step(1, "word", STATUS_DONE)
    st.set_step(1, "img_9x16", STATUS_REJECTED)
    st.set_step(1, "img_16x9", STATUS_SKIPPED)
    st.set_step(1, "video", STATUS_FAILED)
    assert st.is_done(1, "word")        # Xong -> done
    assert st.is_done(1, "img_9x16")    # Bị từ chối -> done (won't retry)
    assert st.is_done(1, "img_16x9")    # Bỏ qua -> done
    assert not st.is_done(1, "video")   # Lỗi -> NOT done (retry on resume)
    assert not st.is_done(2, "word")    # unknown -> not done


def test_meta_roundtrip(tmp_path):
    st = StateStore(tmp_path / "s.json")
    st.set_meta(1, "conversation_url", "https://chat/x")
    assert st.get_meta(1, "conversation_url") == "https://chat/x"
    assert st.get_meta(1, "missing") is None


def test_persistence_survives_reload(tmp_path):
    path = tmp_path / "s.json"
    st = StateStore(path)
    st.set_step(3, "word", STATUS_DONE)
    st.set_meta(3, "conversation_url", "u")
    reloaded = StateStore(path)
    assert reloaded.get_step(3, "word") == STATUS_DONE
    assert reloaded.get_meta(3, "conversation_url") == "u"


def test_atomic_save_no_temp_left(tmp_path):
    path = tmp_path / "s.json"
    StateStore(path).set_step(1, "word", STATUS_DONE)
    assert path.exists()
    assert not (tmp_path / "run_state.json.tmp").exists()


def test_corrupt_file_starts_empty(tmp_path):
    path = tmp_path / "s.json"
    path.write_text("{not json", encoding="utf-8")
    st = StateStore(path)  # loads in __init__
    assert st.get_step(1, "word") is None
```

- [ ] **Step 3: Run test, confirm FAIL.**

- [ ] **Step 4: Implement `core/state_store.py`**

```python
"""Per-script step state, persisted atomically for Resume (AC-06/AC-07)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from horizon_tool.core.statuses import STATUS_DONE, STATUS_SKIPPED, STATUS_REJECTED

# Steps that are considered finished and are NOT redone on Resume. A FAILED or
# absent step is unfinished and will be retried.
TERMINAL = {STATUS_DONE, STATUS_SKIPPED, STATUS_REJECTED}


class StateStore:
    """Tracks each script's per-step status + metadata, saved atomically.

    Layout: {"scripts": {"<ordinal>": {"steps": {...}, "meta": {...}}}}.
    Every mutation persists immediately so a crash mid-run is resumable.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._data: dict[str, Any] = {"scripts": {}}
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            self._data = {"scripts": {}}
            return
        try:
            with self.path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            self._data = data if isinstance(data, dict) and "scripts" in data else {"scripts": {}}
        except (json.JSONDecodeError, OSError):
            self._data = {"scripts": {}}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(self._data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def _script(self, ordinal: int) -> dict[str, Any]:
        return self._data["scripts"].setdefault(str(ordinal), {"steps": {}, "meta": {}})

    def set_step(self, ordinal: int, step: str, status: str) -> None:
        self._script(ordinal)["steps"][step] = status
        self._save()

    def get_step(self, ordinal: int, step: str) -> str | None:
        return self._data["scripts"].get(str(ordinal), {}).get("steps", {}).get(step)

    def is_done(self, ordinal: int, step: str) -> bool:
        return self.get_step(ordinal, step) in TERMINAL

    def set_meta(self, ordinal: int, key: str, value: Any) -> None:
        self._script(ordinal)["meta"][key] = value
        self._save()

    def get_meta(self, ordinal: int, key: str) -> Any:
        return self._data["scripts"].get(str(ordinal), {}).get("meta", {}).get(key)
```

- [ ] **Step 5: Run test, confirm 6 passed. Then full suite.**

- [ ] **Step 6: Commit**

```bash
cd "D:/Home/wf"
git add horizon_tool/core/exceptions.py horizon_tool/core/state_store.py horizon_tool/tests/test_state_store.py
git commit -m "feat: quota/rotation exceptions and atomic per-script state store"
```

---

### Task 2: Quota detection + account rotation

**Files:**
- Modify: `horizon_tool/automation/chatgpt.py` (add `matches_any`/`detect_quota`; raise `QuotaExhausted` in read methods)
- Modify: `horizon_tool/automation/grok.py` (raise `QuotaExhausted` in status read)
- Create: `horizon_tool/core/rotation.py`
- Test: `horizon_tool/tests/test_quota_detect.py`, `horizon_tool/tests/test_rotation.py`

- [ ] **Step 1: Write the failing tests**

```python
# horizon_tool/tests/test_quota_detect.py
from horizon_tool.automation.chatgpt import detect_quota

QUOTA = ["you've reached your.*limit", "quota", "try again later"]


def test_detect_quota_true():
    assert detect_quota("You've reached your usage limit for GPT-4.", QUOTA)
    assert detect_quota("Please try again later.", QUOTA)


def test_detect_quota_false():
    assert not detect_quota("Here is your story.", QUOTA)
```

```python
# horizon_tool/tests/test_rotation.py
import pytest

from horizon_tool.core.account_manager import (
    AccountManager, SERVICE_CHATGPT, STATUS_READY, STATUS_QUOTA, STATUS_IN_USE,
)
from horizon_tool.core.exceptions import QuotaExhausted, AllAccountsExhausted
from horizon_tool.core.rotation import run_step_with_rotation


def make_mgr(tmp_path, n):
    mgr = AccountManager(tmp_path / "a.json", tmp_path / "profiles")
    for i in range(n):
        mgr.add(SERVICE_CHATGPT, f"TK{i+1}")
    return mgr


class FakeWorker:
    def __init__(self, account):
        self.account = account
        self.closed = False
        self.session = self  # so _close finds .session.close

    def close(self):
        self.closed = True


def test_first_account_succeeds(tmp_path):
    mgr = make_mgr(tmp_path, 2)
    built = []
    result, account = run_step_with_rotation(
        service=SERVICE_CHATGPT, account_manager=mgr,
        make_worker=lambda acc: built.append(FakeWorker(acc)) or built[-1],
        do_step=lambda w: "OK")
    assert result == "OK"
    assert mgr.get(account.id).status == STATUS_READY   # freed after success
    assert built[-1].closed is True                     # session closed


def test_switches_on_quota(tmp_path):
    mgr = make_mgr(tmp_path, 2)
    a1, a2 = mgr.list(SERVICE_CHATGPT)
    calls = {"n": 0}
    def do_step(w):
        calls["n"] += 1
        if calls["n"] == 1:
            raise QuotaExhausted("chatgpt")
        return "OK"
    result, account = run_step_with_rotation(
        service=SERVICE_CHATGPT, account_manager=mgr,
        make_worker=lambda acc: FakeWorker(acc), do_step=do_step)
    assert result == "OK"
    assert mgr.get(a1.id).status == STATUS_QUOTA   # first marked exhausted
    assert account.id == a2.id                     # second used


def test_all_exhausted_raises(tmp_path):
    mgr = make_mgr(tmp_path, 2)
    with pytest.raises(AllAccountsExhausted):
        run_step_with_rotation(
            service=SERVICE_CHATGPT, account_manager=mgr,
            make_worker=lambda acc: FakeWorker(acc),
            do_step=lambda w: (_ for _ in ()).throw(QuotaExhausted("chatgpt")))
    for acc in mgr.list(SERVICE_CHATGPT):
        assert mgr.get(acc.id).status == STATUS_QUOTA


def test_non_quota_error_frees_account_and_propagates(tmp_path):
    mgr = make_mgr(tmp_path, 2)
    a1 = mgr.list(SERVICE_CHATGPT)[0]
    with pytest.raises(RuntimeError):
        run_step_with_rotation(
            service=SERVICE_CHATGPT, account_manager=mgr,
            make_worker=lambda acc: FakeWorker(acc),
            do_step=lambda w: (_ for _ in ()).throw(RuntimeError("boom")))
    assert mgr.get(a1.id).status == STATUS_READY   # not a quota problem
```

- [ ] **Step 2: Run tests, confirm FAIL.**

- [ ] **Step 3: Add quota detection to `automation/chatgpt.py`**

Add near `detect_refusal` (module level). Refactor `detect_refusal` to share a helper, and add `detect_quota`:

```python
def _any_match(text: str, patterns: list[str]) -> bool:
    return any(re.search(p, text, flags=re.IGNORECASE) for p in patterns)


def detect_refusal(response_text: str, refusal_patterns: list[str]) -> bool:
    """True if the response matches any policy-refusal pattern (case-insensitive)."""
    return _any_match(response_text, refusal_patterns)


def detect_quota(response_text: str, quota_patterns: list[str]) -> bool:
    """True if the response matches any quota-exhausted pattern (case-insensitive)."""
    return _any_match(response_text, quota_patterns)
```

Add the import at the top: `from horizon_tool.core.exceptions import QuotaExhausted`.

In `ChatGPTWriter._read_last_response`, after reading `inner_text()` and before returning, raise on quota:

```python
    def _read_last_response(self) -> str:
        self._wait_response_complete()
        sel = self.selectors["chatgpt"]
        self.session.wait_for(sel["assistant_message"])
        text = self.session.page.locator(sel["assistant_message"]).last.inner_text()
        if detect_quota(text, self.selectors["patterns"]["quota_exhausted"]):
            raise QuotaExhausted("chatgpt", text)
        return text
```

(Adjust to the current method body; the key addition is the quota check on the read text.)

- [ ] **Step 4: Add quota detection to `automation/grok.py`**

Add `from horizon_tool.automation.chatgpt import detect_refusal, detect_quota` (detect_refusal is already imported — extend it) and `from horizon_tool.core.exceptions import QuotaExhausted`. In `_wait_and_read_status`, after obtaining the status text, raise on quota before returning:

```python
        status_text = ""  # (placeholder read result today)
        if detect_quota(status_text, self.selectors["patterns"]["quota_exhausted"]):
            raise QuotaExhausted("grok", status_text)
        return status_text
```

- [ ] **Step 5: Implement `core/rotation.py`**

```python
"""Run a step with automatic account rotation on quota exhaustion (AC-04/05)."""
from __future__ import annotations

from typing import Any, Callable

from horizon_tool.core.account_manager import (
    AccountManager, STATUS_IN_USE, STATUS_QUOTA, STATUS_READY,
)
from horizon_tool.core.exceptions import AllAccountsExhausted, QuotaExhausted


def _close(worker: Any) -> None:
    session = getattr(worker, "session", None)
    if session is not None and hasattr(session, "close"):
        try:
            session.close()
        except Exception:  # noqa: BLE001 - cleanup must never raise
            pass


def run_step_with_rotation(*, service: str, account_manager: AccountManager,
                           make_worker: Callable[[Any], Any],
                           do_step: Callable[[Any], Any],
                           log: Callable[[str], None] | None = None):
    """Run do_step(worker) with rotation; return (result, account).

    Picks an available account, marks it in-use, builds a worker via
    make_worker(account) and runs do_step. On QuotaExhausted the account is
    marked quota_exhausted and the next available account is tried; when none
    remain, AllAccountsExhausted is raised. Any other error frees the account
    (back to ready) and propagates. The worker's session is closed after every
    attempt.
    """
    while True:
        account = account_manager.next_available(service)
        if account is None:
            raise AllAccountsExhausted(service)
        account_manager.set_status(account.id, STATUS_IN_USE)
        worker = make_worker(account)
        try:
            result = do_step(worker)
        except QuotaExhausted:
            account_manager.set_status(account.id, STATUS_QUOTA)
            if log:
                log(f"Tài khoản '{account.display_name}' hết quota — chuyển tài khoản khác.")
            continue
        except Exception:
            account_manager.set_status(account.id, STATUS_READY)
            raise
        else:
            account_manager.set_status(account.id, STATUS_READY)
            return result, account
        finally:
            _close(worker)
```

- [ ] **Step 6: Run tests, confirm quota (2) + rotation (4) pass. Then full suite.**

- [ ] **Step 7: Commit**

```bash
cd "D:/Home/wf"
git add horizon_tool/automation/chatgpt.py horizon_tool/automation/grok.py horizon_tool/core/rotation.py horizon_tool/tests/test_quota_detect.py horizon_tool/tests/test_rotation.py
git commit -m "feat: quota detection + account rotation helper"
```

---

### Task 3: Worker — rotation, state/Resume, pause-on-exhaustion, report

**Files:**
- Modify: `horizon_tool/gui/worker.py` (rewrite `ScriptRunWorker`)
- Test: rewrite `horizon_tool/tests/test_script_run_worker.py`

**Design:** The worker takes `account_manager`, `writer_factory(account)`, `video_maker_factory(account)`, a `state_path`, `resume: bool`, and report metadata (`plugin_name`, `plugin_hash`). Per script it runs two rotated blocks and writes a report row.

- [ ] **Step 1: Rewrite `ScriptRunWorker` in `gui/worker.py`**

Replace the whole `ScriptRunWorker` class (keep `PipelineWorker` and `_close_writer`) with:

```python
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
        """Word + images on one ChatGPT session. Idempotent via state: a rotation
        retry skips sub-steps already terminal, so only unfinished work reruns.
        Raises QuotaExhausted (to the rotation helper) when the account is out.
        """
        ordinal = script.ordinal
        if not (self._resume and self._state.is_done(ordinal, "word")):
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
        else:
            prompts = self._prompts_from_raw(out_dir)   # resumed: reparse
            self.step_status.emit(ordinal, "word", self._state.get_step(ordinal, "word"))

        wraps = self._config.get("chatgpt", {})
        plan = [
            ("img_9x16", self._do_9x16, prompts[0],
             wraps.get("image_wrapper_9x16", "{PROMPT}")),
            ("img_16x9", self._do_16x9, prompts[1],
             wraps.get("image_wrapper_16x9", "{PROMPT}")),
        ]
        for key, enabled, prompt, wrapper in plan:
            if self._resume and self._state.is_done(ordinal, key):
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
                break
            except Exception as exc:  # noqa: BLE001 - one script must not stop the run
                for step in ("word", "img_9x16", "img_16x9", "video"):
                    if not self._state.is_done(ordinal, step):
                        self._state.set_step(ordinal, step, STATUS_FAILED)
                        self.step_status.emit(ordinal, step, STATUS_FAILED)
                self.log.emit(f"Lỗi kịch bản {ordinal}: {exc}")
            self._write_report_row(report, script, account_name, started)
        report.save()
        self.done.emit()

    def _run_video_step(self, ordinal, out_dir):
        if self._resume and self._state.is_done(ordinal, "video"):
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
```

Update the imports at the top of `worker.py`:

```python
import time
from horizon_tool.core.input_reader import scan_input_folder, filter_by_selection, read_script_content
from horizon_tool.core.pipeline import process_script, render_images, make_video
from horizon_tool.core.output_manager import output_paths
from horizon_tool.core.report import ReportWriter
from horizon_tool.core.state_store import StateStore
from horizon_tool.core.rotation import run_step_with_rotation
from horizon_tool.core.exceptions import AllAccountsExhausted
from horizon_tool.core.statuses import (
    STATUS_RUNNING, STATUS_DONE, STATUS_FAILED, STATUS_REJECTED, STATUS_SKIPPED,
)
```

(`render_images` may now be unused in the worker — keep the import only if used; otherwise drop it. It remains covered by `test_render_images.py`.)

- [ ] **Step 2: Rewrite `horizon_tool/tests/test_script_run_worker.py`** to the new constructor (account_manager + factories taking an account). Key tests:

```python
import pytest
import yaml
from pathlib import Path

pytest.importorskip("PySide6")
from PySide6.QtCore import QCoreApplication  # noqa: E402
from horizon_tool.gui.worker import ScriptRunWorker  # noqa: E402
from horizon_tool.automation.chatgpt import ScriptResult, ImageRenderResult  # noqa: E402
from horizon_tool.automation.grok import VideoResult  # noqa: E402
from horizon_tool.core.exceptions import QuotaExhausted  # noqa: E402
from horizon_tool.core.account_manager import (  # noqa: E402
    AccountManager, SERVICE_CHATGPT, SERVICE_GROK, STATUS_QUOTA,
)
from horizon_tool.core.statuses import STATUS_DONE, STATUS_FAILED, STATUS_SKIPPED  # noqa: E402

SELECTORS_PATH = Path(__file__).resolve().parents[1] / "config" / "selectors.yaml"
FULL = """FULL STORY\n\nCHAPTER ONE — X\n\nBody. **twist.**\n\nKEY SCENES + CONTINUITY NOTE\n\ns\n\nIMAGE PROMPT — 9:16\n\ni\n\nTHUMBNAIL PROMPT — 16:9\n\nt\n\nVIDEO AI PROMPT\n\nSHOT 1 — 3s\n\nFACEBOOK TITLE\n\na. b.\n\nFACEBOOK VIDEO DESCRIPTION\n\nd\n\nSTORY TEASER\n\nte\n\nHASHTAGS\n\n#a #b\n"""


class FakeSession:
    def __init__(self): self.closed = False
    def close(self): self.closed = True


class FakeWriter:
    def __init__(self): self.session = FakeSession()
    def write_script(self, *a, **k): return ScriptResult(raw_text=FULL)
    def render_image(self, prompt, wrapper, dest_path):
        Path(dest_path).write_bytes(b"PNG")
        return ImageRenderResult(status=STATUS_DONE, path=dest_path)


class FakeVideoMaker:
    def __init__(self): self.session = FakeSession()
    def make_video(self, image_path, motion_prompt, duration, quality, dest_path):
        Path(dest_path).write_bytes(b"MP4")
        return VideoResult(status=STATUS_DONE, path=dest_path)


def _mgr(tmp_path):
    m = AccountManager(tmp_path / "a.json", tmp_path / "profiles")
    m.add(SERVICE_CHATGPT, "C1"); m.add(SERVICE_GROK, "G1")
    return m


def _cfg():
    return {"chatgpt": {"image_wrapper_9x16": "{PROMPT}", "image_wrapper_16x9": "{PROMPT}"},
            "grok": {"motion_prompt_override": ""}}


def _worker(tmp_path, mgr, **kw):
    (tmp_path / "in").mkdir(exist_ok=True)
    selectors = yaml.safe_load(SELECTORS_PATH.read_text(encoding="utf-8"))
    defaults = dict(
        input_dir=str(tmp_path / "in"), output_dir=str(tmp_path / "out"),
        selection="", plugin_text="PLUGIN", heading_regexes=selectors["section_headings"],
        account_manager=mgr, writer_factory=lambda acc: FakeWriter(),
        video_maker_factory=lambda acc: FakeVideoMaker(), do_9x16=True, do_16x9=True,
        do_video=True, video_duration="15s", video_quality="1080p",
        plugin_name="v11", plugin_hash="hash", config=_cfg())
    defaults.update(kw)
    return ScriptRunWorker(**defaults)


def test_full_pipeline_produces_all_outputs(qtbot, tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "1.txt").write_text("k", encoding="utf-8")
    mgr = _mgr(tmp_path)
    statuses = []
    w = _worker(tmp_path, mgr)
    w.step_status.connect(lambda o, s, st: statuses.append((o, s, st)))
    with qtbot.waitSignal(w.done, timeout=5000):
        w.start()
    out = tmp_path / "out" / "1"
    assert (out / "1.docx").exists() and (out / "1_9x16.png").exists() and (out / "1.mp4").exists()
    assert (tmp_path / "out" / "report.xlsx").exists()
    assert (tmp_path / "out" / "run_state.json").exists()
    assert (1, "video", STATUS_DONE) in statuses
    assert w.wait(2000)


def test_quota_rotates_to_second_account(qtbot, tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "1.txt").write_text("k", encoding="utf-8")
    mgr = AccountManager(tmp_path / "a.json", tmp_path / "profiles")
    a1 = mgr.add(SERVICE_CHATGPT, "C1"); a2 = mgr.add(SERVICE_CHATGPT, "C2")
    mgr.add(SERVICE_GROK, "G1")
    first = {"used": False}
    class QuotaThenOk:
        def __init__(self): self.session = FakeSession()
        def write_script(self, *a, **k):
            if not first["used"]:
                first["used"] = True
                raise QuotaExhausted("chatgpt")
            return ScriptResult(raw_text=FULL)
        def render_image(self, prompt, wrapper, dest_path):
            Path(dest_path).write_bytes(b"PNG"); return ImageRenderResult(status=STATUS_DONE, path=dest_path)
    w = _worker(tmp_path, mgr, writer_factory=lambda acc: QuotaThenOk())
    with qtbot.waitSignal(w.done, timeout=5000):
        w.start()
    assert mgr.get(a1.id).status == STATUS_QUOTA   # first exhausted
    assert (tmp_path / "out" / "1" / "1.docx").exists()  # succeeded on the second
    assert w.wait(2000)


def test_all_exhausted_emits_and_stops(qtbot, tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "1.txt").write_text("k", encoding="utf-8")
    mgr = AccountManager(tmp_path / "a.json", tmp_path / "profiles")
    mgr.add(SERVICE_CHATGPT, "C1")
    class AlwaysQuota:
        def __init__(self): self.session = FakeSession()
        def write_script(self, *a, **k): raise QuotaExhausted("chatgpt")
        def render_image(self, *a, **k): return ImageRenderResult(status=STATUS_DONE)
    events = []
    w = _worker(tmp_path, mgr, writer_factory=lambda acc: AlwaysQuota(),
                video_maker_factory=None)
    w.exhausted.connect(events.append)
    with qtbot.waitSignal(w.done, timeout=5000):
        w.start()
    assert events == ["chatgpt"]
    assert w.wait(2000)


def test_resume_skips_completed_steps(qtbot, tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "1.txt").write_text("k", encoding="utf-8")
    mgr = _mgr(tmp_path)
    # First run completes everything.
    w1 = _worker(tmp_path, mgr)
    with qtbot.waitSignal(w1.done, timeout=5000):
        w1.start()
    assert w1.wait(2000)
    # Second run in resume mode must NOT call the writer again for the word step.
    calls = {"n": 0}
    class CountingWriter(FakeWriter):
        def write_script(self, *a, **k):
            calls["n"] += 1
            return super().write_script(*a, **k)
    w2 = _worker(tmp_path, mgr, writer_factory=lambda acc: CountingWriter(), resume=True)
    with qtbot.waitSignal(w2.done, timeout=5000):
        w2.start()
    assert calls["n"] == 0   # word already done -> not re-run
    assert w2.wait(2000)
```

- [ ] **Step 3: Run the worker tests, confirm pass. Then the full suite (exit 0).**

- [ ] **Step 4: Commit**

```bash
cd "D:/Home/wf"
git add horizon_tool/gui/worker.py horizon_tool/tests/test_script_run_worker.py
git commit -m "feat: worker rotation, per-step state, Resume, exhaustion pause, report rows"
```

---

### Task 4: GUI — Start/Resume/exhaustion + optional auto-resume

**Files:**
- Modify: `horizon_tool/gui/main_window.py`
- Test: extend `horizon_tool/tests/test_main_window.py`

- [ ] **Step 1: Update `gui/main_window.py`**

Factor worker construction into a helper that both Start and Resume use, add the exhaustion handler, and wire the auto-resume timer. Add imports:

```python
from PySide6.QtCore import QTimer
from horizon_tool.core.plugin_manager import read_plugin_text, apply_variables, plugin_hash
from horizon_tool.core.account_manager import STATUS_QUOTA, STATUS_READY
```

Add to `__init__` (after `self.accounts_window = None`):

```python
        self._auto_resume_timer = QTimer(self)
        self._auto_resume_timer.timeout.connect(self._auto_resume_tick)
```

Replace `on_start` and add helpers:

```python
    def on_start(self) -> None:
        self._launch_run(resume=False)

    def on_resume(self) -> None:
        # Resume a paused running worker, or start a fresh worker in resume mode.
        if self.worker is not None and self.worker.isRunning():
            self._set_paused(False)
            return
        self._launch_run(resume=True)

    def _launch_run(self, *, resume: bool) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        input_dir = self.input_edit.text().strip()
        output_dir = self.output_edit.text().strip()
        plugin_path = self.plugin_combo.currentData()
        if not input_dir or not output_dir or not plugin_path:
            self.append_log("Hãy chọn thư mục input, output và plugin trước khi chạy.")
            return
        selectors = load_yaml(SELECTORS_PATH)
        raw_plugin = read_plugin_text(Path(plugin_path))
        plugin_text = apply_variables(raw_plugin, {
            "VIDEO_DURATION": self.duration_combo.currentText(),
            "VIDEO_QUALITY": self.quality_combo.currentText()})

        el_ms = self.config.raw.get("timeouts", {}).get("element_wait_seconds", 30) * 1000

        def writer_factory(account):
            session = BrowserSession(account.profile_dir, headless=False, element_timeout_ms=el_ms)
            session.start()
            return ChatGPTWriter(session, selectors, self.config.raw)

        def video_maker_factory(account):
            from horizon_tool.automation.grok import GrokVideoMaker
            session = BrowserSession(account.profile_dir, headless=False, element_timeout_ms=el_ms)
            session.start()
            return GrokVideoMaker(session, selectors, self.config.raw)

        if not resume:
            self.table.setRowCount(0)
        self.worker = ScriptRunWorker(
            input_dir=input_dir, output_dir=output_dir,
            selection=self.range_edit.text().strip(), plugin_text=plugin_text,
            heading_regexes=selectors["section_headings"], account_manager=self.account_manager,
            writer_factory=writer_factory, video_maker_factory=video_maker_factory,
            do_9x16=self.step_img_9x16.isChecked(), do_16x9=self.step_thumb_16x9.isChecked(),
            do_video=self.step_video.isChecked(),
            video_duration=self.duration_combo.currentText(),
            video_quality=self.quality_combo.currentText(),
            plugin_name=self.plugin_combo.currentText(),
            plugin_hash=plugin_hash(raw_plugin),
            state_path=str(Path(output_dir) / "run_state.json"), resume=resume,
            config=self.config.raw, parent=self)
        self.worker.log.connect(self.append_log)
        self.worker.step_status.connect(self._on_step_status)
        self.worker.exhausted.connect(self._on_exhausted)
        self.worker.done.connect(self._on_worker_done)
        self._set_running_state(True)
        self.worker.start()

    def _on_exhausted(self, service: str) -> None:
        self.append_log(f"Đã hết tài khoản {service}. Nhấn Tiếp tục khi quota hồi, hoặc bật tự động Resume trong Cài đặt.")
        auto = self.config.raw.get("auto_resume", {})
        if auto.get("enabled"):
            minutes = int(auto.get("check_interval_minutes", 30))
            self._auto_resume_timer.start(max(1, minutes) * 60 * 1000)

    def _auto_resume_tick(self) -> None:
        # Re-check quota accounts: mark them ready again and resume the run.
        if self.worker is not None and self.worker.isRunning():
            return
        reset = 0
        for acc in self.account_manager.list():
            if acc.status == STATUS_QUOTA:
                self.account_manager.set_status(acc.id, STATUS_READY)
                reset += 1
        if reset:
            self.append_log(f"Tự động Resume: đã đặt lại {reset} tài khoản hết quota.")
            self._auto_resume_timer.stop()
            self.on_resume()
```

Update the Resume button connection in `_build_controls` (it currently calls `lambda: self._set_paused(False)`):

```python
        self.resume_btn.clicked.connect(self.on_resume)
```

Also stop the auto-resume timer in `_on_worker_done` (so a completed run doesn't keep ticking):

```python
    def _on_worker_done(self) -> None:
        self._auto_resume_timer.stop()
        self._set_running_state(False)
```

- [ ] **Step 2: Extend `test_main_window.py`**

```python
def test_resume_button_starts_resume_run_when_idle(qtbot, tmp_path, monkeypatch):
    import horizon_tool.gui.main_window as mw
    monkeypatch.setattr(mw, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(mw, "PROFILES_DIR", tmp_path / "profiles")
    app = QApplication.instance() or QApplication([])
    win = mw.MainWindow(AppConfig.load(CONFIG))
    qtbot.addWidget(win)
    launched = {}
    monkeypatch.setattr(win, "_launch_run", lambda *, resume: launched.setdefault("resume", resume))
    win.on_resume()   # idle -> should launch a resume run
    assert launched == {"resume": True}


def test_on_exhausted_logs(qtbot, tmp_path, monkeypatch):
    import horizon_tool.gui.main_window as mw
    monkeypatch.setattr(mw, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(mw, "PROFILES_DIR", tmp_path / "profiles")
    app = QApplication.instance() or QApplication([])
    win = mw.MainWindow(AppConfig.load(CONFIG))
    qtbot.addWidget(win)
    win._on_exhausted("chatgpt")
    assert "hết tài khoản chatgpt" in win.log_pane.toPlainText().lower()
```

- [ ] **Step 3: Run the FULL suite, then smoke check**

Run: `cd "D:/Home/wf" && horizon_tool/.venv/Scripts/python.exe -m pytest horizon_tool/tests -q` — all pass, exit 0.

Smoke (offscreen; guard path):
```
QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 horizon_tool/.venv/Scripts/python.exe -c "import sys; from pathlib import Path; sys.path.insert(0, r'D:\Home\wf'); from PySide6.QtWidgets import QApplication; from horizon_tool.core.config_loader import AppConfig; from horizon_tool.gui.main_window import MainWindow; app=QApplication([]); w=MainWindow(AppConfig.load(Path(r'D:\Home\wf\horizon_tool\config\config.yaml'))); w.on_resume(); print('resume-guard log:', 'Hãy chọn' in w.log_pane.toPlainText()); app.processEvents()"
```
Expect: `resume-guard log: True` (idle Resume with no inputs hits the same guard).

- [ ] **Step 4: Commit**

```bash
cd "D:/Home/wf"
git add horizon_tool/gui/main_window.py horizon_tool/tests/test_main_window.py
git commit -m "feat: Start/Resume wiring, exhaustion notice, optional auto-resume timer"
```

---

## Self-Review

**Spec coverage (Phase 6 = spec §16 item 6 / §11 AC-03..AC-08):**
- AC-03 per-account status display → rotation sets in_use/ready/quota_exhausted on the manager; the Accounts window already renders the status column ✓
- AC-04 detect quota, switch same-type account, redo the in-progress step → `detect_quota` + `QuotaExhausted` + `run_step_with_rotation`; state makes the retry skip already-terminal sub-steps so only the unfinished step reruns ✓
- AC-05 all accounts of a type exhausted → auto-pause + save state + notify → `AllAccountsExhausted` ends the run, `exhausted` signal, state already persisted ✓
- AC-06 save state after each step (atomic JSON: which script/step/URL/files) → `StateStore` per-step + meta (conversation_url, video_prompt) ✓
- AC-07 Resume at the exact unfinished step, surviving restart → `resume=True` skips terminal steps using the on-disk state; prompts re-parsed from `raw_response.txt` ✓
- AC-08 optional auto-resume on a configurable cycle → `_auto_resume_timer` driven by `config.auto_resume` ✓
- Report population (deferred from Phases 3–5) → `ReportWriter` row per script with plugin+hash, account, per-step statuses, duration ✓

**Deferred (intentional):** live-DOM ChatGPT/Grok methods remain placeholders (quota detection is wired into them but only the pure predicate is tested). OUT-04 folder-conflict dialog and per-section "missing" report detail remain minimal (report `missing_sections` left blank for now; the log already reports missing counts).

**Placeholder scan:** No new TODO in code beyond the pre-existing live-DOM selector markers.

**Type/name consistency:** `run_step_with_rotation(service, account_manager, make_worker, do_step, log) -> (result, account)` matches worker calls. Factories now take an `account` (`writer_factory(account)`, `video_maker_factory(account)`) — the worker, GUI, and tests agree. `StateStore` API (set_step/get_step/is_done/set_meta/get_meta) is used consistently. Statuses from `core/statuses.py`. `exhausted(str)` signal matches `_on_exhausted`.
