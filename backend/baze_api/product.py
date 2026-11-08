"""Product routes backed by Mongo. Every request belongs to the seeded user."""

from __future__ import annotations

import copy
import json
import logging
import re
from pathlib import Path

import falcon
from pymongo.errors import PyMongoError

from baze_api.activity import mark_working, working_turn
from baze_api.boxes import BOXES, box_copy, box_prompt, known_profile, recommend_profile, settle_box_prompt, suggestion_reason

log = logging.getLogger("baze.product")
from baze_api.catalog import (
    ACCOUNT_EMAILS,
    ACCOUNTS,
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
from baze_api.identity import current_email
from baze_api.chart import ask_chart, public_chart
from baze_api.db import apps, drafts, messages, users
from baze_api.hermes import HermesClient, HermesError
from baze_api.http import clean_content, new_id, now_ms, read_json
from baze_api.limits import TooMany, admin_code_matches, begin_start, release_hosted_reservation, release_turn, reserve_hosted
from baze_api.runtime import public_turn
from baze_api.proxy import InferenceError, ModelLimitError, complete_chat
from baze_api.provisioner import (
    builder_voice,
    profile_access,
    PowerError,
    begin_hosted_app,
    boot_hosted_app,
    build_in_container,
    access_instruction,
    apply_review,
    delete_shelf_app,
    busy_progress,
    record_progress,
    _activate_plan,
    _hold,
    _mark_plan_done,
    _park_plan,
    _plan_stopped,
    _stop_plan,
    start_catalog_app,
    stop_catalog_app,
    stop_idle_progress,
)
from baze_api.supervisor import (
    apply_form,
    public_actions,
    public_allowlist,
    public_request,
    public_sites,
    revise_decision,
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
        except TooMany as exc:
            raise falcon.HTTPTooManyRequests(description=str(exc)) from exc
        except falcon.HTTPError:
            raise
        except PyMongoError as exc:
            raise falcon.HTTPServiceUnavailable(description="Database unavailable") from exc

    return wrapper


def signed_in_user(settings: Settings) -> dict:
    email = current_email() or USER_EMAIL
    if email not in ACCOUNT_EMAILS:
        email = USER_EMAIL
    document = users(settings).find_one({"email": email})
    if document is None:
        document = users(settings).find_one({"email": USER_EMAIL})
    if document is None:
        raise falcon.HTTPServiceUnavailable(description="Signed-in user is missing")
    return document


def _public_person(person: dict) -> dict:
    return {
        "name": person.get("name") or "",
        "email": person.get("email") or "",
        "initials": person.get("initials") or "",
        "color": person.get("color") or "#334155",
        "ink": person.get("ink") or "#ffffff",
    }


def public_account(settings: Settings, user: dict) -> dict:
    found = {
        person["email"]: person
        for person in users(settings).find({"email": {"$in": list(ACCOUNT_EMAILS)}})
    }
    accounts = [_public_person(found[account["email"]]) for account in ACCOUNTS if account["email"] in found]
    guest = next((account for account in ACCOUNTS if account["email"] != USER_EMAIL), None)
    return {
        "name": user["name"],
        "initials": user["initials"],
        "color": user["color"],
        "ink": user["ink"],
        "email": user["email"],
        "studio": user.get("studio") or "",
        "guest": user["email"] != USER_EMAIL,
        "guestAccount": {"name": guest["name"], "email": guest["email"]} if guest else None,
        "accounts": accounts,
    }


def _people(settings: Settings, document: dict) -> list[dict]:
    ids = [document.get("ownerId"), *(document.get("sharedWith") or [])]
    found = {person["_id"]: person for person in users(settings).find({"_id": {"$in": [item for item in ids if item]}})}
    people = []
    seen: set[str] = set()
    for user_id in ids:
        person = found.get(user_id)
        if person is None or person["_id"] in seen:
            continue
        seen.add(person["_id"])
        people.append(_public_person(person))
    return people


def public_app(document: dict, settings: Settings | None = None, *, shared_by: str | None = None) -> dict:
    payload = {"id": document["_id"]}
    for field in PUBLIC_APP_FIELDS:
        payload[field] = document.get(field)
    payload["runnable"] = bool((document.get("runtime") or {}).get("containerName"))
    payload["sharedBy"] = shared_by if shared_by is not None else document.get("sharedBy")
    payload["deletable"] = shared_by is None and not document.get("sharedBy")
    payload["statusError"] = document.get("statusError")
    payload["people"] = _people(settings, document) if settings is not None else []
    payload["demo"] = bool(document.get("demo"))
    payload["expiresAt"] = document.get("expiresAt")
    return payload


def _load_app(settings: Settings, app_id: str, user: dict, *, owner_only: bool) -> dict:
    document = apps(settings).find_one({"_id": _parse_app_id(app_id), "kind": {"$ne": "runtime"}})
    if document is None:
        raise falcon.HTTPNotFound(description="App not found")
    if document.get("ownerId") == user["_id"]:
        return document
    shared = user["_id"] in (document.get("sharedWith") or [])
    if shared and owner_only:
        raise falcon.HTTPForbidden(description="You can use this app. You can't change it.")
    if shared:
        return document
    raise falcon.HTTPNotFound(description="App not found")


def _share_rows(settings: Settings, document: dict, _user: dict) -> list[dict]:
    shared = set(document.get("sharedWith") or [])
    owner_id = document.get("ownerId")
    found = {
        person["email"]: person
        for person in users(settings).find({"email": {"$in": list(ACCOUNT_EMAILS)}})
    }
    rows = []
    for account in ACCOUNTS:
        person = found.get(account["email"])
        if person is None:
            continue
        rows.append(
            {
                **_public_person(person),
                "owner": person["_id"] == owner_id,
                "shared": person["_id"] == owner_id or person["_id"] in shared,
            }
        )
    return rows


def _shared_by_name(settings: Settings, document: dict, user: dict) -> str | None:
    if document.get("ownerId") == user["_id"]:
        return None
    owner = users(settings).find_one({"_id": document.get("ownerId")}, {"name": 1}) or {}
    return owner.get("name") or ""


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
    documents = [document for document in apps(settings).find(query).sort("sort", 1) if not _closed_check(document)]
    own = [document for document in apps(settings).find(_catalog(user["_id"], shared=False)) if not _closed_check(document)]
    check_docs = [
        document
        for document in apps(settings).find(_catalog(user["_id"], shared=False)).sort("sort", 1)
        if _closed_check(document)
    ]
    shared_query: dict = {
        "sharedWith": user["_id"],
        "ownerId": {"$ne": user["_id"]},
        "kind": {"$ne": "runtime"},
    }
    if status and status != "all":
        shared_query["status"] = status
    shared_docs = list(apps(settings).find(shared_query).sort("sort", 1))
    owner_names = {
        person["_id"]: person.get("name") or ""
        for person in users(settings).find(
            {"_id": {"$in": list({document.get("ownerId") for document in shared_docs})}},
            {"name": 1},
        )
    }
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
        "apps": [public_app(document, settings) for document in documents],
        "sharedTitle": SHELF_COPY["sharedTitle"],
        "sharedSummary": f"{shared_count} apps people shared with you",
        "shared": []
        if shared
        else [
            public_app(document, settings, shared_by=owner_names.get(document.get("ownerId")))
            for document in shared_docs
        ],
        "checks": [] if shared else [_public_check(document) for document in check_docs],
    }
    return page


def _closed_check(document: dict) -> bool:
    runtime = document.get("runtime") or {}
    return runtime.get("profile") == "quarantine" and document.get("verdict") in {"clear", "suspicious"}


def _public_check(document: dict) -> dict:
    return {
        "id": document["_id"],
        "name": document.get("name") or "Check",
        "specimen": document.get("specimen") or "No file was in the box.",
        "verdict": document.get("verdict"),
        "report": document.get("report") or "",
    }


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
        resp.media = public_account(self.settings, user)

    @_guard
    def on_post(self, req: falcon.Request, resp: falcon.Response) -> None:
        email = read_json(req).get("email")
        if email not in ACCOUNT_EMAILS:
            raise falcon.HTTPBadRequest(description="Choose an account on this shelf")
        user = users(self.settings).find_one({"email": email})
        if user is None:
            raise falcon.HTTPNotFound(description="Account not found")
        resp.set_cookie("baze_user", email, path="/", max_age=60 * 60 * 24 * 30, secure=False, http_only=True, same_site="Lax")
        resp.media = public_account(self.settings, user)


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
        featured = [public_app(owned[key], self.settings) for key in FEATURED_KEYS if key in owned]
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
        user = signed_in_user(self.settings)
        _load_app(self.settings, app_id, user, owner_only=True)
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
        resp.media = public_app(document, self.settings)


class AppPrompt:
    """Hand a prompt to the app container. The harness calls back here for the model."""

    def __init__(self, settings: Settings, hermes: HermesClient, services=None) -> None:
        self.settings = settings
        self.hermes = hermes
        self.services = services

    @_guard
    def on_post(self, req: falcon.Request, resp: falcon.Response, app_id: str) -> None:
        user = signed_in_user(self.settings)
        document = _load_app(self.settings, app_id, user, owner_only=True)
        runtime = document.get("runtime") or {}
        if runtime.get("profile") == "quarantine" and document.get("verdict") in {"clear", "suspicious"}:
            raise falcon.HTTPConflict(description="This check is finished.")
        port = runtime.get("harnessPort")
        key = runtime.get("apiServerKey")
        if document.get("status") not in {"live", "attention"} or not isinstance(port, int) or not key:
            raise falcon.HTTPConflict(description="This app is not ready for a prompt")
        body = read_json(req)
        content = clean_content(body.get("content"))
        attached = _attachment_paths(document, body.get("attachments"))
        profile = runtime.get("profile") if runtime.get("profile") in {"web", "data", "quarantine"} else None
        lead = profile_access(self.settings, profile)
        harness_content = f"{builder_voice()}\n\n{content}"
        if lead:
            harness_content = f"{lead}\n\n{harness_content}"
        if attached:
            harness_content = (
                f"{harness_content}\n\nThe person attached:\n" + "\n".join(attached) + "\nUse these files. Do not run them."
            )
        visible = content if not attached else content + "\n" + "\n".join(Path(item).name for item in attached)
        if body.get("to") == "supervisor" and not content:
            raise falcon.HTTPBadRequest(description="Write a message")
        begin_start(self.settings, req.remote_addr or "")
        try:
            if body.get("to") == "supervisor":
                stamp = now_ms()
                messages(self.settings).insert_one(
                    {"_id": new_id(), "appId": document["_id"], "role": "user", "content": content, "createdAt": stamp}
                )
                infer = getattr(self.services, "infer", None) if self.services is not None else None
                sentence = revise_decision(self.settings, document["_id"], content, infer)
                resp.media = {"reply": sentence}
                return
            session_id = (document.get("chat") or {}).get("hermesSessionId")
            stamp = now_ms()
            user_turn = {"_id": new_id(), "appId": document["_id"], "role": "user", "content": visible, "createdAt": stamp}
            messages(self.settings).insert_one(user_turn)
            progress_ids: list[str] = []
            finished = False
            try:
                with busy_progress(document["_id"]):
                    with working_turn(self.settings, document["_id"]):
                        try:
                            tasks = self._big_tasks(visible)
                            if tasks:
                                steps = [
                                    {"id": f"work-{user_turn['_id']}-{index}", "label": label, "state": "active"}
                                    for index, label in enumerate(tasks)
                                ]
                                record_progress(self.settings, document["_id"], steps, stamp + 1)
                                progress_ids = [step["id"] for step in steps]
                            reply, session = self.hermes.complete(
                                base_url=f"http://127.0.0.1:{port}",
                                api_key=key,
                                content=harness_content,
                                session_id=session_id,
                            )
                            if progress_ids:
                                messages(self.settings).update_many(
                                    {"appId": document["_id"], "role": "progress", "stepId": {"$in": progress_ids}},
                                    {"$set": {"state": "done"}},
                                )
                            finished = True
                        except HermesError:
                            raise
                        finally:
                            if progress_ids and not finished:
                                messages(self.settings).update_many(
                                    {"appId": document["_id"], "role": "progress", "stepId": {"$in": progress_ids}},
                                    {"$set": {"state": "stopped"}},
                                )
                        assistant = {
                            "_id": new_id(),
                            "appId": document["_id"],
                            "role": "assistant",
                            "content": reply,
                            "createdAt": stamp + len(progress_ids) + 1,
                        }
                        messages(self.settings).insert_one(assistant)
                        apps(self.settings).update_one(
                            {"_id": document["_id"]},
                            {"$set": {"chat.hermesSessionId": session, "updatedAt": stamp}},
                        )
                        ask_chart(
                            self.settings,
                            document["_id"],
                            self.hermes,
                            base_url=f"http://127.0.0.1:{port}",
                            api_key=key,
                            session_id=session,
                        )
                        _settle(self.settings, self.services, document)
                        resp.media = {"reply": reply, "message": public_turn(assistant)}
            except HermesError as exc:
                self._drop_attempt(document["_id"], user_turn["_id"], progress_ids)
                raise falcon.HTTPBadGateway(description=str(exc)) from exc
        finally:
            release_turn()

    def _big_tasks(self, brief: str) -> list[str]:
        infer = getattr(self.services, "infer", None) if self.services is not None else None
        if infer is None:
            return []
        try:
            text = infer(
                [
                    {
                        "role": "system",
                        "content": (
                            "You list the big tasks for a change to an existing app. "
                            "Reply with one short step per line and nothing else. "
                            "If the change is tiny, reply with none."
                        ),
                    },
                    {"role": "user", "content": brief},
                ]
            )
        except Exception:
            return []
        if not isinstance(text, str):
            return []
        return _task_lines(text)

    def _drop_attempt(self, app_id: str, user_id: str, progress_ids: list[str]) -> None:
        messages(self.settings).delete_one({"_id": user_id})
        if progress_ids:
            messages(self.settings).delete_many(
                {"appId": app_id, "role": "progress", "stepId": {"$in": progress_ids}}
            )


def _settle(settings: Settings, services, document: dict) -> None:
    infer = getattr(services, "infer", None) if services is not None else None
    runner = getattr(services, "runner", None) if services is not None else None
    apply_review(settings, document["_id"], runner, infer)


def resume_decided_plan(settings: Settings, services, app_id: str) -> None:
    """Pick up a plan that was parked for a decision, after that decision was already made."""
    document = apps(settings).find_one({"_id": app_id})
    if document is None:
        return
    runtime = document.get("runtime") or {}
    port = runtime.get("harnessPort")
    key = runtime.get("apiServerKey")
    if document.get("status") not in {"live", "attention"} or not isinstance(port, int) or not key:
        return
    _park_plan(settings, app_id)
    document = apps(settings).find_one({"_id": app_id}) or document
    steps = (document.get("build") or {}).get("steps") or []
    if not any(str(step.get("id", "")).startswith("plan") and step.get("state") == "waiting" for step in steps):
        return
    allowed, refused = public_allowlist(document)
    AppDecision(settings, services)._run(document, port, key, allowed, refused, now_ms())


class AppDecision:
    """The person picks a supervisor action. The harness applies that fix."""

    def __init__(self, settings: Settings, services) -> None:
        self.settings = settings
        self.services = services

    @_guard
    def on_post(self, req: falcon.Request, resp: falcon.Response, app_id: str) -> None:
        user = signed_in_user(self.settings)
        document = _load_app(self.settings, app_id, user, owner_only=True)
        runtime = document.get("runtime") or {}
        port = runtime.get("harnessPort")
        key = runtime.get("apiServerKey")
        if document.get("status") not in {"live", "attention"} or not isinstance(port, int) or not key:
            raise falcon.HTTPConflict(description="This app is not ready for a prompt")
        body = read_json(req)
        if body.get("allow") is True or body.get("allow") is False:
            if box_prompt(document) is None:
                raise falcon.HTTPConflict(description="There is nothing to decide.")
            try:
                sentence = settle_box_prompt(self.settings, document["_id"], bool(body.get("allow")))
            except RuntimeError as exc:
                raise falcon.HTTPBadGateway(description=str(exc)) from exc
            if body.get("allow") is True:
                self._start(document, port, key, [], [], now_ms())
            resp.media = {"reply": sentence}
            return
        hosts = body.get("hosts")
        if not isinstance(hosts, list) or len(hosts) > 40:
            raise falcon.HTTPBadRequest(description="Choose the sites to approve")
        stamp = now_ms()
        try:
            sentence, allowed, refused = apply_form(self.settings, document["_id"], hosts, stamp)
        except RuntimeError as exc:
            raise falcon.HTTPBadGateway(description=str(exc)) from exc
        self._start(document, port, key, allowed, refused, stamp + 1)
        resp.media = {"reply": sentence}

    def _start(self, document: dict, port: int, key: str, allowed: list[str], refused: list[str], at: int) -> None:
        """The decision is saved. The turn itself runs behind the request."""
        mark_working(self.settings, document["_id"])
        _activate_plan(self.settings, document["_id"])
        self.services.spawn(lambda: self._run(document, port, key, allowed, refused, at))

    def _run(self, document: dict, port: int, key: str, allowed: list[str], refused: list[str], at: int) -> None:
        """Hand the decision back as JSON. The builder is not told about the gate."""
        if not allowed and not refused:
            content = "You allowed it. Continue."
        else:
            content = json.dumps({"allowed": allowed, "refused": refused}, ensure_ascii=True)
            content = f"{content}\nContinue. Contact only allowed sites. Keep the app useful without the refused ones."
        session_id = (document.get("chat") or {}).get("hermesSessionId")
        try:
            with working_turn(self.settings, document["_id"]):
                with busy_progress(document["_id"]):
                    _activate_plan(self.settings, document["_id"])
                    try:
                        reply, session = self.services.hermes.complete(
                            base_url=f"http://127.0.0.1:{port}",
                            api_key=key,
                            content=content,
                            session_id=session_id,
                        )
                    except HermesError:
                        log.exception("App %s stopped before the turn finished", document["_id"])
                        _stop_plan(self.settings, document["_id"])
                        _hold(self.settings, document["_id"])
                        return
                    _mark_plan_done(self.settings, document["_id"])
                    if _plan_stopped(self.settings, document["_id"]):
                        _hold(self.settings, document["_id"])
                        return
                    messages(self.settings).insert_one(
                        {
                            "_id": new_id(),
                            "appId": document["_id"],
                            "role": "assistant",
                            "content": reply,
                            "createdAt": now_ms(),
                        }
                    )
                    apps(self.settings).update_one(
                        {"_id": document["_id"]},
                        {"$set": {"chat.hermesSessionId": session, "updatedAt": at}},
                    )
                    ask_chart(
                        self.settings,
                        document["_id"],
                        self.services.hermes,
                        base_url=f"http://127.0.0.1:{port}",
                        api_key=key,
                        session_id=session,
                    )
                    _settle(self.settings, self.services, document)
        except Exception:
            log.exception("App %s stopped before the turn finished", document["_id"])
            _stop_plan(self.settings, document["_id"])
            _hold(self.settings, document["_id"])


class AppManage:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @_guard
    def on_get(self, req: falcon.Request, resp: falcon.Response, app_id: str) -> None:
        user = signed_in_user(self.settings)
        document = _load_app(self.settings, app_id, user, owner_only=False)
        runtime = document.get("runtime") or {}
        turns = list(messages(self.settings).find({"appId": document["_id"]}).sort("createdAt", 1))
        steps = [dict(step) for step in (document.get("build") or {}).get("steps") or []]
        if steps and any(not isinstance(step.get("createdAt"), int) for step in steps):
            spoken = [turn for turn in turns if turn.get("role") in ("user", "assistant")]
            at = _steps_appeared_at(document, spoken)
            steps = [
                {**step, "createdAt": step["createdAt"] if isinstance(step.get("createdAt"), int) else at}
                for step in steps
            ]
            apps(self.settings).update_one({"_id": document["_id"]}, {"$set": {"build.steps": steps}})
        turns = _ensure_progress_chat(self.settings, document, steps, turns)
        stop_idle_progress(self.settings, document["_id"])
        if any(turn.get("role") == "progress" and turn.get("state") == "active" for turn in turns):
            fresh = {
                doc["_id"]: doc.get("state")
                for doc in messages(self.settings).find(
                    {"appId": document["_id"], "role": "progress"}, {"state": 1}
                )
            }
            turns = [
                {**turn, "state": fresh.get(turn["_id"], turn.get("state"))} if turn.get("role") == "progress" else turn
                for turn in turns
            ]
        flow, record = public_chart(document)
        allowed, closed = public_allowlist(document)
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
            "deletable": document.get("ownerId") == user["_id"] and not document.get("sharedBy"),
            "canPrompt": document.get("ownerId") == user["_id"] and not _closed_check(document),
            "sharedBy": _shared_by_name(self.settings, document, user),
            "shares": _share_rows(self.settings, document, user),
            "statusError": document.get("statusError"),
            "boxReady": bool(runtime.get("boxReady")),
            "working": bool(runtime.get("working")),
            "activity": runtime.get("activity") if isinstance(runtime.get("activity"), str) else "",
            "steps": steps,
            "messages": [public_turn(turn) for turn in turns],
            "flow": flow,
            "record": record,
            "actions": public_actions(document),
            "sites": public_sites(document),
            "request": public_request(document),
            "allowed": allowed,
            "closed": closed,
            "demo": bool(document.get("demo")),
            "expiresAt": document.get("expiresAt"),
            "box": box_copy(runtime["profile"]) if runtime.get("profile") in {"web", "data", "quarantine"} else None,
            "boxPrompt": (box_prompt(document) or {}).get("text") or None,
            "check": runtime.get("profile") == "quarantine",
        }


