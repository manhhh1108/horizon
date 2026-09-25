from horizon_tool.automation.chatgpt import detect_quota

QUOTA = ["you've reached your.*limit", "quota", "try again later"]


def test_detect_quota_true():
    assert detect_quota("You've reached your usage limit for GPT-4.", QUOTA)
    assert detect_quota("Please try again later.", QUOTA)


def test_detect_quota_false():
    assert not detect_quota("Here is your story.", QUOTA)
