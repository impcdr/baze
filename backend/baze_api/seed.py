"""Insert the signed-in user and the product catalog once."""

from __future__ import annotations

import copy

from baze_api.catalog import USER_COLOR, USER_EMAIL, USER_INITIALS, USER_INK, USER_NAME, catalog_apps, catalog_drafts
from baze_api.db import apps, drafts, users
from baze_api.http import new_id, now_ms
from baze_api.settings import Settings


def ensure_seed(settings: Settings) -> None:
    if users(settings).find_one({"email": USER_EMAIL}, {"_id": 1}):
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
