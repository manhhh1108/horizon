import pytest
from horizon_tool.core.retry import retry_with_backoff


def test_returns_first_success_no_sleep():
    slept = []
    out = retry_with_backoff(lambda: 42, attempts=3, base_seconds=5,
                             sleep=slept.append)
    assert out == 42
    assert slept == []


def test_retries_then_succeeds_with_backoff():
    slept = []
    calls = {"n": 0}
    def fn():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("mạng lỗi")
        return "ok"
    out = retry_with_backoff(fn, attempts=5, base_seconds=2, sleep=slept.append)
    assert out == "ok"
    assert calls["n"] == 3
    assert slept == [2, 4]           # base*2**0, base*2**1 (no sleep after success)


def test_exhausts_and_raises_last():
    slept = []
    def fn():
        raise RuntimeError("down")
    with pytest.raises(RuntimeError):
        retry_with_backoff(fn, attempts=3, base_seconds=1, sleep=slept.append)
    assert slept == [1, 2]           # slept before attempts 2 and 3, not after the last


def test_excluded_exceptions_propagate_immediately():
    slept = []
    class Fatal(Exception):
        pass
    def fn():
        raise Fatal()
    with pytest.raises(Fatal):
        retry_with_backoff(fn, attempts=5, base_seconds=1, sleep=slept.append,
                           exclude=(Fatal,))
    assert slept == []               # no retry for excluded types
