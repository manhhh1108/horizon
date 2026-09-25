import pytest

pytest.importorskip("playwright")
from horizon_tool.automation.browser import BrowserSession  # noqa: E402


@pytest.fixture
def session(tmp_path):
    """A started headless BrowserSession, or skip if Chromium can't launch."""
    s = BrowserSession(tmp_path / "profile", headless=True,
                       element_timeout_ms=5000, retry_attempts=2)
    try:
        s.start()
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"Chromium unavailable: {exc}")
    yield s
    s.close()


def test_wait_for_and_visible(session):
    session.page.set_content("<textarea id='box'></textarea>")
    loc = session.wait_for("#box")
    assert loc is not None
    assert session.is_visible("#box")
    assert not session.is_visible("#missing")


def test_paste_text_into_textarea(session):
    session.page.set_content("<textarea id='box'></textarea>")
    session.paste_text("#box", "Đây là một kịch bản dài\nnhiều dòng.")
    value = session.page.eval_on_selector("#box", "e => e.value")
    assert value == "Đây là một kịch bản dài\nnhiều dòng."


def test_paste_text_replaces_existing(session):
    session.page.set_content("<textarea id='box'>cũ</textarea>")
    session.paste_text("#box", "mới")
    value = session.page.eval_on_selector("#box", "e => e.value")
    assert value == "mới"


def test_paste_text_into_contenteditable(session):
    # ChatGPT/Grok use contenteditable, not <textarea>; verify clear + insert.
    session.page.set_content(
        "<div id='ed' contenteditable='true'>nội dung cũ</div>"
    )
    session.paste_text("#ed", "văn bản mới\ndòng hai")
    text = session.page.eval_on_selector("#ed", "e => e.innerText")
    assert "văn bản mới" in text
    assert "nội dung cũ" not in text  # old content cleared


def test_click_with_retry_success(session):
    session.page.set_content(
        "<button id='go' onclick=\"this.textContent='clicked'\">go</button>"
    )
    session.click_with_retry("#go")
    assert session.page.eval_on_selector("#go", "e => e.textContent") == "clicked"


def test_click_with_retry_raises_when_absent(session):
    session.page.set_content("<div>nothing</div>")
    with pytest.raises(Exception):
        session.click_with_retry("#missing")


def test_page_property_raises_before_start(tmp_path):
    # No browser launched — pure guard, no Chromium needed.
    s = BrowserSession(tmp_path / "profile", headless=True)
    with pytest.raises(RuntimeError):
        _ = s.page


def test_close_without_start_is_safe(tmp_path):
    s = BrowserSession(tmp_path / "profile", headless=True)
    s.close()  # must not raise even though start() was never called


def test_goto_retries_through_session(tmp_path):
    # goto threads retry_attempts/backoff through retry_with_backoff. Inject a
    # fake page + base=0 so there's no real browser and no real sleep.
    s = BrowserSession(tmp_path / "profile", headless=True,
                       retry_attempts=3, retry_backoff_base_seconds=0)
    calls = {"n": 0}

    class FakePage:
        def goto(self, url, timeout=None):
            calls["n"] += 1
            if calls["n"] < 2:
                raise RuntimeError("mạng lỗi")
            return None

    s._page = FakePage()   # bypass start(); goto() uses self.page
    s.goto("https://example/")
    assert calls["n"] == 2   # failed once, retried, succeeded


def test_screenshot_writes_file(session, tmp_path):
    session.page.set_content("<h1>error state</h1>")
    dest = tmp_path / "error.png"
    session.screenshot(str(dest))
    assert dest.exists() and dest.stat().st_size > 0


def test_goto_exhausts_and_raises(tmp_path):
    s = BrowserSession(tmp_path / "profile", headless=True,
                       retry_attempts=2, retry_backoff_base_seconds=0)

    class FakePage:
        def goto(self, url, timeout=None):
            raise RuntimeError("down")

    s._page = FakePage()
    with pytest.raises(RuntimeError):
        s.goto("https://example/")
