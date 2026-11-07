"""Product routes backed by Mongo. Every request belongs to the seeded user."""

from __future__ import annotations

import copy
import json
import re

import falcon
from pymongo.errors import PyMongoError

from baze_api.catalog import (
    FEATURED_KEYS,
    HOME_COPY,
    PRESETS,
    PROMPT_DRAFTS,
    SHELF_COPY,
    SUGGESTIONS,
    USER_EMAIL,
    live_path,
    preset,
)
from baze_api.db import apps, drafts, messages, users
from baze_api.hermes import HermesClient, HermesError
from baze_api.http import clean_content, new_id, now_ms, read_json
from baze_api.runtime import public_turn
from baze_api.proxy import InferenceError, complete_chat
from baze_api.provisioner import (
    PowerError,
    begin_hosted_app,
    boot_hosted_app,
    build_in_container,
    delete_shelf_app,
    start_catalog_app,
    stop_catalog_app,
)
from baze_api.settings import Settings

APP_ID_RE = re.compile(r"^[0-9a-f]{32}$")
DRAFT_ID_RE = re.compile(r"^[A-Za-z0-9-]{1,80}$")
PUBLIC_APP_FIELDS = (
    "slug",
    "name",
    "summary",
    "detail",
    "status",
    "statusLabel",
    "labels",
    "preset",
    "color",
    "icon",
    "isNew",
    "badge",
    "progress",
    "path",
    "external",
    "sharedBy",
)
DRAFT_FIELDS = (
    "kicker",
    "messages",
    "selectedPreset",
    "briefTitle",
    "brief",
    "note",
    "composerPlaceholder",
    "makeLabel",
    "build",
    "ready",
)


def _guard(fn):
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except falcon.HTTPError:
            raise
        except PyMongoError as exc:
            raise falcon.HTTPServiceUnavailable(description="Database unavailable") from exc

    return wrapper


def signed_in_user(settings: Settings) -> dict:
    document = users(settings).find_one({"email": USER_EMAIL})
    if document is None:
        raise falcon.HTTPServiceUnavailable(description="Signed-in user is missing")
    return document


def public_app(document: dict) -> dict:
    payload = {"id": document["_id"]}
    for field in PUBLIC_APP_FIELDS:
        payload[field] = document.get(field)
    payload["runnable"] = bool((document.get("runtime") or {}).get("containerName"))
    payload["deletable"] = not document.get("sharedBy")
    payload["statusError"] = document.get("statusError")
    return payload


def public_draft(document: dict) -> dict:
    payload = {"id": document["_id"]}
    for field in DRAFT_FIELDS:
        payload[field] = document.get(field)
    return payload


def _parse_app_id(app_id: str) -> str:
    if not APP_ID_RE.match(app_id):
        raise falcon.HTTPNotFound(description="App not found")
    return app_id


def _parse_draft_id(draft_id: str) -> str:
    if not DRAFT_ID_RE.match(draft_id):
        raise falcon.HTTPNotFound(description="Draft not found")
    return draft_id


def _catalog(user_id: str, *, shared: bool | None = None) -> dict:
    query: dict = {"ownerId": user_id, "kind": {"$ne": "runtime"}}
    if shared is True:
        query["sharedBy"] = {"$ne": None}
    elif shared is False:
        query["sharedBy"] = None
    return query


