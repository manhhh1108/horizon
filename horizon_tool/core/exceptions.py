"""Domain exceptions for account quota and rotation."""
from __future__ import annotations


class QuotaExhausted(Exception):
    """Raised when the current service account has hit its usage quota."""

    def __init__(self, service: str = "", message: str = "") -> None:
        super().__init__(message or f"Quota exhausted for service: {service!r}")
        self.service = service


class AllAccountsExhausted(Exception):
    """Raised when no enabled account of a service has quota left."""

    def __init__(self, service: str) -> None:
        super().__init__(f"All {service!r} accounts are exhausted")
        self.service = service
