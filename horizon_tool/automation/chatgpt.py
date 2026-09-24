"""ChatGPT automation for script writing.

The CONTINUE loop and response collection are pure functions (testable without
a browser). The DOM-touching methods on ChatGPTWriter use selectors from
selectors.yaml — those are placeholders to be tuned against the live site.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from horizon_tool.automation.browser import BrowserSession


def should_continue(response_text: str, continue_regex: str) -> bool:
    """True if a response ends with a [PART X COMPLETE …] marker."""
    return re.search(continue_regex, response_text, flags=re.IGNORECASE) is not None


def run_continue_loop(read_response: Callable[[], str],
                      send_message: Callable[[str], None],
                      continue_regex: str, max_parts: int = 20) -> list[str]:
    """Collect response parts, sending CONTINUE while the marker appears.

    read_response(): return the latest completed assistant message.
    send_message(text): send a user message (used to send 'CONTINUE').
    Stops when a part lacks the marker or max_parts is reached.
    """
    parts: list[str] = []
    for _ in range(max_parts):
        text = read_response()
        parts.append(text)
        if not should_continue(text, continue_regex):
            break
        send_message("CONTINUE")
    return parts


@dataclass
class ScriptResult:
    """Outcome of writing one script."""

    raw_text: str
    conversation_url: str | None = None
    docx_path: str | None = None


class ChatGPTWriter:
    """Drives ChatGPT to rewrite a story from a plugin + reference script.

    DOM methods use selectors from `selectors`; they are placeholders marked in
    selectors.yaml and must be verified against the live ChatGPT UI.
    """

    def __init__(self, session: BrowserSession, selectors: dict, config: dict) -> None:
        self.session = session
        self.selectors = selectors
        self.config = config
        self._continue_regex = selectors["patterns"]["continue_marker"]

    # ----- pure orchestration (testable via subclassing/fakes) ------------
    def write_script(self, plugin_text: str, script_text: str,
                     runtime_suffix: str = "") -> ScriptResult:
        """Open a chat, send plugin+script, run the CONTINUE loop, collect text."""
        self._open_new_chat()
        send_mode = self.config.get("chatgpt", {}).get("send_mode", "two_messages")
        if send_mode == "combined":
            first = plugin_text + "\n\n" + script_text
            if runtime_suffix:
                first += "\n\n" + runtime_suffix
            self._send(first)
        else:
            self._send(plugin_text)
            second = script_text + ("\n\n" + runtime_suffix if runtime_suffix else "")
            self._send(second)

        parts = run_continue_loop(
            self._read_last_response, self._send, self._continue_regex,
            max_parts=int(self.config.get("chatgpt", {}).get("max_parts", 20)),
        )
        from horizon_tool.core.section_parser import merge_continue_parts
        raw = merge_continue_parts(parts, self._continue_regex)
        return ScriptResult(
            raw_text=raw,
            conversation_url=self._current_url(),
            docx_path=self._try_download_docx(),
        )

    # ----- DOM methods (selectors are placeholders; tune on live site) ----
    def _open_new_chat(self) -> None:
        self.session.goto(self.selectors["chatgpt"]["url_new_chat"])

    def _send(self, text: str) -> None:
        sel = self.selectors["chatgpt"]
        self.session.paste_text(sel["input_box"], text)
        self.session.click_with_retry(sel["send_button"])

    def _read_last_response(self) -> str:
        # TODO: kiểm tra selector thực tế — wait for the Stop button to vanish
        # (response finished), then read the last assistant message text.
        sel = self.selectors["chatgpt"]
        self.session.wait_for(sel["assistant_message"])
        loc = self.session.page.locator(sel["assistant_message"]).last
        return loc.inner_text()

    def _current_url(self) -> str | None:
        try:
            return self.session.page.url
        except Exception:  # noqa: BLE001
            return None

    def _try_download_docx(self) -> str | None:
        # TODO: kiểm tra selector thực tế — detect a .docx download link and
        # save it. Returns None if ChatGPT returned text only.
        return None