def _shelf(settings: Settings, status: str | None, *, shared: bool) -> dict:
    user = signed_in_user(settings)
    query = _catalog(user["_id"], shared=shared)
    if status and status != "all":
        query["status"] = status
    documents = list(apps(settings).find(query).sort("sort", 1))
    own = list(apps(settings).find(_catalog(user["_id"], shared=False)))
    shared_docs = list(apps(settings).find(_catalog(user["_id"], shared=True)))
    live = sum(1 for app in own if app.get("status") == "live")
    shared_count = len(shared_docs)
    page = {
        "title": SHELF_COPY["sharedTitle"] if shared else SHELF_COPY["title"],
        "summary": (
            f"{shared_count} apps people shared with you"
            if shared
            else f"{len(own)} apps on your shelf · {live} live"
        ),
        "makeLabel": SHELF_COPY["makeLabel"],
        "filters": [] if shared else SHELF_COPY["filters"],
        "empty": SHELF_COPY["sharedEmpty"] if shared else SHELF_COPY["empty"],
        "apps": [public_app(document) for document in documents],
        "sharedTitle": SHELF_COPY["sharedTitle"],
        "sharedSummary": f"{shared_count} apps people shared with you",
        "shared": [] if shared else [public_app(document) for document in shared_docs if not status or status == "all" or document.get("status") == status],
    }
    return page


def _load_draft(settings: Settings, draft_id: str, user_id: str) -> dict:
    document = drafts(settings).find_one({"_id": _parse_draft_id(draft_id), "ownerId": user_id})
    if document is None:
        raise falcon.HTTPNotFound(description="Draft not found")
    return document


def _plain_workspace(app: dict) -> dict:
    panel = {
        "title": app["name"],
        "empty": app["summary"],
        "stats": [],
        "columns": [],
        "rows": [],
        "chartTitle": "",
        "chartStart": "",
        "chartEnd": "",
        "bars": [],
    }
    return {
        "slug": app["slug"],
        "name": app["name"],
        "preset": app["preset"],
        "color": app["color"],
        "icon": app["icon"],
        "primaryAction": "Open",
        "secondaryAction": "Export",
        "madeWithLabel": "Made with baze",
        "madeWithPath": "/",
        "sections": [{"id": "home", "label": "Home", "panel": panel}],
    }


def _blank_draft(prompt: str, draft_id: str) -> dict:
    look = PRESETS[0]
    name = (prompt.split(".")[0] or prompt)[:42]
    return {
        "_id": draft_id,
        "kicker": "Step 1 of 3 · Describe",
        "selectedPreset": look["id"],
        "briefTitle": "What I’m making",
        "composerPlaceholder": "Tell me what to change…",
        "makeLabel": "Looks right, make it",
        "note": "You’ll see screenshots here while we shape it. Once it’s made, your app opens in its own browser tab.",
        "brief": [
            {"label": "Name", "value": name, "swatch": None},
            {"label": "Its one job", "value": "One job, decided in the chat", "swatch": None},
            {"label": "Look", "value": look["label"], "swatch": look["color"]},
            {"label": "Talks to", "value": "Your email only", "swatch": None},
        ],
        "messages": [
            {"id": f"{draft_id}-you", "role": "you", "text": prompt, "shots": [], "askPreset": False},
            {
                "id": f"{draft_id}-baze",
                "role": "baze",
                "text": f"Here’s a first look. {name} stays one job, and we’ll shape the views in this chat.",
                "shots": [{"id": "first", "name": "First view", "accent": look["color"]}],
                "askPreset": True,
            },
        ],
        "build": {
            "kicker": "Step 2 of 3 · Making it",
            "title": f"{name} is taking shape",
            "subtitle": "About a minute left. You can close this page, we’ll email you when it’s ready.",
            "steps": [
                {"id": "write", "label": "Writing it", "state": "done", "progress": 100},
                {"id": "try", "label": "Trying it safely", "state": "active", "progress": 40},
                {"id": "check", "label": "Checking it’s safe", "state": "waiting", "progress": 0},
                {"id": "ready", "label": "Ready for you", "state": "waiting", "progress": 0},
            ],
            "noticeTitle": None,
            "noticeBody": None,
            "waitingTitle": "While you wait",
            "waitingBody": "We’re trying it inside a sealed space that can only reach your email.",
        },
        "ready": {
            "kicker": "Step 3 of 3 · Ready",
            "title": f"{name} is ready",
            "address": f"baze.app/{draft_id} · {look['label']} look",
            "color": look["color"],
            "icon": "lucideReceipt",
            "facts": [
                {"label": "Its one job", "value": "One job, decided in the chat", "swatch": None},
                {"label": "Look", "value": look["label"], "swatch": look["color"]},
                {"label": "Talks to", "value": "Your email only", "swatch": None},
            ],
            "openLabel": "Open your app",
            "openPath": "/",
            "openHint": "It opens in its own browser tab. Baze stays here.",
            "safetyTitle": "Safety check",
            "checks": [
                {"id": "works", "tone": "pass", "text": "It works. We tried the one job inside the safe space."},
                {"id": "email", "tone": "pass", "text": "It only talks to your email."},
            ],
            "publishLabel": "Put it live",
            "shareLabel": "Share the safety check",
        },
    }


