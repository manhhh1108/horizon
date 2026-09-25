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
