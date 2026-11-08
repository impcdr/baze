"""Falcon application factory."""

from __future__ import annotations

import falcon

from baze_api.app_proxy import AppProxy
from baze_api.middleware import AuthMiddleware, CorsMiddleware, CurrentUserMiddleware
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
    AppBuild,
    AppDecision,
    AppFiles,
    AppManage,
    AppSecretRead,
    AppSecrets,
    AppShare,
    AppPersist,
    AppPower,
    AppPrompt,
    AppRecord,
    Creator,
    CreatorMake,
    CreatorMessages,
    CreatorReset,
    Workspace,
)
from baze_api.resources import Conversation, Conversations, Health, Messages, ServiceInfo
from baze_api.runtime import RuntimeApp, RuntimeApps, RuntimeMessages, RuntimeServices
from baze_api.seed import ensure_seed
from baze_api.settings import Settings, load_settings
from baze_api.static import StaticFiles


def create_app(settings: Settings | None = None, services: RuntimeServices | None = None) -> falcon.App:
    settings = settings or load_settings()
    services = services or RuntimeServices.production()
    ensure_seed(settings)
    app = falcon.App(middleware=[CurrentUserMiddleware(), CorsMiddleware(), AuthMiddleware(settings), AppProxy(settings)])
    app.add_route("/api/health", Health(settings))
    app.add_route("/api", ServiceInfo())
    app.add_route("/api/account", Account(settings))
    app.add_route("/api/home", Home(settings))
    app.add_route("/api/presets", Presets())
    app.add_route("/api/apps", Shelf(settings, services))
    app.add_route("/api/apps/{app_id}", AppRecord(settings, services))
    app.add_route("/api/shared", SharedShelf(settings))
    app.add_route("/api/apps/{app_id}/workspace", Workspace(settings))
    app.add_route("/api/apps/{app_id}/power/{action}", AppPower(settings, services.runner, services.healthy))
    app.add_route("/api/apps/{app_id}/prompt", AppPrompt(settings, services.hermes, services))
    app.add_route("/api/apps/{app_id}/decisions", AppDecision(settings, services))
    app.add_route("/api/apps/{app_id}/files", AppFiles(settings))
    app.add_route("/api/apps/{app_id}/secrets/{secret_id}", AppSecretRead(settings))
    app.add_route("/api/apps/{app_id}/secrets", AppSecrets(settings))
    app.add_route("/api/apps/{app_id}/manage", AppManage(settings))
    app.add_route("/api/apps/{app_id}/share", AppShare(settings))
    app.add_route("/api/apps/{app_id}/persist", AppPersist(settings))
    app.add_route("/api/apps/{app_id}/build", AppBuild(settings, services))
    app.add_route("/api/creator", Creator(settings))
    app.add_route("/api/creator/messages", CreatorMessages(settings, services))
    app.add_route("/api/creator/make", CreatorMake(settings, services))
    app.add_route("/api/creator/reset", CreatorReset(settings))
    app.add_route("/api/drafts", Drafts(settings))
    app.add_route("/api/drafts/{draft_id}", Draft(settings))
    app.add_route("/api/drafts/{draft_id}/messages", DraftMessages(settings))
    app.add_route("/api/drafts/{draft_id}/publish", DraftPublish(settings))
    app.add_route("/api/drafts/{draft_id}/share", DraftShare(settings))
    app.add_route("/api/conversations", Conversations(settings))
    app.add_route("/api/conversations/{conversation_id}", Conversation(settings))
    app.add_route("/api/conversations/{conversation_id}/messages", Messages(settings))
    app.add_route("/api/runtime/apps", RuntimeApps(settings, services))
    app.add_route("/api/runtime/apps/{app_id}", RuntimeApp(settings, services))
    app.add_route("/api/runtime/apps/{app_id}/messages", RuntimeMessages(settings, services))
    app.add_sink(StaticFiles(settings.frontend_dist), prefix="/")
    return app
