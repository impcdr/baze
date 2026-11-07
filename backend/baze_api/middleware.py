"""CORS and bearer-token checks."""

from __future__ import annotations

import secrets

import falcon

from baze_api.settings import Settings

PUBLIC_PATHS = {"/api/health", "/api"}
PUBLIC_PREFIXES = ("/api/account", "/api/home", "/api/presets", "/api/apps", "/api/shared", "/api/drafts")


class CorsMiddleware:
    def process_request(self, req: falcon.Request, resp: falcon.Response) -> None:
        if req.method == "OPTIONS":
            resp.status = falcon.HTTP_204
            resp.complete = True

    def process_response(self, req: falcon.Request, resp: falcon.Response, resource, req_succeeded: bool) -> None:
        resp.set_header("Access-Control-Allow-Origin", "*")
        resp.set_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        resp.set_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
        resp.set_header("Access-Control-Max-Age", "600")
        resp.set_header("X-Content-Type-Options", "nosniff")


class AuthMiddleware:
    def __init__(self, settings: Settings) -> None:
        self._token = settings.api_token

    def process_request(self, req: falcon.Request, resp: falcon.Response) -> None:
        if req.method == "OPTIONS" or not req.path.startswith("/api"):
            return
        if req.path in PUBLIC_PATHS or any(
            req.path == prefix or req.path.startswith(prefix + "/") for prefix in PUBLIC_PREFIXES
        ):
            return
        header = req.get_header("Authorization") or ""
        scheme, _, given = header.partition(" ")
        if scheme.lower() != "bearer" or not given or not secrets.compare_digest(given, self._token):
            raise falcon.HTTPUnauthorized(
                title="Unauthorized",
                description="Bearer token required",
                challenges=["Bearer"],
            )
