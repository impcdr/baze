"""Serve the built Angular app without modifying the frontend tree."""

from __future__ import annotations

from pathlib import Path

import falcon

CONTENT_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".ico": "image/x-icon",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json",
    ".map": "application/json",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".txt": "text/plain; charset=utf-8",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
}


class StaticFiles:
    def __init__(self, dist: Path) -> None:
        self.dist = dist

    def __call__(self, req: falcon.Request, resp: falcon.Response) -> None:
        if req.method != "GET":
            raise falcon.HTTPMethodNotAllowed(allowed_methods=["GET"])
        if req.path.startswith("/api"):
            raise falcon.HTTPNotFound()

        relative = req.path.lstrip("/")
        if relative == "":
            self._send(resp, self.dist / "index.html")
            return

        candidate = self._safe(relative)
        if candidate is not None and candidate.is_file():
            self._send(resp, candidate)
            return

        # Client-side routes such as /apps have no file extension.
        if "." not in Path(relative).name:
            index = self.dist / "index.html"
            if index.is_file():
                self._send(resp, index)
                return
        raise falcon.HTTPNotFound()

    def _safe(self, relative: str) -> Path | None:
        root = self.dist.resolve()
        candidate = (root / relative).resolve()
        if not candidate.is_relative_to(root):
            return None
        return candidate

    def _send(self, resp: falcon.Response, path: Path) -> None:
        if not path.is_file():
            raise falcon.HTTPNotFound()
        resp.data = path.read_bytes()
        resp.content_type = CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")
        resp.cache_control = ["no-cache"]
