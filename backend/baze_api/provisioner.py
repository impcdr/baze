"""Start and stop the Hermes container for one runtime app."""

from __future__ import annotations

import logging
import os
import re
import secrets
import shutil
import socket
import subprocess
import threading
import time
import uuid
from datetime import datetime
import urllib.error
import urllib.request
from pathlib import Path

from baze_api.app_proxy import clear_fake_live
from baze_api.docker import docker_command
from baze_api.catalog import MANAGED_APP_IDS, STUDIO_ID, preset
from baze_api.studio_page import (
    HARNESS_OFFSET,
    PAGE_MARKER,
    PAGE_PORT,
    page_file_ready,
    placeholder_page,
    refresh_app_favicon,
    save_reply_page,
    write_host_files,
    write_studio_page,
)
from baze_api.db import apps, messages
from baze_api.http import new_id, now_ms
from baze_api.settings import Settings

_CREATING: set[str] = set()
_CANCELLED: set[str] = set()
_ALLOC = threading.Lock()

log = logging.getLogger("baze.runtime")


def _hosted(document: dict) -> bool:
    return isinstance((document.get("runtime") or {}).get("harnessPort"), int)


def container_args(settings: Settings, document: dict) -> list[str]:
    runtime = document["runtime"]
    hosted = _hosted(document)
    args = [
        "run",
        "-d",
        "--name",
        runtime["containerName"],
        "--restart",
        "unless-stopped",
        "--memory",
        f"{settings.memory_mb}m",
        "--memory-swap",
        f"{settings.memory_mb}m",
        "--cpus",
        settings.cpus,
        "--add-host",
        "baze-inference:host-gateway",
        "-p",
        f"127.0.0.1:{runtime['hostPort']}:{PAGE_PORT if hosted else 8642}",
    ]
    if hosted:
        args.extend(["-p", f"127.0.0.1:{runtime['harnessPort']}:8642"])
    args.extend(
        [
        "-v",
        f"{runtime['dataDir']}:/opt/data",
        "-e",
        "API_SERVER_ENABLED=true",
        "-e",
        "API_SERVER_HOST=0.0.0.0",
        "-e",
        f"API_SERVER_KEY={runtime['apiServerKey']}",
        "-e",
        f"HERMES_UID={os.getuid()}",
        "-e",
        f"HERMES_GID={os.getgid()}",
        ]
    )
    args.append(settings.hermes_image)
    if hosted:
        args.extend(["sh", "/opt/data/app/run.sh"])
    else:
        args.extend(["gateway", "run"])
    return args


def write_config(settings: Settings, document: dict) -> None:
    try:
        _write_config(settings, document)
    except PermissionError:
        _reclaim_data_dir(settings, document)
        _write_config(settings, document)


def _write_config(settings: Settings, document: dict) -> None:
    runtime = document["runtime"]
    root = Path(runtime["dataDir"])
    root.mkdir(parents=True, exist_ok=True)
    base_url = f"http://baze-inference:{settings.proxy_port}/v1"
    # The proxy token is the only credential in this file. The Vultr key stays in the API process.
    text = (
        "model:\n"
        "  provider: custom\n"
        f"  default: {settings.model_id}\n"
        f"  base_url: {base_url}\n"
        f"  api_key: {runtime['proxyToken']}\n"
    )
    (root / "config.yaml").write_text(text)


def _reclaim_data_dir(settings: Settings, document: dict) -> None:
    data_dir = document["runtime"]["dataDir"]
    result = subprocess.run(
        docker_command(
            [
                "run",
                "--rm",
                "--user",
                "root",
                "--entrypoint",
                "chown",
                "-v",
                f"{data_dir}:/opt/data",
                settings.hermes_image,
                "-R",
                f"{os.getuid()}:{os.getgid()}",
                "/opt/data",
            ]
        ),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "could not reclaim the app directory").strip()
        raise RuntimeError(detail)


