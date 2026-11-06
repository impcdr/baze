"""Falcon application factory."""

from __future__ import annotations

import falcon

from kiln_api.middleware import AuthMiddleware, CorsMiddleware
from kiln_api.resources import Conversation, Conversations, Health, Messages, ServiceInfo
from kiln_api.settings import Settings, load_settings
from kiln_api.static import StaticFiles


def create_app(settings: Settings | None = None) -> falcon.App:
    settings = settings or load_settings()
    app = falcon.App(middleware=[CorsMiddleware(), AuthMiddleware(settings)])
    app.add_route("/api/health", Health(settings))
    app.add_route("/api", ServiceInfo())
    app.add_route("/api/conversations", Conversations(settings))
    app.add_route("/api/conversations/{conversation_id}", Conversation(settings))
    app.add_route("/api/conversations/{conversation_id}/messages", Messages(settings))
    app.add_sink(StaticFiles(settings.frontend_dist), prefix="/")
    return app