_FILE_LIMIT = 4 * 1024 * 1024


def _attachment_paths(document: dict, names: object) -> list[str]:
    if not names:
        return []
    if not isinstance(names, list) or len(names) > 4:
        raise falcon.HTTPBadRequest(description="Attach up to 4 files")
    data_dir = (document.get("runtime") or {}).get("dataDir")
    if not isinstance(data_dir, str) or not data_dir:
        raise falcon.HTTPConflict(description="This app is not ready for a file")
    root = Path(data_dir) / "uploads"
    paths = []
    for name in names:
        if not isinstance(name, str) or not name or name != Path(name).name or name in {".", ".."}:
            raise falcon.HTTPBadRequest(description="A file name is not valid")
        if not (root / name).is_file():
            raise falcon.HTTPBadRequest(description="A file is missing")
        paths.append(f"/opt/data/uploads/{name}")
    return paths


def _save_uploads(directory: Path, form) -> list[dict]:
    saved = []
    for part in form:
        if getattr(part, "name", None) != "file":
            continue
        if len(saved) >= 4:
            raise falcon.HTTPBadRequest(description="Attach up to 4 files")
        try:
            name = part.secure_filename
        except ValueError as exc:
            raise falcon.HTTPBadRequest(description="A file name is not valid") from exc
        if not name or name in {".", ".."} or "/" in name or "\\" in name:
            raise falcon.HTTPBadRequest(description="A file name is not valid")
        payload = part.stream.read(_FILE_LIMIT + 1)
        if len(payload) > _FILE_LIMIT:
            raise falcon.HTTPBadRequest(description="A file is too large")
        directory.mkdir(parents=True, exist_ok=True)
        target = _unused_path(directory, name)
        target.write_bytes(payload)
        saved.append({"name": target.name, "path": f"/opt/data/uploads/{target.name}"})
    if not saved:
        raise falcon.HTTPBadRequest(description="Choose a file")
    return saved


