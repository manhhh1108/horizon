# horizon_tool/tests/test_script_run_worker.py
import pytest
import yaml
from pathlib import Path

pytest.importorskip("PySide6")
from PySide6.QtCore import QCoreApplication  # noqa: E402
from horizon_tool.gui.worker import ScriptRunWorker  # noqa: E402
from horizon_tool.automation.chatgpt import ScriptResult, ImageRenderResult  # noqa: E402
from horizon_tool.core.statuses import STATUS_DONE, STATUS_FAILED  # noqa: E402

FULL = """FULL STORY

CHAPTER ONE — X

Body. **twist.**

KEY SCENES + CONTINUITY NOTE

s

IMAGE PROMPT — 9:16

i

THUMBNAIL PROMPT — 16:9

t

VIDEO AI PROMPT

SHOT 1 — 3s

FACEBOOK TITLE

a. b.

FACEBOOK VIDEO DESCRIPTION

d

STORY TEASER

te

HASHTAGS

#a #b
"""


# Resolve selectors relative to the package, not the pytest CWD.
SELECTORS_PATH = Path(__file__).resolve().parents[1] / "config" / "selectors.yaml"


class FakeSession:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class FakeWriter:
    def __init__(self):
        self.session = FakeSession()

    def write_script(self, plugin_text, script_text, runtime_suffix=""):
        return ScriptResult(raw_text=FULL)

    def render_image(self, prompt, wrapper, dest_path):
        # simulate a saved file
        Path(dest_path).write_bytes(b"PNG")
        return ImageRenderResult(status=STATUS_DONE, path=dest_path)


def test_worker_processes_folder(qtbot, tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "1.txt").write_text("kịch bản 1", encoding="utf-8")
    (tmp_path / "in" / "2.txt").write_text("kịch bản 2", encoding="utf-8")
    out = tmp_path / "out"
    selectors = yaml.safe_load(SELECTORS_PATH.read_text(encoding="utf-8"))
    created: list[FakeWriter] = []

    def factory():
        w = FakeWriter()
        created.append(w)
        return w

    statuses = []
    worker = ScriptRunWorker(
        input_dir=str(tmp_path / "in"), output_dir=str(out), selection="",
        plugin_text="PLUGIN", heading_regexes=selectors["section_headings"],
        writer_factory=factory, do_9x16=True, do_16x9=True,
        config={"chatgpt": {"image_wrapper_9x16": "{PROMPT}",
                            "image_wrapper_16x9": "{PROMPT}"}},
    )
    worker.step_status.connect(lambda o, s, st: statuses.append((o, s, st)))
    with qtbot.waitSignal(worker.done, timeout=5000):
        worker.start()

    assert (out / "1" / "1.docx").exists()
    assert (out / "2" / "2.docx").exists()
    assert (out / "1" / "1_9x16.png").exists()
    assert (out / "1" / "1_16x9.png").exists()
    assert any(s == "img_9x16" for _, s, _ in statuses)
    assert any(s == "img_16x9" for _, s, _ in statuses)
    # Each script's browser session is closed after use (no Chromium leak).
    assert len(created) == 2
    assert all(w.session.closed for w in created)
    assert worker.wait(2000)


def test_worker_continues_after_one_script_fails(qtbot, tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "1.txt").write_text("k1", encoding="utf-8")
    (tmp_path / "in" / "2.txt").write_text("k2", encoding="utf-8")
    out = tmp_path / "out"
    selectors = yaml.safe_load(SELECTORS_PATH.read_text(encoding="utf-8"))

    class FlakyWriter:
        def __init__(self, ordinal_holder):
            self.session = FakeSession()
            self._holder = ordinal_holder

        def write_script(self, plugin_text, script_text, runtime_suffix=""):
            self._holder[0] += 1
            if self._holder[0] == 1:
                raise RuntimeError("giả lập lỗi ChatGPT")
            return ScriptResult(raw_text=FULL)

        def render_image(self, prompt, wrapper, dest_path):
            Path(dest_path).write_bytes(b"PNG")
            return ImageRenderResult(status=STATUS_DONE, path=dest_path)

    holder = [0]
    statuses: list[tuple[int, str, str]] = []

    worker = ScriptRunWorker(
        input_dir=str(tmp_path / "in"), output_dir=str(out), selection="",
        plugin_text="P", heading_regexes=selectors["section_headings"],
        writer_factory=lambda: FlakyWriter(holder),
        do_9x16=True, do_16x9=True,
        config={"chatgpt": {"image_wrapper_9x16": "{PROMPT}",
                            "image_wrapper_16x9": "{PROMPT}"}},
    )
    worker.step_status.connect(lambda o, s, st: statuses.append((o, s, st)))
    with qtbot.waitSignal(worker.done, timeout=5000):
        worker.start()

    # First script failed but the second still produced its Word file.
    assert (out / "2" / "2.docx").exists()
    assert (1, "word", STATUS_FAILED) in statuses
    # A failed script resolves ALL its columns (no blank image cells).
    assert (1, "img_9x16", STATUS_FAILED) in statuses
    assert (1, "img_16x9", STATUS_FAILED) in statuses
    assert worker.wait(2000)
