"""Shared HTTP helpers."""

from __future__ import annotations

import re
import uuid

import falcon

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def read_json(req: falcon.Request) -> dict:
    if not req.content_length:
        return {}
    try:
        body = req.media
    except (falcon.MediaNotFoundError, falcon.MediaMalformedError) as exc:
        raise falcon.HTTPBadRequest(description="Expected a JSON object") from exc
    if not isinstance(body, dict):
        raise falcon.HTTPBadRequest(description="Expected a JSON object")
    return body


def parse_id(conversation_id: str) -> str:
    if not UUID_RE.match(conversation_id):
        raise falcon.HTTPNotFound(description="Conversation not found")
    return conversation_id


def new_id() -> str:
    return str(uuid.uuid4())


def now_ms() -> int:
    import time

    return int(time.time() * 1000)


def clean_title(value: object, *, required: bool) -> str | None:
    if value is None:
        if required:
            raise falcon.HTTPBadRequest(description="Title is required")
        return None
    if not isinstance(value, str):
        raise falcon.HTTPBadRequest(description="Title must be a string")
    title = " ".join(value.split())
    if not title:
        raise falcon.HTTPBadRequest(description="Title is required")
    if len(title) > 200:
        raise falcon.HTTPBadRequest(description="Title is too long")
    return title


def clean_content(value: object) -> str:
    if not isinstance(value, str):
        raise falcon.HTTPBadRequest(description="Content must be a string")
    content = value.strip()
    if not content:
        raise falcon.HTTPBadRequest(description="Content is required")
    if len(content) > 20_000:
        raise falcon.HTTPBadRequest(description="Content is too long")
    return content


def public_message(message: dict) -> dict:
    return {
        "id": message["id"],
        "role": message["role"],
        "content": message["content"],
        "createdAt": message["createdAt"],
    }


def public_conversation(document: dict) -> dict:
    return {
        "id": document["_id"],
        "title": document["title"],
        "createdAt": document["createdAt"],
        "updatedAt": document["updatedAt"],
        "messages": [public_message(message) for message in document.get("messages", [])],
    }