class Account:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @_guard
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        user = signed_in_user(self.settings)
        resp.media = {
            "name": user["name"],
            "initials": user["initials"],
            "color": user["color"],
            "ink": user["ink"],
            "email": user["email"],
        }


class Home:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @_guard
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        user = signed_in_user(self.settings)
        owned = {
            document["draftKey"]: document
            for document in apps(self.settings).find(_catalog(user["_id"], shared=False))
            if document.get("draftKey")
        }
        featured = [public_app(owned[key]) for key in FEATURED_KEYS if key in owned]
        own_count = apps(self.settings).count_documents(_catalog(user["_id"], shared=False))
        resp.media = {
            **HOME_COPY,
            "seeAllLabel": f"See all {own_count}",
            "suggestions": SUGGESTIONS,
            "featured": featured,
        }


class Presets:
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        resp.media = PRESETS


class Shelf:
    def __init__(self, settings: Settings, services=None) -> None:
        self.settings = settings
        self.services = services

    @_guard
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        resp.media = _shelf(self.settings, req.get_param("status"), shared=False)


class SharedShelf:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @_guard
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        resp.media = _shelf(self.settings, None, shared=True)


class AppPower:
    def __init__(self, settings: Settings, runner, healthy) -> None:
        self.settings = settings
        self.runner = runner
        self.healthy = healthy

    @_guard
    def on_post(self, req: falcon.Request, resp: falcon.Response, app_id: str, action: str) -> None:
        try:
            if action == "start":
                document = start_catalog_app(self.settings, _parse_app_id(app_id), self.runner, self.healthy)
            elif action == "stop":
                document = stop_catalog_app(self.settings, _parse_app_id(app_id), self.runner)
            else:
                raise falcon.HTTPNotFound(description="App not found")
        except PowerError as exc:
            if exc.code == "missing":
                raise falcon.HTTPNotFound(description=str(exc)) from exc
            if exc.code == "not_runnable":
                raise falcon.HTTPConflict(description=str(exc)) from exc
            raise falcon.HTTPServiceUnavailable(description=str(exc)) from exc
        resp.media = public_app(document)


class AppPrompt:
    """Hand a prompt to the app container. The harness calls back here for the model."""

    def __init__(self, settings: Settings, hermes: HermesClient) -> None:
        self.settings = settings
        self.hermes = hermes

    @_guard
    def on_post(self, req: falcon.Request, resp: falcon.Response, app_id: str) -> None:
        user = signed_in_user(self.settings)
        document = apps(self.settings).find_one(
            {"_id": _parse_app_id(app_id), "ownerId": user["_id"], "kind": {"$ne": "runtime"}}
        )
        if document is None:
            raise falcon.HTTPNotFound(description="App not found")
        runtime = document.get("runtime") or {}
        port = runtime.get("harnessPort")
        key = runtime.get("apiServerKey")
        if document.get("status") != "live" or not isinstance(port, int) or not key:
            raise falcon.HTTPConflict(description="This app is not ready for a prompt")
        content = clean_content(read_json(req).get("content"))
        session_id = (document.get("chat") or {}).get("hermesSessionId")
        try:
            reply, session = self.hermes.complete(
                base_url=f"http://127.0.0.1:{port}",
                api_key=key,
                content=content,
                session_id=session_id,
            )
        except HermesError as exc:
            raise falcon.HTTPBadGateway(description=str(exc)) from exc
        stamp = now_ms()
        user_turn = {"_id": new_id(), "appId": document["_id"], "role": "user", "content": content, "createdAt": stamp}
        assistant = {
            "_id": new_id(),
            "appId": document["_id"],
            "role": "assistant",
            "content": reply,
            "createdAt": stamp + 1,
        }
        messages(self.settings).insert_many([user_turn, assistant])
        apps(self.settings).update_one(
            {"_id": document["_id"]},
            {"$set": {"chat.hermesSessionId": session, "updatedAt": stamp}},
        )
        resp.media = {"reply": reply, "message": public_turn(assistant)}


