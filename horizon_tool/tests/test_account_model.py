from horizon_tool.core.account_manager import (
    Account, AccountStore, SERVICE_CHATGPT, STATUS_READY, STATUS_QUOTA,
)


def test_account_roundtrip_dict():
    acc = Account(
        id="chatgpt_1", service=SERVICE_CHATGPT, display_name="Tài khoản 1",
        profile_dir="profiles/chatgpt_1",
    )
    assert acc.status == STATUS_READY  # default
    assert acc.enabled is True         # default
    restored = Account.from_dict(acc.to_dict())
    assert restored == acc


def test_store_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "accounts.json"
    store = AccountStore(path)
    store.upsert(Account("chatgpt_1", SERVICE_CHATGPT, "A", "p/chatgpt_1"))
    store.upsert(Account("chatgpt_1", SERVICE_CHATGPT, "A", "p/chatgpt_1",
                         status=STATUS_QUOTA))  # same id overwrites
    store.save()

    reloaded = AccountStore(path)
    reloaded.load()
    accounts = reloaded.all()
    assert len(accounts) == 1
    assert accounts[0].status == STATUS_QUOTA


def test_store_load_missing_file_is_empty(tmp_path):
    store = AccountStore(tmp_path / "nope.json")
    store.load()
    assert store.all() == []


def test_store_save_is_atomic(tmp_path):
    path = tmp_path / "accounts.json"
    store = AccountStore(path)
    store.upsert(Account("grok_1", "grok", "G", "p/grok_1"))
    store.save()
    assert path.exists()
    assert not (tmp_path / "accounts.json.tmp").exists()
