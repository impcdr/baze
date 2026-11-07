"""Falcon application factory."""

from __future__ import annotations

import falcon

from baze_api.middleware import AuthMiddleware, CorsMiddleware
from baze_api.product import (
    Account,
    Draft,
    DraftMessages,
    DraftPublish,
    DraftShare,
    Drafts,
    Home,
    Presets,
    SharedShelf,
    Shelf,
    Workspace,
)
from baze_api.resources import Conversation, Conversations, Health, Messages, ServiceInfo
from baze_api.seed import ensure_seed
from baze_api.settings import Settings, load_settings
from baze_api.static import StaticFiles


def create_app(settings: Settings | None = None) -> falcon.App:
    settings = settings or load_settings()
    ensure_seed(settings)
    app = falcon.App(middleware=[CorsMiddleware(), AuthMiddleware(settings)])
    app.add_route("/api/health", Health(settings))
    app.add_route("/api", ServiceInfo())
    app.add_route("/api/account", Account(settings))
    app.add_route("/api/home", Home(settings))
    app.add_route("/api/presets", Presets())
    app.add_route("/api/apps", Shelf(settings))
    app.add_route("/api/shared", SharedShelf(settings))
    app.add_route("/api/apps/{app_id}/workspace", Workspace(settings))
    app.add_route("/api/drafts", Drafts(settings))
    app.add_route("/api/drafts/{draft_id}", Draft(settings))
    app.add_route("/api/drafts/{draft_id}/messages", DraftMessages(settings))
    app.add_route("/api/drafts/{draft_id}/publish", DraftPublish(settings))
    app.add_route("/api/drafts/{draft_id}/share", DraftShare(settings))
    app.add_route("/api/conversations", Conversations(settings))
    app.add_route("/api/conversations/{conversation_id}", Conversation(settings))
    app.add_route("/api/conversations/{conversation_id}/messages", Messages(settings))
    app.add_sink(StaticFiles(settings.frontend_dist), prefix="/")
    return app
