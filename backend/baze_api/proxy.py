"""OpenAI-compatible proxy. Containers call it; only this process holds the Vultr key."""

from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from baze_api.db import apps
from baze_api.docker import bridge_gateway
from baze_api.settings import Settings

log = logging.getLogger("baze.proxy")

CHAT_PATH = "/v1/chat/completions"
MODELS_PATH = "/v1/models"


def token_from(headers: dict[str, str]) -> str:
    header = headers.get("Authorization") or headers.get("authorization") or ""
    scheme, _, given = header.partition(" ")
    if scheme.lower() != "bearer":
        return ""
    return given.strip()


def prepare_upstream(settings: Settings, body: bytes) -> tuple[str, dict[str, str], bytes]:
    payload: dict = {}
    if body:
        parsed = json.loads(body.decode("utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("Expected a JSON object")
        payload = parsed
    payload["model"] = settings.model_id
    payload.setdefault("reasoning_effort", settings.reasoning_effort)
    encoded = json.dumps(payload).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {settings.vultr_api_key}",
        "Content-Type": "application/json",
        "Content-Length": str(len(encoded)),
    }
    base = settings.vultr_base_url.rstrip("/")
    if base.endswith("/v1"):
        url = f"{base}/chat/completions"
    else:
        url = f"{base}{CHAT_PATH}"
    return url, headers, encoded


def models_body(settings: Settings) -> bytes:
    return json.dumps(
        {"object": "list", "data": [{"id": settings.model_id, "object": "model", "owned_by": "baze"}]}
    ).encode("utf-8")


def proxy_request(
    *,
    method: str,
    path: str,
    headers: dict[str, str],
    body: bytes,
    settings: Settings,
    token_ok,
    forward=None,
) -> tuple[int, dict[str, str], bytes]:
    if not token_ok(token_from(headers)):
        return 401, {"Content-Type": "application/json"}, b'{"error":"proxy token required"}'
    if method == "GET" and path == MODELS_PATH:
        payload = models_body(settings)
        return 200, {"Content-Type": "application/json", "Content-Length": str(len(payload))}, payload
    if method != "POST" or path != CHAT_PATH:
        return 404, {"Content-Type": "application/json"}, b'{"error":"not found"}'
    if not settings.vultr_api_key:
        return 503, {"Content-Type": "application/json"}, b'{"error":"inference key is not configured"}'
    try:
        url, upstream_headers, upstream_body = prepare_upstream(settings, body)
    except (UnicodeError, json.JSONDecodeError, ValueError):
        return 400, {"Content-Type": "application/json"}, b'{"error":"expected a JSON object"}'
    if forward is None:
        return _forward(url, upstream_headers, upstream_body)
    status, response_headers, response_body = forward(url, upstream_headers, upstream_body)
    return status, response_headers, response_body


class InferenceError(RuntimeError):
    pass


def complete_chat(settings: Settings, messages: list[dict]) -> str:
    """Call Vultr from this process. The browser never sees the key."""
    if not settings.vultr_api_key:
        raise InferenceError("Inference is not configured")
    try:
        url, headers, payload = prepare_upstream(settings, json.dumps({"messages": messages}).encode("utf-8"))
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise InferenceError("The model did not answer") from exc
    status, _, raw = _forward(url, headers, payload)
    if status != 200:
        raise InferenceError("The model did not answer")
    try:
        text = json.loads(raw.decode("utf-8"))["choices"][0]["message"]["content"]
    except (UnicodeError, json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise InferenceError("The model did not answer") from exc
    if not isinstance(text, str) or not text.strip():
        raise InferenceError("The model did not answer")
    return text.strip()


def _forward(url: str, headers: dict[str, str], body: bytes) -> tuple[int, dict[str, str], bytes]:
    request = Request(url, data=body, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=300) as response:
            return response.status, {"Content-Type": response.headers.get("Content-Type", "application/json")}, response.read()
    except HTTPError as exc:
        return exc.code, {"Content-Type": "application/json"}, exc.read()
    except URLError:
        return 502, {"Content-Type": "application/json"}, b'{"error":"upstream unavailable"}'


def db_token_ok(settings: Settings, token: str) -> bool:
    if not token:
        return False
    return apps(settings).find_one({"runtime.proxyToken": token}, {"_id": 1}) is not None


class _Handler(BaseHTTPRequestHandler):
    settings: Settings
    token_ok = staticmethod(db_token_ok)

    def log_message(self, fmt: str, *args) -> None:
        log.info("%s - %s", self.address_string(), fmt % args)

    def do_GET(self) -> None:
        self._serve()

    def do_POST(self) -> None:
        self._serve()

    def _serve(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        path = self.path.split("?", 1)[0]
        status, headers, payload = proxy_request(
            method=self.command,
            path=path,
            headers={key: value for key, value in self.headers.items()},
            body=body,
            settings=self.settings,
            token_ok=lambda token: self.token_ok(self.settings, token),
        )
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        if "Content-Length" not in headers:
            self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def start_proxy(settings: Settings) -> ThreadingHTTPServer | None:
    if not settings.vultr_api_key:
        log.warning("inference proxy not started: VULTR_INFERENCE_API_KEY is unset")
        return None
    host = bridge_gateway()
    _Handler.settings = settings
    try:
        server = ThreadingHTTPServer((host, settings.proxy_port), _Handler)
    except OSError as exc:
        log.error("inference proxy failed to bind %s:%s (%s)", host, settings.proxy_port, exc)
        return None
    threading.Thread(target=server.serve_forever, name="baze-inference", daemon=True).start()
    log.info("inference proxy on http://%s:%s", host, settings.proxy_port)
    return server
