# horizon_tool/tests/test_pipeline.py
import docx

from horizon_tool.core.pipeline import process_script
from horizon_tool.core.section_parser import ParsedSections
from horizon_tool.automation.chatgpt import ScriptResult

FULL = """FULL STORY

CHAPTER ONE — The Door

He stood. **The truth was a lie.**

KEY SCENES + CONTINUITY NOTE

Scene 1.

IMAGE PROMPT — 9:16

Vertical.

THUMBNAIL PROMPT — 16:9

Horizontal.

VIDEO AI PROMPT

SHOT 1 — 3s

FACEBOOK TITLE

a title. another sentence.

FACEBOOK VIDEO DESCRIPTION

Desc.

STORY TEASER

Teaser.

HASHTAGS

#a #b #c #d #e
"""


class FakeWriter:
    def write_script(self, plugin_text, script_text, runtime_suffix=""):
        return ScriptResult(raw_text=FULL, conversation_url="https://chat/x")


def test_process_script_builds_word_and_raw(tmp_path):
    import yaml
    from pathlib import Path
    selectors = yaml.safe_load(
        (Path("horizon_tool/config/selectors.yaml")).read_text(encoding="utf-8"))
    out_dir = tmp_path / "output" / "3"
    out_dir.mkdir(parents=True)

    result = process_script(
        writer=FakeWriter(), ordinal=3, output_dir=out_dir,
        plugin_text="PLUGIN", script_text="SCRIPT",
        heading_regexes=selectors["section_headings"],
    )

    assert (out_dir / "raw_response.txt").exists()
    docx_path = out_dir / "3.docx"
    assert docx_path.exists()
    doc = docx.Document(str(docx_path))
    assert any(p.text == "FULL STORY" for p in doc.paragraphs)
    assert result.word_status == "Xong"
    assert result.missing_sections == []
    assert result.conversation_url == "https://chat/x"


def test_process_script_reports_missing_sections(tmp_path):
    class PartialWriter:
        def write_script(self, plugin_text, script_text, runtime_suffix=""):
            return ScriptResult(raw_text="FULL STORY\n\nOnly a story.\n\nHASHTAGS\n\n#a")
    import yaml
    from pathlib import Path
    selectors = yaml.safe_load(
        (Path("horizon_tool/config/selectors.yaml")).read_text(encoding="utf-8"))
    out_dir = tmp_path / "5"
    out_dir.mkdir(parents=True)
    result = process_script(
        writer=PartialWriter(), ordinal=5, output_dir=out_dir,
        plugin_text="P", script_text="S",
        heading_regexes=selectors["section_headings"])
    assert (out_dir / "5.docx").exists()
    assert "image_9x16" in result.missing_sections
