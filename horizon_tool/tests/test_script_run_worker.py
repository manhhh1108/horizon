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


def test_video_quota_rotates_to_second_grok_account(qtbot, tmp_path):
    # The Grok/video step must rotate accounts on quota (not silently swallow it).
    app = QCoreApplication.instance() or QCoreApplication([])
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "1.txt").write_text("k", encoding="utf-8")
    mgr = AccountManager(tmp_path / "a.json", tmp_path / "profiles")
    mgr.add(SERVICE_CHATGPT, "C1")
    g1 = mgr.add(SERVICE_GROK, "G1"); g2 = mgr.add(SERVICE_GROK, "G2")
    quota = {"fired": False}

    class QuotaThenOkVideo:
        def __init__(self): self.session = FakeSession()
        def make_video(self, image_path, motion_prompt, duration, quality, dest_path):
            if not quota["fired"]:
                quota["fired"] = True
                raise QuotaExhausted("grok")
            Path(dest_path).write_bytes(b"MP4")
            return VideoResult(status=STATUS_DONE, path=dest_path)

    statuses = []
    w = _worker(tmp_path, mgr, video_maker_factory=lambda acc: QuotaThenOkVideo())
    w.step_status.connect(lambda o, s, st: statuses.append((o, s, st)))
    with qtbot.waitSignal(w.done, timeout=5000):
        w.start()
    assert mgr.get(g1.id).status == STATUS_QUOTA          # first grok account exhausted
    assert (tmp_path / "out" / "1" / "1.mp4").exists()    # video made on the second
    assert (1, "video", STATUS_DONE) in statuses
    assert w.wait(2000)


def test_intra_run_rotation_redoes_only_unfinished_substep(qtbot, tmp_path):
    # Word + the 9:16 image succeed on account 1; the 16:9 image hits quota.
    # After switching to account 2, ONLY the 16:9 image is redone — the word
    # step and the already-done 9:16 image are NOT re-run (fresh run, no resume).
    app = QCoreApplication.instance() or QCoreApplication([])
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "1.txt").write_text("k", encoding="utf-8")
    mgr = AccountManager(tmp_path / "a.json", tmp_path / "profiles")
    mgr.add(SERVICE_CHATGPT, "C1"); mgr.add(SERVICE_CHATGPT, "C2")
    mgr.add(SERVICE_GROK, "G1")
    counters = {"word": 0, "img9": 0, "img16": 0}
    quota = {"fired": False}

    class W:
        def __init__(self): self.session = FakeSession()
        def write_script(self, *a, **k):
            counters["word"] += 1
            return ScriptResult(raw_text=FULL)
        def render_image(self, prompt, wrapper, dest_path):
            if "9x16" in dest_path:
                counters["img9"] += 1
                Path(dest_path).write_bytes(b"PNG")
                return ImageRenderResult(status=STATUS_DONE, path=dest_path)
            counters["img16"] += 1
            if not quota["fired"]:
                quota["fired"] = True
                raise QuotaExhausted("chatgpt")   # 16:9 hits quota once
            Path(dest_path).write_bytes(b"PNG")
            return ImageRenderResult(status=STATUS_DONE, path=dest_path)

    w = _worker(tmp_path, mgr, writer_factory=lambda acc: W(), do_video=False)
    with qtbot.waitSignal(w.done, timeout=5000):
        w.start()
    assert counters["word"] == 1    # word NOT regenerated on the rotation retry
    assert counters["img9"] == 1    # already-done 9:16 image NOT redone
    assert counters["img16"] == 2   # only the quota'd 16:9 image retried
    assert (tmp_path / "out" / "1" / "1_16x9.png").exists()
    assert w.wait(2000)


def test_worker_emits_stats_signals(qtbot, tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "1.txt").write_text("k", encoding="utf-8")
    mgr = _mgr(tmp_path)
    totals, started, finished, accounts = [], [], [], []
    w = _worker(tmp_path, mgr)
    w.run_totals.connect(lambda t, s: totals.append((t, s)))
    w.script_started.connect(lambda o, f: started.append((o, f)))
    w.script_finished.connect(lambda o, st: finished.append((o, st)))
    w.account_in_use.connect(accounts.append)
    with qtbot.waitSignal(w.done, timeout=5000):
        w.start()
    assert totals == [(1, 0)]
    assert started == [(1, "1.txt")]
    assert finished == [(1, STATUS_DONE)]
    assert accounts and accounts[0] == "C1"
    assert w.wait(2000)


