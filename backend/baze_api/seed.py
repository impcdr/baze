"""Insert the signed-in user and the product catalog once."""

from __future__ import annotations

import copy

from baze_api.catalog import (
    RETIRED_APP_IDS,
    USER_COLOR,
    USER_EMAIL,
    USER_INITIALS,
    USER_INK,
    USER_NAME,
    catalog_apps,
    catalog_drafts,
)
from baze_api.db import apps, drafts, users
from baze_api.http import new_id, now_ms
from baze_api.settings import Settings


def ensure_seed(settings: Settings) -> None:
    if users(settings).find_one({"email": USER_EMAIL}, {"_id": 1}):
        reconcile_catalog(settings)
        return
    stamp = now_ms()
    user_id = new_id()
    users(settings).insert_one(
        {
            "_id": user_id,
            "email": USER_EMAIL,
            "name": USER_NAME,
            "initials": USER_INITIALS,
            "color": USER_COLOR,
            "ink": USER_INK,
            "createdAt": stamp,
            "updatedAt": stamp,
        }
    )
    owned_apps = []
    for app in catalog_apps():
        document = copy.deepcopy(app)
        document["ownerId"] = user_id
        document["createdAt"] = stamp
        document["updatedAt"] = stamp
        owned_apps.append(document)
    apps(settings).insert_many(owned_apps)
    owned_drafts = []
    for draft in catalog_drafts():
        document = copy.deepcopy(draft)
        document["ownerId"] = user_id
        document["createdAt"] = stamp
        document["updatedAt"] = stamp
        owned_drafts.append(document)
    drafts(settings).insert_many(owned_drafts)
    reconcile_catalog(settings)


def reconcile_catalog(settings: Settings) -> None:
    """The shelf is only the apps that have their own container."""
    user = users(settings).find_one({"email": USER_EMAIL}, {"_id": 1})
    if user is None:
        return
    apps(settings).delete_many({"ownerId": user["_id"], "_id": {"$in": RETIRED_APP_IDS}})
    drafts(settings).delete_many({"ownerId": user["_id"], "_id": "shifts"})
    stamp = now_ms()
    for app in catalog_apps():
        current = apps(settings).find_one({"_id": app["_id"], "ownerId": user["_id"]}, {"_id": 1})
        if current is None:
            continue
        apps(settings).update_one(
            {"_id": app["_id"]},
            {
                "$set": {
                    "name": app["name"],
                    "slug": app["slug"],
                    "summary": app["summary"],
                    "detail": app["detail"],
                    "path": app["path"],
                    "external": True,
                    "icon": app["icon"],
                    "color": app["color"],
                    "preset": app["preset"],
                    "sort": app["sort"],
                    "sharedBy": None,
                    "updatedAt": stamp,
                }
            },
        )
