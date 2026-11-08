"""In-process limits for temporary apps, turns, visitors, and model calls.

The API is one process. Turn slots and visitor windows live in memory.
The daily model count is one Mongo document so a restart keeps the budget.
How many temporary apps can run is computed from host memory.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from baze_api.db import apps, get_db, messages
from baze_api.settings import Settings

log = logging.getLogger("baze.limits")

MODEL_LIMIT = "The model has answered enough for today. Try again tomorrow."
_HOUR = 3600
_DAY = 86400
_LOCK = threading.Lock()
_TURNS = 0
_PENDING = 0
_STARTS: dict[str, list[float]] = {}


class TooMany(Exception):
    """A visitor, turn, or temporary-app limit was reached."""


def reset() -> None:
    """Drop in-memory windows. Tests use this between cases."""
    global _TURNS, _PENDING
    with _LOCK:
        _TURNS = 0
        _PENDING = 0
        _STARTS.clear()


def mem_total_mb() -> int:
    """Installed RAM in MiB, from MemTotal. Available memory is left out on purpose."""
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        if line.startswith("MemTotal:"):
            return int(line.split()[1]) // 1024
    return 0


def hosted_room(mem_total_mb: int, memory_mb: int, running_demos: int) -> int:
    """Slots left for temporary apps: floor(mem * 0.6 / container cap) minus running demos."""
    if memory_mb <= 0:
        return 0
    slots = (mem_total_mb * 3) // (memory_mb * 5)
    return max(0, slots - max(running_demos, 0))


def running_demo_count(settings: Settings) -> int:
    return apps(settings).count_documents(
        {
            "demo": True,
            "status": {"$ne": "stopped"},
            "runtime.containerName": {"$type": "string"},
            "runtime.desired": {"$ne": "stopped"},
        }
    )


def temporary_running(settings: Settings) -> int:
    return apps(settings).count_documents(
        {
            "kind": {"$ne": "runtime"},
            "demo": {"$ne": True},
            "status": {"$ne": "stopped"},
            "runtime.containerName": {"$type": "string"},
        }
    )


def temporary_room(settings: Settings) -> int:
    return hosted_room(mem_total_mb(), settings.memory_mb, running_demo_count(settings))


def hosted_sentence(room: int) -> str:
    return f"This machine can host {room} temporary apps at once, and that many are already running."


def turn_sentence(settings: Settings) -> str:
    return f"{settings.turn_cap} apps are already being built. Try again in a little while."


def reserve_hosted(settings: Settings) -> None:
    """Hold a temporary slot until the shelf row exists."""
    global _PENDING
    with _LOCK:
        room = temporary_room(settings)
        if temporary_running(settings) + _PENDING >= room:
            raise TooMany(hosted_sentence(room))
        _PENDING += 1


def release_hosted_reservation() -> None:
    global _PENDING
    with _LOCK:
        _PENDING = max(0, _PENDING - 1)


def begin_start(settings: Settings, ip: str) -> None:
    """Record one visitor start and take a turn slot."""
    global _TURNS
    who = ip or "unknown"
    with _LOCK:
        if _TURNS >= settings.turn_cap:
            raise TooMany(turn_sentence(settings))
        if not _allow_ip(who, settings, time.time()):
            raise TooMany("This visitor has started enough apps for now. Try again later.")
        _TURNS += 1


def release_turn() -> None:
    global _TURNS
    with _LOCK:
        _TURNS = max(0, _TURNS - 1)


def _allow_ip(ip: str, settings: Settings, now: float) -> bool:
    stamps = [stamp for stamp in _STARTS.get(ip, []) if now - stamp < _DAY]
    recent = [stamp for stamp in stamps if now - stamp < _HOUR]
    if len(recent) >= settings.ip_starts_per_hour or len(stamps) >= settings.ip_starts_per_day:
        _STARTS[ip] = stamps
        return False
    stamps.append(now)
    _STARTS[ip] = stamps
    return True


def take_model_call(settings: Settings) -> bool:
    """Count one completion for today. False when the daily budget is spent."""
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    coll = get_db(settings).limits
    current = coll.find_one({"_id": "model-calls"})
    if current is None or current.get("day") != day:
        coll.update_one({"_id": "model-calls"}, {"$set": {"day": day, "count": 0}}, upsert=True)
    updated = coll.find_one_and_update(
        {"_id": "model-calls", "day": day, "count": {"$lt": settings.model_calls_per_day}},
        {"$inc": {"count": 1}},
    )
    return updated is not None


def admin_code_matches(settings: Settings, given: str) -> bool:
    """Constant-time compare. An empty configured code never matches."""
    expected = settings.admin_code
    given_digest = hashlib.sha256(given.encode()).digest()
    expected_digest = hashlib.sha256(expected.encode()).digest()
    same = hmac.compare_digest(given_digest, expected_digest)
    return bool(expected) and bool(given) and same


def mark_existing_demos(settings: Settings) -> None:
    """Apps already on the shelf, and every catalog id, stay. New apps carry expiresAt."""
    from baze_api.catalog import MANAGED_APP_IDS, RETIRED_APP_IDS

    ids = [*MANAGED_APP_IDS, *RETIRED_APP_IDS]
    apps(settings).update_many(
        {"$or": [{"_id": {"$in": ids}}, {"expiresAt": {"$exists": False}}]},
        {"$set": {"demo": True}, "$unset": {"expiresAt": ""}},
    )


def expire_temporary(settings: Settings, runner) -> int:
    """Remove temporary apps whose hour has passed. A busy turn is left until it is idle."""
    from baze_api.provisioner import progress_is_busy, remove_app

    now = int(time.time() * 1000)
    removed = 0
    found = list(apps(settings).find({"demo": {"$ne": True}, "expiresAt": {"$lte": now}}))
    for document in found:
        if progress_is_busy(document["_id"]):
            continue
        remove_app(settings, document, runner)
        messages(settings).delete_many({"appId": document["_id"]})
        apps(settings).delete_one({"_id": document["_id"]})
        removed += 1
        log.info("Temporary app %s expired", document["_id"])
    return removed


def sweep_forever(settings: Settings, runner, interval: float = 60) -> None:
    while True:
        time.sleep(interval)
        try:
            expire_temporary(settings, runner)
        except Exception:
            log.exception("temporary apps were not swept")