def test_do_script_false_skips_word_and_images(qtbot, tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "1.txt").write_text("k", encoding="utf-8")
    mgr = _mgr(tmp_path)
    calls = {"n": 0}
    class NoCallWriter(FakeWriter):
        def write_script(self, *a, **k):
            calls["n"] += 1
            return super().write_script(*a, **k)
    statuses = []
    w = _worker(tmp_path, mgr, writer_factory=lambda acc: NoCallWriter(),
                do_script=False, do_video=False)
    w.step_status.connect(lambda o, s, st: statuses.append((o, s, st)))
    with qtbot.waitSignal(w.done, timeout=5000):
        w.start()
    assert calls["n"] == 0                       # word never generated
    assert (1, "word", STATUS_SKIPPED) in statuses
    assert (1, "img_9x16", STATUS_SKIPPED) in statuses   # no prompt -> skipped
    assert w.wait(2000)


def test_video_only_failure_counts_script_as_failed(qtbot, tmp_path):
    # A contained video failure (non-quota) is swallowed to the video column,
    # but the script's overall outcome must still be "failed" (STATUS_FAILED),
    # so live stats increment Lỗi, not Xong.
    app = QCoreApplication.instance() or QCoreApplication([])
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "1.txt").write_text("k", encoding="utf-8")
    mgr = _mgr(tmp_path)

    class BoomVideo:
        def __init__(self): self.session = FakeSession()
        def make_video(self, *a, **k):
            raise RuntimeError("render lỗi")

    finished = []
    w = _worker(tmp_path, mgr, video_maker_factory=lambda acc: BoomVideo())
    w.script_finished.connect(lambda o, st: finished.append((o, st)))
    with qtbot.waitSignal(w.done, timeout=5000):
        w.start()
    assert finished == [(1, STATUS_FAILED)]      # video failure -> script failed
    assert w.wait(2000)


def test_conflict_skip_skips_existing_folder(qtbot, tmp_path):
    from horizon_tool.core.output_manager import SKIP
    app = QCoreApplication.instance() or QCoreApplication([])
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "1.txt").write_text("k", encoding="utf-8")
    (tmp_path / "out" / "1").mkdir(parents=True)   # pre-existing conflict
    mgr = _mgr(tmp_path)
    calls = {"n": 0}
    class CountWriter(FakeWriter):
        def write_script(self, *a, **k):
            calls["n"] += 1
            return super().write_script(*a, **k)
    finished = []
    w = _worker(tmp_path, mgr, writer_factory=lambda acc: CountWriter(),
                conflict_policy=SKIP)
    w.script_finished.connect(lambda o, st: finished.append((o, st)))
    with qtbot.waitSignal(w.done, timeout=5000):
        w.start()
    assert calls["n"] == 0                       # never processed
    assert finished == [(1, STATUS_SKIPPED)]
    assert w.wait(2000)


def test_conflict_timestamp_uses_suffixed_folder(qtbot, tmp_path):
    from horizon_tool.core.output_manager import TIMESTAMP
    app = QCoreApplication.instance() or QCoreApplication([])
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "1.txt").write_text("k", encoding="utf-8")
    (tmp_path / "out" / "1").mkdir(parents=True)   # conflict -> use 1_<ts>
    mgr = _mgr(tmp_path)
    w = _worker(tmp_path, mgr, do_video=False,
                conflict_policy=TIMESTAMP, run_timestamp="20260925_101500")
    with qtbot.waitSignal(w.done, timeout=5000):
        w.start()
    assert (tmp_path / "out" / "1_20260925_101500" / "1.docx").exists()
    assert w.wait(2000)


def test_exhaustion_does_not_emit_script_finished(qtbot, tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "1.txt").write_text("k", encoding="utf-8")
    mgr = AccountManager(tmp_path / "a.json", tmp_path / "profiles")
    mgr.add(SERVICE_CHATGPT, "C1")

    class AlwaysQuota:
        def __init__(self): self.session = FakeSession()
        def write_script(self, *a, **k): raise QuotaExhausted("chatgpt")
        def render_image(self, *a, **k): return ImageRenderResult(status=STATUS_DONE)

    finished, events = [], []
    w = _worker(tmp_path, mgr, writer_factory=lambda acc: AlwaysQuota(),
                video_maker_factory=None)
    w.script_finished.connect(lambda o, st: finished.append((o, st)))
    w.exhausted.connect(events.append)
    with qtbot.waitSignal(w.done, timeout=5000):
        w.start()
    assert events == ["chatgpt"]
    assert finished == []      # exhausted script is paused, not finished
    assert w.wait(2000)
