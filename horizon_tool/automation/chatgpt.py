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
from horizon_tool.core.section_parser import merge_continue_parts


def should_continue(response_text: str, continue_regex: str) -> bool:
    """True if a response contains a [PART X COMPLETE …] marker."""
    return re.search(continue_regex, response_text, flags=re.IGNORECASE) is not None


def run_continue_loop(read_response: Callable[[], str],
                      send_message: Callable[[str], None],
                      continue_regex: str, max_parts: int = 20) -> list[str]:
    """Collect response parts, sending CONTINUE while the marker appears.

    read_response(): return the latest completed assistant message.
    send_message(text): send a user message (used to send 'CONTINUE').
    Stops when a part lacks the marker or max_parts is reached. CONTINUE is
    never sent after the final collected part (including when the cap is hit).
    """
    parts: list[str] = []
    for i in range(max_parts):
        text = read_response()
        parts.append(text)
        if not should_continue(text, continue_regex):
            break
        if i < max_parts - 1:  # don't CONTINUE past the last part we can collect
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
        self._wait_response_complete()
        sel = self.selectors["chatgpt"]
        self.session.wait_for(sel["assistant_message"])
        loc = self.session.page.locator(sel["assistant_message"]).last
        return loc.inner_text()

    def _wait_response_complete(self) -> None:
        # A reply is still streaming while the Stop button is shown; wait for it
        # to appear then vanish so we read a COMPLETED (not stale/streaming)
        # message rather than the previous turn's text.
        # TODO: kiểm tra selector thực tế — verify the stop_button selector; if
        # appear→disappear proves unreliable, track the assistant-message count
        # and wait for a brand-new message instead of the previous one.
        sel = self.selectors["chatgpt"]
        stop = sel.get("stop_button")
        if not stop:
            return
        resp_ms = int(self.config.get("timeouts", {}).get("response_wait_seconds", 600)) * 1000
        try:
            self.session.page.wait_for_selector(stop, timeout=5000)  # streaming began
        except Exception:  # noqa: BLE001 - may have already started/finished
            pass
        try:
            self.session.page.wait_for_selector(stop, state="hidden", timeout=resp_ms)
        except Exception:  # noqa: BLE001 - best effort until selectors are tuned
            pass

    def _current_url(self) -> str | None:
        try:
            return self.session.page.url
        except Exception:  # noqa: BLE001
            return None

    def _try_download_docx(self) -> str | None:
        # TODO: kiểm tra selector thực tế — detect a .docx download link and
        # save it. Returns None if ChatGPT returned text only.
        return None
