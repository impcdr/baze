"""Which seeded account the browser is using."""

from __future__ import annotations

from contextvars import ContextVar

_EMAIL: ContextVar[str | None] = ContextVar("baze_email", default=None)


def set_current_email(email: str | None) -> None:
    _EMAIL.set(email)


def current_email() -> str | None:
    return _EMAIL.get()
