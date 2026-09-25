"""Grok automation: make a video from the 9:16 image.

The result decision (refusal → rejected, render-error → failed, else download)
is a pure function tested without a browser. The DOM steps on GrokVideoMaker
use selectors from selectors.yaml — placeholders tuned against the live site.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from horizon_tool.automation.browser import BrowserSession
from horizon_tool.automation.chatgpt import detect_refusal, detect_quota
from horizon_tool.core.exceptions import QuotaExhausted
from horizon_tool.core.statuses import STATUS_DONE, STATUS_FAILED, STATUS_REJECTED


@dataclass
class VideoResult:
    """Outcome of rendering one video."""

    status: str                 # STATUS_DONE / STATUS_REJECTED / STATUS_FAILED
    path: str | None = None
    reason: str = ""


def resolve_video(status_text: str, refusal_patterns: list[str],
                  error_patterns: list[str],
                  download: Callable[[], str]) -> VideoResult:
    """Decide the outcome of a Grok video attempt.

    Policy refusal → REJECTED; render error → FAILED. In both cases the video is
    skipped with NO retry and download() is not called. Otherwise download() saves
    the mp4 and returns its path → DONE.
    """
    if detect_refusal(status_text, refusal_patterns):
        return VideoResult(status=STATUS_REJECTED, reason="Vi phạm chính sách")
    if detect_refusal(status_text, error_patterns):
        return VideoResult(status=STATUS_FAILED, reason="Render lỗi")
    path = download()
    return VideoResult(status=STATUS_DONE, path=path)


class GrokVideoMaker:
    """Drives Grok to turn a 9:16 image into a video.

    DOM methods use selectors from `selectors`; they are placeholders marked in
    selectors.yaml and must be verified against the live Grok UI.
    """

    def __init__(self, session: BrowserSession, selectors: dict, config: dict) -> None:
        self.session = session
        self.selectors = selectors
        self.config = config

    def make_video(self, image_path: str, motion_prompt: str, duration: str,
                   quality: str, dest_path: str) -> VideoResult:
        """Upload the image, set options, generate, and download the video."""
        self._open_image_to_video()
        self._upload_image(image_path)
        self._enter_motion_prompt(motion_prompt)
        self._select_duration(duration)
        self._select_quality(quality)
        self._click_generate()
        status_text = self._wait_and_read_status()
        patterns = self.selectors["patterns"]
        return resolve_video(
            status_text, patterns["policy_refusal"], patterns["video_error"],
            download=lambda: self._download_video(dest_path),
        )

    # ----- DOM methods (selectors are placeholders; tune on live site) ----
    def _open_image_to_video(self) -> None:
        self.session.goto(self.selectors["grok"]["url_image_to_video"])

    def _upload_image(self, image_path: str) -> None:
        # TODO: kiểm tra selector thực tế — set the file input to image_path.
        sel = self.selectors["grok"]["image_upload_input"]
        self.session.page.set_input_files(sel, image_path)

    def _enter_motion_prompt(self, motion_prompt: str) -> None:
        self.session.paste_text(self.selectors["grok"]["motion_prompt_box"], motion_prompt)

    def _select_duration(self, duration: str) -> None:
        # TODO: kiểm tra selector thực tế — choose the duration control matching `duration`.
        pass

    def _select_quality(self, quality: str) -> None:
        # TODO: kiểm tra selector thực tế — choose the quality control matching `quality`.
        pass

    def _click_generate(self) -> None:
        self.session.click_with_retry(self.selectors["grok"]["generate_button"])

    def _wait_and_read_status(self) -> str:
        # TODO: kiểm tra selector thực tế — wait until render finishes (up to
        # grok.render_timeout_seconds), then read any status/result text so a
        # refusal or render error can be detected. Returns that text.
        timeout_ms = int(self.config.get("grok", {}).get("render_timeout_seconds", 600)) * 1000
        self.session.wait_for(self.selectors["grok"]["video_result"], timeout_ms=timeout_ms)
        status_text = ""  # placeholder — the real status read lands with live tuning
        # NOTE: with status_text == "" this quota check is inert; it becomes live
        # once _wait_and_read_status returns the real Grok status text.
        if detect_quota(status_text, self.selectors["patterns"]["quota_exhausted"]):
            raise QuotaExhausted("grok", status_text)
        return status_text

    def _download_video(self, dest_path: str) -> str:
        # TODO: kiểm tra selector thực tế — locate the rendered video and save it
        # to dest_path. Returns dest_path.
        raise NotImplementedError("Video download must be tuned on the live site")