class AppManage:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @_guard
    def on_get(self, req: falcon.Request, resp: falcon.Response, app_id: str) -> None:
        user = signed_in_user(self.settings)
        document = apps(self.settings).find_one(
            {"_id": _parse_app_id(app_id), "ownerId": user["_id"], "kind": {"$ne": "runtime"}}
        )
        if document is None:
            raise falcon.HTTPNotFound(description="App not found")
        runtime = document.get("runtime") or {}
        turns = messages(self.settings).find({"appId": document["_id"]}).sort("createdAt", 1)
        resp.media = {
            "id": document["_id"],
            "name": document.get("name"),
            "summary": document.get("summary"),
            "status": document.get("status"),
            "statusLabel": document.get("statusLabel") or "",
            "createdAt": document.get("createdAt"),
            "lastRunAt": runtime.get("lastStartedAt"),
            "path": document.get("path"),
            "color": document.get("color"),
            "icon": document.get("icon"),
            "runnable": bool(runtime.get("containerName")),
            "deletable": not document.get("sharedBy"),
            "statusError": document.get("statusError"),
            "boxReady": bool(runtime.get("boxReady")),
            "steps": (document.get("build") or {}).get("steps") or [],
            "messages": [public_turn(turn) for turn in turns],
        }


class AppRecord:
    def __init__(self, settings: Settings, services) -> None:
        self.settings = settings
        self.services = services

    @_guard
    def on_delete(self, req: falcon.Request, resp: falcon.Response, app_id: str) -> None:
        try:
            delete_shelf_app(self.settings, _parse_app_id(app_id), self.services.runner)
        except PowerError as exc:
            if exc.code == "missing":
                raise falcon.HTTPNotFound(description=str(exc)) from exc
            raise falcon.HTTPConflict(description=str(exc)) from exc
        resp.status = falcon.HTTP_204


class Workspace:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @_guard
    def on_get(self, req: falcon.Request, resp: falcon.Response, app_id: str) -> None:
        user = signed_in_user(self.settings)
        document = apps(self.settings).find_one({"_id": _parse_app_id(app_id), "ownerId": user["_id"]})
        if document is None:
            raise falcon.HTTPNotFound(description="App not found")
        if document.get("workspace"):
            workspace = copy.deepcopy(document["workspace"])
            workspace["preset"] = document["preset"]
            workspace["color"] = document["color"]
        else:
            workspace = _plain_workspace(document)
        resp.media = workspace


