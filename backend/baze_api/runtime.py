"""Runtime apps: one Hermes container each, owned by the seeded user."""

from __future__ import annotations

import re
import secrets
import threading

import falcon
from pymongo.errors import PyMongoError

from baze_api.catalog import USER_EMAIL
from baze_api.db import apps, messages, users
from baze_api.docker import DockerCli
from baze_api.hermes import HermesClient, HermesError
from baze_api.http import clean_content, clean_title, new_id, now_ms, read_json
from baze_api.provisioner import http_healthy, provision, remove_app
from baze_api.settings import Settings

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
RUNNING = ("provisioning", "live")


def _guard(fn):
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except falcon.HTTPError:
            raise
        except PyMongoError as exc:
            raise falcon.HTTPServiceUnavailable(description="Database unavailable") from exc

    return wrapper


class RuntimeServices:
    def __init__(self, runner, hermes: HermesClient, spawn, healthy=http_healthy, infer=None) -> None:
        self.runner = runner
        self.hermes = hermes
        self.spawn = spawn
        self.healthy = healthy
        self.infer = infer

    @staticmethod
    def production() -> "RuntimeServices":
        return RuntimeServices(
            DockerCli(),
            HermesClient(),
            lambda fn: threading.Thread(target=fn, name="baze-provision", daemon=True).start(),
        )


def public_runtime_app(document: dict) -> dict:
    chat = document.get("chat") or {}
    return {
        "id": document["_id"],
        "name": document["name"],
        "status": document["status"],
        "statusError": document.get("statusError"),
        "createdAt": document["createdAt"],
        "updatedAt": document["updatedAt"],
        "chat": {"title": chat.get("title"), "hermesSessionId": chat.get("hermesSessionId")},
    }


def public_turn(document: dict) -> dict:
    return {
        "id": document["_id"],
        "role": document["role"],
        "content": document["content"],
        "createdAt": document["createdAt"],
    }


def _owner_id(settings: Settings) -> str:
    document = users(settings).find_one({"email": USER_EMAIL}, {"_id": 1})
    if document is None:
        raise falcon.HTTPServiceUnavailable(description="Signed-in user is missing")
    return document["_id"]


def _load(settings: Settings, app_id: str, owner_id: str) -> dict:
    if not UUID_RE.match(app_id):
        raise falcon.HTTPNotFound(description="App not found")
    document = apps(settings).find_one({"_id": app_id, "kind": "runtime", "ownerId": owner_id})
    if document is None:
        raise falcon.HTTPNotFound(description="App not found")
    return document


def _next_port(settings: Settings) -> int:
    used = {
        document["runtime"]["hostPort"]
        for document in apps(settings).find({"kind": "runtime"}, {"runtime.hostPort": 1})
        if document.get("runtime", {}).get("hostPort") is not None
    }
    port = settings.hermes_port_start
    while port in used:
        port += 1
    return port


def _slug(name: str, app_id: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "app"
    return f"{base}-{app_id[:8]}"


class RuntimeApps:
    def __init__(self, settings: Settings, services: RuntimeServices) -> None:
        self.settings = settings
        self.services = services

    @_guard
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        owner_id = _owner_id(self.settings)
        documents = apps(self.settings).find({"kind": "runtime", "ownerId": owner_id}).sort("createdAt", -1)
        resp.media = [public_runtime_app(document) for document in documents]

    @_guard
    def on_post(self, req: falcon.Request, resp: falcon.Response) -> None:
        owner_id = _owner_id(self.settings)
        name = clean_title(read_json(req).get("name"), required=True)
        running = apps(self.settings).count_documents({"kind": "runtime", "status": {"$in": list(RUNNING)}})
        if running >= self.settings.app_cap:
            raise falcon.HTTPConflict(description="Two apps are already running")
        stamp = now_ms()
        app_id = new_id()
        port = _next_port(self.settings)
        data_dir = str(self.settings.apps_root / app_id)
        document = {
            "_id": app_id,
            "kind": "runtime",
            "ownerId": owner_id,
            "slug": _slug(name, app_id),
            "name": name,
            "status": "provisioning",
            "statusError": None,
            "createdAt": stamp,
            "updatedAt": stamp,
            "chat": {"title": name, "hermesSessionId": None},
            "runtime": {
                "containerName": f"baze-app-{app_id}",
                "image": self.settings.hermes_image,
                "hostPort": port,
                "memoryMb": self.settings.memory_mb,
                "dataDir": data_dir,
                "proxyToken": secrets.token_urlsafe(32),
                "apiServerKey": secrets.token_urlsafe(32),
            },
        }
        apps(self.settings).insert_one(document)
        self.services.spawn(
            lambda: provision(self.settings, app_id, self.services.runner, self.services.healthy)
        )
        resp.status = falcon.HTTP_201
        resp.media = public_runtime_app(document)


class RuntimeApp:
    def __init__(self, settings: Settings, services: RuntimeServices) -> None:
        self.settings = settings
        self.services = services

    @_guard
    def on_get(self, req: falcon.Request, resp: falcon.Response, app_id: str) -> None:
        document = _load(self.settings, app_id, _owner_id(self.settings))
        resp.media = public_runtime_app(document)

    @_guard
    def on_delete(self, req: falcon.Request, resp: falcon.Response, app_id: str) -> None:
        document = _load(self.settings, app_id, _owner_id(self.settings))
        remove_app(self.settings, document, self.services.runner)
        messages(self.settings).delete_many({"appId": app_id})
        apps(self.settings).delete_one({"_id": app_id})
        resp.status = falcon.HTTP_204


class RuntimeMessages:
    def __init__(self, settings: Settings, services: RuntimeServices) -> None:
        self.settings = settings
        self.services = services

    @_guard
    def on_get(self, req: falcon.Request, resp: falcon.Response, app_id: str) -> None:
        _load(self.settings, app_id, _owner_id(self.settings))
        turns = messages(self.settings).find({"appId": app_id}).sort("createdAt", 1)
        resp.media = [public_turn(turn) for turn in turns]

    @_guard
    def on_post(self, req: falcon.Request, resp: falcon.Response, app_id: str) -> None:
        document = _load(self.settings, app_id, _owner_id(self.settings))
        if document["status"] != "live":
            raise falcon.HTTPConflict(description="App is not live")
        content = clean_content(read_json(req).get("content"))
        stamp = now_ms()
        user_turn = {
            "_id": new_id(),
            "appId": app_id,
            "role": "user",
            "content": content,
            "createdAt": stamp,
        }
        session_id = (document.get("chat") or {}).get("hermesSessionId")
        try:
            reply, session = self.services.hermes.complete(
                base_url=f"http://127.0.0.1:{document['runtime']['hostPort']}",
                api_key=document["runtime"]["apiServerKey"],
                content=content,
                session_id=session_id,
            )
        except HermesError as exc:
            raise falcon.HTTPBadGateway(description=str(exc)) from exc
        assistant = {
            "_id": new_id(),
            "appId": app_id,
            "role": "assistant",
            "content": reply,
            "createdAt": stamp + 1,
        }
        messages(self.settings).insert_many([user_turn, assistant])
        apps(self.settings).update_one(
            {"_id": app_id},
            {"$set": {"chat.hermesSessionId": session, "updatedAt": now_ms()}},
        )
        resp.status = falcon.HTTP_201
        resp.media = {"message": public_turn(assistant), "sessionId": session}