def _unused_path(directory: Path, name: str) -> Path:
    candidate = directory / name
    if not candidate.exists():
        return candidate
    stem = Path(name).stem
    suffix = Path(name).suffix
    for number in range(2, 20):
        candidate = directory / f"{stem}-{number}{suffix}"
        if not candidate.exists():
            return candidate
    raise falcon.HTTPConflict(description="That file is already here")


class AppFiles:
    """Store files the person brings into the app chat. Nothing here is executed."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @_guard
    def on_post(self, req: falcon.Request, resp: falcon.Response, app_id: str) -> None:
        user = signed_in_user(self.settings)
        document = _load_app(self.settings, app_id, user, owner_only=True)
        data_dir = (document.get("runtime") or {}).get("dataDir")
        if not isinstance(data_dir, str) or not data_dir:
            raise falcon.HTTPConflict(description="This app is not ready for a file")
        directory = Path(data_dir) / "uploads"
        try:
            saved = _save_uploads(directory, req.get_media())
        except falcon.MediaMalformedError as exc:
            raise falcon.HTTPBadRequest(description="The files were not readable") from exc
        resp.media = {"files": saved}


class AppRecord:
    def __init__(self, settings: Settings, services) -> None:
        self.settings = settings
        self.services = services

    @_guard
    def on_delete(self, req: falcon.Request, resp: falcon.Response, app_id: str) -> None:
        user = signed_in_user(self.settings)
        _load_app(self.settings, app_id, user, owner_only=True)
        code = read_json(req).get("code")
        if not isinstance(code, str) or not admin_code_matches(self.settings, code):
            raise falcon.HTTPForbidden(description="That code does not delete this app")
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
    "Do not name a box. "
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
    turns = _creator_turns(settings)
    text = "\n".join(turn.get("content") or "" for turn in turns if turn.get("role") == "user")
    sketch = _load_sketch(settings)
    profile = recommend_profile(text)
    return {
        "messages": [public_turn(turn) for turn in turns],
        "sketch": sketch,
        "boxes": [dict(box) for box in BOXES],
        "recommended": profile,
        "reason": suggestion_reason(profile, sketch.get("summary") or text),
    }


def _plan_lines(text: str) -> list[str]:
    return _task_lines(text)[:6] or ["Write the app", "Save it in the box"]


def _task_lines(text: str) -> list[str]:
    if text.strip().lower() in {"none", "nothing", "n/a"}:
        return []
    lines = []
    for raw in text.splitlines():
        cleaned = raw.strip().lstrip("-*").strip()
        cleaned = cleaned.lstrip("0123456789.").strip()
        if cleaned and cleaned.lower() not in {"none", "nothing"}:
            lines.append(cleaned[:80])
    return lines[:6]


def _ensure_progress_chat(settings: Settings, document: dict, steps: list[dict], turns: list[dict]) -> list[dict]:
    """Older builds kept tasks on the app. Copy them into the chat at the time they appeared."""
    if not steps or any(turn.get("role") == "progress" for turn in turns):
        return turns
    spoken = [turn for turn in turns if turn.get("role") in ("user", "assistant")]
    base = next((step.get("createdAt") for step in steps if isinstance(step.get("createdAt"), int)), None)
    at = base if isinstance(base, int) else _steps_appeared_at(document, spoken)
    record_progress(settings, document["_id"], steps, at)
    return list(messages(settings).find({"appId": document["_id"]}).sort("createdAt", 1))


def _provision_steps(plan: list[str], at: int) -> list[dict]:
    fixed = (
        ("create", "Creating the container"),
        ("start", "Starting the box"),
        ("harness", "Opening the harness"),
    )
    steps = [{"id": step_id, "label": label, "state": "waiting", "createdAt": at} for step_id, label in fixed]
    steps.extend(
        {"id": f"plan-{index}", "label": label, "state": "waiting", "createdAt": at}
        for index, label in enumerate(plan)
    )
    return steps


def _steps_appeared_at(document: dict, turns: list[dict]) -> int:
    """Where an older step list belongs: just after the reception burst, before later chat."""
    times = [turn["createdAt"] for turn in turns if isinstance(turn.get("createdAt"), int)]
    created = document.get("createdAt") if isinstance(document.get("createdAt"), int) else 0
    if not times:
        return created or now_ms()
    burst_end = times[0]
    for previous, current in zip(times, times[1:]):
        if current - previous > 5000:
            break
        burst_end = current
    return burst_end + 1


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
        except ModelLimitError as exc:
            messages(self.settings).delete_one({"_id": user_turn["_id"]})
            raise falcon.HTTPTooManyRequests(description=str(exc)) from exc
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
        begin_start(self.settings, req.remote_addr or "")
        handed = False
        try:
            reserve_hosted(self.settings)
            try:
                plan_messages = [
                    {"role": "system", "content": "You write build plans. Reply with one short step per line and nothing else."},
                    *({"role": turn["role"], "content": turn["content"]} for turn in turns),
                    {"role": "user", "content": PLAN_REQUEST},
                ]
                try:
                    plan = _plan_lines(_ask_model(self.settings, self.services, plan_messages))
                except ModelLimitError as exc:
                    raise falcon.HTTPTooManyRequests(description=str(exc)) from exc
                except InferenceError as exc:
                    raise falcon.HTTPBadGateway(description=str(exc)) from exc
                chosen = known_profile(read_json(req).get("profile"))
                if chosen is None:
                    raise falcon.HTTPBadRequest(description="Choose a box")
                document = begin_hosted_app(self.settings, user["_id"], prompt, chosen)
            finally:
                release_hosted_reservation()
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
            steps = _provision_steps(plan, stamp + len(copies))
            record_progress(self.settings, app_id, steps, stamp + len(copies))
            apps(self.settings).update_one({"_id": app_id}, {"$set": {"build.steps": steps, "prompt": prompt}})

            def run(app_id: str = app_id) -> None:
                try:
                    boot_hosted_app(self.settings, app_id, self.services.runner, self.services.healthy)
                except Exception:
                    log.exception("App %s did not finish starting", app_id)
                finally:
                    release_turn()

            self.services.spawn(run)
            handed = True
            resp.status = falcon.HTTP_201
            resp.media = {"id": app_id, "steps": steps, "boxReady": False}
        finally:
            if not handed:
                release_turn()


class AppShare:
    """Let another account open the app without asking the builder to change it."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @_guard
    def on_post(self, req: falcon.Request, resp: falcon.Response, app_id: str) -> None:
        user = signed_in_user(self.settings)
        document = _load_app(self.settings, app_id, user, owner_only=True)
        body = read_json(req)
        email = body.get("email")
        shared = body.get("shared")
        if email not in ACCOUNT_EMAILS or not isinstance(shared, bool):
            raise falcon.HTTPBadRequest(description="Choose who can open this app")
        person = users(self.settings).find_one({"email": email})
        if person is None or person["_id"] == user["_id"]:
            raise falcon.HTTPBadRequest(description="Choose someone else")
        change = {"$addToSet": {"sharedWith": person["_id"]}} if shared else {"$pull": {"sharedWith": person["_id"]}}
        apps(self.settings).update_one({"_id": document["_id"]}, change)
        document = apps(self.settings).find_one({"_id": document["_id"]}) or document
        resp.media = {"shares": _share_rows(self.settings, document, user)}


