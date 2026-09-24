# horizon_tool/tests/test_script_run_worker.py
import pytest
import yaml
from pathlib import Path

pytest.importorskip("PySide6")
from PySide6.QtCore import QCoreApplication  # noqa: E402
from horizon_tool.gui.worker import ScriptRunWorker  # noqa: E402
from horizon_tool.automation.chatgpt import ScriptResult  # noqa: E402

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


class FakeWriter:
    def write_script(self, plugin_text, script_text, runtime_suffix=""):
        return ScriptResult(raw_text=FULL)


def test_worker_processes_folder(qtbot, tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "1.txt").write_text("kịch bản 1", encoding="utf-8")
    (tmp_path / "in" / "2.txt").write_text("kịch bản 2", encoding="utf-8")
    out = tmp_path / "out"
    selectors = yaml.safe_load(
        Path("horizon_tool/config/selectors.yaml").read_text(encoding="utf-8"))

    worker = ScriptRunWorker(
        input_dir=str(tmp_path / "in"), output_dir=str(out), selection="",
        plugin_text="PLUGIN", heading_regexes=selectors["section_headings"],
        writer_factory=lambda: FakeWriter(),
    )
    with qtbot.waitSignal(worker.done, timeout=5000):
        worker.start()

    assert (out / "1" / "1.docx").exists()
    assert (out / "2" / "2.docx").exists()
    worker.wait(2000)
