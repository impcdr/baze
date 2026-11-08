"""One-time secrets between a person and the agent in a Data box.

The value lives here until the other side reads it. The log keeps the name and the direction.
"""

from __future__ import annotations

from baze_api.db import apps
from baze_api.http import new_id, now_ms
from baze_api.settings import Settings

_WAITING_CAP = 20
_LOG_CAP = 40


class SecretError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def leave_secret(settings: Settings, app_id: str, *, name: str, value: str, to: str) -> None:
    """Leave a secret for the other side. `to` is who may read it."""
    if to not in {"agent", "user"}:
        raise SecretError("profile")
    cleaned_name = _name(name)
    cleaned_value = _value(value)
    document = apps(settings).find_one({"_id": app_id}, {"runtime.profile": 1, "runtime.secrets": 1})
    if document is None or (document.get("runtime") or {}).get("profile") != "data":
        raise SecretError("profile")
    waiting = [item for item in ((document.get("runtime") or {}).get("secrets") or []) if isinstance(item, dict)]
    if len(waiting) >= _WAITING_CAP:
        raise SecretError("full")
    stamp = now_ms()
    apps(settings).update_one(
        {"_id": app_id},
        {
            "$push": {
                "runtime.secrets": {
                    "id": new_id(),
                    "name": cleaned_name,
                    "value": cleaned_value,
                    "to": to,
                    "at": stamp,
                },
                "runtime.secretLog": {
                    "$each": [{"id": new_id(), "name": cleaned_name, "to": to, "event": "left", "at": stamp}],
                    "$slice": -_LOG_CAP,
                },
            }
        },
    )


def take_secret(settings: Settings, app_id: str, *, to: str, secret_id: str | None = None) -> dict | None:
    """Read one secret addressed to this side. Reading removes it."""
    if to not in {"agent", "user"}:
        raise SecretError("profile")
    for _ in range(3):
        document = apps(settings).find_one(
            {"_id": app_id},
            {"runtime.profile": 1, "runtime.secrets": 1},
        )
        if document is None or (document.get("runtime") or {}).get("profile") != "data":
            raise SecretError("profile")
        match = _oldest((document.get("runtime") or {}).get("secrets") or [], to, secret_id)
        if match is None:
            return None
        stamp = now_ms()
        updated = apps(settings).update_one(
            {"_id": app_id, "runtime.secrets.id": match["id"]},
            {
                "$pull": {"runtime.secrets": {"id": match["id"]}},
                "$push": {
                    "runtime.secretLog": {
                        "$each": [{"id": new_id(), "name": match["name"], "to": to, "event": "read", "at": stamp}],
                        "$slice": -_LOG_CAP,
                    }
                },
            },
        )
        if updated.modified_count:
            return {"name": match["name"], "value": match["value"]}
    return None


def public_secrets(document: dict) -> dict | None:
    """Names and the log. The value stays out of this view."""
    runtime = document.get("runtime") or {}
    if runtime.get("profile") != "data":
        return None
    pending = [item for item in (runtime.get("secrets") or []) if isinstance(item, dict)]
    log = [item for item in (runtime.get("secretLog") or []) if isinstance(item, dict)]
    return {
        "forYou": [_public_pending(item) for item in pending if item.get("to") == "user"],
        "forApp": [_public_pending(item) for item in pending if item.get("to") == "agent"],
        "log": [_public_log(item) for item in log if item.get("event") in {"left", "read"}],
    }


def _public_pending(item: dict) -> dict:
    return {
        "id": item.get("id") or "",
        "name": item.get("name") or "",
        "at": item.get("at") if isinstance(item.get("at"), int) else 0,
    }


def _public_log(item: dict) -> dict:
    return {
        "id": item.get("id") or "",
        "name": item.get("name") or "",
        "to": item.get("to") if item.get("to") in {"agent", "user"} else "agent",
        "event": item.get("event"),
        "at": item.get("at") if isinstance(item.get("at"), int) else 0,
    }


def _oldest(pending: list, to: str, secret_id: str | None) -> dict | None:
    found = []
    for item in pending:
        if not isinstance(item, dict) or item.get("to") != to:
            continue
        if secret_id is not None and item.get("id") != secret_id:
            continue
        if not isinstance(item.get("name"), str) or not isinstance(item.get("value"), str):
            continue
        found.append(item)
    if not found:
        return None
    found.sort(key=lambda item: item.get("at") if isinstance(item.get("at"), int) else 0)
    return found[0]


def _name(value: object) -> str:
    if not isinstance(value, str):
        raise SecretError("name")
    name = " ".join(value.split())
    if not name or len(name) > 60:
        raise SecretError("name")
    return name


def _value(value: object) -> str:
    if not isinstance(value, str):
        raise SecretError("value")
    text = value.strip()
    if not text or len(text) > 4000:
        raise SecretError("value")
    return text
