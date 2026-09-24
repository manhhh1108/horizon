# horizon_tool/tests/test_make_video.py
from horizon_tool.core.pipeline import make_video
from horizon_tool.automation.grok import VideoResult
from horizon_tool.core.statuses import (
    STATUS_DONE, STATUS_REJECTED, STATUS_SKIPPED, STATUS_FAILED,
)

CONFIG = {"grok": {"motion_prompt_override": ""}}


class FakeMaker:
    def __init__(self, status=STATUS_DONE):
        self._status = status
        self.calls = []

    def make_video(self, image_path, motion_prompt, duration, quality, dest_path):
        self.calls.append(dict(image_path=image_path, motion_prompt=motion_prompt,
                               duration=duration, quality=quality, dest_path=dest_path))
        path = dest_path if self._status == STATUS_DONE else None
        return VideoResult(status=self._status, path=path)


def test_make_video_success(tmp_path):
    maker = FakeMaker(STATUS_DONE)
    status = make_video(
        maker=maker, output_dir=tmp_path, ordinal=1, config=CONFIG,
        motion_prompt="camera slowly pushes in", duration="15s", quality="1080p",
        image_path=str(tmp_path / "1_9x16.png"), do_video=True)
    assert status == STATUS_DONE
    assert maker.calls[0]["motion_prompt"] == "camera slowly pushes in"
    assert maker.calls[0]["duration"] == "15s"
    assert maker.calls[0]["dest_path"].endswith("1.mp4")


def test_make_video_none_prompt_no_override_becomes_empty(tmp_path):
    # Section 5 absent (motion_prompt=None) and no override -> passes "" (no crash).
    maker = FakeMaker(STATUS_DONE)
    status = make_video(
        maker=maker, output_dir=tmp_path, ordinal=6, config=CONFIG,
        motion_prompt=None, duration="10s", quality="720p",
        image_path=str(tmp_path / "6_9x16.png"), do_video=True)
    assert status == STATUS_DONE
    assert maker.calls[0]["motion_prompt"] == ""


def test_make_video_uses_config_override_prompt(tmp_path):
    cfg = {"grok": {"motion_prompt_override": "fixed motion"}}
    maker = FakeMaker(STATUS_DONE)
    make_video(maker=maker, output_dir=tmp_path, ordinal=1, config=cfg,
               motion_prompt="from section 5", duration="10s", quality="720p",
               image_path=str(tmp_path / "1_9x16.png"), do_video=True)
    assert maker.calls[0]["motion_prompt"] == "fixed motion"  # override wins


def test_make_video_skipped_when_disabled(tmp_path):
    maker = FakeMaker()
    status = make_video(maker=maker, output_dir=tmp_path, ordinal=2, config=CONFIG,
                        motion_prompt="p", duration="10s", quality="720p",
                        image_path=str(tmp_path / "2_9x16.png"), do_video=False)
    assert status == STATUS_SKIPPED
    assert maker.calls == []


def test_make_video_skipped_when_no_image(tmp_path):
    maker = FakeMaker()
    status = make_video(maker=maker, output_dir=tmp_path, ordinal=3, config=CONFIG,
                        motion_prompt="p", duration="10s", quality="720p",
                        image_path=None, do_video=True)   # 9:16 missing
    assert status == STATUS_SKIPPED
    assert maker.calls == []


def test_make_video_rejection(tmp_path):
    maker = FakeMaker(STATUS_REJECTED)
    status = make_video(maker=maker, output_dir=tmp_path, ordinal=4, config=CONFIG,
                        motion_prompt="p", duration="10s", quality="720p",
                        image_path=str(tmp_path / "4_9x16.png"), do_video=True)
    assert status == STATUS_REJECTED
    assert len(maker.calls) == 1  # no retry


def test_make_video_exception_is_failed(tmp_path):
    class Boom:
        def make_video(self, *a, **k):
            raise RuntimeError("mạng lỗi")
    status = make_video(maker=Boom(), output_dir=tmp_path, ordinal=5, config=CONFIG,
                        motion_prompt="p", duration="10s", quality="720p",
                        image_path=str(tmp_path / "5_9x16.png"), do_video=True)
    assert status == STATUS_FAILED
