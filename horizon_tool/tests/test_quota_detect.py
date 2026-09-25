from horizon_tool.automation.chatgpt import detect_quota, detect_session_expired

QUOTA = ["you've reached your.*limit", "quota", "try again later"]


def test_detect_quota_true():
    assert detect_quota("You've reached your usage limit for GPT-4.", QUOTA)
    assert detect_quota("Please try again later.", QUOTA)


def test_detect_quota_false():
    assert not detect_quota("Here is your story.", QUOTA)


def test_detect_session_expired():
    pats = ["log in", "session expired"]
    assert detect_session_expired("Please log in to continue", pats)
    assert not detect_session_expired("Here is your story.", pats)