class Drafts:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @_guard
    def on_post(self, req: falcon.Request, resp: falcon.Response) -> None:
        user = signed_in_user(self.settings)
        body = read_json(req)
        prompt = body.get("prompt") if isinstance(body.get("prompt"), str) else ""
        lowered = prompt.lower()
        for candidate in PROMPT_DRAFTS:
            if candidate["match"] in lowered:
                existing = drafts(self.settings).find_one({"_id": candidate["id"], "ownerId": user["_id"]})
                if existing is not None:
                    resp.media = public_draft(existing)
                    return
        text = prompt.strip() or "Something new for the shelf"
        count = drafts(self.settings).count_documents({"ownerId": user["_id"]})
        draft_id = f"draft-{count + 1}"
        while drafts(self.settings).find_one({"_id": draft_id}, {"_id": 1}):
            count += 1
            draft_id = f"draft-{count + 1}"
        stamp = now_ms()
        document = _blank_draft(text, draft_id)
        document["ownerId"] = user["_id"]
        document["createdAt"] = stamp
        document["updatedAt"] = stamp
        drafts(self.settings).insert_one(document)
        resp.status = falcon.HTTP_201
        resp.media = public_draft(document)


class Draft:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @_guard
    def on_get(self, req: falcon.Request, resp: falcon.Response, draft_id: str) -> None:
        user = signed_in_user(self.settings)
        resp.media = public_draft(_load_draft(self.settings, draft_id, user["_id"]))

    @_guard
    def on_patch(self, req: falcon.Request, resp: falcon.Response, draft_id: str) -> None:
        user = signed_in_user(self.settings)
        document = _load_draft(self.settings, draft_id, user["_id"])
        body = read_json(req)
        preset_id = body.get("preset") if isinstance(body.get("preset"), str) else ""
        try:
            look = preset(preset_id)
        except KeyError:
            resp.media = public_draft(document)
            return
        document["selectedPreset"] = look["id"]
        document["brief"] = [
            {**row, "value": look["label"], "swatch": look["color"]} if row.get("label") == "Look" else row
            for row in document.get("brief", [])
        ]
        ready = document.get("ready") or {}
        address = ready.get("address") or ""
        ready = {
            **ready,
            "color": look["color"],
            "address": re.sub(r"·.*", f"· {look['label']} look", address),
            "facts": [
                {**row, "value": look["label"], "swatch": look["color"]} if row.get("label") == "Look" else row
                for row in ready.get("facts", [])
            ],
        }
        document["ready"] = ready
        for message in document.get("messages", []):
            message["shots"] = [{**shot, "accent": look["color"]} for shot in message.get("shots", [])]
        drafts(self.settings).replace_one({"_id": document["_id"]}, document)
        apps(self.settings).update_one(
            {"ownerId": user["_id"], "draftKey": document["_id"]},
            {"$set": {"preset": look["id"], "color": look["color"], "updatedAt": now_ms()}},
        )
        resp.media = public_draft(document)


class DraftMessages:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @_guard
    def on_post(self, req: falcon.Request, resp: falcon.Response, draft_id: str) -> None:
        user = signed_in_user(self.settings)
        document = _load_draft(self.settings, draft_id, user["_id"])
        body = read_json(req)
        text = body.get("text") if isinstance(body.get("text"), str) else ""
        text = text.strip()
        if not text:
            resp.media = public_draft(document)
            return
        messages = document.get("messages", [])
        next_index = len(messages) + 1
        messages.extend(
            [
                {
                    "id": f"{document['_id']}-{next_index}",
                    "role": "you",
                    "text": text,
                    "shots": [],
                    "askPreset": False,
                },
                {
                    "id": f"{document['_id']}-{next_index + 1}",
                    "role": "baze",
                    "text": "Noted. I’ll keep that in the app, and the screenshots stay the ones you can see.",
                    "shots": [],
                    "askPreset": False,
                },
            ]
        )
        document["messages"] = messages
        document["updatedAt"] = now_ms()
        drafts(self.settings).replace_one({"_id": document["_id"]}, document)
        resp.media = public_draft(document)


