import pytest

from horizon_tool.core.account_manager import (
    AccountManager, SERVICE_CHATGPT, STATUS_READY, STATUS_QUOTA, STATUS_IN_USE,
)
from horizon_tool.core.exceptions import QuotaExhausted, AllAccountsExhausted, SessionExpired
from horizon_tool.core.rotation import run_step_with_rotation


def make_mgr(tmp_path, n):
    mgr = AccountManager(tmp_path / "a.json", tmp_path / "profiles")
    for i in range(n):
        mgr.add(SERVICE_CHATGPT, f"TK{i+1}")
    return mgr


class FakeWorker:
    def __init__(self, account):
        self.account = account
        self.closed = False
        self.session = self  # so _close finds .session.close

    def close(self):
        self.closed = True


def test_first_account_succeeds(tmp_path):
    mgr = make_mgr(tmp_path, 2)
    built = []
    result, account = run_step_with_rotation(
        service=SERVICE_CHATGPT, account_manager=mgr,
        make_worker=lambda acc: built.append(FakeWorker(acc)) or built[-1],
        do_step=lambda w: "OK")
    assert result == "OK"
    assert mgr.get(account.id).status == STATUS_READY   # freed after success
    assert built[-1].closed is True                     # session closed


def test_switches_on_quota(tmp_path):
    mgr = make_mgr(tmp_path, 2)
    a1, a2 = mgr.list(SERVICE_CHATGPT)
    calls = {"n": 0}
    def do_step(w):
        calls["n"] += 1
        if calls["n"] == 1:
            raise QuotaExhausted("chatgpt")
        return "OK"
    result, account = run_step_with_rotation(
        service=SERVICE_CHATGPT, account_manager=mgr,
        make_worker=lambda acc: FakeWorker(acc), do_step=do_step)
    assert result == "OK"
    assert mgr.get(a1.id).status == STATUS_QUOTA   # first marked exhausted
    assert account.id == a2.id                     # second used


def test_all_exhausted_raises(tmp_path):
    mgr = make_mgr(tmp_path, 2)
    with pytest.raises(AllAccountsExhausted):
        run_step_with_rotation(
            service=SERVICE_CHATGPT, account_manager=mgr,
            make_worker=lambda acc: FakeWorker(acc),
            do_step=lambda w: (_ for _ in ()).throw(QuotaExhausted("chatgpt")))
    for acc in mgr.list(SERVICE_CHATGPT):
        assert mgr.get(acc.id).status == STATUS_QUOTA


def test_non_quota_error_frees_account_and_propagates(tmp_path):
    mgr = make_mgr(tmp_path, 2)
    a1 = mgr.list(SERVICE_CHATGPT)[0]
    with pytest.raises(RuntimeError):
        run_step_with_rotation(
            service=SERVICE_CHATGPT, account_manager=mgr,
            make_worker=lambda acc: FakeWorker(acc),
            do_step=lambda w: (_ for _ in ()).throw(RuntimeError("boom")))
    assert mgr.get(a1.id).status == STATUS_READY   # not a quota problem


def test_make_worker_failure_frees_account_not_stuck_in_use(tmp_path):
    # Building the worker (e.g. launching a browser) fails: the account must be
    # freed back to ready, never stranded in `in_use`, and the error propagates.
    mgr = make_mgr(tmp_path, 1)
    a1 = mgr.list(SERVICE_CHATGPT)[0]

    def boom_factory(acc):
        raise RuntimeError("không mở được trình duyệt")

    with pytest.raises(RuntimeError):
        run_step_with_rotation(
            service=SERVICE_CHATGPT, account_manager=mgr,
            make_worker=boom_factory, do_step=lambda w: "unreached")
    assert mgr.get(a1.id).status == STATUS_READY
    assert mgr.get(a1.id).status != STATUS_IN_USE


def test_session_expired_marks_and_switches(tmp_path):
    from horizon_tool.core.account_manager import STATUS_SESSION_EXPIRED
    mgr = make_mgr(tmp_path, 2)
    a1, a2 = mgr.list(SERVICE_CHATGPT)
    calls = {"n": 0}
    def do_step(w):
        calls["n"] += 1
        if calls["n"] == 1:
            raise SessionExpired("chatgpt")
        return "OK"
    result, account = run_step_with_rotation(
        service=SERVICE_CHATGPT, account_manager=mgr,
        make_worker=lambda acc: FakeWorker(acc), do_step=do_step)
    assert result == "OK"
    assert mgr.get(a1.id).status == STATUS_SESSION_EXPIRED
    assert account.id == a2.id


def test_log_callback_invoked_on_quota_switch(tmp_path):
    mgr = make_mgr(tmp_path, 2)
    logs: list[str] = []
    calls = {"n": 0}

    def do_step(w):
        calls["n"] += 1
        if calls["n"] == 1:
            raise QuotaExhausted("chatgpt")
        return "OK"

    result, _ = run_step_with_rotation(
        service=SERVICE_CHATGPT, account_manager=mgr,
        make_worker=lambda acc: FakeWorker(acc), do_step=do_step, log=logs.append)
    assert result == "OK"
    assert any("hết quota" in m for m in logs)   # switch was logged
