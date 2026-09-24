import pytest

from horizon_tool.core.account_manager import (
    AccountManager, SERVICE_CHATGPT, SERVICE_GROK,
    STATUS_READY, STATUS_QUOTA, STATUS_SESSION_EXPIRED,
)


def make_manager(tmp_path):
    return AccountManager(
        store_path=tmp_path / "accounts.json",
        profiles_root=tmp_path / "profiles",
    )


def test_add_creates_unique_id_and_profile_dir(tmp_path):
    mgr = make_manager(tmp_path)
    a = mgr.add(SERVICE_CHATGPT, "Tài khoản 1")
    b = mgr.add(SERVICE_CHATGPT, "Tài khoản 2")
    assert a.id != b.id
    assert a.service == SERVICE_CHATGPT
    assert (tmp_path / "profiles" / a.id).is_dir()
    reloaded = make_manager(tmp_path)
    assert {x.id for x in reloaded.list(SERVICE_CHATGPT)} == {a.id, b.id}


def test_list_filters_by_service(tmp_path):
    mgr = make_manager(tmp_path)
    mgr.add(SERVICE_CHATGPT, "C1")
    mgr.add(SERVICE_GROK, "G1")
    assert len(mgr.list(SERVICE_CHATGPT)) == 1
    assert len(mgr.list(SERVICE_GROK)) == 1
    assert len(mgr.list()) == 2


def test_rename_enable_status(tmp_path):
    mgr = make_manager(tmp_path)
    a = mgr.add(SERVICE_CHATGPT, "Old")
    mgr.rename(a.id, "New")
    mgr.set_enabled(a.id, False)
    mgr.set_status(a.id, STATUS_QUOTA, quota_reset_at="2026-09-24T10:00:00")
    got = mgr.get(a.id)
    assert got.display_name == "New"
    assert got.enabled is False
    assert got.status == STATUS_QUOTA
    assert got.quota_reset_at == "2026-09-24T10:00:00"


def test_remove_deletes_account(tmp_path):
    mgr = make_manager(tmp_path)
    a = mgr.add(SERVICE_CHATGPT, "X")
    mgr.remove(a.id)
    assert mgr.list(SERVICE_CHATGPT) == []
    with pytest.raises(KeyError):
        mgr.get(a.id)


def test_next_available_skips_disabled_and_unavailable(tmp_path):
    mgr = make_manager(tmp_path)
    a = mgr.add(SERVICE_CHATGPT, "A")
    b = mgr.add(SERVICE_CHATGPT, "B")
    c = mgr.add(SERVICE_CHATGPT, "C")
    mgr.set_enabled(a.id, False)
    mgr.set_status(b.id, STATUS_QUOTA)
    nxt = mgr.next_available(SERVICE_CHATGPT)
    assert nxt.id == c.id


def test_next_available_none_when_all_unavailable(tmp_path):
    mgr = make_manager(tmp_path)
    a = mgr.add(SERVICE_GROK, "A")
    mgr.set_status(a.id, STATUS_SESSION_EXPIRED)
    assert mgr.next_available(SERVICE_GROK) is None


def test_remove_deletes_profile_directory(tmp_path):
    mgr = make_manager(tmp_path)
    a = mgr.add(SERVICE_CHATGPT, "A")
    profile = tmp_path / "profiles" / a.id
    (profile / "cookies").write_text("secret-session", encoding="utf-8")
    assert profile.is_dir()
    mgr.remove(a.id)
    assert not profile.exists()  # session cookies gone, no stale reuse


def test_set_status_rejects_unknown_value(tmp_path):
    mgr = make_manager(tmp_path)
    a = mgr.add(SERVICE_CHATGPT, "A")
    with pytest.raises(ValueError):
        mgr.set_status(a.id, "STATUS_QOUTA")  # typo -> rejected


def test_corrupt_store_file_starts_empty(tmp_path):
    path = tmp_path / "accounts.json"
    path.write_text("{ this is not valid json", encoding="utf-8")
    mgr = AccountManager(store_path=path, profiles_root=tmp_path / "profiles")
    assert mgr.list() == []                       # started empty, no crash
    assert (tmp_path / "accounts.json.corrupt").exists()  # bad file quarantined


def test_from_dict_tolerates_unknown_keys(tmp_path):
    from horizon_tool.core.account_manager import Account
    acc = Account.from_dict({
        "id": "chatgpt_1", "service": SERVICE_CHATGPT, "display_name": "A",
        "profile_dir": "p", "future_field": "ignored",
    })
    assert acc.id == "chatgpt_1"
