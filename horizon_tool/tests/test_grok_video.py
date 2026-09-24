# horizon_tool/tests/test_grok_video.py
from horizon_tool.automation.grok import resolve_video, VideoResult
from horizon_tool.core.statuses import STATUS_DONE, STATUS_REJECTED, STATUS_FAILED

REFUSALS = ["against.*content policy", "can't create this video"]
ERRORS = ["something went wrong", "failed to generate"]


def test_resolve_video_rejects_without_downloading():
    calls = []
    result = resolve_video("This is against our content policy.", REFUSALS, ERRORS,
                           download=lambda: calls.append(1))
    assert result.status == STATUS_REJECTED
    assert result.path is None
    assert calls == []  # refusal -> no download, no retry


def test_resolve_video_render_error_is_failed_without_downloading():
    calls = []
    result = resolve_video("Something went wrong, please retry.", REFUSALS, ERRORS,
                           download=lambda: calls.append(1))
    assert result.status == STATUS_FAILED
    assert result.path is None
    assert calls == []  # render error -> no download, no retry


def test_resolve_video_downloads_when_ok():
    result = resolve_video("Your video is ready!", REFUSALS, ERRORS,
                           download=lambda: "out/1.mp4")
    assert result.status == STATUS_DONE
    assert result.path == "out/1.mp4"
