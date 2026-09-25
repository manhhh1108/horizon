"""Run a step with automatic account rotation on quota exhaustion (AC-04/05)."""
from __future__ import annotations

from typing import Any, Callable

from horizon_tool.core.account_manager import (
    AccountManager, STATUS_IN_USE, STATUS_QUOTA, STATUS_READY, STATUS_SESSION_EXPIRED,
)
from horizon_tool.core.exceptions import AllAccountsExhausted, QuotaExhausted, SessionExpired


def _close(worker: Any) -> None:
    session = getattr(worker, "session", None)
    if session is not None and hasattr(session, "close"):
        try:
            session.close()
        except Exception:  # noqa: BLE001 - cleanup must never raise
            pass


def run_step_with_rotation(*, service: str, account_manager: AccountManager,
                           make_worker: Callable[[Any], Any],
                           do_step: Callable[[Any], Any],
                           log: Callable[[str], None] | None = None):
    """Run do_step(worker) with rotation; return (result, account).

    Picks an available account, marks it in-use, builds a worker via
    make_worker(account) and runs do_step. On QuotaExhausted the account is
    marked quota_exhausted, and on SessionExpired it is marked session_expired
    (with a re-login prompt logged); either way the next available account is
    tried, and when none remain, AllAccountsExhausted is raised. Any other
    error frees the account (back to ready) and propagates. The worker's
    session is closed after every attempt.
    """
    while True:
        account = account_manager.next_available(service)
        if account is None:
            raise AllAccountsExhausted(service)
        account_manager.set_status(account.id, STATUS_IN_USE)
        worker = None
        try:
            # Building the worker (launching a browser) can fail — keep it inside
            # the try so the account is never left stranded in `in_use`.
            worker = make_worker(account)
            result = do_step(worker)
        except QuotaExhausted:
            account_manager.set_status(account.id, STATUS_QUOTA)
            if log:
                log(f"Tài khoản '{account.display_name}' hết quota — chuyển tài khoản khác.")
            continue
        except SessionExpired:
            account_manager.set_status(account.id, STATUS_SESSION_EXPIRED)
            if log:
                log(f"Tài khoản '{account.display_name}': phiên đăng nhập hết hạn — "
                    f"hãy đăng nhập lại. Đang chuyển tài khoản khác.")
            continue
        except Exception:
            account_manager.set_status(account.id, STATUS_READY)
            raise
        else:
            account_manager.set_status(account.id, STATUS_READY)
            return result, account
        finally:
            if worker is not None:
                _close(worker)
