import pytest

from horizon_tool.core.account_manager import (
    AccountManager, SERVICE_CHATGPT, STATUS_READY, STATUS_QUOTA, STATUS_IN_USE,
)
from horizon_tool.core.exceptions import QuotaExhausted, AllAccountsExhausted
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