class DraftPublish:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @_guard
    def on_post(self, req: falcon.Request, resp: falcon.Response, draft_id: str) -> None:
        user = signed_in_user(self.settings)
        document = _load_draft(self.settings, draft_id, user["_id"])
        app = apps(self.settings).find_one({"ownerId": user["_id"], "draftKey": document["_id"]})
        if app is not None:
            apps(self.settings).update_one(
                {"_id": app["_id"]},
                {
                    "$set": {
                        "status": "live",
                        "statusLabel": "Live",
                        "progress": None,
                        "badge": "New",
                        "isNew": True,
                        "labels": [
                            {"text": "New", "tone": "secondary"},
                            {"text": "Live", "tone": "success"},
                        ],
                        "path": live_path(app["_id"]),
                        "external": True,
                        "updatedAt": now_ms(),
                    }
                },
            )
        resp.media = public_draft(document)


class DraftShare:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @_guard
    def on_post(self, req: falcon.Request, resp: falcon.Response, draft_id: str) -> None:
        user = signed_in_user(self.settings)
        _load_draft(self.settings, draft_id, user["_id"])
        resp.media = {"message": "The safety check link is ready to share."}


CREATOR_ID = "creator"
SKETCH_ID = "creator-sketch"
SKETCH_ICONS = (
    "lucideBookOpen",
    "lucideBriefcase",
    "lucideCalculator",
    "lucideCalendarDays",
    "lucideCamera",
    "lucideChefHat",
    "lucideClock",
    "lucideCoffee",
    "lucideDumbbell",
    "lucideFlower2",
    "lucideGamepad2",
    "lucideHeart",
    "lucideHouse",
    "lucideLeaf",
    "lucideList",
    "lucideMail",
    "lucideMapPin",
    "lucideMusic",
    "lucideNotebookPen",
    "lucidePackage",
    "lucidePawPrint",
    "lucidePlane",
    "lucideReceipt",
    "lucideShoppingCart",
    "lucideStickyNote",
    "lucideTrendingUp",
    "lucideUsers",
    "lucideUtensils",
    "lucideWallet",
    "lucideBike",
)
RECEPTION = (
    "You are the reception at baze. The person is deciding what app to make. "
    "Help them settle the requirements in a few short turns. "
    "Ask only what changes the app. Do not write the app, and do not mention how it is hosted. "
    "If they name a color, remember it. Do not suggest one yourself. "
    "When the requirements are clear, tell them they can press Make. "
    "Reply in plain sentences, without markdown."
)
PLAN_REQUEST = "List 3 to 6 short steps to build this app. One step per line. No numbers and no extra text."
SKETCH_SYSTEM = (
    "You keep the app sketch for baze. Reply with only a JSON object with keys name, summary, icon, and color. "
    "name is a short title. summary is one sentence about what the app does, not its color or icon. "
    "icon is one of: "
    + ", ".join(SKETCH_ICONS)
    + ". color is a #hex only when the person has named a color, otherwise an empty string. "
    "Use empty strings for anything not yet clear. "
    "Change earlier guesses when the person changes their mind. Do not invent details."
)


def _ask_model(settings: Settings, services, messages: list[dict]) -> str:
    infer = getattr(services, "infer", None) if services is not None else None
    if infer is not None:
        return infer(messages)
    return complete_chat(settings, messages)


def _creator_turns(settings: Settings) -> list[dict]:
    query = {"appId": CREATOR_ID, "role": {"$in": ["user", "assistant"]}}
    return list(messages(settings).find(query).sort("createdAt", 1))


def _blank_sketch() -> dict:
    return {"name": "", "summary": "", "icon": "", "color": ""}


def _load_sketch(settings: Settings) -> dict:
    document = messages(settings).find_one({"_id": SKETCH_ID, "role": "sketch"}) or {}
    icon = document.get("icon") or ""
    if icon not in SKETCH_ICONS:
        icon = ""
    return {
        "name": (document.get("name") or "")[:48],
        "summary": (document.get("summary") or "")[:140],
        "icon": icon,
        "color": _hex_color(document.get("color")),
    }


