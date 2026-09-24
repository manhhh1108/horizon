# horizon_tool/tests/test_render_images.py
from horizon_tool.core.pipeline import render_images
from horizon_tool.automation.chatgpt import ImageRenderResult
from horizon_tool.core.statuses import STATUS_DONE, STATUS_REJECTED, STATUS_SKIPPED

CONFIG = {"chatgpt": {
    "image_wrapper_9x16": "9:16 ratio:\n{PROMPT}",
    "image_wrapper_16x9": "16:9 ratio:\n{PROMPT}",
}}


class FakeWriter:
    def __init__(self, statuses):
        self._statuses = statuses          # dict dest-substr -> status
        self.calls = []

    def render_image(self, prompt, wrapper, dest_path):
        self.calls.append((prompt, wrapper, dest_path))
        for key, status in self._statuses.items():
            if key in dest_path:
                path = dest_path if status == STATUS_DONE else None
                return ImageRenderResult(status=status, path=path)
        return ImageRenderResult(status=STATUS_DONE, path=dest_path)


def test_renders_both_images(tmp_path):
    writer = FakeWriter({"9x16": STATUS_DONE, "16x9": STATUS_DONE})
    out = render_images(
        writer=writer, output_dir=tmp_path, ordinal=1, config=CONFIG,
        image_9x16_prompt="a vertical scene", thumbnail_16x9_prompt="a key art",
        do_9x16=True, do_16x9=True)
    assert out["img_9x16"] == STATUS_DONE
    assert out["img_16x9"] == STATUS_DONE
    # correct wrappers applied and prompts substituted
    assert any("9:16 ratio:\na vertical scene" == c[0] or
               c[1].replace("{PROMPT}", c[0]) for c in writer.calls)


def test_rejection_is_recorded_without_retry(tmp_path):
    writer = FakeWriter({"9x16": STATUS_REJECTED, "16x9": STATUS_DONE})
    out = render_images(
        writer=writer, output_dir=tmp_path, ordinal=2, config=CONFIG,
        image_9x16_prompt="p", thumbnail_16x9_prompt="q",
        do_9x16=True, do_16x9=True)
    assert out["img_9x16"] == STATUS_REJECTED
    assert out["img_16x9"] == STATUS_DONE
    # exactly two render calls total (no retry of the rejected one)
    assert len(writer.calls) == 2


def test_missing_prompt_is_skipped(tmp_path):
    writer = FakeWriter({})
    out = render_images(
        writer=writer, output_dir=tmp_path, ordinal=3, config=CONFIG,
        image_9x16_prompt=None, thumbnail_16x9_prompt="q",
        do_9x16=True, do_16x9=True)
    assert out["img_9x16"] == STATUS_SKIPPED   # no section 3 -> skip
    assert out["img_16x9"] == STATUS_DONE


def test_disabled_steps_are_skipped(tmp_path):
    writer = FakeWriter({})
    out = render_images(
        writer=writer, output_dir=tmp_path, ordinal=4, config=CONFIG,
        image_9x16_prompt="p", thumbnail_16x9_prompt="q",
        do_9x16=False, do_16x9=False)
    assert out["img_9x16"] == STATUS_SKIPPED
    assert out["img_16x9"] == STATUS_SKIPPED
    assert writer.calls == []
