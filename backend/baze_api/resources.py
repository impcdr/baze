"""Conversation resources stored in MongoDB."""

from __future__ import annotations

import re

import falcon
from pymongo import ReturnDocument
from pymongo.errors import PyMongoError

from baze_api.db import conversations, get_client
from baze_api.http import (
    clean_content,
    clean_title,
    new_id,
    now_ms,
    parse_id,
    public_conversation,
    public_message,
    read_json,
)
from baze_api.replies import reply_for, title_from
from baze_api.settings import Settings


def _guard(fn):
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except falcon.HTTPError:
            raise
        except PyMongoError as exc:
            raise falcon.HTTPServiceUnavailable(description="Database unavailable") from exc

    return wrapper


class Health:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        mongo = "ok"
        try:
            get_client(self.settings).admin.command("ping")
        except PyMongoError:
            mongo = "unavailable"
            resp.status = falcon.HTTP_503
        index = self.settings.frontend_dist / "index.html"
        resp.media = {
            "status": "ok" if mongo == "ok" else "degraded",
            "mongo": mongo,
            "frontend": "ready" if index.is_file() else "missing",
        }


class ServiceInfo:
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        resp.media = {
            "name": "baze",
            "auth": "Authorization: Bearer <API_TOKEN from /home/agent/.env>",
            "frontend": "/",
            "chat": "/chat",
            "endpoints": [
                {"method": "GET", "path": "/api/health", "auth": False},
                {"method": "GET", "path": "/api/conversations", "auth": True},
                {"method": "POST", "path": "/api/conversations", "auth": True, "body": {"title": "optional"}},
                {"method": "GET", "path": "/api/conversations/{id}", "auth": True},
                {"method": "PATCH", "path": "/api/conversations/{id}", "auth": True, "body": {"title": "string"}},
                {"method": "DELETE", "path": "/api/conversations/{id}", "auth": True},
                {
                    "method": "POST",
                    "path": "/api/conversations/{id}/messages",
                    "auth": True,
                    "body": {"content": "string"},
                },
            ],
        }


class Conversations:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @_guard
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        query = (req.get_param("q") or "").strip()
        if len(query) > 200:
            raise falcon.HTTPBadRequest(description="Search query is too long")
        try:
            limit = int(req.get_param("limit") or 100)
        except ValueError as exc:
            raise falcon.HTTPBadRequest(description="Limit must be an integer") from exc
        limit = min(max(limit, 1), 200)
        filt: dict = {}
        if query:
            pattern = re.escape(query)
            filt = {
                "$or": [
                    {"title": {"$regex": pattern, "$options": "i"}},
                    {"messages.content": {"$regex": pattern, "$options": "i"}},
                ]
            }
        documents = conversations(self.settings).find(filt).sort("updatedAt", -1).limit(limit)
        resp.media = {"conversations": [public_conversation(document) for document in documents]}

    @_guard
    def on_post(self, req: falcon.Request, resp: falcon.Response) -> None:
        body = read_json(req)
        title = clean_title(body.get("title"), required=False) or "New chat"
        stamp = now_ms()
        document = {
            "_id": new_id(),
            "title": title,
            "createdAt": stamp,
            "updatedAt": stamp,
            "messages": [],
        }
        conversations(self.settings).insert_one(document)
        resp.status = falcon.HTTP_201
        resp.media = public_conversation(document)


class Conversation:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @_guard
    def on_get(self, req: falcon.Request, resp: falcon.Response, conversation_id: str) -> None:
        document = self._load(conversation_id)
        resp.media = public_conversation(document)

    @_guard
    def on_patch(self, req: falcon.Request, resp: falcon.Response, conversation_id: str) -> None:
        conversation_id = parse_id(conversation_id)
        title = clean_title(read_json(req).get("title"), required=True)
        document = conversations(self.settings).find_one_and_update(
            {"_id": conversation_id},
            {"$set": {"title": title}},
            return_document=ReturnDocument.AFTER,
        )
        if document is None:
            raise falcon.HTTPNotFound(description="Conversation not found")
        resp.media = public_conversation(document)

    @_guard
    def on_delete(self, req: falcon.Request, resp: falcon.Response, conversation_id: str) -> None:
        conversation_id = parse_id(conversation_id)
        result = conversations(self.settings).delete_one({"_id": conversation_id})
        if result.deleted_count == 0:
            raise falcon.HTTPNotFound(description="Conversation not found")
        resp.status = falcon.HTTP_204

    def _load(self, conversation_id: str) -> dict:
        document = conversations(self.settings).find_one({"_id": parse_id(conversation_id)})
        if document is None:
            raise falcon.HTTPNotFound(description="Conversation not found")
        return document


class Messages:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @_guard
    def on_post(self, req: falcon.Request, resp: falcon.Response, conversation_id: str) -> None:
        conversation_id = parse_id(conversation_id)
        content = clean_content(read_json(req).get("content"))
        stamp = now_ms()
        user = {"id": new_id(), "role": "user", "content": content, "createdAt": stamp}
        assistant = {
            "id": new_id(),
            "role": "assistant",
            "content": reply_for(content),
            "createdAt": stamp + 1,
        }
        existing = conversations(self.settings).find_one({"_id": conversation_id}, {"title": 1, "messages.role": 1})
        if existing is None:
            raise falcon.HTTPNotFound(description="Conversation not found")
        has_user = any(message.get("role") == "user" for message in existing.get("messages", []))
        title = existing.get("title") or "New chat"
        if not has_user and title == "New chat":
            title = title_from(content)
        document = conversations(self.settings).find_one_and_update(
            {"_id": conversation_id},
            {
                "$set": {"title": title, "updatedAt": stamp},
                "$push": {"messages": {"$each": [user, assistant]}},
            },
            return_document=ReturnDocument.AFTER,
        )
        if document is None:
            raise falcon.HTTPNotFound(description="Conversation not found")
        resp.status = falcon.HTTP_201
        resp.media = {
            "conversation": public_conversation(document),
            "user": public_message(user),
            "assistant": public_message(assistant),
        }
