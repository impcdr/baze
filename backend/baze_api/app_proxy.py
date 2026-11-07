"""Shelf status, and the public path that serves each app's container."""

from __future__ import annotations

import re
from http import HTTPStatus
from urllib import error, request

import falcon

from baze_api.app_favicon import render_app_favicon
from baze_api.catalog import STUDIO_ID
from baze_api.db import apps
from baze_api.http import now_ms
from baze_api.settings import Settings

_APP_PATH = re.compile(r"^/([0-9a-f]{32})(/.*)?$")
_FAVICON_PATH = re.compile(r"^/favicon\.(?:svg|ico)$")
_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}
_PASS_HEADERS = ("Content-Type", "Location", "Cache-Control", "Content-Disposition")


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = request.build_opener(_NoRedirect)


def clear_fake_live(settings: Settings) -> None:
    """Shelf apps are not Live unless a container is actually serving them."""
    for document in apps(settings).find({"kind": {"$ne": "runtime"}, "status": "live"}):
        labels = [label for label in document.get("labels") or [] if label.get("text") != "Live"]
        apps(settings).update_one(
            {"_id": document["_id"]},
            {
                "$set": {
                    "status": "stopped",
                    "statusLabel": "",
                    "labels": labels,
                    "updatedAt": now_ms(),
                }
            },
        )


def mark_studio_live(settings: Settings) -> None:
    document = apps(settings).find_one({"_id": STUDIO_ID})
    if document is None:
        return
    labels = [label for label in document.get("labels") or [] if label.get("text") != "Live"]
    labels.append({"text": "Live", "tone": "success"})
    apps(settings).update_one(
        {"_id": STUDIO_ID},
        {"$set": {"status": "live", "statusLabel": "Live", "labels": labels, "updatedAt": now_ms()}},
    )


class AppProxy:
    """Serve /{app id} from that app's container. The shelf stays a navigator."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def process_request(self, req: falcon.Request, resp: falcon.Response) -> None:
        match = _APP_PATH.match(req.path)
        if match is None:
            return
        document = apps(self.settings).find_one({"_id": match.group(1), "kind": {"$ne": "runtime"}})
        if document is None:
            return
        suffix = match.group(2) or "/"
        if req.method in ("GET", "HEAD") and _FAVICON_PATH.match(suffix):
            _favicon(resp, document)
            return
        runtime = document.get("runtime") or {}
        port = runtime.get("hostPort")
        if document.get("status") != "live" or not isinstance(port, int):
            _plain(resp, falcon.HTTP_503, f"{document.get('name') or 'This app'} is off.")
            return
        if req.method in ("GET", "HEAD") and not match.group(2):
            resp.status = falcon.HTTP_302
            resp.set_header("Location", f"/{match.group(1)}/")
            resp.complete = True
            return
        target = f"http://127.0.0.1:{port}{suffix}"
        if req.query_string:
            target = f"{target}?{req.query_string}"
        headers = {
            key: value
            for key, value in req.headers.items()
            if key.lower() not in _HOP_HEADERS
        }
        headers["Host"] = f"127.0.0.1:{port}"
        body = req.bounded_stream.read() if req.content_length else None
        upstream = request.Request(target, data=body or None, headers=headers, method=req.method)
        try:
            with _OPENER.open(upstream, timeout=30) as result:
                _relay(resp, result.status, result.headers, result.read())
        except error.HTTPError as exc:
            _relay(resp, exc.code, exc.headers, exc.read())
        except (OSError, error.URLError):
            _plain(resp, falcon.HTTP_502, "The app is not answering.")


def _favicon(resp: falcon.Response, document: dict) -> None:
    payload = render_app_favicon(document.get("color") or "", document.get("icon") or "").encode()
    resp.status = falcon.HTTP_200
    resp.content_type = "image/svg+xml"
    resp.data = payload
    resp.cache_control = ["no-cache"]
    resp.complete = True


def _plain(resp: falcon.Response, status: str, text: str) -> None:
    resp.status = status
    resp.content_type = "text/plain; charset=utf-8"
    resp.text = text
    resp.complete = True


def _relay(resp: falcon.Response, status: int, headers, payload: bytes) -> None:
    try:
        phrase = HTTPStatus(status).phrase
    except ValueError:
        phrase = "Unknown"
    resp.status = f"{status} {phrase}"
    resp.data = payload
    if headers is not None:
        for key in _PASS_HEADERS:
            value = headers.get(key)
            if value:
                resp.set_header(key, value)
    resp.complete = True