def http_healthy(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return 200 <= response.status < 500
    except urllib.error.HTTPError as exc:
        return 200 <= exc.code < 500
    except (OSError, urllib.error.URLError):
        return False


def provision(settings: Settings, app_id: str, runner, healthy=http_healthy) -> None:
    document = apps(settings).find_one({"_id": app_id, "runtime.hostPort": {"$type": "int"}})
    if document is None:
        return
    try:
        write_config(settings, document)
        if document["_id"] == STUDIO_ID:
            _write_studio_page(settings, document)
        runner.run(container_args(settings, document))
        deadline = time.monotonic() + settings.health_timeout
        while True:
            if _ports_ready(document, healthy) and _content_ready(document):
                _set_status(settings, app_id, "live", None)
                return
            if time.monotonic() >= deadline:
                _set_status(settings, app_id, "error", "The app did not become ready")
                return
            time.sleep(settings.health_interval)
    except Exception as exc:
        _set_status(settings, app_id, "error", _redact(document, str(exc)))


def remove_app(settings: Settings, document: dict, runner) -> None:
    name = document.get("runtime", {}).get("containerName")
    if name:
        runner.remove(name)
    data_dir = document.get("runtime", {}).get("dataDir")
    if data_dir:
        shutil.rmtree(data_dir, ignore_errors=True)


def begin_hosted_app(settings: Settings, owner_id: str, prompt: str) -> dict:
    """Reserve the shelf row, ports, and page server. The container starts afterwards."""
    name = _app_name(prompt)
    summary = " ".join(prompt.split())[:160]
    look = preset("ocean")
    stamp = now_ms()
    with _ALLOC:
        app_id = uuid.uuid4().hex
        port = _allocate_port(settings)
        data_dir = str(settings.apps_root / app_id)
        document = {
            "_id": app_id,
            "ownerId": owner_id,
            "sort": _next_sort(settings),
            "slug": _slug(name, app_id),
            "name": name,
            "summary": summary,
            "detail": summary,
            "status": "building",
            "statusLabel": "Starting the box",
            "statusError": None,
            "labels": [{"text": "Being made", "tone": "secondary"}],
            "preset": look["id"],
            "color": look["color"],
            "icon": "lucidePackage",
            "isNew": True,
            "badge": "New",
            "progress": None,
            "path": f"/{app_id}",
            "external": True,
            "sharedBy": None,
            "prompt": prompt,
            "createdAt": stamp,
            "updatedAt": stamp,
            "chat": {"hermesSessionId": None},
            "runtime": {
                "containerName": f"baze-app-{app_id}",
                "image": settings.hermes_image,
                "hostPort": port,
                "harnessPort": port + HARNESS_OFFSET,
                "memoryMb": settings.memory_mb,
                "dataDir": data_dir,
                "proxyToken": secrets.token_urlsafe(32),
                "apiServerKey": secrets.token_urlsafe(32),
                "desired": "running",
            },
        }
        apps(settings).insert_one(document)
    write_config(settings, document)
    write_host_files(data_dir, placeholder_page(app_id, name), color=look["color"], icon="lucidePackage")
    return document


def finish_hosted_app(settings: Settings, app_id: str, prompt: str, runner, hermes, healthy=http_healthy) -> None:
    """Start the box, let the agent write the page, and mark the app live only once it is served."""
    _CREATING.add(app_id)
    document = apps(settings).find_one({"_id": app_id})
    if document is None:
        _CREATING.discard(app_id)
        return
    runtime = document["runtime"]
    name = runtime["containerName"]
    try:
        if not _still_there(settings, app_id):
            return
        if runner.exists(name):
            runner.remove(name)
        log.info("Starting container for %s", app_id)
        runner.run(container_args(settings, document))
        if not _wait_ports(settings, document, healthy) or not _still_there(settings, app_id):
            if _still_there(settings, app_id):
                _fail_create(settings, app_id, runner, "The app did not become ready")
            else:
                runner.remove(name)
            return
        _set_label(settings, app_id, "Writing the app")
        holder: dict = {}

        def ask() -> None:
            try:
                holder["result"] = hermes.complete(
                    base_url=f"http://127.0.0.1:{runtime['harnessPort']}",
                    api_key=runtime["apiServerKey"],
                    content=_build_prompt(prompt),
                    session_id=None,
                )
            except Exception as exc:
                holder["error"] = exc
            finally:
                holder["done"] = True

        threading.Thread(target=ask, name=f"baze-build-{app_id[:8]}", daemon=True).start()
        if not _wait_for_page(settings, runtime, holder) or not _still_there(settings, app_id):
            if _still_there(settings, app_id):
                detail = holder.get("error")
                message = _redact(document, str(detail)) if detail else "The app was not written into the container"
                _fail_create(settings, app_id, runner, message)
            else:
                runner.remove(name)
            return
        reply, session = holder.get("result") or ("", None)
        _go_live(settings, app_id, runner, prompt, reply, session)
        if not holder.get("done"):
            threading.Thread(
                target=_keep_reply,
                args=(settings, app_id, prompt, holder),
                name=f"baze-reply-{app_id[:8]}",
                daemon=True,
            ).start()
        log.info("App %s live on 127.0.0.1:%s", app_id, runtime["hostPort"])
    except Exception as exc:
        log.exception("App %s was not created", app_id)
        if _still_there(settings, app_id) and _page_served(runtime):
            _go_live(settings, app_id, runner, prompt, "", None)
        elif _still_there(settings, app_id):
            _fail_create(settings, app_id, runner, _redact(document, str(exc)) or "The app was not created")
        else:
            runner.remove(name)
    finally:
        _CREATING.discard(app_id)


def boot_hosted_app(settings: Settings, app_id: str, runner, healthy=http_healthy) -> None:
    """Start the container and wait until it answers. Do not prompt it."""
    _CREATING.add(app_id)
    document = apps(settings).find_one({"_id": app_id})
    if document is None:
        _CREATING.discard(app_id)
        return
    runtime = document["runtime"]
    name = runtime["containerName"]
    try:
        if not _still_there(settings, app_id):
            return
        _set_step(settings, app_id, "create", "active")
        if runner.exists(name):
            runner.remove(name)
        log.info("Starting container for %s", app_id)
        runner.run(container_args(settings, document))
        _set_step(settings, app_id, "create", "done")
        _set_step(settings, app_id, "start", "active")
        _set_step(settings, app_id, "harness", "active")
        if not _wait_ports(settings, document, healthy) or not _still_there(settings, app_id):
            if _still_there(settings, app_id):
                _fail_create(settings, app_id, runner, "The container did not become ready")
            else:
                runner.remove(name)
            return
        _set_step(settings, app_id, "start", "done")
        _set_step(settings, app_id, "harness", "done")
        apps(settings).update_one(
            {"_id": app_id},
            {"$set": {"runtime.boxReady": True, "statusLabel": "Box is ready", "updatedAt": now_ms()}},
        )
        log.info("Container for %s is ready on 127.0.0.1:%s", app_id, runtime["hostPort"])
    except Exception as exc:
        log.exception("Container for %s did not start", app_id)
        if _still_there(settings, app_id):
            _fail_create(settings, app_id, runner, _redact(document, str(exc)) or "The container did not start")
        else:
            runner.remove(name)
    finally:
        _CREATING.discard(app_id)


def build_in_container(settings: Settings, app_id: str, runner, hermes, healthy=http_healthy) -> None:
    """Prompt the harness only after the container is up."""
    document = apps(settings).find_one({"_id": app_id})
    if document is None or not (document.get("runtime") or {}).get("boxReady"):
        return
    runtime = document["runtime"]
    name = runtime["containerName"]
    turns = list(messages(settings).find({"appId": app_id}).sort("createdAt", 1))
    prompt = _requirements_prompt(turns, document.get("prompt") or document.get("name") or "The app")
    holder: dict = {}

    def ask() -> None:
        try:
            holder["result"] = hermes.complete(
                base_url=f"http://127.0.0.1:{runtime['harnessPort']}",
                api_key=runtime["apiServerKey"],
                content=prompt,
                session_id=None,
            )
        except Exception as exc:
            holder["error"] = exc
        finally:
            holder["done"] = True

    threading.Thread(target=ask, name=f"baze-build-{app_id[:8]}", daemon=True).start()
    try:
        if not _wait_for_page(settings, runtime, holder) or not _still_there(settings, app_id):
            if _still_there(settings, app_id):
                detail = holder.get("error")
                message = _redact(document, str(detail)) if detail else "The app was not written into the container"
                _fail_create(settings, app_id, runner, message)
            return
        reply, session = holder.get("result") or ("", None)
        _mark_plan_done(settings, app_id)
        _go_live(settings, app_id, runner, prompt, reply, session)
        log.info("App %s live on 127.0.0.1:%s", app_id, runtime["hostPort"])
    except Exception as exc:
        log.exception("App %s was not created", app_id)
        if _still_there(settings, app_id) and _page_served(runtime):
            _mark_plan_done(settings, app_id)
            _go_live(settings, app_id, runner, prompt, "", None)
        elif _still_there(settings, app_id):
            _fail_create(settings, app_id, runner, _redact(document, str(exc)) or "The app was not created")
        else:
            runner.remove(name)


def _set_step(settings: Settings, app_id: str, step_id: str, state: str) -> None:
    apps(settings).update_one(
        {"_id": app_id, "build.steps.id": step_id},
        {"$set": {"build.steps.$.state": state, "statusLabel": _step_label(settings, app_id, step_id), "updatedAt": now_ms()}},
    )


def _step_label(settings: Settings, app_id: str, step_id: str) -> str:
    document = apps(settings).find_one({"_id": app_id}, {"build.steps": 1}) or {}
    for step in (document.get("build") or {}).get("steps") or []:
        if step.get("id") == step_id:
            return step.get("label") or ""
    return ""


def _mark_plan_done(settings: Settings, app_id: str) -> None:
    document = apps(settings).find_one({"_id": app_id}, {"build.steps": 1}) or {}
    steps = []
    for step in (document.get("build") or {}).get("steps") or []:
        if str(step.get("id", "")).startswith("plan"):
            step = {**step, "state": "done"}
        steps.append(step)
    apps(settings).update_one({"_id": app_id}, {"$set": {"build.steps": steps}})


def _requirements_prompt(turns: list[dict], fallback: str) -> str:
    lines = ["The reception gathered these requirements:", ""]
    wrote = False
    for turn in turns:
        content = (turn.get("content") or "").strip()
        if not content:
            continue
        who = "Person" if turn.get("role") == "user" else "Reception"
        lines.append(f"{who}: {content}")
        wrote = True
    if not wrote:
        lines.append(fallback)
    lines.append("")
    lines.append(_build_prompt("Build exactly that app."))
    return "\n".join(lines)


def delete_shelf_app(settings: Settings, app_id: str, runner) -> None:
    document = apps(settings).find_one({"_id": app_id, "kind": {"$ne": "runtime"}})
    if document is None:
        raise PowerError("missing", "App not found")
    if document.get("sharedBy"):
        raise PowerError("kept", "This app stays on the shelf")
    _CANCELLED.add(app_id)
    remove_app(settings, document, runner)
    messages(settings).delete_many({"appId": app_id})
    apps(settings).delete_one({"_id": app_id})


def _ensure_created(settings: Settings, app_id: str, runner, healthy, used: set[int]) -> None:
    document = apps(settings).find_one({"_id": app_id}) or {}
    runtime = document.get("runtime") or {}
    if document.get("status") == "building" and app_id not in _CREATING:
        data_dir = runtime.get("dataDir") or ""
        if data_dir and page_file_ready(data_dir) and _ports_ready({"runtime": runtime}, healthy):
            _set_power(settings, app_id, live=True)
            _note_run(settings, app_id, runner, refresh=False)
            return
        if runtime.get("boxReady"):
            apps(settings).update_one({"_id": app_id}, {"$set": {"runtime.buildStarted": False}})
            return
        _set_status(settings, app_id, "error", "Creation was interrupted")
        apps(settings).update_one({"_id": app_id}, {"$set": {"runtime.desired": "stopped", "statusLabel": "Didn’t start"}})
        if runtime.get("containerName") and runner.running(runtime["containerName"]):
            runner.stop(runtime["containerName"])
        return
    if document.get("status") == "building":
        return
    _ensure_one(settings, app_id, runner, healthy, used)


def _user_hosted_ids(settings: Settings) -> list[str]:
    found = []
    query = {"kind": {"$ne": "runtime"}, "_id": {"$nin": MANAGED_APP_IDS}, "runtime.harnessPort": {"$type": "int"}}
    for document in apps(settings).find(query, {"_id": 1}):
        found.append(document["_id"])
    return found


def _still_there(settings: Settings, app_id: str) -> bool:
    if app_id in _CANCELLED:
        return False
    return apps(settings).find_one({"_id": app_id}, {"_id": 1}) is not None


def _fail_create(settings: Settings, app_id: str, runner, message: str) -> None:
    document = apps(settings).find_one({"_id": app_id}, {"runtime.containerName": 1}) or {}
    name = (document.get("runtime") or {}).get("containerName")
    if name:
        runner.remove(name)
    apps(settings).update_one(
        {"_id": app_id},
        {
            "$set": {
                "status": "error",
                "statusLabel": "Didn’t start",
                "statusError": message[:500],
                "labels": [{"text": "Didn’t start", "tone": "warning"}],
                "runtime.desired": "stopped",
                "updatedAt": now_ms(),
            }
        },
    )


def _set_label(settings: Settings, app_id: str, label: str) -> None:
    apps(settings).update_one(
        {"_id": app_id},
        {"$set": {"statusLabel": label, "updatedAt": now_ms()}},
    )


def _wait_ports(settings: Settings, document: dict, healthy) -> bool:
    deadline = time.monotonic() + settings.health_timeout
    while True:
        if _ports_ready(document, healthy):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(settings.health_interval)


def _page_served(runtime: dict) -> bool:
    body = _fetch_page(runtime.get("hostPort"))
    if body is None:
        return page_file_ready(runtime["dataDir"])
    return 'data-baze-build="placeholder"' not in body and "<html" in body.lower()


def _fetch_page(port: object) -> str | None:
    if not isinstance(port, int):
        return None
    url = f"http://127.0.0.1:{port}/"
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return response.read(20000).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.read(20000).decode("utf-8", "replace")
    except (OSError, urllib.error.URLError):
        return None


def _wait_for_page(settings: Settings, runtime: dict, holder: dict) -> bool:
    """The app is ready when its page is served. The agent may still be looking at it."""
    budget = 300.0 if settings.health_timeout > 0 else 15.0
    deadline = time.monotonic() + budget
    while True:
        reply = holder["result"][0] if holder.get("result") else ""
        if reply:
            save_reply_page(runtime["dataDir"], reply)
        if page_file_ready(runtime["dataDir"]) and _page_served(runtime):
            return True
        if holder.get("done") or time.monotonic() >= deadline:
            return page_file_ready(runtime["dataDir"]) and _page_served(runtime)
        time.sleep(settings.health_interval or 0.05)


def _go_live(settings: Settings, app_id: str, runner, prompt: str, reply: str, session: str | None) -> None:
    if reply:
        _store_build_chat(settings, app_id, prompt, reply, session)
    _set_power(settings, app_id, live=True)
    apps(settings).update_one(
        {"_id": app_id},
        {
            "$set": {
                "badge": "New",
                "isNew": True,
                "statusError": None,
                "statusLabel": "Live",
                "labels": [
                    {"text": "New", "tone": "secondary"},
                    {"text": "Live", "tone": "success"},
                ],
                "runtime.desired": "running",
            }
        },
    )
    _note_run(settings, app_id, runner, refresh=True)


def _keep_reply(settings: Settings, app_id: str, prompt: str, holder: dict) -> None:
    while not holder.get("done"):
        time.sleep(0.5)
    result = holder.get("result")
    if not result or not _still_there(settings, app_id):
        return
    reply, session = result
    _store_build_chat(settings, app_id, prompt, reply, session)


def _store_build_chat(settings: Settings, app_id: str, prompt: str, reply: str, session: str | None) -> None:
    if session:
        apps(settings).update_one({"_id": app_id}, {"$set": {"chat.hermesSessionId": session}})
    if not reply:
        return
    if messages(settings).find_one({"appId": app_id, "role": "assistant", "content": reply}, {"_id": 1}):
        return
    messages(settings).insert_one(
        {"_id": new_id(), "appId": app_id, "role": "assistant", "content": reply, "createdAt": now_ms()}
    )


def _build_prompt(prompt: str) -> str:
    return (
        "Build the app described below and host it in this container.\n\n"
        f"{prompt}\n\n"
        "Write the finished app to /opt/data/app/index.html. "
        "A server is already serving that folder on port 8080, so replacing index.html publishes the app. "
        "You may add other files under /opt/data/app. Do not change server.py, run.sh, or favicon.svg. "
        "Keep the favicon link in the page head. "
        "Do not add a chat box. Code the app however it needs to work. "
        "If you cannot write the file yourself, reply with only the full HTML document."
    )


def _app_name(prompt: str) -> str:
    line = " ".join(prompt.split())
    if len(line) > 42:
        cut = line[:42].strip().rsplit(" ", 1)[0].strip()
        line = cut or line[:42].strip()
    if not line:
        return "New app"
    return line[:1].upper() + line[1:]


def _slug(name: str, app_id: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "app"
    return f"{base}-{app_id[:8]}"


def _next_sort(settings: Settings) -> int:
    last = apps(settings).find_one({"kind": {"$ne": "runtime"}}, {"sort": 1}, sort=[("sort", -1)])
    current = last.get("sort") if last else None
    return current + 1 if isinstance(current, int) else 1


def _allocate_port(settings: Settings) -> int:
    used: set[int] = set()
    for document in apps(settings).find({}, {"runtime.hostPort": 1, "runtime.harnessPort": 1}):
        runtime = document.get("runtime") or {}
        for key in ("hostPort", "harnessPort"):
            port = runtime.get(key)
            if isinstance(port, int):
                used.add(port)
    port = settings.hermes_port_start
    limit = port + 200
    while port < limit:
        harness = port + HARNESS_OFFSET
        if port not in used and harness not in used and _port_free(port) and _port_free(harness):
            return port
        port += 1
    raise RuntimeError("No free port for the app")


def _port_free(port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))
    except OSError:
        return False
    finally:
        sock.close()
    return True


def ensure_managed(settings: Settings, runner, healthy=http_healthy) -> None:
    """Each shelf app has its own container. A stopped choice stays stopped."""
    from baze_api.seed import reconcile_catalog

    reconcile_catalog(settings)
    clear_fake_live(settings)
    used: set[int] = set()
    for app_id in MANAGED_APP_IDS:
        _ensure_one(settings, app_id, runner, healthy, used)
    for app_id in _user_hosted_ids(settings):
        _ensure_created(settings, app_id, runner, healthy, used)


def ensure_studio(settings: Settings, runner, healthy=http_healthy) -> None:
    """Backward-compatible entry for the Studio Invoices container."""
    clear_fake_live(settings)
    _ensure_one(settings, STUDIO_ID, runner, healthy, set())


def _ensure_one(settings: Settings, app_id: str, runner, healthy, used: set[int]) -> None:
    document = apps(settings).find_one({"_id": app_id})
    if document is None:
        log.error("App %s is not in the catalog", app_id)
        return
    runtime = dict(document.get("runtime") or {})
    for key in ("dashboardPort", "dashboardUser", "dashboardPassword"):
        runtime.pop(key, None)
    name = runtime.get("containerName") or f"baze-app-{app_id}"
    port = _take_port(settings, runtime, used)
    if app_id == STUDIO_ID:
        runtime["harnessPort"] = port + HARNESS_OFFSET
    runtime.update(
        {
            "containerName": name,
            "image": settings.hermes_image,
            "hostPort": port,
            "memoryMb": settings.memory_mb,
            "dataDir": runtime.get("dataDir") or str(settings.apps_root / app_id),
            "proxyToken": runtime.get("proxyToken") or secrets.token_urlsafe(32),
            "apiServerKey": runtime.get("apiServerKey") or secrets.token_urlsafe(32),
        }
    )
    apps(settings).update_one({"_id": app_id}, {"$set": {"runtime": runtime, "updatedAt": now_ms()}})
    try:
        refresh_app_favicon(runtime["dataDir"], document.get("color") or "", document.get("icon") or "")
    except OSError:
        log.warning("Could not refresh the favicon for %s", app_id)
    if runtime.get("desired") == "stopped":
        if runner.running(name):
            runner.stop(name)
        _set_power(settings, app_id, live=False)
        log.info("App %s stays stopped", app_id)
        return
    if runner.running(name) and _ports_ready({"runtime": runtime}, healthy) and _content_ready({"_id": app_id, "runtime": runtime}) and _page_ready(app_id, port):
        _set_power(settings, app_id, live=True)
        _note_run(settings, app_id, runner, refresh=False)
        log.info("App %s already live on 127.0.0.1:%s", app_id, port)
        return
    runner.remove(name)
    log.info("Starting container for %s", app_id)
    provision(settings, app_id, runner, healthy)
    current = apps(settings).find_one({"_id": app_id}, {"status": 1, "statusError": 1})
    if current and current.get("status") == "live":
        _set_power(settings, app_id, live=True)
        _note_run(settings, app_id, runner, refresh=True)
        log.info("App %s live on 127.0.0.1:%s", app_id, port)
        return
    log.error("App %s container failed: %s", app_id, (current or {}).get("statusError"))


def _take_port(settings: Settings, runtime: dict, used: set[int]) -> int:
    port = runtime.get("hostPort")
    if isinstance(port, int) and port not in used:
        used.add(port)
        return port
    port = settings.hermes_port_start
    while port in used:
        port += 1
    used.add(port)
    return port


class PowerError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def start_catalog_app(settings: Settings, app_id: str, runner, healthy=http_healthy) -> dict:
    document = _runnable(settings, app_id)
    runtime = document["runtime"]
    name = runtime["containerName"]
    was_running = runner.running(name)
    apps(settings).update_one({"_id": app_id}, {"$set": {"runtime.desired": "running", "updatedAt": now_ms()}})
    try:
        if not was_running:
            if runner.exists(name):
                runner.start(name)
            else:
                provision(settings, app_id, runner, healthy)
    except PowerError:
        raise
    except Exception as exc:
        raise PowerError("unavailable", _redact(document, str(exc))) from exc
    deadline = time.monotonic() + settings.health_timeout
    while True:
        current = apps(settings).find_one({"_id": app_id}) or document
        if _ports_ready(current, healthy):
            started = _set_power(settings, app_id, live=True)
            _note_run(settings, app_id, runner, refresh=not was_running)
            return started
        if current.get("status") == "error" or time.monotonic() >= deadline:
            detail = current.get("statusError") or "The app did not start"
            raise PowerError("unavailable", detail)
        time.sleep(settings.health_interval)


def stop_catalog_app(settings: Settings, app_id: str, runner) -> dict:
    document = _runnable(settings, app_id)
    name = document["runtime"]["containerName"]
    apps(settings).update_one({"_id": app_id}, {"$set": {"runtime.desired": "stopped", "updatedAt": now_ms()}})
    try:
        if runner.exists(name):
            runner.stop(name)
    except Exception as exc:
        raise PowerError("unavailable", _redact(document, str(exc))) from exc
    return _set_power(settings, app_id, live=False)


def _runnable(settings: Settings, app_id: str) -> dict:
    document = apps(settings).find_one({"_id": app_id, "kind": {"$ne": "runtime"}})
    if document is None:
        raise PowerError("missing", "App not found")
    if not (document.get("runtime") or {}).get("containerName"):
        raise PowerError("not_runnable", "This app has no container")
    return document


def _note_run(settings: Settings, app_id: str, runner, *, refresh: bool) -> None:
    document = apps(settings).find_one({"_id": app_id}, {"runtime.lastStartedAt": 1, "runtime.containerName": 1}) or {}
    runtime = document.get("runtime") or {}
    if runtime.get("lastStartedAt") and not refresh:
        return
    stamp = _docker_ms(runner.started_at(runtime["containerName"])) if runtime.get("containerName") and hasattr(runner, "started_at") else None
    apps(settings).update_one(
        {"_id": app_id},
        {"$set": {"runtime.lastStartedAt": stamp or now_ms()}},
    )


def _docker_ms(value: str | None) -> int | None:
    if not value or value.startswith("0001"):
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    if "." in text:
        left, right = text.split(".", 1)
        digits: list[str] = []
        rest = ""
        for index, char in enumerate(right):
            if char.isdigit() and not rest:
                digits.append(char)
            else:
                rest = right[index:]
                break
        text = f"{left}.{(''.join(digits)[:6]).ljust(6, '0')}{rest or '+00:00'}"
    try:
        return int(datetime.fromisoformat(text).timestamp() * 1000)
    except ValueError:
        return None


def _set_power(settings: Settings, app_id: str, *, live: bool) -> dict:
    document = apps(settings).find_one({"_id": app_id}) or {}
    labels = [label for label in document.get("labels") or [] if label.get("text") != "Live"]
    if live:
        labels.append({"text": "Live", "tone": "success"})
        fields = {"status": "live", "statusLabel": "Live", "labels": labels}
    else:
        fields = {"status": "stopped", "statusLabel": "", "labels": labels}
    apps(settings).update_one({"_id": app_id}, {"$set": {**fields, "updatedAt": now_ms()}})
    document.update(fields)
    return document


def _write_studio_page(settings: Settings, document: dict) -> None:
    try:
        write_studio_page(
            document["runtime"]["dataDir"],
            document["_id"],
            color=document.get("color") or "",
            icon=document.get("icon") or "",
        )
    except PermissionError:
        _reclaim_data_dir(settings, document)
        write_studio_page(
            document["runtime"]["dataDir"],
            document["_id"],
            color=document.get("color") or "",
            icon=document.get("icon") or "",
        )


def _content_ready(document: dict) -> bool:
    """Studio and gateway apps are ready when their ports answer. A created app waits for its page."""
    if not _hosted(document) or document.get("_id") == STUDIO_ID:
        return True
    data_dir = (document.get("runtime") or {}).get("dataDir")
    return bool(data_dir) and page_file_ready(data_dir)


def _page_ready(app_id: str, port: int) -> bool:
    if app_id != STUDIO_ID:
        return True
    url = f"http://127.0.0.1:{port}/"
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            body = response.read(8000)
    except urllib.error.HTTPError as exc:
        body = exc.read(8000)
    except (OSError, urllib.error.URLError):
        return False
    return PAGE_MARKER.encode() in body


def _ports_ready(document: dict, healthy) -> bool:
    runtime = document.get("runtime") or {}
    if not healthy(f"http://127.0.0.1:{runtime['hostPort']}/health"):
        return False
    harness = runtime.get("harnessPort")
    if isinstance(harness, int):
        return healthy(f"http://127.0.0.1:{harness}/health")
    return True


def _redact(document: dict, text: str) -> str:
    runtime = document.get("runtime") or {}
    for key in ("apiServerKey", "proxyToken"):
        secret = runtime.get(key)
        if secret:
            text = text.replace(str(secret), "[redacted]")
    return text[:500]


def _set_status(settings: Settings, app_id: str, status: str, error: str | None) -> None:
    apps(settings).update_one(
        {"_id": app_id},
        {"$set": {"status": status, "statusError": error, "updatedAt": now_ms()}},
    )
