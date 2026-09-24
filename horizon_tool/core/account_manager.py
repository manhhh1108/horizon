"""Multi-account model, JSON persistence, and rotation logic.

Passwords are never stored here; only non-secret account metadata. Browser
session cookies live inside each account's own browser profile directory.
"""
from __future__ import annotations

import json
import logging
import shutil
from dataclasses import asdict, dataclass, fields
import os
from pathlib import Path

logger = logging.getLogger(__name__)

SERVICE_CHATGPT = "chatgpt"
SERVICE_GROK = "grok"
SERVICES = (SERVICE_CHATGPT, SERVICE_GROK)

STATUS_READY = "ready"
STATUS_IN_USE = "in_use"
STATUS_QUOTA = "quota_exhausted"
STATUS_SESSION_EXPIRED = "session_expired"
STATUSES = (STATUS_READY, STATUS_IN_USE, STATUS_QUOTA, STATUS_SESSION_EXPIRED)


@dataclass
class Account:
    """Non-secret metadata for one logged-in browser profile."""

    id: str
    service: str
    display_name: str
    profile_dir: str
    enabled: bool = True
    status: str = STATUS_READY
    quota_reset_at: str | None = None
    last_used: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Account":
        # Tolerate unknown keys from a newer/older on-disk format.
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})


class AccountStore:
    """Loads/saves a list of Accounts to a JSON file (atomic writes)."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._accounts: dict[str, Account] = {}

    def load(self) -> None:
        self._accounts = {}
        if not self.path.exists():
            return
        try:
            with self.path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            items = data.get("accounts", [])
        except (json.JSONDecodeError, OSError, AttributeError) as exc:
            # A corrupt state file must never crash startup; start empty and
            # keep the bad file aside for inspection.
            logger.warning("Không đọc được file tài khoản (%s); bắt đầu rỗng.", exc)
            self._quarantine_corrupt_file()
            return
        for item in items:
            acc = Account.from_dict(item)
            self._accounts[acc.id] = acc

    def _quarantine_corrupt_file(self) -> None:
        try:
            os.replace(self.path, self.path.with_suffix(self.path.suffix + ".corrupt"))
        except OSError:
            pass

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"accounts": [a.to_dict() for a in self._accounts.values()]}
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)  # atomic on Windows and POSIX

    def upsert(self, account: Account) -> None:
        self._accounts[account.id] = account

    def remove(self, account_id: str) -> None:
        self._accounts.pop(account_id, None)

    def get(self, account_id: str) -> Account:
        try:
            return self._accounts[account_id]
        except KeyError:
            raise KeyError(f"Account not found: {account_id!r}") from None

    def all(self) -> list[Account]:
        return list(self._accounts.values())


class AccountManager:
    """High-level account operations backed by an AccountStore.

    Every mutating call persists immediately so state survives a crash.
    """

    def __init__(self, store_path: Path, profiles_root: Path) -> None:
        self.profiles_root = Path(profiles_root)
        self._store = AccountStore(Path(store_path))
        self._store.load()

    def _next_id(self, service: str) -> str:
        used = [
            int(a.id.rsplit("_", 1)[1])
            for a in self._store.all()
            if a.service == service and a.id.rsplit("_", 1)[1].isdigit()
        ]
        return f"{service}_{(max(used) + 1) if used else 1}"

    def add(self, service: str, display_name: str) -> Account:
        if service not in SERVICES:
            raise ValueError(f"Unknown service: {service}")
        account_id = self._next_id(service)
        profile_dir = self.profiles_root / account_id
        profile_dir.mkdir(parents=True, exist_ok=True)
        account = Account(
            id=account_id, service=service, display_name=display_name,
            profile_dir=str(profile_dir),
        )
        self._store.upsert(account)
        self._store.save()
        return account

    def remove(self, account_id: str) -> None:
        # Delete the browser profile too, so a later account that happens to
        # reuse this id can never inherit these login/session cookies.
        try:
            account = self._store.get(account_id)
            shutil.rmtree(account.profile_dir, ignore_errors=True)
        except KeyError:
            pass
        self._store.remove(account_id)
        self._store.save()

    def rename(self, account_id: str, display_name: str) -> None:
        account = self._store.get(account_id)
        account.display_name = display_name
        self._store.upsert(account)
        self._store.save()

    def set_enabled(self, account_id: str, enabled: bool) -> None:
        account = self._store.get(account_id)
        account.enabled = enabled
        self._store.upsert(account)
        self._store.save()

    def set_status(self, account_id: str, status: str,
                   quota_reset_at: str | None = None) -> None:
        if status not in STATUSES:
            raise ValueError(f"Unknown status: {status!r}")
        account = self._store.get(account_id)
        account.status = status
        account.quota_reset_at = quota_reset_at
        self._store.upsert(account)
        self._store.save()

    def get(self, account_id: str) -> Account:
        return self._store.get(account_id)

    def list(self, service: str | None = None) -> list[Account]:
        accounts = self._store.all()
        if service is None:
            return accounts
        return [a for a in accounts if a.service == service]

    def next_available(self, service: str) -> Account | None:
        for account in self.list(service):
            if account.enabled and account.status == STATUS_READY:
                return account
        return None