def _save_sketch(settings: Settings, sketch: dict) -> None:
    messages(settings).update_one(
        {"_id": SKETCH_ID},
        {
            "$set": {
                "appId": CREATOR_ID,
                "role": "sketch",
                "name": sketch["name"],
                "summary": sketch["summary"],
                "icon": sketch["icon"],
                "color": sketch["color"],
                "content": "",
                "createdAt": now_ms(),
            }
        },
        upsert=True,
    )


def _parse_sketch(text: str) -> dict | None:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    name = data.get("name") if isinstance(data.get("name"), str) else ""
    summary = data.get("summary") if isinstance(data.get("summary"), str) else ""
    icon = data.get("icon") if isinstance(data.get("icon"), str) else ""
    icon = icon.strip()
    if icon not in SKETCH_ICONS:
        icon = ""
    name = " ".join(name.split())[:48]
    if name.lower() in {"unnamed", "untitled", "app"}:
        name = ""
    return {
        "name": name,
        "summary": " ".join(summary.split())[:140],
        "icon": icon,
        "color": _hex_color(data.get("color")),
    }


def _hex_color(value: object) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", text):
        return text.lower()
    return ""


def _refresh_sketch(settings: Settings, services, turns: list[dict]) -> dict:
    history = [{"role": "system", "content": SKETCH_SYSTEM}]
    history.extend({"role": turn["role"], "content": turn["content"]} for turn in turns)
    history.append({"role": "user", "content": "Update the app sketch."})
    try:
        parsed = _parse_sketch(_ask_model(settings, services, history))
    except InferenceError:
        return _load_sketch(settings)
    if parsed is None:
        return _load_sketch(settings)
    _save_sketch(settings, parsed)
    return parsed


def _creator_media(settings: Settings) -> dict:
    return {
        "messages": [public_turn(turn) for turn in _creator_turns(settings)],
        "sketch": _load_sketch(settings),
    }


def _plan_lines(text: str) -> list[str]:
    lines = []
    for raw in text.splitlines():
        cleaned = raw.strip().lstrip("-*").strip()
        cleaned = cleaned.lstrip("0123456789.").strip()
        if cleaned:
            lines.append(cleaned[:80])
    return lines[:6] or ["Write the app", "Save it in the box"]


def _provision_steps(plan: list[str]) -> list[dict]:
    steps = [
        {"id": "create", "label": "Creating the container", "state": "waiting"},
        {"id": "start", "label": "Starting the box", "state": "waiting"},
        {"id": "harness", "label": "Opening the harness", "state": "waiting"},
    ]
    steps.extend({"id": f"plan-{index}", "label": label, "state": "waiting"} for index, label in enumerate(plan))
    return steps


class Creator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @_guard
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        signed_in_user(self.settings)
        resp.media = _creator_media(self.settings)


class CreatorMessages:
    def __init__(self, settings: Settings, services) -> None:
        self.settings = settings
        self.services = services

    @_guard
    def on_post(self, req: falcon.Request, resp: falcon.Response) -> None:
        signed_in_user(self.settings)
        content = clean_content(read_json(req).get("content"))
        prior = _creator_turns(self.settings)
        user_turn = {"_id": new_id(), "appId": CREATOR_ID, "role": "user", "content": content, "createdAt": now_ms()}
        messages(self.settings).insert_one(user_turn)
        history = [{"role": "system", "content": RECEPTION}]
        history.extend({"role": turn["role"], "content": turn["content"]} for turn in prior)
        history.append({"role": "user", "content": content})
        try:
            reply = _ask_model(self.settings, self.services, history)
        except InferenceError as exc:
            messages(self.settings).delete_one({"_id": user_turn["_id"]})
            raise falcon.HTTPBadGateway(description=str(exc)) from exc
        messages(self.settings).insert_one(
            {"_id": new_id(), "appId": CREATOR_ID, "role": "assistant", "content": reply, "createdAt": now_ms()}
        )
        _refresh_sketch(self.settings, self.services, _creator_turns(self.settings))
        resp.media = _creator_media(self.settings)


