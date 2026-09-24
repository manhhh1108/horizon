from horizon_tool.automation.chatgpt import (
    detect_refusal, resolve_image, ImageRenderResult,
)
from horizon_tool.core.statuses import STATUS_DONE, STATUS_REJECTED

REFUSALS = ["I can't help with that", "against.*content policy",
            "unable to generate this image"]


def test_detect_refusal_matches_patterns():
    assert detect_refusal("Sorry, I can't help with that.", REFUSALS)
    assert detect_refusal("This is against our content policy here", REFUSALS)
    assert not detect_refusal("Here is your image!", REFUSALS)


def test_resolve_image_rejects_without_downloading():
    calls = []
    def download():
        calls.append(True)
        return "should-not-be-called.png"
    result = resolve_image("Sorry, I can't help with that.", REFUSALS, download)
    assert result.status == STATUS_REJECTED
    assert result.path is None
    assert calls == []  # never downloaded on refusal (no retry, skip)


def test_resolve_image_downloads_when_ok():
    result = resolve_image("Here is your image!", REFUSALS, lambda: "out/1_9x16.png")
    assert result.status == STATUS_DONE
    assert result.path == "out/1_9x16.png"
