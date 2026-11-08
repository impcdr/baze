"""What Hermes is doing during a turn. The page reads this from the app, not from the tab."""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from baze_api.db import apps
from baze_api.settings import Settings

_HOST = re.compile(r"https?://([^/\s\"'\\]+)", re.IGNORECASE)
_FILE = re.compile(r"[A-Za-z0-9._-]{1,40}")


def mark_working(settings: Settings, app_id: str) -> None:
    apps(settings).update_one(
        {"_id": app_id},
        {"$set": {"runtime.working": True, "runtime.activity": ""}},
    )


def mark_idle(settings: Settings, app_id: str) -> None:
    apps(settings).update_one(
        {"_id": app_id},
        {"$set": {"runtime.working": False, "runtime.activity": ""}},
    )


def clear_stale_turns(settings: Settings) -> None:
    """A restarted API is not still inside a turn that the previous process started."""
    apps(settings).update_many(
        {"runtime.working": True},
        {"$set": {"runtime.working": False, "runtime.activity": ""}},
    )


def note_activity(settings: Settings, app_id: str, text: str) -> None:
    apps(settings).update_one(
        {"_id": app_id, "runtime.working": True},
        {"$set": {"runtime.activity": (text or "")[:80]}},
    )


def phrase(name: str, arguments: object) -> str:
    """One short line for the current tool. The command itself stays out of the chat."""
    args = _args(arguments)
    if name == "terminal":
        host = _host(str(args.get("command") or ""))
        if host and host not in {"localhost", "127.0.0.1"}:
            return f"Fetching {host}"
        return "Running a command"
    if name in {"write_file", "patch"}:
        label = _file(args)
        return f"Editing {label}" if label else "Editing the app"
    if name == "read_file":
        label = _file(args)
        return f"Reading {label}" if label else "Reading a file"
    if name in {"browser_exec", "browser_navigate"}:
        host = _host(str(args.get("code") or args.get("url") or ""))
        if host and host not in {"localhost", "127.0.0.1"}:
            return f"Opening {host}"
        return "Checking the page" if host else "Looking at the page"
    if name == "vision_analyze":
        return "Checking the page"
    return ""


def _open_tool(raw: str) -> str:
    try:
        calls = json.loads(raw)
    except json.JSONDecodeError:
        return ""
    if not isinstance(calls, list) or not calls:
        return ""
    last = calls[-1]
    if not isinstance(last, dict):
        return ""
    function = last.get("function") if isinstance(last.get("function"), dict) else {}
    name = function.get("name") if isinstance(function.get("name"), str) else ""
    return phrase(name, function.get("arguments")) or "Using a tool"


def current_activity(data_dir: object, session_id: object = None) -> str:
    """The agent's open action. Empty once the latest reply has finished."""
    if not isinstance(data_dir, str) or not data_dir:
        return ""
    path = Path(data_dir) / "state.db"
    if not path.is_file():
        return ""
    scoped = session_id if isinstance(session_id, str) and session_id else None
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=0.2)
    except sqlite3.Error:
        return ""
    try:
        if scoped:
            row = connection.execute(
                "SELECT role, tool_calls, finish_reason FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT 1",
                (scoped,),
            ).fetchone()
        else:
            row = connection.execute(
                "SELECT role, tool_calls, finish_reason FROM messages ORDER BY id DESC LIMIT 1",
            ).fetchone()
    except sqlite3.Error:
        return ""
    finally:
        connection.close()
    if not row:
        return ""
    role, calls, finish = row[0], row[1], row[2]
    if isinstance(calls, str) and calls.strip() and role in {None, "assistant"}:
        return _open_tool(calls)
    if role in {"user", "tool"} or finish == "tool_calls":
        return "Thinking"
    return ""


class ActivityWatch:
    def __init__(self, settings: Settings, app_id: str) -> None:
        self._settings = settings
        self._app_id = app_id
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="baze-activity", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=1)

    def _run(self) -> None:
        while not self._stop.wait(0.4):
            document = apps(self._settings).find_one(
                {"_id": self._app_id},
                {"runtime.dataDir": 1, "runtime.working": 1, "chat.hermesSessionId": 1},
            )
            if not document or not (document.get("runtime") or {}).get("working"):
                continue
            text = current_activity((document.get("runtime") or {}).get("dataDir"))
            note_activity(self._settings, self._app_id, text)


@contextmanager
def working_turn(settings: Settings, app_id: str):
    mark_working(settings, app_id)
    watch = ActivityWatch(settings, app_id)
    try:
        yield
    finally:
        watch.stop()
        mark_idle(settings, app_id)


def _args(arguments: object) -> dict:
    if isinstance(arguments, dict):
        return arguments
    if not isinstance(arguments, str) or not arguments:
        return {}
    try:
        loaded = json.loads(arguments)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _host(text: str) -> str:
    match = _HOST.search(text)
    if not match:
        return ""
    host = match.group(1).split("@")[-1].split(":")[0].strip(".").lower()
    if not re.fullmatch(r"[a-z0-9.-]{1,80}", host):
        return ""
    return host


def _file(args: dict) -> str:
    raw = args.get("path") or args.get("file_path") or ""
    if not isinstance(raw, str) or not raw:
        return ""
    name = raw.replace("\\", "/").rstrip("/").split("/")[-1]
    if not _FILE.fullmatch(name):
        return ""
    return name