class CreatorReset:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @_guard
    def on_post(self, req: falcon.Request, resp: falcon.Response) -> None:
        signed_in_user(self.settings)
        messages(self.settings).delete_many({"appId": CREATOR_ID})
        resp.media = _creator_media(self.settings)


class CreatorMake:
    def __init__(self, settings: Settings, services) -> None:
        self.settings = settings
        self.services = services

    @_guard
    def on_post(self, req: falcon.Request, resp: falcon.Response) -> None:
        if self.services is None:
            raise falcon.HTTPServiceUnavailable(description="Apps cannot be created right now")
        user = signed_in_user(self.settings)
        turns = _creator_turns(self.settings)
        prompt = next((turn["content"] for turn in turns if turn.get("role") == "user"), "")
        if not prompt:
            raise falcon.HTTPBadRequest(description="Tell the reception what to make first")
        plan_messages = [
            {"role": "system", "content": "You write build plans. Reply with one short step per line and nothing else."},
            *({"role": turn["role"], "content": turn["content"]} for turn in turns),
            {"role": "user", "content": PLAN_REQUEST},
        ]
        try:
            plan = _plan_lines(_ask_model(self.settings, self.services, plan_messages))
        except InferenceError as exc:
            raise falcon.HTTPBadGateway(description=str(exc)) from exc
        document = begin_hosted_app(self.settings, user["_id"], prompt)
        app_id = document["_id"]
        sketch = _load_sketch(self.settings)
        named = {}
        if sketch["name"]:
            named["name"] = sketch["name"]
        if sketch["summary"]:
            named["summary"] = sketch["summary"]
            named["detail"] = sketch["summary"]
        if sketch["icon"]:
            named["icon"] = sketch["icon"]
        if sketch["color"]:
            named["color"] = sketch["color"]
        if named:
            apps(self.settings).update_one({"_id": app_id}, {"$set": named})
        stamp = now_ms()
        copies = [
            {
                "_id": new_id(),
                "appId": app_id,
                "role": turn["role"],
                "content": turn["content"],
                "createdAt": stamp + index,
            }
            for index, turn in enumerate(turns)
        ]
        if copies:
            messages(self.settings).insert_many(copies)
        messages(self.settings).delete_many({"appId": CREATOR_ID})
        steps = _provision_steps(plan)
        apps(self.settings).update_one({"_id": app_id}, {"$set": {"build.steps": steps, "prompt": prompt}})
        self.services.spawn(
            lambda app_id=app_id: boot_hosted_app(
                self.settings, app_id, self.services.runner, self.services.healthy
            )
        )
        resp.status = falcon.HTTP_201
        resp.media = {"id": app_id, "steps": steps, "boxReady": False}


class AppBuild:
    def __init__(self, settings: Settings, services) -> None:
        self.settings = settings
        self.services = services

    @_guard
    def on_post(self, req: falcon.Request, resp: falcon.Response, app_id: str) -> None:
        signed_in_user(self.settings)
        app_id = _parse_app_id(app_id)
        document = apps(self.settings).find_one({"_id": app_id, "kind": {"$ne": "runtime"}})
        if document is None:
            raise falcon.HTTPNotFound(description="App not found")
        if not (document.get("runtime") or {}).get("boxReady"):
            raise falcon.HTTPConflict(description="The container is not ready")
        if document.get("status") != "live":
            claimed = apps(self.settings).update_one(
                {"_id": app_id, "runtime.buildStarted": {"$ne": True}},
                {"$set": {"runtime.buildStarted": True, "updatedAt": now_ms()}},
            )
            if claimed.modified_count and self.services is not None:
                self.services.spawn(
                    lambda app_id=app_id: build_in_container(
                        self.settings,
                        app_id,
                        self.services.runner,
                        self.services.hermes,
                        self.services.healthy,
                    )
                )
        resp.status = falcon.HTTP_202
        resp.media = {"id": app_id}
