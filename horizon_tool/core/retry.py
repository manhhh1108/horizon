"""Retry a callable with exponential backoff (spec §12: network/page-load)."""
from __future__ import annotations

import time
from typing import Callable, Iterable


def retry_with_backoff(fn: Callable, *, attempts: int, base_seconds: float,
                       sleep: Callable[[float], None] = time.sleep,
                       exclude: Iterable[type[BaseException]] = (),
                       log: Callable[[str], None] | None = None):
    """Call fn(); on failure retry up to `attempts` times, sleeping
    base_seconds * 2**i before retry i+1. Exceptions in `exclude` propagate
    immediately (no retry). Re-raises the last error if all attempts fail.
    """
    exclude = tuple(exclude)
    attempts = max(1, attempts)
    last: BaseException | None = None
    for i in range(attempts):
        try:
            return fn()
        except exclude:
            raise
        except Exception as exc:  # noqa: BLE001 - retried below
            last = exc
            if log:
                log(f"Thử lại ({i + 1}/{attempts}) sau lỗi: {exc}")
            if i < attempts - 1:
                sleep(base_seconds * (2 ** i))
    raise last  # type: ignore[misc]
