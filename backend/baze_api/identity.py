"""Which seeded account the browser is using, and which address opened the connection."""

from __future__ import annotations

from contextvars import ContextVar

_EMAIL: ContextVar[str | None] = ContextVar("baze_email", default=None)
_IP: ContextVar[str] = ContextVar("baze_ip", default="")


def set_current_email(email: str | None) -> None:
    _EMAIL.set(email)


def current_email() -> str | None:
    return _EMAIL.get()


def set_current_ip(ip: str | None) -> None:
    _IP.set(ip or "")


def current_ip() -> str:
    return _IP.get() or ""


def address_allows(document: dict) -> bool:
    """An app with a creator address is sent only to that connection."""
    locked = document.get("creatorIp") if isinstance(document, dict) else None
    if not isinstance(locked, str) or not locked:
        return True
    return locked == current_ip()
