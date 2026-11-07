"""Product routes backed by Mongo. Every request belongs to the seeded user."""

from __future__ import annotations

import copy
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
from baze_api.db import apps, drafts, users
from baze_api.http import now_ms, read_json
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


def _shelf(settings: Settings, status: str | None, *, shared: bool) -> dict:
    user = signed_in_user(settings)
    query: dict = {"ownerId": user["_id"]}
    query["sharedBy"] = {"$ne": None} if shared else None
    if status and status != "all":
        query["status"] = status
    documents = list(apps(settings).find(query).sort("sort", 1))
    own = list(apps(settings).find({"ownerId": user["_id"], "sharedBy": None}))
    shared_docs = list(apps(settings).find({"ownerId": user["_id"], "sharedBy": {"$ne": None}}))
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
            for document in apps(self.settings).find({"ownerId": user["_id"], "sharedBy": None})
            if document.get("draftKey")
        }
        featured = [public_app(owned[key]) for key in FEATURED_KEYS if key in owned]
        own_count = apps(self.settings).count_documents({"ownerId": user["_id"], "sharedBy": None})
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
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @_guard
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        resp.media = _shelf(self.settings, req.get_param("status"), shared=False)


class SharedShelf:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @_guard
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        resp.media = _shelf(self.settings, None, shared=True)


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
