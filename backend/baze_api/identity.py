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


def visitor_ip(peer: str | None, forwarded: str | None) -> str:
    """The person on the other side of the connection.

    A local proxy is the only peer allowed to name them. A header from anywhere else is ignored.
    """
    address = peer or ""
    if address in {"127.0.0.1", "::1"}:
        named = (forwarded or "").split(",")[0].strip()
        if named:
            return named
    return address


def address_allows(document: dict) -> bool:
    """An app with a creator address is sent only to that connection."""
    locked = document.get("creatorIp") if isinstance(document, dict) else None
    if not isinstance(locked, str) or not locked:
        return True
    return locked == current_ip()