class AppBuild:
    def __init__(self, settings: Settings, services) -> None:
        self.settings = settings
        self.services = services

    @_guard
    def on_post(self, req: falcon.Request, resp: falcon.Response, app_id: str) -> None:
        user = signed_in_user(self.settings)
        document = _load_app(self.settings, app_id, user, owner_only=True)
        app_id = document["_id"]
        if not (document.get("runtime") or {}).get("boxReady"):
            raise falcon.HTTPConflict(description="The container is not ready")
        if document.get("status") != "live":
            claimed = apps(self.settings).update_one(
                {"_id": app_id, "runtime.buildStarted": {"$ne": True}},
                {"$set": {"runtime.buildStarted": True, "updatedAt": now_ms()}},
            )
            if claimed.modified_count and self.services is not None:
                begin_start(self.settings, req.remote_addr or "")

                def run(app_id: str = app_id) -> None:
                    try:
                        build_in_container(
                            self.settings,
                            app_id,
                            self.services.runner,
                            self.services.hermes,
                            self.services.healthy,
                            self.services.infer,
                        )
                    except Exception:
                        log.exception("App %s did not finish building", app_id)
                    finally:
                        release_turn()

                try:
                    self.services.spawn(run)
                except Exception:
                    release_turn()
                    raise
        resp.status = falcon.HTTP_202
        resp.media = {"id": app_id}


class AppPersist:
    """Turn a temporary app into a demo app when the admin code matches."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @_guard
    def on_post(self, req: falcon.Request, resp: falcon.Response, app_id: str) -> None:
        user = signed_in_user(self.settings)
        document = _load_app(self.settings, app_id, user, owner_only=True)
        code = read_json(req).get("code")
        if not isinstance(code, str) or not admin_code_matches(self.settings, code):
            raise falcon.HTTPForbidden(description="That code does not persist this app")
        apps(self.settings).update_one(
            {"_id": document["_id"]},
            {"$set": {"demo": True, "updatedAt": now_ms()}, "$unset": {"expiresAt": ""}},
        )
        resp.media = {"demo": True, "expiresAt": None}
