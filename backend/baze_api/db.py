"""MongoDB client for users, apps, drafts, and conversations."""

from __future__ import annotations

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from baze_api.settings import Settings

_client: MongoClient | None = None
_db_name: str | None = None


def get_client(settings: Settings) -> MongoClient:
    global _client, _db_name
    if _client is None or _db_name != settings.mongo_db:
        _client = MongoClient(
            host=settings.mongo_host,
            port=settings.mongo_port,
            username=settings.mongo_username,
            password=settings.mongo_password,
            authSource=settings.mongo_auth_source,
            directConnection=True,
            serverSelectionTimeoutMS=3000,
        )
        _db_name = settings.mongo_db
        database = _client[settings.mongo_db]
        database.conversations.create_index([("updatedAt", -1)])
        database.users.create_index("email", unique=True)
        database.apps.create_index([("ownerId", 1), ("sort", 1)])
        database.apps.create_index("slug", unique=True)
        database.apps.create_index("draftKey", unique=True, sparse=True)
        database.drafts.create_index([("ownerId", 1), ("updatedAt", -1)])
    return _client


def get_db(settings: Settings) -> Database:
    return get_client(settings)[settings.mongo_db]


def conversations(settings: Settings) -> Collection:
    return get_db(settings).conversations


def users(settings: Settings) -> Collection:
    return get_db(settings).users


def apps(settings: Settings) -> Collection:
    return get_db(settings).apps


def drafts(settings: Settings) -> Collection:
    return get_db(settings).drafts
